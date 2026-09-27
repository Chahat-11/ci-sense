"""Seed PRs with known breakages so CI-Sense's verdicts can be scored against ground truth.

Each case becomes a branch seed/NN-<name> off origin/main with one or more realistic commits,
exactly one of which introduces the failure. Branches are built in a temporary git worktree,
so the current checkout and main are never touched.

    python scripts/seed_failures.py --dry-run     # print the plan, change nothing
    python scripts/seed_failures.py               # create branches, push, open PRs
    python scripts/seed_failures.py --force       # recreate cases whose branch already exists
    python scripts/seed_failures.py --cleanup     # close seed PRs, delete seed/* branches
"""

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
GROUND_TRUTH = ROOT / "seeds" / "ground_truth.json"
BASE = "main"
API = "https://api.github.com"
TRAILER = "\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"


def replace(path, old, new):
    return ("replace", path, old, new)


def append(path, text):
    return ("append", path, text)


# Each commit: (message, [edits], guilty). Exactly one commit per case is guilty.
CASES = [
    {
        "id": "01", "name": "import-typo", "category": "import_error",
        "title": "Tidy up test imports",
        "description": "Test module imports src.calculater (typo), so collection fails with ModuleNotFoundError.",
        "commits": [
            ("Tidy up test imports", [
                replace("tests/test_calculator.py", "from src.calculator import add, divide",
                        "from src.calculater import add, divide"),
            ], True),
        ],
    },
    {
        "id": "02", "name": "divide-logic", "category": "logic_bug",
        "title": "Streamline divide return path",
        "description": "divide returns a * b instead of a / b.",
        "commits": [
            ("Streamline divide return path", [
                replace("src/calculator.py", "    return a / b", "    return a * b"),
            ], True),
        ],
    },
    {
        "id": "03", "name": "wrong-expectation", "category": "test_bug",
        "title": "Update add test values",
        "description": "Test expects add(2, 3) == 6; the implementation is correct.",
        "commits": [
            ("Update add test values", [
                replace("tests/test_calculator.py", "    assert add(2, 3) == 5", "    assert add(2, 3) == 6"),
            ], True),
        ],
    },
    {
        "id": "04", "name": "syntax-error", "category": "syntax_error",
        "title": "Add type hints to calculator functions",
        "description": "Type-hint refactor drops the colon after add's signature: SyntaxError in src/calculator.py.",
        "commits": [
            ("Add type hints to calculator functions", [
                replace("src/calculator.py", "def add(a, b):", "def add(a: float, b: float) -> float"),
                replace("src/calculator.py", "def divide(a, b):", "def divide(a: float, b: float) -> float:"),
            ], True),
        ],
    },
    {
        "id": "05", "name": "bad-dependency", "category": "dependency",
        "title": "Guard against hanging tests",
        "description": "requirements.txt pins pytest-timeout==99.1.0, which does not exist; pip install fails before pytest runs.",
        "commits": [
            ("Add pytest-timeout to guard against hanging tests", [
                append("requirements.txt", "pytest-timeout==99.1.0\n"),
            ], True),
        ],
    },
    {
        "id": "06", "name": "add-bug-among-three", "category": "multi_commit_logic",
        "title": "Docs, add cleanup and extra divide coverage",
        "description": "Three commits; the middle one changes add to compute a + a.",
        "commits": [
            ("Document local setup in README", [
                append("README.md", "\n## Setup\n\n    pip install -r requirements.txt\n"),
            ], False),
            ("Use in-place accumulation in add", [
                replace("src/calculator.py", "def add(a, b):\n    return a + b",
                        "def add(a, b):\n    total = a\n    total += a\n    return total"),
            ], True),
            ("Add divide test for negative numbers", [
                append("tests/test_calculator.py",
                       "\n\ndef test_divide_negative():\n    assert divide(-9, 3) == -3\n"),
            ], False),
        ],
    },
    {
        "id": "07", "name": "rename-without-tests", "category": "multi_commit_rename",
        "title": "Rename divide and polish docs",
        "description": "First of three commits renames divide to safe_divide in src only; tests still import divide.",
        "commits": [
            ("Rename divide to safe_divide to make zero handling explicit", [
                replace("src/calculator.py", "def divide(a, b):", "def safe_divide(a, b):"),
            ], True),
            ("Add project description to README", [
                replace("README.md", "# ci-sense\n",
                        "# ci-sense\n\nA small calculator library used to exercise CI failure triage.\n"),
            ], False),
            ("Add module docstring to calculator", [
                replace("src/calculator.py", "def add(a, b):",
                        '"""Basic arithmetic helpers."""\n\n\ndef add(a, b):'),
            ], False),
        ],
    },
    {
        "id": "08", "name": "zero-check-change", "category": "multi_commit_behavior",
        "title": "Add multiply and refine zero handling",
        "description": "Second of two commits makes divide return signed infinity for non-zero numerators over zero, "
                       "so divide(10, 0) no longer raises ValueError.",
        "commits": [
            ("Add multiply helper with tests", [
                append("src/calculator.py", "\n\ndef multiply(a, b):\n    return a * b\n"),
                replace("tests/test_calculator.py", "from src.calculator import add, divide",
                        "from src.calculator import add, divide, multiply"),
                append("tests/test_calculator.py",
                       "\n\ndef test_multiply():\n    assert multiply(4, 5) == 20\n"
                       "\n\ndef test_divide_by_zero_numerator():\n"
                       "    with pytest.raises(ValueError):\n        divide(10, 0)\n"),
            ], False),
            ("Return signed infinity for non-zero numerators over zero", [
                replace("src/calculator.py",
                        "    if b == 0:\n        raise ValueError(\"cannot divide by zero\")\n",
                        "    if b == 0 and a == 0:\n        raise ValueError(\"cannot divide by zero\")\n"
                        "    if b == 0:\n        return float(\"inf\") if a > 0 else float(\"-inf\")\n"),
            ], True),
        ],
    },
]


