# Project timeline & the audit trajectory

85 HOS-numbered entries (`HOS-000` → `HOS-079`) span 2026-07-28 → 2026-08-10 in `CHANGELOG.md`, plus a sequence of point-in-time audit reports under `docs/release/`. Useful for understanding *why* something is built the way it is, or why a given component carries a specific known limitation.

## The shape of the project's history

**HOS-000 → HOS-028** (07-28 → 07-29): Foundation. RAL → Agent Layer → Memory → Skills → Events → Service Layer → Mission Control API. This built the "World B" stack from scratch.

**HOS-029 → HOS-040** (07-29): Frontend + Runtime Intelligence. Mission Control Dashboard, the original Centers, Runtime Event Bus, Runtime Resource/Recovery/Intelligence engines, Model Benchmark & Discovery.

**HOS-041 → HOS-058** (07-29, one very large day): Mission Graph, Intelligent Mission Planner, Agent Supervisor, Multi-Agent Collaboration, Workspace/Sandbox, Policy Engine, Unified Memory/Knowledge Graph, Dynamic Skill Distribution, MCP/Tools Platform, Autonomous Mission Execution Engine, Cockpit, KTransformers, Alexandrie, KlaatCode, Oh My Pi, Self-Evolution.

**Then the audit era begins** — and this is the part worth understanding in detail, because it's the direct source of the "two worlds, several duplicated systems" reality documented in `backend-map.md`:

- **RC1** (07-29, score 65/100, NO GO) — subsystems were individually well-built (3117/3133 tests passing) but **nothing assembled them**. The app didn't even start. 0 of 70 served routes belonged to HOS.
- **HOS-066B** (07-30) — built the composition root (`ServiceSpec` catalog, `DependencyContainer`, `HermesBootstrap`) that fixed this: 32/32 subsystems now instantiate.
- **RC2** (07-30, score 71/100, still NO GO) — the platform layer was now genuinely excellent, but the **headline capability was fabricated**: `AutonomousOrchestrator`'s validation step was literally `random.random() > 0.15`, six identical requests alternated success/failure with six invented durations, the MCP client "connected" without a socket call.
- **R-001** (07-30) — direct fix: `RealTaskExecutor`, which never fabricates (raises an error instead of inventing success), real Ollama inference, real JSON-RPC MCP. Explicitly scoped to single-task goals — multi-step decomposition and deep validation were separately tracked as still-open.
- **RC3** (07-30, score 79/100) — confirmed execution was now real, found a mission lifecycle events never reaching the event bus, a 3.8× throughput degradation from unbounded collections, several Cockpit panels still hardcoding fake data next to real APIs. Most-cited remaining gap: **no surface decomposed a goal into a DAG and executed it via `/missions`** — the `mission_planner` service existed but nothing called it from the mission routes.
- **P-002** (07-30) — migrated 74 legacy endpoints under `/api/v1`.
- **R-003 / R-004** (07-30, first run on the *real* target machine — Windows 11, not the originally-planned Ubuntu) — found Hermes couldn't see the GPU at all despite Ollama using it, VRAM capacity was invented in a comment, the Cockpit couldn't reach the backend (wrong prefix in the shipped `.env.local.example`), 11 client methods assumed bare arrays where the API returns wrapped envelopes. All fixed. Confirmed `rocm-smi` is unavailable on this machine class entirely (GPU telemetry has to come from elsewhere). Found the blocking condition for GO: `num_ctx` had to be raised from the 4096 default (a needle-in-haystack probe proved truncation was eating the *start* of prompts).
- **P-001** (07-30) — added the 8 Centers R-004 found missing (17→25 sidebar entries, later consolidated to 22 real Centers after two merges).
- **R-006** (08-09) — wired the real, previously-never-instantiated Code Intelligence router into the composition root; found (and left explicitly out of scope) that KlaatCode's CLI integration targets a command interface that doesn't exist in the installed version, and Oh My Pi's `omp` npm package has no runnable executable via `npx` in this environment.

**The HOS-065C → HOS-079 series** (08-01 → 08-10, most recent, still ongoing) is a sustained, tab-by-tab repeat of the same audit-find-wire-verify pattern applied to each remaining Cockpit surface: real benchmarks (065C) → cloud escalation gating (066C) → Autonomous OS (067) → Missions (068) → Execution (069) → Agents (070) → Model Intelligence (071, 073) → Runtime (072) → Assistant/chat rewrite (074, 075, 076) → Code Intelligence (R-006) → Autonomous real-world test (077) → Assistant web search (078) → Ollama model refresh (079).

## The recurring pattern, if you only remember one thing

Every entry in this series follows the same method, stated or implied: **audit the real code before writing anything → find where a real-looking pipeline is never actually called (a "phantom pipeline") → wire it in, don't rewrite it → verify against real Ollama/real hardware/real browser with exact measured numbers → explicitly name what's still out of scope.** This is not a coincidence or a style choice — it's the project's actual, dominant, unwritten organizing principle (see [hermes/verification](../../verification/SKILL.md)), more consistently followed than any single line in the founding VISION.md or cahier des charges.

## Standing, still-open items (as of HOS-079, not superseded by anything later)

- No plain `/missions` surface distinct from `/autonomous` decomposes-and-executes independently — they now share one engine (see main `SKILL.md`), which resolved the RC3 gap differently than originally framed.
- `SecurityEngine`'s per-agent gate and `ToolPolicy`/`ToolSandbox` write-enforcement remain unwired platform-wide (see `security-systems.md`).
- KTransformers, vLLM, llama.cpp remain non-functional/absent as real runtimes; FreeBuff remains fully stubbed.
- No authentication on any HTTP route (deliberate, single-user scope).
- Docker deployment remains unverified end-to-end (no daemon available in any audit environment so far).
- Cahier des charges §12 (context-window auto-summarization) remains wholly unimplemented.
- KlaatCode and Oh My Pi CLI integrations are structurally broken independent of Hermes's own wiring (external tool version/packaging issues, not something Hermes-side code can fix alone).

## Test suite trend (real numbers, for calibration)

3363 (065C) → 3437 (066C) → 3463 (067) → 3479 (068) → 3496+ (069) → 3522 (070) → 3542 (071) → 3566 (072) → 3587 (074) → 3603 (075) → 3677 (R-006) → 3703 passed / 3 skipped / 1 pre-existing flake (079, most recent). The one recurring flake (`test_task_executor_shares_the_container_model_intelligence`, a test-ordering/shared-state issue) has been tracked across multiple passes without being fixed — see [hermes/verification](../../verification/SKILL.md) for how to tell a pre-existing flake from a real regression.
