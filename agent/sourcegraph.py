"""Sourcegraph code search: gives the LLM outside evidence about the failure from public code.

Two retrieval queries run against Sourcegraph's public index (this repo itself is too small to be
indexed on sourcegraph.com): (1) for dependency pins added in a patch, which versions of that
package real requirements files use; (2) the exact error message, to see how it occurs in the wild.
Searching this repo's own symbols is opt-in (SRC_SEARCH_REPO=1) for instances that do index it.

Configured by SRC_ACCESS_TOKEN (required), SRC_ENDPOINT (default https://sourcegraph.com) and
SRC_REV (optional revision to search; default is the repo's default branch, which on
sourcegraph.com is usually the only indexed one). Any failure returns "" so triage never
depends on Sourcegraph being reachable.
"""

import os
import re

import requests

ENDPOINT = (os.environ.get("SRC_ENDPOINT") or "https://sourcegraph.com").rstrip("/")
IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
STOP_WORDS = {
    "assert", "error", "failed", "failure", "where", "test", "tests", "passed", "traceback", "line",
    "file", "module", "import", "from", "none", "true", "false", "self", "return", "def", "class",
    "pytest", "python", "usr", "lib", "site", "packages", "home", "runner", "work", "github",
    "short", "summary", "info", "session", "collecting", "collected", "items", "root", "rootdir",
    "platform", "linux", "plugins", "cachedir", "exit", "code", "process", "completed", "run",
}
GRAPHQL = """
query($q: String!) {
  search(query: $q, version: V3) {
    results {
      results {
        ... on FileMatch { file { path } lineMatches { preview lineNumber } }
      }
    }
  }
}
"""


def enabled():
    return bool(os.environ.get("SRC_ACCESS_TOKEN", "").strip())


def key_identifiers(error_text, patch_text, limit=4):
    """Identifiers that appear in both the error and the changed lines rank first, then error-only ones."""
    changed = "\n".join(l[1:] for l in patch_text.splitlines()
                        if l.startswith(("+", "-")) and not l.startswith(("+++", "---")))
    in_error = [w for w in dict.fromkeys(IDENTIFIER_PATTERN.findall(error_text)) if w.lower() not in STOP_WORDS]
    in_patch = set(IDENTIFIER_PATTERN.findall(changed))
    ranked = [w for w in in_error if w in in_patch] + [w for w in in_error if w not in in_patch]
    return ranked[:limit]


def run_query(query, count=5):
    resp = requests.post(
        f"{ENDPOINT}/.api/graphql",
        headers={"Authorization": f"token {os.environ['SRC_ACCESS_TOKEN'].strip()}"},
        json={"query": GRAPHQL, "variables": {"q": query}},
        timeout=20,
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("errors"):
        raise RuntimeError(body["errors"][0]["message"])
    hits = []
    for result in body["data"]["search"]["results"]["results"]:
        for match in result.get("lineMatches", [])[:2]:
            hits.append(f"{result['file']['path']}:{match['lineNumber'] + 1}: {match['preview'].strip()[:160]}")
    return hits[:count]


def search(repo, identifier, rev=None, count=5):
    scope = f"repo:^github\\.com/{re.escape(repo)}$" + (f"@{rev}" if rev else "")
    return run_query(f"{scope} type:file patterntype:regexp count:{count} \\b{identifier}\\b", count)


PIN_PATTERN = re.compile(r"^\+\s*([A-Za-z0-9_.\-]+)\s*==\s*[\w.]+", re.MULTILINE)
ERROR_LINE_PATTERN = re.compile(r"^\s*(?:E\s+)?([A-Za-z]*(?:Error|Exception)): (.+)$", re.MULTILINE)


def pinned_packages(patch_text):
    return list(dict.fromkeys(PIN_PATTERN.findall(patch_text)))[:2]


def error_message(error_text):
    """Exact exception text with quoted/dotted specifics removed so it matches other projects' code."""
    m = ERROR_LINE_PATTERN.search(error_text)
    if not m:
        return None
    msg = re.split(r"['\"(:]", m.group(2))[0].strip()
    return f"{m.group(1)}: {msg}" if len(msg) >= 8 else None


def build_context(repo, error_text, patch_text):
    """Return a text block of Sourcegraph evidence, or "" if unavailable."""
    if not enabled():
        return ""
    sections = []
    try:
        for pkg in pinned_packages(patch_text):
            hits = run_query(f"type:file patterntype:regexp count:5 file:requirements.*\\.txt$ ^{re.escape(pkg)}==", 5)
            if hits:
                sections.append(f"Versions of `{pkg}` pinned in public requirements files:\n" + "\n".join(f"  {h}" for h in hits))
        msg = error_message(error_text)
        if msg:
            hits = run_query(f"type:file patterntype:literal count:3 \"{msg}\"", 3)
            if hits:
                sections.append(f"Public code mentioning `{msg}`:\n" + "\n".join(f"  {h}" for h in hits))
        if os.environ.get("SRC_SEARCH_REPO") == "1":
            rev = os.environ.get("SRC_REV", "").strip() or None
            for ident in key_identifiers(error_text, patch_text):
                hits = search(repo, ident, rev)
                if hits:
                    sections.append(f"`{ident}` appears in this repo at:\n" + "\n".join(f"  {h}" for h in hits))
    except Exception as exc:
        print(f"Sourcegraph unavailable — {type(exc).__name__}: {exc}; continuing without it.")
        return ""
    return "\n\n".join(sections)
