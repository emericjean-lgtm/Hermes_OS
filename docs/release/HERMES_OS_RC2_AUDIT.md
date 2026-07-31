# Hermes OS v1.0 — RC2 Final Production Audit

> **Date:** 2026-07-30
> **Auditor role:** independent software quality auditor
> **Scope:** the assembled application after HOS-066B — architecture, backend, frontend, end-to-end missions, security, performance, fault tolerance, packaging, documentation
> **Method:** everything verified against the real `create_app()`, the real dependency container, the real composition root and the real Cockpit. No mocks except where a fault had to be injected deliberately. Ollama was live (16 models); Alexandrie was down; the Docker daemon was unavailable.

---

## Executive Summary

Hermes OS is two systems in one repository, and they are of very different maturity.

**The platform is genuinely good.** The composition root built by HOS-066B assembles 32 subsystems deterministically in dependency order, with no cycles, no orphans, no isolated islands, verified single-instance ownership, clean reverse-order shutdown and no thread or heap leaks across repeated build/teardown cycles. 740 endpoint probes — every route, every method, five payload shapes — produced **zero true server errors**. The security boundaries that exist hold: path traversal blocked on six encodings, permission escalation refused, unknown principals denied by default, MCP DNS-rebinding protection rejecting hostile Host and Origin headers. Fault injection was handled gracefully — a corrupted subsystem is reported `unhealthy` and recovers, a WebSocket disconnect is clean, an unwritable volume returns 422, a running mission cancels. Event dispatch sustains 71,000 events/s. 3,341 tests pass.

**The product's core capability is not implemented.** `POST /api/v1/autonomous/start` — "Autonomous Mission Execution", the marquee feature — does not execute anything. Its execution step is:

```python
# backend/autonomous/autonomous_orchestrator.py:124
# Simulate execution
success = random.random() > 0.15   # 85% success rate
duration = random.uniform(500, 5000)
time.sleep(0.01)  # Tiny delay for realism
```

Six identical requests returned alternating success/failure and six distinct random durations. The report claims `runtimes_used: ["ktransformers"]` while the KTransformers adapter reports `is_real_kt: false`, the orchestrator reports `total_decisions: 0`, and zero agents are registered. Ollama was running with 16 models throughout and was never invoked. The mission-graph path is equally inert: a mission with two nodes flips to `running` and stays at `completed: 0` forever, because `_execute_via_hermes` is documented as "a lightweight placeholder" that emits one event and returns. The outbound MCP client is simulated too — `connect()` always returns success without a network call, and `call()` returns a canned `{"status": "ok"}`.

The distinction that matters: **the orchestration is real and the work is not.** Planning, routing decisions, policy evaluation, trust scoring, threat detection, memory storage, event propagation and the MCP *server* all compute real results. Nothing connects them to an executor. And because every API reports success, a user cannot tell.

**12 defects were found and fixed during this audit** (§Corrections), including a sandbox path-traversal, 21 endpoints returning 500 on client input, 8 event topics still being silently dropped, and a 1000× regression on the Cockpit's health-polling path. **6 issues remain**, one of them critical.

**Decision: 🔴 NO GO.**

---

## Scores

| Axis | Score | Basis |
|---|---:|---|
| Architecture | **88** | 32/32 deterministic build, 0 cycles, 0 orphans, 0 isolated, verified DI, clean shutdown, no leaks. Deducted for module-global route binding and undeclared shared singletons (fixed). |
| Backend | **78** | 0 true 5xx across 740 probes, 0 concurrency failures, graceful degradation. Deducted: validation rests on a boundary net rather than schemas; 3 `response_model` on 195+ routes. |
| Frontend | **62** | Builds clean, 0 type errors, 65/65 tests, 17/17 sidebar ids resolve. Deducted: 39 API paths 404 on a live path, Installer Center absent, loading/empty/error indistinguishable. |
| Security | **80** | Traversal, escalation and rebinding all blocked; fail-closed defaults. Deducted for the sandbox escape found here, and no authentication on the bound interface. |
| Performance | **85** | 71k events/s, sub-millisecond endpoints, 850 ms bootstrap, 1533 req/s parallel. Deducted for `/system/status` at 5.2 s. |
| Reliability | **82** | Fault injection graceful, recovery verified, cancel works, no leaks. Deducted for ≤5 s health staleness and single-start app objects. |
| Maintainability | **84** | Exceptional comment quality, 0 TODO/FIXME, catalogues derived from code. Deducted for 321 unused imports and 6 unresolved duplications. |
| Documentation | **60** | Comprehensive and well-structured, but contains claims this audit falsified. |
| Production | **55** | 3 compose files valid, 6 profiles, backup/restore/migrations tested. Deducted: Docker daemon unverified, installer is hardware detection only, 7 unbounded dependencies. |
| **Overall** | **71** | Platform-grade infrastructure carrying an unimplemented core capability. |

