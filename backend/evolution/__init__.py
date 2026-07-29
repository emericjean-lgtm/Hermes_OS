"""Self Evolution & Continuous Improvement Engine for Hermes OS (HOS-058)."""

from .evolution_analyzer import EvolutionAnalyzer
from .evolution_engine import EvolutionEngine
from .evolution_models import (
    EVOLUTION_EVENTS,
    EvolutionExperiment,
    EvolutionProposal,
    EvolutionReport,
    EvolutionStatus,
    EvolutionType,
    OptimizationPattern,
    RiskLevel,
    SystemMetrics,
)
from .evolution_scheduler import EvolutionScheduler
from .evolution_simulator import EvolutionSimulator
from .evolution_validator import EvolutionValidator, ValidationVerdict
from .improvement_detector import ImprovementDetector

__all__ = [
    "EvolutionAnalyzer",
    "EvolutionEngine",
    "EvolutionExperiment",
    "EvolutionProposal",
    "EvolutionReport",
    "EvolutionScheduler",
    "EvolutionSimulator",
    "EvolutionStatus",
    "EvolutionType",
    "EvolutionValidator",
    "ImprovementDetector",
    "OptimizationPattern",
    "RiskLevel",
    "SystemMetrics",
    "ValidationVerdict",
    "EVOLUTION_EVENTS",
]
