"""Hermes Ollama dashboard plugin — backend API routes.

Mounted at /api/plugins/hermes-ollama/ by Hermes Agent's dashboard
plugin system (see manifest.json). Runs inside Hermes Agent's own
Python process, not this repo's — kept dependency-light (stdlib
urllib.request only, no httpx/requests) since fastapi is the only
third-party package this file can safely assume Hermes's own
environment already provides, same reasoning as
config/hermes_agent_hooks/aegis_gate.py's pre_tool_call hook.

Every route here is a thin proxy to the Hermes Ollama backend's own REST
API (http://127.0.0.1:8000 by default, override with the
HERMES_OLLAMA_BACKEND_URL env var) — the dashboard's JS bundle
(dist/index.js) runs in the browser and can't reach that backend
directly (different origin, and this backend's CORS is locked to
http://localhost:3000, see backend/main.py's CORSMiddleware); this
router runs server-side inside Hermes Agent instead, so it isn't
subject to CORS.

Most routes are read-only. The two write routes (create_project,
create_task) exist so a project can actually be *started* from the
dashboard rather than only observed — they were added after the
2026-07-25 finding that natural-language "crée une tâche" is unreliable
on local models (see README.md's "Telegram gateway" section), which
makes a deterministic click path worth having. Deliberately NOT exposed
as write routes: anything that mutates files, runs a workflow, or
deletes — those either belong behind Aegis (files_apply) or carry a
human-validation gate whose approval flow lives in the agent runtime,
not in a dashboard button.

Not exercised end-to-end against a real Hermes Agent install from this
sandbox (same caveat as aegis_gate.py — hermes-agent.nousresearch.com is
unreachable here) — the proxy logic itself is unit tested directly
against a fake backend server, see backend/tests/
test_hermes_dashboard_plugin.py.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

BACKEND_URL = os.environ.get("HERMES_OLLAMA_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")


def _get_json(path: str, *, timeout: float = 10.0) -> object:
    """GET {BACKEND_URL}<path> and return the parsed JSON body. Raises
    HTTPException(502) if the backend is unreachable or returns
    something that isn't valid JSON — surfaced to the dashboard as a
    normal error response rather than crashing the plugin route, same
    "don't fail the whole page over one unreachable dependency"
    reasoning as GpuMonitor's own Ollama-unreachable handling."""
    url = f"{BACKEND_URL}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - local-only, fixed base URL
            return json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=502, detail=f"Hermes Ollama backend unreachable at {url!r}: {exc}"
        ) from exc


def _post_json(path: str, body: dict, *, timeout: float = 15.0) -> object:
    """POST <body> as JSON to {BACKEND_URL}<path>. Mirrors _get_json's
    error handling, plus HTTPError: the backend's own 4xx (e.g. a
    validation error on an empty title) is forwarded with its status and
    detail intact rather than being flattened into a generic 502, so the
    dashboard can show the real reason a create was rejected."""
    url = f"{BACKEND_URL}{path}"
    data = json.dumps(body).encode()
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - local-only, fixed base URL
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read()).get("detail", exc.reason)
        except (json.JSONDecodeError, ValueError, AttributeError):
            detail = exc.reason
        raise HTTPException(status_code=exc.code, detail=detail) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=502, detail=f"Hermes Ollama backend unreachable at {url!r}: {exc}"
        ) from exc


@router.get("/system-status")
async def system_status():
    return _get_json("/system/status")


@router.get("/projects")
async def projects():
    return _get_json("/projects")


@router.get("/tasks")
async def tasks():
    return _get_json("/tasks")


@router.get("/progression")
async def progression():
    return _get_json("/hse/progression")


@router.get("/messages")
async def messages(limit: int = 25):
    """Inter-agent message bus trace (§9.2) — who asked what of whom, and
    what came back. The one view that answers "what is each agent actually
    doing"; the other routes only show end state (a task's status, a
    project's existence), never the exchange that produced it."""
    return _get_json(f"/messages?limit={int(limit)}")


class ProjectCreate(BaseModel):
    """Mirrors the backend's own ProjectCreateRequest (backend/api/routes/
    projects.py) — declared here rather than imported because this file
    runs inside Hermes Agent's process, which has no import path to this
    repo's backend package."""

    name: str
    description: str = ""


class TaskCreate(BaseModel):
    """Mirrors the backend's TaskCreateRequest. `agent` is intentionally
    omitted: leaving it null lets the backend's own router assign, which
    is the behaviour tasks_create already has from MCP and /tache."""

    title: str
    description: str = ""
    objective: str = ""
    priority: str = "medium"
    project_id: str | None = None


@router.post("/projects")
async def create_project(body: ProjectCreate):
    return _post_json("/projects", body.model_dump())


@router.post("/tasks")
async def create_task(body: TaskCreate):
    return _post_json("/tasks", body.model_dump())