---

## Remaining Issues

### 🔴 CRITICAL

#### R-1 — No execution path performs real work

**Severity:** Critical — the product's primary capability is absent while its API reports success.

**Root cause.** Three independent execution paths all terminate in a stub:

| Path | Location | What it does instead |
|---|---|---|
| Autonomous Core (HOS-063) | `backend/autonomous/autonomous_orchestrator.py:124-127` | `random.random() > 0.15`, `random.uniform(500, 5000)`, `sleep(0.01)` |
| Mission graph (HOS-041/024) | `backend/agent/execution_engine.py:756-768` | emits `TASK_READY` and returns; docstring: "a lightweight placeholder" |
| KTransformers (HOS-052C) | `backend/runtime/ktransformers/hermes_adapter.py:145` | `_SimulatedKernel`; reports `adapter_version: "0.6.1 (simulated)"` |
| MCP client (HOS-049) | `backend/tools/mcp/mcp_client.py:26,57` | "Simulated connection", "Simulated tool call" |

**Evidence.** Six identical `POST /api/v1/autonomous/start` requests:

```
run 0: success=True   duration_ms=3158.4  runtimes=('ktransformers',)  agents=('code_intelligence',)
run 1: success=True   duration_ms=4103.4  runtimes=('ktransformers',)  agents=('code_intelligence',)
run 2: success=False  duration_ms=989.8   runtimes=('ktransformers',)  agents=('code_intelligence',)
run 3: success=False  duration_ms=1381.5  runtimes=('ktransformers',)  agents=('code_intelligence',)
run 4: success=True   duration_ms=4554.1  runtimes=('ktransformers',)  agents=('code_intelligence',)
run 5: success=True   duration_ms=4439.9  runtimes=('ktransformers',)  agents=('code_intelligence',)

distinct success values : {False, True}      <- identical input, different outcome
distinct durations      : 6 of 6             <- generated, not measured
KTransformers stats     : {"total_models": 0, "is_real_kt": false, "adapter_version": "0.6.1 (simulated)"}
Orchestrator stats      : {"total_decisions": 0, "known_runtimes": 0}
Agents registered       : {"agents": [], "total": 0}
Ollama loaded models    : ['nomic-embed-text:latest']   <- never invoked by execution
```

Mission graph:

```
create -> 200 {"mission_id":"d31dac…","status":"ready","nodes":2}
start  -> 200 {"status":"running"}
state  -> 200 {"progress":{"total":2,"completed":0,"failed":0,"ready":2,"running":0}}
```

The mission reports `running` while no node ever leaves `ready`.

**Reproduction.**
```bash
python -c "
from fastapi.testclient import TestClient; from backend.main import create_app
with TestClient(create_app()) as c:
    for _ in range(6):
        g = c.post('/api/v1/autonomous/start', json={'user_request':'Create a REST API'}).json()['goal_id']
        print(c.get(f'/api/v1/autonomous/{g}/report').json()['results'])
"
```

**Fix.** Out of scope for an audit: implementing execution is feature work, explicitly excluded by the RC2 rules. The remediation plan is in §Remediation.

**Verification.** Not verified — unimplemented.

---

### 🟠 MAJOR

#### R-2 — 39 frontend API paths return 404 on a live rendering path

**Severity:** Major — user-visible, on shipped UI, no crash.

**Root cause.** Two client layers are shipped and both are live:

| Layer | Consumers | Targets |
|---|---|---|
| `frontend/src/lib/*` | `app/{agents,missions,execution,runtimes}/page.tsx`, `components/layout/{StatusBar,Topbar}.tsx` | **MissionControlRouter (HOS-028)** — never mounted |
| `frontend/src/services/client.ts` | `features/*-center.tsx` via `hooks/use-api.ts` | the mounted HOS routers |

HOS-066B unified the *prefix* (`/api/hermes-os` → `/api/v1`) but not the *surface*. The `lib/*` clients call 39 paths that no mounted router serves.

**Evidence.** Contract check against the real route table: 124 distinct frontend paths, 39 with no backend route, including `/api/v1/status`, `/api/v1/statistics`, `/api/v1/version`, `/api/v1/diagnostics`, `/api/v1/tick`, `/api/v1/freebuff/*`, `/api/v1/hermes/*`, `/api/v1/missions/{id}/pause|resume`, `/api/v1/agents/{id}/{resume,cancel,retry,recover,duplicate}`.

Mounting `MissionControlRouter` would resolve 13 of the 25 sampled, **collide on 14 already-served paths** (`/api/v1/missions`, `/api/v1/skills`, `/api/v1/runtimes`, `/api/v1/memory/search`, `/api/v1/execution`, …) and leave 12 implemented nowhere.

**Impact.** The client throws on non-OK and consumers use optional chaining, so widgets degrade to blank/zero rather than crashing — combined with R-6 this is indistinguishable from a healthy idle system.

**Fix.** Requires an architecture decision (which of two mission/skills/runtime/memory APIs is canonical) plus implementing 12 absent endpoints. Not a mechanical fix; deliberately not attempted.

**Verification.** Not verified — open.

#### R-3 — Outbound MCP client fabricates success

**Severity:** Major — a shipped API reports work it never performed.

**Root cause.** `backend/tools/mcp/mcp_client.py`: `connect()` sets `MCPStatus.CONNECTED` with no transport; `call()` returns `{"status": "ok", …}` unconditionally.

**Evidence.** `POST /api/v1/mcp/connect {"host": "169.254.169.254", "port": 80}` → `200 {"connected": true}` with no packet emitted. Any host "connects".

**Note.** The MCP **server** side is real — `backend/mcp_server/` serves streamable HTTP, validated by 24 passing tests and the Host-header probes in §Phase 5. Only the client is stubbed. When it is implemented, host validation must be added or this becomes an SSRF vector.

**Fix.** Feature work. Interim mitigation: have `/api/v1/mcp/connect` report `simulated: true` so the Tools Center cannot present fabricated connections as real.

**Verification.** Not verified — open.

#### R-4 — Seven dependencies have no upper bound

**Severity:** Major — this has already caused a failure.

**Root cause.** `backend/requirements.txt`: `fastapi>=0.115`, `uvicorn[standard]>=0.30`, `sqlalchemy>=2.0`, `chromadb>=0.5`, `mcp>=1.0`, `pypdf>=5.0`, `python-docx>=1.1`.

**Evidence.** `mcp>=1.0` resolved to 1.26.0, which enabled DNS-rebinding protection by default and broke all 24 MCP tests with `421 Misdirected Request` — diagnosed in the RC1 audit. The same class of break is available to the other six.

**Fix.** Add upper bounds, e.g. `mcp>=1.26,<2`, `fastapi>=0.115,<1`.

**Verification.** Not applied — a dependency-pinning change needs a full install-and-test cycle that this audit did not have a clean environment for.

#### R-5 — Documentation asserts claims this audit falsified

**Severity:** Major — misleads the release decision.

**Root cause.** After HOS-066B I recorded C-3 (divergent API clients) and Cockpit reachability as resolved. R-2 shows C-3 is half-resolved, and the Installer Center does not exist.

**Evidence.** `ROADMAP.md` — "17/17 ids de sidebar résolvent"; true for the sidebar, but the audit scope lists an Installer Center that has no implementation. `CHANGELOG.md` `[HOS-066B]` — "C-3 … ✅ `/api/v1` canonique".

**Fix.** Corrected in this pass — see §Corrections C-11.

