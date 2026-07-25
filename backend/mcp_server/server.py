"""MCP server exposing Aegis/Atlas/Echo/Kronos/Minerva/Veritas/Hermes
Scribe/Hermes Eyes/Hermes Swift as tools, plus the inter-agent message
bus trace (core/message_bus.py), hardware/process telemetry
(monitoring/gpu_monitor.py), the workflow engine (workflows/engine.py),
project management (projects/store.py), and self-evolution
(self_evolution/, §20 — skill library + progression tracking), for any
MCP client to call — built specifically so Hermes Agent
(NousResearch's agent runtime, see hermes-agent.nousresearch.com) can
use them when it takes over orchestration from core/router.py +
agents/hermes_prime.py.

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
from collections.abc import Callable
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from backend.agents.aegis import AegisAgent
from backend.agents.echo import EchoAgent
from backend.agents.kronos import KronosAgent
from backend.agents.hermes_eyes import DEFAULT_ANALYSIS_PROMPT, HermesEyesAgent
from backend.agents.hermes_scribe import HermesScribeAgent
from backend.agents.hermes_swift import HermesSwiftAgent
from backend.agents.minerva import MinervaAgent
from backend.agents.veritas import VeritasAgent
from backend.core.agent_registry import get_agent_registry
from backend.core.config import get_settings, load_models_config
from backend.core.message_bus import get_message_bus
from backend.documents.extractor import extract_text
from backend.memory import project_memory
from backend.memory.episodic import MemoryEntry
from backend.memory.skill_library import Skill, status_for
from backend.monitoring.gpu_monitor import get_gpu_monitor
from backend.projects.project_manager import Project
from backend.projects.store import get_project_store
from backend.security.aegis_engine import ActionRequest
from backend.self_evolution import progression_tracker
from backend.self_evolution.pipeline import process_task
from backend.tasks.task_manager import Task
from backend.tools import file_tools, git_tools
from backend.workflows import loader as workflow_loader
from backend.workflows.engine import WorkflowEngine
from backend.workflows.schema import WorkflowDefinition


def _aegis() -> AegisAgent:
    return get_agent_registry().get("aegis")


def _echo() -> EchoAgent:
    return get_agent_registry().get("echo")


def _kronos() -> KronosAgent:
    return get_agent_registry().get("kronos")


def _minerva() -> MinervaAgent:
    return get_agent_registry().get("minerva")


def _veritas() -> VeritasAgent:
    return get_agent_registry().get("veritas")


def _scribe() -> HermesScribeAgent:
    return get_agent_registry().get("hermes_scribe")


def _eyes() -> HermesEyesAgent:
    return get_agent_registry().get("hermes_eyes")


def _swift() -> HermesSwiftAgent:
    return get_agent_registry().get("hermes_swift")


def _task_to_dict(task: Task, *, evolution: dict | None = None) -> dict:
    return {
        "id": task.id,
        "project_id": task.project_id,
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
        "evolution": evolution,
    }


def _project_to_dict(project: Project) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "root_path": project.root_path,
        "status": project.status,
        "tags": project.tags_list,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
    }


def _memory_to_dict(entry: MemoryEntry) -> dict:
    return {
        "id": entry.id,
        "project_id": entry.project_id,
        "type": entry.type,
        "content": entry.content,
        "tags": [t for t in entry.tags.split(",") if t],
        "confidence": entry.confidence,
        "created_at": entry.created_at.isoformat(),
    }


def _skill_to_dict(skill: Skill) -> dict:
    settings = get_settings()
    return {
        "id": skill.id,
        "project_id": skill.project_id,
        "name": skill.name,
        "description": skill.description,
        "procedure": skill.procedure,
        "confidence": skill.confidence,
        "status": status_for(
            skill.confidence,
            min_confidence=settings.skill_min_confidence,
            auto_validate_threshold=settings.skill_auto_validate_threshold,
        ),
        "decay": skill.decay,
        "uses": skill.uses,
        "successes": skill.successes,
        "tags": skill.tags_list,
        "source_task_id": skill.source_task_id,
        "created_at": skill.created_at.isoformat(),
        "updated_at": skill.updated_at.isoformat(),
    }


# ── Aegis: security ──────────────────────────────────────────────────


async def security_evaluate(
    action_type: str,
    description: str,
    target_path: str | None = None,
    requesting_agent: str = "unknown",
    task_id: str | None = None,
    project_id: str | None = None,
    include_advisory: bool = False,
) -> dict:
    """Ask Aegis whether an action is allowed. Returns a verdict
    (allow/deny/require_human_validation) and the reason. Always call
    this before any file write, git operation, system command, or other
    potentially risky action — never assume something is safe.
    requesting_agent identifies the caller for the message bus trace
    (core/message_bus.py) — pass your own agent name if you have one.
    include_advisory=True additionally runs an LLM advisory pass when
    the verdict is require_human_validation (no-op, no extra model call,
    on allow/deny) — context for a human reviewer, never a second vote
    on the verdict itself."""
    aegis = _aegis()
    action = ActionRequest(
        action_type=action_type,
        description=description,
        target_path=target_path,
        requesting_agent=requesting_agent,
        task_id=task_id,
        project_id=project_id,
    )
    decision = aegis.evaluate(action)
    if include_advisory:
        decision = await aegis.advise(action, decision)
    return {
        "verdict": decision.verdict.value,
        "reason": decision.reason,
        "action_type": decision.action_type,
        "advisory": decision.advisory,
    }


# ── Atlas: file tools (Aegis-gated) ───────────────────────────────────


def files_list(path: str, project_id: str | None = None) -> list[str]:
    """List a directory's contents. Only works inside ALLOWED_PATHS, and
    inside the project's root too if project_id is given (see
    projects_* tools)."""
    return file_tools.list_directory(_aegis(), path, project_id=project_id)


def files_read(path: str, project_id: str | None = None) -> str:
    """Read a file's contents. Only works inside ALLOWED_PATHS, and
    inside the project's root too if project_id is given."""
    return file_tools.read_file(_aegis(), path, project_id=project_id)


