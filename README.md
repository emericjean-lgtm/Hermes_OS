# Hermes Ollama

Local, single-user AI copilot orchestrating Ollama models through a
multi-agent backend. Full specification: **[CAHIER_DES_CHARGES_HERMES_OLLAMA.md](./CAHIER_DES_CHARGES_HERMES_OLLAMA.md)**
— read it first, it is the source of truth for scope, architecture, and
target hardware (AMD RX 6800 16 GB / i5-13500 / 32 GB DDR5).

## Current state

Built and tested so far: a config-driven model router, a mockable Ollama
client, the Hermes Prime orchestrator agent, a streaming `/chat` API, a
minimal Chat page, **Aegis** (deterministic security gate, `/security/evaluate`,
plus an opt-in LLM advisory pass — `include_advisory: true` — that
annotates a `require_human_validation` verdict with the security-role
model's read on what's worth double-checking, never a second vote on
the verdict itself; the advisory prompt requires an explicit
`ADVISORY:` marker and only the text after the last occurrence of it is
kept, same fixed-format-prompt + parse pattern as Veritas's
`VERDICT:/ISSUES:/CORRECTIONS:` — confirmed necessary on real hardware:
`chat_stream()` also passes `think=True` as defense-in-depth, but
Ollama 0.32.0 was confirmed (via a direct `/api/chat` test) to ignore
`think` entirely for `phi4-reasoning:14b-q4_K_M`, inlining its whole
chain-of-thought into `message.content` regardless — the marker/parse
step is what actually keeps that reasoning trace out of the advisory
text a human reviewer sees),
**Atlas** (Aegis-gated file tools with diff + backup, `/files*`), **Echo**
(SQLite long-term memory + ChromaDB documentary/RAG memory, `/memory*`),
**Kronos** (task tracking with status/history, `/tasks*`), **Minerva**
(research/RAG agent: retrieves passages from Echo's documentary memory,
synthesizes a cited answer, `/research`), **Veritas** (QA agent: reviews
another agent's output and returns a parsed verdict — approved /
needs_revision / rejected — plus issues and corrections, `/verify`),
**Hermes Scribe** (writing/documentation agent: brief -> document,
`/write`), **Hermes Eyes** (vision agent: multimodal image analysis via
`gemma4:12b`, `/vision/analyze`), **Hermes Swift** (always-on, ultra-fast
request classifier: labels a raw request with a task type from
`models.yaml`'s routing matrix, `/classify`), the **message bus** (typed
inter-agent trace — every `AegisAgent.evaluate()` call publishes a
VALIDATION_REQUEST plus a VALIDATION_GRANTED/VALIDATION_DENIED/ESCALATION,
persisted to SQLite, queryable via `/messages` and filterable by
`task_id`/`agent`), the **workflow engine** (a graph of agent actions
defined in YAML under `data/workflows/`, cahier des charges §15 —
`WorkflowEngine.run()` walks the graph via the same normalized tool
registry the MCP server uses, resolves `$steps.<node>.<key>` placeholders
between steps, branches on `on_success`/`on_failure` edges, halts at
`human_validation` gates, and traces every node through the message bus;
`simulate()` is a pure dry-run. Every run is persisted (SQLite,
`backend/workflows/run_store.py`) and genuinely **resumable**: pass a
previous run's `id` back as `run_id` (plus any newly-approved node ids)
to continue past a gate — only nodes not already decided
(success/failed) are (re-)evaluated, approved_nodes accumulates across
resumes, and `GET /workflows/runs/{run_id}` checks a run's state without
executing anything. `/workflows*` REST API, example workflow
at `data/workflows/full-code-review.yaml`), **projects** (multi-project
scoping — not in the original cahier des charges; `Project` entity with
status active/archived and tags, `/projects*` REST API — and `project_id`
is now threaded through everything else: tasks (Kronos), long-term +
documentary memory (Echo, including a ChromaDB metadata `where` filter
on recall), the message bus, Aegis's `ActionRequest`, and workflows,
each filterable by `project_id` on its list/search endpoints. Atlas's
file tools are now project-scoped too:
`AegisEngine.evaluate(action, project_root=...)` narrows the global
`ALLOWED_PATHS` whitelist to a project's `root_path` when given —
narrowing only, `ALLOWED_PATHS` remains the hard boundary regardless —
resolved by `AegisAgent` from `action.project_id` (a `project_id` that
doesn't resolve to a real project escalates to
`require_human_validation` rather than silently skipping the extra
restriction); threaded through `file_tools`, `/files*`, and `files_*`),
**hardware monitoring** (cahier des charges §21 — `GpuMonitor.snapshot()`,
two platform backends picked via `platform.system()`: **Linux** reads
GPU VRAM/temperature/load via `rocm-smi --json`, CPU/RAM/swap via
`/proc`; **Windows** — confirmed necessary against real hardware, the
actual target machine turned out to run Ollama natively on Windows, not
Ubuntu+ROCm — reads GPU VRAM from the registry
(`HardwareInformation.qwMemorySize`, the max across every adapter
subkey, since a system with both an iGPU and the discrete card needs to
pick the right one) and GPU load/used VRAM from Windows' own
cross-vendor `GPU Engine`/`GPU Adapter Memory` performance counters (no
vendor tool needed), CPU via `Win32_Processor.LoadPercentage`, RAM/swap
via `Win32_OperatingSystem`/`Win32_PageFileUsage` — all via PowerShell.
GPU **temperature** has no equivalent on Windows without a vendor tool
this project doesn't require, so it's `null` there rather than a
fabricated `0.0` (never fed into the alert thresholds either). Currently-
loaded Ollama models via the shared `OllamaClient`'s `/api/ps`; disk via
stdlib. Alerts against `.env`'s `GPU_ALERT_TEMP_C`/`GPU_CRITICAL_TEMP_C`/
`GPU_VRAM_WARNING_PCT` thresholds; degrades to `"gpu": null` when the
platform's GPU command isn't available at all — including in this
sandbox, which has neither an AMD GPU nor Windows — and to an "Ollama
unreachable" alert rather than failing outright if Ollama itself is
down; `/system/status` REST
endpoint), **HSE / Hermes Self-Evolution** (cahier des charges §20 — the
system learns from its own executions: `auto_evaluator` reads a
completed task's status as a deterministic success/failure signal (no
LLM call — same reasoning as the other self_evolution/ modules),
`skill_extractor` turns a clean success into a new `Skill` (SQLite,
`backend/memory/skill_library.py`) starting between `.env`'s
`SKILL_MIN_CONFIDENCE` and `SKILL_AUTO_VALIDATE_THRESHOLD` — "en
révision" until reuse pushes it past the auto-validate threshold via
`record_use()`'s reinforcement (and Ebbinghaus-style `apply_decay()` for
unused skills, gated behind `EBBINGHAUS_DECAY_ENABLED`, §11.6),
`reflection_engine` templates a post-task reflection into Echo's memory
when `REFLECTION_ENABLED`, and `progression_tracker` aggregates success
rate / skill counts on demand. Skill dedup: before creating a skill,
the pipeline checks for an existing one with the same name in the same
project (`EchoAgent.find_skill_by_name()`, case-insensitive, exact,
fully deterministic) and reinforces it instead of spawning a near-
duplicate — a semantic (near-duplicate wording) dedup pass is possible
too (skills can be indexed into a dedicated cosine-distance ChromaDB
collection via `index_skill`/searched via `search_skills`/`GET
/skills/search`) but isn't wired into the automatic dedup path, since
its distance threshold needs tuning against a real embedding model this
sandbox doesn't have — same "needs a live Ollama server" caveat as
Echo's `index_document`/`recall`. Deliberately *not* auto-triggered from
Kronos's `update_task()` — called explicitly via
`POST /hse/process/{task_id}` + `GET /hse/progression`, and `/skills*`
for the library itself, or in the same request as marking a task done:
`PATCH /tasks/{id}` (and the `tasks_update` MCP tool) take an opt-in
`run_hse: bool` that runs the pipeline right after the update and
returns its result under the response's `hse` key — one call instead of
two, still opt-in, matching this project's "explicit call, no hidden
side effects" pattern elsewhere), and an **MCP server** exposing
Aegis/Atlas/Echo/Kronos/Minerva/Veritas/Hermes Scribe/Hermes Eyes/Hermes
Swift as tools plus the bus's `messages_list`, hardware telemetry's
`system_status`, the workflow engine's `workflows_*`, `projects_*`, and
HSE's `skills_*`/`hse_process_task`/`hse_progression` (see "Hermes Agent
integration" below). 371 tests passing — every module in the original
cahier des charges roadmap is now built; see `config/agents.yaml` for
the full agent registry. Telegram and workflow scheduling
(`triggers.yaml`) are no longer planned as our own builds — Hermes
Agent's native gateway and `cronjob` cover both, see "Hermes Agent
integration" below. A **Hermes Agent dashboard plugin**
(`config/hermes_agent_dashboard/`) is built too — a "Hermes Ollama" tab
inside Hermes Agent's own web UI, so the planned Next.js frontend
(currently just a minimal Chat page) doesn't need to grow into a full
second UI; see "Hermes Agent integration" below.

