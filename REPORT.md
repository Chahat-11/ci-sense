# CI-Sense: evaluation report

## 1. Research question
Given a failed CI run and the commits in a PR, can an LLM-based triage agent identify the commit that broke the build more accurately than (B1) a naive "newest commit" heuristic and (B2) deterministic scoring alone? Does adding Sourcegraph repo-wide code search (RQ2) improve attribution over the LLM without it?

**Hypotheses.** H1: LLM > deterministic > last-commit, mainly on multi-commit cases where the failing line and the root cause are in different commits. H2: Sourcegraph context helps on cross-file cases (e.g. rename, case 07) and does not hurt elsewhere.

## 2. Method
- **Pipeline** (`agent/triage.py`): fetch logs -> distill error -> candidate commits (PR compare) -> deterministic score (file named in error, identifier overlap, config files) -> LLM verdict (Groq `openai/gpt-oss-120b`, temperature 0, JSON output, 3 retries, deterministic fallback) -> optional Sourcegraph context (`agent/sourcegraph.py`).
- **Dataset**: 14 seeded PRs (`seeds/ground_truth.json`). Cases 01-05 are single-commit failures (import, logic, test bug, syntax, dependency); 06-08 are multi-commit; 09-14 are *hard* multi-commit cases with decoys: the failing line sits in a different commit than the root cause (e.g. a correct new test exposes an earlier silent `//` or `round()` change; a docstring-only commit touches the same function as the real culprit; one of three plugin pins in requirements.txt does not exist). Exactly one guilty commit per case, known by construction; we verified locally that cases 10, 12, 13 first fail at the guilty commit, while in 09 and 14 the bug is dormant until a later, correct test exposes it (ground truth = root cause, not trigger).
- **Metrics**: accuracy (verdict sha == guilty sha), wrong, abstained, average confidence for correct vs wrong, fallback rate.
- **Variants**: `last_commit`, `deterministic`, `llm`, `llm_sourcegraph` (`scripts/ablation.py`, LLM variants x3 runs).
- **Reproduce**: `cp .env.example .env`, fill keys, `pip install -r requirements.txt`, `python scripts/seed_failures.py`, `python scripts/evaluate.py --wait`, `python scripts/ablation.py --runs 1` (use `--runs 3` only with enough Groq quota: the free tier allows 200k tokens/day and 14 cases x 6 LLM runs exceeds it). Environment: Python 3.13, `groq` client, model `openai/gpt-oss-120b`, temperature 0. The ablation reports Wilson 95% intervals, multi-commit-only accuracy, per-category/per-case accuracy, and how often Sourcegraph returned context (`seeds/ablation.json`; also shown in the web UI Evaluation page).

## 3. Results
Live pipeline on all 14 cases (`seeds/results.json`): **14/14 correct**, 14 LLM verdicts, 0 fallbacks, average confidence 0.969. This includes all six hard decoy cases (09-14).

Ablation on the **original 8 cases** (LLM variants run 3x each, temperature 0). The 14-case ablation with confidence intervals and Sourcegraph-usage logging is implemented (`scripts/ablation.py`) but could not be completed because the Groq free-tier daily token limit (200k) was exhausted; rerun with `--runs 1` once quota resets and replace this table:

| Variant | Runs | Correct | Wrong | Abstained | Accuracy |
|---|---|---|---|---|---|
| last_commit (naive baseline) | 8 | 6 | 2 | 0 | 75% |
| deterministic scoring | 8 | 6 | 2 | 0 | 75% |
| llm | 24 | 24 | 0 | 0 | 100% |
| llm_sourcegraph | 24 | 24 | 0 | 0 | 100% |

On the three multi-commit cases (06-08), the only ones where choosing among commits matters:

| Variant | 06 | 07 | 08 | Correct |
|---|---|---|---|---|
| last_commit | wrong | wrong | correct | 1/3 |
| deterministic | wrong | correct | wrong | 1/3 |
| llm | correct | correct | correct | 3/3 |
| llm_sourcegraph | correct | correct | correct | 3/3 |

## 4. Interpretation
- **H1 supported on this data.** Both baselines make 2 errors, all in the multi-commit cases, while the LLM was right in all 24 runs. The two baselines fail on different cases: last_commit misses 06 and 07 because the guilty commit is not the newest; deterministic scoring misses 06 and 08, where a later commit touching the test file or sharing identifiers with the error out-scores the real culprit (e.g. 06: the unrelated "Add divide test" commit scored 5 vs 3 for the guilty commit). The LLM resolves these by reasoning about the diff against the failing assertion (`4 == 5` from `add(2, 3)` points to the `a + a` change).
- **LLM runs were stable:** 3 repetitions per case gave identical verdicts (no run-to-run variance at temperature 0).
- **H2 not supported / not testable here.** llm_sourcegraph scored the same as llm. The LLM already reaches 100%, so there is no headroom for extra context to help. Also, the live Sourcegraph retrieval (public requirements files and public error-message matches) was only verified manually on example queries; the ablation does not log whether context was actually retrieved for each case, so we cannot claim the context was used or useful.
- Single-commit cases (01-05) are trivially correct for every method, so overall accuracy overstates the gap; the 3-case table is the informative one.
- The earlier live run (`seeds/results.json`, 8/8, average confidence 0.968) agrees with the ablation LLM results.

## 5. Limitations and failure analysis
- Small (n=14), synthetic, single tiny repo (a calculator). Even with six decoy cases the LLM made no errors, so we have no LLM failure cases to analyse and the benchmark may still be too easy; with n=14 a 14/14 result has a 95% Wilson interval of roughly 78-100%, so it cannot establish a true accuracy of 100%.
- LLM repetitions at temperature 0 are not independent, so intervals use one run per case.
- The only failures observed are baseline failures (last-commit and deterministic scoring) and a *process* failure: when the Groq key was invalid, or the daily quota exhausted, the pipeline silently fell back to deterministic scoring (75% on 8 cases); the ablation script now aborts rather than record fallback runs as LLM results.
- Failures were injected by us, and the author wrote both the cases and the heuristics (possible bias); the LLM may have seen similar patterns in training.
- Most cases have one guilty commit, no flaky tests, infra failures, or multi-cause failures.
- Confidence is uncalibrated: with 100% accuracy there are no wrong cases to compare confidence against.
- Patches truncated (3000 chars / 1500 to the LLM); large diffs may lose the culprit.
- Single model and prompt; no prompt ablation. Groq rate limits trigger fallback to deterministic scoring.
- Sourcegraph on sourcegraph.com indexes the default branch only, so it sees `main` (pre-change code), not the PR head; it needs a public, indexed repo and a token. Matches are textual, not semantic.
- Logs are distilled with regexes; unusual log formats can hide the real error.

## 6. Conclusions
On our 8 seeded cases the LLM triage agent attributed the failing commit correctly in every run (100%) versus 75% for both a last-commit heuristic and deterministic scoring, with the entire difference coming from the three multi-commit cases. Sourcegraph public-code context did not change accuracy on the 8-case ablation, because the LLM was already at ceiling. The sample is small and synthetic, so we make no claim about real-world accuracy; a larger and harder benchmark (more multi-commit and ambiguous failures) is needed to test whether Sourcegraph context helps.
