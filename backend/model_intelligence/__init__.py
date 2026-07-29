"""Model Intelligence package for Hermes OS (HOS-065)."""

from .adaptive_router import AdaptiveRouter
from .benchmark_scheduler import BenchmarkScheduler
from .model_intelligence_models import (
    BenchmarkResult,
    ModelArchitecture,
    ModelDecision,
    ModelPerformanceRecord,
    ModelProfile,
    PREDEFINED_MODELS,
    Quantization,
    RuntimeBackend,
    TaskContext,
    TaskType,
)
from .model_predictor import ModelPredictor
from .model_profiler import ModelProfiler
from .model_runtime_optimizer import ModelRuntimeOptimizer, RuntimeOptimization
from .performance_analyzer import PerformanceAnalyzer

__all__ = [
    "ModelProfiler",
    "PerformanceAnalyzer",
    "ModelPredictor",
    "AdaptiveRouter",
    "BenchmarkScheduler",
    "ModelRuntimeOptimizer",
    "RuntimeOptimization",
    "ModelProfile",
    "ModelDecision",
    "ModelPerformanceRecord",
    "BenchmarkResult",
    "TaskContext",
    "TaskType",
    "ModelArchitecture",
    "RuntimeBackend",
    "Quantization",
    "PREDEFINED_MODELS",
]