**Real hardware update:** all of the above has now been exercised
end-to-end on the actual target machine — except it turned out to be
**native Windows Ollama, not Ubuntu+ROCm** (the RX 6800 / i5-13500 / 32GB
box the cahier des charges was written for, just running Windows 11
rather than the assumed Ubuntu 24.04). `/chat`, `/vision/analyze`,
`/classify`, `/verify`, `/memory/index`+`/research`, the full HSE loop
(task → skill → index → semantic search), `/projects`, `/workflows`, and
`/security/evaluate` (including the LLM advisory pass) were all run
against real models on the real GPU, not the fake Ollama client. `pytest`
still passes fully with the fake client (371 tests) for anyone without
this hardware. Four real, hardware-only bugs were found and fixed along
the way — none reproducible against the fake client:

1. **GPU/CPU/RAM monitoring had no Windows path** — `GpuMonitor` only
   ever shelled out to `rocm-smi`/read `/proc`, both Linux-only. Fixed
   with a Windows branch (`platform.system()`-gated) using PowerShell:
   registry `HardwareInformation.qwMemorySize` for VRAM total (max
   across adapters, to skip past an iGPU), the `GPU Engine`/`GPU Adapter
   Memory` performance counters for load/used VRAM, `Win32_Processor`
   for CPU, `Win32_OperatingSystem`/`Win32_PageFileUsage` for RAM/swap.
   Temperature has no cross-vendor Windows equivalent without a vendor
   tool, so it's `null` there (never fed into alert thresholds) rather
   than a fabricated `0.0`.
