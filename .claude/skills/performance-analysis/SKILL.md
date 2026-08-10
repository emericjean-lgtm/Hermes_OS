---
name: performance-analysis
description: Analyze CPU, RAM, GPU/VRAM, latency, I/O, concurrency, queue, cache, and model-call performance — only after a real problem or a measurable risk has actually been identified. Use when investigating a specific reported slowness, before optimizing something with real evidence it's a bottleneck, or when a change could plausibly affect a latency-sensitive path.
---

# Performance Analysis

Optimize only what's actually measured to be slow. A change made on a guess about performance, without measuring first, has a real chance of making the code worse (less readable, more complex) for a benefit that was never confirmed to exist. This applies with extra force in Hermes OS, which has an established, repeatedly-demonstrated discipline of measuring on real hardware rather than assuming — see [hermes/runtime](../hermes/runtime/SKILL.md) and [hermes/verification](../hermes/verification/SKILL.md).

## Before touching anything

Confirm there's a real problem: a reported slow path, a specific latency budget being missed, a resource ceiling being hit. If the concern is speculative ("this might be slow"), measure first — don't optimize on a guess. If measurement confirms it's fine, say so and stop; that's a valid, useful outcome of this skill, not a failure to find something to fix.

## What to measure, and how, in this codebase

- **CPU / RAM** — `psutil`-based real sampling is the established pattern here (see `backend/monitoring/system_monitor.py`, `scripts/validation/measure_mission.py`'s background sampling thread). Don't estimate from code inspection alone when a real number is one script away.
- **GPU / VRAM** — see [resource-analysis](../resource-analysis/SKILL.md) for the full detail; the short version is `ollama ps`'s real `PROCESSOR`/`SIZE` columns and Ollama's own `/api/ps` are the source of truth on this hardware, not an assumption from a model's parameter count.
- **Latency** — for model calls specifically, Ollama's own response fields (`load_duration`, `eval_count`, `eval_duration`, `prompt_eval_duration`) give real, precise numbers — this project explicitly rejects estimating these (a past version of the benchmark scheduler used `random.uniform()` and was found and replaced specifically because of that). For HTTP endpoints, wall-clock timing around the real call, not a theoretical complexity estimate.
- **I/O** — real file/DB/network operation timing, not assumed cost. SQLite and ChromaDB operations in this project are usually fast enough not to matter, but verify rather than assume for anything in a hot path (chat streaming, mission step dispatch).
- **Concurrency** — this project bounds parallelism deliberately (e.g. `mission_max_parallel_tasks`, chosen from real measured concurrent-model VRAM cost, not a generic default) — if investigating a concurrency-related slowdown or considering raising a bound, re-measure the real combined resource cost rather than assuming headroom exists.
- **Queues** — check for real backlog/wait-time evidence (a queue actually growing, a real wait observed) before assuming a queueing bottleneck.
- **Cache** — verify a cache is actually being hit at the rate assumed (log or count real hits/misses) before crediting or blaming it for a performance characteristic.
- **Model calls** — the single most expensive operation class in this system by far. Before optimizing anything else in a path that also makes a model call, confirm the model call itself isn't dominating the total time — it usually is.

## Real budgets that exist in this project

The cahier des charges (§22.1) states real, specific first-token latency budgets by tier (fast/turbo-tier under 1s, standard under 3s, heavier/quality-tier under 8s), plus memory search under 500ms and document indexing under 10s/doc. If investigating a latency complaint, check which tier/budget actually applies before concluding something is "too slow" — a heavier reasoning model taking several seconds is expected, not a bug, if it's within its own tier's real budget.

## Reporting a finding

State the real measured number, what it's being compared against (a stated budget, a previous measurement, a user report), and — only once the bottleneck is actually identified — a specific, targeted fix. Don't propose a general "optimize this area" without pointing at the specific measured cause. If the fix has a trade-off (more memory for less CPU, more complexity for less latency), state it plainly rather than presenting the change as a pure win.

## What NOT to do

- Don't add caching, batching, or async parallelism speculatively "because it's usually faster" — each adds real complexity and failure modes that need justifying against an actual measured problem.
- Don't micro-optimize a path that isn't actually hot — trace where time is really going first.
- Don't report a percentage improvement without the real before/after numbers behind it.
