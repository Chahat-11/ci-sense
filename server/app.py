"""CI-Sense web API.

    uvicorn server.app:app --reload --port 8787

Reads triage verdicts from the hidden ci-sense-data in github-actions[bot] PR comments,
serves evaluation results, and streams live (never posted) triage runs over SSE.
"""

import asyncio
import datetime
import json
import os
import re
import sys
import threading
import time
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path

import requests
from dotenv import dotenv_values
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

ROOT = Path(__file__).resolve().parent.parent


def normalize_repo(value):
    value = re.sub(r"^(https?://)?(www\.)?github\.com/", "", value.strip())
    return value.removesuffix(".git").strip("/")


# Load .env with whitespace stripped, and hand the agent module a clean environment before importing it.
for key, value in dotenv_values(ROOT / ".env").items():
    if value is not None and key not in os.environ:
        os.environ[key] = value
for key in ("GITHUB_TOKEN", "GROQ_API_KEY", "GROQ_MODEL", "GITHUB_REPO", "GITHUB_REPOSITORY"):
    if key in os.environ:
        os.environ[key] = os.environ[key].strip()
if not os.environ.get("GITHUB_REPOSITORY"):
    os.environ["GITHUB_REPOSITORY"] = normalize_repo(os.environ["GITHUB_REPO"])

sys.path.insert(0, str(ROOT / "agent"))
import triage  # noqa: E402


def _refuse_post(*_args, **_kwargs):
    raise RuntimeError("The web API never posts to GitHub.")


triage.post_comment = _refuse_post

REPO = os.environ["GITHUB_REPOSITORY"]
API = "https://api.github.com"
BOT = "github-actions[bot]"
DATA_PATTERN = re.compile(r"<!-- ci-sense-data (.*?) -->", re.DOTALL)
CACHE_SECONDS = 60
STAGES = ["fetching logs", "distilling", "finding candidates", "scoring", "LLM verdict"]

session = requests.Session()
session.headers.update({
    "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
    "Accept": "application/vnd.github+json",
})

@asynccontextmanager
async def lifespan(_app):
    """Fetch PRs, comments and runs in the background so the first page load is fast."""

    def warm():
        try:
            pull_requests()
            bot_comments()
            failed_runs()
        except Exception as exc:  # the endpoints will surface the error on first request
            print(f"Cache warm-up failed: {type(exc).__name__}")

    threading.Thread(target=warm, daemon=True).start()
    yield


