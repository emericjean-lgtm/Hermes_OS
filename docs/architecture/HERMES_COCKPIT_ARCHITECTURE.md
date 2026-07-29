# Hermes Mission Center & AI Operations Cockpit (HOS-051)

## Overview

The Hermes Cockpit is a unified Next.js 15 frontend that provides complete visibility and control over Hermes OS. It consolidates all backend modules (missions, agents, runtime, memory, skills, tools, governance, events) into a single dark-themed, real-time operations interface.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         Topbar                                    │
│     System Health · Uptime · Version · WebSocket Status          │
├──────────┬───────────────────────────────────────────────────────┤
│          │                                                        │
│  Sidebar │  Active View (9 total)                                 │
│          │                                                        │
│  Dashboard│  ┌──────────────────────────────────────────────────┐│
│  Missions │  │  Feature Center Component                        ││
│  Agents   │  │  (Mission / Agent / Runtime / Memory / Skills /  ││
│  Runtime  │  │   Tools / Governance / Events)                   ││
│  Memory   │  │                                                  ││
│  Skills   │  │  • Cards · Stats · Tables · Charts               ││
│  Tools    │  │  • Live WebSocket stream                         ││
│  Governance│  │  • Actions: approve / reject / start / pause /  ││
│  Events   │  │    resume / cancel                               ││
│          │  └──────────────────────────────────────────────────┘│
├──────────┴───────────────────────────────────────────────────────┤
│                        StatusBar                                  │
│   Missions · Agents · Runtimes · Memory · Events Live Counts     │
└──────────────────────────────────────────────────────────────────┘
```

## Views

### 1. Dashboard
Overview of the entire Hermes OS system:
- System health status (HEALTHY/DEGRADED/UNHEALTHY)
- Key metrics: active missions, completed, failed, active agents, pending approvals
- Runtime health overview
- Live event stream (last 10 events)
- Recent missions with progress bars
- Active agents with status badges

### 2. Mission Center
DAG-based autonomous mission orchestration:
- Mission list with status/priority/progress
- Create new missions
- View mission details (nodes, dependencies, type, priority)
- Actions: start, pause, resume, cancel
- Progress tracking per mission

### 3. Agent Center
Multi-agent supervision & collaboration:
- Agent status overview (READY/BUSY/ERROR/COMPLETED)
- Agent list with capabilities and runtime
- Agent detail with metrics (tasks completed, success rate, tokens)
- Collaboration messages live feed

### 4. Runtime Center
Model health, resources & intelligent selection:
- Live resource monitoring (CPU/RAM/VRAM/GPU temp)
- Runtime cards with reliability & performance bars
- Circuit breaker status (CLOSED/OPEN/HALF_OPEN)
- Latency, success rate, execution count per runtime

### 5. Memory Center
Unified memory, knowledge graph & retrieval:
- Hybrid search (graph + embeddings + keyword)
- Knowledge graph node visualization
- Experience cards (success/failure with learnings)
- Memory statistics

### 6. Skills Center
Dynamic skill distribution & intelligent selection:
- Automatic skill selection by task description
- Skill registry (name, status, tags, metrics)
- Cache status viewer
- Success rate and memory usage per skill

### 7. Tools Center
MCP Platform & external tools governance:
- Native tools list (GitHub, GitLab, Docker, etc.)
- MCP server connections
- Tool health overview (latency, success rate)
- Permission badges

### 8. Governance Center
Human approval, policy engine & audit trail:
- Pending approval requests with approve/reject actions
- Policy rules (ALLOW/DENY/REVIEW_REQUIRED)
- Audit log with timestamps, principals, operations, results

### 9. Event Center
Real-time event bus & system observability:
- Live event stream via WebSocket
- Severity filters (INFO/WARNING/ERROR/CRITICAL)
- Source filters
- Correlation ID tracking
- Auto-reconnect with backoff

## Data Flow

```
Backend FastAPI                 Frontend Next.js
    │                               │
    ├── REST /api/v1/* ──────► React Query Hooks (30+)
    │   (70+ endpoints)           │
    │                               ├── Server State (auto-refresh)
    │                               └── Mutations (actions)
    │
    ├── WebSocket /ws/events ─► useWebSocket Hook
    │   (real-time events)       │
    │                               ├── Live Event Stream
    │                               └── Cockpit Store (Zustand)
    │
    └── TypeScript Types ─────► types/hermes.ts (60+ types)
```

## Component Architecture

```
CockpitShell
├── Sidebar (navigation)
├── Topbar (health, uptime, WS status)
├── Active View (1 of 9)
│   ├── DashboardView
│   ├── MissionCenter
│   ├── AgentCenter
│   ├── RuntimeCenter
│   ├── MemoryCenter
│   ├── SkillsCenter
│   ├── ToolsCenter
│   ├── GovernanceCenter
│   └── EventsCenter
└── StatusBar (live stats)
```

## API Client Structure

The `services/client.ts` provides strongly-typed fetch wrappers for all backend modules:

| Module | Client | Endpoints |
|---|---|---|
| System | `systemClient` | health, statistics, version |
| Missions | `missionsClient` | list, get, create, graph, timeline, progress, start, pause, resume, cancel |
| Agents | `agentsClient` | list, get, create, start, stop, pause, metrics |
| Collaboration | `collaborationClient` | messages, sendMessage, delegate, review, history |
| Runtime | `runtimeClient` | list, get, health, metrics, resources, allocations, release, select |
| Memory | `memoryClient` | search, searchAdvanced, graph, experiences, index, statistics |
| Skills | `skillsClient` | list, get, select, load, unload, cache, statistics |
| Tools | `toolsClient` | list, get, register, execute, select, health, metrics, mcpServers, mcpConnect, mcpDisconnect |
| Governance | `governanceClient` | rules, evaluate, approvals, approve, reject, audit |
| Execution | `executionClient` | start, get, list, pause, resume, cancel, timeline, statistics |
| Events | `eventsClient` | list |

## Hooks

### Data Fetching (React Query)
- `useSystemHealth()`, `useSystemStatistics()`
- `useMissions()`, `useMission(id)`, `useMissionGraph(id)`, `useMissionTimeline(id)`
- `useAgents()`, `useAgent(id)`
- `useRuntimes()`, `useRuntimeHealth()`, `useResourceStatus()`
- `useMemorySearch(q)`, `useKnowledgeGraph()`, `useExperiences()`
- `useSkills()`, `useSelectSkills(desc)`, `useSkillCache()`
- `useTools()`, `useToolsHealth()`, `useMCPServers()`
- `usePolicyRules()`, `useApprovals()`, `useAuditLog()`
- `useExecutions()`, `useExecution(id)`

### Mutations (React Query)
- `useCreateMission()`, `useMissionAction(id)` (start/pause/resume/cancel)
- `useCreateAgent()`
- `useSendMessage()`
- `useExecuteTool()`
- `useApproveAction()`, `useRejectAction()`
- `useStartExecution()`, `useExecutionAction(id)` (pause/resume/cancel)

### Real-time (WebSocket)
- `useWebSocket({ sources?, enabled? })` — events, connected, error, clearEvents

### State (Zustand)
- `useCockpitStore()` — activeView, liveEvents, filters, wsConnected, selectedMission/Agent

## Design System

### Colors
| Token | Value | Usage |
|---|---|---|
| `--hermes-bg` | `#0a0a0f` | Background |
| `--hermes-surface` | `#111118` | Sidebar/Topbar |
| `--hermes-card` | `#18181f` | Cards |
| `--hermes-border` | `#27272f` | Borders |
| `--hermes-amber` | `#f59e0b` | Primary accent |
| `--hermes-green` | `#22c55e` | Success/healthy |
| `--hermes-red` | `#ef4444` | Error/danger |
| `--hermes-blue` | `#3b82f6` | Info |
| `--hermes-purple` | `#8b5cf6` | Sources/runtimes |

### Components
- `Card` — bordered container with title, subtitle, action slot, Framer Motion fade-in
- `Badge` — 6 variants (default, success, warning, danger, info, purple)
- `StatCard` — metric display with label, value, description, trend indicator
- `ProgressBar` — animated bar with color by percentage (green ≥80%, amber ≥50%, red <50%)

## Stack

| Technology | Version | Purpose |
|---|---|---|
| Next.js | 15.1 | Framework |
| React | 19 | UI library |
| TypeScript | 5.7 | Type safety |
| TailwindCSS | 3.4 | Styling |
| TanStack React Query | 5 | Server state |
| Zustand | 5 | Client state |
| Framer Motion | 11 | Animations |
| Lucide React | latest | Icons |
| Vitest | 2.1 | Testing |
| Testing Library | 16 | Component testing |

## API Integration

All backend modules are accessible via the API client at `NEXT_PUBLIC_API_URL` (default: `http://localhost:8000/api/v1`).

WebSocket events are streamed from `NEXT_PUBLIC_WS_URL` (default: `ws://localhost:8000/ws/events`).
