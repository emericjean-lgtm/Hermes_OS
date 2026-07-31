"""Resource Predictor for the Runtime Simulation Engine (HOS-039).

Estimates VRAM, RAM, duration, and load for a task on a given runtime.
"""

from __future__ import annotations

from typing import Callable, Optional

from backend.runtime.simulation.simulation_models import ResourcePrediction


class ResourcePredictor:
    """Predicts resource consumption for simulated task execution."""

    # Default model size estimates (VRAM in MB)
    _model_vram: dict[str, int] = {
        "qwen3:1.7b": 2048,
        "qwen3:4b": 5120,
        "qwen3:8b": 8192,
        "qwen3:14b": 14336,
        "qwen3-coder:30b": 30720,
        "deepseek-r1:14b": 14336,
        "deepseek-r1:32b": 32768,
        "gemma3:12b": 12288,
        "phi4:14b": 14336,
    }

    # Task multipliers for VRAM overhead
    _task_multipliers: dict[str, float] = {
        "chat": 1.0,
        "code": 1.3,
        "vision": 1.5,
        "reasoning": 1.8,
        "embedding": 0.5,
        "default": 1.0,
    }

    def __init__(
        self,
        get_model: Optional[Callable[[str], str]] = None,
        get_stats: Optional[Callable[[str], dict]] = None,
    ) -> None:
        self._get_model = get_model or (lambda rid: "")
        self._get_stats = get_stats or (lambda rid: {})

    def predict(
        self,
        runtime_id: str,
        task_type: str = "default",
        estimated_tokens: int = 500,
    ) -> ResourcePrediction:
        """Predict resources needed for a task on a runtime."""
        model = self._get_model(runtime_id) or "unknown"
        stats = self._get_stats(runtime_id) or {}

        # Base VRAM from model size
        base_vram = self._model_vram.get(model, 8192)

        # Task overhead
        multiplier = self._task_multipliers.get(task_type, 1.0)
        vram = int(base_vram * multiplier)

        # RAM estimate: ~2x VRAM for overhead
        ram = vram * 2

        # Duration estimate based on tokens and latency stats
        avg_latency = stats.get("avg_duration_ms", 200.0)
        estimated_duration = avg_latency * (estimated_tokens / 100)

        # Expected load
        expected_load = min(95.0, (vram / (16 * 1024)) * 100)

        return ResourcePrediction(
            vram_mb=vram,
            ram_mb=ram,
            estimated_duration_ms=round(estimated_duration, 2),
            expected_load_pct=round(expected_load, 1),
            concurrent_capacity=max(1, int((16 * 1024) / max(vram, 1))),
        )
