"""Generate a large synthetic triage benchmark from bench/fixture by mutation.

Each case is a real git history built in a temporary repo: a clean base commit, then 1-5 commits of
which exactly one is guilty. The failure log is real pytest output from running the suite at the head
commit. Every case is checked before it is kept:

  * every commit before the guilty one passes the tests,
  * the head fails,
  * reverting only the guilty commit on the head (git revert) makes the tests pass again,
  * for non-latent cases, the guilty commit is the first failing commit.

Categories
  logic_bug   operator/constant mutation in src that the existing tests catch
  latent_bug  mutation the existing tests miss; a later, correct "add test" commit exposes it
  test_bug    a test's expected value is changed; the source is fine
  rename      a src function is renamed but the tests still use the old name
  syntax      a type-hint edit drops the colon of a def line

Decoy commits (docs, comments, behaviour-preserving refactors, extra passing tests, README,
valid dependency pins, new helpers) are biased towards the same function/file as the guilty commit.

    python scripts/bench_generate.py                 # default: 140 cases, seed 7
    python scripts/bench_generate.py --cases 40 --seed 1

Writes bench/cases.jsonl (one case per line). Nothing touches GitHub.
"""

import argparse
import ast
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "bench" / "fixture"
HELDOUT = ROOT / "bench" / "heldout"
OUT = ROOT / "bench" / "cases.jsonl"
MODULES = ["pricing", "inventory", "textutil", "dates", "stats"]
CI_ROOT = "/home/runner/work/shop/shop"
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "GIT_AUTHOR_NAME": "dev", "GIT_AUTHOR_EMAIL": "dev@example.com",
       "GIT_COMMITTER_NAME": "dev", "GIT_COMMITTER_EMAIL": "dev@example.com"}

CATEGORY_TARGETS = {"logic_bug": 0.43, "latent_bug": 0.18, "test_bug": 0.18, "rename": 0.11, "syntax": 0.10}
COMMIT_COUNT_WEIGHTS = {1: 15, 2: 25, 3: 30, 4: 20, 5: 10}


def src_path(module):
    return f"shop/{module}.py"


def test_path(module):
    return f"tests/test_{module}.py"


def read_fixture():
    files = {}
    for path in sorted(FIXTURE.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            files[str(path.relative_to(FIXTURE))] = path.read_text()
    return files


def load_heldout():
    """module -> [(test name, source)] for every held-out test function."""
    out = {}
    for module in MODULES:
        text = (HELDOUT / f"test_{module}.py").read_text()
        lines = text.splitlines()
        out[module] = [(n.name, "\n".join(lines[n.lineno - 1:n.end_lineno]))
                       for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)]
    return out


# ---------------------------------------------------------------- running tests

def git(cwd, *args, check=True):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=ENV)
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def pytest_in(cwd, verbose=False):
    args = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-v" if verbose else "-q"]
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=ENV, timeout=60)
    return result.returncode == 0, result.stdout + result.stderr


def write_files(cwd, files):
    for path, text in files.items():
        target = Path(cwd, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)


class Scratch:
    """One reusable directory for quick pass/fail checks of a file set."""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="bench-scratch-")

    def run(self, files, verbose=False):
        for child in Path(self.dir).iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()
        write_files(self.dir, files)
        return pytest_in(self.dir, verbose)


# ---------------------------------------------------------------- mutation sites

BINOP = {ast.Add: ("+", "-"), ast.Sub: ("-", "+"), ast.Mult: ("*", "/"), ast.Div: ("/", "//"),
         ast.FloorDiv: ("//", "/"), ast.Mod: ("%", "//")}
CMP = {ast.Lt: ("<", "<="), ast.LtE: ("<=", "<"), ast.Gt: (">", ">="), ast.GtE: (">=", ">"),
       ast.Eq: ("==", "!="), ast.NotEq: ("!=", "==")}
BOOL = {ast.And: ("and", "or"), ast.Or: ("or", "and")}


def _gap_token(lines, left, right, token):
    """Locate `token` between the end of node `left` and the start of node `right` on one line."""
    if left.end_lineno != right.lineno:
        return None
    line = lines[left.end_lineno - 1]
    gap = line[left.end_col_offset:right.col_offset]
    pattern = rf"(?<![=<>!*/]){re.escape(token)}(?![=<>*/])" if not token.isalpha() else rf"\b{token}\b"
    match = re.search(pattern, gap)
    if not match:
        return None
    start = left.end_col_offset + match.start()
    return left.end_lineno, start, start + len(token)


