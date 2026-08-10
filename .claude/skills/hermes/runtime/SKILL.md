---
name: runtime
description: Hermes OS's real runtime constraints and conventions for anything touching Ollama, models, GPU/VRAM, agent execution, or the model routing system. Use before changing config/models.yaml, adding a model-dependent feature, debugging a model/inference issue, or touching backend/core/router.py or backend/model_intelligence/.
---

# Hermes OS — Runtime

Hermes OS runs real local models on real, specific, constrained consumer hardware — this isn't a cloud deployment with elastic capacity, and treating it like one (assuming a model "should" fit, or that VRAM is generous) is the most common category of mistake here.

## The real hardware, and a real environment surprise

Target: AMD RX 6800, 16GB GDDR6 VRAM (~17.16GB usable at Q4 quantization per this project's own measured budget), i5-13500 (6P+8E, 20 threads), 32GB DDR5 RAM, ROCm/HIP.

**The cahier des charges recommends Ubuntu 24.04 as primary target — but real development and validation has actually happened on Windows 11**, with WSL2 present but stopped. `rocm-smi` is confirmed unavailable on this machine entirely (not just "not installed" — a real, confirmed environment fact) — GPU telemetry comes from the Windows registry (`HardwareInformation.qwMemorySize`) and Ollama's own `/api/ps`/`/api/tags`, not ROCm tooling. Don't assume `rocm-smi` is available when writing GPU-monitoring code or debugging steps for this environment.

GPU temperature thresholds (cahier des charges §21): 85°C alert, 90°C critical (suggest pause).

## Config is the source of truth — `config/models.yaml`

One Ollama tag per role (currently 12: swift, standard, orchestrator, code, code_agentic, reasoning, reasoning_escalation, vision, security, embedding, double_check, advanced_analysis), each with real, dated `vram_gb`/`num_ctx` figures — the file's own comments distinguish a real on-device measurement from an extrapolation, and flag which roles are tight against the VRAM budget. **Never hardcode a model tag anywhere else** — resolve through the router. This project has direct, recent evidence (HOS-079) of what happens otherwise: a routine model swap surfaced four separate hardcoded-tag sites outside this file, each silently wrong the moment the config changed.

`always_loaded: true` pins a model in VRAM (`keep_alive: -1`) instead of letting it expire — currently `swift` and `embedding`, chosen because they're the fast/cheap roles hit on nearly every request. A third always-loaded model would eat headroom this budget doesn't have; don't add one without re-checking the real combined VRAM cost first.

## Two real routers — know which one you're touching

- **`backend/core/router.py`** (`ModelRouter`) — static, deterministic, config-driven. Used for chat (`BaseAgent`) and for the mission planner's own LLM decomposition call. Selection order: already-loaded model wins regardless of tier → first candidate that fits reported available VRAM → smallest candidate if nothing fits (flagged as an expected-offload downgrade) → priority order if no VRAM info at all.
- **`backend/model_intelligence/`** (`AdaptiveRouter`) — a separate, learned/scored implementation, does **not** call `ModelRouter`. Used for real Mission/Autonomous task execution, and for the cloud-fallback model choice in chat. Fed by real execution outcomes (`ModelProfiler.update_performance()`), so its scoring genuinely improves from real usage, not just static config.

Don't assume changing one affects the other — they're independently reachable from different real code paths. See [hermes/architecture](../architecture/SKILL.md).

## Verify a model change on this real hardware before accepting it

This project's established practice, not optional: before changing `config/models.yaml`, actually pull the candidate model and check `ollama ps` for its real `PROCESSOR` column (e.g. `100% GPU` vs `18%/82% CPU/GPU`) with a real generation in flight — a split that spills onto CPU is a real, measurable latency regression, not a theoretical concern. This exact check caught a real regression during the most recent model refresh: a "newer" candidate model looked like a reasonable upgrade on paper but measured worse GPU residency than the model it would have replaced, and was rejected on that basis alone. "Newer" and "smaller" are not proof of "better" on this specific card — measure.

For anything needing real latency/throughput numbers (not just VRAM fit), `scripts/validation/bench_models.py` is the established harness — it enforces one model resident at a time, verifies VRAM is genuinely reclaimed between models, and reads all timing from Ollama's own response fields (`load_duration`, `eval_count`) rather than estimating.

## Cloud escalation — gated, local-first, not a default

OpenRouter is available as a second runtime, but strictly bounded: only free-tier (`:free`) models, only considered when no local model is viable or a task explicitly opts into escalation, and gated by Aegis's `cloud_inference` category (`min_autonomy_for_auto_allow: high` — the highest bar in the permission matrix, deliberately above most other categories including `web_search`'s `medium`). At the shipped default autonomy, cloud is unreachable regardless of whether an API key is present. Don't treat cloud availability as a fallback to reach for casually — it's deliberately the last resort, and the gate is there on purpose.

## Real tool-calling gotcha (found the hard way, worth knowing before touching this path)

Ollama's streaming `/api/chat` only includes `tool_calls` on the **final** streamed chunk, which also happens to carry `done: true`. Code that checks `done` and returns before reading that chunk's `message` field will silently drop every tool call the model ever makes — this was a real bug found by live-testing against a real model with a tools payload, not something a unit test with a mocked client would have caught. If you're touching `OllamaClient.chat_events()` or anything building a tool-calling loop on top of it, read `message` (thinking/content/tool_calls) *before* checking `done`, not after.

## Debugging a real Ollama/model issue

1. Confirm Ollama itself is reachable: `curl http://127.0.0.1:11434/api/tags`. An empty `{"models":[]}` with previously-working models means something external wiped the local model store — this has happened before on this machine.
2. If pulls fail with an error mentioning `id_ed25519` — Ollama's local pull-signing key, normally auto-generated at service startup — check whether `~/.ollama/id_ed25519` actually exists. It only regenerates when the service *starts*, not while already running; if the key (or the whole `.ollama` directory) was wiped while Ollama kept running, a full stop/restart of the Ollama process is what regenerates it, not just retrying the pull.
3. For a "the model gave a wrong/truncated answer" report, check `num_ctx` before assuming a model-quality issue — this project has a real, confirmed case where a too-small default context window silently truncated the *start* of prompts, and the fix was raising `num_ctx`, not switching models.
4. For "the response is slow," check `ollama ps`'s `PROCESSOR` column for CPU/GPU split before assuming a code-level performance bug — a model that doesn't fit VRAM will be slow for hardware reasons no code change fixes; see [performance-analysis](../../performance-analysis/SKILL.md) and [resource-analysis](../../resource-analysis/SKILL.md).

## The real agent roster (World A, `config/agents.yaml`)

Hermes Prime (orchestrator), Hermes Swift (fast routing/classification, always-on), Atlas (developer/code), Minerva (research/RAG), Hermes Scribe (writing), Aegis (security, always-on), Kronos (planning/tasks), Hermes Eyes (vision), Veritas (QA/review), Echo (memory/skills, always-on). Each maps to a role in `config/models.yaml` via `core.agent_registry.AgentRegistry`. See [hermes/architecture](../architecture/SKILL.md) for how this relates to the separate, DI-wired World-B execution path.
