"""KlaatCode Deep Integration (HOS-054D).

Adapters bridging KlaatCode analysis, diagnostics, and cost estimation
into the Hermes OS core subsystems:
- CodeGraphAdapter → Knowledge Graph (HOS-047)
- DiagnosticsAdapter → Validation Engine (HOS-050)
- CostGuardAdapter → Runtime Orchestrator (HOS-038)
"""

from .code_graph_adapter import CodeGraphAdapter, CodeEntity, CodeRelation, CodeRelationship
from .cost_guard_adapter import CostGuardAdapter, RuntimeRecommendation, TaskCostEstimate
from .diagnostics_adapter import (
    DiagnosticIssue,
    DiagnosticsAdapter,
    DiagnosticsReport,
    PatchValidationResult,
)

__all__ = [
    # Code Graph
    "CodeGraphAdapter",
    "CodeEntity",
    "CodeRelationship",
    "CodeRelation",
    # Cost Guard
    "CostGuardAdapter",
    "TaskCostEstimate",
    "RuntimeRecommendation",
    # Diagnostics
    "DiagnosticsAdapter",
    "DiagnosticIssue",
    "DiagnosticsReport",
    "PatchValidationResult",
]
