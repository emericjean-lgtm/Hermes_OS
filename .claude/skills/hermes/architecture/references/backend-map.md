# Backend package map (full detail)

Grounded 2026-08-10 by direct code audit. "Live" means: appears in `backend/core/bootstrap/service_registry.py`'s `SERVICE_SPECS` and its factory/route_binder actually run at startup (`backend/main.py::create_app()` → `HermesBootstrap().build()`), or is a World A module reachable via the legacy routes/MCP server that `main.py` does mount. "Dead" means: confirmed by repo-wide search that nothing outside the package itself (and sometimes its own tests) imports it.

## The composition root

`backend/core/bootstrap/` is what decides live vs. dead:
- `service_registry.py` — `SERVICE_SPECS`: 34 declarative entries (key, factory, dependencies, route_binder, produced/consumed events), topologically built.
- `bootstrap.py` — `HermesBootstrap.build()` walks the specs, instantiates into a `DependencyContainer`, binds routes, validates the dependency graph, registers health checks.
- `dependency_container.py` — thread-safe, explicit key-based DI (no autowiring by type).
- `event_wiring.py` — `EventDispatcher`, the one `on_event()` callable every subsystem gets; fans out to both `SystemEventBus` and `EventHub`. Its allow-list is derived from real enums/dicts across the codebase, not hand-maintained.
- `registry_seeding.py` — seeds agents from `config/agents.yaml` (enabled-only) into `AgentSupervisor`, tools into `ToolRegistry`/`MCPRegistry`. Explicitly does **not** fabricate skills — zero `SkillDefinition`s exist, so the skill registry is seeded empty, honestly.
- `router_registry.py` — mounts every bootstrap router under `/api/v1`, and republishes the 22 legacy World-A routers there too (so the Cockpit only knows one base URL), splitting path-colliding ones into `/api/v1/legacy/*`.

## Package by package

