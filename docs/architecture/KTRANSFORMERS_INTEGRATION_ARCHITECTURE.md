# KTransformers Integration Architecture — HOS-052C

> Final integration layer between Hermes OS and KTransformers.
> Date: 2026-07-29

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                   HERMES OS (Orchestration)              │
│                                                          │
│  Mission Planner → Agent Supervisor → Skill Distributor  │
│       ↓                    ↓                ↓            │
│  Runtime Orchestrator ← Policy Engine → Memory Manager   │
│       ↓                                                  │
│  ┌─────────────────────────────────────────────────┐    │
│  │         KTRuntime (Hermes ↔ KT Bridge)          │    │
│  │                                                 │    │
│  │  ┌─────────────────────────────────────────┐   │    │
│  │  │       HermesKTAdapter                   │   │    │
│  │  │  ┌──────────────────────┐               │   │    │
│  │  │  │  kt-kernel (real)    │ ← optional    │   │    │
│  │  │  │  KTransformersConfig │               │   │    │
│  │  │  │  KTModel             │               │   │    │
│  │  │  │  Optimizer           │               │   │    │
│  │  │  └──────────────────────┘               │   │    │
│  │  │  ┌──────────────────────┐               │   │    │
│  │  │  │  Simulated Fallback  │ ← CI/dev      │   │    │
│  │  │  └──────────────────────┘               │   │    │
│  │  └─────────────────────────────────────────┘   │    │
│  │                                                 │    │
│  │  Integrations:                                  │    │
│  │  ├── KTOchestratorIntegration (HOS-038)         │    │
│  │  ├── KTDiscoveryIntegration (HOS-040)           │    │
│  │  ├── KTBenchmarkIntegration (HOS-040)           │    │
│  │  ├── KTResourceIntegration (HOS-035)            │    │
│  │  └── KTEventBusBridge (HOS-034)                 │    │
│  └─────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│              KTRANSFORMERS (Inference)                    │
│                                                          │
│  Chunked Prefill  │  Heterogeneous Offloading            │
│  MoE Expert Placement  │  Async Forward Passes           │
│  Continuous Batching  │  Online Quantization             │
│  3-Layer Prefix Cache  │  NUMA-Aware Thread Pool         │
│                                                          │
│  Backends:                                               │
│  AMX_INT4/INT8 │ AVX512_FP8_BF16/VBMI/VNNI/BASE         │
│  AVX2_LLAMAFILE │ BLIS_AMD │ CUDA │ ROCm │ HYBRID       │
└──────────────────────────────────────────────────────────┘
```

---

## Design Principle: Adapters, Not Copies

KTransformers handles inference execution natively. Hermes OS should never duplicate:

- Chunked prefill (long context, memory control)
- Heterogeneous offloading (dynamic CPU↔GPU split)  
- MoE expert placement (hot experts→GPU, cold experts→CPU)
- Asynchronous forward passes (submit_forward/sync)
- Continuous batching (balance_serve)
- Online quantization (load_weights_from_tensors)
- 3-layer prefix cache (GPU-CPU-Disk)
- NUMA-aware thread pool

Instead, Hermes provides thin adapters that integrate KT with the broader operating system.

---

## File Structure

```
backend/runtime/ktransformers/
├── __init__.py                  # Public exports
├── kt_models.py                 # Enums + dataclasses (12 backends, 16 quantizations)
├── hermes_adapter.py            # Central bridge (real kt-kernel + fallback)
├── kt_runtime.py                # Orchestrator: register, load, infer, optimize
├── kt_routes.py                 # 13 REST endpoints
└── integrations/
    ├── __init__.py
    ├── orchestrator.py          # KTOchestratorIntegration (Runtime Orchestrator)
    ├── discovery.py             # KTDiscoveryIntegration + KTBenchmarkIntegration
    └── resources.py             # KTResourceIntegration + KTEventBusBridge
