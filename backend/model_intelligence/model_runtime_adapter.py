"""Runtime Orchestrator integration for Model Intelligence (HOS-065B).

Connects AdaptiveRouter to Runtime Orchestrator, Simulation Engine,
Resource Manager, and KTransformers for pre-execution simulation.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from .model_intelligence_models import ModelProfile, Quantization, RuntimeBackend, TaskContext
from .model_profiler import ModelProfiler
from .model_runtime_optimizer import ModelRuntimeOptimizer


@dataclass
class OptimizedExecutionPlan:
    """Detailed execution plan comparing model+runtime+hardware options."""

    model_id: str
    recommended_runtime: str
    recommended_quantization: str
    estimated_vram_mb: int
    estimated_ram_mb: int
    estimated_latency_ms: float
    estimated_tokens_per_second: float
    confidence: float
    risk_level: str  # low, medium, high
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    reasoning: str = ""


@dataclass
class SimulationComparison:
    """Comparison of multiple model+runtime+hardware combinations."""

    model_id: str
    combinations: list[dict[str, Any]] = field(default_factory=list)
    selected_index: int = 0


# Hardware system simulation data
DEFAULT_SYSTEM_SPECS = {
    "ram_gb": 32,
    "vram_mb": 16384,
    "cpu_cores": 8,
    "has_cuda": True,
    "has_rocm": False,
}


class ModelRuntimeAdapter:
    """Bridges Model Intelligence with Runtime Orchestrator."""

    def __init__(
        self,
        optimizer: ModelRuntimeOptimizer | None = None,
        profiler: ModelProfiler | None = None,
        system_info: dict[str, Any] | None = None,
    ) -> None:
        self._optimizer = optimizer or ModelRuntimeOptimizer()
        self._profiler = profiler or ModelProfiler()
        self._system_info = system_info or dict(DEFAULT_SYSTEM_SPECS)
        self._lock = threading.RLock()
        self._simulation_history: list[SimulationComparison] = []

    def update_system_info(self, info: dict[str, Any]) -> None:
        """Update system hardware info."""
        with self._lock:
            self._system_info.update(info)

    def simulate_execution(
        self,
        profile: ModelProfile,
        task: Any = None,
        system_info: dict[str, Any] | None = None,
    ) -> OptimizedExecutionPlan:
        """Simulate model execution and return optimized plan."""
        sys_info = system_info or self._system_info

        # Create a basic task context for optimization
        if task is None:
            task = TaskContext(
                max_vram_mb=sys_info.get("vram_mb", 16384),
            )

        # Use optimizer's optimize method
        system_vram = sys_info.get("vram_mb", 16384)
        has_gpu = sys_info.get("has_cuda", False) or sys_info.get("has_rocm", False)
        optimizations = self._optimizer.optimize(profile, task, system_vram, has_gpu)

        # Build alternatives
        alternatives = []
        vram_total = sys_info.get("vram_mb", 16384)

        for opt in optimizations[1:4]:
            risk = "low" if opt.estimated_vram_mb <= vram_total * 0.7 \
                else ("medium" if opt.estimated_vram_mb <= vram_total else "high")
            alternatives.append({
                "runtime": opt.runtime.value if hasattr(opt.runtime, "value") else str(opt.runtime),
                "quantization": opt.quantization.value if hasattr(opt.quantization, "value") else str(opt.quantization),
                "estimated_vram_mb": opt.estimated_vram_mb,
                "estimated_tokens_per_second": opt.estimated_tps,
                "risk_level": risk,
            })

        best = optimizations[0] if optimizations else None
        if best:
            est_vram = best.estimated_vram_mb
            risk = "low" if est_vram <= vram_total * 0.7 \
                else ("medium" if est_vram <= vram_total else "high")
            est_latency = 50000.0 / max(best.estimated_tps, 1)
        else:
            est_vram = profile.vram_required_mb
            risk = "high"
            est_latency = 0.0

        execution_plan = OptimizedExecutionPlan(
            model_id=profile.model_id,
            recommended_runtime=best.runtime.value if best else "ollama",
            recommended_quantization=best.quantization.value if best else "q4_k_m",
            estimated_vram_mb=est_vram,
            estimated_ram_mb=sys_info.get("ram_gb", 32) * 512,
            estimated_latency_ms=est_latency,
            estimated_tokens_per_second=best.estimated_tps if best else profile.tokens_per_second,
            confidence=best.score if best else 0.5,
            risk_level=risk,
            alternatives=alternatives,
            reasoning=best.reason if best else "No viable optimization found",
        )

        # Store in history
        comparison = SimulationComparison(
            model_id=profile.model_id,
            combinations=[{
                "runtime": execution_plan.recommended_runtime,
                "quantization": execution_plan.recommended_quantization,
                "vram_mb": execution_plan.estimated_vram_mb,
                "tps": execution_plan.estimated_tokens_per_second,
                "risk": execution_plan.risk_level,
            }] + alternatives,
            selected_index=0,
        )

        with self._lock:
            self._simulation_history.append(comparison)
            if len(self._simulation_history) > 500:
                self._simulation_history.pop(0)

        return execution_plan

    def compare_runtimes(
        self,
        profile: ModelProfile,
        runtimes: list[RuntimeBackend] | None = None,
    ) -> list[dict[str, Any]]:
        """Compare model performance across different runtimes."""
        if runtimes is None:
            runtimes = [RuntimeBackend.OLLAMA, RuntimeBackend.KTRANSFORMERS,
                        RuntimeBackend.VLLM, RuntimeBackend.LLAMACPP]

        results = []
        for runtime in runtimes:
            quants = self._optimizer._get_viable_quantizations(profile, runtime)
            quant = quants[0] if quants else Quantization.Q4_K_M
            vram = self._optimizer._estimate_vram(profile, quant, runtime)
            tps = self._optimizer._estimate_tps(profile, quant, runtime)

            vram_total = self._system_info.get("vram_mb", 16384)
            risk = "low" if vram <= vram_total * 0.7 \
                else ("medium" if vram <= vram_total else "high")

            results.append({
                "runtime": runtime.value if hasattr(runtime, "value") else str(runtime),
                "quantization": quant.value if hasattr(quant, "value") else str(quant),
                "estimated_vram_mb": vram,
                "estimated_tokens_per_second": tps,
                "risk_level": risk,
                "feasible": vram <= vram_total,
            })

        return sorted(results, key=lambda x: -x["estimated_tokens_per_second"])

    def get_best_configuration(
        self, profile: ModelProfile, context: Any = None
    ) -> dict[str, Any]:
        """Get the single best configuration for a model."""
        plan = self.simulate_execution(profile, context)
        return {
            "model_id": plan.model_id,
            "runtime": plan.recommended_runtime,
            "quantization": plan.recommended_quantization,
            "estimated_vram_mb": plan.estimated_vram_mb,
            "estimated_tokens_per_second": plan.estimated_tokens_per_second,
            "risk_level": plan.risk_level,
            "confidence": plan.confidence,
        }

    def get_stats(self) -> dict[str, Any]:
        """Get adapter statistics."""
        with self._lock:
            return {
                "total_simulations": len(self._simulation_history),
                "system_info": dict(self._system_info),
            }
