# CI-Sense study guide (read top to bottom, one step at a time)

## Step 1. What is this project? (one sentence)
When a CI test run fails on a pull request, CI-Sense reads the failure log and the PR's commits, and tells you **which commit broke the build, why, and how to fix it**, posted as a PR comment.

**Why it matters:** with several commits in a PR, the failing line is often not in the commit that caused it. Humans waste time guessing.

## Step 2. The research question (say this exactly)
> Can an LLM-based triage agent identify the commit that broke a CI build more accurately than (B1) a naive "newest commit" heuristic and (B2) deterministic rule-based scoring? And does adding Sourcegraph code-search context improve it further?

- **H1:** LLM > deterministic > last-commit, mostly on multi-commit cases.
- **H2:** Sourcegraph context helps on dependency/error cases and does not hurt elsewhere.

**Why this question is fair:** it has a measurable answer (is the chosen commit the guilty one: yes/no), a known ground truth (we planted the bug), and baselines to compare against.

## Step 3. How it works: the pipeline (the code is `agent/triage.py`)
Trigger: GitHub Actions workflow `tests` fails -> workflow `triage` starts -> runs `agent/triage.py`.

| # | Stage | What it does | Why |
|---|---|---|---|
| 1 | Fetch logs | Downloads the failed run's log zip via the GitHub API | The log is the evidence of what failed |
| 2 | Distil error | Strips timestamps; keeps windows of 2 lines before / 7 after any line matching Error, Traceback, FAILED, assert, Exception; cuts "Post job cleanup" noise | Raw logs are huge and noisy; the LLM needs only the error |
| 3 | Find candidates | Lists the non-merge commits in the PR (`compare base...head`); on main, commits since the last green run | Only these commits can be responsible |
| 4 | Get diffs | For each candidate: message, files changed, patch (cut to 3000 chars) | The diff is the real evidence of what changed |
| 5 | Deterministic score | +3 if a changed file is named in the error; +2 if changed lines share identifiers with the error; +2 if config/dependency files changed and the error looks config-related | A cheap, explainable signal; also our baseline B2 and our fallback |
| 6 | (Optional) Sourcegraph | Searches public code for pinned packages and the exact error text (see Step 5) | Outside evidence |
| 7 | LLM verdict | Sends error + candidates + scores + patches to Groq `openai/gpt-oss-120b` at temperature 0, JSON mode; returns what failed, why, responsible sha, confidence, fix | Reasons about interactions between commits |
| 8 | Safety checks | The returned sha must be one of the candidates; 3 retries on transient errors; otherwise fall back to the deterministic verdict | The LLM must never invent a commit; the tool must never crash |
| 9 | Post comment | Writes a PR comment plus a hidden JSON block (`<!-- ci-sense-data ... -->`) that the evaluator and UI read; secrets are redacted | Results are machine-readable |

### Why not other approaches? (they WILL ask)
- **`git bisect`:** re-runs the tests for many commits: slow, costly in CI minutes. We do one pass using the logs we already have.
- **Rules/regex only:** that is our baseline B2; it fails when the failing file is not the guilty commit's file.
- **Send the whole repo or full log to the LLM:** expensive, noisy, hits token limits.
- **Fine-tune a model:** no labelled data, and no need: a prompted model already does this.
- **Embeddings / RAG over the repo:** the repo is tiny and the diffs are the evidence; retrieval over the repo adds noise. (Sourcegraph is our retrieval component, over public code.)
- **Why Groq `gpt-oss-120b`:** free tier, fast, supports JSON mode. **Why temperature 0:** repeatable output. **Why a fallback:** CI tooling must still say something if the API is down.

## Step 4. The dataset (what we test on)
14 **seeded** pull requests on this repo (`seeds/ground_truth.json`, created by `scripts/seed_failures.py`). We plant exactly one guilty commit in each, so ground truth is known by construction.

| Cases | Type | Why |
|---|---|---|
| 01-05 | Single commit: import typo, logic bug, wrong test, syntax error, bad dependency pin | Sanity checks (any method should pass) |
| 06-08 | Multi-commit: bug in the middle commit, rename without updating tests, behaviour change | Real attribution problem |
| 09-14 | **Hard decoys:** the failing line is in a *different* commit than the root cause (a correct new test exposes an earlier silent `//` or `round()` change; a docstring-only commit touches the same function as the culprit; one bad pin among three valid plugin pins; a harmless refactor before a bad test edit) | Designed to fool the baselines |

Note for 09 and 14: the bug stays hidden until a later *correct* test exposes it. Our ground truth is the **root cause**, not the commit where the failure first appears. Say this out loud; it is a design choice.

