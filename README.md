# ci-sense

Run tests with: pytest -v

## Evaluation

Seed PRs with known breakages, let CI-Sense triage them, then score its verdicts:

    python scripts/seed_failures.py --dry-run   # preview the cases
    python scripts/seed_failures.py             # push seed/* branches and open PRs
    python scripts/evaluate.py --wait           # score verdicts once triage has run
    python scripts/seed_failures.py --cleanup   # close seed PRs, delete seed/* branches

Ground truth lives in `seeds/ground_truth.json`; scores are written to `seeds/results.json`.

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
