# R-001 — Simulation Inventory & Real Execution Layer

> **Date:** 2026-07-30
> **Trigger:** RC2 audit finding R-1 — *"The orchestration is real. The work is not."*
> **Scope:** every production simulation in the repository, classified and resolved or justified.

---

## 1. Inventory method

An AST + pattern scan over every `.py`, `.ts` and `.tsx` file for the terms named in the
brief (`simulate`, `fake`, `mock`, `dummy`, `placeholder`, `stub`, `random.random`,
`random.uniform`, `sleep(`, `not implemented`, `would use`, `TODO exec`), plus a
second pass that flags **fabricated success** structurally: a function that
returns `True` / `{"success": True}` / sets `status = CONNECTED|COMPLETED` while
making no outbound call.

```
total hits           1081
production            424   across 87 files
test-only             657   across 72 files   (left untouched, per the brief)
```

Reproduce: `python scratchpad/inventory.py`.

---

## 2. Classification

The brief asks each occurrence to be classified. The four categories, with the
counts that matter:

### 2.1 Temporary implementation → **replaced** (the R-1 blocker)

| Location | What it did | Resolution |
|---|---|---|
| `backend/autonomous/autonomous_orchestrator.py:124` | `success = random.random() > 0.15`; `duration = random.uniform(500, 5000)`; `sleep(0.01)` — every autonomous goal returned a coin-flip outcome with an invented duration | Delegates to `MissionExecutor` via new `_execute_plan()`; outcome and duration are measured |
| `backend/autonomous/autonomous_orchestrator.py:176` | `runtimes_used=["ktransformers"]` hardcoded while nothing ran | Reports the runtime that actually answered |
| `backend/autonomous/autonomous_orchestrator.py:170-174` | `execution_summary`, `improvements`, `lessons` were fixed strings | Derived from real task results, durations and errors |
| `backend/execution/mission_executor.py:96` | `task.result = f"Simulated result for: {task.title}"`; `task.duration_ms = 42.0` | Calls the injected task executor; failure fails the task |
| `backend/tools/mcp/mcp_client.py:26` | `connect()` set `CONNECTED` with no packet — any host "connected" | Real JSON-RPC `initialize` over HTTP, bounded timeout + retries |
| `backend/tools/mcp/mcp_client.py:57` | `call()` returned a canned `{"status": "ok"}` | Real `tools/call`; transport failure is reported as failure |
| `backend/tools/mcp/mcp_client.py:199` | `ping()` echoed the cached status, so it could never detect a server that had gone away | Real `ping` request; marks ERROR on failure |

### 2.2 Production implementation → **legitimate, kept**

These matched the scan but are correct as they are. Removing them would be the
redesign the brief forbids.

| Location | Why it is not a simulation |
|---|---|
| `backend/runtime/simulation/*` (57 hits) | The **Runtime Simulation Engine (HOS-039)** is a *feature*: what-if analysis of a placement decision *before* executing it. Simulating a hypothetical is its purpose. |
| `backend/ral/adapters/stub_runtime.py` (19 hits) | `StubRuntime` is the documented demo/health runtime from HOS-004, used to prove the RAL contract and as the default at boot. It is honest about being an echo. |
| `backend/evolution/evolution_simulator.py` | Simulates the *impact of a proposal* before applying it — again a feature, not a stand-in. |
| `backend/voice/{speech_to_text,text_to_speech}.py` | Abstract provider base classes (`is_available` returns True for the null provider). No concrete provider ships in v1.0. |
| `backend/core/integration/integration_manager.py` | `register_component` / `initialize` return True after in-memory bookkeeping. No I/O is expected. |
| `backend/runtime/ktransformers/kt_scheduler.py` | `enqueue` / `cancel` / `complete` manipulate an in-memory queue. |
| `backend/execution/{task_scheduler,execution_state}.py` | Pause/resume/cancel on an in-memory state machine. |

### 2.3 Unavailable dependency → **honest failure** (STEP 3)

| Location | Status |
|---|---|
| `backend/runtime/ktransformers/hermes_adapter.py::_SimulatedKernel` | `kt_kernel` is not installed in this environment. The adapter already reports `is_real_kt: false` and `adapter_version: "0.6.1 (simulated)"` in its telemetry, so it does not claim to be real. **Not** used by the execution path any more: `RealTaskExecutor` routes to Ollama and raises `RuntimeUnavailableError` for anything it cannot serve. Left in place as the documented CI fallback; see §5 for the residual risk. |
| vLLM, llama.cpp | No adapter exists. A task naming them now raises `RuntimeUnavailableError` rather than silently succeeding. |

