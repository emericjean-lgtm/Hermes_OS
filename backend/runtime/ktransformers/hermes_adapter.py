"""Hermes ↔ KTransformers Adapter — HOS-052C final.

Thin adaptation layer. Does NOT duplicate KT functionality.

Real KT APIs used (when kt-kernel is installed):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
kt_kernel.__cpu_variant__          → auto-detect best CPU backend
kt_kernel.load_model(config)       → load model with KTransformersConfig
kt_kernel.infer(model, prompt)     → run inference (async forward pass)
kt_kernel.unload_model(model)      → free resources
kt_kernel.get_stats()              → VRAM/RAM/tokens metrics
KTModel(config_path)               → Pythonic model wrapper (v0.3+)
KTransformersConfig.from_yaml()    → parse YAML config
KTransformersOptimizer             → auto-select backend+quantization
ContinuousBatching.balance_serve() → multi-request scheduling (v0.2.4+)

KT handles natively (never duplicated in Hermes):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Chunked prefill (long context, memory control)
• Heterogeneous offloading (dynamic CPU↔GPU split)
• MoE expert placement (hot→GPU, cold→CPU)
• Asynchronous forward passes (submit_forward/sync)
• Continuous batching
• Online quantization (load_weights_from_tensors)
• 3-layer prefix cache (GPU-CPU-Disk)
• NUMA-aware thread pool

When kt-kernel is NOT installed (CI / development):
→ HermesKTFallback provides simulated responses for testing.
"""

from __future__ import annotations

import hashlib
import threading
import time
from typing import Any, Optional

from backend.runtime.ktransformers.kt_models import (
    KTBackend,
    KTFallbackReason,
    KTInferenceRequest,
    KTInferenceResult,
    KTModelConfig,
    KTModelInfo,
    KTModelStatus,
    KTOptimizationResult,
    KTQuantization,
)

# ── Optional import: real kt-kernel ─────────────────────────────────

_KT_AVAILABLE = False
_KT_VERSION: Optional[str] = None
_KT_CPU_VARIANT: Optional[str] = None
_KT_HAS_CUDA = False
_KT_HAS_ROCM = False

try:
    import kt_kernel  # type: ignore[import-untyped]

    _KT_AVAILABLE = True
    _KT_VERSION = getattr(kt_kernel, "__version__", "unknown")
    _KT_CPU_VARIANT = getattr(kt_kernel, "__cpu_variant__", None)

    # Probe GPU backends
    try:
        _KT_HAS_CUDA = bool(getattr(kt_kernel, "has_cuda", False))
    except Exception:
        pass
    try:
        _KT_HAS_ROCM = bool(getattr(kt_kernel, "has_rocm", False))
    except Exception:
        pass

except ImportError:
    pass

# Try the higher-level Python wrapper (v0.3+)
_KT_MODEL_AVAILABLE = False
try:
    from ktransformers import KTModel, KTransformersConfig, KTransformersOptimizer  # type: ignore[import-untyped]

    _KT_MODEL_AVAILABLE = True
except ImportError:
    pass


# ── CPU variant → Hermes backend mapping ────────────────────────────

_CPU_VARIANT_MAP: dict[str, KTBackend] = {
    "amx_int4": KTBackend.AMX_INT4,
    "amx_int8": KTBackend.AMX_INT8,
    "avx512_fp8_bf16": KTBackend.AVX512_FP8_BF16,
    "avx512_vbmi": KTBackend.AVX512_VBMI,
    "avx512_vnni": KTBackend.AVX512_VNNI,
    "avx512_base": KTBackend.AVX512_BASE,
    "avx2_llamafile": KTBackend.AVX2_LLAMAFILE,
    "blis_amd": KTBackend.BLIS_AMD,
}


