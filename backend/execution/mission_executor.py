"""Mission Executor — the central execution engine (HOS-050).

Orchestrates the complete pipeline:
    User Goal → Planner → Graph → Scheduler → Agents → Skills → Runtime → Tools → Validation → Memory
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict, deque
from datetime import datetime, timezone
from typing import Any

from .execution_models import (
    ExecutionMeta,
    ExecutionReport,
    ExecutionState,
    TaskExecution,
    TaskExecutionStatus,
    ValidationOutcome,
)
from .execution_state import ExecutionStateMachine
from .task_scheduler import TaskScheduler
from .agent_coordinator import AgentCoordinator
from .validation_engine import ValidationEngine
from .feedback_loop import FeedbackLoop
from .optimization_engine import OptimizationEngine
from .task_executor import RuntimeUnavailableError

# --------------------------------------------------------------------
"""Le déroulé d'une exécution de mission, tel qu'il est annoncé.

    Les neuf étaient publiés et jetés par la liste blanche : le
    Cockpit ne voyait donc jamais une mission démarrer (HOS-181)."""
EXECUTION_EVENTS: dict[str, str] = {
    "planning": "execution.planning",
    "started": "execution.started",
    "task_started": "execution.task_started",
    "task_completed": "execution.task_completed",
    "waiting_approval": "execution.waiting_approval",
    "retry": "execution.retry",
    "optimized": "execution.optimized",
    "completed": "execution.completed",
    "failed": "execution.failed",
    # HOS-247 : le budget de la mission a ete atteint et la tache suivante
    # n'a pas ete engagee. Distinct de `failed` : rien n'a echoue.
    "budget_depasse": "execution.budget_depasse",
}

logger = logging.getLogger("hermes_os.execution.mission")


def _decision_en_json(meta: dict, modele: str, runtime_servi: str) -> str:
    """La décision de routage, réduite à ce qu'on saura relire (HOS-242).

    Quatre faits, et l'écart entre eux : ce que le routeur a demandé, ce
    que l'exécuteur a réellement appelé, ce qui a servi les poids, et le
    modèle. Sans cela, « pourquoi cette mission a-t-elle tourné en local
    alors que le cloud était demandé ? » n'a de réponse que dans un
    journal qui a déjà défilé.

    Les valeurs absentes restent absentes : une clé manquante se lit
    « on ne sait pas », une valeur inventée se lit comme un fait.
    """
    import json

    demande = str(meta.get("runtime_demande_par_le_routeur") or "")
    servi = str(runtime_servi or "")
    fait = {
        "runtime_demande": demande,
        "runtime_servi": servi,
        "modele": str(modele or ""),
        "fournisseur": str(meta.get("fournisseur") or ""),
    }
    # Le repli n'est nommé que lorsqu'il est **constaté** : un routeur qui
    # n'a rien demandé n'a pas été défait.
    if demande and servi and demande != servi:
        fait["repli"] = f"{demande} indisponible, servi par {servi}"
    fait = {c: v for c, v in fait.items() if v}
    return json.dumps(fait, ensure_ascii=False, sort_keys=True) if fait else ""


def _unique(values: Any) -> list[str]:
    """Non-empty values, de-duplicated, in first-seen order."""
    seen: dict[str, None] = {}
    for value in values:
        if value:
            seen.setdefault(str(value), None)
    return list(seen)


class MissionExecutor:
    """Central execution engine that orchestrates a full mission from user goal to completion.

    Pipeline:
        1. Planning — transforms user goal into tasks (via Mission Planner integration)
        2. Scheduling — determines execution order with parallelization
        3. Assignment — assigns agents, skills, runtimes, tools
        4. Execution — runs tasks with validation after each
        5. Feedback — analyzes outcomes and feeds into Memory/Intelligence
        6. Optimization — identifies improvements for future missions
    """

    #: Diagnostic event tail kept in memory. See ``_events``.
    MAX_RETAINED_EVENTS = 2000

    def __init__(self, task_executor: Any = None, on_event: Any = None,
                 agent_registry: Any = None, capability_matcher: Any = None,
                 trust_engine: Any = None, registre: Any = None) -> None:
        """
        Args:
            task_executor: performs the actual work for one task. Injected so the
                engine keeps orchestrating and something else executes — the
                separation the simulated step used to blur. Defaults to
                :class:`~backend.execution.task_executor.RealTaskExecutor`.
            on_event: the shared event dispatcher.
            agent_registry: the real ``backend.agents.agent_registry.AgentRegistry``
                (HOS-070) — the one ``GET /api/v1/agents`` and the Cockpit's
                Agent Center actually read from. None (the default) disables
                the sync entirely: every agent then keeps showing its
                initial "READY, 0 tasks" state forever, which was the
                previous behaviour for every real mission ever run — nothing
                ever updated this registry outside of agent create/stop.
            capability_matcher: the real ``CapabilityMatcher`` (HOS-070) —
                passed straight through to the internal ``AgentCoordinator``.
                None (the default) keeps the coordinator's own simpler
                keyword-based selection, matching prior behaviour.
            trust_engine: the real ``backend.security.agent_trust_engine.
                AgentTrustEngine`` (HOS-070) — fed a real outcome per task so
                an agent's trust score means something. Deliberately *not*
                the full ``SecurityEngine.check_access()`` gate: that engine
                has no default permissions/policies configured anywhere
                (confirmed — ``PermissionManager.check_permission()`` and
                ``evaluate_policies()`` both default-deny with nothing
                granted), so wiring it into mandatory dispatch today would
                silently block every real mission. Building the missing
                policy-configuration layer (the SecurityEngine equivalent of
                Aegis's config/security.yaml) is a separate, materially
                larger initiative than this pass — see the HOS-070 CHANGELOG
                entry.
        """
        self._lock = threading.RLock()
        self._scheduler = TaskScheduler()
        self._coordinator = AgentCoordinator(capability_matcher=capability_matcher)
        self._validator = ValidationEngine()
        self._feedback = FeedbackLoop()
        self._optimizer = OptimizationEngine()
        self._agent_registry = agent_registry
        self._trust_engine = trust_engine
        # Ring buffer: this is a diagnostic tail for get_events(), not an
        # archive. Unbounded, it grew 5 entries per mission forever — 4000
        # dicts after 800 missions, the single largest allocation site in a
        # load run (RC3 P5). Durable history belongs to SystemEventBus.
        self._events: deque[dict[str, Any]] = deque(maxlen=self.MAX_RETAINED_EVENTS)
        # execution_id -> its own task ids. Bounded like everything else here:
        # the scheduler retains a fixed window, so this must not outgrow it.
        self._execution_tasks: OrderedDict[str, list[str]] = OrderedDict()
        self._on_event = on_event

        if task_executor is None:
            from .task_executor import RealTaskExecutor

            task_executor = RealTaskExecutor(on_event=on_event)
        self._task_executor = task_executor

        # HOS-221. Sans lui, ce module reste ce qu'il était la nuit du
        # 29 au 30 août : un rapport en mémoire, un `deque(maxlen=2000)`
        # explicitement décrit plus haut comme « a diagnostic tail, not
        # an archive », et rien de durable pour répondre à « pourquoi la
        # première tentative a échoué ». Défaillant par conception :
        # une trace qui casse la mission qu'elle décrit ne vaut rien.
        self._registre = registre
        if self._registre is None:
            try:
                from backend.runs.registre import Registre

                self._registre = Registre()
            except Exception:  # pragma: no cover - base indisponible
                logger.warning("registre des runs indisponible", exc_info=True)
        #: execution_id -> identifiant du run. Borné comme le reste ici.
        self._runs: OrderedDict[str, str] = OrderedDict()

    # ── Agent registry sync (HOS-070) ──────────────────────────

    def _sync_agent_started(self, agent_name: str, mission_id: str, task_id: str) -> None:
        """Reflect a real task assignment in the Cockpit's agent registry.

        Best-effort — telemetry must never fail the task it describes.
        Idempotent to call again on a retry re-entry (still the same
        agent, still busy). Simplification, documented rather than hidden:
        a single status field, last-write-wins — if the same named agent
        is genuinely dispatched to two tasks concurrently (nothing hard-
        prevents that today; AgentCoordinator only *penalizes* a loaded
        agent in scoring, it does not exclude it), the second BUSY/READY
        transition wins. Good enough for a Cockpit display, not a
        scheduling invariant.
        """
        if self._agent_registry is None or not agent_name:
            return
        try:
            from backend.agents.agent_models import AgentStatus

            agent = self._agent_registry.find_by_name(agent_name)
            if agent is None:
                return
            agent.current_task_id = task_id
            agent.current_mission_id = mission_id
            self._agent_registry.update_status(agent.agent_id, AgentStatus.BUSY)
        except Exception:
            logger.debug("agent registry sync (start) failed for %s",
                         agent_name, exc_info=True)

    def _sync_agent_released(self, agent_name: str, duration_ms: float,
                             status: TaskExecutionStatus) -> None:
        """Counterpart to ``_sync_agent_started`` — called once per attempt,
        alongside every existing ``self._coordinator.release_agent()`` call.

        Only a terminal outcome (COMPLETED/FAILED) counts toward the
        agent's real success rate — a PENDING retry re-enters
        ``execute_task()`` immediately (see node_execution.py's loop) and
        is not a distinct, countable attempt from the Cockpit's point of
        view; the agent stays marked BUSY throughout. NEEDS_REVIEW
        (WAITING_APPROVAL) frees the agent without counting a win or a
        loss — a human decides next, not a metric.
        """
        if not agent_name:
            return
        is_terminal = status in (TaskExecutionStatus.COMPLETED, TaskExecutionStatus.FAILED)
        success = status == TaskExecutionStatus.COMPLETED

        # HOS-070: AgentTrustEngine.record_result() existed and was never
        # called by anything — every agent's trust score stayed at its
        # default (a brand-new AgentTrustScore) no matter how many real
        # tasks it completed or failed. Independent of agent_registry
        # below — either integration works whether or not the other is
        # wired.
        if is_terminal and self._trust_engine is not None:
            try:
                self._trust_engine.record_result(agent_name, success)
            except Exception:
                logger.debug("trust engine sync failed for %s", agent_name, exc_info=True)

        if self._agent_registry is None:
            return
        try:
            from backend.agents.agent_models import AgentStatus

            agent = self._agent_registry.find_by_name(agent_name)
            if agent is None:
                return
            if is_terminal:
                self._agent_registry.update_metrics(agent.agent_id, duration_ms, success)
            if status != TaskExecutionStatus.PENDING:
                agent.current_task_id = ""
                agent.current_mission_id = ""
                self._agent_registry.update_status(agent.agent_id, AgentStatus.READY)
        except Exception:
            logger.debug("agent registry sync (release) failed for %s",
                         agent_name, exc_info=True)

    # ── Public API ──

    def prepare(self, meta: ExecutionMeta, tasks: list[TaskExecution],
                dependencies: dict[str, list[str]] | None = None,
                contrat: Any = None) -> ExecutionStateMachine:
        """Prepare execution: register tasks with dependencies, build schedule plan.

        ``contrat`` (HOS-229) : ce qui doit être vrai à la fin. Rangé dans
        le registre des runs, d'où le relais le relit pour le mettre dans
        le prompt.

        HOS-221 avait créé `Contrat` **et** la colonne qui l'accueille, et
        vérifié depuis : rien n'y écrivait, rien ne l'y relisait. Le
        modèle chargé de satisfaire des critères ne les voyait donc pas.

        `None` reste le défaut, et c'est honnête : **rien ne dérive
        aujourd'hui un contrat d'un objectif en prose.** Le faire demande
        la boucle du jalon suivant. Le chemin existe et attend son
        appelant plutôt que d'inventer des critères que personne n'a
        écrits.
        """
        with self._lock:
            sm = ExecutionStateMachine(meta)
            sm.transition(ExecutionState.PLANNING, "Preparing execution")

            # Remember which tasks belong to *this* execution. The scheduler is
            # shared by every mission in the process, so finalize() cannot tell
            # them apart from the registry alone and would report one mission's
            # figures over every task ever registered (R-002 P5).
            self._execution_tasks[meta.execution_id] = [t.task_id for t in tasks]
            while len(self._execution_tasks) > self._scheduler.MAX_RETAINED_TASKS:
                self._execution_tasks.popitem(last=False)

            for task in tasks:
                deps = (dependencies or {}).get(task.task_id, [])
                self._scheduler.register_task(task, deps)

            self._ouvrir_le_run(meta, tasks, contrat)

            self._publish("execution.started", {"execution_id": meta.execution_id})
            self._publish("execution.planning", {"execution_id": meta.execution_id})

            sm.transition(ExecutionState.READY, "Tasks registered and scheduled")
            return sm

    def _maybe_finalize_state(self, sm: ExecutionStateMachine) -> None:
        """Transition ``sm`` to its terminal state once every task under
        this execution is itself terminal (HOS-069).

        Scoped per-execution via ``TaskScheduler.all_done()`` — see its
        docstring for why the previous whole-scheduler ``is_all_done()``
        check was wrong once more than one execution shares the scheduler
        (real since HOS-068's concurrent GraphExecutor dispatch). Reports
        FAILED, not COMPLETED, when any of this execution's own tasks
        failed — the previous unconditional "all done -> COMPLETED" made a
        failed execution report itself as completed to every caller of
        ``ExecutionController.get()``/``list_executions()``. Call sites
        must already hold ``self._lock``.
        """
        if sm.is_terminal():
            return
        own_task_ids = self._execution_tasks.get(sm._meta.execution_id, [])
        if not self._scheduler.all_done(own_task_ids):
            return
        own_tasks = [self._scheduler.get_task(tid) for tid in own_task_ids]
        any_failed = any(
            t is not None and t.status == TaskExecutionStatus.FAILED for t in own_tasks
        )
        if any_failed:
            sm.transition(ExecutionState.FAILED, "One or more tasks failed")
            self._publish("execution.failed", {"execution_id": sm._meta.execution_id})
        else:
            sm.transition(ExecutionState.COMPLETED, "All tasks completed")
            self._publish("execution.completed", {"execution_id": sm._meta.execution_id})

    def execute_task(self, sm: ExecutionStateMachine, task_id: str) -> dict[str, Any]:
        """Execute a single task through the full pipeline.

        Locking is deliberately narrow (HOS-068): only the scheduler/
        coordinator/state-machine bookkeeping — genuinely shared mutable
        state — is held under ``self._lock``. The actual inference call
        (``self._task_executor.execute``, which can run for tens of
        seconds — see HOS-065C's real benchmark data) runs *outside* it.
        Before this, the whole method was one ``with self._lock:`` block,
        which meant calling this concurrently from multiple tasks (as
        GraphExecutor now does for independent DAG nodes) would have just
        serialized every task onto one lock, one at a time — real threads,
        fake parallelism. ``task``/``assignment`` are safe to mutate lock-
        free here: each is retrieved once per call and never touched by a
        concurrent call for a *different* task_id.
        """
        with self._lock:
            # The scheduler already keys tasks by id. This used to copy the whole
            # registry and linear-scan it, making each execution O(tasks-ever-
            # registered) and the engine as a whole O(n²): throughput fell from
            # 1012 to 454 missions/s across a 1000-mission run (RC3 P5).
            task = self._scheduler.get_task(task_id)

            if task is None:
                return {"task_id": task_id, "status": "not_found"}

            # HOS-247 : le budget de la mission, vérifié **avant**
            # d'engager cette tâche et jamais pendant. Une tâche déjà
            # lancée va au bout de son propre plafond (900 s pour l'agent,
            # 1 200 s pour le nœud) : ce budget décide de ce qu'on
            # engage, pas de ce qu'on interrompt. C'est ce qui le
            # distingue d'un timeout, et ce qui fait qu'il ne tue rien.
            #
            # Ici plutôt qu'ailleurs parce que les deux chemins — le
            # marcheur de graphe autonome et l'appel direct — convergent
            # sur cette méthode. Un second compteur ailleurs dériverait
            # du premier.
            if sm.budget_depasse():
                return self._refuser_pour_budget(sm, task, task_id)

            sm.transition(ExecutionState.RUNNING, f"Executing task {task_id}")
            self._publish("execution.task_started", {"task_id": task_id})

            # HOS-069: a fresh attempt starts with a clean error list. Before
            # this, a retry's errors accumulated on top of the previous
            # attempt's — so a task that failed once (e.g. a transient
            # RuntimeUnavailableError, now retried — see below) and then
            # genuinely succeeded on retry was still judged RETRY/FAIL by
            # ValidationEngine, which reads task.errors: the earlier
            # attempt's now-irrelevant error was still sitting there. Only
            # this attempt's own outcome should decide this attempt's
            # validation.
            task.errors = []

            # 1. Coordinate: select agent, skills, runtime, tools
            assignment = self._coordinator.assign(task)
            task.assigned_agent = assignment.agent_id
            task.assigned_runtime = assignment.runtime_id
            task.assigned_skills = assignment.skill_ids
            task.assigned_tools = assignment.tool_ids
            task.status = TaskExecutionStatus.RUNNING
            task.started_at = datetime.now(timezone.utc)
            self._sync_agent_started(task.assigned_agent, sm._meta.mission_id, task_id)

        # 2. Execute for real, lock-free — this is the "calls the agent via
        #    runtime" that the previous comment promised and never did. A
        #    task that cannot run now fails; it does not report an invented
        #    result.
        try:
            outcome = self._task_executor.execute(task, assignment)
        except RuntimeUnavailableError as exc:
            with self._lock:
                task.errors.append(str(exc))
                task.completed_at = datetime.now(timezone.utc)
                task.duration_ms = (
                    (task.completed_at - task.started_at).total_seconds() * 1000.0
                    if task.started_at else 0.0
                )
                # HOS-069: this used to fail the task outright on the very
                # first runtime problem — an Ollama timeout, a VRAM
                # admission denial, a connection error — with zero retry
                # attempts at all, unlike the validation-outcome RETRY path
                # below. A transient failure (the model finishes loading, a
                # concurrent task frees VRAM, a network blip passes) got no
                # second chance. Same bounded ceiling, same PENDING re-entry
                # node_execution.py's retry loop already drives; the next
                # attempt also gets a real alternative model — see
                # RealTaskExecutor._resolve_model()'s retry branch.
                # HOS-225 : la reprise consulte la cause au lieu de
                # reprendre à l'identique. Trois cas changent réellement :
                # un refus de politique ou de sécurité ne se reprend
                # **pas** (la reprise viendra de l'accord humain, pas de
                # la boucle) ; un manque de VRAM demande un modèle plus
                # petit et non un autre de même taille ; une fenêtre de
                # contexte fermée ne se répare pas en changeant de
                # modèle. Sans indice, on retombe exactement sur le
                # comportement d'avant — reprendre une fois, sans rien
                # changer qu'on ne saurait justifier.
                from backend.runs.taxonomie import classer, remede

                classement = classer(str(exc))
                soin = remede(classement.cause)
                # Le classement n'est pas accroché à la tâche : elle n'a
                # pas de champ pour ça, et lui en ajouter un donnerait un
                # champ que personne ne lit. Il voyage par les événements
                # ci-dessous et par la `raison` du registre, qui sont les
                # deux endroits où on le cherchera.
                #
                # Le budget reste celui de la mission. La taxonomie dit
                # **si** on reprend, pas combien de fois : elle n'a aucune
                # mesure qui justifierait de rétrécir un chiffre que
                # quelqu'un a décidé.
                max_retries = sm._meta.max_retries_per_task
                if soin.reessayer and task.retries < max_retries:
                    task.retries += 1
                    task.status = TaskExecutionStatus.PENDING
                    self._publish("execution.retry", {
                        "task_id": task_id, "reason": "runtime_unavailable",
                        "detail": str(exc), "attempt": task.retries,
                        "cause": classement.cause.value,
                        "indice": classement.indice,
                        "remede": soin.explication,
                        "changer_de_modele": soin.changer_de_modele,
                        "reduire_le_modele": soin.reduire_le_modele,
                        "elargir_le_contexte": soin.elargir_le_contexte,
                        "changer_de_fournisseur": soin.changer_de_fournisseur,
                        "attendre_s": soin.attendre_s,
                    })
                else:
                    task.status = TaskExecutionStatus.FAILED
                    self._publish("execution.failed", {
                        "task_id": task_id, "reason": "runtime_unavailable",
                        "detail": str(exc),
                        "cause": classement.cause.value,
                        "indice": classement.indice,
                        # Pourquoi on ne reprend pas : « plafond atteint »
                        # et « on ne doit pas » sont deux choses, et les
                        # confondre ferait chercher un bug de compteur là
                        # où il y a un refus assumé.
                        "abandon": ("cause non reprenable" if not soin.reessayer
                                    else "plafond de tentatives atteint"),
                        "remede": soin.explication,
                    })
                self._scheduler.update_task(task_id, task.status)
                self._coordinator.release_agent(task_id)
                self._sync_agent_released(task.assigned_agent, task.duration_ms, task.status)
                # This early-exit path used to leave sm stuck at RUNNING
                # forever on a terminal failure — a runtime-unavailable
                # failure never transitioned it to a terminal state at all,
                # unlike the validation-outcome path below. That made this
                # execution permanently "active" to ExecutionController.get()/
                # list_executions() even though nothing was ever going to run
                # it again. A no-op here while task.status is PENDING (not
                # yet terminal) — correctly leaves sm active until the retry
                # itself resolves.
                self._maybe_finalize_state(sm)
            return {
                "task_id": task_id,
                "status": task.status.value,
                "error": str(exc),
                "runtime_available": False,
            }

        with self._lock:
            task.result = outcome.result
            task.duration_ms = outcome.duration_ms
            task.assigned_runtime = outcome.runtime_id
            task.resources_used = outcome.resources()
            task.completed_at = datetime.now(timezone.utc)
            # outcome.model (the specific tag Model Intelligence picked and
            # Ollama actually served — see task_executor.py's model_for) is
            # about to be shadowed by the validation outcome below and was
            # never returned to any caller. AutonomousOrchestrator needs it
            # to report which model a goal really used, not just "ollama".
            served_model = outcome.model
            # HOS-241 : et il ne reste plus local. Le registre des runs
            # affichait une colonne `modele` vide depuis HOS-221 parce
            # que personne ne la remplissait — la question « quel modele
            # a reellement execute cette mission ? » etait sans reponse.
            task.model_used = served_model
            # HOS-242 : le fournisseur et la decision de routage, dans
            # le meme mouvement. `metadata` porte deja les deux ;
            # aucune source nouvelle n'est ouverte ici.
            meta_sortie = getattr(outcome, "metadata", None) or {}
            task.provider_used = str(meta_sortie.get("fournisseur") or "")
            task.decision_de_routage = _decision_en_json(
                meta_sortie, served_model, outcome.runtime_id)

            # 3. Validate
            sm.transition(ExecutionState.VALIDATING, f"Validating task {task_id}")
            outcome = self._validator.validate(task)
            task.validation_outcome = outcome

            if outcome == ValidationOutcome.PASS:
                task.status = TaskExecutionStatus.COMPLETED
                # Not dispatched: RealTaskExecutor already publishes
                # execution.task_completed for this task, with richer detail
                # (runtime, model, duration, tokens). Announcing it again here
                # made subscribers count every task twice.
                self._publish("execution.task_completed",
                              {"task_id": task_id, "outcome": "pass"},
                              dispatch=False)
            elif outcome == ValidationOutcome.RETRY:
                # HOS-069: was a hardcoded 3 — ExecutionMeta.max_retries_per_task
                # existed as a field and was never actually read anywhere.
                if task.retries < sm._meta.max_retries_per_task:
                    task.retries += 1
                    task.status = TaskExecutionStatus.PENDING
                    task.errors.append("Retry after validation")
                else:
                    task.status = TaskExecutionStatus.FAILED
                    self._publish("execution.failed", {"task_id": task_id, "reason": "Max retries"})
            elif outcome == ValidationOutcome.FAIL:
                task.status = TaskExecutionStatus.FAILED
                self._publish("execution.failed", {"task_id": task_id, "reason": "Validation failed"})
            elif outcome == ValidationOutcome.NEEDS_REVIEW:
                sm.transition(ExecutionState.WAITING_APPROVAL, "Needs human review")
                self._publish("execution.waiting_approval", {"task_id": task_id})

            # Update scheduler
            self._scheduler.update_task(task_id, task.status)

            # Release agent
            self._coordinator.release_agent(task_id)
            self._sync_agent_released(task.assigned_agent, task.duration_ms, task.status)

            self._maybe_finalize_state(sm)

            return {
                "task_id": task_id,
                "status": task.status.value,
                "agent": task.assigned_agent,
                "runtime": task.assigned_runtime,
                "model": served_model,
                "skills": task.assigned_skills,
                "tools": task.assigned_tools,
                "outcome": task.validation_outcome.value if task.validation_outcome else None,
                "duration_ms": task.duration_ms,
            }

    def finalize(self, sm: ExecutionStateMachine) -> ExecutionReport:
        """Produce final report and trigger feedback + optimization."""
        with self._lock:
            # Every figure below is measured. total_duration_ms used to be
            # `42.0 * progress["total"]` — a constant per task, marked
            # "# simulated" — and this report is fed straight into
            # self._feedback.analyze(), so the feedback loop was learning from a
            # fabricated number. The runtime/skill/tool lists were hard-coded
            # empty even though every assignment records them (R-002 P5).
            task_ids = self._execution_tasks.get(sm._meta.execution_id, [])
            tasks = [t for t in (self._scheduler.get_task(tid) for tid in task_ids)
                     if t is not None]
            runtimes = _unique(t.assigned_runtime for t in tasks)
            skills = _unique(s for t in tasks for s in (t.assigned_skills or []))
            tools = _unique(s for t in tasks for s in (t.assigned_tools or []))
            agents = _unique(t.assigned_agent for t in tasks) or list(sm._meta.tags)
            # HOS-069: this used to default to empty — a failed task's
            # actual reason (VRAM admission denial, Ollama timeout,
            # validation failure) never reached the report at all, so
            # /execution/{id} and the Cockpit could show FAILED with no
            # explanation of why.
            errors = [t.errors[-1] for t in tasks if t.errors]

            report = ExecutionReport(
                execution_id=sm._meta.execution_id,
                mission_id=sm._meta.mission_id,
                state=sm.state,
                # HOS-069: was self._scheduler.get_progress()["total"/"completed"/
                # "failed"] — counts over *every* task on the shared scheduler
                # (up to its retention cap), not this execution's own. Invisible
                # before this phase because nothing ever called finalize() for a
                # real node execution; once it does (real Mission activity),
                # every report showed a growing global count instead of this
                # execution's actual 1 (or few) task(s) — e.g. "2/2 tasks" for
                # a single-task execution that happened to be the 2nd to finish
                # process-wide.
                total_tasks=len(tasks),
                completed_tasks=sum(1 for t in tasks if t.status == TaskExecutionStatus.COMPLETED),
                failed_tasks=sum(1 for t in tasks if t.status == TaskExecutionStatus.FAILED),
                total_duration_ms=sum(t.duration_ms or 0.0 for t in tasks),
                errors=errors,
                agents_used=agents,
                runtimes_used=runtimes,
                skills_used=skills,
                tools_used=tools,
            )

            # Feedback into Memory / Intelligence
            self._feedback.analyze(report)
            self._optimizer.record_execution(report.execution_id, {
                "state": report.state.value,
                "total_tasks": report.total_tasks,
                "failed_tasks": report.failed_tasks,
            })

            self._clore_le_run(report, tasks)

            recs = self._optimizer.generate_recommendations()
            if recs:
                self._publish("execution.optimized", {"execution_id": report.execution_id, "recommendations": len(recs)})

            return report

    # ── Le registre des runs (HOS-221) ─────────────────────────────

    def _ouvrir_le_run(self, meta: ExecutionMeta, tasks: list[TaskExecution],
                       contrat: Any = None) -> None:
        """Inscrire l'exécution au registre durable, avant qu'elle parte.

        Toujours en meilleur effort : une trace qui ferait échouer la
        mission qu'elle décrit serait pire que pas de trace. C'est la
        même règle que ``_sync_agent_started`` applique déjà juste
        au-dessus.
        """
        if self._registre is None:
            return
        try:
            runtimes = _unique(t.assigned_runtime for t in tasks)
            agents = _unique(t.assigned_agent for t in tasks)
            run = self._registre.ouvrir(
                mission=meta.mission_id,
                objectif=meta.user_goal,
                runtime=runtimes[0] if runtimes else "",
                agent=agents[0] if agents else "",
                contrat=contrat.to_json() if contrat is not None else "",
            )
            self._registre.demarrer(run.identifiant)
            self._runs[meta.execution_id] = run.identifiant
            while len(self._runs) > self._scheduler.MAX_RETAINED_TASKS:
                self._runs.popitem(last=False)
        except Exception:
            logger.warning("run non inscrit au registre", exc_info=True)

    @staticmethod
    def _joindre(valeurs) -> str:
        """Ce qu'un run inscrit quand ses tâches n'ont pas tout à fait
        tourné sur la même chose.

        Une mission décomposée peut employer deux modèles — le plan sur
        l'un, l'exécution sur l'autre (HOS-229). Prendre le premier
        laisserait croire qu'un seul a servi ; les joindre dit la vérité,
        et l'ordre d'apparition la rend lisible.
        """
        vus: list[str] = []
        for valeur in valeurs:
            texte = str(valeur or "").strip()
            if texte and texte not in vus:
                vus.append(texte)
        return ", ".join(vus)

    def _refuser_pour_budget(self, sm: Any, task: Any, task_id: str) -> dict[str, Any]:
        """Ne pas engager cette tache : le budget de la mission est atteint.

        Un refus, pas une panne. La tache est marquee `FAILED` parce que
        c'est le seul etat terminal dont dispose `TaskExecutionStatus` —
        mais son message dit *pourquoi*, et la taxonomie le classe
        `BUDGET`, distinct de `QUOTA` (une limite du fournisseur) et de
        `RESSOURCE` (une limite de la machine).

        **Ce n'est jamais `PERDU`.** Perdu veut dire « on ne sait pas ce
        qui s'est passe » ; ici on le sait exactement, et c'est nous qui
        l'avons decide.

        Les preuves deja produites par les taches precedentes ne sont pas
        touchees : ce chemin n'ecrit rien d'autre que le sort de la tache
        refusee.
        """
        motif = (
            f"budget de mission atteint : {sm.budget_consomme_s:.0f} s "
            f"consommées sur {sm.budget_s:.0f} s — tâche {task_id} non engagée")
        task.status = TaskExecutionStatus.FAILED
        task.errors = [motif]
        task.completed_at = datetime.now(timezone.utc)
        logger.warning("%s", motif)
        self._publish("execution.budget_depasse", {
            "task_id": task_id,
            "mission_id": getattr(sm._meta, "mission_id", ""),
            "consomme_s": round(sm.budget_consomme_s, 1),
            "budget_s": sm.budget_s,
        })
        return {"task_id": task_id, "status": task.status.value,
                "error": motif, "budget_depasse": True}

    def _clore_le_run(self, report: ExecutionReport,
                      tasks: list[TaskExecution]) -> None:
        """Clore le run avec ce qui s'est réellement passé.

        ``cause`` est renseignée depuis HOS-225, et **seulement quand un
        indice la démontre** : `backend.runs.taxonomie` rend `INCONNUE`
        sans rien inventer quand le message ne dit rien. La contrainte de
        HOS-221 tient donc toujours — une étiquette fausse coûte plus
        cher qu'une case vide, parce qu'on la croit — et elle est
        maintenant portée par un classificateur qui enregistre son indice
        au lieu d'être portée par une case laissée vide.

        ``raison`` continue de porter l'erreur brute : le classement est
        une lecture, jamais un remplacement.
        """
        identifiant = self._runs.pop(report.execution_id, None)
        if self._registre is None or identifiant is None:
            return
        from backend.runs.registre import Statut

        statut = (Statut.REUSSI if report.state == ExecutionState.COMPLETED
                  else Statut.ECHOUE)
        raison = ""
        if report.errors:
            derniere = report.errors[-1]
            raison = str(derniere.get("message", derniere)
                         if isinstance(derniere, dict) else derniere)[:2000]
        # Les jetons sont mesurés par le runtime quand il les rapporte —
        # `resources_used` porte la même valeur que la télémétrie, pas une
        # estimation refaite ici.
        entree = sum(int((t.resources_used or {}).get("prompt_tokens", 0))
                     for t in tasks)
        sortie = sum(int((t.resources_used or {}).get("completion_tokens", 0))
                     for t in tasks)
        cause = None
        if statut is not Statut.REUSSI and raison:
            from backend.runs.taxonomie import classer

            classement = classer(raison)
            # `INCONNUE` reste `None` en base plutôt qu'une étiquette :
            # une colonne vide se lit « on ne sait pas », une étiquette
            # « inconnue » se lit comme un diagnostic posé.
            cause = classement.cause if classement.classe else None
            if classement.indice:
                logger.info("run %s classé %s (%s)", identifiant,
                            classement.cause.value, classement.indice)

        # HOS-241 : ce qui a réellement servi, avant de clore — un run
        # terminal est gelé, y compris pour lui ajouter un fait.
        #
        # `ouvrir()` avait enregistré l'intention du coordinateur. Ici,
        # `assigned_runtime` porte le runtime que la réponse a déclaré
        # (`mission_executor` l'y réécrit après exécution) et `model_used`
        # le modèle qui a réellement répondu. Les tâches qui n'ont jamais
        # tourné n'ont ni l'un ni l'autre : on n'écrit rien plutôt que
        # d'écrire ce qui avait été demandé.
        try:
            self._registre.constater(
                identifiant,
                runtime=self._joindre(t.assigned_runtime for t in tasks),
                modele=self._joindre(t.model_used for t in tasks),
                fournisseur=self._joindre(t.provider_used for t in tasks),
                decision=self._joindre(t.decision_de_routage for t in tasks))
        except Exception:
            logger.warning("constat d'exécution non inscrit", exc_info=True)

        # R-6 : ce que ce run a coûté à la machine, avant de clore — un
        # run terminal est gelé, y compris pour lui ajouter un chiffre.
        #
        # Même forme que les jetons juste au-dessus : agrégé depuis les
        # tâches, sans ouvrir aucune source nouvelle. Les grandeurs
        # physiques ne s'additionnent pourtant pas comme des jetons — voir
        # `consommation.agreger`, qui prend le maximum d'une réservation et
        # non sa somme, parce que les tâches ne tiennent pas la carte en
        # même temps.
        try:
            from backend.runs.consommation import agreger

            mesures = agreger([getattr(t, "ressources_physiques", None) or {}
                               for t in tasks])
            if mesures:
                self._registre.mesurer(identifiant, **mesures)
        except Exception:
            logger.warning("consommation physique non inscrite", exc_info=True)

        try:
            self._registre.terminer(identifiant, statut, raison=raison,
                                    cause=cause,
                                    jetons_entree=entree, jetons_sortie=sortie)
        except Exception:
            logger.warning("run non clos au registre", exc_info=True)

    def run_de(self, execution_id: str) -> str | None:
        """L'identifiant de run qui corrèle cette exécution au registre.

        C'est aussi ce qui corrèle le registre au bus d'événements : les
        deux portent le même identifiant, et aucun des deux ne duplique
        l'autre.
        """
        return self._runs.get(execution_id)

    def pause(self, sm: ExecutionStateMachine) -> bool:
        with self._lock:
            if sm.state == ExecutionState.RUNNING:
                sm.transition(ExecutionState.PAUSED, "User requested pause")
                return True
            return False

    def resume(self, sm: ExecutionStateMachine) -> bool:
        with self._lock:
            if sm.state == ExecutionState.PAUSED:
                sm.transition(ExecutionState.RUNNING, "User requested resume")
                return True
            return False

    def cancel(self, sm: ExecutionStateMachine) -> bool:
        with self._lock:
            if not sm.is_terminal():
                sm.transition(ExecutionState.CANCELLED, "User requested cancel")
                return True
            return False

    def get_timeline(self, sm: ExecutionStateMachine) -> dict[str, Any]:
        with self._lock:
            progress = self._scheduler.get_progress()
            history = [{"from": old.value, "to": new.value, "reason": reason}
                       for old, new, reason in sm.history]
            return {
                "execution_id": sm._meta.execution_id,
                "state": sm.state.value,
                "progress": progress,
                "history": history,
                "events_count": len(self._events),
            }

    def get_events(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events)

    # ── Event publication ──

    def _publish(self, event_type: str, data: dict[str, Any],
                 dispatch: bool = True) -> None:
        """Record an event locally and dispatch it to the shared event bus.

        The dispatch half used to be missing: ``on_event`` was accepted,
        documented as "the shared event dispatcher", stored — and never called.
        Every mission lifecycle event was appended to this private list and went
        nowhere, so the Cockpit's live feed never saw a mission start, a task
        start or a mission completion (RC3 P2). Only the one event
        ``RealTaskExecutor`` emits itself was reaching subscribers.

        Args:
            dispatch: set False for milestones a collaborator already announces
                on the same topic, so subscribers do not see it twice. The event
                is still recorded in the local diagnostic tail either way.
        """
        event = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **data,
        }
        self._events.append(event)

        if not dispatch or self._on_event is None:
            return
        try:
            self._on_event(event_type, event)
        except Exception:
            # Telemetry must never fail the mission it is describing.
            logger.warning("event dispatch failed for %s", event_type, exc_info=True)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "scheduler": self._scheduler.stats(),
                "coordinator": self._coordinator.stats(),
                "validator": self._validator.stats(),
                "feedback": self._feedback.stats(),
                "optimizer": self._optimizer.stats(),
                "events_published": len(self._events),
            }
