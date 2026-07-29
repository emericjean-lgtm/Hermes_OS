"""KTransformers Runtime Integration — HOS-052C.

Hermes OS ↔ KTransformers final integration layer.

Architecture:
  KT handles inference execution natively (chunked prefill, MoE placement,
  heterogeneous offloading, online quantization, etc.)
  Hermes handles orchestration (planning, selection, governance, memory).

Modules:
  hermes_adapter  — Bridge to real kt-kernel (optional import, CI fallback)
  kt_models       — Enums + dataclasses mapping to KT API types
  kt_runtime      — Central orchestrator: register, load, infer, optimize
  kt_routes       — 13 REST endpoints
  integrations/   — Thin adapters for Hermes subsystems:
    orchestrator  — KTOchestratorIntegration (Runtime Orchestrator HOS-038)
    discovery     — KTDiscoveryIntegration + KTBenchmarkIntegration (HOS-040)
    resources     — KTResourceIntegration + KTEventBusBridge (HOS-035/034)
"""

from backend.runtime.ktransformers.kt_models import (
    KTBackend,
    KTBenchmarkResult,
    KTFallbackReason,
    KTInferenceRequest,
    KTInferenceResult,
    KTLoadConfig,
    KTModelConfig,
    KTModelInfo,
    KTModelStatus,
    KTOptimizationResult,
    KTQuantization,
)
from backend.runtime.ktransformers.hermes_adapter import HermesKTAdapter
from backend.runtime.ktransformers.kt_runtime import KTRuntime, get_kt_runtime
from backend.runtime.ktransformers.kt_routes import router

__all__ = [
    # Models
    "KTBackend",
    "KTBenchmarkResult",
    "KTFallbackReason",
    "KTInferenceRequest",
    "KTInferenceResult",
    "KTLoadConfig",
    "KTModelConfig",
    "KTModelInfo",
    "KTModelStatus",
    "KTOptimizationResult",
    "KTQuantization",
    # Adapter
    "HermesKTAdapter",
    # Runtime
    "KTRuntime",
    "get_kt_runtime",
    # Router
    "router",
]
