"""Model Intelligence models for Hermes OS (HOS-065)."""

from __future__ import annotations

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


PREDEFINED_MODELS: dict[str, dict[str, Any]] = {
    "qwen3-coder-30b": {
        "name": "Qwen3-Coder 30B",
        "architecture": "qwen",
        "parameters_b": 30.0,
        "vram_required_mb": 18000,
        "ram_required_mb": 24000,
        "context_window": 32768,
        "tokens_per_second": 25.0,
        "task_scores": {"code_generation": 0.95, "debug": 0.92, "analysis": 0.88},
        "available_backends": ["ollama", "ktransformers"],
        "tags": ["code", "reasoning"],
    },
    "deepseek-coder-16b": {
        "name": "DeepSeek Coder 16B",
        "architecture": "deepseek",
        "parameters_b": 16.0,
        "vram_required_mb": 10000,
        "ram_required_mb": 16000,
        "context_window": 16384,
        "tokens_per_second": 35.0,
        "task_scores": {"code_generation": 0.90, "debug": 0.85, "analysis": 0.80},
        "available_backends": ["ollama", "ktransformers", "llamacpp"],
        "tags": ["code"],
    },
    "llama3.2-3b": {
        "name": "Llama 3.2 3B",
        "architecture": "llama",
        "parameters_b": 3.0,
        "vram_required_mb": 2000,
        "ram_required_mb": 4000,
        "context_window": 8192,
        "tokens_per_second": 80.0,
        "task_scores": {"chat": 0.85, "analysis": 0.75, "code_generation": 0.70},
        "available_backends": ["ollama", "llamacpp", "transformers"],
        "tags": ["general", "lightweight"],
    },
    "codellama-7b": {
        "name": "CodeLlama 7B",
        "architecture": "codellama",
        "parameters_b": 7.0,
        "vram_required_mb": 5000,
        "ram_required_mb": 8000,
        "context_window": 16384,
        "tokens_per_second": 45.0,
        "task_scores": {"code_generation": 0.85, "debug": 0.80, "refactor": 0.82},
        "available_backends": ["ollama", "llamacpp", "ktransformers"],
        "tags": ["code"],
    },
    "mistral-7b": {
        "name": "Mistral 7B",
        "architecture": "mistral",
        "parameters_b": 7.0,
        "vram_required_mb": 5000,
        "ram_required_mb": 8000,
        "context_window": 32768,
        "tokens_per_second": 50.0,
        "task_scores": {"chat": 0.90, "analysis": 0.85, "reasoning": 0.82},
        "available_backends": ["ollama", "llamacpp", "transformers"],
        "tags": ["general", "reasoning"],
    },
    "phi3-14b": {
        "name": "Phi-3 14B",
        "architecture": "phi",
        "parameters_b": 14.0,
        "vram_required_mb": 8000,
        "ram_required_mb": 12000,
        "context_window": 131072,
        "tokens_per_second": 40.0,
        "task_scores": {"reasoning": 0.92, "analysis": 0.88, "code_generation": 0.82},
        "available_backends": ["ollama", "llamacpp"],
        "tags": ["reasoning", "long-context"],
    },
}
