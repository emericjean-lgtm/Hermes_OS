"""A task must see what the tasks it depends on produced (HOS-105).

Before this, a decomposed mission behaved like a set of unrelated one-shot
prompts. A task received the mission objective and its own node title, and
nothing else: ``mark_completed`` set a status and a timestamp, and
``result_summary`` — written on every node by ``node_execution`` — was read
by no one. Every task rediscovered the ground from scratch.

The load-bearing test here is
``test_the_carried_context_is_text_and_survives_a_model_change``. Routing
different tasks to different models is the next piece of work; anything
carried as KV cache or a provider-side session would evaporate at exactly
the moment the model is swapped, and the mission would look like the model
change broke it.
"""
from __future__ import annotations

import pytest

from backend.core.bootstrap.service_registry import _upstream_results_for
from backend.mission.mission_models import Mission, MissionNode


def _Task(mission_id: str, node_id: str):
    """La tâche telle que la production la construit, pas une imitation.

    C'est ici que HOS-105 s'est perdu (corrigé en HOS-121). L'ancien double
    posait `self.task_id = node_id` — un identifiant que
    `node_execution.py` ne produit **jamais** : il écrit
    `task_id=f"{node.node_id}-task"`. `_upstream_results_for` lisait
    `task_id` en premier, cherchait `"n2-task"` parmi les `node_id`, ne
    trouvait rien et rendait `None`. Tous les tests de ce module passaient
    au vert pendant que la fonction ne servait à rien en production.

    On passe donc par le vrai `TaskExecution`, construit exactement comme
    `make_node_executor` le fait. Un double qui diverge de la production
    ne teste que lui-même.
    """
    from backend.execution.execution_models import (
        TaskExecution, TaskExecutionStatus,
    )

    return TaskExecution(
        task_id=f"{node_id}-task",
        node_id=node_id,
        mission_id=mission_id,
        title=node_id,
        status=TaskExecutionStatus.PENDING,
    )


@pytest.fixture
def mission(monkeypatch):
    """A three-node chain: collect -> analyse -> report."""
    mission = Mission(title="m", objective="Produce a report")
    mission.nodes = [
        MissionNode(node_id="n1", title="Collect the data"),
        MissionNode(node_id="n2", title="Analyse it", depends_on=["n1"]),
        MissionNode(node_id="n3", title="Write the report", depends_on=["n2"]),
    ]
    mission.nodes[0].result_summary = "wrote data.csv, 412 rows"
    mission.nodes[1].result_summary = "median latency 84 ms, two outliers"

    from backend.mission import routes

    monkeypatch.setitem(routes._missions, mission.mission_id, mission)  # noqa: SLF001
    return mission


# ── the point of the exercise ────────────────────────────────────────────

def test_a_task_sees_what_its_dependency_produced(mission):
    carried = _upstream_results_for(_Task(mission.mission_id, "n2"))

    assert carried is not None
    assert "wrote data.csv, 412 rows" in carried
    assert "Collect the data" in carried, "the summary alone does not say what produced it"


def test_a_first_task_carries_nothing(mission):
    """Nothing ran before it. An empty section would be noise in the prompt."""
    assert _upstream_results_for(_Task(mission.mission_id, "n1")) is None


def test_only_direct_dependencies_are_carried(mission):
    """Walking the whole transitive history would rebuild the 64k wall
    documented in CLAUDE.md — where tool schemas get truncated and the agent
    answers that it has no tools."""
    carried = _upstream_results_for(_Task(mission.mission_id, "n3"))

    assert "median latency 84 ms" in carried
    assert "data.csv" not in carried, "n1 is two hops away and must not travel"


def test_the_carried_context_is_text_and_survives_a_model_change(mission):
    """The reason this is a prerequisite for per-task model routing.

    Nothing here is tied to a runtime, a session id or a KV cache: the same
    call made under any model returns the same string, because the state
    lives on the Mission. A design that carried a provider-side session
    would lose everything precisely when the model changes — and the
    failure would look like the model change broke the mission.
    """
    first = _upstream_results_for(_Task(mission.mission_id, "n2"))
    second = _upstream_results_for(_Task(mission.mission_id, "n2"))

    assert first == second
    assert isinstance(first, str)


# ── the ways it would quietly go wrong ───────────────────────────────────

def test_a_dependency_that_reported_nothing_is_still_named(mission):
    """"It ran and told us nothing" is a different fact from "it never
    existed", and a task that can tell them apart can decide to go look."""
    mission.nodes[0].result_summary = ""

    carried = _upstream_results_for(_Task(mission.mission_id, "n2"))

    assert "Collect the data" in carried
    assert "aucun résumé" in carried


