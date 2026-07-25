"""Snapshots & rollback — cahier des charges §19.3.

The spec asks for state (tasks, context, modified files) to be saved
every N configurable steps, under `data/snapshots/`, so a mission can be
resumed after an interruption (§19.2) and changes undone (§7, principle
n°4: reversible). It is also acceptance criterion **T8**.

**What is snapshotted, and what deliberately isn't.**

  - *Tasks* and *workflow runs* — the durable application state. Captured
    whole, from SQLite.
  - *Context* — whatever the caller passes: session id, current step,
    mission objective. Free-form on purpose; this module has no business
    deciding what a caller considers its own state.
  - *Modified files* — **not** copied here. `file_tools.propose_write`
    already backs up every file before overwriting it, into that same
    `data/snapshots/` directory. Duplicating that would double the disk
    cost and create two restore paths that could disagree. A snapshot
    records the file *paths* each task touched, so a human can find the
    matching backups; it does not own them.

**Restoring is destructive, and treated as such.** Writing a snapshot
back overwrites tasks that may have progressed since. So restore is
never automatic — not at startup, not on crash recovery — and goes
through Aegis as `data_migration`, which is mandatory_validation at every
autonomy level (§17.3 lists "migration de données"). `preview_restore`
exists so a human can see exactly what would change before agreeing,
the same "show the diff first" contract as file writes (§14.1).

Snapshots are plain JSON files. No new table, no schema migration, and a
snapshot stays readable with `cat` even if this module is broken — which
matters for something whose whole purpose is recovering from a bad state.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from backend.core.config import get_settings
from backend.memory.db import make_engine, make_session_factory
from backend.security.aegis_engine import ActionRequest, Verdict
from backend.tasks.task_manager import Task
from backend.workflows.run_store import WorkflowRunRecord

SNAPSHOT_VERSION = 1


class SnapshotError(RuntimeError):
    pass


@dataclass(frozen=True)
class SnapshotInfo:
    """A snapshot's header, without loading its payload."""

    id: str
    created_at: str
    reason: str
    task_count: int
    run_count: int
    context: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RestorePreview:
    """What a restore would change — computed without changing anything."""

    snapshot_id: str
    tasks_restored: int
    tasks_overwritten: list[str] = field(default_factory=list)
    tasks_created: list[str] = field(default_factory=list)
    # Tasks that exist now but not in the snapshot. Restoring does NOT
    # delete them — see restore_snapshot's docstring for why.
    tasks_absent_from_snapshot: list[str] = field(default_factory=list)
    runs_restored: int = 0


@dataclass(frozen=True)
class RestoreResult:
    restored: bool
    snapshot_id: str
    verdict: str = "allow"
    reason: str = ""
    tasks_restored: int = 0
    runs_restored: int = 0


def _snapshot_dir() -> Path:
    directory = Path(get_settings().snapshot_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _session_factory():
    return make_session_factory(make_engine(get_settings().sqlite_path))


def _task_to_dict(task: Task) -> dict:
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
        "models_used": task.models_used,
        "files": task.files,
        "test_results": task.test_results,
        "history": task.history,
    }


def _run_to_dict(run: WorkflowRunRecord) -> dict:
    return {
        "id": run.id,
        "workflow_id": run.workflow_id,
        "project_id": run.project_id,
        "status": run.status,
        "node_results": run.node_results,
        "pending_nodes": run.pending_nodes,
        "approved_nodes": run.approved_nodes,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }


def create_snapshot(*, reason: str = "", context: dict | None = None) -> SnapshotInfo:
    """Capture the current application state.

    Non-destructive by construction: it only reads. Safe to call on a
    timer or every N steps without asking anyone.
    """
    with _session_factory()() as session:
        tasks = [_task_to_dict(t) for t in session.query(Task).all()]
        runs = [_run_to_dict(r) for r in session.query(WorkflowRunRecord).all()]

    snapshot_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    payload = {
        "version": SNAPSHOT_VERSION,
        "id": snapshot_id,
        "created_at": datetime.now(UTC).isoformat(),
        "reason": reason,
        "context": context or {},
        "tasks": tasks,
        "workflow_runs": runs,
        # Paths only — the file contents live in propose_write's backups.
        "files_touched": sorted({f for t in tasks for f in json.loads(t["files"])}),
    }

    path = _snapshot_dir() / f"{snapshot_id}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    return SnapshotInfo(
        id=snapshot_id,
        created_at=payload["created_at"],
        reason=reason,
        task_count=len(tasks),
        run_count=len(runs),
        context=payload["context"],
    )


def list_snapshots() -> list[SnapshotInfo]:
    """Newest first. Reads only each file's header fields."""
    infos: list[SnapshotInfo] = []
    for path in _snapshot_dir().glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A corrupt file must not hide the healthy ones — this list is
            # what someone reaches for when things have already gone wrong.
            continue
        if "tasks" not in payload:
            continue  # not one of ours (propose_write's .bak files live here too)
        infos.append(
            SnapshotInfo(
                id=payload.get("id", path.stem),
                created_at=payload.get("created_at", ""),
                reason=payload.get("reason", ""),
                task_count=len(payload.get("tasks", [])),
                run_count=len(payload.get("workflow_runs", [])),
                context=payload.get("context", {}),
            )
        )
    return sorted(infos, key=lambda s: s.created_at, reverse=True)


