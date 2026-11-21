"""Mine real CI failures from open-source GitHub repos into a labelled triage benchmark.

For each repo, pull-request workflow runs are grouped by (head repo, branch, workflow) and scanned for
the pattern  success @ S  ->  failure @ F  ->  success @ G  (each later sha a descendant of the earlier).

  candidates   every non-merge commit in the PR up to F, as CI-Sense's PR mode sees them (the commits up to
               S already passed CI, so they are real decoys); the guilty one must be in S..F
  fix          the single non-merge commit in F..G  (what turned CI green again)
  label        SZZ: blame the lines the fix deleted or changed, restricted to S..F. The case is kept only
               when those lines all come from exactly one candidate. Failures whose fix touches no
               candidate line (flaky tests, infra, upstream breakage) are dropped automatically.

The failing run's real log is downloaded while GitHub still retains it (about 90 days).
Writes bench/real_cases.jsonl and bench/real_logs/<id>.txt.gz. Read-only on GitHub.

    python scripts/mine_real.py                          # default repo list
    python scripts/mine_real.py --repos encode/httpx pallets/click --since 2026-09-01
"""

import argparse
import datetime
import gzip
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "bench" / "real_cases.jsonl"
LOGS = ROOT / "bench" / "real_logs"
API = "https://api.github.com"
DEFAULT_REPOS = [
    "pydantic/pydantic", "marshmallow-code/marshmallow", "pallets/click", "python-attrs/attrs", "encode/httpx",
    "Textualize/rich", "Textualize/textual", "fastapi/fastapi", "pytest-dev/pytest", "aio-libs/aiohttp",
    "scrapy/scrapy", "python-poetry/poetry", "pypa/pip", "sympy/sympy", "pallets/flask", "pallets/jinja",
]
MAX_CANDIDATES = 15
MAX_RUN_PAGES = 10

load_dotenv(ROOT / ".env", override=True)
SESSION = requests.Session()
SESSION.headers.update({"Authorization": f"Bearer {os.environ['GITHUB_TOKEN'].strip()}",
                        "Accept": "application/vnd.github+json"})


def gh(path, **params):
    resp = SESSION.get(f"{API}{path}", params=params, timeout=60)
    if resp.status_code in (404, 409, 410, 422):
        return None
    resp.raise_for_status()
    return resp


def git(cwd, *args, check=True):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:3])}: {result.stderr.strip()[:300]}")
    return result.stdout


def pr_runs(repo, since):
    """Pull-request workflow runs since `since`, newest first (capped at MAX_RUN_PAGES pages)."""
    runs = []
    for page in range(1, MAX_RUN_PAGES + 1):
        resp = gh(f"/repos/{repo}/actions/runs", event="pull_request", per_page=100, page=page,
                  created=f">={since}")
        batch = resp.json()["workflow_runs"] if resp else []
        runs += [r for r in batch if r["status"] == "completed" and r["conclusion"] in ("success", "failure")]
        if len(batch) < 100:
            break
    return runs


def compare(repo, base, head):
    resp = gh(f"/repos/{repo}/compare/{base}...{head}")
    return resp.json() if resp else None


def episodes(runs):
    """Yield (S, F, G): failure F followed by success G on the same branch and workflow.

    S is the previous run if it succeeded, or None when F is the branch's first run (then every PR commit
    up to F is a candidate, as in CI-Sense's PR mode). Episodes after an earlier failure are skipped."""
    groups = defaultdict(list)
    for r in runs:
        head_repo = (r.get("head_repository") or {}).get("full_name")
        groups[(head_repo, r["head_branch"], r["workflow_id"])].append(r)
    for group in groups.values():
        # one verdict per sha: a sha that both failed and passed (re-run) is flaky, so drop it
        by_sha = {}
        for r in sorted(group, key=lambda r: r["created_at"]):
            by_sha.setdefault(r["head_sha"], set()).add(r["conclusion"])
        order, seen = [], set()
        for r in sorted(group, key=lambda r: r["created_at"]):
            if r["head_sha"] not in seen and len(by_sha[r["head_sha"]]) == 1:
                seen.add(r["head_sha"])
                order.append(r)
        for i in range(len(order) - 1):
            f, g = order[i], order[i + 1]
            if (f["conclusion"], g["conclusion"]) != ("failure", "success"):
                continue
            if i == 0:
                yield None, f, g
            elif order[i - 1]["conclusion"] == "success":
                yield order[i - 1], f, g


def commit_detail(repo, sha):
    """Same shape as agent/triage.py get_commit_diff, so the eval sees exactly what CI-Sense sees."""
    data = gh(f"/repos/{repo}/commits/{sha}").json()
    files = data.get("files", [])
    return {"sha": data["sha"], "message": data["commit"]["message"], "files": [f["filename"] for f in files],
            "patch": "\n".join(f.get("patch", "") for f in files)[:3000]}


