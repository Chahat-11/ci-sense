# ci-sense

Run tests with: pytest -v

## Evaluation

Seed PRs with known breakages, let CI-Sense triage them, then score its verdicts:

    python scripts/seed_failures.py --dry-run   # preview the cases
    python scripts/seed_failures.py             # push seed/* branches and open PRs
    python scripts/evaluate.py --wait           # score verdicts once triage has run
    python scripts/seed_failures.py --cleanup   # close seed PRs, delete seed/* branches

Ground truth lives in `seeds/ground_truth.json`; scores are written to `seeds/results.json`.
