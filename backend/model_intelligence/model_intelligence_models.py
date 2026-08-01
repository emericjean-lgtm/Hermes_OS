"""Model Intelligence models for Hermes OS (HOS-065)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


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
        quality = self.task_scores.get("quality", 0.5)
        speed = min(1.0, self.tokens_per_second / 100.0) if self.tokens_per_second > 0 else 0.5
        reliability = self.success_rate
        efficiency = 1.0 - (self.vram_required_mb / 80000.0) if self.vram_required_mb > 0 else 0.5
        return (quality * 0.3 + speed * 0.2 + reliability * 0.3 + efficiency * 0.2 + self.benchmark_score * 0.1)


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
            "tags": [role_name, role.get("tier", "")],
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
