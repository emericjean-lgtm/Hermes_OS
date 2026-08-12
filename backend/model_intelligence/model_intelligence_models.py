"""Model Intelligence models for Hermes OS (HOS-065)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar, Optional


class ModelArchitecture(str, Enum):
    LLAMA = "llama"
    MISTRAL = "mistral"
    QWEN = "qwen"
    DEEPSEEK = "deepseek"
    PHI = "phi"
    CODELAMA = "codellama"
    FALCON = "falcon"
    GEMMA = "gemma"
    STARCODER = "starcoder"
    MIXTRAL = "mixtral"
    OTHER = "other"


class TaskType(str, Enum):
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    DEBUG = "debug"
    REFACTOR = "refactor"
    ANALYSIS = "analysis"
    CHAT = "chat"
    DOCUMENTATION = "documentation"
    OPTIMIZATION = "optimization"
    REASONING = "reasoning"
    GENERAL = "general"


class RuntimeBackend(str, Enum):
    OLLAMA = "ollama"
    KTRANSFORMERS = "ktransformers"
    TRANSFORMERS = "transformers"
    VLLM = "vllm"
    LLAMACPP = "llamacpp"
    # OpenRouter's free (":free") model pool — the only cloud tier this
    # project uses (see backend/connectors/openrouter_client.py). Never the
    # default: AdaptiveRouter only offers it when no local model is viable
    # or a task explicitly opts in, and only when Aegis's cloud_inference
    # category authorizes it (config/security.yaml) — see AdaptiveRouter's
    # CloudGate.
    OPENROUTER = "openrouter"


class Quantization(str, Enum):
    NONE = "none"
    Q4_0 = "q4_0"
    Q4_K_M = "q4_k_m"
    Q5_K_M = "q5_k_m"
    Q8_0 = "q8_0"
    F16 = "f16"


@dataclass
class ModelProfile:
    model_id: str
    name: str
    architecture: ModelArchitecture = ModelArchitecture.OTHER
    parameters_b: float = 0.0
    quantization: Quantization = Quantization.NONE
    vram_required_mb: int = 0
    ram_required_mb: int = 0
    context_window: int = 4096
    tokens_per_second: float = 0.0
    latency_ms: float = 0.0
    task_scores: dict[str, float] = field(default_factory=dict)
    historical_success_rate: float = 0.0
    total_runs: int = 0
    successful_runs: int = 0
    available_backends: list[RuntimeBackend] = field(default_factory=list)
    recommended_quantization: Quantization = Quantization.Q4_K_M
    tags: list[str] = field(default_factory=list)
    last_used: str = ""
    benchmark_score: float = 0.0
    # False only for embedding-only models (nomic-embed-text): they serve
    # /api/embed, not /api/chat, and Ollama returns 400 Bad Request if asked
    # to chat with one. AdaptiveRouter must exclude them from task-execution
    # recommendations even though they belong in the general catalogue —
    # found via a real POST /verification-free mission run, where nomic-
    # embed-text won every recommendation on VRAM footprint alone (0.3GB,
    # smallest of all twelve) with every other ranking signal still at its
    # neutral untrained default.
    chat_capable: bool = True
    #: What Ollama's own /api/show reports under "capabilities" — the real
    #: source, not a guess from the tag. Necessary for agentic work, and
    #: demonstrably not sufficient: qwen3.5:2b and even
    #: qwen3-embedding:0.6b both declare "tools".
    declares_tools: bool = False
    #: Set from a real measured run when one exists. None means "never
    #: measured", which is why agentic_capable falls back to a size
    #: heuristic rather than assuming either answer.
    measured_agentic_success: Optional[bool] = None
    #: What the runtime will actually hand out, as opposed to
    #: ``context_window`` above, which is what the weights support. Kept as
    #: a separate field precisely because conflating the two is the bug this
    #: encodes: devstral supports 131072 and was being served 8192. None
    #: means never probed.
    served_context: Optional[int] = None
    #: Bytes of this model pushed out of VRAM at its served context. The
    #: number that actually decides usability on fixed local hardware
    #: (HOS-096): devstral given 65536 needs 25.52 GB, of which 10.75 GB —
    #: 42% of the model — lands on CPU on a 16 GB card. It still answers, so
    #: nothing reports an error; it simply takes ~300s per task and calls
    #: tools erratically. Raising the context to fix truncation is what
    #: pushed it over the edge, so the two settings cannot be reasoned about
    #: separately. None means never measured.
    cpu_offload_bytes: Optional[int] = None

    #: Kept only to describe a model, never to judge it. HOS-096 measured
    #: three trials each on real agentic work and found parameter count has
    #: no predictive value here — if anything it inverts:
    #:
    #:     lfm2.5-2.6b-128k   2.7B   3/3   ~25s   1.67 GB
    #:     qwen3.5:9b-128k    9.7B   3/3   ~47s  10.18 GB
    #:     gemma4:12b-64k    11.9B   0/3   timeout
    #:     devstral          23.6B   1/3   ~300s (spills 10.75 GB to CPU)
    #:
    #: A 2.7B model wins outright while an 11.9B one never completes a
    #: single trial. The earlier 7B floor would have rejected the best model
    #: available on this hardware. What separates them is post-training:
    #: LFM2.5 was trained with agentic reinforcement learning, the others
    #: are general models asked to behave like agents.
    AGENTIC_MIN_PARAMETERS_B: ClassVar[float] = 0.0

    #: Hermes Agent's own guidance, corroborated here by measurement: below
    #: roughly 64k of *served* context, agents call tools far less reliably
    #: and hallucinate results more. Note "served", not "supported" — the
    #: distinction cost real debugging time (HOS-090): devstral advertises
    #: 131072 and Hermes' own context cache knows it, yet Ollama was handing
    #: out 8192 because the OpenAI-compatible /v1 endpoint carries no
    #: num_ctx and Ollama falls back to its own default. A tool schema plus
    #: a mission brief does not fit in 8k, so the tools were silently
    #: truncated away and the agent answered that it had no file access —
    #: which was true.
    AGENTIC_MIN_CONTEXT: ClassVar[int] = 65536

    @property
    def agentic_capable(self) -> bool:
        """Can this model actually drive an agent loop?

        Only a measured run answers this (HOS-096). Every structural signal
        was tried and each one was refuted by the next measurement: parameter
        count inverts (2.7B passes 3/3, 11.9B fails 0/3), a declared "tools"
        capability is claimed even by an embedding model, 64k of served
        context did not save gemma4:12b, and fitting in VRAM did not either.

        So an unmeasured model is treated as **unproven**, not as capable.
        That is deliberately conservative: guessing was wrong roughly half
        the time on real models here, and the cost of guessing wrong is a
        mission that reports success and accomplishes nothing — the failure
        this whole line of work exists to remove. Callers substitute a
        known-good fallback for anything unproven, and agentic_probe.py is
        how a model earns its way out of that state.

        The checks below are fast structural disqualifiers, not evidence of
        capability: they can only rule a model *out*.
        """
        # Disqualifiers first, and deliberately ahead of the measurement:
        # a past verdict was taken under past conditions, and the runtime
        # can invalidate it. devstral measured 1/3 *because* it was spilling
        # to CPU; a model that starts overflowing after a context change is
        # in that same state whatever it once scored.
        if not self.chat_capable:
            return False
        if not self.declares_tools:
            return False
        if self.parameters_b < self.AGENTIC_MIN_PARAMETERS_B:
            return False
        if self.cpu_offload_bytes:
            return False
        if self.served_context is not None and self.served_context < self.AGENTIC_MIN_CONTEXT:
            return False
        if self.measured_agentic_success is not None:
            return self.measured_agentic_success
        # Survived every disqualifier, but none of them is positive evidence
        # — gemma4:12b clears all of them and still failed 0/3. Unproven.
        return False

    def __post_init__(self) -> None:
        if not self.last_used:
            self.last_used = datetime.now(timezone.utc).isoformat()

    @property
    def success_rate(self) -> float:
        if self.total_runs == 0:
            return self.historical_success_rate
        return self.successful_runs / self.total_runs

    @property
    def overall_score(self) -> float:
        """A rough, self-contained approximation of PerformanceAnalyzer.
        compute_model_score() (HOS-071 Phase B) — same Quality 30 /
        Reliability 25 / Speed 20 / Efficiency 15 / Benchmark 10 weights,
        for any caller with only a bare profile and no analyzer to ask
        (e.g. ModelEvolutionAdapter comparing two candidates). Not
        interchangeable with the real formula: each factor here reads only
        what this object carries (this profile's own success_rate/
        benchmark_score, a linear speed curve) rather than the analyzer's
        richer, shared inputs (per-model performance records, a real
        cross-model benchmark history, human ratings) — the two can
        legitimately disagree on the exact number. ModelProfiler/
        ModelPredictor (HOS-071 Phase B) never read this property; they
        always call compute_model_score() directly, which is the one score
        that actually drives ranking and real recommendation."""
        quality = self.task_scores.get("quality", 0.5)
        speed = min(1.0, self.tokens_per_second / 100.0) if self.tokens_per_second > 0 else 0.5
        reliability = self.success_rate
        efficiency = 1.0 - (self.vram_required_mb / 80000.0) if self.vram_required_mb > 0 else 0.5
        return (quality * 0.30 + speed * 0.20 + reliability * 0.25
                + efficiency * 0.15 + self.benchmark_score * 0.10)


@dataclass
class TaskContext:
    task_type: TaskType = TaskType.GENERAL
    complexity: float = 0.3
    language: str = "python"
    max_latency_ms: int = 5000
    max_vram_mb: int = 8192
    max_ram_mb: int = 16384
    priority: str = "normal"
    security_level: str = "normal"
    requires_reasoning: bool = False
    requires_code: bool = True
    deadline_s: int = 300
    budget_tokens: int = 100000
    # Explicit opt-in for a cloud (OpenRouter free-model) escalation, mirroring
    # how reasoning_escalation/advanced_analysis are deliberate, named local
    # tiers rather than something a complexity heuristic silently triggers.
    # False (the default) still lets AdaptiveRouter reach for cloud in the one
    # other honest case: no local model is viable at all (see recommend()).
    cloud_escalation_allowed: bool = False


@dataclass
class ModelDecision:
    model_id: str
    model_name: str
    runtime: RuntimeBackend
    quantization: Quantization
    confidence: float
    reason: str
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    estimated_latency_ms: int = 0
    estimated_tokens_per_second: float = 0.0
    estimated_vram_mb: int = 0
    task_context: TaskContext | None = None
    # The per-role operational context window (config/models.yaml's
    # roles.*.num_ctx, HOS-065C) — not the model's architectural maximum
    # (that lives on ModelProfile.context_window too, same source). 0 means
    # "the caller's own default", the same convention chat_events() already
    # uses for its own num_ctx parameter.
    num_ctx: int = 0


@dataclass
class ModelPerformanceRecord:
    model_id: str
    task_type: TaskType
    duration_ms: int
    tokens_used: int
    success: bool
    human_rating: float = 0.0
    error_type: str = ""
    vram_used_mb: int = 0
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class BenchmarkResult:
    benchmark_id: str
    model_id: str
    task_type: TaskType
    latency_ms: float
    tokens_per_second: float
    vram_usage_mb: int
    ram_usage_mb: int
    quality_score: float
    temperature: float
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


_ARCH_PREFIXES: tuple[tuple[str, str], ...] = (
    ("qwen", "qwen"), ("deepseek", "deepseek"), ("gemma", "gemma"),
    ("phi", "phi"), ("mistral", "mistral"), ("mixtral", "mixtral"),
    ("llama", "llama"), ("codellama", "codellama"), ("falcon", "falcon"),
    ("starcoder", "starcoder"),
)


def _infer_architecture(model_tag: str) -> str:
    tag = model_tag.lower()
    for prefix, arch in _ARCH_PREFIXES:
        if prefix in tag:
            return arch
    return "other"


_PARAM_COUNT_RE = re.compile(r"(\d+(?:\.\d+)?)b(?:[^a-z0-9]|$)", re.IGNORECASE)


def _infer_parameters_b(model_tag: str) -> float:
    """Read the parameter count the vendor already put in their own tag
    (``qwen3.5:9b`` -> 9.0), rather than leaving every entry at 0 or
    inventing a number nobody measured. Tags with no size suffix
    (``devstral``, ``nomic-embed-text``) honestly stay at 0.0."""
    match = _PARAM_COUNT_RE.search(model_tag)
    return float(match.group(1)) if match else 0.0


def _build_predefined_models() -> dict[str, dict[str, Any]]:
    """Seed the profiler from config/models.yaml's roles — the same file
    agent_registry.py and ModelRouter treat as the single source of truth
    for which Ollama tag backs which role.

    This replaced six fictional entries (``qwen3-coder-30b``,
    ``mistral-7b``, ``codellama-7b``, ``phi3-14b``, ``deepseek-coder-16b``,
    ``llama3.2-3b``) that this deployment has never had installed — the
    Models Center presented a plausible-looking benchmark leaderboard for
    models nobody could run. Fields this project has no measured data for
    (``tokens_per_second``, ``task_scores``, ``context_window``) are left
    at their honest defaults — see ``ModelProfile.overall_score``, which
    already degrades gracefully to neutral values rather than requiring
    them — instead of being filled with equally invented plausible numbers.
    """
    try:
        from backend.core.config import load_models_config

        roles: dict[str, dict[str, Any]] = load_models_config().get("roles") or {}
    except Exception:
        # A missing/unreadable config/models.yaml must not take the whole
        # module down at import time; an empty catalogue is honest about
        # not knowing any models, which is what the old fictional six
        # never were.
        return {}

    models: dict[str, dict[str, Any]] = {}
    for role_name, role in roles.items():
        tag = role.get("model")
        if not tag or tag in models:
            continue
        models[tag] = {
            "name": tag,
            "architecture": _infer_architecture(tag),
            "parameters_b": _infer_parameters_b(tag),
            "vram_required_mb": int(float(role.get("vram_gb", 0)) * 1024),
            "available_backends": ["ollama"],
            # HOS-073: deduped — a role whose own tier shares its name
            # (config/models.yaml's "standard" role has tier "standard")
            # produced the literal string twice, which the Cockpit's tags
            # list renders with key={tag}, colliding as a React duplicate
            # key ("Encountered two children with the same key, `standard`").
            "tags": list(dict.fromkeys(t for t in (role_name, role.get("tier", "")) if t)),
            # The embedding role serves /api/embed, not /api/chat.
            "chat_capable": role_name != "embedding",
            # HOS-065C: the operational context window chosen for this role
            # from real benchmark data (latency/VRAM measured at several
            # candidates — see CHANGELOG), not the model's architectural
            # maximum. 8192 only if a role predates that pass.
            "context_window": int(role.get("num_ctx", 8192)),
        }
    return models


PREDEFINED_MODELS: dict[str, dict[str, Any]] = _build_predefined_models()
