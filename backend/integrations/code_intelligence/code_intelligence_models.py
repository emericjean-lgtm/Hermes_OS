"""Code Intelligence models (HOS-055D).

Shared data models for the intelligent routing layer between KlaatCode
and Oh My Pi. Defines task classification, provider selection, and
scoring structures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ── Enums ────────────────────────────────────────────────────

class CodeIntelligenceTaskType(str, Enum):
    """Task types the Code Intelligence layer can route."""
    CODE_ANALYSIS = "code_analysis"
    REFACTORING = "refactoring"
    DEBUGGING = "debugging"
    ARCHITECTURE_REVIEW = "architecture_review"
    CODE_GENERATION = "code_generation"
    TEST_GENERATION = "test_generation"
    OPTIMIZATION = "optimization"
    DIAGNOSTICS = "diagnostics"
    CODE_REVIEW = "code_review"
    DOCUMENTATION = "documentation"


class CodeProvider(str, Enum):
    """Available code intelligence providers."""
    KLATCODE = "klaatcode"
    OHMYPI = "ohmypi"
    HYBRID = "hybrid"  # Both providers sequentially


class SelectionStrategy(str, Enum):
    """How the router selects a provider."""
    SINGLE_BEST = "single_best"   # Highest-scoring provider only
    HYBRID_BOTH = "hybrid_both"   # Run both, merge results
    KLATCODE_ONLY = "klaatcode_only"
    OHMYPI_ONLY = "ohmypi_only"


class RouteReason(str, Enum):
    """Why a particular provider was chosen."""
    LSP_REQUIRED = "lsp_required"
    DAP_REQUIRED = "dap_required"
    AST_REQUIRED = "ast_required"
    EXECUTION_REQUIRED = "execution_required"
    PROJECT_ANALYSIS = "project_analysis"
    DIAGNOSTICS_NEEDED = "diagnostics_needed"
    COST_OPTIMAL = "cost_optimal"
    HIGHEST_HISTORICAL = "highest_historical"
    LANGUAGE_PREFERENCE = "language_preference"
    FALLBACK = "fallback"


# ── Dataclasses ──────────────────────────────────────────────

@dataclass
class ProviderScore:
    """Scoring result for a single provider."""
    provider: CodeProvider
    score: float  # 0.0 - 1.0
    factors: dict[str, float] = field(default_factory=dict)
    reasoning: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "provider": self.provider.value,
            "score": round(self.score, 4),
            "factors": {k: round(v, 4) for k, v in self.factors.items()},
            "reasoning": self.reasoning,
        }


@dataclass
class RoutingDecision:
    """Final routing decision from the Code Intelligence Router."""
    task_type: CodeIntelligenceTaskType
    selected_provider: CodeProvider
    strategy: SelectionStrategy
    primary_reason: RouteReason
    scores: list[ProviderScore] = field(default_factory=list)
    hybrid_order: list[CodeProvider] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    decided_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "task_type": self.task_type.value,
            "selected_provider": self.selected_provider.value,
            "strategy": self.strategy.value,
            "primary_reason": self.primary_reason.value,
            "scores": [s.to_dict() for s in self.scores],
            "hybrid_order": [p.value for p in self.hybrid_order],
            "metadata": self.metadata,
            "decided_at": self.decided_at.isoformat(),
        }


@dataclass
class CodeIntelligenceTask:
    """A task routed through the Code Intelligence layer."""
    task_id: str = ""
    task_type: CodeIntelligenceTaskType = CodeIntelligenceTaskType.CODE_ANALYSIS
    language: str = ""
    project_path: str = ""
    complexity: float = 0.5
    parameters: dict[str, Any] = field(default_factory=dict)
    requires_lsp: bool = False
    requires_dap: bool = False
    requires_ast: bool = False
    requires_execution: bool = False
    mission_id: str = ""
    node_id: str = ""
    agent_id: str = ""


@dataclass
class ProviderExecutionResult:
    """Result from executing a task with a specific provider."""
    provider: CodeProvider
    task_id: str = ""
    success: bool = False
    data: Any = None
    error: str = ""
    duration_ms: float = 0.0
    mcp_action: str = ""
    artifacts: list[str] = field(default_factory=list)


@dataclass
class HybridExecutionResult:
    """Combined result from a hybrid (KlaatCode + Oh My Pi) execution."""
    task_id: str = ""
    overall_success: bool = False
    klaatcode_result: ProviderExecutionResult | None = None
    ohmypi_result: ProviderExecutionResult | None = None
    merged_data: Any = None
    total_duration_ms: float = 0.0
    errors: list[str] = field(default_factory=list)


# ── Task-to-Provider mappings ────────────────────────────────

# Heuristic: which provider is best for which task type
TASK_PROVIDER_PREFERENCE: dict[CodeIntelligenceTaskType, list[CodeProvider]] = {
    CodeIntelligenceTaskType.CODE_ANALYSIS: [CodeProvider.KLATCODE, CodeProvider.OHMYPI],
    CodeIntelligenceTaskType.REFACTORING: [CodeProvider.OHMYPI, CodeProvider.KLATCODE],
    CodeIntelligenceTaskType.DEBUGGING: [CodeProvider.OHMYPI],
    CodeIntelligenceTaskType.ARCHITECTURE_REVIEW: [CodeProvider.KLATCODE],
    CodeIntelligenceTaskType.CODE_GENERATION: [CodeProvider.OHMYPI, CodeProvider.KLATCODE],
    CodeIntelligenceTaskType.TEST_GENERATION: [CodeProvider.KLATCODE, CodeProvider.OHMYPI],
    CodeIntelligenceTaskType.OPTIMIZATION: [CodeProvider.KLATCODE, CodeProvider.OHMYPI],
    CodeIntelligenceTaskType.DIAGNOSTICS: [CodeProvider.KLATCODE, CodeProvider.OHMYPI],
    CodeIntelligenceTaskType.CODE_REVIEW: [CodeProvider.KLATCODE, CodeProvider.OHMYPI],
    CodeIntelligenceTaskType.DOCUMENTATION: [CodeProvider.KLATCODE],
}
