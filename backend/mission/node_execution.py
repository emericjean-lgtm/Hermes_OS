"""Adapter binding one mission DAG node to the shared execution engine.

``GraphExecutor`` has always taken an ``execute_node`` callable and nothing ever
supplied one, so it fell back to ``lambda n: True``: every node of every mission
created through ``/api/v1/missions`` was declared successful without any work
being done, while ``/api/v1/autonomous`` reached the real engine. This module is
the missing plug — not a second engine.

It performs no execution of its own. It translates a :class:`MissionNode` into
the :class:`TaskExecution` the engine already consumes, drives the exact
``prepare()`` → ``execute_task()`` sequence :class:`AutonomousOrchestrator` uses,
and reports the real outcome back to the DAG. Both surfaces therefore run the
same scheduler, coordinator, validation engine and task executor (R-002 P1).
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from backend.mission.mission_models import MissionNode

logger = logging.getLogger("hermes_os.mission.node_execution")


def make_node_executor(engine: Any) -> Callable[[MissionNode], bool]:
    """Return an ``execute_node`` hook that runs a node on ``engine``.

    Args:
        engine: the shared ``MissionExecutor``. If ``None`` the hook reports
            failure rather than success — a node whose engine is missing has not
            been executed, and saying otherwise is the defect this replaces.
    """

    def execute_node(node: MissionNode) -> bool:
        if engine is None:
            logger.error(
                "node %s cannot run: no execution engine is wired", node.node_id)
            return False

        from backend.execution.execution_models import (
            ExecutionMeta,
            ExecutionPriority,
            TaskExecution,
            TaskExecutionStatus,
        )

        task = TaskExecution(
            task_id=f"{node.node_id}-task",
            node_id=node.node_id,
            title=node.title or node.description or node.node_id,
            status=TaskExecutionStatus.PENDING,
            assigned_runtime=getattr(node, "preferred_runtime", "") or "",
            assigned_skills=list(getattr(node, "required_skills", []) or []),
        )
        meta = ExecutionMeta(
            mission_id=getattr(node, "mission_id", "") or node.node_id,
            user_goal=task.title,
            priority=ExecutionPriority.NORMAL,
        )

        try:
            state_machine = engine.prepare(meta, [task])
            outcome = engine.execute_task(state_machine, task.task_id)
        except Exception:
            # A node that raised has not succeeded. Report it and let the DAG
            # mark it failed; never swallow this into a success.
            logger.warning("node %s raised during execution",
                           node.node_id, exc_info=True)
            return False

        # Write the measured outcome back onto the node's own fields, so the DAG
        # and /missions/{id}/graph report what actually happened.
        node.actual_duration_ms = task.duration_ms
        node.completed_at = task.completed_at
        if task.assigned_runtime:
            node.preferred_runtime = task.assigned_runtime

        if outcome.get("runtime_available") is False:
            reason = outcome.get("error", "runtime unavailable")
            node.result_summary = f"not executed: {reason}"
            logger.warning("node %s could not run: %s", node.node_id, reason)
            return False

        if task.errors:
            node.result_summary = f"failed: {task.errors[-1]}"
        elif task.result is not None:
            summary = str(task.result)
            node.result_summary = summary[:500]

        return task.status == TaskExecutionStatus.COMPLETED

    return execute_node
