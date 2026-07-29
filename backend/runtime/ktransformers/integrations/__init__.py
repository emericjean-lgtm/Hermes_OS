"""KT integrations with Hermes OS subsystems — HOS-052C.

Adapters, not copies. Each integration creates a thin bridge between
Hermes OS orchestration and KTransformers execution.
"""

from backend.runtime.ktransformers.integrations.orchestrator import KTOchestratorIntegration
from backend.runtime.ktransformers.integrations.discovery import KTDiscoveryIntegration, KTBenchmarkIntegration
from backend.runtime.ktransformers.integrations.resources import KTResourceIntegration, KTEventBusBridge

__all__ = [
    "KTOchestratorIntegration",
    "KTDiscoveryIntegration",
    "KTBenchmarkIntegration",
    "KTResourceIntegration",
    "KTEventBusBridge",
]