def mutation_sites(text):
    """All single-token mutations inside top-level functions, indexed stably per (function, kind)."""
    lines = text.splitlines()
    sites = []
    for fn in functions(text).values():
        docstring = ast.get_docstring(fn) is not None
        found = []
        for node in ast.walk(fn):
            loc, kind, old, new = None, None, None, None
            if isinstance(node, ast.BinOp) and type(node.op) in BINOP:
                old, new = BINOP[type(node.op)]
                loc, kind = _gap_token(lines, node.left, node.right, old), "binop"
            elif isinstance(node, ast.AugAssign) and type(node.op) in BINOP:
                old, new = BINOP[type(node.op)][0] + "=", BINOP[type(node.op)][1] + "="
                loc, kind = _gap_token(lines, node.target, node.value, old), "augassign"
            elif isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in CMP:
                old, new = CMP[type(node.ops[0])]
                loc, kind = _gap_token(lines, node.left, node.comparators[0], old), "compare"
            elif isinstance(node, ast.BoolOp) and type(node.op) in BOOL:
                old, new = BOOL[type(node.op)]
                loc, kind = _gap_token(lines, node.values[0], node.values[1], old), "boolop"
            elif (isinstance(node, ast.Constant) and type(node.value) is int
                  and node.lineno == node.end_lineno):
                old, new = str(node.value), str(node.value + 1)
                loc, kind = (node.lineno, node.col_offset, node.end_col_offset), "constant"
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not) and node.lineno == node.operand.lineno:
                old, new = lines[node.lineno - 1][node.col_offset:node.operand.col_offset], ""
                loc, kind = (node.lineno, node.col_offset, node.operand.col_offset), "not"
            if loc is None or kind is None:
                continue
            if docstring and loc[0] == fn.body[0].lineno:
                continue
            if lines[loc[0] - 1][loc[1]:loc[2]] != old:
                continue
            found.append((loc, kind, old, new))
        found.sort(key=lambda f: (f[0][0], f[0][1]))
        counts = Counter()
        for loc, kind, old, new in found:
            sites.append({"func": fn.name, "kind": kind, "idx": counts[kind], "loc": loc, "old": old, "new": new})
            counts[kind] += 1
    return sites


def splice(text, loc, new):
    lines = text.split("\n")
    line_no, start, end = loc
    lines[line_no - 1] = lines[line_no - 1][:start] + new + lines[line_no - 1][end:]
    return "\n".join(lines)


def apply_site(files, path, spec):
    """Re-find the site described by spec in the current text (earlier decoys may have moved it)."""
    for site in mutation_sites(files[path]):
        if (site["func"], site["kind"], site["idx"]) == (spec["func"], spec["kind"], spec["idx"]):
            if site["old"] != spec["old"]:
                return None
            return {**files, path: splice(files[path], site["loc"], spec["new"])}
    return None


def test_constant_sites(text):
    """Numeric expected values in `assert x == <number>` lines of a test file."""
    lines = text.splitlines()
    sites = []
    for fn in ast.parse(text).body:
        if not isinstance(fn, ast.FunctionDef):
            continue
        idx = 0
        for node in ast.walk(fn):
            if (isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare)
                    and isinstance(node.test.ops[0], ast.Eq)):
                comp = node.test.comparators[0]
                if isinstance(comp, ast.Constant) and type(comp.value) in (int, float) and comp.lineno == comp.end_lineno:
                    old = lines[comp.lineno - 1][comp.col_offset:comp.end_col_offset]
                    new = str(comp.value + 1) if type(comp.value) is int else str(round(comp.value + 0.5, 2))
                    sites.append({"func": fn.name, "kind": "expect", "idx": idx,
                                  "loc": (comp.lineno, comp.col_offset, comp.end_col_offset), "old": old, "new": new})
                    idx += 1
    return sites


def functions(text):
    try:
        tree = ast.parse(text)
    except SyntaxError:  # a syntax-error case broke this file; decoys skip it
        return {}
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


# ---------------------------------------------------------------- guilty edits