### 2.4 Test-only → **untouched** (657 hits)

`tests/`, `backend/tests/`, `conftest.py`, `__tests__/` and the fake Ollama
clients the agents are deliberately built around
(`backend/agents/minerva.py`: *"fully testable with a fake Ollama client"*).

One addition: `tests/support/fake_inference.py`, and autouse fixtures in
`tests/architecture/conftest.py` and `tests/autonomous/conftest.py`. See §4.

---

## 3. The real execution layer

New: **`backend/execution/task_executor.py`** — `RealTaskExecutor`.

`MissionExecutor.execute_task` already had the whole real pipeline: coordinate an
agent/runtime/skills/tools → *execute* → validate → retry → schedule → release.
Only the middle step was fake, and its own comment said what belonged there
(*"in real system, this calls the agent via runtime"*). `RealTaskExecutor` is
that call.

**Contract**

- **Never fabricates.** Any transport failure, timeout or empty completion raises
  `RuntimeUnavailableError`; the caller fails the task. A task that could not run
  does not report success.
- **Real telemetry.** Duration from `perf_counter`; model and provider from the
  runtime's own response; token counts reported when the runtime supplies them
  and flagged `"token_counts": "estimated"` when derived — so a reader can always
  tell measured from inferred.
- **Records what served, not what was asked for.** `runtime_id` comes from the
  response. Reporting the *requested* runtime is how the old report claimed
  `ktransformers` for work nothing did.
- **Sync/async bridge.** `MissionExecutor` is synchronous and runs in FastAPI's
  threadpool; the Ollama client is async. The bridge is one dedicated background
  loop per executor (`run_coroutine_threadsafe`), not `asyncio.run`, which raises
  when the calling thread already has a running loop.

---

## 4. Keeping the unit suite hermetic

Wiring real execution into `MissionExecutor` made every existing `execute_task`
unit test issue a live LLM request: `tests/architecture/test_execution.py` plus
`tests/autonomous/` went from **0.6 s to 16 minutes**.

Per STEP 11 (*"Keep unit tests. Add integration tests using real execution."*),
only the **outbound call** is replaced in the unit suites, following the
convention the codebase already uses for its agents. The executor, its telemetry,
the artifact write, the validator, the retry policy and the scheduler all remain
production code, so these stay tests of the pipeline rather than tests of a stub.

```
tests/architecture/test_execution.py + tests/autonomous/   16 min  →  0.57 s   (143 passing)
```

Real-execution coverage lives in **`tests/integration/test_real_execution.py`**
(15 tests), which skips when no runtime is reachable — a skip is honest, a pass
against a stub is the problem R-001 removes.

Its assertions are chosen to be unsatisfiable by fabrication:

| Test | What fabrication could not do |
|---|---|
| `test_duration_is_measured_not_generated` | reported duration must be within 35 % of wall clock |
| `test_identical_requests_do_not_flip_outcome` | 3 identical goals must agree (old code flipped ~1 in 6) |
| `test_goal_executes_and_reports_measured_facts` | `runtimes_used == ["ollama"]`, tokens > 0, duration tracks wall clock |
| `test_mission_task_fails_when_runtime_is_down` | failed task must carry **no** result |
| `test_empty_completion_is_a_failure_not_a_success` | an empty answer is not work |
| `test_connects_to_a_real_mcp_server` | boots Hermes' own MCP server and completes a real handshake |
| `test_unreachable_server_is_not_reported_connected` | 3 unreachable hosts, all must report failure |

---

## 5. Verification

Same probe the RC2 audit used to prove execution was fake, re-run against the
same endpoint:

| | RC2 (before) | R-001 (after) |
|---|---|---|
| `success` for 3 identical requests | alternating `True`/`False` | `True`, `True`, `True` |
| reported vs wall-clock duration | uncorrelated | **0.1 % max gap** |
| `runtimes_used` | `["ktransformers"]` hardcoded | `["ollama"]`, measured |
| `tasks_completed` | — | `1/1` |
| tokens | `0` | `78` |
| outputs | none | 41 chars of real code |
| Ollama loaded model during the run | `nomic-embed-text` (untouched) | **`qwen3:4b`** — pulled in by the call |
| runtime down | success reported anyway | `RuntimeUnavailableError`, task FAILED, no result |

