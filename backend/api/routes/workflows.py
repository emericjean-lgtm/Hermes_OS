"""Workflow endpoints — cahier des charges §15, §24.1 (GET /workflows,
POST /workflows, POST /workflows/{id}/run, POST /workflows/{id}/simulate).
Wraps backend/workflows/{schema,loader,engine}.py; GET/{id} and DELETE
are natural additions matching /tasks and /memory's CRUD shape, not
explicitly named in §24.1 but consistent with it.

Nodes/edges travel as plain dicts, not typed Pydantic sub-models: the
spec's edge contract uses "from", which isn't a valid Python field name
(same reasoning as messages.py) — WorkflowDefinition.from_dict()/
to_dict() already do this conversion, so routes just pass dicts through.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.workflows import loader
from backend.workflows.engine import NodeResult, WorkflowEngine, WorkflowExecutionError, WorkflowRun
from backend.workflows.schema import InvalidWorkflowError, WorkflowDefinition

router = APIRouter()


def _engine() -> WorkflowEngine:
    # Constructed fresh per call, not a module-level singleton: it opens
    # a SQLite connection (for run persistence, see engine.py) resolved
    # from get_settings() at construction time — a singleton built once
    # at import time would freeze that path before tests ever get a
    # chance to override SQLITE_PATH. Cheap enough to build per call
    # (same pattern mcp_server/server.py's workflows_* tools already use).
    return WorkflowEngine()


class WorkflowCreateRequest(BaseModel):
    id: str
    name: str
    description: str = ""
    nodes: list[dict]
    edges: list[dict] = []
    project_id: str | None = None


class RunRequest(BaseModel):
    approved_nodes: list[str] = []
    # Pass back a previous run's "id" to resume it past a
    # human_validation gate instead of re-executing the whole graph —
    # see engine.py's run() docstring. Omit to start a fresh run.
    run_id: str | None = None


def _node_result_to_dict(node_result: NodeResult) -> dict:
    return {
        "node_id": node_result.node_id,
        "status": node_result.status,
        "result": node_result.result,
        "error": node_result.error,
    }


def _run_to_dict(run: WorkflowRun) -> dict:
    return {
        "id": run.id,
        "workflow_id": run.workflow_id,
        "project_id": run.project_id,
        "status": run.status,
        "node_results": {
            node_id: _node_result_to_dict(nr) for node_id, nr in run.node_results.items()
        },
        "pending_nodes": run.pending_nodes,
    }


@router.get("/workflows")
async def list_workflows(project_id: str | None = None) -> list[dict]:
    return [w.to_dict() for w in loader.list_workflows(project_id=project_id)]


@router.post("/workflows")
async def create_workflow(request: WorkflowCreateRequest) -> dict:
    try:
        workflow = WorkflowDefinition.from_dict(request.model_dump())
    except InvalidWorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    loader.save_workflow(workflow)
    return workflow.to_dict()


@router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str) -> dict:
    try:
        return loader.load_workflow(workflow_id).to_dict()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/workflows/{workflow_id}")
async def delete_workflow(workflow_id: str) -> dict:
    if not loader.delete_workflow(workflow_id):
        raise HTTPException(status_code=404, detail=f"No workflow {workflow_id!r}")
    return {"deleted": True, "id": workflow_id}


@router.post("/workflows/{workflow_id}/simulate")
async def simulate_workflow(workflow_id: str) -> dict:
    try:
        workflow = loader.load_workflow(workflow_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    result = _engine().simulate(workflow)
    return {
        "workflow_id": result.workflow_id,
        "execution_order": result.execution_order,
        "human_validation_nodes": result.human_validation_nodes,
        # §6: which nodes run concurrently, and the cap they run under.
        # execution_order alone can't show that.
        "execution_waves": result.execution_waves,
        "max_parallel": result.max_parallel,
    }


@router.post("/workflows/{workflow_id}/run")
async def run_workflow(workflow_id: str, request: RunRequest) -> dict:
    try:
        workflow = loader.load_workflow(workflow_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        run = await _engine().run(
            workflow, run_id=request.run_id, approved_nodes=set(request.approved_nodes)
        )
    except WorkflowExecutionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _run_to_dict(run)


@router.get("/workflows/runs/{run_id}")
async def get_workflow_run(run_id: str) -> dict:
    run = _engine().get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"No workflow run {run_id!r}")
    return _run_to_dict(run)
