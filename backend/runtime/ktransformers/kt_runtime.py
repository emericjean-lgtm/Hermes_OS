"""KTransformers Runtime — HOS-052C final.

Orchestrates the Hermes ↔ KT bridge. All inference logic is delegated
to kt-kernel via HermesKTAdapter. This module handles only:
- Registration & lifecycle
- Optimization (delegated to KT)
- Event publishing
- Integration wiring
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Optional

from backend.runtime.ktransformers.hermes_adapter import HermesKTAdapter
from backend.runtime.ktransformers.integrations import (
    KTBenchmarkIntegration,
    KTDiscoveryIntegration,
    KTEventBusBridge,
    KTOchestratorIntegration,
    KTResourceIntegration,
)
from backend.runtime.ktransformers.kt_models import (
    KTBackend,
    KTBenchmarkResult,
    KTFallbackReason,
    KTInferenceRequest,
    KTInferenceResult,
    KTLoadConfig,
    KTModelConfig,
    KTModelInfo,
    KTModelStatus,
    KTOptimizationResult,
    KTQuantization,
)


class KTRuntime:
    """Central orchestrator for KTransformers within Hermes OS.

    Architecture:
      Hermes (plan, select, govern) → KTRuntime (route) → HermesKTAdapter → kt-kernel (execute)

    KT handles natively:
      • Chunked prefill • Heterogeneous offloading • MoE expert placement
      • Async forward passes • Continuous batching • Online quantization
      • 3-layer prefix cache • NUMA-aware thread pool
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._adapter = HermesKTAdapter.get_instance()
        self._models: dict[str, KTModelInfo] = {}
        self._configs: dict[str, KTModelConfig] = {}

        self.orchestrator = KTOchestratorIntegration()
        self.discovery = KTDiscoveryIntegration()
        self.benchmark = KTBenchmarkIntegration()
        self.resources = KTResourceIntegration()
        self.events = KTEventBusBridge()

    def register_model(self, info: KTModelInfo) -> KTModelInfo:
        with self._lock:
            if info.id in self._models:
                return self._models[info.id]
            info.status = KTModelStatus.UNREGISTERED
            self._models[info.id] = info
            self.events.model_discovered(info)
            return info

    def get_model(self, model_id: str) -> Optional[KTModelInfo]:
        return self._models.get(model_id)

    def list_models(
        self,
        status: Optional[KTModelStatus] = None,
        backend: Optional[KTBackend] = None,
        quantization: Optional[KTQuantization] = None,
    ) -> list[KTModelInfo]:
        models = list(self._models.values())
        if status:
            models = [m for m in models if m.status == status]
        if backend:
            models = [m for m in models if m.backend == backend]
        if quantization:
            models = [m for m in models if m.quantization == quantization]
        return sorted(models, key=lambda m: m.name)

    def discover_and_register(self) -> list[KTModelInfo]:
        discovered = self.discovery.discover()
        with self._lock:
            for info in discovered:
                self._models[info.id] = info
        return discovered

    def load_model(self, model_id: str, config: Optional[KTLoadConfig] = None) -> tuple[bool, str]:
        info = self._models.get(model_id)
        if info is None:
            return False, f"Model {model_id} not found"

        can_load, reason = self.resources.can_load(info)
        if not can_load:
            self.events.fallback_triggered(info, reason)
            return False, reason

        kt_config = KTModelConfig(
            backend=config.backend if config and config.backend else info.backend,
            quantization=config.quantization if config and config.quantization else info.quantization,
            context_length=config.context_length if config and config.context_length else info.context_length,
            n_gpu_layers=config.n_gpu_layers if config else 0,
            chunk_size=config.chunk_size if config else 4096,
            use_moe_offloading=config.use_moe_offloading if config and config.use_moe_offloading else info.supports_moe_offloading,
        )

        self._adapter.load_model(info, kt_config)
        with self._lock:
            self._configs[model_id] = kt_config
        self.events.model_loaded(info, kt_config.backend)
        return True, "OK"

    def unload_model(self, model_id: str) -> bool:
        info = self._models.get(model_id)
        if info is None:
            return False
        self._adapter.unload_model(info)
        with self._lock:
            self._configs.pop(model_id, None)
        self.events.model_unloaded(info)
        return True

    def infer(self, request: KTInferenceRequest) -> KTInferenceResult:
        info = self._models.get(request.model_id)
        if info is None:
            return KTInferenceResult(
                error=f"Model {request.model_id} not registered",
                fallback_reason=KTFallbackReason.BACKEND_UNAVAILABLE,
            )
        if info.status != KTModelStatus.LOADED:
            return KTInferenceResult(
                error=f"Model {info.name} not loaded (status: {info.status.value})",
                fallback_reason=KTFallbackReason.BACKEND_UNAVAILABLE,
            )

        result = self._adapter.infer(info, request)
        if not result.error:
            self.events.inference_completed(
                info, result.tokens_generated, result.tokens_per_second, result.backend_used
            )
        else:
            self.events.fallback_triggered(info, result.error)
        return result

    def optimize(self, model_id: str, task_type: str = "general") -> KTOptimizationResult:
        info = self._models.get(model_id)
        if info is None:
            return KTOptimizationResult(model_id=model_id, reasoning="Model not found")

        return self._adapter.optimize(
            info,
            vram_available=self.resources.get_vram_available(),
            ram_available=self.resources.get_ram_available(),
            task_type=task_type,
        )

    def run_benchmark(self, model_id: str, profile: str) -> KTBenchmarkResult:
        info = self._models.get(model_id)
        if info is None:
            return KTBenchmarkResult(model_id=model_id, profile=profile, success=False, error="Model not found")

        if info.status != KTModelStatus.LOADED:
            ok, _ = self.load_model(model_id)
            if not ok:
                return KTBenchmarkResult(model_id=model_id, profile=profile, success=False, error="Could not load for benchmark")

        result = self.benchmark.run_benchmark(info, profile)
        if result.success:
            self.events.benchmark_completed(info, profile, result.tokens_per_second)
        return result

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            models = list(self._models.values())
            loaded = sum(1 for m in models if m.status == KTModelStatus.LOADED)
            return {
                "adapter": self._adapter.get_cpu_info(),
                "models_total": len(models),
                "models_loaded": loaded,
                "models": [
                    {"id": m.id, "name": m.name, "status": m.status.value, "backend": m.backend.value,
                     "quantization": m.quantization.value, "vram_required_gb": m.vram_required_gb, "size_gb": m.size_gb}
                    for m in models
                ],
                "resources": self.resources.get_snapshot(),
                "events_count": len(self.events.get_history()),
            }

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            models = list(self._models.values())
            by_backend: dict[str, int] = {}
            by_status: dict[str, int] = {}
            for m in models:
                by_backend[m.backend.value] = by_backend.get(m.backend.value, 0) + 1
                by_status[m.status.value] = by_status.get(m.status.value, 0) + 1

            return {
                "total_models": len(models),
                "by_backend": by_backend,
                "by_status": by_status,
                "adapter_version": self._adapter.kt_version,
                "best_backend": self._adapter.best_backend.value,
                "has_cuda": self._adapter.has_cuda,
                "has_rocm": self._adapter.has_rocm,
                "is_real_kt": self._adapter.get_stats()["is_real"],
            }


_runtime_instance: Optional[KTRuntime] = None
_runtime_lock = threading.Lock()


def get_kt_runtime() -> KTRuntime:
    global _runtime_instance
    if _runtime_instance is None:
        with _runtime_lock:
            if _runtime_instance is None:
                _runtime_instance = KTRuntime()
    return _runtime_instance
