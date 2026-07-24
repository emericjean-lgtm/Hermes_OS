"""MCP server exposing Aegis/Atlas/Echo/Kronos/Minerva as tools for any
MCP client to call — built specifically so Hermes Agent (NousResearch's
agent runtime, see hermes-agent.nousresearch.com) can use them when it
takes over orchestration from core/router.py + agents/hermes_prime.py.

Mounted into the main FastAPI app at /mcp (see backend/main.py), so
there's still one process to run: an MCP client (Hermes Agent's
`mcp_servers` config, an "http" server) points at
http://<host>:8000/mcp.

Every tool here is a thin wrapper around the same agents the REST API
uses (backend/api/routes/*.py) — no business logic lives in this file.

Deliberately NOT using `from __future__ import annotations` (unlike the
rest of this codebase): FastMCP's tool registration reads live type
objects off each parameter to build the tool's JSON schema, not
stringified annotations, and PEP 563's postponed evaluation breaks that
introspection (confirmed: `issubclass() arg 1 must be a class` on every
`X | None` param until this import was removed).

Tools are plain functions registered onto a FastMCP instance via
create_mcp_server() rather than the more common `@mcp.tool()` decorator
on a module-level instance: a FastMCP's streamable-HTTP session manager
can only be `.run()` once per instance (see backend/main.py's lifespan),
so anything that needs a fresh app per call — tests, mainly — needs a
fresh FastMCP too. A decorator bound at import time can't give you that.
"""
from mcp.server.fastmcp import FastMCP

from backend.agents.aegis import AegisAgent
from backend.agents.echo import EchoAgent
from backend.agents.kronos import KronosAgent
from backend.agents.minerva import MinervaAgent
from backend.core.agent_registry import get_agent_registry
from backend.memory.episodic import MemoryEntry
from backend.security.aegis_engine import ActionRequest
from backend.tasks.task_manager import Task
from backend.tools import file_tools


def _aegis() -> AegisAgent:
    return get_agent_registry().get("aegis")


def _echo() -> EchoAgent:
    return get_agent_registry().get("echo")


def _kronos() -> KronosAgent:
    return get_agent_registry().get("kronos")


def _minerva() -> MinervaAgent:
    return get_agent_registry().get("minerva")


def _task_to_dict(task: Task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "objective": task.objective,
        "status": task.status,
        "priority": task.priority,
        "agent": task.agent,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "models_used": task.models_used_list,
        "files": task.files_list,
        "test_results": task.test_results_dict,
        "history": task.history_list,
    }


def _memory_to_dict(entry: MemoryEntry) -> dict:
    return {
        "id": entry.id,
        "type": entry.type,
        "content": entry.content,
        "tags": [t for t in entry.tags.split(",") if t],
        "confidence": entry.confidence,
        "created_at": entry.created_at.isoformat(),
    }


# ── Aegis: security ──────────────────────────────────────────────────


def security_evaluate(action_type: str, description: str, target_path: str | None = None) -> dict:
    """Ask Aegis whether an action is allowed. Returns a verdict
    (allow/deny/require_human_validation) and the reason. Always call
    this before any file write, git operation, system command, or other
    potentially risky action — never assume something is safe."""
    decision = _aegis().evaluate(
        ActionRequest(action_type=action_type, description=description, target_path=target_path)
    )
    return {
        "verdict": decision.verdict.value,
        "reason": decision.reason,
        "action_type": decision.action_type,
    }


# ── Atlas: file tools (Aegis-gated) ───────────────────────────────────


def files_list(path: str) -> list[str]:
    """List a directory's contents. Only works inside ALLOWED_PATHS."""
    return file_tools.list_directory(_aegis(), path)


def files_read(path: str) -> str:
    """Read a file's contents. Only works inside ALLOWED_PATHS."""
    return file_tools.read_file(_aegis(), path)


def files_diff(path: str, new_content: str) -> str:
    """Preview a unified diff of writing new_content to path, without
    applying it. Use before files_apply to show what would change."""
    before = file_tools.read_existing_or_empty(_aegis(), path)
    return file_tools.compute_diff(before, new_content, path)


def files_apply(path: str, new_content: str) -> dict:
    """Write new_content to path — but only if Aegis allows it. Takes a
    backup of any existing file first. Returns applied (bool), verdict,
    reason, diff, and backup_path. If applied is false, nothing was
    written; check verdict/reason for why."""
    result = file_tools.propose_write(_aegis(), path, new_content)
    return {
        "applied": result.applied,
        "verdict": result.verdict,
        "reason": result.reason,
        "diff": result.diff,
        "backup_path": result.backup_path,
    }


# ── Echo: memory ───────────────────────────────────────────────────