def failed_job_log(repo, run_id):
    """The failed jobs' logs from the run's log archive (whole run if job names can't be matched)."""
    resp = gh(f"/repos/{repo}/actions/runs/{run_id}/logs")
    if resp is None:
        return None
    jobs = gh(f"/repos/{repo}/actions/runs/{run_id}/jobs", per_page=100)
    failed = [j["name"] for j in (jobs.json()["jobs"] if jobs else []) if j["conclusion"] == "failure"]
    with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
        names = [n for n in sorted(archive.namelist()) if n.endswith(".txt")]
        top = [n for n in names if "/" not in n]
        keep = [n for n in top if any(name in n for name in failed)] or top or names
        return "\n".join(archive.read(n).decode("utf-8", errors="replace") for n in keep)


HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@")


def touched_old_lines(diff):
    """{path: [old line numbers deleted or changed]} from a unified diff (non-blank lines only)."""
    out, path, old = defaultdict(list), None, 0
    for line in diff.splitlines():
        if line.startswith("--- "):
            path = None if line[4:] == "/dev/null" else line[6:]
        elif (m := HUNK.match(line)):
            old = int(m.group(1))
        elif path and line.startswith("-") and not line.startswith("---"):
            if line[1:].strip():
                out[path].append(old)
            old += 1
        elif path and line.startswith(" "):
            old += 1
    return out


def szz(clone, s_sha, f_sha, g_sha, candidate_shas):
    """Candidate shas that introduced lines the fix (F..G) removed, blaming only within S..F."""
    diff = git(clone, "diff", "--no-color", "-U0", f_sha, g_sha, check=False)
    blamed = defaultdict(int)
    for path, lines in touched_old_lines(diff).items():
        for start in lines:
            out = git(clone, "blame", "-l", "-s", "-L", f"{start},{start}", f"{s_sha}..{f_sha}", "--", path, check=False)
            sha = out.split(" ", 1)[0].lstrip("^") if out else ""
            if sha in candidate_shas:
                blamed[sha] += 1
    return dict(blamed)


def ensure_commits(clone, shas, pr_number):
    missing = [s for s in shas if subprocess.run(["git", "cat-file", "-e", f"{s}^{{commit}}"], cwd=clone,
                                                 capture_output=True).returncode != 0]
    if not missing:
        return True
    refs = list(missing) + ([f"+refs/pull/{pr_number}/head:refs/remotes/pr/{pr_number}"] if pr_number else [])
    git(clone, "fetch", "-q", "--filter=blob:none", "origin", *refs, check=False)
    return all(subprocess.run(["git", "cat-file", "-e", f"{s}^{{commit}}"], cwd=clone,
                              capture_output=True).returncode == 0 for s in shas)


def pr_number_for(repo, run):
    if run.get("pull_requests"):
        return run["pull_requests"][0]["number"]
    head_repo = (run.get("head_repository") or {}).get("full_name")
    if head_repo and head_repo != repo:  # fork PR: run.pull_requests is empty, look up by owner:branch
        resp = gh(f"/repos/{repo}/pulls", head=f"{head_repo.split('/')[0]}:{run['head_branch']}", state="all")
    else:
        resp = gh(f"/repos/{repo}/commits/{run['head_sha']}/pulls")
    prs = resp.json() if resp else []
    return prs[0]["number"] if prs else None


def pr_candidates(repo, pr_number, f_sha):
    """All non-merge commits CI-Sense would consider for this PR at F (PR base...F), oldest first."""
    pr = gh(f"/repos/{repo}/pulls/{pr_number}") if pr_number else None
    span = compare(repo, pr.json()["base"]["sha"], f_sha) if pr else None
    if not span or span["status"] not in ("ahead", "diverged"):
        return None
    if any(len(c["parents"]) > 1 for c in span["commits"]):
        return None
    return [c["sha"] for c in span["commits"]]


def refresh(cases):
    """Recompute candidate lists of already-mined cases with the PR-wide rule (labels are unchanged)."""
    out = {}
    for case in cases.values():
        shas = pr_candidates(case["repo"], case["pr_number"], case["failing_sha"])
        if not shas or case["guilty_sha"] not in shas or len(shas) > MAX_CANDIDATES:
            print(f"   {case['id']}: could not rebuild PR candidates, dropped")
            continue
        case["commits"] = [commit_detail(case["repo"], sha) for sha in shas]
        case["n_commits"] = len(shas)
        case["difficulty"] = "easy" if len(shas) == 1 else "multi"
        out[case["id"]] = case
        print(f"   {case['id']}: {len(shas)} PR candidate(s)")
    return out


