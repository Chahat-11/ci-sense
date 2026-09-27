import argparse
import datetime
import fnmatch
import io
import json
import keyword
import os
import re
import time
import zipfile

import requests
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
RUN_ID = os.environ.get("RUN_ID")
REPO = os.environ.get("GITHUB_REPOSITORY")

API = "https://api.github.com"
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}
GROQ_MODEL = os.environ.get("GROQ_MODEL") or "openai/gpt-oss-120b"


def get_run(run_id):
    resp = requests.get(f"{API}/repos/{REPO}/actions/runs/{run_id}", headers=HEADERS, timeout=30)
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


SECRET_PATTERN = re.compile(r"\b(gsk_|ghp_|gho_|ghs_|ghu_|github_pat_)[A-Za-z0-9_]+")


def redact_secrets(text):
    """Scrub API keys/tokens by pattern and by exact value, so escaped or partial echoes can't leak."""
    text = SECRET_PATTERN.sub(r"\1[REDACTED]", text)
    for secret in (GROQ_API_KEY, GITHUB_TOKEN):
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def post_comment(pr_number, body):
    resp = requests.post(
        f"{API}/repos/{REPO}/issues/{pr_number}/comments",
        headers=HEADERS,
        json={"body": redact_secrets(body)},
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
    cleanup = re.search(r"^.*Post job cleanup", log_text, flags=re.MULTILINE)
    if cleanup:
        log_text = log_text[:cleanup.start()]
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
CONFIG_ERROR_PATTERN = re.compile(r"ModuleNotFoundError|ImportError|KeyError|(?<!git )\bconfig\b", re.IGNORECASE)


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
    "responsible_commit (must be a full sha copied from the candidates, or \"none\" if no "
    "candidate plausibly caused the failure), confidence (0 to 1), "
    "suggested_fix, reasoning."
)


def fallback_verdict(scored_candidates, reason=None):
    verdict = _fallback_verdict(scored_candidates)
    verdict["fallback_reason"] = reason
    return verdict


def _fallback_verdict(scored_candidates):
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
    if best["score"] == 0:
        return {
            "what_failed": "See the distilled error below.",
            "why": "No candidate commit matched any deterministic signal.",
            "responsible_commit": None,
            "confidence": None,
            "suggested_fix": "Inspect the distilled error and the candidates below manually.",
            "reasoning": "",
            "fallback": True,
        }
    return {
        "what_failed": "See the distilled error below.",
        "why": "; ".join(best["reasons"]) or "No deterministic signal matched; picked by default.",
        "responsible_commit": best["sha"],
        "confidence": None,
        "suggested_fix": "Review the changes in the responsible commit against the error below.",
        "reasoning": "",
        "fallback": True,
    }


LLM_ATTEMPTS = 3
LLM_RETRY_WAITS = [2, 5]


def is_transient_groq_error(exc, groq):
    if isinstance(exc, (groq.APIConnectionError, groq.APITimeoutError, groq.RateLimitError)):
        return True
    return isinstance(exc, groq.APIStatusError) and exc.status_code >= 500


def log_llm_fallback(reason, exc=None):
    key_status = f"key present, length {len(GROQ_API_KEY)}" if GROQ_API_KEY else "key empty"
    if exc is not None:
        reason = f"{reason}: {type(exc).__name__}: {exc}"
        if exc.__cause__ is not None:
            reason += f" (cause: {type(exc.__cause__).__name__}: {exc.__cause__})"
    reason = redact_secrets(reason)
    message = f"{reason} [{key_status}]"
    print(f"LLM verdict unavailable — {message}; using deterministic scoring.")
    return message


def llm_verdict(error_text, scored_candidates):
    if not GROQ_API_KEY:
        return fallback_verdict(scored_candidates, log_llm_fallback("GROQ_API_KEY not set"))
    if not scored_candidates:
        return fallback_verdict(scored_candidates, log_llm_fallback("no candidate commits to judge"))

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
        import groq

        # max_retries=0: the retry loop below is the only retry layer
        client = groq.Groq(api_key=GROQ_API_KEY, timeout=30, max_retries=0)
    except Exception as exc:
        return fallback_verdict(scored_candidates, log_llm_fallback("could not create Groq client", exc))

    for attempt in range(1, LLM_ATTEMPTS + 1):
        content = None
        try:
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
            )
            content = response.choices[0].message.content
            verdict = json.loads(content)
            break
        except Exception as exc:
            if attempt < LLM_ATTEMPTS and is_transient_groq_error(exc, groq):
                print(f"LLM attempt {attempt} failed ({type(exc).__name__}), retrying")
                time.sleep(LLM_RETRY_WAITS[attempt - 1])
                continue
            if content is not None:
                reason = log_llm_fallback(f"unparseable response {content[:500]!r}", exc)
            else:
                reason = log_llm_fallback(f"Groq call failed on attempt {attempt}", exc)
            return fallback_verdict(scored_candidates, reason)

    responsible = verdict.get("responsible_commit")
    if responsible is None or str(responsible).strip().lower() == "none":
        verdict["responsible_commit"] = None
    elif responsible not in {c["sha"] for c in scored_candidates}:
        reason = log_llm_fallback(
            f"responsible_commit {responsible!r} is not a candidate sha; raw response {content[:500]!r}"
        )
        return fallback_verdict(scored_candidates, reason)
    verdict["fallback"] = False
    verdict["fallback_reason"] = None
    return verdict