2. **Aegis's advisory pass leaked its model's raw reasoning trace** —
   `phi4-reasoning:14b-q4_K_M` (the `security` role model) ignores
   Ollama's `think` API parameter entirely (confirmed via a direct
   `/api/chat` test: no `message.thinking` field ever appears), so its
   whole chain-of-thought landed in the advisory text a human reviewer
   sees. Fixed with a fixed-format-prompt + `ADVISORY:`-marker parse,
   same pattern as Veritas's `VERDICT:/ISSUES:/CORRECTIONS:` — but this
   fix is **not fully reliable**: this specific model is extremely
   verbose (one real run took 117s / 4,363 tokens deliberating about the
   format instruction itself, quoting `"ADVISORY:"` repeatedly *while*
   reasoning about it) and occasionally lands the marker in the wrong
   place, returning an empty string or taking minutes. Worth revisiting
   with a different `security` model if this proves too flaky in
   practice.
3. **Hermes Agent's own model requirements ruled out this project's
   `orchestrator`** — see "Hermes Agent integration" below.
4. **The Hermes Agent dashboard plugin needed an undocumented opt-in** —
   see `config/hermes_agent_dashboard/README.md`.

`config/models.yaml`'s `standard`/`orchestrator`/`vision`/`security`
roles were also upgraded from the original cahier des charges' tags
(`qwen3:8b`→`qwen3.5:9b`, `hermes3:8b`→Hermes-4-14B, `gemma3:12b`→`gemma4:12b`,
`phi4:14b`→`phi4-reasoning:14b-q4_K_M`) after confirming availability and
real VRAM figures on this hardware — see that file's own comments for
the full reasoning per role.