RENAMES = {
    "round_money": "round_currency", "subtotal": "items_subtotal", "apply_discount": "discounted_price",
    "bulk_discount": "bulk_price", "tax": "tax_amount", "total": "order_total", "split_bill": "split_amount",
    "available": "quantity_on_hand", "restock": "add_stock", "reserve": "reserve_stock", "low_stock": "skus_below",
    "reorder_amount": "reorder_quantity", "slugify": "to_slug", "truncate": "shorten", "title_case": "to_title",
    "word_count": "count_words", "initials": "name_initials", "is_leap": "is_leap_year",
    "days_in_month": "month_length", "day_of_year": "ordinal_day", "quarter": "fiscal_quarter",
    "format_duration": "human_duration", "mean": "average", "median": "middle_value", "clamp": "bound",
    "moving_average": "rolling_mean", "normalize": "rescale",
}
HINTS = {"pricing": "float", "inventory": "dict", "textutil": "str", "dates": "int", "stats": "float"}
GUILTY_MESSAGES = {
    "binop": ["Simplify {f} arithmetic", "Refactor {f} calculation", "Tidy up {f}", "Streamline {f}"],
    "augassign": ["Simplify accumulation in {f}", "Tidy up {f} loop", "Refactor {f}"],
    "compare": ["Adjust boundary check in {f}", "Clarify {f} condition", "Tidy up {f}", "Handle edge case in {f}"],
    "boolop": ["Simplify conditions in {f}", "Clean up {f} guard", "Tidy up {f}"],
    "not": ["Simplify conditions in {f}", "Clean up {f} guard", "Invert check in {f} for readability"],
    "constant": ["Adjust {f} defaults", "Tweak constants in {f}", "Tidy up {f}", "Update {f} thresholds"],
    "test_bug": ["Update {f} expectations", "Refresh expected values in {f}", "Tidy up {f}"],
    "rename": ["Rename {f} to {new} for clarity", "Use clearer name for {f}"],
    "syntax": ["Add return type hint to {f}", "Annotate {f}"],
}


def rename_edit(files, module, func):
    path, new = src_path(module), RENAMES[func]
    if func not in functions(files[path]):
        return None
    return {**files, path: re.sub(rf"\b{func}\b", new, files[path])}, new


def syntax_edit(files, module, func):
    path = src_path(module)
    fn = functions(files[path]).get(func)
    if fn is None:
        return None
    lines = files[path].split("\n")
    line = lines[fn.lineno - 1]
    if not line.rstrip().endswith("):"):
        return None
    lines[fn.lineno - 1] = line.rstrip()[:-1] + f" -> {HINTS[module]}"
    return {**files, path: "\n".join(lines)}


# ---------------------------------------------------------------- decoys

COMMENTS = ["# keep this pure: callers rely on getting a new value back",
            "# see README for the rounding conventions used here",
            "# NOTE: inputs are assumed to be validated by the caller",
            "# fast path first, then the general case"]
README_SECTIONS = ["\n## Development\n\n    pip install -r requirements.txt\n    pytest -q\n",
                   "\n## Modules\n\n- pricing: totals, discounts, tax\n- inventory: stock levels\n",
                   "\n## Contributing\n\nOpen a PR; CI runs the test suite on every push.\n",
                   "\n## Versioning\n\nThis project follows semantic versioning.\n"]
PINS = ["pytest-cov==4.1.0\n", "pytest-xdist==3.5.0\n", "pytest-randomly==3.15.0\n", "pytest-timeout==2.3.1\n"]
HELPERS = {
    "pricing": ("percent_of", "def percent_of(part, whole):\n    if whole == 0:\n        return 0.0\n    return round_money(part * 100 / whole)\n"),
    "inventory": ("total_units", "def total_units(stock):\n    return sum(stock.values())\n"),
    "textutil": ("is_blank", "def is_blank(text):\n    return not text.strip()\n"),
    "dates": ("is_weekend_index", "def is_weekend_index(weekday):\n    return weekday in (5, 6)\n"),
    "stats": ("value_range", "def value_range(values):\n    return max(values) - min(values)\n"),
}


def insert_after_header(text, func, new_line):
    """Insert an indented line as the first statement of func (after its docstring if present)."""
    fn = functions(text).get(func)
    if fn is None:
        return None
    lines = text.split("\n")
    anchor = fn.body[0]
    at = anchor.end_lineno if ast.get_docstring(fn) is not None else anchor.lineno - 1
    if ast.get_docstring(fn) is not None and new_line.strip().startswith('"""'):
        return None
    indent = " " * anchor.col_offset
    lines.insert(at, indent + new_line)
    return "\n".join(lines)