**Verification.** ✅ `ROADMAP.md` and `CHANGELOG.md` now state the residual gap.

#### R-6 — Loading, empty and failed states are indistinguishable

**Severity:** Major in combination with R-2; Minor alone.

**Root cause.** Every Center reads React Query data as `data?.field || 0` / `|| "UNKNOWN"` and never destructures `isLoading`/`isError`. A 404, a pending fetch and a genuinely empty system all render as zeros.

**Evidence.** `features/dashboard/dashboard-view.tsx:20-28` — `missions?.filter(...).length || 0`, `health?.status || "UNKNOWN"`. No Center of 16 renders an error state.

**Fix.** Surface `isError`/`isLoading` per widget. Small but touches 16 files; deferred as UI work rather than a defect fix.

**Verification.** Not verified — open.

---

### 🟡 MINOR

| # | Issue | Evidence |
|---|---|---|
| R-7 | `GET /system/status` takes 5.2 s | legacy endpoint probes Ollama and the GPU synchronously |
| R-8 | 11 of 32 subsystems expose no telemetry accessor | reported honestly as `silent` by `/api/v1/system/health`, neither healthy nor degraded |
| R-9 | An app object cannot be started twice | `StreamableHTTPSessionManager.run() can only be called once per instance`; production starts once, but an in-place ASGI restart fails |
| R-10 | Health readings may be up to 5 s stale | deliberate trade for the fix in C-10; fault detection verified still correct after the delay |

---

## Corrections applied during this audit

Only defects blocking production readiness were fixed. No feature was added.

| # | Severity | Defect | Fix | Verification |
|---|---|---|---|---|
| C-1 | Major | 8 event topics still silently dropped after HOS-066B claimed the drift fixed (`AUTONOMOUS_EVENTS["goal_received"]` and a topic held in a variable are invisible to an AST scan of string literals) | Harvest all 6 `*_EVENTS` catalogues; make the publish path permissive for unknown-but-well-formed topics, warning once per topic; keep the subscribe path strict | ✅ 0 rejections while driving real subsystems; allow-list 143 → 179 |
| C-2 | Major | Malformed topics could reach subscribers | `_is_well_formed` refuses non-dotted, leading/trailing-dot, whitespace-bearing and non-string topics | ✅ 7 malformed forms refused, `policy.allowed` delivered |
| C-3 | Major | 4 subsystems shared one instance across app instances without `adopts_module_singleton`, so the dependency report described them as per-app | Flag `klaatcode`, `ohmypi`, `ktransformers`, `model_intelligence` | ✅ undeclared sharing now 0; asserted as an invariant, not a list |
| C-4 | Critical | 21 endpoints returned **500** to an empty or malformed body (`payload["field"]` → KeyError; enum coercion → ValueError) | `KeyError`/`ValueError` handlers at the app boundary → 422 naming the offending field, full traceback still logged | ✅ 21 → 0; `Field required: 'user_request'` |
| C-5 | Major | 24 of 192 requests failed under 32-thread load | same root cause as C-4, not a race | ✅ 24 → 0 failures |
| C-6 | Major | `POST /api/v1/alexandrie/documents` returned 500 when Alexandrie was offline | 503 with a pointer to the health endpoint; the adapter returns `None` only on circuit-open or upstream failure, never for bad input | ✅ 503, and `alexandrie/health` corroborates `healthy: false` |
| C-7 | Critical | **Workspace sandbox escape.** `work_dir=f"{base}/{mission_id}/{agent_id}"` interpolated caller-supplied ids; `mission_id="../../PWNED"` resolved to `…/AppData/Local/PWNED/atk`, outside the base | `_safe_path_component` reduces each id to one contained directory name | ✅ 14 attack inputs (`../..`, `..\..`, absolute, drive-letter, NUL, URL-encoded, `.`, `..`, empty) all contained at exactly depth 2 |
| C-8 | Major | `/api/v1/system/health` took **864 ms** p50 and served **1 req/s** under load, because KlaatCode (1080 ms) and Oh My Pi (894 ms) telemetry accessors do live network probes | 5 s TTL cache on the probe, matching `AlexandrieClient` | ✅ 864 ms → 0.8 ms; 1 → **1533 req/s**; fault still detected within one TTL and recovery verified |
| C-9 | Minor | Health probe called parameterised accessors blind (`LearningEngine.get_stats(runtime_id)`), scoring a healthy subsystem unhealthy | Signature inspection; skip accessors with required parameters | ✅ `runtime_intelligence` no longer unhealthy |
| C-10 | Minor | `policy.allowed` / `policy.denied` absent from the topic catalogue | Added, with a note on why the AST harvest missed them | ✅ present |
| C-11 | Major | ROADMAP/CHANGELOG asserted C-3 resolved and Cockpit fully reachable | Corrected to state the residual 39-path gap and the absent Installer Center | ✅ documents match the measured state |
| C-12 | Major | `POST /api/v1/execution/start` returned **500** when `tasks` was not a list of objects (`AttributeError: 'str' object has no attribute 'get'`) — missed by the Phase 2 payload set and caught by the regression test written for C-4 | Shape validation in the adapter, rather than widening the app handlers to `AttributeError`, which would also swallow genuine server bugs | ✅ 422 naming `body.tasks`; valid payloads still 200 |