def build_comment(verdict, scored_candidates, distilled, header=None):
    by_sha = {c["sha"]: c for c in scored_candidates}
    responsible = by_sha.get(verdict["responsible_commit"])
    if responsible is None:
        commit_line = "could not attribute with confidence"
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


def with_hidden_data(text, result):
    """Append the result as an HTML comment; "--" is escaped so the JSON can't close the comment."""
    data = json.dumps(result, ensure_ascii=False).replace("--", "-\\u002d")
    return f"{text}\n\n<!-- ci-sense-data {data} -->"


VERDICT_FIELDS = ["what_failed", "why", "responsible_commit", "confidence", "suggested_fix", "reasoning"]


def run_pipeline(run_id, post=False, progress=None):
    """Triage one failed run. Returns (result, comment_body); posts to GitHub only when post=True.

    progress(stage, status, preview) is called with status "start" when a stage begins and
    "done" (plus a small preview dict of its output) when it finishes.
    """

    def stage(name, status="start", preview=None):
        if progress:
            progress(name, status, preview)

    run = get_run(run_id)
    pr_number = get_pr_number(run)

    stage("fetching logs")
    log_text = get_run_logs(run_id)
    stage("fetching logs", "done", {"log_lines": log_text.count("\n") + 1, "log_bytes": len(log_text)})

    stage("distilling")
    distilled = distill_error(log_text)
    stage("distilling", "done", {"lines": distilled.count("\n") + 1, "preview": distilled[:600]})

    stage("finding candidates")
    branch, last_good_sha = run["head_branch"], None
    if pr_number is not None:
        resp = requests.get(f"{API}/repos/{REPO}/pulls/{pr_number}", headers=HEADERS, timeout=30)
        resp.raise_for_status()
        base_ref = resp.json()["base"]["ref"]
        print(f"PR #{pr_number}: comparing {base_ref}...{run['head_sha'][:7]}")
        commits = get_candidate_commits(base_ref, run["head_sha"])
    else:
        last_good_sha = get_last_success_sha(branch)
        print(f"Last good sha on {branch}: {last_good_sha}")
        if last_good_sha:
            commits = get_candidate_commits(last_good_sha, run["head_sha"])
        else:
            commits = get_commits_since(branch, None)
    candidates = [get_commit_diff(c["sha"]) for c in commits]
    print(f"Candidate commits: {[c['sha'][:7] for c in candidates]}")
    stage("finding candidates", "done", {
        "count": len(candidates),
        "pr_number": pr_number,
        "last_good_sha": last_good_sha,
        "head_sha": run["head_sha"],
        "candidates": [{"sha": c["sha"], "message": c["message"].splitlines()[0]} for c in candidates],
    })

    header = None
    if pr_number is None:
        since = f"since last green run `{last_good_sha[:7]}`" if last_good_sha else "(no previous green run found)"
        header = (
            f"Failure on `{branch}` at `{run['head_sha'][:7]}` — "
            f"{len(candidates)} candidate commits {since}."
        )

    stage("scoring")
    scored = [{**c, **score_candidate(c, distilled)} for c in candidates]
    stage("scoring", "done", {
        "scores": [{"sha": c["sha"], "score": c["score"], "reasons": c["reasons"]} for c in scored],
    })

    stage("LLM verdict")
    verdict = llm_verdict(distilled, scored)
    stage("LLM verdict", "done", {
        "responsible_commit": verdict["responsible_commit"],
        "confidence": verdict.get("confidence"),
        "fallback": verdict["fallback"],
    })
    body = build_comment(verdict, scored, distilled, header)
    guilty_sha = verdict["responsible_commit"]
    guilty_pr = get_commit_pr(guilty_sha) if guilty_sha else None

    result = {
        "run_id": int(run_id),
        "pr_number": pr_number,
        "guilty_pr": guilty_pr,
        "head_sha": run["head_sha"],
        "last_good_sha": last_good_sha,
        "candidates": [
            {k: c[k] for k in ("sha", "message", "files", "score", "reasons")} for c in scored
        ],
        **{k: verdict.get(k) for k in VERDICT_FIELDS},
        "fallback": verdict["fallback"],
        "fallback_reason": verdict["fallback_reason"],
        "model": GROQ_MODEL,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "distilled_error": distilled[:1500],
    }

    posts = []
    if pr_number is not None:
        posts.append((pr_number, body))
    else:
        print(f"Guilty PR: {guilty_pr}")
        if guilty_pr is None:
            if guilty_sha is None:
                print("No commit could be attributed with confidence; not posting.\n")
            else:
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

    if posts:
        stage("posting")
    for target, text in posts:
        text = with_hidden_data(text, result)
        if post:
            post_comment(target, text)
            print(f"Posted triage comment on PR #{target}.")
        else:
            print(f"\n=== Would post to PR #{target} ===\n{text}")
    if posts:
        stage("posting", "done", {"targets": [target for target, _ in posts], "posted": post})

    return result, body


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CI-Sense failure triage")
    parser.add_argument("--local", metavar="RUN_ID", help="triage this run and print the comment instead of posting it")
    args = parser.parse_args()

    if args.local:
        if not REPO:
            REPO = normalize_repo(os.environ["GITHUB_REPO"])
        run_pipeline(args.local, post=False)
    else:
        run_pipeline(RUN_ID, post=True)
