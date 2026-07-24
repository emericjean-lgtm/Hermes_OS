"""Hermes Ollama dashboard plugin — backend API routes.

Mounted at /api/plugins/hermes-ollama/ by Hermes Agent's dashboard
plugin system (see manifest.json). Runs inside Hermes Agent's own
Python process, not this repo's — kept dependency-light (stdlib
urllib.request only, no httpx/requests) since fastapi is the only
third-party package this file can safely assume Hermes's own
environment already provides, same reasoning as
config/hermes_agent_hooks/aegis_gate.py's pre_tool_call hook.

Every route here is a thin read-only proxy to the Hermes Ollama
backend's own REST API (http://127.0.0.1:8000 by default, override with
the HERMES_OLLAMA_BACKEND_URL env var) — the dashboard's JS bundle
(dist/index.js) runs in the browser and can't reach that backend
directly (different origin, and this backend's CORS is locked to
http://localhost:3000, see backend/main.py's CORSMiddleware); this
router runs server-side inside Hermes Agent instead, so it isn't
subject to CORS.

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

router = APIRouter()

BACKEND_URL = os.environ.get("HERMES_OLLAMA_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")


def _get_json(path: str, *, timeout: float = 5.0) -> object:
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
