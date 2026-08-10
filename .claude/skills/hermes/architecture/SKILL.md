---
name: architecture
description: The real, audited map of Hermes OS's backend and frontend architecture — what each subsystem actually does, what's genuinely wired into the running app versus built-but-dormant versus dead code, and how the three main request flows (chat, Mission, Autonomous goal) really work. Use before touching any backend package or central frontend system, whenever you need to know whether something is actually live, or whenever a design doc's claim needs checking against real code.
---

# Hermes OS — Real Architecture

This is derived exclusively from reading the actual current code (backend packages, frontend source, the composition root, and the 27+ `docs/architecture/*.md` design docs cross-checked against what's really wired) — not from what any one document claims. Where a design doc and the real code disagree, the real code wins, and that disagreement is noted explicitly. Last grounded: 2026-08-10 (HOS-079). Re-verify anything load-bearing before relying on it if this skill is being read much later — this codebase changes fast and has a real history of docs drifting from reality.

## The one fact that reframes everything else

**Hermes OS's backend is two systems from different development eras, coexisting in the same tree, sharing only a few pieces of real infrastructure.**

- **"World A" — the walking skeleton.** Chat- and MCP-first. Code comments cite `cahier des charges §N`. A roster of 10 named agents (`backend/agents/*.py` — Hermes Prime, Hermes Swift, Atlas, Minerva, Hermes Scribe, Aegis, Kronos, Hermes Eyes, Veritas, Echo, from `config/agents.yaml`) built on `core.agent_registry.AgentRegistry` + `core.router.ModelRouter`, backed by SQLite (`memory/db.py`) + real ChromaDB (`memory/semantic.py`). Reachable via legacy REST (`api/routes/*.py`) and a real ~62-tool MCP server (`mcp_server/server.py`). **This is what actually answers `/chat` today.**
- **"World B" — "Hermes OS" proper.** Cockpit/mission-first. Code comments cite `HOS-0xx`. A DI composition root (`core/bootstrap/`) builds ~34 subsystems (mission planning/execution, autonomous goals, runtime orchestration, model intelligence, security/policy engines, evolution, skills, collaboration…) and mounts them under `/api/v1`.

They share: `AegisEngine` (the real security gate), `config/*.yaml`, `connectors/ollama_client.py`, and part of the SQLite file. Otherwise: **two agent registries, two memory systems, two skill concepts, two task trackers, three runtime layers, three governance layers, and five event-bus implementations** — each half genuinely real code, not one real and one fake. See `references/backend-map.md` for exactly which is which.

Why this matters for you: never assume a class named `AgentRegistry`, `MemoryManager`, or `Skill` is *the* one without checking which package it's in — the wrong guess is a live trap here, not a hypothetical one.

## The anchor systems, and their real status

| System (as commonly named) | Real package | Status |
|---|---|---|
| Mission Execution Engine / Mission Planner | `backend/mission/` (+ `backend/execution/`) | **Live, load-bearing.** Real LLM-driven DAG decomposition, real bounded-parallel execution. Shared by Missions and Autonomous goals — see below. |
| Agent Supervisor | `backend/agents/agent_supervisor.py` | Live DI service, real tracking (status/trust/metrics) kept in sync since HOS-070 — but its own `dispatch_node`/`execute_full_mission` methods are **not** the path a real mission takes (that's `mission.graph_executor.GraphExecutor`). |
| Runtime Orchestrator / Runtime Resource Manager | `backend/runtime/` (HOS-035–040) | Live, real, tested — VRAM/RAM tracking is genuinely fed real GPU data. But **advisory only**: consulted by simulation/what-if and by Autonomous's report for alternative-runtime *names*, never to actually route a real task's execution. |
| Model Router | `backend/core/router.py` (`ModelRouter`) | **Live, primary router for chat and for planning's LLM call.** Config-driven from `config/models.yaml`, deterministic (already-loaded model wins → fits VRAM → smallest → priority order). |
| Model Intelligence / adaptive routing | `backend/model_intelligence/` (`AdaptiveRouter`) | **Live, primary router for real Mission/Autonomous task execution** (a separate implementation from `ModelRouter`, doesn't call it). Also supplies the cloud-fallback model choice for chat. Real learned scoring, fed by real execution outcomes. |
| Memory / Knowledge Graph | `backend/memory/` | **Two real, disjoint systems** — see `references/backend-map.md` §Memory. The one Mission/Autonomous write to (`memory_manager.py`) is in-process dicts with a SHA-256-hash embedding stub, lost on restart. The one Echo actually uses (`db.py` + `semantic.py`/ChromaDB) is real and persistent. |
| Event Bus | Five real implementations, unified by `main.py`'s `lifespan()` forwarding them all into `core.event_hub.EventHub` (what the Cockpit's one WebSocket actually shows) | **Live.** See `references/backend-map.md` §Events for the full list — don't assume "the event bus" means one thing. |
| Governance / Security | Three real, non-equivalent layers — see `references/security-systems.md` | **Only Aegis (`backend/security/aegis_engine.py`) is the universal, always-consulted gate.** SecurityEngine and PolicyEngine are real but not unified into mission/task dispatch. |
| MCP / Tools | `backend/mcp_server/` (Hermes **as** an MCP server, inbound, real) + `backend/tools/` (Hermes **as** an MCP client + general tool platform, real) | **Live**, both directions — but they're opposite directions, don't conflate them. |
| Skills (Hermes's own internal skill system) | `backend/skills/` | **Real, complete machinery — structurally empty.** Zero `SkillDefinition`s exist anywhere in the repo; nothing has ever loaded. Distinct from `backend/memory/skill_library.py` (a *different*, populated "skill" concept used by Echo). Also distinct from **this** `.claude/skills/` directory, which is a Claude-Code-facing system with nothing to do with either. |
| Model Benchmark / Discovery | `backend/model_intelligence/benchmark_scheduler.py` | **Live and real** — runs an actual prompt through Ollama, reads real `eval_count`/`eval_duration`, not simulated. |
| Autonomous Mission Execution | `backend/autonomous/` (`AutonomousOrchestrator`) | **Live.** Runs on the *same* DAG planner/executor as a plain Mission (a deliberate dedup) — see the flow below. |

## The three real request flows

**Chat** (`POST /chat`, World A): `AgentRegistry.get(agent)` → `BaseAgent.respond_events()` → `ModelRouter.select_model()` → `OllamaClient.chat_events()` streams, with a bounded (3-round) real tool-calling loop if tools were offered. No Mission, no DAG, no DI container involved at all.

**Mission** (`POST /missions`, World B): `MissionPlanner.plan()` (real LLM-driven `TaskDecomposer`, or a rule-based/generic fallback the mission's own `decomposition_method` field records honestly) → `build_mission()` → `GraphExecutor.build_graph()`. `POST /missions/{id}/start` → Aegis gate (if project-bound) → `execute_step()` loop, each ready node dispatched through `ExecutionController` → the shared `MissionExecutor` (`TaskScheduler` → `AgentCoordinator` → `RealTaskExecutor`, which resolves the model via `AdaptiveRouter`, checks VRAM admission, calls Ollama for real) → result written back onto the node → on completion, episodic memory + evolution metrics recorded.

**Autonomous goal** (`POST /autonomous/goals`, World B): `AutonomousInterpreter.interpret()` → a two-tier Aegis check (path-based, then a risk-relevant `autonomous_goal_execute` check that can `BLOCK` or pause for `REVIEW`) → `_plan_via_dag()` calls the **same** `MissionPlanner.plan()`/`build_mission()` a Mission uses, registering the result under `/missions` too → `_execute_via_dag()` drives the **same** `execute_step()` loop. The extra pieces versus a plain Mission are goal interpretation, the extra risk-relevant security check, and an explicit learning-loop call after completion. This sharing was a deliberate fix (before it, Autonomous had its own disconnected pipeline) — don't assume Autonomous is a separate execution engine from Missions; it isn't anymore.

**Resume is genuinely limited on both**: pausing a Mission or an Autonomous goal only flips a status enum — it does not re-enter planning/execution from where it stopped. A fresh `/start` is what actually resumes stepping. This is a real, current, documented limitation, not something to assume works.

## Frontend architecture — the short version

Next.js 15 / React 19, one real route (`/dashboard`), everything else is client-side view switching via a single Zustand store (`useCockpitStore`). "Cockpit" (`CockpitShell`) is the permanent shell, not itself a Center. **22 real Centers** exist (confirmed, not aspirational) — Mission, Agent, Runtime, Memory, Skills, Tools, Governance, Dashboard, Assistant/Conversation, Models, Execution, Autonomous, Code Intelligence, Workspace, Security, Validation, Evolution, Health, Monitoring, Events, System, Deployment. All confirmed to call real backend hooks, not mock data (several carry in-code comments about having been "fabricated end to end" before a real remediation pass — the same honesty discipline as the backend). Dark theme only, no light mode. Full detail, the design-token system, and the two-tier component scaffold (and which is inconsistently adopted where) is in `references/frontend-map.md` and in [design-system](../../design-system/SKILL.md) / [ui-ux](../../ui-ux/SKILL.md).

## Known, real, current gaps (not hypothetical — from actual audits)

- No CI/CD exists at all (no `.github/workflows`, nothing).
- `deployment/` and `installer/` (Postgres/Redis/Docker) are disconnected from the real SQLite/ChromaDB dev stack — don't treat them as how the app actually runs.
- `§12` context-window auto-summarization (cahier des charges) remains entirely unimplemented.
- No authentication on any HTTP route — deliberate, single-user local-tool scope, not an oversight to "fix."
- `ToolPolicy`'s write-enforcement branch is a documented no-op outside the one place (Code Intelligence) that got a local patch.

## Where to go deeper

- `references/backend-map.md` — full package-by-package breakdown (every `backend/` directory: responsibility, real status, dependents) and the complete dead/live/duplicated inventory.
- `references/security-systems.md` — Aegis vs SecurityEngine vs PolicyEngine, disambiguated, with real call sites.
- `references/frontend-map.md` — full Centers inventory, design tokens, state management, API client layer, known dead frontend code.
- `references/timeline.md` — condensed HOS-000→HOS-079 history and the RC/R/P audit trajectory, for when you need to know *why* something is the way it is.
- The real, current `docs/architecture/*.md` and `CHANGELOG.md` for anything this summary doesn't cover, or to verify something before relying on it — this skill is a map, not a replacement for the territory.
