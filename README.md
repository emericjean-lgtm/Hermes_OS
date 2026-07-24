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
`models.yaml`'s routing matrix, `/classify`), and an **MCP server**
exposing Aegis/Atlas/Echo/Kronos/Minerva/Veritas/Hermes Scribe/Hermes
Eyes/Hermes Swift as tools (see "Hermes Agent integration" below). 144
tests passing. Still not implemented: the message bus, workflows, HSE,
GPU monitoring, Telegram — see `config/agents.yaml` for the full agent
roster (`enabled: false` = not built yet).

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

[Hermes Agent](https://hermes-agent.nousresearch.com/) (NousResearch's
open-source agent runtime — unrelated to this project's own name, which is
thematic) is meant to replace `core/router.py` + `agents/hermes_prime.py` as
the primary orchestrator: it decides which model to use and drives the
conversation, while this backend's Aegis/Atlas/Echo/Kronos stay exactly as
built and get called as **MCP tools** instead of via `/chat`.

**On your machine** (this integration can't be installed or live-tested from
a sandboxed session — `hermes-agent.nousresearch.com` is blocked by this
environment's network policy; everything up to that install step has been
built and tested here):

```bash
# 1. Install Hermes Agent
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash

# 2. Point its model provider at your local Ollama
hermes model
# -> choose "Custom endpoint" -> http://127.0.0.1:11434/v1

# 3. Connect it to this backend's MCP server (Aegis/Atlas/Echo/Kronos as tools)
# Backend must be running: uvicorn backend.main:app --host 0.0.0.0 --port 8000
# Copy config/hermes_agent_mcp.example.yaml into Hermes Agent's mcp_servers config.
```

The MCP server is mounted at `/mcp` on the same FastAPI app (`backend/mcp_server/`,
tools in `backend/mcp_server/server.py`) — verified end-to-end with the
official `mcp` Python SDK client over the real streamable-HTTP protocol
(20 tools: `security_evaluate`, `files_*`, `memory_*`, `research_query`,
`verify_output`, `write_document`, `analyze_image`, `classify_request`,
`tasks_*`).

## Adding a real agent

1. Write `backend/agents/<name>.py` implementing `BaseAgent`.
2. Flip `enabled: true` for it in `config/agents.yaml`.
3. Add any new task types it needs to `config/models.yaml`'s `routing` map.

No other file should need to change — this is the whole point of the
config-driven registry (see cahier des charges §7, principle 6).
