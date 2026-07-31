"""REST API routes for the KlaatCode integration (HOS-054B).

Exposes:
    GET  /klaatcode/status              — adapter status + client stats
    GET  /klaatcode/capabilities        — list of exposed capabilities
    POST /klaatcode/analyze             — analyse a project
    POST /klaatcode/execute             — execute any KlaatCode action
    POST /klaatcode/diagnostics         — run diagnostics on a file
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from backend.tools.tool_policy import ToolPolicy
from backend.tools.tool_sandbox import ToolSandbox

from .klaatcode_client import KlaatCodeClient
from .klaatcode_mcp_adapter import KlaatCodeMCPAdapter


# ── Global instances ─────────────────────────────────────────
# These are instantiated once and reused across requests.

_client = KlaatCodeClient()
_policy = ToolPolicy()
_sandbox = ToolSandbox()
_adapter = KlaatCodeMCPAdapter(_client, _policy, _sandbox)


# ── FastAPI Router ───────────────────────────────────────────

klaatcode_router = APIRouter(prefix="/klaatcode", tags=["KlaatCode"])


# ── Request models ───────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    path: str = "."
    agent_id: str = ""
    mission_id: str = ""


class ExecuteRequest(BaseModel):
    action: str
    parameters: Optional[dict[str, Any]] = None
    agent_id: str = ""
    mission_id: str = ""


class DiagnosticsRequest(BaseModel):
    file: str = "."
    agent_id: str = ""
    mission_id: str = ""


# ── Route handlers ───────────────────────────────────────────

@klaatcode_router.get("/status")
async def get_status():
    """GET /klaatcode/status — adapter status + client stats."""
    return {
        "status": _adapter.get_status(),
        "tools": len(_adapter.get_tool_definitions()),
        "capabilities": len(_adapter.get_capabilities()),
    }


@klaatcode_router.get("/capabilities")
async def get_capabilities():
    """GET /klaatcode/capabilities — all KlaatCode capabilities exposed via MCP."""
    return {
        "capabilities": _adapter.get_capability_list(),
        "count": len(_adapter.get_capabilities()),
    }


@klaatcode_router.post("/analyze")
async def post_analyze(body: AnalyzeRequest):
    """POST /klaatcode/analyze — analyse a code project."""
    response = _adapter.analyze_project(
        path=body.path,
        agent_id=body.agent_id,
        mission_id=body.mission_id,
    )
    return _response_to_dict(response)


@klaatcode_router.post("/execute")
async def post_execute(body: ExecuteRequest):
    """POST /klaatcode/execute — execute any KlaatCode action."""
    params = body.parameters or {}
    response = _adapter.execute(
        action=body.action,
        parameters=params,
        agent_id=body.agent_id,
        mission_id=body.mission_id,
    )
    return _response_to_dict(response)


@klaatcode_router.post("/diagnostics")
async def post_diagnostics(body: DiagnosticsRequest):
    """POST /klaatcode/diagnostics — run code diagnostics."""
    response = _adapter.run_diagnostics(
        file=body.file,
        agent_id=body.agent_id,
        mission_id=body.mission_id,
    )
    return _response_to_dict(response)


# ── Helpers ──────────────────────────────────────────────────

def _response_to_dict(response) -> dict:
    """Serialize a KlaatCodeResponse to a JSON-safe dict."""
    return {
        "id": response.id,
        "request_id": response.request_id,
        "status": response.status.value,
        "data": response.data,
        "error": response.error,
        "duration_ms": response.duration_ms,
        "timestamp": response.timestamp.isoformat() if response.timestamp else None,
        "success": response.status.value == "success",
    }


# ── Backward-compatible handler functions (for test imports) ─

def handle_get_status() -> dict:
    return {
        "status": _adapter.get_status(),
        "tools": len(_adapter.get_tool_definitions()),
        "capabilities": len(_adapter.get_capabilities()),
    }


def handle_get_capabilities() -> dict:
    return {
        "capabilities": _adapter.get_capability_list(),
        "count": len(_adapter.get_capabilities()),
    }


def handle_post_analyze(
    path: str = ".",
    agent_id: str = "",
    mission_id: str = "",
) -> dict:
    response = _adapter.analyze_project(path=path, agent_id=agent_id, mission_id=mission_id)
    return _response_to_dict(response)


def handle_post_execute(
    action: str,
    parameters: Optional[dict] = None,
    agent_id: str = "",
    mission_id: str = "",
) -> dict:
    params = parameters or {}
    response = _adapter.execute(action=action, parameters=params,
                                agent_id=agent_id, mission_id=mission_id)
    return _response_to_dict(response)


def handle_post_diagnostics(
    file: str = ".",
    agent_id: str = "",
    mission_id: str = "",
) -> dict:
    response = _adapter.run_diagnostics(file=file, agent_id=agent_id, mission_id=mission_id)
    return _response_to_dict(response)
