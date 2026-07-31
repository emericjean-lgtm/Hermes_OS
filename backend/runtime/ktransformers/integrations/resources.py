"""KT ↔ Resource Manager & Event Bus integrations (HOS-035, HOS-034).

- KTResourceIntegration: feeds live HW info into KT optimization
- KTEventBusBridge: publishes KT events on the Hermes Event Bus
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any

from backend.runtime.ktransformers.hermes_adapter import HermesKTAdapter
from backend.runtime.ktransformers.kt_models import KTBackend, KTModelInfo


class KTResourceIntegration:
    """Bridge: Resource Manager (HOS-035) → KT optimization.

    Feeds live hardware metrics (VRAM, RAM, CPU load) into KT's
    optimizer so it can make informed backend/quantization decisions.
    """

    def __init__(self) -> None:
        self._adapter = HermesKTAdapter.get_instance()
        self._lock = threading.Lock()
        self._latest: dict[str, float] = {
            "vram_total_gb": 0.0,
            "vram_used_gb": 0.0,
            "vram_free_gb": 0.0,
            "ram_total_gb": 0.0,
            "ram_used_gb": 0.0,
            "ram_free_gb": 0.0,
        }

    def update_resources(self, metrics: dict[str, float]) -> None:
        """Receive live hardware metrics from the Resource Manager."""
        with self._lock:
            self._latest.update(metrics)

    def get_vram_available(self) -> float:
        return self._latest.get("vram_free_gb", 0.0)

    def get_ram_available(self) -> float:
        return self._latest.get("ram_free_gb", 0.0)

    def get_snapshot(self) -> dict[str, float]:
        with self._lock:
            return dict(self._latest)

    def can_load(self, info: KTModelInfo) -> tuple[bool, str]:
        """Check if this model can be loaded given current resources."""
        vram_free = self.get_vram_available()
        ram_free = self.get_ram_available()

        if info.vram_required_gb > 0 and vram_free < info.vram_required_gb:
            return False, (
                f"VRAM insufficient: need {info.vram_required_gb:.1f}GB, "
                f"have {vram_free:.1f}GB"
            )
        if info.ram_required_gb > 0 and ram_free < info.ram_required_gb:
            return False, (
                f"RAM insufficient: need {info.ram_required_gb:.1f}GB, "
                f"have {ram_free:.1f}GB"
            )
        return True, "OK"


class KTEventBusBridge:
    """Bridge: KTransformers → Hermes Event Bus (HOS-034).

    Publishes KT lifecycle events on the Hermes Event Bus for
    observability in the Cockpit.
    """

    EVENT_TYPES = [
        "kt.model.discovered",
        "kt.model.loaded",
        "kt.model.unloaded",
        "kt.inference.completed",
        "kt.benchmark.completed",
        "kt.fallback.triggered",
    ]

    def __init__(self) -> None:
        self._adapter = HermesKTAdapter.get_instance()
        self._history: deque[dict[str, Any]] = deque(maxlen=500)
        self._lock = threading.Lock()
        self._callbacks: list[Any] = []  # EventBus subscriber callbacks

    def subscribe(self, callback: Any) -> None:
        """Register an EventBus callback."""
        self._callbacks.append(callback)

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        """Publish a KT event on the Hermes Event Bus."""
        event = {
            "id": str(hash(f"{event_type}_{payload}")),
            "type": event_type,
            "source": "ktransformers",
            "severity": payload.get("severity", "info"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        with self._lock:
            self._history.append(event)
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                pass

    def model_discovered(self, info: KTModelInfo) -> None:
        self.publish("kt.model.discovered", {
            "model_id": info.id,
            "model_name": info.name,
            "backend": info.backend.value,
            "architecture": info.architecture,
        })

    def model_loaded(self, info: KTModelInfo, backend: KTBackend) -> None:
        self.publish("kt.model.loaded", {
            "model_id": info.id,
            "model_name": info.name,
            "backend": backend.value,
            "vram_required_gb": info.vram_required_gb,
        })

    def model_unloaded(self, info: KTModelInfo) -> None:
        self.publish("kt.model.unloaded", {
            "model_id": info.id,
            "model_name": info.name,
        })

    def inference_completed(
        self,
        info: KTModelInfo,
        tokens: int,
        tps: float,
        backend: KTBackend,
    ) -> None:
        self.publish("kt.inference.completed", {
            "model_id": info.id,
            "model_name": info.name,
            "tokens_generated": tokens,
            "tokens_per_second": tps,
            "backend": backend.value,
        })

    def benchmark_completed(self, info: KTModelInfo, profile: str, tps: float) -> None:
        self.publish("kt.benchmark.completed", {
            "model_id": info.id,
            "model_name": info.name,
            "profile": profile,
            "tokens_per_second": tps,
        })

    def fallback_triggered(self, info: KTModelInfo, reason: str) -> None:
        self.publish("kt.fallback.triggered", {
            "model_id": info.id,
            "model_name": info.name,
            "reason": reason,
            "severity": "warning",
        })

    def get_history(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._history)
