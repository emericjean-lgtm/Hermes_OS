# Autonomous Mission Execution Architecture (HOS-050)

## Overview

The Autonomous Mission Execution Engine is the central orchestrator of Hermes OS. It takes a user goal and autonomously executes it through the complete pipeline: planning, scheduling, agent assignment, skill distribution, runtime selection, tool execution, validation, memory updates, and optimization.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                     ExecutionController                               │
│       (Lifecycle: start / pause / resume / cancel / finalize)        │
├──────────────────────────────────────────────────────────────────────┤
│                     MissionExecutor                                   │
│      (Pipeline: Goal → Plan → Schedule → Execute → Validate → Feed)  │
├──────────────┬──────────────┬──────────────┬─────────────────────────┤
│ TaskScheduler│AgentCoord.   │ValidationEng.│  FeedbackLoop           │
│ (waves,      │(agent+skill  │(PASS/FAIL/   │  (learnings,            │
│  parallel,   │ +runtime+    │ RETRY/NEEDS  │   recommendations)      │
│  deps)       │  tool)       │  _REVIEW)    │                         │
├──────────────┴──────────────┴──────────────┴─────────────────────────┤
│                     OptimizationEngine                                │
│       (slow tasks detection, runtime issues, recommendations)         │
├──────────────────────────────────────────────────────────────────────┤
│                     ExecutionStateMachine                             │
│       (10 states, valid transitions, checkpoints, rollback)           │
└──────────────────────────────────────────────────────────────────────┘
```

## State Machine

```
CREATED → PLANNING → READY → RUNNING ─┬─→ VALIDATING → COMPLETED
                      ↑       ↓       │       ↓
                  CANCELLED  PAUSED    │     FAILED
                             ↓        │       ↓
                          RUNNING     │    RUNNING (retry)
                                      │
                            WAITING_APPROVAL
```

### Valid Transitions

| From | To |
|---|---|
| CREATED | PLANNING, CANCELLED |
| PLANNING | READY, FAILED, CANCELLED |
| READY | RUNNING, CANCELLED |
| RUNNING | PAUSED, WAITING_APPROVAL, VALIDATING, FAILED, COMPLETED, CANCELLED |
| WAITING_APPROVAL | RUNNING, FAILED, CANCELLED |
| PAUSED | RUNNING, CANCELLED |
| VALIDATING | COMPLETED, RUNNING, FAILED, CANCELLED |
| FAILED | RUNNING (retry), CANCELLED |

## Components

### ExecutionStateMachine (`execution_state.py`)
- Thread-safe (RLock)
- 10 states with validated transitions
- Checkpoint system (AUTO, PAUSE, PRE_VALIDATION, PRE_TOOL, MANUAL)
- History tracking

### TaskScheduler (`task_scheduler.py`)
- DAG-aware scheduling with parallel waves
- 4 strategies: PARALLEL, SEQUENTIAL, PRIORITY, RESOURCE_AWARE
- Dependency resolution and blocking detection
- Progress tracking

### AgentCoordinator (`agent_coordinator.py`)
- Optimal agent/skills/runtime/tools selection per task
- Capability matching with keyword scoring
- Agent load tracking and release
- Confidence scoring per assignment

### ValidationEngine (`validation_engine.py`)
- Post-execution validation with configurable criteria
- 4 outcomes: PASS, FAIL, RETRY, NEEDS_REVIEW
- Max retries enforcement (3 default)

### FeedbackLoop (`feedback_loop.py`)
- Post-mission analysis: efficiency, learnings, recommendations
- Structured inputs for Memory Manager and Runtime Intelligence
- Error pattern extraction

### OptimizationEngine (`optimization_engine.py`)
- Slow task identification (>2x expected duration)
- Runtime underperformance detection (avg >10s)
- Category-based recommendations (RUNTIME, SKILL, AGENT, TOOL, SCHEDULE, RESOURCE)

### MissionExecutor (`mission_executor.py`)
- Central pipeline orchestration
- Simulated EventBus (8 event types)
- Full prepare → execute → finalize lifecycle

### ExecutionController (`execution_controller.py`)
- Multi-execution management
- Lifecycle: start, pause, resume, cancel, finalize
- Timeline and statistics

## Integration Points

| Layer | Integration |
|---|---|
| Mission Planner (HOS-042) | Receives tasks from planner |
| Agent Supervisor (HOS-043) | Assigns agents via coordinator |
| Skill Distributor (HOS-048) | Skill selection per task |
| Runtime Orchestrator (HOS-038) | Runtime selection per task |
| Policy Engine (HOS-046) | Pre-execution approval |
| Memory Manager (HOS-047) | Post-mission memory updates |
| Tool Platform (HOS-049) | Tool selection per task |
| Recovery Engine (HOS-036) | Triggered on validation failure |
| Event Bus (HOS-034) | All execution events published |

## REST API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/execution/start` | Start autonomous execution |
| `GET` | `/execution/{id}` | Get execution state |
| `GET` | `/execution` | List all executions |
| `POST` | `/execution/{id}/pause` | Pause execution |
| `POST` | `/execution/{id}/resume` | Resume execution |
| `POST` | `/execution/{id}/cancel` | Cancel execution |
| `GET` | `/execution/{id}/timeline` | Full timeline |
| `GET` | `/execution/statistics` | Global statistics |

