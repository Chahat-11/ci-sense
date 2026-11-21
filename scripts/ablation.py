"""Replay every seeded failure through each pipeline variant and score against seeds/ground_truth.json.

    python scripts/ablation.py [--runs 3]

Variants: last_commit (naive baseline), deterministic (scoring only), llm, llm_sourcegraph.
LLM variants are repeated --runs times to expose nondeterminism. Nothing is posted to GitHub.
Needs GITHUB_TOKEN, GITHUB_REPO, GROQ_API_KEY and (for llm_sourcegraph) SRC_ACCESS_TOKEN in .env.
Writes seeds/ablation.json.
"""

import argparse
import contextlib
import io
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
os.environ.setdefault("GITHUB_REPOSITORY", os.environ.get("GITHUB_REPO", "").removeprefix("https://github.com/").removesuffix(".git"))
sys.path.insert(0, str(ROOT / "agent"))
import triage  # noqa: E402

VARIANTS = ["last_commit", "deterministic", "llm", "llm_sourcegraph"]
LLM_VARIANTS = {"llm", "llm_sourcegraph"}


def failed_run_id(pr_number):
    pr = requests.get(f"{triage.API}/repos/{triage.REPO}/pulls/{pr_number}", headers=triage.HEADERS, timeout=30).json()
    runs = requests.get(f"{triage.API}/repos/{triage.REPO}/actions/workflows/test.yml/runs", headers=triage.HEADERS,
                        params={"head_sha": pr["head"]["sha"], "per_page": 5}, timeout=30).json()["workflow_runs"]
    failed = [r for r in runs if r["conclusion"] == "failure"]
    return failed[0]["id"] if failed else None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=int, default=3, help="repetitions for LLM variants")
    args = parser.parse_args()
    truth = json.loads((ROOT / "seeds" / "ground_truth.json").read_text())

    rows = []
    for case in truth["cases"]:
        run_id = failed_run_id(case["pr_number"])
        if run_id is None:
            print(f"case {case['case']}: no failed run found, skipping")
            continue
        for variant in VARIANTS:
            for rep in range(args.runs if variant in LLM_VARIANTS else 1):
                with contextlib.redirect_stdout(io.StringIO()):
                    result, _ = triage.run_pipeline(run_id, post=False, mode=variant)
                if variant in LLM_VARIANTS and result["fallback"]:
                    sys.exit(f"case {case['case']} {variant}: LLM unavailable, so this run would silently measure the "
                             f"deterministic fallback. Reason: {result['fallback_reason']}")
                sha = result["responsible_commit"]
                outcome = "abstained" if not sha else ("correct" if sha == case["guilty_sha"] else "wrong")
                rows.append({"case": case["case"], "category": case["category"], "variant": variant, "rep": rep,
                             "outcome": outcome, "confidence": result["confidence"], "fallback": result["fallback"],
                             "n_candidates": len(result["candidates"]),
                             "sourcegraph_chars": result.get("sourcegraph_chars", 0)})
                print(f"case {case['case']} {variant:<16} rep {rep} {outcome}")

    def wilson(k, n, z=1.96):
        if not n:
            return None
        p = k / n
        d = 1 + z * z / n
        centre = (p + z * z / (2 * n)) / d
        half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
        return [round(max(0, centre - half), 3), round(min(1, centre + half), 3)]

    def stats(subset):
        n = len(subset)
        k = sum(r["outcome"] == "correct" for r in subset)
        return {"n": n, "correct": k, "wrong": sum(r["outcome"] == "wrong" for r in subset),
                "abstained": sum(r["outcome"] == "abstained" for r in subset),
                "accuracy": round(k / n, 3) if n else None, "ci95": wilson(k, n)}

    summary, multi, by_category, by_case = {}, {}, {}, {}
    for variant in VARIANTS:
        vr = [r for r in rows if r["variant"] == variant and r["rep"] == 0]  # one run per case: reps are not independent
        summary[variant] = {**stats(vr), "all_runs": stats([r for r in rows if r["variant"] == variant])}
        multi[variant] = stats([r for r in vr if r["n_candidates"] > 1])
        by_category[variant] = {c: stats([r for r in vr if r["category"] == c]) for c in sorted({r["category"] for r in vr})}
        by_case[variant] = {c: stats([r for r in vr if r["case"] == c]) for c in sorted({r["case"] for r in vr})}
    sg = [r for r in rows if r["variant"] == "llm_sourcegraph"]  # all reps
    sourcegraph_usage = {"runs": len(sg), "runs_with_context": sum(r["sourcegraph_chars"] > 0 for r in sg),
                         "cases_with_context": sorted({r["case"] for r in sg if r["sourcegraph_chars"] > 0})}
    summary_out = {"summary": summary, "multi_commit_only": multi, "by_category": by_category,
                   "by_case": by_case, "sourcegraph_usage": sourcegraph_usage}
    summary = summary_out
    print("\n" + json.dumps(summary, indent=2))
    (ROOT / "seeds" / "ablation.json").write_text(json.dumps({**summary, "rows": rows}, indent=2) + "\n")


if __name__ == "__main__":
    main()
