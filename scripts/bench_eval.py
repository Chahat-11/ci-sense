"""Score CI-Sense on the synthetic benchmark (bench/cases.jsonl) without touching GitHub.

Each case's real pytest log and commits go through the same functions the CI agent uses:
distill_error -> score_candidate -> verdict. Variants:

  last_commit    naive baseline: blame the newest commit
  deterministic  scoring heuristics only (the agent's fallback)
  llm            scoring + Groq LLM verdict (what runs in CI, minus Sourcegraph)

    python scripts/bench_eval.py                    # all variants, all cases
    python scripts/bench_eval.py --limit 40         # first 40 cases only
    python scripts/bench_eval.py --variants llm     # just the LLM
    python scripts/bench_eval.py --set real         # real-repo cases from scripts/mine_real.py

LLM verdicts are cached in bench/runs.jsonl, so a run stopped by Groq's daily token limit resumes where
it left off. Writes bench/results.json.
"""

import argparse
import contextlib
import gzip
import io
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
SETS = {
    "synthetic": (ROOT / "bench" / "cases.jsonl", ROOT / "bench" / "runs.jsonl", ROOT / "bench" / "results.json"),
    "real": (ROOT / "bench" / "real_cases.jsonl", ROOT / "bench" / "real_runs.jsonl",
             ROOT / "bench" / "real_results.json"),
}
VARIANTS = ["last_commit", "deterministic", "llm"]
MAX_WAIT_SECONDS = 30 * 60

load_dotenv(ROOT / ".env", override=True)
os.environ.setdefault("GITHUB_TOKEN", "unused")
sys.path.insert(0, str(ROOT / "agent"))
import triage  # noqa: E402


class DailyLimit(Exception):
    pass


def retry_after(reason):
    match = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m(?!s))?(?:([\d.]+)s)?(?:([\d.]+)ms)?", reason or "")
    if not match or not any(match.groups()):
        return None
    h, m, s, ms = match.groups()
    return int(h or 0) * 3600 + int(m or 0) * 60 + float(s or 0) + float(ms or 0) / 1000


def case_log(case):
    if "log" in case:
        return case["log"]
    return gzip.decompress((ROOT / case["log_path"]).read_bytes()).decode("utf-8", errors="replace")


def verdict_for(case, variant):
    distilled = triage.distill_error(case_log(case))
    candidates = [{k: c[k] for k in ("sha", "message", "files", "patch")} for c in case["commits"]]
    scored = [{**c, **triage.score_candidate(c, distilled)} for c in candidates]
    if variant == "last_commit":
        return {"responsible_commit": scored[-1]["sha"], "confidence": None, "fallback": False, "fallback_reason": None}
    if variant == "deterministic":
        return triage.fallback_verdict(scored, "deterministic only")
    for _ in range(40):
        with contextlib.redirect_stdout(io.StringIO()):
            verdict = triage.llm_verdict(distilled, scored)
        reason = verdict.get("fallback_reason") or ""
        if not verdict["fallback"] or "RateLimit" not in reason:
            return verdict
        wait = retry_after(reason)
        if wait is None or wait > MAX_WAIT_SECONDS:  # Groq's daily limit is a rolling window: short waits are fine
            raise DailyLimit(reason[:300])
        print(f"    rate limited, waiting {wait:.0f}s")
        time.sleep(wait + 1)
    raise DailyLimit("still rate limited after 40 waits")


def outcome(case, sha):
    if not sha:
        return "abstained"
    return "correct" if sha == case["guilty_sha"] else "wrong"


def wilson(k, n, z=1.96):
    if not n:
        return None
    p, d = k / n, 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return [round(max(0, centre - half), 3), round(min(1, centre + half), 3)]