def files_diff(path: str, new_content: str, project_id: str | None = None) -> str:
    """Preview a unified diff of writing new_content to path, without
    applying it. Use before files_apply to show what would change."""
    before = file_tools.read_existing_or_empty(_aegis(), path, project_id=project_id)
    return file_tools.compute_diff(before, new_content, path)


def files_apply(path: str, new_content: str, project_id: str | None = None) -> dict:
    """Write new_content to path — but only if Aegis allows it. Takes a
    backup of any existing file first. Returns applied (bool), verdict,
    reason, diff, and backup_path. If applied is false, nothing was
    written; check verdict/reason for why."""
    result = file_tools.propose_write(_aegis(), path, new_content, project_id=project_id)
    return {
        "applied": result.applied,
        "verdict": result.verdict,
        "reason": result.reason,
        "diff": result.diff,
        "backup_path": result.backup_path,
    }


# ── Echo: memory ───────────────────────────────────────────────────


def memory_remember(
    type: str,
    content: str,
    tags: list[str] | None = None,
    confidence: float = 1.0,
    project_id: str | None = None,
) -> dict:
    """Store a long-term memory entry (preference, decision, etc.).
    Deduplicated automatically by exact content within the same type and
    project."""
    entry = _echo().remember(
        type_=type, content=content, tags=tags, confidence=confidence, project_id=project_id
    )
    return _memory_to_dict(entry)


def memory_list(type: str | None = None, project_id: str | None = None) -> list[dict]:
    """List stored long-term memory entries, optionally filtered by type
    and/or project."""
    return [_memory_to_dict(e) for e in _echo().list_memories(type_=type, project_id=project_id)]


def memory_forget(memory_id: str) -> bool:
    """Delete a memory entry by id. Returns whether it existed."""
    return _echo().forget(memory_id)


def memory_index(
    doc_id: str, text: str, metadata: dict | None = None, project_id: str | None = None
) -> int:
    """Chunk and index a document into the documentary/RAG memory store.
    Requires a live Ollama server for embeddings. Returns chunks indexed."""
    return _echo().index_document(doc_id, text, metadata or {}, project_id=project_id)


