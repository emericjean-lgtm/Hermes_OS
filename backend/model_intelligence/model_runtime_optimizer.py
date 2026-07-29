"""Model-Runtime Co-Optimizer for Hermes OS (HOS-065).

Analyzes model + runtime + hardware combinations to select
the optimal configuration for each task.
"""

from __future__ import annotations

from typing import Any

from .model_intelligence_models import (
    ModelProfile,
    Quantization,
    RuntimeBackend,
    TaskContext,
)


class RuntimeOptimization:
    """Represents a complete model+runtime+hardware optimization decision."""

    def __init__(self, model_id: str, runtime: RuntimeBackend,
                 quantization: Quantization, score: float,
                 estimated_vram_mb: int, estimated_tps: float,
                 reason: str):
        self.model_id = model_id
        self.runtime = runtime
        self.quantization = quantization
        self.score = score
        self.estimated_vram_mb = estimated_vram_mb
        self.estimated_tps = estimated_tps
        self.reason = reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "runtime": self.runtime.value,
            "quantization": self.quantization.value,
            "score": round(self.score, 3),
            "estimated_vram_mb": self.estimated_vram_mb,
            "estimated_tps": round(self.estimated_tps, 1),
            "reason": self.reason,
        }


class ModelRuntimeOptimizer:
    """Optimizes model + runtime + hardware combinations."""

    def __init__(self) -> None:
        self._optimizations: list[RuntimeOptimization] = []
        self._max_history = 200

    def optimize(self, profile: ModelProfile, task: TaskContext,
                 system_vram_mb: int = 8192, has_gpu: bool = True) -> list[RuntimeOptimization]:
        """Find all viable model+runtime+quantization combinations, ranked by score."""
        optimizations = []

        for runtime in profile.available_backends:
            for quantization in self._get_viable_quantizations(profile, runtime):
                vram_estimate = self._estimate_vram(profile, quantization, runtime)
                if vram_estimate > system_vram_mb:
                    continue
                if not has_gpu and runtime in (RuntimeBackend.KTRANSFORMERS, RuntimeBackend.VLLM):
                    continue

                score = self._compute_optimization_score(profile, quantization, runtime, task)
                tps = self._estimate_tps(profile, quantization, runtime)
                reason = self._generate_optimization_reason(profile, quantization, runtime, vram_estimate)

                opt = RuntimeOptimization(
                    model_id=profile.model_id,
                    runtime=runtime,
                    quantization=quantization,
                    score=score,
                    estimated_vram_mb=vram_estimate,
                    estimated_tps=tps,
                    reason=reason,
                )
                optimizations.append(opt)

        optimizations.sort(key=lambda o: -o.score)
        self._optimizations.extend(optimizations)
        if len(self._optimizations) > self._max_history:
            self._optimizations = self._optimizations[-self._max_history:]

        return optimizations

    def get_best(self, profile: ModelProfile, task: TaskContext,
                  system_vram_mb: int = 8192, has_gpu: bool = True
                  ) -> RuntimeOptimization | None:
        optimizations = self.optimize(profile, task, system_vram_mb, has_gpu)
        return optimizations[0] if optimizations else None

    def get_optimization_history(self, limit: int = 20) -> list[dict[str, Any]]:
        return [o.to_dict() for o in self._optimizations[-limit:]]

    def _get_viable_quantizations(self, profile: ModelProfile,
                                   runtime: RuntimeBackend) -> list[Quantization]:
        if runtime == RuntimeBackend.OLLAMA:
            return [Quantization.Q4_K_M, Quantization.Q5_K_M, Quantization.Q8_0]
        if runtime == RuntimeBackend.KTRANSFORMERS:
            return [Quantization.Q4_0, Quantization.Q4_K_M, Quantization.Q8_0]
        if runtime == RuntimeBackend.LLAMACPP:
            return [Quantization.Q4_0, Quantization.Q4_K_M, Quantization.Q5_K_M, Quantization.Q8_0]
        if runtime == RuntimeBackend.TRANSFORMERS:
            return [Quantization.F16]
        return [Quantization.Q4_K_M]

    def _estimate_vram(self, profile: ModelProfile, quant: Quantization,
                        runtime: RuntimeBackend) -> int:
        base_vram = profile.vram_required_mb
        quant_mult = {
            Quantization.Q4_0: 0.4,
            Quantization.Q4_K_M: 0.45,
            Quantization.Q5_K_M: 0.55,
            Quantization.Q8_0: 0.7,
            Quantization.F16: 0.95,
            Quantization.NONE: 1.0,
        }.get(quant, 0.5)

        runtime_overhead = {
            RuntimeBackend.OLLAMA: 1.0,
            RuntimeBackend.KTRANSFORMERS: 0.85,
            RuntimeBackend.LLAMACPP: 0.9,
            RuntimeBackend.TRANSFORMERS: 1.3,
            RuntimeBackend.VLLM: 1.2,
        }.get(runtime, 1.0)

        return int(base_vram * quant_mult * runtime_overhead)

    def _estimate_tps(self, profile: ModelProfile, quant: Quantization,
                       runtime: RuntimeBackend) -> float:
        base_tps = profile.tokens_per_second
        quant_speed = {
            Quantization.Q4_0: 1.3,
            Quantization.Q4_K_M: 1.2,
            Quantization.Q5_K_M: 1.0,
            Quantization.Q8_0: 0.8,
            Quantization.F16: 0.5,
        }.get(quant, 1.0)

        runtime_speed = {
            RuntimeBackend.OLLAMA: 1.0,
            RuntimeBackend.KTRANSFORMERS: 1.4,
            RuntimeBackend.LLAMACPP: 0.9,
            RuntimeBackend.TRANSFORMERS: 0.6,
            RuntimeBackend.VLLM: 1.5,
        }.get(runtime, 1.0)

        return base_tps * quant_speed * runtime_speed

    def _compute_optimization_score(self, profile: ModelProfile,
                                     quant: Quantization,
                                     runtime: RuntimeBackend,
                                     task: TaskContext) -> float:
        speed_score = self._estimate_tps(profile, quant, runtime) / 100.0
        vram_efficiency = 1.0 - (self._estimate_vram(profile, quant, runtime) / 80000.0)
        task_fit = profile.task_scores.get(task.task_type.value, 0.5)
        return speed_score * 0.3 + vram_efficiency * 0.3 + task_fit * 0.4

    def _generate_optimization_reason(self, profile: ModelProfile,
                                       quant: Quantization,
                                       runtime: RuntimeBackend,
                                       vram: int) -> str:
        if runtime == RuntimeBackend.KTRANSFORMERS:
            return f"KTransformers: {quant.value} quant, ~{vram}MB VRAM (GPU offload available)"
        if runtime == RuntimeBackend.OLLAMA:
            return f"Ollama: {quant.value} quant, ~{vram}MB VRAM (easy setup)"
        if runtime == RuntimeBackend.VLLM:
            return f"vLLM: {quant.value} quant, ~{vram}MB VRAM (high throughput)"
        if runtime == RuntimeBackend.LLAMACPP:
            return f"llama.cpp: {quant.value} quant, ~{vram}MB VRAM (CPU+GPU hybrid)"
        return f"{runtime.value}: {quant.value} quant, ~{vram}MB VRAM"