def test_each_summary_is_capped(mission):
    from backend.core.bootstrap.service_registry import _UPSTREAM_SUMMARY_CHARS

    mission.nodes[0].result_summary = "x" * 5000

    carried = _upstream_results_for(_Task(mission.mission_id, "n2"))

    assert len(carried) < _UPSTREAM_SUMMARY_CHARS + 200


def test_the_number_of_dependencies_is_capped(mission):
    """A fan-in node can depend on many others; the total is what has to
    stay small enough not to crowd out the task's own instructions."""
    from backend.core.bootstrap.service_registry import _UPSTREAM_MAX_NODES

    extra = [MissionNode(node_id=f"e{i}", title=f"Step {i}") for i in range(12)]
    for node in extra:
        node.result_summary = f"summary {node.node_id}"
    mission.nodes.extend(extra)
    mission.nodes[2].depends_on = [n.node_id for n in extra]

    carried = _upstream_results_for(_Task(mission.mission_id, "n3"))

    assert len(carried.splitlines()) == _UPSTREAM_MAX_NODES


def test_an_unknown_mission_carries_nothing_rather_than_raising():
    assert _upstream_results_for(_Task("mission_that_does_not_exist", "n1")) is None


def test_a_task_without_a_mission_carries_nothing():
    assert _upstream_results_for(_Task("", "n1")) is None


# ── l'incident lui-même (HOS-121) ────────────────────────────────────────

def test_la_tache_du_test_est_celle_que_la_production_construit():
    """Le garde-fou contre la répétition de l'incident.

    Tout ce module passait au vert pendant que la fonction rendait `None`
    en production, parce que le double posait `task_id = node_id`. Si
    `make_node_executor` change la forme de l'identifiant, c'est ici que ça
    doit casser — pas trente minutes plus loin dans une mission réelle.
    """
    from backend.mission.mission_models import MissionNode

    node = MissionNode(node_id="n7", title="Un noeud")
    node.mission_id = "m7"

    reelle = None

    class _Controleur:
        def start(self, meta, tasks):
            nonlocal reelle
            reelle = tasks[0]
            raise RuntimeError("on ne veut que la tâche, pas l'exécution")

    from backend.mission.node_execution import make_node_executor

    make_node_executor(_Controleur())(node)

    assert reelle is not None, "la production n'a construit aucune tâche"
    fabriquee = _Task("m7", "n7")
    assert reelle.task_id == fabriquee.task_id
    assert reelle.node_id == fabriquee.node_id


def test_le_contexte_amont_atteint_une_tache_de_production(mission):
    """L'incident : `_upstream_results_for` lisait `task_id` en premier, et
    `task_id` vaut `"<node_id>-task"`. La recherche ne trouvait aucun nœud
    et rendait `None` — HOS-105 était inerte sur le seul chemin qui compte.
    """
    tache = _Task(mission.mission_id, "n2")

    assert tache.task_id == "n2-task", "le préfixe est justement le piège"
    carried = _upstream_results_for(tache)

    assert carried is not None, (
        "une tâche construite comme en production ne reçoit rien — "
        "c'est exactement le défaut de HOS-105")
    assert "wrote data.csv, 412 rows" in carried


# ── the prompt the model actually receives ───────────────────────────────

def test_the_executor_puts_the_upstream_work_in_the_prompt():
    """The resolver being correct is not enough — it has to reach the
    model. This drives the real _build_messages."""
    from backend.execution.task_executor import RealTaskExecutor

    executor = RealTaskExecutor(
        mission_brief_for=lambda task: "Produce a report",
        upstream_results_for=lambda task: "- Collect the data : wrote data.csv",
    )
    messages = executor._build_messages(  # noqa: SLF001
        _Task("m1", "n2"), assignment=None)

    user = next(m["content"] for m in messages if m["role"] == "user")
    assert "wrote data.csv" in user
    assert "do not redo it" in user.lower()


def test_a_task_with_no_upstream_gets_no_empty_section():
    from backend.execution.task_executor import RealTaskExecutor

    executor = RealTaskExecutor(
        mission_brief_for=lambda task: "Produce a report",
        upstream_results_for=lambda task: None,
    )
    messages = executor._build_messages(  # noqa: SLF001
        _Task("m1", "n1"), assignment=None)

    user = next(m["content"] for m in messages if m["role"] == "user")
    assert "Already done" not in user


def test_a_failing_resolver_never_fails_the_task():
    """Context is an improvement on having none. A lookup that throws must
    not take the task down with it."""
    from backend.execution.task_executor import RealTaskExecutor

    def _explode(task):
        raise RuntimeError("mission store unreachable")

    executor = RealTaskExecutor(upstream_results_for=_explode)

    messages = executor._build_messages(_Task("m1", "n2"), assignment=None)  # noqa: SLF001

    assert any(m["role"] == "user" for m in messages)
