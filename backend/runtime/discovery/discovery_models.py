"""Discovery models for the Model Benchmark & Discovery Engine (HOS-040)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4


class DiscoverySource(str, Enum):
    HUGGINGFACE = "huggingface"
    OLLAMA = "ollama"
    GITHUB = "github"
    ARTIFICIAL_ANALYSIS = "artificial_analysis"
    LIVEBENCH = "livebench"
    MANUAL = "manual"


class ModelStatus(str, Enum):
    DISCOVERED = "discovered"
    ANALYZED = "analyzed"
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    BENCHMARKED = "benchmarked"
    REGISTERED = "registered"
    DEPRECATED = "deprecated"


class BenchmarkProfile(str, Enum):
    CODING = "coding"
    REASONING = "reasoning"
    GENERAL_CHAT = "general_chat"
    TOOL_USE = "tool_use"
    LONG_CONTEXT = "long_context"


class Quantization(str, Enum):
    FP16 = "fp16"
    Q8_0 = "q8_0"
    Q6_K = "q6_k"
    Q5_K_M = "q5_k_m"
    Q4_K_M = "q4_k_m"
    Q3_K_M = "q3_k_m"
    Q2_K = "q2_k"
    UNKNOWN = "unknown"


@dataclass
class ModelInfo:
    """Discovered model metadata."""

    model_id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    provider: str = ""
    architecture: str = ""
    parameter_count_b: float = 0.0
    quantization: Quantization = Quantization.UNKNOWN
    size_bytes: int = 0
    source: DiscoverySource = DiscoverySource.MANUAL
    source_url: str = ""
    tags: list[str] = field(default_factory=list)
    status: ModelStatus = ModelStatus.DISCOVERED
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CompatibilityReport:
    """Analyzes whether a model can run on the current hardware."""

    model_name: str = ""
    compatible: bool = False
    vram_required_bytes: int = 0
    vram_available_bytes: int = 0
    ram_required_bytes: int = 0
    ram_available_bytes: int = 0
    rocm_supported: bool = False
    quantization_compatible: bool = False
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class BenchmarkResult:
    """Benchmark results for a model under a specific profile."""

    benchmark_id: str = field(default_factory=lambda: uuid4().hex)
    model_name: str = ""
    profile: BenchmarkProfile = BenchmarkProfile.GENERAL_CHAT
    # Speed metrics
    tokens_per_second: float = 0.0
    time_to_first_token_ms: float = 0.0
    total_duration_ms: float = 0.0
    # Resource metrics
    vram_peak_bytes: int = 0
    ram_peak_bytes: int = 0
    # Quality metrics
    success: bool = True
    stability_score: float = 0.0
    error_count: int = 0
    # Meta
    prompt_tokens: int = 0
    completion_tokens: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DiscoveryRun:
    """Result of a discovery scan."""

    run_id: str = field(default_factory=lambda: uuid4().hex)
    sources: list[DiscoverySource] = field(default_factory=list)
    models_found: int = 0
    new_models: int = 0
    models: list[ModelInfo] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