app = FastAPI(title="CI-Sense API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# --- GitHub access with a small in-memory cache -------------------------------------------

_cache = {}
_cache_lock = threading.Lock()


def cached(key, loader):
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
    value = loader()
    with _cache_lock:
        _cache[key] = (now + CACHE_SECONDS, value)
    return value


def gh_paginate(path, params=None):
    url, items = f"{API}{path}", []
    params = {"per_page": 100, **(params or {})}
    while url:
        resp = session.get(url, params=params, timeout=30)
        if resp.status_code >= 400:
            raise HTTPException(502, f"GitHub API error {resp.status_code} on {path}")
        items += resp.json()
        url, params = resp.links.get("next", {}).get("url"), None
    return items


def pull_requests():
    def load():
        return {
            pr["number"]: {
                "number": pr["number"],
                "title": pr["title"],
                "state": "merged" if pr.get("merged_at") else pr["state"],
                "branch": pr["head"]["ref"],
                "url": pr["html_url"],
            }
            for pr in gh_paginate(f"/repos/{REPO}/pulls", {"state": "all"})
        }
    return cached("pulls", load)


def bot_comments():
    """Every github-actions[bot] comment carrying ci-sense-data, parsed, newest first."""

    def load():
        parsed = []
        for c in gh_paginate(f"/repos/{REPO}/issues/comments"):
            if c["user"]["login"] != BOT or "ci-sense-data" not in c["body"]:
                continue
            match = DATA_PATTERN.search(c["body"])
            if not match:
                continue
            try:
                data = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
            parsed.append({
                "id": c["id"],
                "kind": "triage" if "CI-Sense triage" in c["body"] else "note",
                "pr_number": int(c["issue_url"].rsplit("/", 1)[1]),
                "comment_url": c["html_url"],
                "created_at": c["created_at"],
                "data": data,
            })
        parsed.sort(key=lambda c: c["created_at"], reverse=True)
        return parsed
    return cached("comments", load)


def commit_message(data, sha):
    for c in data.get("candidates", []):
        if c["sha"] == sha:
            return c["message"].splitlines()[0]
    return None


def summarize(comment):
    data, prs = comment["data"], pull_requests()
    pr = prs.get(comment["pr_number"], {})
    responsible = data.get("responsible_commit")
    return {
        "id": comment["id"],
        "pr_number": comment["pr_number"],
        "pr_title": pr.get("title"),
        "pr_state": pr.get("state"),
        "pr_url": pr.get("url"),
        "comment_url": comment["comment_url"],
        "created_at": comment["created_at"],
        "run_id": data.get("run_id"),
        "run_url": f"https://github.com/{REPO}/actions/runs/{data.get('run_id')}",
        "head_sha": data.get("head_sha"),
        "is_main_failure": data.get("pr_number") is None,
        "responsible_commit": responsible,
        "responsible_message": commit_message(data, responsible) if responsible else None,
        "confidence": data.get("confidence"),
        "fallback": bool(data.get("fallback")),
        "what_failed": data.get("what_failed"),
        "candidate_count": len(data.get("candidates", [])),
    }


def triages():
    return [c for c in bot_comments() if c["kind"] == "triage"]


# --- Endpoints ----------------------------------------------------------------------------

@app.get("/api/meta")
def meta():
    return {"repo": REPO, "model": triage.GROQ_MODEL, "llm_configured": bool(triage.GROQ_API_KEY)}


@app.get("/api/triages")
def list_triages():
    return [summarize(c) for c in triages()]


@app.get("/api/triages/{comment_id}")
def get_triage(comment_id: int):
    comment = next((c for c in triages() if c["id"] == comment_id), None)
    if comment is None:
        raise HTTPException(404, "Triage not found")
    data = comment["data"]
    notes = [
        {"pr_number": n["pr_number"], "comment_url": n["comment_url"],
         "pr_title": pull_requests().get(n["pr_number"], {}).get("title")}
        for n in bot_comments()
        if n["kind"] == "note" and n["data"].get("run_id") == data.get("run_id")
    ]
    return {**summarize(comment), "result": data, "notes": notes, "repo": REPO}


@app.get("/api/stats")
def stats():
    items = [summarize(c) for c in triages()]
    llm = [t for t in items if not t["fallback"]]
    confidences = [t["confidence"] for t in llm if isinstance(t["confidence"], (int, float))]
    per_day = Counter(t["created_at"][:10] for t in items)
    today = datetime.datetime.now(datetime.timezone.utc).date()
    days = [(today - datetime.timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
    return {
        "triaged": len(items),
        "attributed": sum(1 for t in items if t["responsible_commit"]),
        "abstained": sum(1 for t in items if not t["responsible_commit"]),
        "llm": len(llm),
        "fallback": len(items) - len(llm),
        "avg_confidence": round(sum(confidences) / len(confidences), 3) if confidences else None,
        "per_day": [{"date": d, "count": per_day.get(d, 0)} for d in days],
    }


@app.get("/api/runs/failed")
def failed_runs():
    def load():
        resp = session.get(f"{API}/repos/{REPO}/actions/workflows/test.yml/runs",
                           params={"status": "failure", "per_page": 30}, timeout=30)
        if resp.status_code >= 400:
            raise HTTPException(502, f"GitHub API error {resp.status_code} listing runs")
        return resp.json()["workflow_runs"]

    by_branch = {}
    for pr in sorted(pull_requests().values(), key=lambda p: p["number"]):
        by_branch[pr["branch"]] = pr
    triaged_runs = {c["data"].get("run_id") for c in triages()}
    runs = []
    for run in cached("failed_runs", load):
        pr = by_branch.get(run["head_branch"]) if run["event"] == "pull_request" else None
        runs.append({
            "id": run["id"],
            "branch": run["head_branch"],
            "event": run["event"],
            "head_sha": run["head_sha"],
            "commit_message": ((run.get("head_commit") or {}).get("message") or "").split("\n", 1)[0],
            "created_at": run["created_at"],
            "url": run["html_url"],
            "pr_number": pr["number"] if pr else None,
            "pr_title": pr["title"] if pr else None,
            "triaged": run["id"] in triaged_runs,
        })
    return runs


def deterministic_pick(candidates):
    """Mirror of the agent's fallback: first highest-scored candidate, or nobody if every score is 0."""
    if not candidates:
        return None
    best = max(candidates, key=lambda c: c["score"])
    return best["sha"] if best["score"] > 0 else None


@app.get("/api/evaluation")
def evaluation():
    try:
        results = json.loads((ROOT / "seeds" / "results.json").read_text())
        truth = json.loads((ROOT / "seeds" / "ground_truth.json").read_text())
    except FileNotFoundError:
        raise HTTPException(404, "No evaluation results yet. Run scripts/seed_failures.py and scripts/evaluate.py.")
    truth_by_case = {c["case"]: c for c in truth["cases"]}
    latest_by_pr = {}
    for c in triages():  # newest first
        latest_by_pr.setdefault(c["pr_number"], c)

    cases = []
    for row in results["cases"]:
        gt = truth_by_case.get(row["case"], {})
        comment = latest_by_pr.get(row["pr_number"])
        candidates = comment["data"].get("candidates", []) if comment else []
        det_sha = deterministic_pick(candidates) if comment else None
        messages = {c["sha"]: c["message"].splitlines()[0] for c in gt.get("commits", [])}
        cases.append({
            **row,
            "name": gt.get("name"),
            "description": gt.get("description"),
            "commits": [{**c, "message": c["message"]} for c in gt.get("commits", [])],
            "expected_message": messages.get(row["expected_sha"]),
            "deterministic_sha": det_sha,
            "deterministic_result": None if not comment else (
                "abstained" if det_sha is None else ("correct" if det_sha == row["expected_sha"] else "wrong")
            ),
            "scores": [{"sha": c["sha"], "score": c["score"], "reasons": c["reasons"]} for c in candidates],
            "triage_id": comment["id"] if comment else None,
        })

    completed = [c for c in cases if c["result"] != "pending"]
    det_done = [c for c in cases if c["deterministic_result"]]
    return {
        "summary": results["summary"],
        "cases": cases,
        "accuracy": {
            "llm": round(sum(c["result"] == "correct" for c in completed) / len(completed), 3) if completed else None,
            "deterministic": round(sum(c["deterministic_result"] == "correct" for c in det_done) / len(det_done), 3)
            if det_done else None,
        },
    }


@app.post("/api/triage/{run_id}/stream")
async def stream_triage(run_id: int):
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()
    starts, current = {}, {"stage": None}

    def emit(event):
        loop.call_soon_threadsafe(queue.put_nowait, event)

    def progress(stage, status, preview=None):
        now = time.monotonic()
        if status == "start":
            starts[stage], current["stage"] = now, stage
            emit({"type": "stage", "stage": stage, "status": "running"})
        else:
            duration = round((now - starts.get(stage, now)) * 1000)
            emit({"type": "stage", "stage": stage, "status": "done", "duration_ms": duration, "preview": preview})

    def work():
        started = time.monotonic()
        try:
            result, body = triage.run_pipeline(str(run_id), post=False, progress=progress)
            emit({
                "type": "result",
                "result": result,
                "comment": triage.redact_secrets(body),
                "run_url": f"https://github.com/{REPO}/actions/runs/{run_id}",
                "duration_ms": round((time.monotonic() - started) * 1000),
            })
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            message = f"Run {run_id} was not found in {REPO}." if status == 404 else f"GitHub API error ({status})."
            emit({"type": "error", "stage": current["stage"], "message": message})
        except Exception as exc:  # surfaced to the UI, secrets scrubbed
            emit({"type": "error", "stage": current["stage"],
                  "message": triage.redact_secrets(f"{type(exc).__name__}: {exc}")[:500]})
        finally:
            emit(None)

    threading.Thread(target=work, daemon=True).start()

    async def events():
        yield f"event: started\ndata: {json.dumps({'type': 'started', 'run_id': run_id, 'stages': STAGES})}\n\n"
        while True:
            event = await queue.get()
            if event is None:
                break
            yield f"event: {event['type']}\ndata: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