Direct executor run:

```
runtime : ollama | model: qwen3:1.7b
duration: 5858 ms
tokens  : 54 prompt / 10 completion  {'token_counts': 'estimated'}
result  : 'def reverse_string(s):\n    return s[::-1]'
```

MCP, against unreachable hosts:

```
169.254.169.254:80        connected=False  URLError: WinError 10051
127.0.0.1:59999           connected=False  URLError: WinError 10061
does-not-exist.invalid:80 connected=False  URLError: getaddrinfo failed
```

**Regression:** `tests/` **2497** passed · `backend/tests/` **796** passed · frontend **65** passed, 0 type errors, production build succeeds — **3,358 tests, 0 failures**.
Unit suites stayed hermetic (16 min → 0.57 s) and 17 tests were added: 15 real-execution
integration tests plus 2 MCP real-contract tests replacing 4 that asserted the simulation.

---

## 6. What remains — explicitly justified

R-001 asks that every production simulation be *eliminated or explicitly
justified*. The following are justified rather than eliminated, and each is a
scoped piece of work rather than a hidden fake:

| # | Item | Justification | Effort |
|---|---|---|---|
| J-1 | **KTransformers `_SimulatedKernel`** | `kt_kernel` is not installable in this environment. The adapter is honest (`is_real_kt: false` in its telemetry) and is no longer on the execution path. Making it real requires the native library. | dependent on `kt-kernel` availability |
| J-2 | **vLLM and llama.cpp adapters** | Do not exist. Tasks naming them now fail with `RuntimeUnavailableError` instead of succeeding. Writing two runtime adapters is new subsystem work, which the brief excludes. | 1–2 wk each |
| J-3 | **Specialised agents (STEP 4)** | `RealTaskExecutor` invokes the LLM with the agent's identity, skills and tools in the system prompt, so an agent's *selection* now shapes real inference. Each agent driving its own tool-calling loop (KlaatCode indexing a repo, OhMyPi editing via LSP) needs its own executor and is not a simulation removal — those agents' MCP fallbacks already label themselves `{"status": "simulated"}`. | 2–3 wk |
| J-4 | **Workspace artifacts (STEP 6)** | The executor writes results through `WorkspaceManager.create_artifact` when a workspace is wired; the bootstrap does not yet pass one to the executor, so artifacts are in-memory. Real git branches and rollback exist in `git_workspace.py` but are not on the autonomous path. | 3–5 d |
| J-5 | **ValidationEngine depth (STEP 7)** | Validation runs for real, but its default criterion is `result_present`. Real syntax/policy/security validation of generated output is new capability, not de-simulation. | 1 wk |
| J-6 | **Memory write-back breadth (STEP 8)** | `AutonomousMemoryLoop.process_report` receives the real report, so episodic memory gets real data. Working/procedural/knowledge-graph/experience write-back is not yet fanned out. | 3–5 d |
| J-7 | **Cockpit (STEP 10)** | The Centers now display real values because the API returns real values. `features/evolution/evolution-center.tsx` still renders `MOCK_PROPOSALS`/`MOCK_REPORTS` client-side. | 0.5 d |
| J-8 | **`evolution_scheduler.py` metrics** | `random.uniform` generates candidate metrics for the evolution *simulator*. Feeding it real telemetry depends on J-6. | 2–3 d |
| J-9 | **`execution_engine._execute_via_hermes`** | Still a placeholder, but off the autonomous path — `AutonomousOrchestrator` routes through `MissionExecutor`. It matters when the Hermes-Agent adapter is used directly. | 2–3 d |

### Success criteria

| Criterion | Status |
|---|---|
| No production endpoint may fabricate execution | ✅ for `/api/v1/autonomous/*`, `/api/v1/execution/*`, `/api/v1/mcp/*` — the three that did |
| Every reported success must correspond to work that actually occurred | ✅ verified: outcome deterministic, duration tracks wall clock, tokens counted, runtime named is the one that answered |
| Hermes OS executes real autonomous missions from request to validated result | ⚠️ **yes for single-task goals**: interpret → plan → select → **real inference** → validate → memory → report. Multi-step decomposition needs J-3; the `DecisionEngine` emits selection decisions, not a task breakdown |
