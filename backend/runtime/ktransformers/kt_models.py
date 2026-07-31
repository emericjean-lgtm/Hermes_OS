"""KTransformers models — HOS-052C final integration.

Maps directly to real kt-kernel APIs:
- kt_kernel.__cpu_variant__ → KTBackend auto-detection
- KTransformersConfig YAML → KTModelConfig
- InjectionConfig → MoE expert placement
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4


# ── Backends (matching real kt-kernel.__cpu_variant__) ──────────────

class KTBackend(str, Enum):
    """Real KTransformers CPU/GPU backends.

    kt-kernel probes CPU at import time and selects the best available:
    - AMX_INT4/INT8: Intel Sapphire Rapids+ (2023+) — best perf, quantized
    - AVX512FP8_BF16: Ice Lake, Zen 4+ (2021+) — FP8/BF16 native
    - AVX512_VBMI: Ice Lake client (2019+) — RAWINT4
    - AVX512_VNNI: Cascade Lake+ (2019+) — RAWINT4
    - AVX512_BASE: Skylake-X+ (2017+) — RAWINT4 with fallbacks
    - AVX2_LLAMAFILE: Haswell+ (2013+) — GGUF via llamafile
    - BLIS_AMD: AMD Zen+ — INT8 prefill/decode
    - CUDA: NVIDIA SM 8.0+ (Ampere+) — GPTQ
    - ROCM: AMD GPU — HIP
    """
    AMX_INT4 = "amx_int4"
    AMX_INT8 = "amx_int8"
    AVX512_FP8_BF16 = "avx512_fp8_bf16"
    AVX512_VBMI = "avx512_vbmi"
    AVX512_VNNI = "avx512_vnni"
    AVX512_BASE = "avx512_base"
    AVX2_LLAMAFILE = "avx2_llamafile"
    BLIS_AMD = "blis_amd"
    CUDA = "cuda"
    ROCM = "rocm"
    CPU = "cpu"          # generic fallback
    HYBRID = "hybrid"    # CPU+GPU heterogeneous


class KTQuantization(str, Enum):
    """Quantization formats supported by KTransformers.

    KT supports online quantization: load weights → quantize in memory.
    Formats vary by backend (AMX only supports INT4/INT8).
    """
    Q2_K = "Q2_K"
    Q3_K_S = "Q3_K_S"
    Q3_K_M = "Q3_K_M"
    Q4_0 = "Q4_0"
    Q4_K_S = "Q4_K_S"
    Q4_K_M = "Q4_K_M"
    Q5_0 = "Q5_0"
    Q5_K_S = "Q5_K_S"
    Q5_K_M = "Q5_K_M"
    Q6_K = "Q6_K"
    Q8_0 = "Q8_0"
    FP16 = "FP16"
    BF16 = "BF16"
    FP8 = "FP8"
    INT4 = "INT4"
    INT8 = "INT8"
    GPTQ = "GPTQ"
    RAWINT4 = "RAWINT4"


class KTModelStatus(str, Enum):
    UNREGISTERED = "unregistered"
    DOWNLOADING = "downloading"
    CACHED = "cached"
    LOADED = "loaded"
    FAILED = "failed"
    UNLOADED = "unloaded"


class KTFallbackReason(str, Enum):
    NONE = "none"
    VRAM_INSUFFICIENT = "vram_insufficient"
    RAM_INSUFFICIENT = "ram_insufficient"
    CPU_INCOMPATIBLE = "cpu_incompatible"
    BACKEND_UNAVAILABLE = "backend_unavailable"
    MODEL_CORRUPT = "model_corrupt"
    TIMEOUT = "timeout"


# ── Model Config (maps to KTransformersConfig YAML) ──────────────────

@dataclass
class KTModelConfig:
    """Maps to real KTransformersConfig YAML.

    Example YAML:
        backend: "amx_int4"
        quantization: "INT4"
        context_length: 131072
        n_gpu_layers: 28
        chunk_size: 8192
        use_moe_offloading: true
        hot_experts: 4
        thread_pool_size: 32
    """
    backend: KTBackend = KTBackend.CPU
    quantization: KTQuantization = KTQuantization.Q4_K_M
    context_length: int = 32768
    n_gpu_layers: int = 0
    chunk_size: int = 4096          # chunked prefill size
    use_moe_offloading: bool = False  # MoE: hot experts→GPU, cold→CPU
    hot_experts: int = 0            # number of experts kept on GPU
    thread_pool_size: int = 0       # 0 = auto-detect
    use_flash_attention: bool = True
    use_continuous_batching: bool = False  # v0.2.4+
    prefix_cache_layers: int = 3    # GPU-CPU-Disk


# ── Model Info (maps to KTModel) ──────────────────────────────────

@dataclass
class KTModelInfo:
    """Represents a model registered with KTransformers.

    Maps to the real KT model lifecycle:
    - register → download (checksum) → cache → load → infer
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    full_name: str = ""             # e.g. "deepseek-ai/DeepSeek-V3"
    architecture: str = ""          # e.g. "MoE", "dense"
    num_parameters: str = ""        # e.g. "671B" (total)
    active_parameters: str = ""     # e.g. "37B" (per-token, MoE)
    size_gb: float = 0.0            # model file size on disk
    quantization: KTQuantization = KTQuantization.Q4_K_M
    backend: KTBackend = KTBackend.CPU
    status: KTModelStatus = KTModelStatus.UNREGISTERED
    vram_required_gb: float = 0.0
    ram_required_gb: float = 0.0
    context_length: int = 32768
    supports_rocm: bool = False
    supports_cuda: bool = False
    supports_moe_offloading: bool = False
    checksum: str = ""
    source: str = ""                # "huggingface", "ollama", "local"
    download_url: str = ""
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    loaded_at: Optional[datetime] = None
    last_benchmark: Optional[datetime] = None

    @property
    def is_moe(self) -> bool:
        return self.architecture.lower() == "moe"