def stats(rows):
    n, k = len(rows), sum(r["outcome"] == "correct" for r in rows)
    conf_ok = [r["confidence"] for r in rows if r["outcome"] == "correct" and isinstance(r["confidence"], (int, float))]
    conf_bad = [r["confidence"] for r in rows if r["outcome"] == "wrong" and isinstance(r["confidence"], (int, float))]
    return {"n": n, "correct": k, "wrong": sum(r["outcome"] == "wrong" for r in rows),
            "abstained": sum(r["outcome"] == "abstained" for r in rows),
            "accuracy": round(k / n, 3) if n else None, "ci95": wilson(k, n),
            "avg_conf_correct": round(sum(conf_ok) / len(conf_ok), 3) if conf_ok else None,
            "avg_conf_wrong": round(sum(conf_bad) / len(conf_bad), 3) if conf_bad else None,
            "fallback": sum(bool(r.get("fallback")) for r in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, help="only the first N cases")
    parser.add_argument("--variants", nargs="+", default=VARIANTS, choices=VARIANTS)
    parser.add_argument("--pause", type=float, default=2.0, help="seconds between LLM calls")
    parser.add_argument("--set", choices=sorted(SETS), default="synthetic", help="which case file to score")
    args = parser.parse_args()
    CASES, RUNS, RESULTS = SETS[args.set]

    cases = [json.loads(line) for line in CASES.read_text().splitlines()][: args.limit]
    cache = {}
    if RUNS.exists():
        for line in RUNS.read_text().splitlines():
            r = json.loads(line)
            cache[(r["case"], r["variant"], r["model"])] = r

    rows, stopped = [], None
    for case in cases:
        for variant in args.variants:
            model = triage.GROQ_MODEL if variant == "llm" else "-"
            key = (case["id"], variant, model)
            if key not in cache:
                if stopped and variant == "llm":
                    continue
                try:
                    verdict = verdict_for(case, variant)
                except DailyLimit as exc:
                    stopped = str(exc)
                    print(f"Stopping LLM calls (resume later): {stopped}")
                    continue
                cache[key] = {"case": case["id"], "variant": variant, "model": model,
                              "responsible_commit": verdict["responsible_commit"],
                              "confidence": verdict.get("confidence"), "fallback": bool(verdict.get("fallback")),
                              "fallback_reason": verdict.get("fallback_reason")}
                if variant == "llm":
                    with RUNS.open("a") as f:
                        f.write(json.dumps(cache[key]) + "\n")
                    print(f"  {case['id']} {case['category']:<11} {case['difficulty']:<6} "
                          f"{outcome(case, verdict['responsible_commit'])}")
                    time.sleep(args.pause)
            r = cache[key]
            rows.append({**r, "category": case["category"], "difficulty": case["difficulty"],
                         "n_commits": case["n_commits"], "outcome": outcome(case, r["responsible_commit"])})

    report = {"model": triage.GROQ_MODEL, "cases": len(cases), "incomplete": stopped, "overall": {}, "by_category": {},
              "by_difficulty": {}, "by_n_commits": {}, "multi_commit": {}}
    for variant in args.variants:
        vr = [r for r in rows if r["variant"] == variant]
        report["overall"][variant] = stats(vr)
        report["multi_commit"][variant] = stats([r for r in vr if r["n_commits"] > 1])
        for field, out in (("category", "by_category"), ("difficulty", "by_difficulty"), ("n_commits", "by_n_commits")):
            groups = defaultdict(list)
            for r in vr:
                groups[str(r[field])].append(r)
            out_v = report[out].setdefault(variant, {})
            for g in sorted(groups):
                out_v[g] = stats(groups[g])
    report["rows"] = rows
    RESULTS.write_text(json.dumps(report, indent=2) + "\n")

    print(f"\nModel {triage.GROQ_MODEL}; {len(cases)} cases" + (" (LLM incomplete, rerun to resume)" if stopped else ""))
    print(f"{'variant':<14} {'n':>4} {'accuracy':>9}  95% CI          multi-commit")
    for variant in args.variants:
        s, m = report["overall"][variant], report["multi_commit"][variant]
        if s["n"]:
            print(f"{variant:<14} {s['n']:>4} {s['accuracy']:>9.1%}  {s['ci95']}  {m['accuracy']:.1%} (n={m['n']})")
    for field in ("by_category", "by_difficulty", "by_n_commits"):
        print(f"\n{field.replace('_', ' ')}:")
        groups = sorted({g for v in args.variants for g in report[field].get(v, {})})
        print(f"  {'':<12}" + "".join(f"{v:>15}" for v in args.variants))
        for g in groups:
            cells = []
            for v in args.variants:
                s = report[field].get(v, {}).get(g)
                cells.append(f"{s['correct']}/{s['n']} {s['accuracy']:.0%}".rjust(15) if s else " " * 15)
            print(f"  {g:<12}" + "".join(cells))
    print(f"\nWrote {RESULTS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