**Regression status after all corrections:** `tests/` **2480** passed (139 of them the assembly/RC2 integration suite) · `backend/tests/` **796** passed · frontend **65** passed, 0 type errors, production build succeeds. **3,341 tests, 0 failures.**

---

## Phase results

### Phase 1 — Architecture — 88

| Check | Result |
|---|---|
| Composition root | ✅ 32/32 built, byte-identical across two builds |
| Dependency injection | ✅ all 16 `on_event` seams verified by publishing and counting, not by attribute inspection |
| Service lifetime | ✅ `container.get` stable for all 32 |
| Singleton correctness | ✅ after C-3: 8 shared instances, all declared |
| Circular dependencies | ✅ none (runtime graph and module-level imports) |
| Bootstrap sequence | ✅ every dependency precedes its consumer |
| Shutdown sequence | ✅ reverse build order; no errors; second shutdown safe |
| Resource cleanup | ✅ no thread leaked across build+shutdown |
| Memory ownership | ✅ +87 KiB over 5 build/shutdown cycles |
| Container concurrency | ✅ exactly one winner under 32-way contention |

`AutonomousEngine` exposes no `_on_event` because it is a facade forwarding to its orchestrator; verified the dispatcher arrives there and that `start_goal` emits 8 real events. My first probe checked the wrong object — recorded here so the "finding" is not mistaken for a defect.

### Phase 2 — Backend — 78

740 probes (every route x every method x five payload shapes) after C-4/C-6/C-12:

```
200=408  400=5  404=75  422=247  503=5
TRUE ERRORS (500/502/504): 0
DEGRADED (503, Alexandrie verifiably down): 5
```

Malformed input (5 payload shapes × 77 POST endpoints), non-JSON bodies, and 32-thread concurrency all produce zero true errors. **Authentication:** none on the bound interface — a documented v1.0 scope boundary (ROADMAP HOS-040), not a defect, but every mutating endpoint is unauthenticated and the deployment must not expose the port beyond localhost.

### Phase 3 — Frontend — 62

✅ 17/17 sidebar ids resolve · ✅ 0 type errors · ✅ 65/65 tests · ✅ production build, 14 pages
❌ Installer Center absent · ❌ 39 API paths 404 (R-2) · ❌ states indistinguishable (R-6) · ⚠️ `evolution` Center mapped but not in the sidebar

### Phase 4 — End-to-end missions — not passable

Planning, decision generation, event emission and state transitions are real. Execution is not (R-1). No mission produced an artifact, invoked a runtime, or ran an agent.

### Phase 5 — Security — 80

| Attack | Result |
|---|---|
| Path traversal read (6 encodings) | ✅ all 403 |
| Write outside `ALLOWED_PATHS` (3 forms) | ✅ all 422 |
| Workspace escape | 🔴 **succeeded** → fixed (C-7) → ✅ 14/14 contained |
| Permission escalation across resources | ✅ denied |
| Unknown principal default | ✅ denied (fail-closed) |
| Approve a non-existent request | ✅ `ok: false` |
| Tool execution with traversal id / escalated permission | ✅ refused |
| MCP hostile Host (4 hosts incl. 169.254.169.254) | ✅ all 421 |
| MCP hostile Origin | ✅ 403 |
| MCP connect to link-local metadata | ⚠️ "succeeds" but performs no I/O (R-3) |