def decoy_docstring(files, module, func, rng, ctx):
    path = src_path(module)
    fn = functions(files[path]).get(func)
    if fn is None or ast.get_docstring(fn) is not None:
        return None
    text = insert_after_header(files[path], func, f'"""Return the {func.replace("_", " ")} result."""')
    return text and ({**files, path: text}, f"Document {func}")


def decoy_comment(files, module, func, rng, ctx):
    path = src_path(module)
    if "# " in files[path].split(f"def {func}(", 1)[-1].split("\ndef ", 1)[0]:
        return None
    text = insert_after_header(files[path], func, rng.choice(COMMENTS))
    return text and ({**files, path: text}, rng.choice([f"Add note to {func}", f"Comment {func} assumptions"]))


def decoy_extract_return(files, module, func, rng, ctx):
    path = src_path(module)
    fn = functions(files[path]).get(func)
    if fn is None or any(isinstance(n, ast.Name) and n.id == "result" for n in ast.walk(fn)):
        return None
    returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return) and n.value is not None
               and not isinstance(n.value, (ast.Name, ast.Constant)) and n.lineno == n.end_lineno]
    if not returns:
        return None
    node = rng.choice(returns)
    lines = files[path].split("\n")
    line = lines[node.lineno - 1]
    indent = line[:len(line) - len(line.lstrip())]
    expr = line.strip()[len("return "):]
    lines[node.lineno - 1] = f"{indent}result = {expr}\n{indent}return result"
    return {**files, path: "\n".join(lines)}, rng.choice([f"Name intermediate result in {func}",
                                                          f"Make {func} easier to step through"])


def decoy_add_test(files, module, func, rng, ctx):
    pool = [(n, s) for n, s in ctx["heldout"][module]
            if func in s and n not in ctx["used_tests"] and n not in ctx["forbidden_tests"]]
    if not pool:
        return None
    name, source = rng.choice(pool)
    ctx["used_tests"].add(name)
    path = test_path(module)
    return ({**files, path: files[path].rstrip("\n") + "\n\n\n" + source + "\n"},
            rng.choice([f"Add test for {func}", f"Cover {func} edge cases", f"Test {func} more thoroughly"]))


def decoy_readme(files, module, func, rng, ctx):
    section = rng.choice([s for s in README_SECTIONS if s not in files["README.md"]] or [None])
    if section is None:
        return None
    return {**files, "README.md": files["README.md"] + section}, rng.choice(["Expand README", "Document project layout",
                                                                              "Update README"])


def decoy_pin(files, module, func, rng, ctx):
    pins = [p for p in PINS if p.split("==")[0] not in files["requirements.txt"]]
    if not pins:
        return None
    pin = rng.choice(pins)
    return ({**files, "requirements.txt": files["requirements.txt"] + pin},
            f"Add {pin.split('==')[0]} to dev requirements")


def decoy_helper(files, module, func, rng, ctx):
    name, source = HELPERS[module]
    path = src_path(module)
    if f"def {name}(" in files[path]:
        return None
    return {**files, path: files[path].rstrip("\n") + "\n\n\n" + source}, f"Add {name} helper"


SAME_FUNC_DECOYS = [decoy_docstring, decoy_comment, decoy_extract_return, decoy_add_test]
OTHER_DECOYS = [decoy_readme, decoy_pin, decoy_helper]


def make_decoy(files, guilty_module, guilty_func, rng, ctx):
    for _ in range(20):
        roll = rng.random()
        if roll < 0.45:
            module, func = guilty_module, guilty_func
            maker = rng.choice(SAME_FUNC_DECOYS)
        elif roll < 0.7:
            module = guilty_module
            func = rng.choice(sorted(functions(files[src_path(module)])) or [guilty_func])
            maker = rng.choice(SAME_FUNC_DECOYS)
        else:
            module = rng.choice(MODULES)
            func = rng.choice(sorted(functions(files[src_path(module)])) or [guilty_func])
            maker = rng.choice(SAME_FUNC_DECOYS + OTHER_DECOYS)
        out = maker(files, module, func, rng, ctx)
        if out:
            new_files, message = out
            same = module == guilty_module and func == guilty_func and maker in SAME_FUNC_DECOYS
            return new_files, message, {"kind": maker.__name__.removeprefix("decoy_"), "module": module,
                                        "func": func, "same_function": same}
    return None


# ---------------------------------------------------------------- screening