def memory_search(query: str, n_results: int = 5, project_id: str | None = None) -> list[dict]:
    """Semantic search over indexed documents, optionally scoped to a
    project. Requires a live Ollama server for embeddings."""
    return _echo().recall(query, n_results=n_results, project_id=project_id)


def memory_project_brief(project_id: str) -> dict:
    """Everything remembered about one project, grouped by the kinds the
    cahier des charges §12 names: architecture, roadmap, decision,
    documentation. Load this ONCE before working on a project instead of
    listing every memory and sorting them yourself. Entries whose type
    falls outside that vocabulary come back under "other" rather than
    being dropped. Permanent memory (preferences, rules) is deliberately
    not folded in — use memory_list for that."""
    brief = _echo().project_brief(project_id)
    return {
        "project_id": brief.project_id,
        "by_type": brief.by_type,
        "other": brief.other,
        "total": brief.total,
    }


def memory_known_types() -> dict:
    """The §12 memory vocabulary: which `type` values belong to project
    memory and which to permanent memory. Unknown types are still
    accepted by memory_remember — this is guidance, not a whitelist."""
    return project_memory.known_types()


def documents_index(
    path: str,
    doc_id: str | None = None,
    metadata: dict | None = None,
    project_id: str | None = None,
) -> dict:
    """Index a document *file* into the RAG store: read it (Aegis-gated),
    extract its text, chunk, embed. Handles .pdf, .docx, and the plain-text
    family (.md, .txt, .json, .yaml, source code...). Images are refused —
    use analyze_image for those. Unlike memory_index, which needs text you
    have already extracted, this takes a path and does the extraction
    itself. Requires a live Ollama server for embeddings."""
    data = file_tools.read_bytes(_aegis(), path, project_id=project_id)
    extracted = extract_text(path, data=data)

    if not extracted.text.strip():
        # Indexing nothing would create a document that can never match a
        # query, and hide the reason (usually a scanned PDF) in a chunk
        # count of zero.
        return {
            "indexed": False,
            "chunks": 0,
            "format": extracted.format,
            "units": extracted.units,
            "warnings": list(extracted.warnings),
            "reason": "no extractable text",
        }

    chunks = _echo().index_document(
        doc_id or Path(path).name,
        extracted.text,
        {**(metadata or {}), "source_path": path, "format": extracted.format},
        project_id=project_id,
    )
    return {
        "indexed": True,
        "chunks": chunks,
        "format": extracted.format,
        "units": extracted.units,
        "warnings": list(extracted.warnings),
        "characters": len(extracted.text),
    }


# ── Git (§14) — read-only phase ──────────────────────────────────────


def git_status(repo_path: str, project_id: str | None = None) -> dict:
    """Inspect a git repository: current branch, staged/modified/untracked
    files, and how far ahead/behind its upstream it is. `protected` is true
    when the checked-out branch is one you must never commit to directly
    (main/master/production). Read-only — nothing is modified."""
    result = git_tools.status(_aegis(), repo_path, project_id=project_id)
    return {
        "branch": result.branch,
        "detached": result.detached,
        "dirty": result.dirty,
        "staged": list(result.staged),
        "modified": list(result.modified),
        "untracked": list(result.untracked),
        "ahead": result.ahead,
        "behind": result.behind,
        "protected": result.protected,
    }


def git_log(repo_path: str, limit: int = 20, project_id: str | None = None) -> list[dict]:
    """Recent commits of a repository, newest first (sha, author, ISO date,
    subject). Read-only."""
    return [
        {"sha": c.sha, "author": c.author, "date": c.date, "subject": c.subject}
        for c in git_tools.log(_aegis(), repo_path, limit=limit, project_id=project_id)
    ]


def git_branches(repo_path: str, project_id: str | None = None) -> dict:
    """Local and remote branches of a repository, plus the current one.
    Read-only."""
    result = git_tools.branches(_aegis(), repo_path, project_id=project_id)
    return {
        "current": result.current,
        "local": list(result.local),
        "remote": list(result.remote),
    }


