# Hermes Ollama

Local, single-user AI copilot orchestrating Ollama models through a
multi-agent backend. Full specification: **[CAHIER_DES_CHARGES_HERMES_OLLAMA.md](./CAHIER_DES_CHARGES_HERMES_OLLAMA.md)**
— read it first, it is the source of truth for scope, architecture, and
target hardware (AMD RX 6800 16 GB / i5-13500 / 32 GB DDR5).

## Current state: walking skeleton

This repository currently implements the minimal end-to-end slice needed to
build on top of: a config-driven model router, a mockable Ollama client, the
Hermes Prime orchestrator agent, a streaming `/chat` API, and a minimal Chat
page. Everything else in the cahier des charges (the other 9 agents, memory,
tasks, workflows, Aegis, monitoring, HSE, Telegram...) is designed for but
not yet implemented — see `config/agents.yaml` for the full agent roster
declared with `enabled: false`.

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

uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

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

## Adding a real agent

1. Write `backend/agents/<name>.py` implementing `BaseAgent`.
2. Flip `enabled: true` for it in `config/agents.yaml`.
3. Add any new task types it needs to `config/models.yaml`'s `routing` map.

No other file should need to change — this is the whole point of the
config-driven registry (see cahier des charges §7, principle 6).