def screen(base, heldout, scratch):
    """Classify every candidate guilty edit against the base suite and the held-out suite."""
    full = dict(base)
    for module in MODULES:
        full[test_path(module)] = base[test_path(module)].rstrip("\n") + "\n\n\n" + \
            "\n\n\n".join(s for _, s in heldout[module]) + "\n"
    assert scratch.run(base)[0] and scratch.run(full)[0], "fixture must pass with and without held-out tests"

    pool = {"logic_bug": [], "latent_bug": [], "test_bug": [], "rename": [], "syntax": []}
    for module in MODULES:
        path = src_path(module)
        for site in mutation_sites(base[path]):
            spec = {"module": module, **{k: site[k] for k in ("func", "kind", "idx", "old", "new")}}
            mutated = apply_site(base, path, spec)
            if mutated is None:
                continue
            if not scratch.run(mutated)[0]:
                pool["logic_bug"].append(spec)
                continue
            full_mut = {**full, path: mutated[path]}
            ok, out = scratch.run(full_mut, verbose=True)
            if ok:
                continue  # survives every test: equivalent or untested mutant
            killers = re.findall(r"::(test_\w+) FAILED", out)
            killers = [k for k in killers if any(k == n for n, _ in heldout[module])]
            if killers:
                pool["latent_bug"].append({**spec, "killers": killers})
        tests = functions(base[test_path(module)])
        test_lines = base[test_path(module)].splitlines()
        for site in test_constant_sites(base[test_path(module)]):
            node = tests[site["func"]]
            body = "\n".join(test_lines[node.lineno - 1:node.end_lineno])
            target = re.search(rf"\b{module}\.(\w+)", body)
            pool["test_bug"].append({"module": module, "target": target.group(1) if target else None,
                                     **{k: site[k] for k in ("func", "kind", "idx", "old", "new")}})
        for func in functions(base[path]):
            if re.search(rf"\b{module}\.{func}\b", base[test_path(module)]):
                pool["rename"].append({"module": module, "func": func})
                pool["syntax"].append({"module": module, "func": func})
    return pool


# ---------------------------------------------------------------- building a case

def apply_guilty(files, category, spec):
    module, func = spec["module"], spec["func"]
    if category in ("logic_bug", "latent_bug"):
        out = apply_site(files, src_path(module), spec)
        message_key, extra = spec["kind"], {}
    elif category == "test_bug":
        path = test_path(module)
        out = None
        for site in test_constant_sites(files[path]):
            if (site["func"], site["idx"]) == (func, spec["idx"]) and site["old"] == spec["old"]:
                out = {**files, path: splice(files[path], site["loc"], spec["new"])}
        message_key, extra = "test_bug", {}
    elif category == "rename":
        res = rename_edit(files, module, func)
        out, extra = (res[0], {"new": res[1]}) if res else (None, {})
        message_key = "rename"
    else:
        out, message_key, extra = syntax_edit(files, module, func), "syntax", {}
    return out, message_key, extra


def git_patch(repo, sha, path):
    diff = git(repo, "diff", f"{sha}^", sha, "--", path)
    lines = diff.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("@@")), len(lines))
    return "\n".join(lines[start:])