## Step 5. Sourcegraph (what, why, and the honest truth)
- **What:** Sourcegraph is a code-search engine. We call its API to search public code.
- **How we use it:** (a) for a package pinned in the patch (e.g. `pytest-timeout==99.1.0`) we search public `requirements*.txt` files to show which versions really exist; (b) we search for the exact error text to see how it appears in real code. The results are added to the LLM prompt as "external evidence".
- **Why public code, not our repo:** sourcegraph.com does not index small repos like ours (we tested: our repo returns "not found", while `pallets/flask` works). Running our own Sourcegraph needs Docker and several GB, so we did not.
- **Result:** no measurable difference, because the LLM is already at ceiling on our data. Say so honestly. It is implemented, tested manually, and we log how often context was retrieved (`sourcegraph_chars`).

## Step 6. Metrics and baselines
- **Main metric:** attribution accuracy = fraction of cases where the verdict sha equals the guilty sha. Also: wrong, abstained ("none"), average confidence, fallback rate.
- **Baselines:** B1 `last_commit` (blame the newest commit); B2 `deterministic` (scoring only, no LLM).
- **Variants compared (ablation, `scripts/ablation.py`):** last_commit, deterministic, llm, llm_sourcegraph.
- **Confidence intervals:** Wilson 95% interval (good for small n). With 14 cases, 14/14 correct only means accuracy is plausibly between about 78% and 100%.

## Step 7. Results (all numbers are real, from `seeds/ablation.json` and `seeds/results.json`)
Live pipeline: 14/14 correct, average confidence 0.969, 0 fallbacks.

| Variant | Correct | Accuracy | 95% CI | Multi-commit only (9) |
|---|---|---|---|---|
| last_commit | 7/14 | 50% | 27-73% | 2/9 |
| deterministic | 8/14 | 57% | 33-79% | 3/9 |
| llm | 14/14 | 100% | 79-100% | 9/9 |
| llm + Sourcegraph | 14/14 | 100% | 79-100% | 9/9 |

How to read it: the LLM wins by about 43-50 points over the baselines, all of it from multi-commit cases. Sourcegraph changed nothing (LLM already perfect; context was retrieved in only 4 of 14 runs: cases 01, 05, 07, 11). The intervals are wide because n is 14.

## Step 8. Limitations (say these before they ask)
1. Small (14 cases), synthetic, one tiny calculator repo: does not prove real-world accuracy.
2. We wrote the bugs *and* the heuristics: possible author bias. The model may also have seen similar bug patterns in training.
3. The LLM made no errors even on the decoy cases, so the benchmark may still be too easy; we have no LLM failure cases to analyse.
4. Confidence scores are not calibrated (no wrong answers to compare against).
5. Patches are truncated (3000 chars; 1500 sent to the LLM); big diffs could hide the culprit.
6. One model, one prompt; no prompt ablation.
7. Free-tier rate limits: when the key was invalid, or the daily token quota ran out, the pipeline silently fell back to deterministic scoring (we observed 75% accuracy that looked like an LLM result). Fix: the ablation script now aborts if the LLM is unavailable.
8. Sourcegraph: public index only, text matches, no effect measured.
9. Log distillation is regex-based; unusual log formats could hide the real error.

## Step 9. Likely questions and short answers
- *Why is accuracy 100%, is it too easy?* Probably partly yes; it is small and synthetic. The baselines get only 1/3 on multi-commit cases, so the benchmark does separate methods, but we cannot claim real-world 100%.
- *What would you do next?* Real-world failures from open-source repos, more models, calibrate confidence, flaky-test cases, multi-cause failures.
- *Why does the LLM beat deterministic scoring?* The score uses surface overlap (file named, shared words); the LLM reads the diff against the failing assertion (e.g. `4 == 5` from `add(2, 3)` points to the `a + a` change).
- *What if the LLM is wrong or down?* The sha must be a candidate; otherwise fall back to scoring; it can also answer "none".
- *Is the evaluation leaking?* The LLM never sees ground truth; it sees only the log and the diffs.
- *How to reproduce?* README + `.env.example` + the commands in REPORT.md.

## Step 10. Live demo script (3 minutes)
1. API `http://localhost:8787`, UI `http://localhost:5173`.
2. **Overview**: show triage history from real PR comments.
3. **Live Triage**: pick a failed run and watch the stages stream (nothing is posted to GitHub).
4. **Evaluation**: per-case table, LLM vs scoring, and the ablation card.
5. **How it works**: the pipeline diagram.
6. On GitHub: open PR #6 (or any seed PR) and show the real bot comment.
7. Show `seeds/ground_truth.json` and `scripts/evaluate.py` to prove scoring is automatic.
