"""KTransformers model manager — registry, download, integrity (HOS-052)."""

from __future__ import annotations

import hashlib
import threading
from typing import Optional

from backend.runtime.ktransformers.kt_models import (
    KTBackend,
    KTModelInfo,
    KTModelStatus,
    KTQuantization,
)


class KTModelManager:
    """Thread-safe registry and lifecycle manager for KTransformers models.

    Handles model registration, download simulation, integrity verification,
    versioning, and querying by backend/quantization/status.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._models: dict[str, KTModelInfo] = {}

    # ── Registration ──────────────────────────────────

    def register(self, model: KTModelInfo) -> KTModelInfo:
        """Register a new model in the registry."""
        with self._lock:
            self._models[model.id] = model
            return model

    def get(self, model_id: str) -> Optional[KTModelInfo]:
        """Get a model by ID."""
        with self._lock:
            return self._models.get(model_id)

    def list_all(self) -> list[KTModelInfo]:
        """List all registered models."""
        with self._lock:
            return list(self._models.values())

    def list_by_status(self, status: KTModelStatus) -> list[KTModelInfo]:
        """List models by status."""
        with self._lock:
            return [m for m in self._models.values() if m.status == status]

    def list_by_backend(self, backend: KTBackend) -> list[KTModelInfo]:
        """List models compatible with a given backend."""
        with self._lock:
            return [m for m in self._models.values() if m.backend == backend]

    def list_by_quantization(self, q: KTQuantization) -> list[KTModelInfo]:
        """List models with a given quantization."""
        with self._lock:
            return [m for m in self._models.values() if m.quantization == q]

    def search(self, query: str) -> list[KTModelInfo]:
        """Simple search by name or tags."""
        q = query.lower()
        with self._lock:
            return [
                m for m in self._models.values()
                if q in m.name.lower() or any(q in t.lower() for t in m.tags)
            ]

    # ── Lifecycle ─────────────────────────────────────

    def update_status(self, model_id: str, status: KTModelStatus) -> bool:
        """Update a model's lifecycle status."""
        with self._lock:
            model = self._models.get(model_id)
            if model is None:
                return False
            model.status = status
            return True

    def remove(self, model_id: str) -> bool:
        """Remove a model from the registry."""
        with self._lock:
            return self._models.pop(model_id, None) is not None

    # ── Download (simulated) ──────────────────────────

    def simulate_download(self, model_id: str) -> bool:
        """Simulate downloading a model (marks DOWNLOADING then AVAILABLE)."""
        with self._lock:
            model = self._models.get(model_id)
            if model is None:
                return False
            model.status = KTModelStatus.DOWNLOADING
        # In real impl: download, verify checksum
        with self._lock:
            model.status = KTModelStatus.AVAILABLE
            return True

    # ── Integrity ─────────────────────────────────────

    @staticmethod
    def compute_checksum(path: str, size_bytes: int = 0) -> str:
        """Compute a simulated SHA256 checksum for a model file."""
        content = f"{path}:{size_bytes}".encode()
        return hashlib.sha256(content).hexdigest()

    def verify_integrity(self, model_id: str) -> bool:
        """Verify a model's integrity by checksum."""
        with self._lock:
            model = self._models.get(model_id)
            if model is None:
                return False
            if not model.checksum:
                return True  # No checksum to verify against
            expected = self.compute_checksum(model.path, int(model.size_gb * 1024**3))
            return expected == model.checksum

    # ── Statistics ────────────────────────────────────

    def count_by_status(self) -> dict[str, int]:
        """Count models by status."""
        with self._lock:
            counts: dict[str, int] = {}
            for m in self._models.values():
                key = m.status.value
                counts[key] = counts.get(key, 0) + 1
            return counts

    def total_models(self) -> int:
        """Total number of registered models."""
        with self._lock:
            return len(self._models)

    def total_size_gb(self) -> float:
        """Total size of all registered models in GB."""
        with self._lock:
            return sum(m.size_gb for m in self._models.values())