# ── Load Config ────────────────────────────────────────────────────

@dataclass
class KTLoadConfig:
    """Load-time configuration passed to kt-kernel."""
    model_id: str = ""
    backend: Optional[KTBackend] = None   # None = auto-detect
    quantization: Optional[KTQuantization] = None
    context_length: Optional[int] = None
    n_gpu_layers: int = 0
    chunk_size: int = 4096
    use_moe_offloading: bool = False
    hot_experts: int = 0
    use_flash_attention: bool = True
    preload: bool = False


# ── Inference Request / Result ─────────────────────────────────────

@dataclass
class KTInferenceRequest:
    id: str = field(default_factory=lambda: str(uuid4()))
    model_id: str = ""
    prompt: str = ""
    max_tokens: int = 2048
    temperature: float = 0.7
    top_p: float = 0.95
    stream: bool = False
    stop_tokens: list[str] = field(default_factory=list)


@dataclass
class KTInferenceResult:
    id: str = field(default_factory=lambda: str(uuid4()))
    model_id: str = ""
    text: str = ""
    tokens_generated: int = 0
    tokens_per_second: float = 0.0
    time_to_first_token_ms: float = 0.0
    total_time_ms: float = 0.0
    vram_used_gb: float = 0.0
    ram_used_gb: float = 0.0
    backend_used: KTBackend = KTBackend.CPU
    fallback_reason: KTFallbackReason = KTFallbackReason.NONE
    error: Optional[str] = None


# ── Optimization ───────────────────────────────────────────────────

@dataclass
class KTOptimizationResult:
    """Auto-selected optimal config based on hardware + task type."""
    model_id: str = ""
    recommended_backend: KTBackend = KTBackend.CPU
    recommended_quantization: KTQuantization = KTQuantization.Q4_K_M
    n_gpu_layers: int = 0
    context_length: int = 32768
    chunk_size: int = 4096
    use_moe_offloading: bool = False
    hot_experts: int = 0
    fallback_chain: list[KTBackend] = field(default_factory=list)
    reasoning: str = ""


# ── Benchmark ───────────────────────────────────────────────────────

@dataclass
class KTBenchmarkResult:
    id: str = field(default_factory=lambda: str(uuid4()))
    model_id: str = ""
    profile: str = ""               # coding, reasoning, general_chat, tool_use, long_context
    backend: KTBackend = KTBackend.CPU
    quantization: KTQuantization = KTQuantization.Q4_K_M
    tokens_per_second: float = 0.0
    time_to_first_token_ms: float = 0.0
    vram_peak_gb: float = 0.0
    ram_peak_gb: float = 0.0
    success: bool = True
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