```

---

## Key Components

### HermesKTAdapter

Central bridge. Import kt-kernel optionally; fall back to simulation.

```python
adapter = HermesKTAdapter.get_instance()  # Singleton
adapter.load_model(info, config)          # → kt_kernel.load_model()
result = adapter.infer(info, request)     # → kt_kernel.infer()
opt = adapter.optimize(info, vram, ram)   # → KTransformersOptimizer
```

### KTRuntime

Orchestrator. Wires together discovery, resources, events, and the adapter.

```python
rt = KTRuntime()
rt.discover_and_register()               # → 10 models
rt.load_model("qwen3-coder-30b")         # → resource check → adapter.load
rt.infer(request)                         # → adapter.infer → events
rt.optimize("qwen3-coder-30b", "coding") # → adapter.optimize
```

### Integration Adapters

| Adapter | Hermes Module | Role |
|---|---|---|
| `KTOchestratorIntegration` | Runtime Orchestrator (HOS-038) | Present KT as runtime candidate |
| `KTDiscoveryIntegration` | Discovery Engine (HOS-040) | Auto-discover KT-compatible models |
| `KTBenchmarkIntegration` | Benchmark Engine (HOS-040) | Run benchmarks with real KT inference |
| `KTResourceIntegration` | Resource Manager (HOS-035) | Feed live VRAM/RAM into optimization |
| `KTEventBusBridge` | Event Bus (HOS-034) | Publish KT lifecycle events |

---

## Backends

All 12 real KTransformers CPU/GPU backends:

| Backend | CPU Required | Performance |
|---|---|---|
| `AMX_INT4` | Sapphire Rapids+ (2023+) | ⚡⚡⚡ Best |
| `AMX_INT8` | Sapphire Rapids+ (2023+) | ⚡⚡⚡ Excellent |
| `AVX512_FP8_BF16` | Ice Lake, Zen 4+ (2021+) | ⚡⚡⚡ Excellent |
| `AVX512_VBMI` | Ice Lake client (2019+) | ⚡⚡ Very good |
| `AVX512_VNNI` | Cascade Lake+ (2019+) | ⚡⚡ Very good |
| `AVX512_BASE` | Skylake-X+ (2017+) | ⚡⚡ Good |
| `AVX2_LLAMAFILE` | Haswell+ (2013+) | ⚡ Decent |
| `BLIS_AMD` | AMD Zen+ | ⚡ Decent |
| `CUDA` | NVIDIA SM 8.0+ | ⚡⚡ GPU |
| `ROCM` | AMD GPU | ⚡⚡ GPU AMD |
| `CPU` | Any | ⚡ Fallback |
| `HYBRID` | CPU + GPU | ⚡⚡ Mixed |

---

## Known Models

10 KT-compatible models in the discovery catalog:

| Model | Architecture | Total Params | Active Params | VRAM | RAM |
|---|---|---|---|---|---|
| DeepSeek-V3 | MoE | 671B | 37B | 480GB | 512GB |
| DeepSeek-R1 | MoE | 671B | 37B | 480GB | 512GB |
| DeepSeek-V4-Flash | MoE | 685B | 21B | 460GB | 500GB |
| Qwen3-MoE | MoE | 30B | 3B | 24GB | 32GB |
| Qwen3-Coder-30B | MoE | 30B | 3B | 24GB | 32GB |
| Qwen3-Next | MoE | 80B | 3B | 56GB | 64GB |
| GLM-5 | MoE | 130B | 13B | 88GB | 96GB |
| Mixtral 8×7B | MoE | 47B | 13B | 32GB | 40GB |
| Mixtral 8×22B | MoE | 141B | 39B | 96GB | 128GB |
| Kimi-K2 | MoE | 104B | 15B | 72GB | 80GB |

---

## REST API (13 endpoints)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/runtime/ktransformers/models` | List models (filters: status, backend, quantization) |
| `GET` | `/runtime/ktransformers/models/{id}` | Model detail |
| `POST` | `/runtime/ktransformers/discover` | Discover KT-compatible models |
| `POST` | `/runtime/ktransformers/load` | Load a model |
| `POST` | `/runtime/ktransformers/unload` | Unload a model |
| `POST` | `/runtime/ktransformers/infer` | Run inference |
| `POST` | `/runtime/ktransformers/benchmark` | Run benchmark |
| `POST` | `/runtime/ktransformers/optimize` | Get optimal config |
| `GET` | `/runtime/ktransformers/orchestrator/candidates` | Runtime candidates |
| `GET` | `/runtime/ktransformers/status` | Full status |
| `GET` | `/runtime/ktransformers/statistics` | Aggregated stats |
| `POST` | `/runtime/ktransformers/resources` | Update HW metrics |
| `GET` | `/runtime/ktransformers/events` | Recent events |

