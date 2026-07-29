"""Compatibility Analyzer for the Discovery Engine (HOS-040).

Checks whether a model can run on the current hardware configuration.
"""

from __future__ import annotations

from typing import Callable, Optional

from backend.runtime.discovery.discovery_models import (
    CompatibilityReport,
    ModelInfo,
    Quantization,
)


class CompatibilityAnalyzer:
    """Analyzes hardware compatibility for discovered models."""

    # Approximate VRAM multipliers per quantization level (relative to FP16)
    _quant_multipliers: dict[Quantization, float] = {
        Quantization.FP16: 1.0,
        Quantization.Q8_0: 0.55,
        Quantization.Q6_K: 0.45,
        Quantization.Q5_K_M: 0.38,
        Quantization.Q4_K_M: 0.30,
        Quantization.Q3_K_M: 0.25,
        Quantization.Q2_K: 0.20,
        Quantization.UNKNOWN: 0.50,
    }

    # ROCm-supported architectures
    _rocm_architectures: set[str] = {
        "llama", "mistral", "mixtral", "gemma", "phi",
        "qwen", "qwen2", "qwen3", "deepseek", "command-r",
        "falcon", "starcoder", "codegemma", "llama3",
    }

    def __init__(
        self,
        get_gpu: Optional[Callable] = None,
    ) -> None:
        self._get_gpu = get_gpu or (lambda: None)

    def analyze(self, model: ModelInfo, vram_total: int = 0) -> CompatibilityReport:
        """Check if a model is compatible with the current hardware."""
        report = CompatibilityReport(
            model_name=model.name,
            vram_available_bytes=vram_total,
        )

        # 1. Estimate VRAM requirement
        multiplier = self._quant_multipliers.get(model.quantization, 0.5)
        report.vram_required_bytes = int(model.parameter_count_b * 1024**3 * multiplier)
        report.ram_required_bytes = report.vram_required_bytes * 2

        if vram_total > 0:
            report.ram_available_bytes = vram_total

        # 2. VRAM check
        if report.vram_required_bytes <= vram_total:
            report.compatible = True
        elif vram_total == 0:
            # Unknown GPU — mark as uncertain, assume compatible for now
            report.compatible = True
        else:
            report.issues.append(
                f"VRAM required ({_fmt_bytes(report.vram_required_bytes)}) "
                f"> available ({_fmt_bytes(vram_total)})"
            )

        # 3. ROCm architecture check
        arch_lower = model.architecture.lower()
        for supported in self._rocm_architectures:
            if supported in arch_lower:
                report.rocm_supported = True
                break

        if not report.rocm_supported and model.architecture:
            report.recommendations.append(
                f"Architecture '{model.architecture}' may not be ROCm-optimized"
            )

        # 4. Quantization compatibility
        if model.quantization in (Quantization.Q2_K, Quantization.Q3_K_M):
            report.recommendations.append(
                f"Quantization {model.quantization.value} may degrade quality significantly"
            )

        report.quantization_compatible = True  # Ollama handles quantization transparently

        # 5. Recommendations
        if not report.compatible and vram_total > 0:
            # Suggest lighter quantization
            for q, mult in sorted(self._quant_multipliers.items(), key=lambda x: x[1]):
                est = int(model.parameter_count_b * 1024**3 * mult)
                if est <= vram_total and q != Quantization.FP16:
                    report.recommendations.append(
                        f"Consider {q.value} quantization ({_fmt_bytes(est)} VRAM)"
                    )
                    break

        return report


def _fmt_bytes(b: int) -> str:
    if b >= 1024**3:
        return f"{b / 1024**3:.1f} GB"
    if b >= 1024**2:
        return f"{b / 1024**2:.0f} MB"
    return f"{b} B"
