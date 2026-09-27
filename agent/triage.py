import os

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


if __name__ == "__main__":
    run = get_run()
    pr_number = get_pr_number(run)
    if pr_number is None:
        print(f"Run {RUN_ID} is not associated with a pull request; skipping comment.")
    else:
        post_comment(pr_number, "🤖 CI-Sense: pipeline failure detected, triage in progress.")
        print(f"Posted triage comment on PR #{pr_number}.")