def git_diff(
    repo_path: str, staged: bool = False, project_id: str | None = None
) -> str:
    """Uncommitted changes in a repository as a unified diff. Set
    staged=True for what is in the index instead of the working tree.
    Truncated past 20k characters. Read-only."""
    return git_tools.diff(_aegis(), repo_path, staged=staged, project_id=project_id)


def _write_result_to_dict(result) -> dict:
    return {
        "applied": result.applied,
        "operation": result.operation,
        "verdict": result.verdict,
        "reason": result.reason,
        "output": result.output,
        "detail": result.detail,
    }


def git_create_branch(
    repo_path: str,
    name: str,
    from_ref: str | None = None,
    project_id: str | None = None,
) -> dict:
    """Create a branch and check it out. Protected names (main/master/
    production/prod) are refused — §14 forbids working directly on the
    main branch. Returns applied=false with a verdict/reason if Aegis or
    that rule blocks it; nothing is changed in that case."""
    return _write_result_to_dict(
        git_tools.create_branch(
            _aegis(), repo_path, name, from_ref=from_ref, project_id=project_id
        )
    )


def git_commit(
    repo_path: str,
    message: str,
    paths: list[str] | None = None,
    project_id: str | None = None,
) -> dict:
    """Stage and commit. `paths` limits staging to those files; omit it to
    stage everything. REFUSED on a protected branch (§14: never commit
    directly to main) — create a feature branch first. Returns
    applied=false with the reason rather than raising."""
    return _write_result_to_dict(
        git_tools.commit(_aegis(), repo_path, message, paths=paths, project_id=project_id)
    )


def git_push(
    repo_path: str,
    remote: str = "origin",
    branch: str | None = None,
    set_upstream: bool = True,
    project_id: str | None = None,
) -> dict:
    """Push a branch to a remote. REFUSED for protected branches (§14) —
    open a pull request instead. There is deliberately no force option."""
    return _write_result_to_dict(
        git_tools.push(
            _aegis(),
            repo_path,
            remote=remote,
            branch=branch,
            set_upstream=set_upstream,
            project_id=project_id,
        )
    )


def git_revert(repo_path: str, sha: str, project_id: str | None = None) -> dict:
    """Roll back a commit by adding a new commit that undoes it (git
    revert, never reset --hard) — reversible, and it cannot lose committed
    work. Refused on a protected branch."""
    return _write_result_to_dict(
        git_tools.revert_commit(_aegis(), repo_path, sha, project_id=project_id)
    )


def git_create_pull_request(
    repo_path: str,
    title: str,
    body: str,
    base: str = "main",
    project_id: str | None = None,
) -> dict:
    """Open a pull request from the current branch via the gh CLI. This is
    an outward-facing action (it publishes and notifies people), so it is
    classified git_critical — always requires human validation, at any
    autonomy level."""
    return _write_result_to_dict(
        git_tools.create_pull_request(
            _aegis(), repo_path, title, body, base=base, project_id=project_id
        )
    )


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


# ── Veritas: QA review ─────────────────────────────────────────────────


async def verify_output(output: str, context: str = "", criteria: list[str] | None = None) -> dict:
    """Ask Veritas to QA-review another agent's output and report a
    verdict — approved / needs_revision / rejected — plus specific issues
    and suggested corrections. Use this on critical tasks (e.g. after
    Atlas generates code) before treating the work as done. `context`
    should describe what the output was meant to accomplish; `criteria`
    are extra specific things to check."""
    decision, stream = await _veritas().review(output, context=context, criteria=criteria)
    reply = "".join([chunk async for chunk in stream])
    parsed = VeritasAgent.parse_verdict(reply)
    return {
        "verdict": parsed["verdict"],
        "issues": parsed["issues"],
        "corrections": parsed["corrections"],
        "model": decision.model,
    }


# ── Hermes Scribe: writing/documentation ────────────────────────────────


async def write_document(
    brief: str, format: str = "markdown", tone: str = "neutral", context: str = ""
) -> dict:
    """Turn a brief into a complete document (report, README, summary,
    etc.). `format` is the output format (markdown, plain text...), `tone`
    the writing register (neutral, formal, casual...), `context` any
    background the writer should know but that isn't part of the brief."""
    decision, stream = await _scribe().write(brief, format=format, tone=tone, context=context)
    document = "".join([chunk async for chunk in stream])
    return {"document": document, "model": decision.model}