### Phase 6 — Performance — 85

| Metric | Value |
|---|---|
| Bootstrap build | ~850 ms |
| Shutdown | <5 ms |
| Event throughput | **71,240 events/s** |
| Endpoint p50 | 0.5–0.7 ms (`/health`, agents, skills, missions, security) |
| `/api/v1/system/health` | 864 ms → **0.8 ms** (C-8) |
| Parallel (160 req, 16 threads) | 1 → **1533 req/s** (C-8) |
| `/system/status` | 5.2 s (R-7) |

### Phase 7 — Fault injection — 82

| Fault | Behaviour |
|---|---|
| Dependency down (Alexandrie, real) | ✅ 200 with degraded payload; 503 on write |
| Subsystem raising from telemetry | ✅ `/system/health` → `unhealthy: ['security_engine']`; ✅ recovers on restore |
| Runtime registry empty | ✅ `/api/v1/runtimes` still serves |
| WebSocket abrupt disconnect | ✅ clean; server healthy after |
| Write to unavailable volume | ✅ 422 |
| Cancel a running mission | ✅ `cancelled` |

### Phase 8 — Packaging — 55

✅ 3 compose files **validate** (`docker compose config`) · ✅ 2 Dockerfiles, nginx.conf, `.env.example` · ✅ 6 deployment profiles (`local_gpu`, `cpu_only`, `wsl`, `docker`, `server`, `cloud_gpu`) · ✅ migrations, backup and restore tested (84/84)
❌ **Docker daemon unavailable — no image was built and no container was run.** Compose validity is syntax, not a deployment proof.
⚠️ Installer is `system_detector.py` + `hardware_profile.py` — hardware detection, no install/update/rollback flow, no API, no UI.
❌ 7 unbounded dependencies (R-4)

### Phase 9 — Documentation — 60

✅ README, ROADMAP, CHANGELOG, ARCHITECTURE, RC1 audit, composition-root architecture, generated dependency report all present and internally coherent
❌ Contained falsified claims → corrected (C-11)
⚠️ `docs/integrations/` covers only Freebuff and Hermes Agent; Alexandrie, KlaatCode, Oh My Pi and KTransformers are documented under `docs/architecture/` instead
⚠️ No document states which capabilities are simulated — the single most important fact for a user evaluating v1.0

---

## Risk Assessment

| Risk | Likelihood | Impact | Exposure |
|---|---|---|---|
| A user runs an autonomous mission, receives a success report, and discovers nothing happened | **Certain** | **Severe** — credibility loss on first contact | R-1 |
| Cockpit widgets show blank/zero indefinitely and are read as "idle" rather than "disconnected" | High | Moderate | R-2 + R-6 |
| Tools Center presents MCP servers as connected that were never contacted | High | Moderate | R-3 |
| An unpinned dependency upgrade breaks the build or the runtime | Moderate | High | R-4 |
| Unauthenticated API reached beyond localhost | Low if deployed as documented | **Severe** | Phase 2 |
| Docker deployment fails on first real run | Unknown — **unverified** | High | Phase 8 |
| Sandbox escape via a path component | ~~High~~ | ~~Severe~~ | **Closed** (C-7) |
| Client input crashes an endpoint | ~~Certain~~ | ~~Moderate~~ | **Closed** (C-4) |

The unquantified risk is Phase 8: without a Docker daemon this audit could not build an image or start a container. Compose files parse; that is all that was established.

---

## Final Decision

### 🔴 NO GO

Against the stated success criteria:

| Criterion | Status |
|---|---|
| All tests pass | ✅ 3,341 passing, 0 failures |
| No critical issue remains | ❌ **R-1** |
| No major issue remains | ❌ **R-2, R-3, R-4, R-6** |
| No architecture regression | ✅ verified |
| No orphan subsystem | ✅ 0 orphans, 0 isolated |
| No unreachable Cockpit Center | ❌ Installer Center absent |
| No broken API | ❌ 39 frontend paths 404 |
| No unsafe execution path | ✅ after C-7; and there is no execution path to be unsafe |
| Production deployment validated | ❌ **not validated** — Docker daemon unavailable |