## Project layout

```
backend/     FastAPI app, agents, router, Ollama client, tests
frontend/    Next.js 16 + TypeScript + Tailwind, minimal Chat page
config/      models.yaml (routing matrix) and agents.yaml (agent registry)
data/        SQLite/ChromaDB/logs at runtime (gitignored, dirs kept via .gitkeep)
```

## Quickstart

### 1. Backend

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

cp .env.example .env
# Edit .env: set ALLOWED_PATHS to your real project directories.

uvicorn backend.main:app --reload --reload-dir backend --host 0.0.0.0 --port 8000
```

`--reload-dir backend` keeps the auto-reloader from watching `frontend/node_modules`
(otherwise every `pnpm install` triggers spurious restarts).

Run the test suite (no GPU/Ollama required, uses a fake client):

```bash
pytest
```

### 2. Ollama (on your local machine, not in this sandbox)

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3.5:9b   # default "standard" model used by the walking skeleton
```

See §25 of the cahier des charges for the full ROCm setup (RX 6800 needs
`HSA_OVERRIDE_GFX_VERSION=10.3.0`) and the full model pull list.

### 3. Frontend

```bash
cd frontend
pnpm install
cp .env.local.example .env.local
pnpm dev
```

Open http://localhost:3000, type a message — it is routed through Hermes
Prime and streamed back from whichever model `config/models.yaml` resolves
for the `conversation` task type.

## Hermes Agent integration

[Hermes Agent](https://github.com/NousResearch/hermes-agent) (NousResearch's
open-source agent runtime — unrelated to this project's own name, which is
thematic) replaces `core/router.py` + `agents/hermes_prime.py` as the primary
orchestrator. Installed and confirmed working end-to-end on real hardware
(v0.19.0, RX 6800, native Windows Ollama):

