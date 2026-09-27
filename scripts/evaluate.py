"""Score CI-Sense verdicts on seeded PRs against seeds/ground_truth.json.

    python scripts/evaluate.py          # score whatever triage comments exist now
    python scripts/evaluate.py --wait   # poll every 30s until nothing is pending (max 10 minutes)
"""

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
GROUND_TRUTH = ROOT / "seeds" / "ground_truth.json"
RESULTS = ROOT / "seeds" / "results.json"
API = "https://api.github.com"
BOT = "github-actions[bot]"
DATA_PATTERN = re.compile(r"<!-- ci-sense-data (.*?) -->", re.DOTALL)
POLL_SECONDS, WAIT_LIMIT_SECONDS = 30, 600


def resolve_repo():
    repo = os.environ.get("GITHUB_REPOSITORY") or os.environ.get("GITHUB_REPO")
    if not repo:
        repo = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout
    repo = re.sub(r"^(https?://|git@)?(www\.)?github\.com[/:]", "", repo.strip())
    return repo.removesuffix(".git").strip("/")


def latest_triage_data(repo, pr_number):
    headers = {
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN'].strip()}",
        "Accept": "application/vnd.github+json",
    }
    url, comments = f"{API}/repos/{repo}/issues/{pr_number}/comments?per_page=100", []
    while url:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        comments += resp.json()
        url = resp.links.get("next", {}).get("url")
    triage = [c for c in comments if c["user"]["login"] == BOT and "ci-sense-data" in c["body"]]
    if not triage:
        return None
    latest = max(triage, key=lambda c: c["created_at"])
    return json.loads(DATA_PATTERN.search(latest["body"]).group(1))


def classify(case, data):
    if data is None:
        return "pending"
    verdict = data.get("responsible_commit")
    if not verdict or str(verdict).lower() == "none":
        return "abstained"
    return "correct" if verdict == case["guilty_sha"] else "wrong"


def evaluate(repo, truth):
    rows = []
    for case in truth["cases"]:
        data = latest_triage_data(repo, case["pr_number"])
        rows.append({
            "case": case["case"],
            "category": case["category"],
            "pr_number": case["pr_number"],
            "expected_sha": case["guilty_sha"],
            "verdict_sha": (data or {}).get("responsible_commit"),
            "confidence": (data or {}).get("confidence"),
            "source": None if data is None else ("fallback" if data.get("fallback") else "llm"),
            "fallback_reason": (data or {}).get("fallback_reason"),
            "result": classify(case, data),
        })
    return rows


def average(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 3) if values else None


def summarize(rows):
    counts = {k: sum(r["result"] == k for r in rows) for k in ("correct", "wrong", "abstained", "pending")}
    completed = [r for r in rows if r["result"] != "pending"]
    return {
        "cases": len(rows),
        "completed": len(completed),
        "accuracy": round(counts["correct"] / len(completed), 3) if completed else None,
        "counts": counts,
        "llm": sum(r["source"] == "llm" for r in rows),
        "fallback": sum(r["source"] == "fallback" for r in rows),
        "avg_confidence_correct": average(r["confidence"] for r in rows if r["result"] == "correct"),
        "avg_confidence_wrong": average(r["confidence"] for r in rows if r["result"] == "wrong"),
    }


def short(sha):
    return str(sha)[:7] if sha else "—"


def print_report(rows, summary):
    header = f"{'case':<5} {'category':<22} {'expected':<9} {'verdict':<9} {'conf':>5}  {'source':<9} result"
    print(header)
    print("-" * len(header))
    for r in rows:
        conf = f"{r['confidence']:.2f}" if isinstance(r["confidence"], (int, float)) else "—"
        print(f"{r['case']:<5} {r['category']:<22} {short(r['expected_sha']):<9} {short(r['verdict_sha']):<9} "
              f"{conf:>5}  {r['source'] or '—':<9} {r['result']}")
    s = summary
    acc = f"{s['accuracy']:.0%}" if s["accuracy"] is not None else "n/a"
    print(f"\nAccuracy: {acc} ({s['counts']['correct']}/{s['completed']} completed cases)")
    print("Counts: " + ", ".join(f"{k} {v}" for k, v in s["counts"].items()))
    print(f"Verdict source: LLM {s['llm']}, fallback {s['fallback']}")
    print(f"Avg confidence: correct {s['avg_confidence_correct']}, wrong {s['avg_confidence_wrong']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--wait", action="store_true", help="poll every 30s until no case is pending (max 10 min)")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    repo = resolve_repo()
    truth = json.loads(GROUND_TRUTH.read_text())

    deadline = time.monotonic() + WAIT_LIMIT_SECONDS
    while True:
        rows = evaluate(repo, truth)
        pending = sum(r["result"] == "pending" for r in rows)
        if not args.wait or not pending or time.monotonic() >= deadline:
            break
        print(f"{pending} case(s) pending; checking again in {POLL_SECONDS}s")
        time.sleep(POLL_SECONDS)

    summary = summarize(rows)
    print_report(rows, summary)
    RESULTS.write_text(json.dumps({"summary": summary, "cases": rows}, indent=2) + "\n")
    print(f"\nWrote {RESULTS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