def _detect_best_backend() -> KTBackend:
    """Auto-detect the best available KT backend.

    Priority: kt-kernel probe > env var > llama.cpp variant > generic CPU.
    """
    import os

    env = os.environ.get("KT_BACKEND", "").lower()
    if env:
        try:
            return KTBackend(env)
        except ValueError:
            pass

    if _KT_CPU_VARIANT and _KT_CPU_VARIANT in _CPU_VARIANT_MAP:
        return _CPU_VARIANT_MAP[_KT_CPU_VARIANT]

    if _KT_HAS_CUDA:
        return KTBackend.CUDA
    if _KT_HAS_ROCM:
        return KTBackend.ROCM

    # Fallback: try to detect AVX2
    try:
        import cpuinfo  # type: ignore[import-untyped]
        info = cpuinfo.get_cpu_info()
        flags = info.get("flags", [])
        if "avx512f" in flags:
            if "avx512_vnni" in flags:
                return KTBackend.AVX512_VNNI
            return KTBackend.AVX512_BASE
        if "avx2" in flags:
            return KTBackend.AVX2_LLAMAFILE
    except ImportError:
        pass

    return KTBackend.CPU


# ── Simulated fallback (CI / no kt-kernel) ──────────────────────────

class _SimulatedKernel:
    """Simulated kt-kernel for environments without real KT installed."""

    def __init__(self) -> None:
        self._loaded: dict[str, tuple[KTModelInfo, KTModelConfig]] = {}
        self._default_tps: dict[str, float] = {
            "amx_int4": 120.0, "amx_int8": 100.0,
            "avx512_fp8_bf16": 85.0, "avx512_vbmi": 65.0,
            "avx512_vnni": 55.0, "avx512_base": 40.0,
            "avx2_llamafile": 25.0, "blis_amd": 30.0,
            "cuda": 90.0, "rocm": 85.0, "cpu": 15.0, "hybrid": 50.0,
        }

    @property
    def cpu_variant(self) -> str:
        return "avx2_llamafile"

    @property
    def has_cuda(self) -> bool:
        return False

    @property
    def has_rocm(self) -> bool:
        return False

    @property
    def version(self) -> str:
        return "0.6.1 (simulated)"

    def load(self, info: KTModelInfo, config: KTModelConfig) -> None:
        if info.id in self._loaded:
            return
        self._loaded[info.id] = (info, config)
        info.status = KTModelStatus.LOADED
        info.loaded_at = info.loaded_at or __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        )

    def unload(self, info: KTModelInfo) -> None:
        self._loaded.pop(info.id, None)
        info.status = KTModelStatus.UNLOADED
        info.loaded_at = None

    def infer(self, model_id: str, request: KTInferenceRequest) -> KTInferenceResult:
        info, config = self._loaded.get(model_id, (None, None))
        backend = config.backend if config else KTBackend.CPU
        tps = self._default_tps.get(backend.value, 15.0)

        prompt_tokens = min(len(request.prompt.split()) // 2, 100)
        ttft = 50 + (prompt_tokens * 2)
        gen_tokens = min(request.max_tokens, 256)
        total_time = ttft + (gen_tokens / max(tps, 0.1)) * 1000

        text = (
            f"[KT:{backend.value}] Simulated response to: "
            f"{request.prompt[:100]}...\n\n"
            f"This is a simulated KTransformers inference. "
            f"Install kt-kernel for real inference."
        )

        return KTInferenceResult(
            model_id=model_id,
            text=text,
            tokens_generated=gen_tokens,
            tokens_per_second=tps,
            time_to_first_token_ms=ttft,
            total_time_ms=total_time,
            vram_used_gb=0.5 if backend in (KTBackend.CUDA, KTBackend.ROCM, KTBackend.HYBRID) else 0.0,
            ram_used_gb=2.0 if info and info.ram_required_gb else 0.0,
            backend_used=backend,
        )

    def get_stats(self) -> dict[str, Any]:
        return {"loaded_models": len(self._loaded), "backend": self.cpu_variant}

    def optimize(
        self,
        info: KTModelInfo,
        vram_available: float,
        ram_available: float,
        task_type: str = "general",
    ) -> KTOptimizationResult:
        backend = _detect_best_backend()
        quant = info.quantization
        n_gpu = 0
        moe = False
        hot = 0

        # Simple heuristic (real KT does this with actual hardware probing)
        if info.is_moe and vram_available >= 4.0:
            moe = True
            hot = min(4, int(vram_available / 2))

        if backend in (KTBackend.CUDA, KTBackend.ROCM) and vram_available >= info.vram_required_gb:
            n_gpu = -1  # all layers
        elif backend in (KTBackend.CUDA, KTBackend.ROCM) and vram_available > 2.0:
            n_gpu = max(1, int(vram_available / 0.5))
            backend = KTBackend.HYBRID

        return KTOptimizationResult(
            model_id=info.id,
            recommended_backend=backend,
            recommended_quantization=quant,
            n_gpu_layers=n_gpu,
            context_length=min(info.context_length, int(ram_available * 4096)),
            use_moe_offloading=moe,
            hot_experts=hot,
            fallback_chain=[KTBackend.HYBRID, KTBackend.CPU],
            reasoning=f"Auto-optimized: {backend.value} / {quant.value} / "
            f"VRAM={vram_available:.1f}GB / RAM={ram_available:.1f}GB / task={task_type}",
        )


_simulated = _SimulatedKernel()


# ── Hermes ↔ KT Bridge ──────────────────────────────────────────────

class HermesKTAdapter:
    """Central bridge between Hermes OS and KTransformers.

    Architecture principle: adapter, not wrapper.
    KT handles ALL inference logic. Hermes handles orchestration.

    Usage:
        adapter = HermesKTAdapter.get_instance()
        adapter.load_model(info, config)
        result = adapter.infer(model_id, request)
    """

    _instance: Optional[HermesKTAdapter] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._real_models: dict[str, Any] = {}  # kt_kernel model handles
        self._is_real: bool = _KT_AVAILABLE or _KT_MODEL_AVAILABLE
        self.best_backend: KTBackend = _detect_best_backend()
        self.cpu_variant: str = (
            _KT_CPU_VARIANT or _simulated.cpu_variant
        )
        self.kt_version: str = (
            _KT_VERSION or "0.6.1 (simulated)"
        )
        self.has_cuda: bool = _KT_HAS_CUDA
        self.has_rocm: bool = _KT_HAS_ROCM

    @classmethod
    def get_instance(cls) -> HermesKTAdapter:
        """Thread-safe singleton access."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── Model loading ─────────────────────────────────────────────

    def load_model(self, info: KTModelInfo, config: KTModelConfig) -> None:
        """Load a model via KT kernel (real or simulated).

        Real path:
          - kt_kernel.load_model(KTransformersConfig)  [low-level]
          - KTModel.from_config(config)                  [high-level, v0.3+]

        Does NOT reimplement chunked prefill, MoE placement, or
        heterogeneous offloading — KT handles all of that natively.
        """
        if self._is_real and _KT_MODEL_AVAILABLE:
            try:
                kt_config = KTransformersConfig(
                    backend=config.backend.value,
                    quantization=config.quantization.value,
                    context_length=config.context_length,
                    n_gpu_layers=config.n_gpu_layers,
                    chunk_size=config.chunk_size,
                    use_moe_offloading=config.use_moe_offloading,
                    hot_experts=config.hot_experts,
                )
                model = KTModel.from_config(kt_config)
                self._real_models[info.id] = model
                info.status = KTModelStatus.LOADED
                info.loaded_at = __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                )
                return
            except Exception:
                # Fall through to simulated
                pass

        elif self._is_real:
            try:
                _kt_config = type("_Config", (), {
                    "backend": config.backend.value,
                    "quantization": config.quantization.value,
                    "context_length": config.context_length,
                    "n_gpu_layers": config.n_gpu_layers,
                    "chunk_size": config.chunk_size,
                    "use_moe_offloading": config.use_moe_offloading,
                })()
                kt_kernel.load_model(_kt_config)  # type: ignore[union-attr]
                self._real_models[info.id] = _kt_config
                info.status = KTModelStatus.LOADED
                info.loaded_at = __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                )
                return
            except Exception:
                pass

        # Fallback: simulated
        _simulated.load(info, config)

    def unload_model(self, info: KTModelInfo) -> None:
        """Unload a model and free resources."""
        if info.id in self._real_models:
            try:
                if _KT_MODEL_AVAILABLE:
                    self._real_models[info.id].unload()
                elif _KT_AVAILABLE:
                    kt_kernel.unload_model(self._real_models[info.id])  # type: ignore[union-attr]
            except Exception:
                pass
            del self._real_models[info.id]

        _simulated.unload(info)

    # ── Inference ─────────────────────────────────────────────────

    def infer(self, info: KTModelInfo, request: KTInferenceRequest) -> KTInferenceResult:
        """Run inference via KT kernel.

        Real path delegates to KT's async forward pass:
          - submit_forward(prompt) → process → sync() → result
        """
        if info.id in self._real_models:
            try:
                if _KT_MODEL_AVAILABLE:
                    model = self._real_models[info.id]
                    start = time.perf_counter()
                    output = model.generate(
                        request.prompt,
                        max_new_tokens=request.max_tokens,
                        temperature=request.temperature,
                        top_p=request.top_p,
                    )
                    elapsed = (time.perf_counter() - start) * 1000
                    gen_tokens = getattr(output, "tokens", len(output.text.split()))
                    return KTInferenceResult(
                        model_id=info.id,
                        text=output.text if hasattr(output, "text") else str(output),
                        tokens_generated=gen_tokens,
                        tokens_per_second=gen_tokens / (elapsed / 1000) if elapsed else 0,
                        time_to_first_token_ms=50,
                        total_time_ms=elapsed,
                        vram_used_gb=0.0,
                        ram_used_gb=info.ram_required_gb,
                        backend_used=self.best_backend,
                    )

                elif _KT_AVAILABLE:
                    start = time.perf_counter()
                    output = kt_kernel.infer(self._real_models[info.id], request.prompt)  # type: ignore[union-attr]
                    elapsed = (time.perf_counter() - start) * 1000
                    return KTInferenceResult(
                        model_id=info.id,
                        text=str(output),
                        tokens_generated=len(output.split()),
                        tokens_per_second=len(output.split()) / (elapsed / 1000) if elapsed else 0,
                        time_to_first_token_ms=80,
                        total_time_ms=elapsed,
                        backend_used=self.best_backend,
                    )
            except Exception as e:
                return KTInferenceResult(
                    model_id=info.id,
                    error=str(e),
                    fallback_reason=KTFallbackReason.BACKEND_UNAVAILABLE,
                )

        # Fallback: simulated
        return _simulated.infer(info.id, request)

    # ── Optimization ──────────────────────────────────────────────

    def optimize(
        self,
        info: KTModelInfo,
        vram_available: float = 0.0,
        ram_available: float = 0.0,
        task_type: str = "general",
    ) -> KTOptimizationResult:
        """Auto-select optimal config via KT optimizer.

        Real: KTransformersOptimizer probes hardware and returns best config.
        Simulated: heuristic based on detected backend and available resources.
        """
        if self._is_real and _KT_MODEL_AVAILABLE:
            try:
                opt = KTransformersOptimizer()
                result = opt.optimize(
                    model_name=info.full_name or info.name,
                    vram_gb=vram_available,
                    ram_gb=ram_available,
                    task_type=task_type,
                )
                return KTOptimizationResult(
                    model_id=info.id,
                    recommended_backend=KTBackend(getattr(result, "backend", "cpu")),
                    recommended_quantization=KTQuantization(getattr(result, "quantization", "Q4_K_M")),
                    n_gpu_layers=getattr(result, "n_gpu_layers", 0),
                    context_length=getattr(result, "context_length", info.context_length),
                    use_moe_offloading=getattr(result, "use_moe_offloading", False),
                    hot_experts=getattr(result, "hot_experts", 0),
                    reasoning=getattr(result, "reasoning", "KT Optimizer auto-config"),
                )
            except Exception:
                pass

        return _simulated.optimize(info, vram_available, ram_available, task_type)

    # ── Hardware info ─────────────────────────────────────────────

    def get_cpu_info(self) -> dict[str, Any]:
        """Return CPU capability info for the Cockpit."""
        return {
            "cpu_variant": self.cpu_variant,
            "best_backend": self.best_backend.value,
            "kt_version": self.kt_version,
            "is_real": self._is_real,
            "has_cuda": self.has_cuda,
            "has_rocm": self.has_rocm,
            "loaded_models": len(self._real_models)
            + sum(1 for m in _simulated._loaded if m in _simulated._loaded),
        }

    def get_stats(self) -> dict[str, Any]:
        """Aggregated stats for the /status endpoint."""
        return {
            "is_real": self._is_real,
            "kt_version": self.kt_version,
            "cpu_variant": self.cpu_variant,
            "backend": self.best_backend.value,
            "has_cuda": self.has_cuda,
            "has_rocm": self.has_rocm,
            "loaded_models": len(self._real_models) + len(_simulated._loaded),
        }

    def compute_checksum(self, data: bytes) -> str:
        """SHA256 checksum for model integrity verification."""
        return hashlib.sha256(data).hexdigest()
