"""KTransformers optimizer — auto-select backend, quantization, layers (HOS-052)."""

from __future__ import annotations

from backend.runtime.ktransformers.kt_models import (
    KTBackend,
    KTFallbackReason,
    KTOptimizationResult,
    KTQuantization,
)


class KTOptimizer:
    """Automatic optimization engine for KTransformers.

    Determines the optimal backend, quantization level, VRAM/CPU layers split,
    and context size based on available hardware resources.

    Decision factors:
    1. VRAM available → can we fit the model?
    2. RAM available → fallback if VRAM insufficient
    3. Backend availability → ROCm > CUDA > CPU
    4. Task type → coding prefers Q5/Q6, chat prefers Q4 for speed
    5. Context needs → more context = more VRAM
    """

    # Typical model size multipliers by quantization
    _QUANT_SIZE_FACTORS: dict[KTQuantization, float] = {
        KTQuantization.Q2_K: 0.40,
        KTQuantization.Q3_K: 0.50,
        KTQuantization.Q4_K_M: 0.55,
        KTQuantization.Q5_K_M: 0.65,
        KTQuantization.Q6_K: 0.75,
        KTQuantization.Q8_0: 0.90,
        KTQuantization.F16: 1.00,
        KTQuantization.F32: 2.00,
        KTQuantization.IQ4_NL: 0.50,
    }

    # Approx VRAM overhead per 1K context tokens (for 7B models)
    _VRAM_PER_1K_CONTEXT_GB: float = 0.25

    def __init__(self):
        self._available_backends: list[KTBackend] = [
            KTBackend.ROCM,
            KTBackend.CUDA,
            KTBackend.CPU,
        ]
        self._vram_total_gb: float = 16.0
        self._vram_free_gb: float = 12.0
        self._ram_total_gb: float = 32.0
        self._ram_free_gb: float = 24.0

    # ── Configuration ─────────────────────────────────

    def set_hardware(
        self,
        vram_total: float = 16.0,
        vram_free: float = 12.0,
        ram_total: float = 32.0,
        ram_free: float = 24.0,
        backends: list[KTBackend] | None = None,
    ) -> None:
        """Configure available hardware resources."""
        self._vram_total_gb = vram_total
        self._vram_free_gb = vram_free
        self._ram_total_gb = ram_total
        self._ram_free_gb = ram_free
        if backends is not None:
            self._available_backends = backends

    # ── Optimization ──────────────────────────────────

    def optimize(
        self,
        model_params: str,  # e.g. "7B", "13B", "70B"
        task_type: str = "chat",
        desired_context: int = 4096,
        prefer_speed: bool = True,
    ) -> KTOptimizationResult:
        """Run the optimization pipeline and return recommendations.

        Args:
            model_params: Model size like "7B", "13B"
            task_type: "chat", "coding", "reasoning", "extraction"
            desired_context: Desired context window size
            prefer_speed: If True, prefer Q4 for speed; if False, prefer Q6/Q8 for quality
        """
        base_size_gb = self._estimate_base_size(model_params)

        # Pick quantization
        if task_type in ("coding", "reasoning"):
            quant = KTQuantization.Q5_K_M if self._vram_free_gb > base_size_gb * 0.8 else KTQuantization.Q4_K_M
        elif prefer_speed:
            quant = KTQuantization.Q4_K_M
        else:
            quant = KTQuantization.Q6_K

        model_size = base_size_gb * self._QUANT_SIZE_FACTORS[quant]
        context_vram = (desired_context / 1000) * self._VRAM_PER_1K_CONTEXT_GB
        total_vram_needed = model_size + context_vram

        # Determine backend
        backend = self._available_backends[0] if self._available_backends else KTBackend.CPU
        can_fit_vram = total_vram_needed <= self._vram_free_gb
        can_fit_ram = total_vram_needed <= self._ram_free_gb

        fallback_needed = False
        fallback_reason = None
        n_gpu_layers = -1

        if not can_fit_vram and can_fit_ram:
            # Fallback: try hybrid (GPU + CPU offload)
            if KTBackend.ROCM in self._available_backends or KTBackend.CUDA in self._available_backends:
                backend = KTBackend.HYBRID
                fallback_needed = True
                fallback_reason = KTFallbackReason.VRAM_INSUFFICIENT
                vram_fittable_gb = min(model_size, self._vram_free_gb * 0.8)
                n_gpu_layers = max(1, int(32 * (vram_fittable_gb / model_size)))
            else:
                backend = KTBackend.CPU
                fallback_needed = True
                fallback_reason = KTFallbackReason.RAM_INSUFFICIENT
                n_gpu_layers = 0
        elif not can_fit_ram:
            backend = KTBackend.CPU
            fallback_needed = True
            fallback_reason = KTFallbackReason.RAM_INSUFFICIENT
            n_gpu_layers = 0

        # Score
        score = 100.0
        if fallback_needed:
            score -= 30
        if quant != KTQuantization.Q4_K_M:
            score -= 5
        score = max(0.0, score)

        explanation_parts = [f"Model ~{model_params} ({base_size_gb:.1f}GB base)"]
        if fallback_needed:
            explanation_parts.append(f"FALLBACK: {fallback_reason.value}")
        else:
            explanation_parts.append(f"Fits in VRAM ({self._vram_free_gb:.1f}GB free)")

        return KTOptimizationResult(
            model_id="",
            recommended_backend=backend,
            recommended_quantization=quant,
            recommended_n_gpu_layers=n_gpu_layers,
            recommended_context_size=desired_context,
            vram_available_gb=self._vram_free_gb,
            ram_available_gb=self._ram_free_gb,
            can_fit_vram=can_fit_vram,
            can_fit_ram=can_fit_ram,
            fallback_needed=fallback_needed,
            fallback_reason=fallback_reason,
            score=score,
            explanation=" | ".join(explanation_parts),
        )

    # ── Helpers ───────────────────────────────────────

    @staticmethod
    def _estimate_base_size(params: str) -> float:
        """Estimate base (F16) model size from param count string."""
        multipliers = {"B": 1.0, "M": 0.001}
        for suffix, mult in multipliers.items():
            if params.upper().endswith(suffix):
                try:
                    num = float(params.upper().replace(suffix, ""))
                    # Each param = 2 bytes in F16
                    return (num * mult * 2.0)
                except ValueError:
                    pass
        # Default: assume 7B
        return 14.0

    def get_capabilities(self) -> dict:
        """Get optimizer hardware capabilities."""
        return {
            "vram_total_gb": self._vram_total_gb,
            "vram_free_gb": self._vram_free_gb,
            "ram_total_gb": self._ram_total_gb,
            "ram_free_gb": self._ram_free_gb,
            "available_backends": [b.value for b in self._available_backends],
        }
