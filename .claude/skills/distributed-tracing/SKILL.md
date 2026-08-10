---
name: distributed-tracing
description: Trace a request through Hermes OS's real chain (Mission/goal, Planner, Agent, Router, Model, Tool, Memory, Event) using the project's own existing event/audit infrastructure. Use when debugging a cross-component issue or verifying an end-to-end flow actually happened as expected — not for setting up new observability tooling.
---

# Distributed Tracing (Hermes OS's real infrastructure)

Hermes OS has no OpenTelemetry, Jaeger, or Zipkin dependency anywhere in the codebase — confirmed by checking `backend/requirements.txt` and the whole tree. **Don't introduce one.** This project has a stated, deliberate discipline of using what's already there over adding a new stack, and the existing event/audit infrastructure already does real, structured tracing for exactly the chain this skill is about — it's just not branded "distributed tracing."

## What actually traces a request today

- **`core.audit_log`** — every `/chat` call writes one `AuditEntry` per request (model, tier, duration, first-token latency, token count) — real per-request tracing for the chat path.
- **`config/security.yaml`-driven Aegis decisions** — every permission check (`AegisEngine.evaluate()`) is published to the World-A message bus (`core.message_bus.MessageBus`), giving a real trace of every gated action a request triggered.
- **The event bus family** (see [hermes/architecture](../hermes/architecture/references/backend-map.md)'s Events section) — `EventDispatcher` gives every DI-wired subsystem a shared `on_event(type, payload, severity)` call, forwarded into both `SystemEventBus` and `EventHub`. A mission or goal's real path through Planner → Agent → Router → Model → Tool → Memory is reconstructable from the sequence of events it publishes along the way — this is genuinely the closest thing to a trace this project has, and it's real, not aspirational.
- **`MissionReport`/`AutonomousReport`** — built directly from a mission/goal's own measured fields (`actual_duration_ms`, `result_summary`, real serving runtime per node) rather than a separate tracking system that could drift out of sync. This is the primary artifact for "what actually happened during this run."

## How to actually trace a real chain

1. **Identify the entry point** — a Mission id, a goal id, or a chat request. `GET /missions/{id}/report` or `GET /autonomous/goals/{id}` gives the structured, already-aggregated view first — check this before manually reconstructing anything from raw events.
2. **If the aggregated report doesn't answer the question**, go to the raw event stream: query `EventHub`/`SystemEventBus` for events in the relevant time window, or read the audit log for the specific request. Correlate by mission/goal/task id — these ids are real, threaded through the DAG execution (`MissionNode`, `TaskExecution`) and into the events each step publishes.
3. **For the model-routing decision specifically**, both `ModelRouter` and `AdaptiveRouter` (see [hermes/runtime](../hermes/runtime/SKILL.md)) return a decision object with a `reason` string explaining *why* that model was chosen (already-loaded / fits VRAM / smallest-fallback / etc.) — this is real, structured routing provenance, already present, not something to add.
4. **For a tool-calling chain**, `BaseAgent`'s bounded tool-loop yields real `tool_calls`/`tool_result` stream chunks — these are visible in the actual NDJSON response stream for a chat request, and (for Missions/Autonomous) in the task's real execution record.

## When you'd genuinely need something more

If a real, recurring need emerges for cross-process correlation that the existing event/audit infrastructure can't answer — not as a default assumption, only after confirming the existing infrastructure is actually insufficient for a specific real question — that's a [technical-spec-review](../technical-spec-review/SKILL.md)-worthy decision, not something to add unilaterally mid-task. If it does come up, prefer extending the existing correlation-id-based event pattern (already present in `runtime/events/event_models.py`) over introducing an entirely new tracing stack — this project already has five real event-bus implementations (see [hermes/architecture](../hermes/architecture/references/backend-map.md)); a sixth, OpenTelemetry-shaped one is very unlikely to be the right answer before the existing five are actually exhausted.
