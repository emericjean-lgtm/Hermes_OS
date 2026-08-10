---
name: resource-analysis
description: Analyze hardware and runtime resource constraints for Hermes OS — VRAM, RAM, CPU, GPU, local model concurrency, model-switch cost, and queue saturation. Use before adding a model-dependent feature, changing concurrency settings, or whenever a change could plausibly increase resource pressure on this deployment's real, fixed hardware budget.
---

# Resource Analysis

Hermes OS's own stated design principle (cahier des charges §7) is **"Économe en VRAM"** — never load a heavy model when a light one suffices — and this project runs on a real, fixed, unforgiving hardware budget, not elastic cloud capacity. "Resource-aware" here means measured against the actual card in the actual machine, not a generic assumption about what a modern GPU can do.

## The real budget

AMD RX 6800, 16GB GDDR6, ~17.16GB usable VRAM at Q4 quantization per this project's own measured figure (this already accounts for real overhead — don't re-derive a "theoretical" 16GB budget from the card's spec sheet alone). 32GB system RAM. `rocm-smi` is not available on this deployment's real environment (Windows, no WSL2 GPU passthrough currently) — GPU state comes from Ollama's own `/api/ps`/`/api/tags` and Windows-registry-reported VRAM, not ROCm tooling. See [hermes/runtime](../hermes/runtime/SKILL.md) for the full detail.

## What to check before adding VRAM/RAM pressure

- **Does the new/changed model actually fit?** Check `config/models.yaml`'s real, dated `vram_gb` figure for the role, and if you're proposing a new model, verify it on-device (`ollama ps`'s real `PROCESSOR` split during a real generation) before accepting it — see [hermes/runtime](../hermes/runtime/SKILL.md)'s established verify-before-commit practice, including the real example of a "newer" model rejected after measuring a real GPU-residency regression.
- **What's already resident?** `swift` and `embedding` are `always_loaded: true` (pinned via `keep_alive: -1`) — their VRAM cost is a permanent floor on top of whatever else is active, not a one-time cost. Any new always-loaded model needs to justify eating further into that shared headroom.
- **What's the realistic concurrent load?** This project's own established parallelism bounds (e.g. `mission_max_parallel_tasks`) were set from real measured combined VRAM cost of concurrent role models, not a generic default — if touching a concurrency setting, re-measure rather than assuming the old bound's margin still applies after your change.
- **Model-switch cost** — swapping the resident model has a real, measurable load-time cost (Ollama's own `load_duration`). A feature that causes frequent switching between large models will pay this cost repeatedly; consider whether the access pattern can favor reuse of an already-loaded model (this is exactly what `ModelRouter`'s "already-loaded wins" rule optimizes for — don't build something that fights it).
- **Queue/saturation** — if a change could cause several requests to want GPU-resident inference simultaneously, check what actually happens on contention (does it queue, does it force an eviction, does a request fail?) rather than assuming the system gracefully handles concurrent demand beyond the real single-card budget.

## CPU/RAM considerations beyond the GPU

Not everything is VRAM-bound — a model that partially or fully offloads to CPU (common for anything exceeding the VRAM budget) shifts real cost onto the 20-thread CPU and 32GB system RAM instead; this is usually a large latency regression, not a free fallback, and should be treated as a real finding worth flagging (see [hermes/runtime](../hermes/runtime/SKILL.md)'s note on `ollama ps`'s CPU/GPU split), not a silent acceptable outcome.

## Reporting

State the real, current resource cost (measured, with the actual command/output that produced the number — `ollama ps`, `/api/ps`, a real benchmark run), what budget or existing allocation it's being weighed against, and whether the change is safely within budget, requires a trade-off (which existing thing loses headroom), or doesn't fit at all on this hardware. Don't state a resource conclusion without a real measurement behind it — see [hermes/verification](../hermes/verification/SKILL.md).
