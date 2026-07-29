"""KTransformers loading engine — lazy, preload, warm cache (HOS-052)."""

from __future__ import annotations

import threading
import time
from typing import Optional

from backend.runtime.ktransformers.kt_models import (
    KTBackend,
    KTLoadConfig,
    KTModelInfo,
    KTModelStatus,
)


class KTLoader:
    """Intelligent model loader with lazy loading, preload, and auto-unload.

    Simulates model loading operations (no real KTransformers dependency).
    """

    def __init__(self, model_manager, cache_manager):
        self._model_manager = model_manager
        self._cache_manager = cache_manager
        self._lock = threading.RLock()
        self._loaded_models: dict[str, KTLoadConfig] = {}
        self._load_times: dict[str, float] = {}  # model_id -> epoch seconds
        self._preload_queue: list[str] = []

    # ── Load / Unload ─────────────────────────────────

    def load(self, config: KTLoadConfig) -> bool:
        """Load a model with the given configuration.

        Returns True if the model was successfully loaded or already loaded.
        """
        with self._lock:
            model = self._model_manager.get(config.model_id)
            if model is None:
                return False

            # Already loaded
            if config.model_id in self._loaded_models:
                return True

            # Mark loading
            self._model_manager.update_status(config.model_id, KTModelStatus.LOADED)
            self._loaded_models[config.model_id] = config
            self._load_times[config.model_id] = time.time()

            # Add to cache
            self._cache_manager.add(config.model_id, model.size_gb)
            return True

    def unload(self, model_id: str) -> bool:
        """Unload a model from memory."""
        with self._lock:
            if model_id not in self._loaded_models:
                return False
            del self._loaded_models[model_id]
            self._load_times.pop(model_id, None)
            self._model_manager.update_status(model_id, KTModelStatus.AVAILABLE)
            self._cache_manager.remove(model_id)
            return True

    def is_loaded(self, model_id: str) -> bool:
        """Check if a model is currently loaded."""
        with self._lock:
            return model_id in self._loaded_models

    def get_config(self, model_id: str) -> Optional[KTLoadConfig]:
        """Get the load config for a loaded model."""
        with self._lock:
            return self._loaded_models.get(model_id)

    # ── Lazy Loading ──────────────────────────────────

    def ensure_loaded(self, model_id: str, backend: KTBackend = KTBackend.ROCM) -> bool:
        """Load a model only if not already loaded (lazy)."""
        with self._lock:
            if model_id in self._loaded_models:
                return True
        config = KTLoadConfig(model_id=model_id, backend=backend, n_gpu_layers=-1)
        return self.load(config)

    # ── Preload ───────────────────────────────────────

    def preload(self, model_id: str, backend: KTBackend = KTBackend.ROCM) -> bool:
        """Preload a model into the queue for later use."""
        with self._lock:
            if model_id in self._preload_queue:
                return True
            model = self._model_manager.get(model_id)
            if model is None:
                return False
            self._preload_queue.append(model_id)
        return self.load(KTLoadConfig(model_id=model_id, backend=backend))

    def process_preload_queue(self) -> int:
        """Process pending preload requests. Returns count loaded."""
        count = 0
        with self._lock:
            queue = list(self._preload_queue)
            self._preload_queue.clear()
        for model_id in queue:
            if self.ensure_loaded(model_id):
                count += 1
        return count

    # ── Auto-unload ───────────────────────────────────

    def auto_unload_idle(self, max_idle_seconds: float = 300.0) -> list[str]:
        """Unload models that have been idle for too long."""
        now = time.time()
        unloaded: list[str] = []
        with self._lock:
            for model_id, loaded_at in list(self._load_times.items()):
                if now - loaded_at > max_idle_seconds:
                    self.unload(model_id)
                    unloaded.append(model_id)
        return unloaded

    def unload_all(self) -> int:
        """Unload all models. Returns count unloaded."""
        with self._lock:
            ids = list(self._loaded_models.keys())
        count = 0
        for mid in ids:
            if self.unload(mid):
                count += 1
        return count

    # ── Statistics ────────────────────────────────────

    def loaded_count(self) -> int:
        """Number of currently loaded models."""
        with self._lock:
            return len(self._loaded_models)

    def loaded_ids(self) -> list[str]:
        """IDs of currently loaded models."""
        with self._lock:
            return list(self._loaded_models.keys())