# ── Hermes Eyes: vision ──────────────────────────────────────────────────


async def analyze_image(
    images: list[str], prompt: str = DEFAULT_ANALYSIS_PROMPT, context: str = ""
) -> dict:
    """Analyze one or more images (screenshots, photos, diagrams). `images`
    are base64-encoded strings (no data URI prefix). `prompt` is what to
    look for/describe, `context` is background the model should know
    (e.g. what the screenshot is from). Requires a live Ollama server with
    a multimodal model (config/models.yaml's "vision" role)."""
    decision, stream = await _eyes().analyze(images, prompt=prompt, context=context)
    description = "".join([chunk async for chunk in stream])
    return {"description": description, "model": decision.model}


# ── Hermes Swift: fast pre-routing classification ───────────────────────


async def classify_request(request: str, default: str = "conversation") -> dict:
    """Ask Swift (the always-on, ultra-fast classifier) to label a raw
    request with a task type from config/models.yaml's routing matrix
    (e.g. "code_generation", "research", "writing"). Falls back to
    `default` if the model's reply doesn't match a known task type. Use
    this before routing an ambiguous request to a specific agent/model."""
    decision, stream = await _swift().classify(request)
    reply = "".join([chunk async for chunk in stream])
    task_type = _swift().parse_task_type(reply, default=default)
    return {"task_type": task_type, "model": decision.model}


# ── Kronos: tasks ────────────────────────────────────────────────────


def tasks_create(
    title: str,
    description: str = "",
    objective: str = "",
    priority: str = "medium",
    agent: str | None = None,
    project_id: str | None = None,
) -> dict:
    """Create a new task. Status starts at 'todo'. project_id optionally
    scopes it to a project (see projects_* tools)."""
    task = _kronos().create_task(
        title=title,
        description=description,
        objective=objective,
        priority=priority,
        agent=agent,
        project_id=project_id,
    )
    return _task_to_dict(task)


def tasks_get(task_id: str) -> dict | None:
    """Fetch a task by id, or None if it doesn't exist."""
    task = _kronos().get_task(task_id)
    return _task_to_dict(task) if task else None


def tasks_list(status: str | None = None, project_id: str | None = None) -> list[dict]:
    """List tasks, optionally filtered by status (todo/in_progress/
    blocked/awaiting_validation/in_test/done/cancelled/reversible/
    partially_successful/to_resume) and/or project_id."""
    return [_task_to_dict(t) for t in _kronos().list_tasks(status=status, project_id=project_id)]


def tasks_update(
    task_id: str,
    status: str | None = None,
    files: list[str] | None = None,
    models_used: list[str] | None = None,
    test_results: dict | None = None,
    note: str | None = None,
    project_id: str | None = None,
    run_evolution: bool = False,
) -> dict | None:
    """Update a task: change status, attach touched files/models used,
    record test results, reassign it to a different project, or just
    append a free-form history note. Every change is appended to the
    task's history, nothing overwritten silently. Returns None if the
    task doesn't exist. run_evolution=True additionally runs the self-evolution pipeline
    (self_evolution/pipeline.py) right after — the natural place to
    trigger it, since marking a task done/cancelled/partially_successful
    IS the terminal transition it needs; the result is included under
    the "evolution" key. No-op if the resulting status isn't terminal, and not
    automatic on every update — same opt-in reasoning as
    security_evaluate's include_advisory."""
    task = _kronos().update_task(
        task_id,
        status=status,
        files=files,
        models_used=models_used,
        test_results=test_results,
        note=note,
        project_id=project_id,
    )
    if task is None:
        return None
    evolution_result = process_task(task, _echo()) if run_evolution else None
    return _task_to_dict(task, evolution=evolution_result)


def tasks_delete(task_id: str) -> bool:
    """Delete a task by id. Returns whether it existed."""
    return _kronos().delete_task(task_id)


# ── Message bus: inter-agent trace ───────────────────────────────────────


