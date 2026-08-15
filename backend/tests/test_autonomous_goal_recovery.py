"""A running goal must be findable without its id (HOS-102).

The Autonomous Center held the id of the goal it had just launched in
component-local React state (``useState``) and read the goal itself off a
mutation's ``data``. Switching tabs unmounts that component — the Cockpit
shell keys its ``AnimatePresence`` on the active view — so both died while
the goal kept running on the server. The task had not stopped; the UI had
simply forgotten which one it was watching, and nothing could enumerate
goals to find it again.

These tests pin the server side of the remedy: goals are listable, newest
first, and a goal that is still running appears in that list.
"""
from __future__ import annotations

import time

import pytest

from backend.autonomous.autonomous_engine import AutonomousEngine
from backend.execution.execution_models import TaskExecutionStatus


class _InstantExecutor:
    """Stands in for MissionExecutor so these tests never call a model.

    Written after the first version of this file took 278 s for seven
    tests: ``AutonomousEngine()`` with no arguments builds a real
    MissionExecutor, so every ``start_goal`` ran real local inference. The
    goal listing being tested here is a read path over ``_goals`` — it has
    no opinion about what the tasks did.

    Only ``prepare`` and ``execute_task`` are reached from the autonomous
    execution path (see ``_execute_plan`` in autonomous_orchestrator.py);
    implementing more would be inventing an interface the code never calls.
    """

    def prepare(self, meta, tasks):
        # Marked here rather than in execute_task because that method
        # receives a task_id, not the task — and a goal whose tasks never
        # complete would be reported as failed, which is a different
        # scenario from the one under test.
        for task in tasks:
            task.status = TaskExecutionStatus.COMPLETED
        return object()

    def execute_task(self, state_machine, task_id):
        return {"success": True, "runtime_available": True, "runtime": "stub"}


@pytest.fixture
def engine():
    return AutonomousEngine(mission_executor=_InstantExecutor())


def test_a_started_goal_can_be_found_without_holding_its_id(engine):
    """The whole point: the id the UI lost is recoverable from the server."""
    started = engine.start_goal("Analyser le module d'authentification")

    listed = engine.list_goals()

    assert [g["goal_id"] for g in listed] == [started["goal_id"]]
    assert listed[0]["user_request"] == "Analyser le module d'authentification"


def test_goals_are_listed_newest_first(engine):
    """A user coming back to the tab is looking for what they just launched,
    not for what they ran an hour ago."""
    # La pause sépare les deux horodatages : l'horloge Windows avance par
    # pas de ~15,6 ms, et deux lancements consécutifs seraient ex aequo, ce
    # qui ferait tirer ce verdict au sort (HOS-112).
    first = engine.start_goal("premier objectif")
    time.sleep(0.02)
    second = engine.start_goal("deuxième objectif")

    listed = engine.list_goals()

    assert [g["goal_id"] for g in listed] == [second["goal_id"], first["goal_id"]]


def test_the_listing_is_bounded(engine):
    for index in range(7):
        engine.start_goal(f"objectif {index}")

    assert len(engine.list_goals(limit=3)) == 3


def test_an_empty_engine_lists_nothing_rather_than_failing(engine):
    assert engine.list_goals() == []


def test_the_status_counters_and_the_listing_agree(engine):
    """get_status has always counted goals it could not name. If these two
    ever disagree, one of them is reading a different collection."""
    engine.start_goal("a")
    engine.start_goal("b")

    assert engine.get_status()["total_goals"] == len(engine.list_goals())


def test_the_route_handler_returns_what_the_cockpit_expects(engine):
    from backend.autonomous import routes

    routes.create_autonomous_routes(engine)
    engine.start_goal("objectif via la route")

    payload = routes.handle_list_goals()

    assert payload["success"] is True
    assert payload["total"] == 1
    assert payload["goals"][0]["user_request"] == "objectif via la route"


def test_a_running_goal_does_not_block_the_engine():
    """Listing, status and cancel must answer *while* a goal runs.

    ``start_goal`` used to hold ``self._lock`` across planning and real
    local inference, and every other lock-taking method waited behind it.
    Measured against the live backend before the fix: a
    ``GET /autonomous/goals`` issued during a running goal timed out after
    25 s. Cancelling a goal that was going wrong was therefore impossible —
    the same defect HOS-069 removed from MissionExecutor.

    The slow phase is simulated by an executor that blocks until this test
    releases it, so the test costs no inference and still exercises the
    real lock discipline.
    """
    import threading

    release = threading.Event()
    entered = threading.Event()

    class _BlockingExecutor(_InstantExecutor):
        def execute_task(self, state_machine, task_id):
            entered.set()
            release.wait(timeout=10)
            return super().execute_task(state_machine, task_id)

    engine = AutonomousEngine(mission_executor=_BlockingExecutor())
    runner = threading.Thread(
        target=lambda: engine.start_goal("objectif long"), daemon=True)
    runner.start()

    assert entered.wait(timeout=10), "the goal never reached execution"
    try:
        # Timed, not merely attempted. Under the old lock these calls still
        # returned — after waiting out the whole slow phase — so a test that
        # only asserted their results would have passed against the very bug
        # it exists to catch. What is wrong is the *waiting*.
        started = time.perf_counter()
        listed = engine.list_goals()
        total = engine.get_status()["total_goals"]
        engine.cancel_goal(listed[0]["goal_id"] if listed else "none")
        elapsed = time.perf_counter() - started

        assert len(listed) == 1, "a running goal is not listed"
        assert total == 1
        assert elapsed < 2.0, (
            f"reads waited {elapsed:.1f}s on the running goal's lock — "
            "start_goal is holding it across execution again"
        )
    finally:
        release.set()
        runner.join(timeout=15)

    assert not runner.is_alive(), "the goal thread never finished"


def test_starting_a_goal_does_not_run_on_the_event_loop():
    """POST /autonomous/start must not be an ``async def``.

    Narrowing the orchestrator's lock (above) was necessary and not
    sufficient. ``start_goal`` runs planning and real local inference
    synchronously — minutes — and an async path operation executes that on
    uvicorn's event loop thread, so the server answers *nothing* else in
    the meantime. Measured against the live backend with the lock already
    narrow: ``GET /autonomous/status`` still timed out at 25 s, and so did
    ``/missions`` and ``/health``. After declaring this handler ``def`` —
    FastAPI then runs it in its threadpool — the same four calls answered
    in 0.12 s, 0.00 s, 0.00 s and 0.00 s while a goal was running.

    Asserted structurally rather than by racing a real request: the defect
    is entirely determined by the handler's declaration, and a timing test
    over a threadpool would be flaky for no extra information.
    """
    import inspect

    from backend.autonomous.routes import router

    start = next(r for r in router.routes
                 if getattr(r, "path", "") == "/autonomous/start")

    assert not inspect.iscoroutinefunction(start.endpoint), (
        "POST /autonomous/start is async again — a running goal will freeze "
        "the whole API, not just the Autonomous Center"
    )


def test_goals_is_not_matched_as_a_goal_id():
    """"/goals" is declared before "/{goal_id}"; registered the other way
    round FastAPI resolves it as a goal named "goals" and returns 404."""
    from backend.autonomous.routes import router

    paths = [r.path for r in router.routes]

    assert paths.index("/autonomous/goals") < paths.index("/autonomous/{goal_id}")