def git(*args, cwd=ROOT, check=True):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout.strip()


def resolve_repo():
    repo = os.environ.get("GITHUB_REPOSITORY") or os.environ.get("GITHUB_REPO") or git("remote", "get-url", "origin")
    repo = re.sub(r"^(https?://|git@)?(www\.)?github\.com[/:]", "", repo.strip())
    return repo.removesuffix(".git").strip("/")


def github(method, path, **kwargs):
    headers = {
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN'].strip()}",
        "Accept": "application/vnd.github+json",
    }
    resp = requests.request(method, f"{API}{path}", headers=headers, timeout=30, **kwargs)
    if resp.status_code >= 400:
        sys.exit(f"GitHub {method} {path} failed: HTTP {resp.status_code} {resp.text[:300]}")
    return resp.json() if resp.content else None


def branch_name(case):
    return f"seed/{case['id']}-{case['name']}"


def apply_edit(files, edit):
    kind, path = edit[0], edit[1]
    content = files[path]
    if kind == "replace":
        old, new = edit[2], edit[3]
        if content.count(old) != 1:
            raise ValueError(f"{path}: expected exactly one match for {old!r}, found {content.count(old)}")
        files[path] = content.replace(old, new)
    else:
        files[path] = content.rstrip("\n") + "\n" + edit[2] if content.strip() else edit[2]


def plan_case(case, base_files):
    """Apply every commit in memory; returns [(message, guilty, {path: (before, after)})]."""
    files = dict(base_files)
    steps = []
    for message, edits, guilty in case["commits"]:
        before = dict(files)
        for edit in edits:
            apply_edit(files, edit)
        changed = {p: (before[p], files[p]) for p in {e[1] for e in edits}}
        steps.append((message, guilty, changed))
    return steps


def load_base_files():
    paths = {e[1] for case in CASES for _, edits, _ in case["commits"] for e in edits}
    return {p: git("show", f"origin/{BASE}:{p}") + "\n" for p in paths}