def messages_list(
    task_id: str | None = None,
    agent: str | None = None,
    project_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """List traced inter-agent bus messages (§9.2/§24.4), most recent
    first. Every Aegis evaluate() call publishes a VALIDATION_REQUEST plus
    a VALIDATION_GRANTED/VALIDATION_DENIED/ESCALATION here, regardless of
    whether it was triggered via a tool call or the REST API. Filter by
    task_id to see the trace for one task, by agent to see everything a
    given agent sent or received, and/or by project_id."""
    messages = get_message_bus().list_messages(
        task_id=task_id, agent=agent, project_id=project_id, limit=limit
    )
    return [m.to_dict() for m in messages]


# ── System: hardware/process telemetry ──────────────────────────────────


async def system_status() -> dict:
    """Hardware/process status (§21): enabled agents, configured model
    roles, GPU VRAM/temperature/load (rocm-smi, null if unavailable —
    e.g. no AMD GPU on this machine), currently-loaded Ollama models,
    CPU/RAM/swap/disk, and any threshold alerts (GPU_ALERT_TEMP_C/
    GPU_CRITICAL_TEMP_C/GPU_VRAM_WARNING_PCT in .env)."""
    registry = get_agent_registry()
    models_config = load_models_config()
    snapshot = await get_gpu_monitor().snapshot()
    return {
        "enabled_agents": registry.list_enabled(),
        "configured_roles": sorted(models_config["roles"]),
        **snapshot.to_dict(),
    }


# ── Workflows: graph of agent actions ──────────────────────────────────


def workflows_list(project_id: str | None = None) -> list[dict]:
    """List all saved workflow definitions, optionally filtered by project_id."""
    return [w.to_dict() for w in workflow_loader.list_workflows(project_id=project_id)]


def workflows_get(workflow_id: str) -> dict | None:
    """Fetch a workflow definition by id, or None if it doesn't exist."""
    try:
        return workflow_loader.load_workflow(workflow_id).to_dict()
    except FileNotFoundError:
        return None


def workflows_create(
    id: str,
    name: str,
    nodes: list[dict],
    edges: list[dict] | None = None,
    description: str = "",
    project_id: str | None = None,
) -> dict:
    """Create/overwrite a workflow definition. Each node is
    {id, action, params, human_validation} where action is a tool name
    from this same tool registry (e.g. "research_query", "files_apply").
    Each edge is {from, to, condition} where condition is
    always/on_success/on_failure (default "always"). project_id
    optionally scopes the workflow to a project (see projects_* tools).
    Raises ValueError if the graph is invalid (missing fields, unknown
    node references, or a cycle)."""
    workflow = WorkflowDefinition.from_dict(
        {
            "id": id,
            "name": name,
            "description": description,
            "nodes": nodes,
            "edges": edges or [],
            "project_id": project_id,
        }
    )
    workflow_loader.save_workflow(workflow)
    return workflow.to_dict()


def workflows_delete(workflow_id: str) -> bool:
    """Delete a workflow definition by id. Returns whether it existed."""
    return workflow_loader.delete_workflow(workflow_id)


def workflows_simulate(workflow_id: str) -> dict:
    """Dry-run a workflow: computes the execution order and which nodes
    are human-validation gates, without calling any agent action or
    touching the message bus."""
    workflow = workflow_loader.load_workflow(workflow_id)
    result = WorkflowEngine().simulate(workflow)
    return {
        "workflow_id": result.workflow_id,
        "execution_order": result.execution_order,
        "human_validation_nodes": result.human_validation_nodes,
        # §6: which nodes run concurrently, and the cap they run under.
        # execution_order alone can't show that.
        "execution_waves": result.execution_waves,
        "max_parallel": result.max_parallel,
    }


def _workflow_run_to_dict(run) -> dict:
    return {
        "id": run.id,
        "workflow_id": run.workflow_id,
        "project_id": run.project_id,
        "status": run.status,
        "node_results": {
            node_id: {
                "node_id": nr.node_id,
                "status": nr.status,
                "result": nr.result,
                "error": nr.error,
            }
            for node_id, nr in run.node_results.items()
        },
        "pending_nodes": run.pending_nodes,
    }


async def workflows_run(
    workflow_id: str, approved_nodes: list[str] | None = None, run_id: str | None = None
) -> dict:
    """Execute a workflow's graph of agent actions (see workflows_create's
    docstring for the node/edge shape). Halts at the first
    human_validation node not listed in approved_nodes. Pass back a
    previous call's "id" as run_id to resume that run past the gate
    instead of re-executing the whole graph from the start — only nodes
    not already decided get (re-)evaluated, and approved_nodes
    accumulates across resumes (see backend/workflows/engine.py). Omit
    run_id to start a fresh run."""
    workflow = workflow_loader.load_workflow(workflow_id)
    run = await WorkflowEngine().run(
        workflow, run_id=run_id, approved_nodes=set(approved_nodes or [])
    )
    return _workflow_run_to_dict(run)


def workflows_get_run(run_id: str) -> dict | None:
    """Fetch a persisted workflow run's current state without executing
    anything. Returns None if no such run exists."""
    run = WorkflowEngine().get_run(run_id)
    return _workflow_run_to_dict(run) if run else None


# ── Projects: multi-project scoping ─────────────────────────────────────


def projects_create(
    name: str, description: str = "", root_path: str | None = None, tags: list[str] | None = None
) -> dict:
    """Create a project. Status starts at 'active'. root_path is a
    suggested filesystem root for this project (not yet enforced as an
    Aegis whitelist — see backend/projects/project_manager.py)."""
    project = get_project_store().create(
        name=name, description=description, root_path=root_path, tags=tags
    )
    return _project_to_dict(project)


def projects_get(project_id: str) -> dict | None:
    """Fetch a project by id, or None if it doesn't exist."""
    project = get_project_store().get(project_id)
    return _project_to_dict(project) if project else None


def projects_list(status: str | None = None, tag: str | None = None) -> list[dict]:
    """List projects, optionally filtered by status (active/archived) or tag."""
    return [_project_to_dict(p) for p in get_project_store().list(status=status, tag=tag)]


def projects_update(
    project_id: str,
    name: str | None = None,
    description: str | None = None,
    root_path: str | None = None,
    status: str | None = None,
    tags: list[str] | None = None,
) -> dict | None:
    """Update a project's fields. Returns None if it doesn't exist."""
    project = get_project_store().update(
        project_id,
        name=name,
        description=description,
        root_path=root_path,
        status=status,
        tags=tags,
    )
    return _project_to_dict(project) if project else None


def projects_delete(project_id: str) -> bool:
    """Delete a project by id. Returns whether it existed."""
    return get_project_store().delete(project_id)


# ── Skills & self-evolution (§20) ────────────────────────────


def skills_list(project_id: str | None = None, tag: str | None = None) -> list[dict]:
    """List skills, optionally filtered by project_id or tag. Each
    skill's `status` (validated/in_review/below_floor) is computed live
    against the current SKILL_MIN_CONFIDENCE/SKILL_AUTO_VALIDATE_THRESHOLD
    settings, not stored."""
    return [_skill_to_dict(s) for s in _echo().list_skills(project_id=project_id, tag=tag)]


def skills_get(skill_id: str) -> dict | None:
    """Fetch a skill by id, or None if it doesn't exist."""
    skill = _echo().get_skill(skill_id)
    return _skill_to_dict(skill) if skill else None


def skills_use(skill_id: str, success: bool) -> dict | None:
    """Record a reuse of an existing skill, nudging its confidence up
    (success) or down (failure) — see memory/skill_library.py's
    record_use(). Returns None if the skill doesn't exist."""
    skill = _echo().use_skill(skill_id, success=success)
    return _skill_to_dict(skill) if skill else None


def skills_delete(skill_id: str) -> bool:
    """Delete a skill by id. Returns whether it existed."""
    return _echo().forget_skill(skill_id)


def skills_index(skill_id: str) -> bool:
    """Index a skill into the semantic search collection (see
    skills_search) — needs a live Ollama server for embeddings, unlike
    every other skills_* tool. Not automatic on skill creation. Returns
    False if the skill doesn't exist."""
    skill = _echo().get_skill(skill_id)
    if skill is None:
        return False
    _echo().index_skill(skill)
    return True


def skills_search(query: str, n_results: int = 5, project_id: str | None = None) -> list[dict]:
    """Semantic search over indexed skills (see skills_index) — needs a
    live Ollama server for embeddings. Returns skills most relevant to
    `query` first, each with a `distance` field (cosine distance: 0.0 is
    identical, larger is less similar)."""
    return [
        {**_skill_to_dict(skill), "distance": distance}
        for skill, distance in _echo().search_skills(query, n_results=n_results, project_id=project_id)
    ]


def evolution_process_task(task_id: str) -> dict:
    """Runs the self-evolution pipeline for one task (evaluate success/failure ->
    extract a new skill on clean success -> reflect if
    REFLECTION_ENABLED) — see self_evolution/pipeline.py. Safe to call on
    a non-terminal task: returns outcome=None/skill_id=None/
    reflection=None rather than erroring. Raises if the task doesn't
    exist."""
    task = _kronos().get_task(task_id)
    if task is None:
        raise ValueError(f"No task {task_id!r}")
    return process_task(task, _echo())


def evolution_progression(project_id: str | None = None) -> dict:
    """Aggregate self-evolution stats (task success rate, skills created/validated/
    in_review, average skill confidence), optionally scoped to a
    project — see self_evolution/progression_tracker.py."""
    tasks = _kronos().list_tasks(project_id=project_id)
    skills = _echo().list_skills(project_id=project_id)
    return progression_tracker.compute_progression(tasks, skills)


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
    memory_project_brief,
    memory_known_types,
    documents_index,
    git_status,
    git_log,
    git_branches,
    git_diff,
    git_create_branch,
    git_commit,
    git_push,
    git_revert,
    git_create_pull_request,
    research_query,
    verify_output,
    write_document,
    analyze_image,
    classify_request,
    tasks_create,
    tasks_get,
    tasks_list,
    tasks_update,
    tasks_delete,
    messages_list,
    system_status,
    workflows_list,
    workflows_get,
    workflows_create,
    workflows_delete,
    workflows_simulate,
    workflows_run,
    workflows_get_run,
    projects_create,
    projects_get,
    projects_list,
    projects_update,
    projects_delete,
    skills_list,
    skills_get,
    skills_use,
    skills_delete,
    skills_index,
    skills_search,
    evolution_process_task,
    evolution_progression,
]