def build_case(case_id, category, spec, n_commits, base, rng, heldout, scratch):
    module, func = spec["module"], spec["func"]
    ctx = {"heldout": heldout, "used_tests": set(), "forbidden_tests": set(spec.get("killers", []))}
    if category == "latent_bug":
        n_commits = max(n_commits, 2)
    guilty_idx = rng.randrange(n_commits - 1) if category == "latent_bug" else rng.randrange(n_commits)
    expose_idx = rng.randrange(guilty_idx + 1, n_commits) if category == "latent_bug" else None

    files, steps = dict(base), []
    for i in range(n_commits):
        if i == guilty_idx:
            new_files, key, extra = apply_guilty(files, category, spec)
            if new_files is None:
                return None
            message = rng.choice(GUILTY_MESSAGES[key]).format(f=func, **extra)
            meta = {"kind": "guilty"}
        elif i == expose_idx:
            name = rng.choice(spec["killers"])
            source = dict(heldout[module])[name]
            path = test_path(module)
            new_files = {**files, path: files[path].rstrip("\n") + "\n\n\n" + source + "\n"}
            message = rng.choice([f"Add test for {func}", f"Cover {func} edge cases", f"Test {func} boundaries"])
            meta = {"kind": "exposing_test", "module": module, "func": func, "same_function": True, "test": name}
        else:
            out = make_decoy(files, module, spec.get("target") or func, rng, ctx)
            if out is None:
                return None
            new_files, message, meta = out
        steps.append((message, new_files, i == guilty_idx, meta))
        files = new_files

    repo = tempfile.mkdtemp(prefix="bench-case-")
    try:
        git(repo, "init", "-q", "-b", "main")
        write_files(repo, base)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "Initial commit")
        commits, prev, first_failing = [], base, None
        for i, (message, new_files, guilty, meta) in enumerate(steps):
            changed = sorted(p for p in new_files if new_files[p] != prev.get(p))
            if not changed:
                return None
            write_files(repo, {p: new_files[p] for p in changed})
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", message)
            sha = git(repo, "rev-parse", "HEAD")
            ok, _ = pytest_in(repo)
            if not ok and first_failing is None:
                first_failing = sha
            if i < guilty_idx and not ok:
                return None  # a decoy broke the build before the guilty commit
            if guilty and category != "latent_bug" and ok:
                return None  # the guilty edit did not actually fail
            if guilty and category == "latent_bug" and not ok:
                return None
            commits.append({"sha": sha, "message": message, "files": changed,
                            "patch": "\n".join(git_patch(repo, sha, p) for p in changed)[:3000],
                            "guilty": guilty, "role": meta["kind"], "same_function": meta.get("same_function", False)})
            prev = new_files

        ok, log = pytest_in(repo, verbose=True)
        if ok:
            return None
        guilty_sha = commits[guilty_idx]["sha"]
        reverted = subprocess.run(["git", "revert", "--no-commit", guilty_sha], cwd=repo, capture_output=True, env=ENV)
        if reverted.returncode != 0 or not pytest_in(repo)[0]:
            return None  # reverting the guilty commit alone does not fix the head
        git(repo, "reset", "-q", "--hard", "HEAD")
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    log = log.replace(repo, CI_ROOT).replace(str(Path(repo).resolve()), CI_ROOT)
    log = f"Run python -m pytest -v\n{log}\nError: Process completed with exit code 1.\n"
    decoys = [c for c in commits if not c["guilty"]]
    hard = (category == "latent_bug" or any(c["same_function"] for c in decoys)
            or (guilty_idx != n_commits - 1 and any(src_path(module) in c["files"] or test_path(module) in c["files"]
                                                     for c in commits[guilty_idx + 1:])))
    difficulty = "easy" if n_commits == 1 else ("hard" if hard else "medium")
    return {
        "id": case_id, "category": category, "difficulty": difficulty, "n_commits": n_commits,
        "module": module, "func": func, "guilty_index": guilty_idx, "guilty_sha": guilty_sha,
        "first_failing_sha": first_failing,
        "mutation": {k: v for k, v in spec.items() if k in ("kind", "idx", "old", "new")},
        "commits": commits, "log": log,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cases", type=int, default=140)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    rng = random.Random(args.seed)

    base, heldout, scratch = read_fixture(), load_heldout(), Scratch()
    pool = screen(base, heldout, scratch)
    print("Screened guilty edits: " + ", ".join(f"{k} {len(v)}" for k, v in pool.items()))

    targets = {c: round(args.cases * w) for c, w in CATEGORY_TARGETS.items()}
    targets["logic_bug"] += args.cases - sum(targets.values())
    cases, n = [], 0
    for category, target in targets.items():
        specs = pool[category][:]
        rng.shuffle(specs)
        made, attempts = 0, 0
        while made < target and attempts < target * 8 and specs:
            spec = specs[attempts % len(specs)]
            attempts += 1
            n_commits = rng.choices(list(COMMIT_COUNT_WEIGHTS), weights=list(COMMIT_COUNT_WEIGHTS.values()))[0]
            case = build_case(f"b{n + 1:03d}", category, spec, n_commits, base, rng, heldout, scratch)
            if case is None:
                continue
            cases.append(case)
            n += 1
            made += 1
            print(f"  {case['id']} {category:<11} {case['difficulty']:<6} {case['n_commits']} commit(s)  "
                  f"{case['module']}.{case['func']}")
        if made < target:
            print(f"  warning: only {made}/{target} {category} cases could be built")
    shutil.rmtree(scratch.dir, ignore_errors=True)

    OUT.write_text("".join(json.dumps(c) + "\n" for c in cases))
    print(f"\n{len(cases)} cases -> {OUT.relative_to(ROOT)}")
    for field in ("category", "difficulty", "n_commits"):
        print(f"  by {field}: " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(c[field] for c in cases).items())))


if __name__ == "__main__":
    main()
