# Agent Supervisor Architecture (HOS-043)

## Overview

The Agent Supervisor is the central orchestrator for agent-based task execution in Hermes OS. It receives MissionNodes from the Mission Graph Engine (HOS-041), matches them to specialized agents via capability-based scoring, dispatches tasks, tracks execution, and collects metrics.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    AgentSupervisor                            │
│                                                              │
│  ┌────────────────┐  ┌──────────────────┐                   │
│  │  AgentRegistry │  │ CapabilityMatcher │                   │
│  │  (indexes: cap, │  │ (scoring: 5      │                   │
│  │   status, id)   │  │  weighted factors)│                  │
│  └───────┬────────┘  └────────┬─────────┘                   │
│          │                    │                              │
│  ┌───────▼────────────────────▼─────────┐                    │
│  │          TaskDispatcher              │                    │
│  │  select → context → execute → result │                    │
│  └───────┬────────────────────┬─────────┘                    │
│          │                    │                              │
│  ┌───────▼────────┐  ┌────────▼──────────┐                  │
│  │ AgentLifecycle │  │ ExecutionContext  │                  │
│  │ (10 states,    │  │ Manager           │                  │
│  │  validated     │  │ (by agent/mission)│                  │
│  │  transitions)  │  │                   │                  │
│  └────────────────┘  └───────────────────┘                  │
│                                                              │
│  EventBus ← agent.{created,started,ready,busy,...}          │
│  EventBus ← task.{assigned,reassigned,completed,failed}     │
└──────────────────────────────────────────────────────────────┘
```

## Components

### AgentRegistry
- Thread-safe registry with multi-index: by ID, capability, status
- Query methods: `find_by_capability`, `find_by_capabilities` (ALL), `find_by_any_capability` (ANY), `find_by_status`, `find_available`
- Metrics tracking: `update_metrics(agent_id, duration_ms, success)`

### CapabilityMatcher
- 5-factor weighted scoring: capability (30%), load (25%), availability (20%), history (15%), runtime preference (10%)
- Task type → capability mapping (12 types mapped)
- Skill name → capability conversion

### AgentLifecycle
- 10 states: CREATED → STARTING → READY ⇄ BUSY → COMPLETED/FAILED/STOPPED
- RECOVERING: FAILED → RECOVERING → READY
- PAUSED: READY ⇄ PAUSED
- All transitions validated, history tracked, events emitted

### TaskDispatcher
- Pipeline: select agent → create context → mark busy → execute → record result → mark ready
- Supports reassignment (task.reassigned events)
- Result tracking by mission and agent

### AgentSupervisor
- `create_agent(name, capabilities, ...)` — creates and starts agent
- `dispatch_node(mission, node)` — single node dispatch
- `execute_mission_step(mission)` — dispatches all ready nodes
- `execute_full_mission(mission)` — processes entire DAG
- `reassign_node(mission, node)` — reassigns to different agent

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | /agents | List all agents |
| POST | /agents | Create new agent |
| GET | /agents/{id} | Agent details + history + tasks |
| GET | /agents/status | Registry statistics |
| GET | /agents/metrics | All agent metrics |
| POST | /agents/{id}/start | Start (resume) agent |
| POST | /agents/{id}/stop | Stop agent |
| POST | /agents/{id}/pause | Pause agent |

## Events Published

| Event | Trigger |
|---|---|
| agent.created | New agent registered |
| agent.started | Agent transitions to STARTING |
| agent.ready | Agent is READY for tasks |
| agent.busy | Agent assigned a task |
| agent.completed | Agent completed lifecycle |
| agent.failed | Agent entered FAILED state |
| agent.stopped | Agent stopped |
| task.assigned | Task dispatched to agent |
| task.reassigned | Task moved to different agent |
| task.dispatch_failed | No suitable agent found |

## Integration Points

- **Mission Graph (HOS-041)**: receives MissionNode with type/skills/priority
- **Runtime Orchestrator (HOS-038)**: callback for runtime selection per agent
- **Event Bus (HOS-034)**: publishes all lifecycle and task events

## Example: Multi-Agent Mission Execution

```
Mission: "Build Auth System"
  ├─ n1: "Design architecture"      → DesignerAgent  (design)
  ├─ n2: "Implement backend"        → CoderAgent     (implementation, depends: n1)
  ├─ n3: "Write tests"              → CoderAgent     (testing, depends: n2)
  └─ n4: "Code review"              → ReviewerAgent  (review, depends: n2 + n3)

Execution order:
  Step 1: n1 dispatched → DesignerAgent (→ COMPLETED)
  Step 2: n2 dispatched → CoderAgent    (→ COMPLETED)
  Step 3: n3 dispatched → CoderAgent ∥ n4 dispatched → ReviewerAgent
```

## Validation

- pytest: 49/49 passed
- Thread safety: concurrent agent creation + concurrent dispatch tested
- 916+ total architecture tests (HOS-000 through HOS-043)