def get_tool_registry() -> dict[str, Callable]:
    """Name -> tool function, for anything that needs to dispatch by name
    rather than import each tool individually. Currently used by the
    workflow engine (backend/workflows/engine.py): every function above
    already normalizes whatever tuple/stream-returning agent method it
    wraps into a plain params-in, dict/list/bool/str-out call — reusing
    that here means the engine doesn't need a second per-agent adapter
    layer just to sequence agent actions in a graph."""
    return {fn.__name__: fn for fn in _ALL_TOOLS}


def create_mcp_server() -> FastMCP:
    """Builds a fresh FastMCP instance with every tool registered. Call
    this once per app instance (see backend/main.py's create_app()) —
    never share one FastMCP/session-manager across multiple app
    lifespans, its streamable-HTTP session manager can only run() once."""
    server = FastMCP(
        name="hermes-ollama",
        instructions=(
            "Tools for Hermes Ollama's security gate (Aegis), file operations "
            "(Atlas), persistent memory (Echo), task tracking (Kronos), "
            "research/RAG (Minerva), QA review (Veritas), writing/"
            "documentation (Hermes Scribe), image analysis (Hermes Eyes), fast "
            "request classification (Hermes Swift), the inter-agent message "
            "bus trace (messages_list), hardware/process telemetry "
            "(system_status), workflows chaining these actions into a "
            "graph (workflows_*), multi-project scoping (projects_*), and "
            "self-evolution (skills_*, evolution_process_task, evolution_progression) "
            "— skills extracted from successfully completed tasks, with a "
            "confidence score that reuse reinforces and decays over time. "
            "Every file/security operation is bound by "
            "ALLOWED_PATHS and the configured autonomy level "
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