- **`backend/agent/`** (singular) — **dead**. A third-generation, complete, tested mission/agent orchestration attempt (HOS-017–024). Only referenced by `backend/services/mission_control.py` and `backend/api/hos_routes.py` — neither of which `main.py` imports. Superseded by `backend/mission/` + `backend/agents/` + `backend/execution/`.
- **`backend/agents/`** (plural) — **live, the real one**. Two unrelated things share this name: (1) the chat-agent contract, `BaseAgent`/10 concrete agents from `config/agents.yaml`, instantiated by `core.agent_registry.AgentRegistry`; (2) mission-execution agent *tracking* — `agent_models.Agent`, `agent_registry.AgentRegistry` (same class name, unrelated class!), `AgentSupervisor`, `CapabilityMatcher`. Also: `agents/collaboration/` (`CollaborationEngine`, HOS-044 — real, DI-wired, real routes, but nothing in the real Mission/Autonomous path ever uses it); `agents/specialized/` (code_intelligence/klaatcode/ohmypi routing — real, DI-wired).
- **`backend/api/`** — `api/routes/*.py` (chat, tasks, memory, files, git, workflows, projects, skills, documents, snapshots, logs, ws, verification, verify, write, vision, classify, messages, research, security, system, evolution) is **live**, the real World-A handlers. `api/router.py` + `api/hos_routes.py` are **dead** (part of the `backend/agent/` cluster).
- **`backend/autonomous/`** — **live**. See the main SKILL.md's flow description; shares its DAG engine with `backend/mission/`.
- **`backend/config/`** — **dead**. `ConfigManager` (HOS-062, JSON-profile-based) — unrelated to and not to be confused with `backend/core/config.py` (the real one). Only consumer is the also-dead `backend/storage/`.
- **`backend/connectors/`** — **live, foundational**. `ollama_client.OllamaClient` is what every real inference call in both worlds ultimately goes through — retries only on connection errors, separates thinking/content/tool_calls/tool_result stream chunks. `openrouter_client.OpenRouterClient` is the cloud fallback, only constructed when `OPENROUTER_API_KEY` is set.
- **`backend/conversation/`** — **live but a third, disconnected LLM-response path**. `ConversationManager`/`ResponseGenerator` (HOS-064) calls `OllamaClient` directly, independent of both `/chat` (World A `BaseAgent`) and Mission/Autonomous execution.
- **`backend/core/`** — **live, foundational**. `core/config.py` (`Settings`, `get_settings()`/`load_models_config()`/`load_agents_config()`/`load_security_config()` — the real, universally-respected settings loader). `core/router.py` (`ModelRouter`). `core/agent_registry.py` (World A's agent builder — distinct from `agents/agent_registry.py`). `core/event_hub.py` (`EventHub`, the real-time WebSocket fan-out the Cockpit listens on). `core/message_bus.py` (World A's SQLite inter-agent trace, every Aegis check publishes here). `core/audit_log.py`, `core/snapshot_manager.py`.
- **`backend/documents/`** — **live, minor utility**. Text extraction (pdf/docx/plain/code) for the MCP server and `api/routes/documents.py`.
- **`backend/events/`** — **live**. `SystemEventBus` (HOS-025), one of the two sinks `EventDispatcher` forwards to.
- **`backend/evolution/`** — **live, real data**. `EvolutionEngine` (HOS-058) ingests real `SystemMetrics` from both Mission and Autonomous completions; production role today is detection/proposal generation, not unattended auto-apply.
- **`backend/execution/`** — **live, foundational to World B**. `MissionExecutor` (the real cross-cutting engine: `TaskScheduler`/`AgentCoordinator`/`ValidationEngine`/`FeedbackLoop`/`OptimizationEngine`), `ExecutionController` (thin lifecycle wrapper around the shared `MissionExecutor`), `RealTaskExecutor` (does the actual work — one chat completion per task; `assigned_tools` is currently only a text hint to the model, not a real tool-call invocation — a real, current, documented limitation).
- **`backend/explainability/`** — **live but unfed**. `DecisionExplainer` (HOS-064) is real, HTTP-callable, but confirmed by grep: nothing outside its own package ever calls `.explain()`.
- **`backend/integrations/`** — mostly **live**: `alexandrie/` (external doc-sync adapter, real, but stores with an embedding *stub*), `code_intelligence/`/`klaatcode/`/`ohmypi/` (real, DI-wired adapters). `hermes_agent/adapter.py` is **dead** (only the dead `mission_control.py` imports it).
- **`backend/logging/`** — **dead**. `production_logger.py` unreferenced anywhere.
- **`backend/mcp_server/`** — **live**. Hermes **as** an MCP server (inbound): ~62 real tool functions, each a thin wrapper around a World-A agent, mounted at `/mcp`. Built for external agent runtimes (e.g. NousResearch's "Hermes Agent") to drive Hermes.
- **`backend/memory/`** — **live but bifurcated** (see "Memory" below).
- **`backend/mission/`** — **live**. See main SKILL.md flow description.
- **`backend/model_intelligence/`** — **live**. `AdaptiveRouter` (see main SKILL.md) + `ModelProfiler`/`ModelPredictor`/`PerformanceAnalyzer`/`BenchmarkScheduler`/`ModelRuntimeOptimizer`.
- **`backend/monitoring/`** — **partially live**. `SystemMonitor` (HOS-062, real CPU/RAM/disk sampling) is DI-wired but has no dedicated routes of its own — only reachable via `/api/v1/system/statistics`. `gpu_monitor.py` is a real utility used directly (note: a *different* `GPUMonitor` class also exists at `runtime/resources/gpu_monitor.py`, used by the DI `resource_manager` — same name, two classes, don't conflate). `health_monitor.py`/`recovery_manager.py` are **dead**.
- **`backend/policy/`** — **live, partially wired**. See `security-systems.md`.
- **`backend/projects/`** — **live, World A infra**. `ProjectStore` (SQLite CRUD), explicitly "not an agent" — reached via a module-level singleton, not DI.
- **`backend/ral/`** — **live**. "Runtime Abstraction Layer" — real protocol + registry/factory + adapters, plus a genuinely durable SQLite event bus. Not what serves real chat/task inference (that's direct `OllamaClient` calls).
- **`backend/runtime/`** — **live, advisory-only**. See main SKILL.md's Runtime Orchestrator row. `runtime/ktransformers/` is real but inert unless the optional `kt-kernel` package is installed. `runtime/code_intelligence/ci_scorer.py` is an orphaned, unreferenced file (unrelated to `agents/specialized/code_intelligence/` despite the name).
- **`backend/sds/`** — **live**. "Surface Découplée Système" — the FastAPI-lifecycle glue holding the RAL's event bus/runtime registry as process singletons, served at `/api/hermes-os/*`. `main.py`'s own comment: it does not yet route real inference through this registry — that remains separate future work.
- **`backend/security/`** — **live**. See `security-systems.md`.
- **`backend/self_evolution/`** — **live, populated**. A small, explicitly-triggered pipeline (not auto-run) turning a completed World-A `Task` into a reusable `Skill` (in `memory/skill_library.py`'s SQLite table) — distinct from and unrelated to `backend/skills/`'s empty HOS-048 machinery, despite the identical word.
- **`backend/services/`** — **dead**. Just `mission_control.py`, part of the `backend/agent/` dead cluster.
- **`backend/skills/`** — **live machinery, structurally empty**. Real `SkillRegistry`/`SkillProfiler`/`SkillCache`/`SkillLoader`/`SkillSelector`/`SkillOrchestrator` (HOS-048), DI-wired with real routes — but zero `SkillDefinition`s exist anywhere in the repository. This is Hermes's *own* internal agent-skill system; it has nothing to do with this `.claude/skills/` directory.
- **`backend/storage/`** — **dead**. `backup_manager.py`/`database_manager.py`/`migration_manager.py`, unreferenced outside themselves and `tests/production/`.
- **`backend/tasks/`** — **live, World A**. `task_manager.Task` (Kronos's simple SQLite task) — unrelated to `mission.mission_models.MissionNode`/`execution.execution_models.TaskExecution` (World B's much richer task representations). Don't confuse the two "task" concepts.
- **`backend/tools/`** — **live**. Hermes **as** an MCP client + general tool platform (opposite direction from `mcp_server/`): `ToolRegistry`/`ToolExecutor`/`ToolSandbox`/`ToolPolicy`/`ToolRouter`, real connectors (browser/database/docker/filesystem/github/gitlab/rest_api/web_search).
- **`backend/voice/`** — **dead**. `speech_to_text.py`/`text_to_speech.py`, unreferenced anywhere.
- **`backend/workflows/`** — **live, World A**. `WorkflowEngine` executes agent-action graphs via the exact same normalized functions the MCP server exposes; persists run state so a run paused at a human-validation gate can resume.
- **`backend/workspace/`** — **live**. `WorkspaceManager` (HOS-045) — isolated per-mission/agent workspaces, real Git ops, path-sanitized against traversal.

## Memory — the bifurcation in detail

Two real, disjoint systems share the word "memory":
1. **`memory/db.py` + `memory/semantic.py`** — SQLite + real ChromaDB. Persistent. What `EchoAgent` (World A) actually reads/writes.
2. **`memory/memory_manager.py`** (HOS-047, `MemoryManager`) — what Mission/Autonomous write episodic/procedural records to on completion. **Entirely in-process dicts, with a SHA-256-hash "embedding" stub** (not a real embedding) — lost on process restart.

`memory/unified_memory.py` (a third attempt) is **dead** — not imported anywhere. `memory/skill_library.py`'s `Skill` table is yet another, separate concept (see `self_evolution` above) from `backend/skills/`'s empty registry.

## Events — the five real implementations

`SystemEventBus` (HOS-025) · `EventHub` (the Cockpit's actual WebSocket feed) · `EventDispatcher` (the shared per-subsystem callable, forwards into both of the above) · `ral.event_bus_impl.EventBusImpl` (a third, SQLite-backed durable bus, forwarded into `EventHub` via a wildcard subscription in `main.py`'s `lifespan()`) · `core.message_bus.MessageBus` (World A's Aegis trace, also proxied into `EventHub`) · `runtime.events.event_bus.RuntimeEventBus` (a fourth, runtime-scoped bus with its own WebSocket) · `agents.collaboration.message_bus.MessageBus` (a fifth, private to `CollaborationEngine`). `main.py`'s `lifespan()` is where these get stitched together so the Cockpit's one WebSocket sees all of them.

## Config — Python-side, two modules, one real

`backend/core/config.py` is the real, universally-used one (`Settings`, `get_settings()`, the `load_*_config()` functions — its own docstring says nothing else should read `os.environ` or parse the YAML files directly, and this is genuinely respected everywhere else). `backend/config/` (`ConfigManager`) is unrelated, JSON-profile-based, and dead. Top-level `config/models.yaml`/`security.yaml`/`agents.yaml`/`verification.yaml` are all real and actively consumed; `config/capability_graph.yaml` is dead/aspirational — its own header says HOS-000 status (no nodes/edges/rules defined), and no `.py` file anywhere reads it. The routing it once promised was instead built as `ModelRouter`, independently.

## Complete dead/duplicated inventory

**Fully dead**: `backend/agent/` (whole package) · `backend/services/` · `backend/api/router.py` + `hos_routes.py` · `backend/memory/unified_memory.py` · `backend/integrations/hermes_agent/` · `backend/config/` (ConfigManager) · `backend/storage/` (whole package) · `backend/voice/` (whole package) · `backend/logging/production_logger.py` · `backend/monitoring/health_monitor.py` + `recovery_manager.py` · `backend/runtime/code_intelligence/ci_scorer.py` · `config/capability_graph.yaml`.

**Live but structurally empty/unfed**: `backend/skills/` (zero `SkillDefinition`s) · `backend/explainability/` (`.explain()` never called) · `backend/agents/collaboration/` (no real task ever uses it) · `backend/conversation/` (not what `/chat` uses) · `agents/agent_supervisor.py`'s own DAG-walking methods (not the DAG walker actually used).

**Duplicated concepts (both halves real — the load-bearing pattern of this whole codebase)**: two agent registries · two memory systems · two skill concepts · two task trackers · three runtime layers · two-and-a-half security gates (see `security-systems.md`) · five event buses.

**Genuinely solid and load-bearing across both worlds**: `connectors/ollama_client.py` · `core/config.py` + the real `config/*.yaml` files · `security/aegis_engine.py` + `permission_matrix.py` · `core/bootstrap/` · `mission/` + `execution/` · `mcp_server/server.py`.
