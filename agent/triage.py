import io
import os
import re
import zipfile

import requests

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
RUN_ID = os.environ["RUN_ID"]
REPO = os.environ["GITHUB_REPOSITORY"]

API = "https://api.github.com"
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}


def get_run():
    resp = requests.get(f"{API}/repos/{REPO}/actions/runs/{RUN_ID}", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_pr_number(run):
    prs = run.get("pull_requests") or []
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


def distill_error(log_text):
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


if __name__ == "__main__":
    run = get_run()
    pr_number = get_pr_number(run)
    if pr_number is None:
        print(f"Run {RUN_ID} is not associated with a pull request; skipping comment.")
    else:
        failed_jobs = get_failed_jobs(RUN_ID)
        job_names = ", ".join(job["name"] for job in failed_jobs) or "unknown"
        distilled = distill_error(get_run_logs(RUN_ID))[:1500]
        body = (
            "🤖 CI-Sense: pipeline failure detected.\n\n"
            f"**Failed jobs:** {job_names}\n\n"
            f"```\n{distilled}\n```"
        )
        post_comment(pr_number, body)
        print(f"Posted triage comment on PR #{pr_number}.")
