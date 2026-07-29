# Hermes OS — Getting Started

## Overview

Hermes OS is a modular operating system for AI agents. It provides:

1. **Runtime Abstraction** — swap backends (Ollama, OpenAI, Anthropic) without code changes
2. **Task Orchestration** — DAG-based mission planning and execution
3. **Unified Memory** — scoped, queryable memory across all agents
4. **Skill Management** — adaptive selection of relevant skills per mission
5. **Event Bus** — central observability across all subsystems
6. **Mission Control** — unified API for the entire platform

## Architecture Layers

```
┌─────────────────────────────────────────────┐
│            Service Layer (HOS-027)          │
│         MissionControlService Façade        │
├─────────────────────────────────────────────┤
│     API Layer (HOS-028)                     │
│     REST /api/v1/* + WebSocket /ws/events   │
├────────────────┬───────────────┬────────────┤
│  Agent Layer   │ Runtime Layer │   Mem/     │
│  (HOS-017-024) │ (HOS-004-016) │ Skills/E   │
│  ExecutionGraph│ RuntimeRouter │ UnifiedMem │
│  TaskPlanner   │ DecisionEngine│ SkillOrch  │
│  Supervisor    │ Recovery      │ SystemBus  │
│  Lifecycle     │ Health/Monitor│            │
└────────────────┴───────────────┴────────────┘
```

## Quick Start

```bash
# Install and start
pip install -r backend/requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Try the API
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/runtimes
curl http://localhost:8000/api/v1/version

# Run tests
pytest tests/architecture/
```

## Next Steps

- Read the [Architecture](ARCHITECTURE.md) document
- Explore the [API endpoints](../api/endpoints.md)
- Check the [Roadmap](../roadmap/development.md)
