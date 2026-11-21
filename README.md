# ci-sense

Run tests with: pytest -v

## Evaluation

Seed PRs with known breakages, let CI-Sense triage them, then score its verdicts:

    python scripts/seed_failures.py --dry-run   # preview the cases
    python scripts/seed_failures.py             # push seed/* branches and open PRs
    python scripts/evaluate.py --wait           # score verdicts once triage has run
    python scripts/seed_failures.py --cleanup   # close seed PRs, delete seed/* branches

Ground truth lives in `seeds/ground_truth.json`; scores are written to `seeds/results.json`.

### Synthetic benchmark (offline, 140 cases)

The 14 seeded PRs are too few to measure accuracy precisely, so `bench/` adds a larger benchmark that
runs locally without GitHub. `bench/fixture/` is a small retail library (`shop/`, 27 functions) with a
deliberately incomplete test suite; `bench/heldout/` holds extra edge-case tests.

    python scripts/bench_generate.py    # build bench/cases.jsonl (140 cases, seed 7)
    python scripts/bench_eval.py        # score last_commit / deterministic / llm -> bench/results.json

Each case is a real git history (1–5 commits, exactly one guilty) with real pytest output from the head.
Bugs come from mutating the fixture (operator and constant swaps, renames, a dropped colon, wrong test
expectations). Latent bugs are mutants the base suite misses, exposed by a later, correct "add test"
commit. Decoy commits (docstrings, comments, behaviour-preserving refactors, passing tests, README edits,
valid pins) favour the guilty function. Each case is kept only if the commits before the guilty one pass,
the head fails, and `git revert` of the guilty commit alone makes the head pass again.
LLM verdicts are cached in `bench/runs.jsonl`, so a run stopped by Groq's daily limit resumes on rerun.

### Real-repo cases

    python scripts/mine_real.py               # mine real PR failures -> bench/real_cases.jsonl
    python scripts/bench_eval.py --set real   # -> bench/real_results.json

The miner finds PR CI runs that failed and then passed. Candidates are the PR's commits up to the failure,
as in CI-Sense's PR mode. The label comes from SZZ: blame the lines the fix changed, and keep the case only
if they all come from one commit. Labels are automatic and have not been checked by hand.

### Results so far (gpt-oss-120b; LLM runs incomplete because of Groq's free-tier daily limit)

| Set | Cases | last_commit | deterministic | LLM |
|---|---|---|---|---|
| Synthetic | 140 | 44.3% | 58.6% | 100% (126/126 run; 14 syntax cases not yet run) |
| Synthetic, multi-commit | 121 | 35.5% | 52.1% | 100% (109/109 run) |
| Real (9 repos) | 17 | 82.4% | 88.2% | 3/4 run: 3 correct, 1 abstained |
| Real, multi-commit | 4 | 1/4 | 3/4 | 0/1 run (abstained) |

Caveats: the synthetic bugs are single-token mutations in a small library written for this benchmark, so the
LLM's 100% shows they are too easy, not that CI-Sense is perfect. 13 of the 17 real cases have only one
candidate commit, which any method gets right. Several real failures are lint or format failures. Rerun the
two `bench_eval.py` commands to finish the remaining LLM verdicts.

## Running the UI

A FastAPI backend (`server/`) reads verdicts from the PR comments and streams live triage runs; a React frontend (`web/`) displays them. Both read credentials from the root `.env` (`GITHUB_TOKEN`, `GITHUB_REPO`, `GROQ_API_KEY`, optional `GROQ_MODEL`). Live triage in the UI never posts to GitHub.

    pip install -r server/requirements.txt
    uvicorn server.app:app --port 8787          # API on http://localhost:8787

    cd web && npm install
    npm run dev                                 # UI on http://localhost:5173

Or start both with `scripts/dev.sh`. To point the UI at a different API, set `VITE_API_BASE` (see `web/.env.example`).

## Sourcegraph context

When `SRC_ACCESS_TOKEN` is set (plus optional `SRC_ENDPOINT`, default `https://sourcegraph.com`, and `SRC_REV`), triage searches Sourcegraph for the key identifiers in the error and passes the repo-wide matches to the LLM (`agent/sourcegraph.py`). It degrades silently if unavailable. For CI, add `SRC_ACCESS_TOKEN` as a repo secret. The repo must be indexed by the Sourcegraph instance.

## Ablation / baselines

    python scripts/ablation.py --runs 1    # last_commit vs deterministic vs llm vs llm_sourcegraph -> seeds/ablation.json

## Running on Kubernetes

The API and the web UI each build into a Docker image (`Dockerfile`, `web/Dockerfile`) and run as Deployments with Services (`k8s/`). Your `.env` becomes a Kubernetes Secret, so keys are never baked into an image. Locally this uses [kind](https://kind.sigs.k8s.io/) (Kubernetes inside Docker); you need Docker Desktop running.

    scripts/k8s.sh up      # create cluster, build + load images, deploy
    scripts/k8s.sh open    # UI on http://localhost:8080
    scripts/k8s.sh down    # delete the cluster

Useful commands: `kubectl get pods`, `kubectl logs deploy/ci-sense-api`, `kubectl scale deploy/ci-sense-web --replicas=3`.