def mine_repo(repo, since, workdir, existing):
    print(f"\n== {repo}")
    runs = pr_runs(repo, since)
    found = list(episodes(runs))
    print(f"   {len(runs)} PR runs, {len(found)} fail->pass episodes")
    clone = Path(workdir, repo.replace("/", "__"))
    cases = []
    for s, f, g in found:
        case_id = f"{repo}#{f['id']}"
        if case_id in existing:
            continue
        pr_number = pr_number_for(repo, f)
        if s is not None:
            span = compare(repo, s["head_sha"], f["head_sha"])
        else:
            pr = gh(f"/repos/{repo}/pulls/{pr_number}") if pr_number else None
            span = compare(repo, pr.json()["base"]["sha"], f["head_sha"]) if pr else None
        fix_span = compare(repo, f["head_sha"], g["head_sha"])
        if not span or not fix_span or span["status"] != "ahead" or fix_span["status"] != "ahead":
            print(f"   {f['id']}: history not linear (force-push?), skipped")
            continue
        s_sha = s["head_sha"] if s is not None else span["merge_base_commit"]["sha"]
        if any(len(c["parents"]) > 1 for c in span["commits"] + fix_span["commits"]):
            print(f"   {f['id']}: contains a merge commit, skipped")
            continue
        candidates = [c["sha"] for c in span["commits"]]  # since last green: where the culprit must be
        fixes = [c["sha"] for c in fix_span["commits"]]
        if not candidates or len(candidates) > MAX_CANDIDATES or not 1 <= len(fixes) <= 3:
            print(f"   {f['id']}: {len(candidates)} candidates / {len(fixes)} fix commits, skipped")
            continue
        if not clone.exists():
            print("   cloning (partial)...")
            subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--no-checkout",
                            f"https://github.com/{repo}.git", str(clone)], capture_output=True)
        if not ensure_commits(clone, [s_sha, f["head_sha"], g["head_sha"]], pr_number):
            print(f"   {f['id']}: commits not fetchable, skipped")
            continue
        blamed = szz(clone, s_sha, f["head_sha"], g["head_sha"], set(candidates))
        if len(blamed) != 1:
            reason = "fix touches no candidate line (flaky/infra/additive fix)" if not blamed else \
                f"fix touches lines from {len(blamed)} candidates"
            print(f"   {f['id']}: {reason}, skipped")
            continue
        guilty = next(iter(blamed))
        pr_shas = pr_candidates(repo, pr_number, f["head_sha"])
        if not pr_shas or guilty not in pr_shas or len(pr_shas) > MAX_CANDIDATES:
            print(f"   {f['id']}: PR candidate list unusable, skipped")
            continue
        log = failed_job_log(repo, f["id"])
        if not log:
            print(f"   {f['id']}: log expired, skipped")
            continue
        LOGS.mkdir(parents=True, exist_ok=True)
        log_file = LOGS / f"{repo.replace('/', '__')}__{f['id']}.txt.gz"
        log_file.write_bytes(gzip.compress(log.encode()))
        fix = commit_detail(repo, fixes[-1])
        case = {
            "id": case_id, "repo": repo, "pr_number": pr_number, "workflow": f["name"],
            "run_id": f["id"], "run_url": f["html_url"], "last_green_sha": s and s["head_sha"],
            "base_sha": s_sha, "failing_sha": f["head_sha"], "fix_shas": fixes, "green_sha": g["head_sha"], "fix_message": fix["message"].splitlines()[0],
            "guilty_sha": guilty, "label_method": "szz", "szz_lines": blamed[guilty],
            "n_commits": len(pr_shas), "n_since_green": len(candidates), "category": "real",
            "difficulty": "easy" if len(pr_shas) == 1 else "multi",
            "commits": [commit_detail(repo, sha) for sha in pr_shas],
            "log_path": str(log_file.relative_to(ROOT)),
        }
        cases.append(case)
        print(f"   {f['id']}: kept, {len(candidates)} candidate(s), fix '{case['fix_message'][:60]}'")
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repos", nargs="+", default=DEFAULT_REPOS)
    parser.add_argument("--since", default=(datetime.date.today() - datetime.timedelta(days=85)).isoformat())
    parser.add_argument("--refresh", action="store_true", help="rebuild candidate lists of existing cases and exit")
    args = parser.parse_args()

    existing = {}
    if OUT.exists():
        existing = {c["id"]: c for c in map(json.loads, OUT.read_text().splitlines())}
    if args.refresh:
        existing = refresh(existing)
        OUT.write_text("".join(json.dumps(c) + "\n" for c in existing.values()))
        print(f"{len(existing)} cases, {sum(c['n_commits'] > 1 for c in existing.values())} with more than one candidate")
        return
    workdir = Path(tempfile.gettempdir(), "ci-sense-mine")
    workdir.mkdir(exist_ok=True)
    for repo in args.repos:
        try:
            for case in mine_repo(repo, args.since, workdir, existing):
                existing[case["id"]] = case
                OUT.write_text("".join(json.dumps(c) + "\n" for c in existing.values()))
        except Exception as exc:  # one bad repo should not stop the rest
            print(f"   {repo} failed: {type(exc).__name__}: {exc}")
    cases = list(existing.values())
    print(f"\n{len(cases)} real cases in {OUT.relative_to(ROOT)} "
          f"({sum(c['n_commits'] > 1 for c in cases)} with more than one candidate)")
    remaining = gh("/rate_limit").json()["resources"]["core"]["remaining"]
    print(f"GitHub API calls remaining this hour: {remaining}")


if __name__ == "__main__":
    main()
