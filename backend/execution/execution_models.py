"""Execution models for the Autonomous Mission Execution Engine (HOS-050)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


# ── Enums ────────────────────────────────────────────────────

class ExecutionState(str, Enum):
    """Full state machine for mission execution lifecycle."""
    CREATED = "created"
    PLANNING = "planning"
    READY = "ready"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    PAUSED = "paused"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskExecutionStatus(str, Enum):
    """Per-task execution status within a mission."""
    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    WAITING = "waiting"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ExecutionPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class CheckpointType(str, Enum):
    """Type of checkpoint saved during execution."""
    AUTO = "auto"          # Automatic periodic checkpoint
    PAUSE = "pause"        # Checkpoint before pausing
    PRE_VALIDATION = "pre_validation"  # Before validation step
    PRE_TOOL = "pre_tool"  # Before tool execution
    MANUAL = "manual"      # User-requested checkpoint


class SchedulerStrategy(str, Enum):
    """Task scheduling strategies."""
    PARALLEL = "parallel"       # Execute all independent tasks in parallel
    SEQUENTIAL = "sequential"   # One task at a time
    PRIORITY = "priority"       # Highest priority first
    RESOURCE_AWARE = "resource" # Consider resource constraints (GPU/RAM)


class ValidationOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    RETRY = "retry"
    NEEDS_REVIEW = "needs_review"


class OptimizationCategory(str, Enum):
    RUNTIME = "runtime"
    SKILL = "skill"
    AGENT = "agent"
    TOOL = "tool"
    SCHEDULE = "schedule"
    RESOURCE = "resource"


#: Le budget de temps par défaut d'une exécution de mission (HOS-247).
#: Nommé plutôt qu'écrit en dur dans le dataclass : le cas `0` doit
#: pouvoir y retomber sans dupliquer la valeur à deux endroits, où elles
#: divergeraient au premier réglage.
BUDGET_MISSION_PAR_DEFAUT_S = 3600.0


def budget_de(meta: "ExecutionMeta") -> float:
    """Le budget effectif d'une exécution, en secondes (HOS-247).

    Une seule lecture de la sémantique, à un seul endroit : la dupliquer
    chez chaque appelant les ferait diverger au premier réglage, et le
    cas `0` serait tôt ou tard interprété comme « illimité » par l'un
    d'eux — précisément l'invention que ce jalon refuse.
    """
    brut = getattr(meta, "max_duration_seconds", None)
    if brut is None:
        # Rétrocompatibilité : un `meta` d'avant HOS-247, ou un double de
        # test qui ne porte pas le champ. Le défaut s'applique, et se
        # comporte donc comme le dataclass l'a toujours annoncé.
        return BUDGET_MISSION_PAR_DEFAUT_S
    valeur = float(brut)
    if valeur < 0:
        raise ValueError(
            f"budget de mission invalide : {valeur} s. Il n'existe pas de "
            "valeur « illimitée » — 0 demande le défaut "
            f"({BUDGET_MISSION_PAR_DEFAUT_S} s), un nombre positif fixe le "
            "budget.")
    return valeur or BUDGET_MISSION_PAR_DEFAUT_S


# ── Dataclasses ──────────────────────────────────────────────

@dataclass
class ExecutionMeta:
    """Metadata for a mission execution instance."""
    execution_id: str = field(default_factory=lambda: uuid4().hex[:12])
    mission_id: str = ""
    user_goal: str = ""
    priority: ExecutionPriority = ExecutionPriority.NORMAL
    #: Budget de temps de l'exécution entière, en secondes (HOS-247).
    #:
    #: **3 600 s n'est pas un chiffre rond choisi par confort** : c'est
    #: 1,65 fois le pire cas *réussi* mesuré sur le terrain — 2 186 s pour
    #: une mission de 7 tâches menée à 7/7 (`docs/essai-skills360.md`). Un
    #: budget de 1 800 s aurait tué cette mission-là à 82 % de son travail.
    #: C'est aussi exactement 3 plafonds de nœud (1 200 s), soit 4 tâches
    #: au budget agent plein ou ~11 à la cadence réellement observée.
    #:
    #: Sémantique, alignée sur la seule convention documentée du dépôt —
    #: `ModelDecision.num_ctx`, où 0 signifie « le défaut de l'appelant » :
    #:
    #: * `> 0` — le budget, en secondes ;
    #: * `0`   — utiliser `BUDGET_MISSION_PAR_DEFAUT_S` ;
    #: * `< 0` — **invalide**, rejeté bruyamment.
    #:
    #: Il n'existe **aucune** valeur « illimitée », et il serait malhonnête
    #: d'en offrir une : `MAX_EXECUTION_PASSES × plafond_du_noeud()` borne
    #: déjà toute mission à 33 heures.
    max_duration_seconds: float = BUDGET_MISSION_PAR_DEFAUT_S
    max_retries_per_task: int = 3
    scheduler_strategy: SchedulerStrategy = SchedulerStrategy.RESOURCE_AWARE
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class TaskExecution:
    """Runtime tracking for a single task node during execution."""
    task_id: str = ""
    node_id: str = ""
    # Workspace/Filesystem tool layer (HOS-084) — RealTaskExecutor's
    # workspace_project_for(task) reads this to resolve the owning
    # Mission's bound Project. Empty for a task that did not originate
    # from a Mission node (e.g. the standalone /execution/start API with
    # no mission_id given) — same "empty means not applicable" convention
    # as task_type below.
    mission_id: str = ""
    title: str = ""
    # HOS-070: mirrors MissionNode.type (mission/mission_models.py) — the
    # input CapabilityMatcher's task-type -> capability map expects
    # ("analysis", "implementation", ...). Empty for a task that did not
    # originate from a Mission node (e.g. the standalone /execution/start
    # API), which AgentCoordinator's real-matcher path treats the same way
    # CapabilityMatcher itself does: falls back to AgentCapability.CUSTOM.
    task_type: str = ""
    # Mirrors MissionNode.preferred_agent — a scoring hint, not a hard
    # requirement (CapabilityMatcher still checks capability/availability
    # first).
    preferred_agent: str = ""
    status: TaskExecutionStatus = TaskExecutionStatus.PENDING
    assigned_agent: str = ""
    assigned_runtime: str = ""
    # HOS-241: the model that actually served this task, taken from the
    # response metadata by RealTaskExecutor. Distinct from every
    # ``assigned_*`` field above, which hold what the coordinator *asked
    # for*: a retry swaps the model (task_executor._resolve_model), and a
    # ledger that recorded the request would claim a model that never ran.
    # Empty until the task has actually executed — never a default.
    model_used: str = ""
    # HOS-242: who actually served the weights, as distinct from the
    # runtime surface called. "local" for Ollama; for OpenRouter the
    # upstream provider it names in its own response. Empty when the
    # response does not say — never inferred from the runtime, which
    # would pass a guess off as a measurement.
    provider_used: str = ""
    # HOS-242: the routing decision this task was executed under, as
    # compact JSON. Answers "what was asked for, what served it, and
    # why they differ" for a run long after its events have scrolled.
    decision_de_routage: str = ""
    assigned_skills: list[str] = field(default_factory=list)
    # AgentCoordinator's recommendation, surfaced to the model as a text
    # hint in the system prompt (see RealTaskExecutor._build_messages()) —
    # NOT a real tool/MCP invocation (HOS-069 audit finding). No tool named
    # here is ever actually called.
    assigned_tools: list[str] = field(default_factory=list)
    result: Any = None
    errors: list[str] = field(default_factory=list)
    retries: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: float = 0.0
    resources_used: dict[str, float] = field(default_factory=dict)
    #: R-6 — ce que cette tentative a constaté de la machine, en octets.
    #:
    #: Séparé de `resources_used` pour une raison mesurée : celui-ci n'est
    #: écrit qu'au retour normal d'`execute` (`mission_executor`, « with
    #: self._lock: task.resources_used = outcome.resources() »), et le
    #: chemin `RuntimeUnavailableError` sort **avant**. Une tâche en échec
    #: y perdrait toute trace physique, alors que c'est précisément le cas
    #: où l'on veut savoir ce que la carte portait.
    #:
    #: Écrit par `RealTaskExecutor` dans son `finally`, donc sur toutes les
    #: sorties. Clés absentes = non mesuré ; jamais de zéro par défaut.
    #: Sémantique complète : `backend/runs/consommation.py`.
    ressources_physiques: dict[str, Any] = field(default_factory=dict)
    validation_outcome: ValidationOutcome | None = None


@dataclass
class ExecutionCheckpoint:
    """Snapshot of execution state for pause/resume/rollback."""
    checkpoint_id: str = field(default_factory=lambda: uuid4().hex[:8])
    execution_id: str = ""
    checkpoint_type: CheckpointType = CheckpointType.AUTO
    state: ExecutionState = ExecutionState.CREATED
    completed_tasks: list[str] = field(default_factory=list)
    current_task_id: str = ""
    metadata_snapshot: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ExecutionTimeline:
    """Chronological record of execution events for the Mission Center."""
    execution_id: str = ""
    entries: list[dict[str, Any]] = field(default_factory=list)

    def add(self, event_type: str, detail: dict[str, Any]) -> None:
        self.entries.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            **detail,
        })


@dataclass
class ExecutionReport:
    """Final report produced after mission completion."""
    execution_id: str = ""
    mission_id: str = ""
    state: ExecutionState = ExecutionState.CREATED
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    total_duration_ms: float = 0.0
    agents_used: list[str] = field(default_factory=list)
    runtimes_used: list[str] = field(default_factory=list)
    skills_used: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    optimizations: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