Four of nine criteria fail.

**The decisive one is R-1.** Everything else on this list is a finite, well-understood piece of work. R-1 is not a defect in a feature; it is the absence of the feature the release is named for. Hermes OS presents itself as an autonomous operating system, and its autonomous execution is `random.random() > 0.15`. Shipping that as v1.0 — with APIs that return fabricated success reports — would misrepresent the product to its users, and no amount of platform quality compensates for it.

**This is not a negative verdict on the engineering.** The infrastructure audited here is better than most production systems: a genuinely correct composition root, honest health reporting that distinguishes "silent" from "healthy", security boundaries that hold under attack, 71k events/s, and a test suite that now catches assembly regressions rather than only unit behaviour. HOS-066B did what it claimed for the platform. The gap is that the platform has nothing plugged into its executor.

### What GO requires

| # | Action | Effort | Clears |
|---|---|---|---|
| 1 | **Implement execution.** Wire `AutonomousOrchestrator` step 4 and `ExecutionEngine._execute_via_hermes` to the real path: `RuntimeOrchestrator.select` → `OllamaClient` (live, verified working) → `AgentSupervisor` → tool/filesystem, with measured durations and real outcomes replacing `random`. | 2–4 weeks | **R-1** |
| 2 | Register real agents at startup so `AgentSupervisor` is non-empty, and record runtime decisions so `runtimes_used` reflects what ran. | 3–5 d | R-1 |
| 3 | Decide the canonical mission/skills/runtime/memory API; retire the loser; implement the 12 absent endpoints or remove the clients that call them. | 1–2 wk | **R-2** |
| 4 | Implement the outbound MCP transport, with host validation from the outset. Until then, mark `/api/v1/mcp/connect` responses `simulated: true`. | 1 wk | **R-3** |
| 5 | Add upper bounds to all 7 unbounded requirements; verify with a clean install. | 0.5 d | **R-4** |
| 6 | Surface `isLoading`/`isError` in all 16 Centers. | 2–3 d | **R-6** |
| 7 | Build the images and run the stack on a live Docker daemon; validate WSL, Linux and Windows paths and the GPU/CPU/server profiles. | 2–3 d | Phase 8 |
| 8 | Implement or withdraw the Installer Center. | 1 wk or 0 d | Phase 3 |
| 9 | State plainly in README and ROADMAP which capabilities are simulated, for as long as any are. | 0.5 d | Phase 9 |

**Interim option.** If a release is needed before item 1 lands, the honest path is to ship as **v0.9 "platform preview"**: keep the assembled platform, the real Ollama chat/classify/vision paths and the observability surface, and remove or clearly label the Autonomous, Mission-execution and MCP-client endpoints as not-yet-functional. That is a defensible release. v1.0 with R-1 open is not.

---

## Annexe — Reproducing this audit

```bash
# Phase 1 — architecture
python scratchpad/p1_architecture.py

# Phase 2 — every endpoint, every method, adversarial payloads
python scratchpad/p2_backend.py

# Phase 3 — Cockpit contract against the real route table
python scratchpad/p3_frontend.py

# Phase 4 — is execution real?
python scratchpad/p4_e2e.py

# Phase 5 — attacks
python scratchpad/p5_security.py

# Phases 6-9
python scratchpad/p6789.py

# Regressions
python -m pytest tests --timeout=300 --timeout-method=thread
python -m pytest --timeout=300 --timeout-method=thread
cd frontend && npx tsc --noEmit && npx next build && npx vitest run
```

Live introspection on a running instance:

```
GET /api/v1/system/assembly      build + router report, completeness
GET /api/v1/system/dependencies  full dependency graph
GET /api/v1/system/health        per-subsystem status (healthy / unhealthy / silent)
GET /api/v1/system/ready         completeness gate with blockers
GET /api/v1/system/statistics    per-subsystem telemetry + event counters
```