---

## Events (6 types)

Published on the Hermes Event Bus (HOS-034):

| Event | Trigger |
|---|---|
| `kt.model.discovered` | Model found by discovery |
| `kt.model.loaded` | Model successfully loaded |
| `kt.model.unloaded` | Model unloaded |
| `kt.inference.completed` | Inference finished |
| `kt.benchmark.completed` | Benchmark finished |
| `kt.fallback.triggered` | Insufficient resources / error |

---

## Example: Full Pipeline

```python
# 1. Discover models
rt = KTRuntime()
models = rt.discover_and_register()  # → 10 models from catalog

# 2. Feed hardware resources
rt.resources.update_resources({
    "vram_total_gb": 24.0, "vram_free_gb": 20.0,
    "ram_total_gb": 64.0, "ram_free_gb": 48.0,
})

# 3. Find a suitable model
model = next(m for m in models if m.name == "qwen3-coder-30b")

# 4. Optimize for coding task
opt = rt.optimize(model.id, "coding")
# → recommended_backend: HYBRID, MoE offloading: True, hot_experts: 2

# 5. Load
ok, msg = rt.load_model(model.id)  # → kt_kernel.load_model()
# Event: kt.model.loaded

# 6. Infer
result = rt.infer(KTInferenceRequest(model_id=model.id, prompt="Write auth middleware"))
# → 384 tokens, 45 t/s, VRAM: 3.8GB
# Event: kt.inference.completed

# 7. Check status
status = rt.get_status()
# models_total: 10, models_loaded: 1, adapter: {cpu_variant: "avx2_llamafile", ...}
```

---

## Limitations (due to KTransformers itself)

| Limitation | Impact | Mitigation |
|---|---|---|
| Requires Intel Sapphire Rapids+ for AMX backends | Most consumer CPUs use AVX2 fallback | Auto-detection selects best available |
| No native Windows support | Development on Linux/macOS only | CI fallback works everywhere |
| Model download not automated in kt-kernel | Models must be pre-downloaded | Hermes tracks status and checks availability |
| No streaming API in simulated fallback | Tests use batch inference only | Real kt-kernel supports streaming |
| ROCm support varies by GPU model | AMD GPU compatibility not universal | BLIS_AMD CPU backend as fallback |

---

## Tests: 73 (10 classes)

| Class | Tests |
|---|---|
| TestKTModels | 10 |
| TestHermesAdapter | 9 |
| TestDiscoveryIntegration | 8 |
| TestOrchestratorIntegration | 7 |
| TestResourceIntegration | 5 |
| TestEventBusBridge | 6 |
| TestKTRuntime | 14 |
| TestFullIntegration | 3 |
| TestThreadSafety | 3 |
| TestBackendDetection | 3 |
| TestKnownModels | 5 |
| **Total** | **73** |

---

## Conclusion

HOS-052C transforms the KTransformers integration from a proof-of-concept into a production-ready bridge. Hermes OS orchestrates; KTransformers executes. The adapter layer is thin, well-tested, and ready for real kt-kernel deployment.
