# Hermes Ollama

Local, single-user AI copilot orchestrating Ollama models through a
multi-agent backend. Full specification: **[CAHIER_DES_CHARGES_HERMES_OLLAMA.md](./CAHIER_DES_CHARGES_HERMES_OLLAMA.md)**
— read it first, it is the source of truth for scope, architecture, and
target hardware (AMD RX 6800 16 GB / i5-13500 / 32 GB DDR5).

## Current state

Built and tested so far: a config-driven model router, a mockable Ollama
client, the Hermes Prime orchestrator agent, a streaming `/chat` API, a
minimal Chat page, **Aegis** (deterministic security gate, `/security/evaluate`),
**Atlas** (Aegis-gated file tools with diff + backup, `/files*`), **Echo**
(SQLite long-term memory + ChromaDB documentary/RAG memory, `/memory*`),
**Kronos** (task tracking with status/history, `/tasks*`), **Minerva**
(research/RAG agent: retrieves passages from Echo's documentary memory,
synthesizes a cited answer, `/research`), **Veritas** (QA agent: reviews
another agent's output and returns a parsed verdict — approved /
needs_revision / rejected — plus issues and corrections, `/verify`),
**Hermes Scribe** (writing/documentation agent: brief -> document,
`/write`), **Hermes Eyes** (vision agent: multimodal image analysis via
`gemma3:12b`, `/vision/analyze`), **Hermes Swift** (always-on, ultra-fast
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
`simulate()` is a pure dry-run. `/workflows*` REST API, example workflow
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
and an **MCP server** exposing Aegis/Atlas/Echo/Kronos/Minerva/Veritas/Hermes
Scribe/Hermes Eyes/Hermes Swift as tools plus the bus's `messages_list`,
the workflow engine's `workflows_*`, and `projects_*` (see "Hermes Agent
integration" below). 263 tests passing. Still not implemented: HSE, GPU
monitoring — see `config/agents.yaml` for the full agent roster
(`enabled: false` = not built yet). Telegram and workflow scheduling
(`triggers.yaml`) are no longer planned as our own builds — Hermes
Agent's native gateway and `cronjob` cover both, see "Hermes Agent
integration" below.

**Important:** this environment has no AMD GPU / ROCm. The backend was
built and tested here entirely against a fake Ollama client (see
`backend/tests/`), so the routing/agent/API logic is verified, but real
model inference has not been. Pull this branch onto your Ubuntu/ROCm
machine and follow the ROCm + Ollama install steps in the cahier des
charges (§25) before testing actual generation quality and speed.

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
ollama pull qwen3:8b   # default "standard" model used by the walking skeleton
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
orchestrator. Based on reviewing its actual feature set (its docs site is
unreachable from this sandbox, but the GitHub repo/docs aren't):

- **Hermes Agent runs on one model per session** — it has no per-task-type
  routing of its own. That's fine: Hermes becomes the planning/conversation
  brain on this project's `orchestrator` model (`hermes3:8b`), while every
  specialized per-task model choice (`qwen3:8b` for Minerva, `deepseek-r1:14b`
  for Veritas, `gemma3:12b` for Eyes...) still happens *inside* the MCP tools
  below — Hermes never needs to know about it, this project's "one model per
  role" principle (cahier des charges §7) is unaffected.
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

**On your machine** (this integration can't be installed or live-tested from
a sandboxed session — `hermes-agent.nousresearch.com` is blocked by this
environment's network policy; everything up to that install step has been
built and tested here):

```bash
# 1. Install Hermes Agent
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash

# 2. Copy config/hermes_agent_mcp.example.yaml's blocks into
# ~/.hermes/config.yaml: model provider (custom endpoint -> Ollama),
# this backend's MCP server, disabled native toolsets, and the
# pre_tool_call -> Aegis hook. Edit the hook's absolute path first.
# Backend must be running: uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

The MCP server is mounted at `/mcp` on the same FastAPI app (`backend/mcp_server/`,
tools in `backend/mcp_server/server.py`) — verified end-to-end with the
official `mcp` Python SDK client over the real streamable-HTTP protocol
(32 tools: `security_evaluate`, `files_*`, `memory_*`, `research_query`,
`verify_output`, `write_document`, `analyze_image`, `classify_request`,
`tasks_*`, `messages_list`, `workflows_*`, `projects_*`). The `pre_tool_call` hook script
(`config/hermes_agent_hooks/aegis_gate.py`) is built strictly from Hermes
Agent's published hook contract — not exercised end-to-end from this
sandbox, so verify it against your real installation before relying on it.

## Adding a real agent

1. Write `backend/agents/<name>.py` implementing `BaseAgent`.
2. Flip `enabled: true` for it in `config/agents.yaml`.
3. Add any new task types it needs to `config/models.yaml`'s `routing` map.

No other file should need to change — this is the whole point of the
config-driven registry (see cahier des charges §7, principle 6).