def memory_remember(
    type: str, content: str, tags: list[str] | None = None, confidence: float = 1.0
) -> dict:
    """Store a long-term memory entry (preference, decision, etc.).
    Deduplicated automatically by exact content within the same type."""
    entry = _echo().remember(type_=type, content=content, tags=tags, confidence=confidence)
    return _memory_to_dict(entry)


def memory_list(type: str | None = None) -> list[dict]:
    """List stored long-term memory entries, optionally filtered by type."""
    return [_memory_to_dict(e) for e in _echo().list_memories(type_=type)]


def memory_forget(memory_id: str) -> bool:
    """Delete a memory entry by id. Returns whether it existed."""
    return _echo().forget(memory_id)


def memory_index(doc_id: str, text: str, metadata: dict | None = None) -> int:
    """Chunk and index a document into the documentary/RAG memory store.
    Requires a live Ollama server for embeddings. Returns chunks indexed."""
    return _echo().index_document(doc_id, text, metadata or {})


def memory_search(query: str, n_results: int = 5) -> list[dict]:
    """Semantic search over indexed documents. Requires a live Ollama
    server for embeddings."""
    return _echo().recall(query, n_results=n_results)


# ── Minerva: research/RAG ─────────────────────────────────────────────


async def research_query(query: str, n_results: int = 5) -> dict:
    """Retrieve relevant passages from indexed documents and ask an LLM
    to synthesize a cited answer from them (Minerva's RAG loop — retrieval
    + grounded generation, not just a raw model completion). Requires a
    live Ollama server for both the embeddings and the synthesis model.
    Returns answer, passages (with source metadata), and which model
    produced the answer."""
    decision, stream, passages = await _minerva().research(query, n_results=n_results)
    answer = "".join([chunk async for chunk in stream])
    return {"answer": answer, "passages": passages, "model": decision.model}


# ── Kronos: tasks ────────────────────────────────────────────────────


def tasks_create(
    title: str,
    description: str = "",
    objective: str = "",
    priority: str = "medium",
    agent: str | None = None,
) -> dict:
    """Create a new task. Status starts at 'todo'."""
    task = _kronos().create_task(
        title=title, description=description, objective=objective, priority=priority, agent=agent
    )
    return _task_to_dict(task)


def tasks_get(task_id: str) -> dict | None:
    """Fetch a task by id, or None if it doesn't exist."""
    task = _kronos().get_task(task_id)
    return _task_to_dict(task) if task else None


def tasks_list(status: str | None = None) -> list[dict]:
    """List tasks, optionally filtered by status (todo/in_progress/
    blocked/awaiting_validation/in_test/done/cancelled/reversible/
    partially_successful/to_resume)."""
    return [_task_to_dict(t) for t in _kronos().list_tasks(status=status)]


def tasks_update(
    task_id: str,
    status: str | None = None,
    files: list[str] | None = None,
    models_used: list[str] | None = None,
    test_results: dict | None = None,
    note: str | None = None,
) -> dict | None:
    """Update a task: change status, attach touched files/models used,
    record test results, or just append a free-form history note. Every
    change is appended to the task's history, nothing overwritten
    silently. Returns None if the task doesn't exist."""
    task = _kronos().update_task(
        task_id,
        status=status,
        files=files,
        models_used=models_used,
        test_results=test_results,
        note=note,
    )
    return _task_to_dict(task) if task else None


def tasks_delete(task_id: str) -> bool:
    """Delete a task by id. Returns whether it existed."""
    return _kronos().delete_task(task_id)


_ALL_TOOLS = [
    security_evaluate,
    files_list,
    files_read,
    files_diff,
    files_apply,
    memory_remember,
    memory_list,
    memory_forget,
    memory_index,
    memory_search,
    research_query,
    tasks_create,
    tasks_get,
    tasks_list,
    tasks_update,
    tasks_delete,
]


def create_mcp_server() -> FastMCP:
    """Builds a fresh FastMCP instance with every tool registered. Call
    this once per app instance (see backend/main.py's create_app()) —
    never share one FastMCP/session-manager across multiple app
    lifespans, its streamable-HTTP session manager can only run() once."""
    server = FastMCP(
        name="hermes-ollama",
        instructions=(
            "Tools for Hermes Ollama's security gate (Aegis), file operations "
            "(Atlas), persistent memory (Echo), task tracking (Kronos), and "
            "research/RAG (Minerva). Every file/security operation is bound "
            "by ALLOWED_PATHS and the configured autonomy level "
            "(config/security.yaml) — a denied or require_human_validation "
            "verdict means don't proceed."
        ),
        # FastMCP's own default is "/mcp", which would double up with the
        # "/mcp" prefix this app is mounted under in backend/main.py (i.e.
        # requests would need to hit /mcp/mcp). "/" makes the
        # streamable-HTTP route sit at the mounted sub-app's own root.
        streamable_http_path="/",
    )
    for fn in _ALL_TOOLS:
        server.add_tool(fn)
    return server