def load_snapshot(snapshot_id: str) -> dict:
    path = _snapshot_dir() / f"{snapshot_id}.json"
    if not path.exists():
        raise SnapshotError(f"No snapshot {snapshot_id!r}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SnapshotError(f"Snapshot {snapshot_id!r} is corrupt: {exc}") from exc


def preview_restore(snapshot_id: str) -> RestorePreview:
    """What restoring would change — reads only, changes nothing.

    The §14.1 contract applied to state: show the diff before asking.
    """
    payload = load_snapshot(snapshot_id)
    snapshot_tasks = {t["id"]: t for t in payload.get("tasks", [])}

    with _session_factory()() as session:
        current_ids = {t.id for t in session.query(Task).all()}

    return RestorePreview(
        snapshot_id=snapshot_id,
        tasks_restored=len(snapshot_tasks),
        tasks_overwritten=sorted(set(snapshot_tasks) & current_ids),
        tasks_created=sorted(set(snapshot_tasks) - current_ids),
        tasks_absent_from_snapshot=sorted(current_ids - set(snapshot_tasks)),
        runs_restored=len(payload.get("workflow_runs", [])),
    )


def restore_snapshot(aegis, snapshot_id: str, *, project_id: str | None = None) -> RestoreResult:
    """Write a snapshot back over the current state.

    Gated as `data_migration` — mandatory_validation at every autonomy
    level (§17.3). Returns a result object on refusal rather than raising,
    matching file_tools.propose_write and git_tools.

    **Tasks present now but absent from the snapshot are left alone.**
    Restoring is not "make the world look exactly like then": deleting
    work created after the snapshot would make recovery *lose* data,
    which is the opposite of the point. The preview reports them so the
    human knows they will survive.
    """
    payload = load_snapshot(snapshot_id)  # raises before any gate if unusable

    decision = aegis.evaluate(
        ActionRequest(
            action_type="data_migration",
            description=f"Restore application state from snapshot {snapshot_id}",
            requesting_agent="snapshot_manager",
            project_id=project_id,
        )
    )
    if decision.verdict is not Verdict.ALLOW:
        return RestoreResult(
            restored=False,
            snapshot_id=snapshot_id,
            verdict=decision.verdict.value,
            reason=decision.reason,
        )

    tasks = payload.get("tasks", [])
    runs = payload.get("workflow_runs", [])

    with _session_factory()() as session:
        for data in tasks:
            task = session.get(Task, data["id"])
            if task is None:
                task = Task(id=data["id"])
                session.add(task)
            task.project_id = data["project_id"]
            task.title = data["title"]
            task.description = data["description"]
            task.objective = data["objective"]
            task.status = data["status"]
            task.priority = data["priority"]
            task.agent = data["agent"]
            task.created_at = datetime.fromisoformat(data["created_at"])
            task.updated_at = datetime.fromisoformat(data["updated_at"])
            task.models_used = data["models_used"]
            task.files = data["files"]
            task.test_results = data["test_results"]
            task.history = data["history"]

        for data in runs:
            run = session.get(WorkflowRunRecord, data["id"])
            if run is None:
                run = WorkflowRunRecord(id=data["id"])
                session.add(run)
            run.workflow_id = data["workflow_id"]
            run.project_id = data["project_id"]
            run.status = data["status"]
            run.node_results = data["node_results"]
            run.pending_nodes = data["pending_nodes"]
            run.approved_nodes = data["approved_nodes"]
            run.created_at = datetime.fromisoformat(data["created_at"])
            run.updated_at = datetime.fromisoformat(data["updated_at"])

        session.commit()

    return RestoreResult(
        restored=True,
        snapshot_id=snapshot_id,
        tasks_restored=len(tasks),
        runs_restored=len(runs),
    )


def prune_snapshots(keep: int | None = None) -> list[str]:
    """Delete all but the `keep` most recent. Returns the ids removed.

    Bounded on purpose: a snapshot every N steps fills a disk otherwise,
    and §3.7 budgets only ~2-5 GB for logs and snapshots combined.
    """
    keep = keep if keep is not None else get_settings().snapshot_keep
    snapshots = list_snapshots()
    removed: list[str] = []
    for info in snapshots[keep:]:
        path = _snapshot_dir() / f"{info.id}.json"
        try:
            path.unlink()
            removed.append(info.id)
        except OSError:
            continue
    return removed


class StepCounter:
    """Trigger a snapshot every N steps (§19.3).

    Kept as an explicit object a caller ticks, rather than a hidden hook:
    the project's rule throughout is that cross-cutting effects happen on
    an explicit call, never grafted invisibly onto an existing contract
    (see self_evolution/pipeline.py's docstring for the same reasoning).
    """

    def __init__(self, every: int | None = None) -> None:
        self._every = every if every is not None else get_settings().snapshot_every_steps
        self._steps = 0

    def step(self, *, reason: str = "", context: dict | None = None) -> SnapshotInfo | None:
        """Count one step; snapshot when the interval is reached.

        `every <= 0` disables automatic snapshots entirely — the escape
        hatch for anyone who wants only manual ones.
        """
        if self._every <= 0:
            return None
        self._steps += 1
        if self._steps % self._every:
            return None
        return create_snapshot(reason=reason or f"auto: {self._steps} steps", context=context)
