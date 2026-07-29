"""REST API routes for Oh My Pi (HOS-055B)."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from backend.tools.tool_policy import ToolPolicy
from backend.tools.tool_sandbox import ToolSandbox

from .ohmypi_client import OhMyPiClient
from .ohmypi_mcp_adapter import OhMyPiMCPAdapter


_client = OhMyPiClient()
_policy = ToolPolicy()
_sandbox = ToolSandbox()
_adapter = OhMyPiMCPAdapter(_client, _policy, _sandbox)

ohmypi_router = APIRouter(prefix="/ohmypi", tags=["OhMyPi"])


class ExecuteRequest(BaseModel):
    action: str
    parameters: Optional[dict[str, Any]] = None
    agent_id: str = ""
    mission_id: str = ""


class AnalyzeRequest(BaseModel):
    path: str = "."
    agent_id: str = ""
    mission_id: str = ""


@ohmypi_router.get("/status")
async def get_status():
    return {"status": _adapter.get_status(), "tools": len(_adapter.get_tool_definitions()),
            "capabilities": len(_adapter.get_capabilities())}


@ohmypi_router.get("/capabilities")
async def get_capabilities():
    caps = [{"name": c.name, "description": c.description,
             "inputs": c.inputs, "requires_lsp": c.requires_lsp}
            for c in _adapter.get_capabilities()]
    return {"capabilities": caps, "count": len(caps)}


@ohmypi_router.post("/execute")
async def post_execute(body: ExecuteRequest):
    params = body.parameters or {}
    response = _adapter.execute(action=body.action, parameters=params,
                                 agent_id=body.agent_id, mission_id=body.mission_id)
    return {"id": response.id, "status": response.status.value, "data": response.data,
            "error": response.error, "duration_ms": response.duration_ms,
            "success": response.status.value == "success"}


def handle_get_status() -> dict:
    return {"status": _adapter.get_status(), "tools": len(_adapter.get_tool_definitions()),
            "capabilities": len(_adapter.get_capabilities())}


def handle_get_capabilities() -> dict:
    caps = [{"name": c.name, "description": c.description} for c in _adapter.get_capabilities()]
    return {"capabilities": caps, "count": len(caps)}


def handle_post_execute(action: str, parameters: Optional[dict] = None,
                         agent_id: str = "", mission_id: str = "") -> dict:
    params = parameters or {}
    response = _adapter.execute(action=action, parameters=params, agent_id=agent_id, mission_id=mission_id)
    return {"id": response.id, "status": response.status.value, "data": response.data,
            "error": response.error, "duration_ms": response.duration_ms,
            "success": response.status.value == "success"}