def branch_exists(branch):
    local = git("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False)
    remote = git("ls-remote", "--heads", "origin", branch)
    return bool(local or remote)


def find_open_pr(repo, branch):
    owner = repo.split("/")[0]
    prs = github("GET", f"/repos/{repo}/pulls", params={"head": f"{owner}:{branch}", "state": "open"})
    return prs[0] if prs else None


def delete_branch(repo, branch):
    assert branch.startswith("seed/"), branch
    pr = find_open_pr(repo, branch)
    if pr:
        github("PATCH", f"/repos/{repo}/pulls/{pr['number']}", json={"state": "closed"})
        print(f"  closed PR #{pr['number']}")
    if git("ls-remote", "--heads", "origin", branch):
        git("push", "origin", "--delete", branch)
        print(f"  deleted remote {branch}")
    if git("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False):
        git("branch", "-D", branch)
        print(f"  deleted local {branch}")


def seed_case(repo, case, steps):
    branch = branch_name(case)
    assert branch.startswith("seed/"), branch
    workdir = tempfile.mkdtemp(prefix="ci-sense-seed-")
    git("worktree", "add", "-q", "-b", branch, workdir, f"origin/{BASE}")
    commits, guilty_sha = [], None
    try:
        for message, guilty, changed in steps:
            for path, (_, after) in changed.items():
                Path(workdir, path).write_text(after)
            git("add", *changed, cwd=workdir)
            git("commit", "-q", "-m", message + TRAILER, cwd=workdir)
            sha = git("rev-parse", "HEAD", cwd=workdir)
            commits.append({"sha": sha, "message": message, "guilty": guilty})
            if guilty:
                guilty_sha = sha
        git("push", "-q", "-u", "origin", f"{branch}:{branch}", cwd=workdir)
    finally:
        git("worktree", "remove", "--force", workdir, check=False)

    pr = github("POST", f"/repos/{repo}/pulls", json={
        "title": f"Seed {case['id']}: {case['title']}",
        "head": branch,
        "base": BASE,
        "body": "Seeded by `scripts/seed_failures.py` for CI-Sense evaluation.",
    })
    print(f"  pushed {branch} ({len(commits)} commits), opened PR #{pr['number']}")
    return {
        "case": case["id"],
        "name": case["name"],
        "branch": branch,
        "pr_number": pr["number"],
        "category": case["category"],
        "description": case["description"],
        "guilty_sha": guilty_sha,
        "commits": commits,
    }


def print_plan(case, steps, exists):
    status = "EXISTS (skip unless --force)" if exists else "new"
    print(f"\n=== Seed {case['id']}: {case['title']}  [{case['category']}]  branch {branch_name(case)}  ({status})")
    print(f"    ground truth: {case['description']}")
    for i, (message, guilty, changed) in enumerate(steps, 1):
        print(f"  commit {i}/{len(steps)}{'  <-- GUILTY' if guilty else ''}: {message}")
        for path, (before, after) in changed.items():
            diff = difflib.unified_diff(before.splitlines(), after.splitlines(), f"a/{path}", f"b/{path}", n=1, lineterm="")
            for line in list(diff)[2:]:
                print(f"      {line}")


def cleanup(repo):
    remote = [line.split("refs/heads/", 1)[1] for line in git("ls-remote", "--heads", "origin", "seed/*").splitlines()]
    local = git("for-each-ref", "--format=%(refname:short)", "refs/heads/seed/").splitlines()
    branches = sorted(set(remote) | set(local))
    if not branches:
        print("No seed branches found.")
    for branch in branches:
        print(branch)
        delete_branch(repo, branch)
    git("worktree", "prune")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="print the plan without pushing anything")
    parser.add_argument("--cleanup", action="store_true", help="close seed PRs and delete seed/* branches")
    parser.add_argument("--force", action="store_true", help="recreate cases whose branch already exists")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    repo = resolve_repo()
    git("fetch", "-q", "origin", BASE)

    if args.cleanup:
        cleanup(repo)
        return

    base_files = load_base_files()
    plans = [(case, plan_case(case, base_files)) for case in CASES]
    for case, steps in plans:
        assert sum(guilty for _, guilty, _ in steps) == 1, f"case {case['id']} needs exactly one guilty commit"

    print(f"Repo {repo}, base origin/{BASE} @ {git('rev-parse', '--short', f'origin/{BASE}')}")
    if args.dry_run:
        for case, steps in plans:
            print_plan(case, steps, branch_exists(branch_name(case)))
        print(f"\nDry run: {len(plans)} cases, nothing pushed.")
        return

    truth = json.loads(GROUND_TRUTH.read_text()) if GROUND_TRUTH.exists() else {"cases": []}
    by_case = {c["case"]: c for c in truth["cases"]}
    for case, steps in plans:
        branch = branch_name(case)
        print(f"\nSeed {case['id']} -> {branch}")
        if branch_exists(branch):
            if not args.force:
                print("  branch exists, skipping (use --force to recreate)")
                continue
            delete_branch(repo, branch)
        by_case[case["id"]] = seed_case(repo, case, steps)
        truth["cases"] = [by_case[k] for k in sorted(by_case)]
        GROUND_TRUTH.parent.mkdir(exist_ok=True)
        GROUND_TRUTH.write_text(json.dumps(truth, indent=2) + "\n")
    print(f"\nGround truth written to {GROUND_TRUTH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