- **Hermes Agent runs on one model per session** — it has no per-task-type
  routing of its own. Every specialized per-task model choice
  (`qwen3.5:9b` for Minerva, `deepseek-r1:14b` for Veritas, `gemma4:12b`
  for Eyes...) still happens *inside* the MCP tools below — Hermes never
  needs to know about it, this project's "one model per role" principle
  (cahier des charges §7) is unaffected.
  **Hermes Agent's own model is `devstral`, not this project's
  `orchestrator`** (Hermes-4-14B) — two real constraints, found on real
  hardware, ruled the latter out:
  1. Hermes Agent hard-requires ≥64K tokens of context for its own model
     (errors at startup below that). Hermes-4-14B's real window is
     40,960 — confirmed via the base model's own `config.json`
     (`max_position_embeddings: 40960, rope_scaling: null`), not a
     quantization artifact, so no alternate GGUF conversion fixes it.
  2. `qwen3.5:9b` (this project's `standard`, 262K context) was tried
     next and technically satisfies the context floor, but reliably
     *narrates* tool use in prose instead of emitting a real
     `tool_calls` response — Hermes never sets `tool_choice` for a
     "custom" OpenAI-compatible provider (confirmed by capturing the
     real HTTP request to Ollama), leaving it at the default `auto`,
     and this model just doesn't call tools reliably under `auto`.
     Forcing `tool_choice: "required"` fixed it in isolation, but that
     isn't something Hermes Agent's config exposes for a custom
     provider.
  `devstral` (this project's `code_agentic`, 131K context, Mistral's
  agent-first coding model) reliably emits real tool calls under
  Hermes's actual default — confirmed the same way, and then
  end-to-end through a live `hermes -z` run and `hermes chat`.
  `config/models.yaml`'s `orchestrator` role is untouched and still used
  internally by this backend's own router; only Hermes Agent's own
  session model differs from it.
- Hermes ships 40+ **native tools of its own** (terminal, file patch/read,
  memory, todo, kanban, cronjob). `terminal`/`patch`/`read_file` are disabled
  in the example config below — they'd bypass Aegis entirely — with a
  `pre_tool_call` hook (`config/hermes_agent_hooks/aegis_gate.py`) as a
  second layer of defense in case they're re-enabled later. Kanban is
  disabled too: Kronos stays the single source of truth for this project's
  tasks (Kanban is built for coordinating Hermes's *own* internal subagents,
  a different concern with a different status vocabulary). Hermes's native
  `memory`/session recall stay enabled — that's Hermes's own conversational
  memory of you across sessions, not a duplicate of Echo's project RAG/
  decision store. `cronjob` also stays enabled and replaces the cahier des
  charges' `triggers.yaml` scheduler outright — no need to build one.
- Full reasoning for all of the above is in
  `config/hermes_agent_mcp.example.yaml`'s comments.
- **Dashboard**: Hermes Agent's own web UI supports dashboard plugins
  (manifest.json + a pre-built JS bundle using
  `window.__HERMES_PLUGIN_SDK__` + an optional `plugin_api.py` FastAPI
  router) — used here instead of building a second, separate Next.js
  frontend. `config/hermes_agent_dashboard/` is a full plugin: a
  "Hermes Ollama" tab showing projects, tasks, hardware telemetry (from
  `/system/status`), and HSE progression (from `/hse/progression`).
  `plugin_api.py` runs inside Hermes Agent's own process and proxies
  each request to this backend server-side (the browser-side JS can't
  reach this backend directly — different origin, and this backend's
  CORS is locked to `http://localhost:3000`). Built from NousResearch's
  own published example plugin's verbatim source (manifest shape, SDK
  globals, `plugin_api.py`'s `router = APIRouter()` convention) — see
  `config/hermes_agent_dashboard/README.md` for install steps and what
  isn't verified end-to-end.

**On your machine:**

```bash
# 1. Install Hermes Agent (Linux/macOS)
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
# On Windows, the installer above detects it and tells you to use instead:
#   iex (irm https://hermes-agent.nousresearch.com/install.ps1)

# 2. Copy config/hermes_agent_mcp.example.yaml's blocks into
# ~/.hermes/config.yaml: model provider (custom endpoint -> Ollama, model
# devstral — see above), this backend's MCP server, disabled native
# toolsets, plugins.enabled for the dashboard, and the pre_tool_call ->
# Aegis hook. Edit the hook's absolute path first.
# Backend must be running: uvicorn backend.main:app --host 0.0.0.0 --port 8000

# 3. Install the dashboard plugin (optional, replaces the Next.js frontend)
mkdir -p ~/.hermes/plugins/hermes-ollama
cp -r config/hermes_agent_dashboard ~/.hermes/plugins/hermes-ollama/dashboard
# Then add plugins.enabled: [hermes-ollama] to config.yaml — see that
# plugin's own README for why this step is easy to miss and what breaks
# without it.
```

The MCP server is mounted at `/mcp` on the same FastAPI app (`backend/mcp_server/`,
tools in `backend/mcp_server/server.py`) — verified end-to-end with the
official `mcp` Python SDK client over the real streamable-HTTP protocol
*and* with a live Hermes Agent install (`hermes mcp test hermes-ollama`,
42 tools: `security_evaluate`, `files_*`, `memory_*`, `research_query`,
`verify_output`, `write_document`, `analyze_image`, `classify_request`,
`tasks_*`, `messages_list`, `system_status`, `workflows_*`, `projects_*`,
`skills_*`, `hse_process_task`, `hse_progression`).
The `pre_tool_call` hook script (`config/hermes_agent_hooks/aegis_gate.py`)
is confirmed working end-to-end on real hardware: `hermes hooks test
pre_tool_call --for-tool terminal` blocks correctly against Hermes's own
synthetic-payload harness, and a live run (Hermes Agent on `devstral`,
`terminal` toolset temporarily re-enabled for the test) attempted a real
native tool call, got blocked here, and surfaced the block to the user
instead of executing anything.

## Adding a real agent

1. Write `backend/agents/<name>.py` implementing `BaseAgent`.
2. Flip `enabled: true` for it in `config/agents.yaml`.
3. Add any new task types it needs to `config/models.yaml`'s `routing` map.

No other file should need to change — this is the whole point of the
config-driven registry (see cahier des charges §7, principle 6).