## Events Published

| Event | Description |
|---|---|
| `execution.started` | New execution created |
| `execution.planning` | Tasks registered and scheduled |
| `execution.task_started` | Single task execution begins |
| `execution.task_completed` | Task completed successfully |
| `execution.waiting_approval` | Task needs human approval |
| `execution.failed` | Task or mission failed |
| `execution.completed` | Mission completed |
| `execution.optimized` | Optimizations generated |

## Complete Execution Flow

```
POST /execution/start { goal: "Créer une application web" }
  ↓
MissionExecutor.prepare()
  → ExecutionStateMachine: CREATED → PLANNING → READY
  → TaskScheduler: registers tasks with dependencies
  → Event: execution.started, execution.planning
  ↓
MissionExecutor.execute_task("t1")
  → AgentCoordinator.assign() → agent: coder, skills: [python-coding], runtime: ollama
  → Simulated execution → result: "Simulated result for: ..."
  → ValidationEngine.validate() → PASS
  → Event: execution.task_started, execution.task_completed
  ↓
MissionExecutor.finalize()
  → ExecutionReport: state=COMPLETED, tasks=3, efficiency=100%
  → FeedbackLoop.analyze() → learnings extracted
  → OptimizationEngine.record_execution()
  → Event: execution.completed, execution.optimized
  ↓
Memory updates + Knowledge Graph enrichment
```

## Tests

- **TestExecutionStateMachine**: 12 tests (transitions, checkpoints, pause/resume, cancel, stats)
- **TestTaskScheduler**: 8 tests (registration, dependencies, waves, progress, done)
- **TestAgentCoordinator**: 7 tests (assign, load, runtime, skills, fallback, stats)
- **TestValidationEngine**: 6 tests (pass, fail, retry, needs_review, stats)
- **TestFeedbackLoop**: 5 tests (success, failure, memory input, intelligence input, stats)
- **TestOptimizationEngine**: 4 tests (slow tasks, runtime issues, recommendations, stats)
- **TestMissionExecutor**: 9 tests (prepare, execute, finalize, pause/resume, cancel, timeline, events, stats)
- **TestExecutionController**: 8 tests (start, get, execute, pause, cancel, finalize, timeline, list, stats)
- **TestRoutes**: 10 tests (start, dependencies, get, list, pause, resume, cancel, timeline, stats)
- **TestThreadSafety**: 3 tests (concurrent registration, concurrent execution, concurrent state transitions)

**Total: 72 tests**
