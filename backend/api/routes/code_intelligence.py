"""GET/POST /api/v1/code-intelligence — the missing HTTP surface (R-006).

CodeIntelligenceAgent and CodeIntelligenceRouter (HOS-055D) were real,
non-trivial code that no route ever called — this module is adapters only,
wired onto the real container-built agent (see
``backend/core/bootstrap/service_registry.py::_make_code_intelligence``).
No routing/scoring/execution logic lives here.

Endpoint status, so nothing here claims a capability that doesn't exist:

* ``GET  /status``        IMPLEMENTED — real agent + router counters.
* ``GET  /capabilities``  IMPLEMENTED — real profile/task-type catalogue.
* ``GET  /providers``     IMPLEMENTED — same adapter status KlaatCode/Oh My
  Pi's own routes already serve (no second status check).
* ``POST /analyze``       IMPLEMENTED — routes to CODE_ANALYSIS.
* ``POST /review``        IMPLEMENTED — routes to CODE_REVIEW.
* ``POST /debug``         IMPLEMENTED — routes to DEBUGGING.
* ``POST /explain``       IMPLEMENTED — routes to DOCUMENTATION, the closest
  real ``CodeIntelligenceTaskType``; there is no dedicated "explain" task
  type in the underlying model, so this is an honest relabelling, not a new
  capability.
* ``GET  /history``       IMPLEMENTED — the agent's real task record log.

REFACTOR/AST/LSP/CODEGRAPH endpoints from the original brief are NOT
IMPLEMENTED here — out of this phase's minimum surface; adding them without
a real, exercised contract behind them would be exactly the fabricated
dashboard this release is fixing.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.agents.specialized.code_intelligence.code_intelligence_agent import (
    CodeIntelligenceAgent,
)
from backend.integrations.code_intelligence.code_intelligence_models import (
    CodeIntelligenceTaskType,
    CodeProvider,
)

router = APIRouter(prefix="/code-intelligence", tags=["code-intelligence"])

_agent: Optional[CodeIntelligenceAgent] = None


def create_code_intelligence_routes(agent: CodeIntelligenceAgent) -> APIRouter:
    global _agent
    _agent = agent
    return router


def _ensure() -> CodeIntelligenceAgent:
    if _agent is None:
        raise HTTPException(503, "Code Intelligence agent not initialized")
    return _agent


def _parse_force_provider(raw: Optional[str]) -> Optional[CodeProvider]:
    if raw is None:
        return None
    try:
        return CodeProvider(raw)
    except ValueError:
        valid = ", ".join(p.value for p in CodeProvider)
        raise HTTPException(422, f"force_provider must be one of: {valid}") from None


class CodeTaskRequest(BaseModel):
    project_path: str = "."
    language: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    mission_id: str = ""
    node_id: str = ""
    # Validated against CodeProvider by hand (see _parse_force_provider) so an
    # invalid value 422s with the real allowed set, not a Pydantic enum dump.
    force_provider: Optional[str] = None


def _run(task_type: CodeIntelligenceTaskType, body: CodeTaskRequest) -> dict:
    agent = _ensure()
    force = _parse_force_provider(body.force_provider)
    parameters = {
        **body.parameters,
        "project_path": body.project_path,
        # KlaatCode's own client reads "path" for analyze_project, not
        # "project_path" — an explicit caller-supplied "path" still wins.
        "path": body.parameters.get("path", body.project_path),
        "language": body.language,
    }
    result = agent.execute_task(
        task_type.value,
        parameters,
        mission_id=body.mission_id,
        node_id=body.node_id,
        force_provider=force,
    )
    return {
        "success": result.outcome.value == "success",
        "summary": result.summary,
        "duration_ms": result.duration_ms,
        "data": result.details.get("data") if result.details else None,
        "provider": result.details.get("provider") if result.details else None,
        "strategy": result.details.get("strategy") if result.details else None,
        "decision": result.details.get("decision") if result.details else None,
        "error": result.error_message or None,
    }


@router.get("/status")
async def get_status() -> dict:
    return _ensure().get_status_dict()


@router.get("/capabilities")
async def get_capabilities() -> dict:
    agent = _ensure()
    return {
        "capabilities": [c.value for c in agent.agent_capabilities],
        "providers": agent.profile.providers,
        "task_types": [t.value for t in CodeIntelligenceTaskType],
    }


@router.get("/providers")
async def get_providers() -> dict:
    """Reuses each provider's own real status check — the same one
    ``GET /klaatcode/status``/``GET /ohmypi/status`` already serve — rather
    than computing a second, possibly-diverging notion of availability."""
    agent = _ensure()
    kc = agent._klaatcode_agent  # noqa: SLF001 - same module, intentional
    omp = agent._ohmypi_agent  # noqa: SLF001
    hn = agent._hermes_native_executor  # noqa: SLF001

    def _provider_view(sub_agent: Any) -> dict:
        if sub_agent is None:
            return {"available": False, "status": None}
        adapter = getattr(sub_agent, "_mcp_adapter", None)
        return {
            "available": bool(sub_agent.is_available),
            "status": adapter.get_status() if adapter is not None else None,
        }

    return {
        "klaatcode": _provider_view(kc),
        "ohmypi": _provider_view(omp),
        "hermes_native": {
            "available": hn is not None and bool(hn.is_available),
            "status": None if hn is None else {"agent_id": hn.agent_id},
        },
    }


@router.post("/analyze")
async def post_analyze(body: CodeTaskRequest) -> dict:
    return _run(CodeIntelligenceTaskType.CODE_ANALYSIS, body)


@router.post("/review")
async def post_review(body: CodeTaskRequest) -> dict:
    return _run(CodeIntelligenceTaskType.CODE_REVIEW, body)


@router.post("/debug")
async def post_debug(body: CodeTaskRequest) -> dict:
    return _run(CodeIntelligenceTaskType.DEBUGGING, body)


@router.post("/explain")
async def post_explain(body: CodeTaskRequest) -> dict:
    return _run(CodeIntelligenceTaskType.DOCUMENTATION, body)


@router.get("/history")
async def get_history(limit: int = 50) -> dict:
    agent = _ensure()
    records = agent.get_task_history(limit=limit)
    return {"history": records, "total": len(records)}
