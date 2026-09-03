"""Execution state machine for HOS-050 — manages lifecycle transitions."""

from __future__ import annotations

import threading
import time
from typing import Any

from .execution_models import (
    budget_de,
    ExecutionCheckpoint,
    ExecutionMeta,
    ExecutionState,
    CheckpointType,
)


class ExecutionStateMachine:
    """Thread-safe state machine for mission execution lifecycle.

    Valid transitions:
        CREATED → PLANNING → READY → RUNNING → (VALIDATING → COMPLETED | FAILED)
                             ↓         ↓           ↓
                          CANCELLED  PAUSED → RUNNING (resume)
                                     WAITING_APPROVAL → RUNNING
    """

    VALID_TRANSITIONS: dict[ExecutionState, set[ExecutionState]] = {
        ExecutionState.CREATED:           {ExecutionState.PLANNING, ExecutionState.CANCELLED},
        ExecutionState.PLANNING:          {ExecutionState.READY, ExecutionState.FAILED, ExecutionState.CANCELLED},
        ExecutionState.READY:             {ExecutionState.RUNNING, ExecutionState.CANCELLED},
        ExecutionState.RUNNING:           {ExecutionState.PAUSED, ExecutionState.WAITING_APPROVAL,
                                          ExecutionState.VALIDATING, ExecutionState.FAILED,
                                          ExecutionState.COMPLETED, ExecutionState.CANCELLED},
        ExecutionState.WAITING_APPROVAL:  {ExecutionState.RUNNING, ExecutionState.FAILED, ExecutionState.CANCELLED},
        ExecutionState.PAUSED:            {ExecutionState.RUNNING, ExecutionState.CANCELLED},
        ExecutionState.VALIDATING:        {ExecutionState.COMPLETED, ExecutionState.RUNNING,
                                          ExecutionState.FAILED, ExecutionState.CANCELLED},
        ExecutionState.COMPLETED:         set(),
        ExecutionState.FAILED:            {ExecutionState.RUNNING, ExecutionState.CANCELLED},  # retry
        ExecutionState.CANCELLED:         set(),
    }

    def __init__(self, meta: ExecutionMeta | None = None) -> None:
        self._lock = threading.RLock()
        self._state: ExecutionState = ExecutionState.CREATED
        self._history: list[tuple[ExecutionState, ExecutionState, str]] = []
        self._checkpoints: dict[str, ExecutionCheckpoint] = {}
        self._meta = meta or ExecutionMeta()
        #: t0 du budget de mission (HOS-247) : la construction de la
        #: machine d'état, c'est-à-dire l'instant où cette exécution
        #: existe. Pas `meta.created_at`, qui est posé par le
        #: `default_factory` du dataclass et peut précéder l'exécution de
        #: loin ; pas `meta.started_at`, qui n'est **posé par personne** —
        #: mesuré.
        #:
        #: Monotone et non `datetime.now()` : une horloge civile recule à
        #: l'heure d'hiver et lors d'une synchronisation NTP, et une
        #: mission serait alors coupée ou prolongée par le réglage de la
        #: machine. La date civile reste sur `meta` pour l'affichage ; la
        #: **décision** d'expiration ne s'appuie que sur celle-ci.
        #:
        #: `perf_counter` plutôt que `monotonic` : les deux sont monotones,
        #: mais `monotonic` a ~16 ms de résolution sur Windows — mesuré, un
        #: budget de 1 ms s'y lisait « 0 s consommée ». Sans importance à
        #: l'échelle d'un budget en heures, mais un test qui vérifie la
        #: frontière ne doit pas dépendre de la granularité de l'horloge.
        #: C'est aussi ce que `task_executor` utilise déjà pour ses durées.
        self._budget_t0 = time.perf_counter()
        #: Ce que la mission avait déjà consommé au moment où cette machine
        #: est née (HOS-248). Lu **une seule fois** : c'est le seul terme
        #: civil, et le limiter à une lecture est ce qui garde la mesure
        #: d'un nœud en cours à l'abri d'un saut d'horloge.
        self._budget_offset_s = self._offset_missionnel()
        # Valider tôt : une valeur négative doit être refusée là où elle
        # est fournie, pas découverte au milieu d'une mission.
        budget_de(self._meta)

    def _mission(self) -> Any:
        """La mission dont cette exécution est un nœud, ou `None`.

        Passe par le registre des missions, qui est un **cache** devant la
        base (M-8) : une lecture par tâche, sur une tâche qui dure des
        centaines de secondes, ne coûte rien. Ce serait autre chose dans
        une boucle serrée, et c'est pourquoi le budget se consulte entre
        deux unités de travail et nulle part ailleurs.

        Ne lève jamais : une mission illisible fait retomber le budget sur
        celui de l'exécution, ce qui est le comportement d'avant HOS-248.
        """
        mission_id = getattr(self._meta, "mission_id", "") or ""
        if not mission_id:
            return None
        try:
            from backend.mission.routes import _missions

            return _missions.get(mission_id)
        except Exception:  # pragma: no cover - registre indisponible
            return None

    @property
    def budget_s(self) -> float:
        """Le budget qui s'applique, en secondes. Toujours > 0.

        **Précédence, explicite (HOS-248)** :

        1. la **mission**, quand elle existe — c'est l'autorité ;
        2. à défaut, l'`ExecutionMeta` de cette exécution.

        Le chemin direct (`POST /execution/start`) n'a pas de mission au
        registre : il garde donc son budget local, qui y est bien un
        budget d'exécution puisqu'un seul `ExecutionMeta` couvre toutes
        ses tâches. Sur le chemin du DAG, au contraire, il y en a un par
        nœud — et c'est tout le défaut que ce jalon corrige.
        """
        mission = self._mission()
        if mission is not None:
            return budget_de(mission)
        return budget_de(self._meta)

    @property
    def budget_consomme_s(self) -> float:
        """Le temps consommé par ce qui porte le budget.

        Deux termes, et un seul est civil :

            déjà consommé avant cette machine   (civil, lu **une fois**)
          + écoulé depuis sa construction       (monotone)

        Le premier ne peut pas être monotone : il traverse la frontière
        du processus, et une horloge monotone ne mesure que depuis un
        démarrage. Il est donc lu sur `Mission.started_at`, persisté — et
        lu **une seule fois**, à la construction.

        Le second, qui est celui qui court pendant qu'une mission
        travaille, reste sur `perf_counter`. Un recul de l'horloge système
        — heure d'hiver, synchronisation NTP — ne peut donc plus allonger
        ni raccourcir une mission en cours : au pire il décale l'offset
        d'un nœud qui démarre juste après, jamais la mesure d'un nœud qui
        tourne.

        C'est ce que la passe 9 décrivait : « ancrage temporel persistant
        → horloge monotone du processus courant ». Sans registre global :
        l'offset tient sur la machine d'état elle-même.
        """
        return self._budget_offset_s + (time.perf_counter() - self._budget_t0)

    def _offset_missionnel(self) -> float:
        """Ce que la mission avait déjà consommé quand cette machine est née.

        Zéro quand aucune mission n'est enregistrée, ou qu'elle n'a pas
        encore été démarrée : on mesure alors ce qu'on sait mesurer, et
        le budget se comporte comme avant HOS-248.
        """
        mission = self._mission()
        depart = getattr(mission, "started_at", None) if mission else None
        if depart is None:
            return 0.0
        from datetime import datetime, timezone

        if depart.tzinfo is None:
            depart = depart.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - depart).total_seconds())

    def budget_depasse(self) -> bool:
        """Le budget est-il atteint ?

        Consultée **entre** deux unités de travail, jamais pendant : une
        tâche déjà engagée va au bout de son propre plafond. Ce budget
        décide de ce qu'on *engage*, pas de ce qu'on interrompt — c'est ce
        qui le distingue d'un timeout, et ce qui fait qu'il ne tue rien.

        Depuis HOS-248, la mission prime : tous les nœuds d'une même
        tentative lisent le **même** `started_at` et le **même** budget,
        si bien qu'un `ExecutionMeta` neuf ne remet aucun compteur à zéro.
        """
        return self.budget_consomme_s >= self.budget_s

    @property
    def state(self) -> ExecutionState:
        with self._lock:
            return self._state

    @property
    def history(self) -> list[tuple[ExecutionState, ExecutionState, str]]:
        with self._lock:
            return list(self._history)

    def can_transition(self, target: ExecutionState) -> bool:
        with self._lock:
            return target in self.VALID_TRANSITIONS.get(self._state, set())

    def transition(self, target: ExecutionState, reason: str = "") -> ExecutionState:
        """Attempt a state transition. Returns the new state or raises ValueError.

        A transition to the state already current is a no-op, not an error
        (HOS-068): this state machine can be shared across several tasks of
        one execution, and MissionExecutor.execute_task() now runs its slow
        inference call outside its own lock so genuinely concurrent tasks
        can each try to mark the shared execution RUNNING (or VALIDATING) at
        nearly the same moment. Neither call is wrong — the execution
        legitimately is already in that state — so racing to set it again
        must not raise. This does not weaken the graph for any other target:
        a *different* target still goes through the full check below.
        """
        with self._lock:
            if target == self._state:
                self._history.append((self._state, target, reason))
                return self._state
            if target not in self.VALID_TRANSITIONS.get(self._state, set()):
                allowed = self.VALID_TRANSITIONS.get(self._state, set())
                raise ValueError(
                    f"Invalid transition: {self._state.value} → {target.value}. "
                    f"Allowed: {[s.value for s in allowed]}"
                )
            old = self._state
            self._state = target
            self._history.append((old, target, reason))
            return self._state

    def save_checkpoint(self, checkpoint_type: CheckpointType = CheckpointType.AUTO,
                        metadata: dict[str, Any] | None = None) -> ExecutionCheckpoint:
        with self._lock:
            cp = ExecutionCheckpoint(
                execution_id=self._meta.execution_id,
                checkpoint_type=checkpoint_type,
                state=self._state,
                metadata_snapshot=metadata or {},
            )
            self._checkpoints[cp.checkpoint_id] = cp
            return cp

    def get_checkpoint(self, checkpoint_id: str) -> ExecutionCheckpoint | None:
        with self._lock:
            return self._checkpoints.get(checkpoint_id)

    def get_last_checkpoint(self) -> ExecutionCheckpoint | None:
        with self._lock:
            if not self._checkpoints:
                return None
            # max() returns the *first* of several equal maxima, and two
            # checkpoints saved inside one clock tick share created_at — which
            # is routine on Windows, whose clock is coarse. Iterating the
            # insertion-ordered dict backwards makes the most recently saved
            # checkpoint win such ties, which is what "last" means here.
            return max(reversed(self._checkpoints.values()), key=lambda c: c.created_at)

    def is_terminal(self) -> bool:
        return self.state in {ExecutionState.COMPLETED, ExecutionState.FAILED, ExecutionState.CANCELLED}

    def is_active(self) -> bool:
        return self.state in {ExecutionState.RUNNING, ExecutionState.VALIDATING}

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": self._state.value,
                "history_length": len(self._history),
                "checkpoints": len(self._checkpoints),
                "is_terminal": self.is_terminal(),
                "is_active": self.is_active(),
            }
