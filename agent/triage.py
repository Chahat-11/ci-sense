import argparse
import fnmatch
import io
import json
import keyword
import os
import re
import zipfile

import requests
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
RUN_ID = os.environ.get("RUN_ID")
REPO = os.environ.get("GITHUB_REPOSITORY")

API = "https://api.github.com"
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}
GROQ_MODEL = os.environ.get("GROQ_MODEL") or "openai/gpt-oss-120b"


def get_run():
    resp = requests.get(f"{API}/repos/{REPO}/actions/runs/{RUN_ID}", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_pr_number(run):
    owner = REPO.split("/")[0]
    resp = requests.get(
        f"{API}/repos/{REPO}/pulls",
        headers=HEADERS,
        params={"head": f"{owner}:{run['head_branch']}", "state": "open"},
        timeout=30,
    )
    resp.raise_for_status()
    prs = resp.json()
    if prs:
        return prs[0]["number"]
    return None


def post_comment(pr_number, body):
    resp = requests.post(
        f"{API}/repos/{REPO}/issues/{pr_number}/comments",
        headers=HEADERS,
        json={"body": body},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_failed_jobs(run_id):
    resp = requests.get(f"{API}/repos/{REPO}/actions/runs/{run_id}/jobs", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return [job for job in resp.json()["jobs"] if job["conclusion"] == "failure"]


def get_run_logs(run_id):
    resp = requests.get(f"{API}/repos/{REPO}/actions/runs/{run_id}/logs", headers=HEADERS, timeout=60)
    resp.raise_for_status()
    parts = []
    with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
        for name in sorted(archive.namelist()):
            if name.endswith(".txt"):
                parts.append(archive.read(name).decode("utf-8", errors="replace"))
    return "\n".join(parts)


ERROR_PATTERN = re.compile(r"(Error|Traceback|FAILED|assert|Exception)", re.IGNORECASE)


def strip_timestamps(text):
    return re.sub(r"^\d{4}-\d{2}-\d{2}T[\d:.]+Z\s?", "", text, flags=re.MULTILINE)


def distill_error(log_text):
    log_text = strip_timestamps(log_text)
    lines = log_text.splitlines()
    windows = []
    for i, line in enumerate(lines):
        if ERROR_PATTERN.search(line):
            start, end = max(0, i - 2), min(len(lines), i + 7)
            if windows and start <= windows[-1][1]:
                windows[-1][1] = max(windows[-1][1], end)
            else:
                windows.append([start, end])
    if not windows:
        return log_text[-2000:]
    return "\n---\n".join("\n".join(lines[start:end]) for start, end in windows)


def get_last_success_sha(branch):
    resp = requests.get(
        f"{API}/repos/{REPO}/actions/workflows/test.yml/runs",
        headers=HEADERS,
        params={"branch": branch, "status": "success", "per_page": 1},
        timeout=30,
    )
    resp.raise_for_status()
    runs = resp.json()["workflow_runs"]
    if runs:
        return runs[0]["head_sha"]
    return None


def get_commits_since(branch, since_sha):
    resp = requests.get(
        f"{API}/repos/{REPO}/commits",
        headers=HEADERS,
        params={"sha": branch, "per_page": 20},
        timeout=30,
    )
    resp.raise_for_status()
    commits = [c for c in resp.json() if len(c["parents"]) <= 1]
    if since_sha is None:
        return commits[:5]
    candidates = []
    for commit in commits:
        if commit["sha"] == since_sha:
            break
        candidates.append(commit)
    return candidates


def get_candidate_commits(base, head):
    """Non-merge commits in base...head; base and head can be branch names or shas."""
    resp = requests.get(f"{API}/repos/{REPO}/compare/{base}...{head}", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return [
        {"sha": c["sha"], "message": c["commit"]["message"]}
        for c in resp.json()["commits"]
        if len(c["parents"]) <= 1
    ]


def get_commit_pr(sha):
    resp = requests.get(f"{API}/repos/{REPO}/commits/{sha}/pulls", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    prs = resp.json()
    if prs:
        return prs[0]["number"]
    return None


def get_commit_diff(sha):
    resp = requests.get(f"{API}/repos/{REPO}/commits/{sha}", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    files = data.get("files", [])
    return {
        "sha": data["sha"],
        "message": data["commit"]["message"],
        "files": [f["filename"] for f in files],
        "patch": "\n".join(f.get("patch", "") for f in files)[:3000],
    }


IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
NOISE_WORDS = {"assert", "error", "failed", "where", "test", "tests", "passed"}
CONFIG_FILE_PATTERNS = ["requirements*.txt", "*.toml", "*.cfg", "*.ini", "*.yml", "*.yaml", ".env*"]
CONFIG_ERROR_PATTERN = re.compile(r"ModuleNotFoundError|ImportError|KeyError|config", re.IGNORECASE)


def score_candidate(detail, error_text):
    score, reasons = 0, []

    for path in detail["files"]:
        basename = os.path.basename(path)
        if path in error_text or basename in error_text:
            score += 3
            reasons.append(f"touches {path} named in error")
            break

    error_idents = {
        word for word in IDENTIFIER_PATTERN.findall(error_text)
        if word not in keyword.kwlist and word.lower() not in NOISE_WORDS
    }
    changed_lines = "\n".join(
        line[1:] for line in detail["patch"].splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    )
    matched = sorted(error_idents & set(IDENTIFIER_PATTERN.findall(changed_lines)))
    if matched:
        score += 2
        reasons.append(f"changed lines mention {', '.join(matched[:5])}")

    touches_config = any(
        fnmatch.fnmatch(os.path.basename(path), pattern)
        for path in detail["files"] for pattern in CONFIG_FILE_PATTERNS
    )
    if touches_config and CONFIG_ERROR_PATTERN.search(error_text):
        score += 2
        reasons.append("touches config/dependency files and error looks config-related")

    return {"score": score, "reasons": reasons}


SYSTEM_PROMPT = (
    "You are a CI failure triage assistant. You receive a distilled CI error and a list of "
    "candidate commits, each with sha, message, changed files, a deterministic score with "
    "reasons, and a truncated patch. Identify which commit most likely caused the failure. "
    "The failing line may be in one commit while the root cause is in another; reason about "
    "interactions between commits. Respond ONLY with JSON with keys: what_failed, why, "
    "responsible_commit (must be a full sha copied from the candidates), confidence (0 to 1), "
    "suggested_fix, reasoning."
)


def fallback_verdict(scored_candidates):
    if not scored_candidates:
        return {
            "what_failed": "See the distilled error below.",
            "why": "No candidate commits were found for this run.",
            "responsible_commit": None,
            "confidence": None,
            "suggested_fix": "Inspect the distilled error manually.",
            "reasoning": "",
            "fallback": True,
        }
    best = max(scored_candidates, key=lambda c: c["score"])
    return {
        "what_failed": "See the distilled error below.",
        "why": "; ".join(best["reasons"]) or "No deterministic signal matched; picked by default.",
        "responsible_commit": best["sha"],
        "confidence": None,
        "suggested_fix": "Review the changes in the responsible commit against the error below.",
        "reasoning": "",
        "fallback": True,
    }


def llm_verdict(error_text, scored_candidates):
    if not GROQ_API_KEY or not scored_candidates:
        return fallback_verdict(scored_candidates)

    candidates_payload = [
        {
            "sha": c["sha"],
            "message": c["message"],
            "files": c["files"],
            "score": c["score"],
            "reasons": c["reasons"],
            "patch": c["patch"][:1500],
        }
        for c in scored_candidates
    ]
    user_message = (
        f"Distilled CI error:\n{error_text}\n\n"
        f"Candidate commits:\n{json.dumps(candidates_payload, indent=2)}"
    )

    try:
        from groq import Groq

        response = Groq(api_key=GROQ_API_KEY).chat.completions.create(
            model=GROQ_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
        )
        verdict = json.loads(response.choices[0].message.content)
    except Exception as exc:
        print(f"LLM verdict unavailable ({type(exc).__name__}); using deterministic scoring.")
        return fallback_verdict(scored_candidates)

    if verdict.get("responsible_commit") not in {c["sha"] for c in scored_candidates}:
        print("LLM returned a sha outside the candidate set; using deterministic scoring.")
        return fallback_verdict(scored_candidates)
    verdict["fallback"] = False
    return verdict


def build_comment(verdict, scored_candidates, distilled, header=None):
    by_sha = {c["sha"]: c for c in scored_candidates}
    responsible = by_sha.get(verdict["responsible_commit"])
    if responsible is None:
        commit_line = "none identified"
    else:
        confidence = verdict.get("confidence")
        confidence_text = f"{round(float(confidence) * 100)}%" if confidence is not None else "n/a"
        commit_line = (
            f"`{responsible['sha'][:7]}` — {responsible['message'].splitlines()[0]} "
            f"(confidence {confidence_text})"
        )

    lines = [header, ""] if header else []
    lines += [
        "## 🤖 CI-Sense triage",
        f"**What failed:** {verdict.get('what_failed', '')}",
        f"**Why:** {verdict.get('why', '')}",
        f"**Responsible commit:** {commit_line}",
        f"**Suggested fix:** {verdict.get('suggested_fix', '')}",
    ]
    if verdict.get("fallback"):
        lines.append("")
        lines.append("_Verdict is from deterministic scoring only (LLM verdict unavailable)._")

    table = ["| Commit | Score | Reasons |", "| --- | --- | --- |"]
    for c in scored_candidates:
        reasons = "; ".join(c["reasons"]).replace("|", "\\|") or "—"
        table.append(f"| `{c['sha'][:7]}` | {c['score']} | {reasons} |")

    lines += [
        "",
        "<details><summary>Evidence</summary>",
        "",
        *table,
        "",
        f"```\n{distilled[:1500]}\n```",
        "",
        "</details>",
    ]
    return "\n".join(lines)


def normalize_repo(value):
    value = re.sub(r"^(https?://)?(www\.)?github\.com/", "", value.strip())
    return value.removesuffix(".git").strip("/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CI-Sense failure triage")
    parser.add_argument("--local", metavar="RUN_ID", help="triage this run and print the comment instead of posting it")
    args = parser.parse_args()

    if args.local:
        RUN_ID = args.local
        if not REPO:
            REPO = normalize_repo(os.environ["GITHUB_REPO"])

    run = get_run()
    pr_number = get_pr_number(run)

    if pr_number is not None:
        resp = requests.get(f"{API}/repos/{REPO}/pulls/{pr_number}", headers=HEADERS, timeout=30)
        resp.raise_for_status()
        base_ref = resp.json()["base"]["ref"]
        print(f"PR #{pr_number}: comparing {base_ref}...{run['head_sha'][:7]}")
        commits = get_candidate_commits(base_ref, run["head_sha"])
    else:
        branch = run["head_branch"]
        last_good_sha = get_last_success_sha(branch)
        print(f"Last good sha on {branch}: {last_good_sha}")
        if last_good_sha:
            commits = get_candidate_commits(last_good_sha, run["head_sha"])
        else:
            commits = get_commits_since(branch, None)
    candidates = [get_commit_diff(c["sha"]) for c in commits]
    print(f"Candidate commits: {[c['sha'][:7] for c in candidates]}")

    header = None
    if pr_number is None:
        since = f"since last green run `{last_good_sha[:7]}`" if last_good_sha else "(no previous green run found)"
        header = (
            f"Failure on `{branch}` at `{run['head_sha'][:7]}` — "
            f"{len(candidates)} candidate commits {since}."
        )

    distilled = distill_error(get_run_logs(RUN_ID))
    scored = [{**c, **score_candidate(c, distilled)} for c in candidates]
    verdict = llm_verdict(distilled, scored)
    body = build_comment(verdict, scored, distilled, header)

    posts = []
    if pr_number is not None:
        posts.append((pr_number, body))
    else:
        guilty_sha = verdict["responsible_commit"]
        guilty_pr = get_commit_pr(guilty_sha) if guilty_sha else None
        print(f"Guilty PR: {guilty_pr}")
        if guilty_pr is None:
            print("Could not find the PR that introduced the responsible commit; not posting.\n")
            print(body)
        else:
            posts.append((guilty_pr, body))
            head_pr = get_commit_pr(run["head_sha"])
            if head_pr is not None and head_pr != guilty_pr:
                note = (
                    f"🤖 CI-Sense: this failure on main was attributed to #{guilty_pr} "
                    f"(`{guilty_sha[:7]}`), not to this PR. Details in #{guilty_pr}."
                )
                posts.append((head_pr, note))

    for target, text in posts:
        if args.local:
            print(f"\n=== Would post to PR #{target} ===\n{text}")
        else:
            post_comment(target, text)
            print(f"Posted triage comment on PR #{target}.")
