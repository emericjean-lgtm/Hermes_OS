"""Model Benchmark & Discovery Engine (HOS-040).

Discovers, benchmarks, and analyzes models from multiple sources.
Feeds the Runtime Intelligence Layer with performance data.
"""

from backend.runtime.discovery.discovery_models import (
    DiscoverySource,
    DiscoveryRun,
    ModelInfo,
    ModelStatus,
    BenchmarkProfile,
    BenchmarkResult,
    CompatibilityReport,
    Quantization,
)
from backend.runtime.discovery.model_registry import ModelRegistry
from backend.runtime.discovery.compatibility_analyzer import CompatibilityAnalyzer
from backend.runtime.discovery.benchmark_engine import BenchmarkEngine
from backend.runtime.discovery.discovery_engine import (
    DiscoveryEngine,
    DiscoveryConnector,
    OllamaConnector,
    HuggingFaceConnector,
)
from backend.runtime.discovery.cron_scheduler import CronScheduler, TaskType

__all__ = [
    "DiscoverySource",
    "DiscoveryRun",
    "ModelInfo",
    "ModelStatus",
    "BenchmarkProfile",
    "BenchmarkResult",
    "CompatibilityReport",
    "Quantization",
    "ModelRegistry",
    "CompatibilityAnalyzer",
    "BenchmarkEngine",
    "DiscoveryEngine",
    "DiscoveryConnector",
    "OllamaConnector",
    "HuggingFaceConnector",
    "CronScheduler",
    "TaskType",
]
