# Workspace & Sandbox Architecture (HOS-045)

## Overview

The Workspace & Sandbox Manager provides isolated execution environments for agents. Each agent gets its own workspace with a Git feature branch, sandboxed environment, artifact versioning, and policy enforcement.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      WorkspaceManager                             │
│                                                                  │
│  ┌────────────────┐  ┌──────────────┐  ┌──────────────────┐     │
│  │ SandboxManager │  │ArtifactMgr   │  │   GitWorkspace   │     │
│  │ (work dir,     │  │ (versioning, │  │ (branches,       │     │
│  │  env vars,     │  │  checksums,  │  │  commits, merge, │     │
│  │  read-only,    │  │  7 types)    │  │  rollback, stash)│     │
│  │  network,      │  │              │  │                   │     │
│  │  tools, temp)  │  │              │  │                   │     │
│  └───────┬────────┘  └──────┬───────┘  └────────┬──────────┘     │
│          │                  │                   │                 │
│  ┌───────┴──────────────────┴───────────────────┴──────────┐     │
│  │              WorkspacePolicyEngine                      │     │
│  │  disk_quota (90% warn, 100% deny), max_duration,       │     │
│  │  read_only, network, allowed_tools                     │     │
│  └──────────────────────────────────────────────────────────┘     │
│                                                                  │
│  Storage: workspaces[], by_agent{}, by_mission{}                 │
│  EventBus → workspace.* + sandbox.* + artifact.* + git.*         │
└──────────────────────────────────────────────────────────────────┘
```

## Components

### WorkspaceManager
- **create**: new workspace per agent/mission with disk/time quotas
- **open/lock/release**: lifecycle transitions
- **archive/destroy**: cleanup
- Queries: by agent, by mission, list all

### SandboxManager
- **create**: isolated environment with custom env vars
- **start/stop/destroy**: lifecycle
- Controls: read_only, network_access, allowed_tools, max_temp_mb
- Auto-cleanup on destroy
- Future backends: Docker, Podman, Firecracker, WSL (not implemented)

### ArtifactManager
- 7 types: FILE, PATCH, REPORT, LOG, DOCUMENTATION, TEST_RESULT, OTHER
- Automatic versioning (v1, v2, ...)
- SHA256 checksums
- Query by workspace, agent, type, name

### GitWorkspace
- Feature branches only (never touches main directly)
- commit (with hash), merge, rollback, stash
- Track branches + commits per workspace
- Replaceable abstraction (future VCS)

### WorkspacePolicyEngine
- Built-in: disk_quota_warning (90%), disk_quota_deny (100%), max_duration, read_only
- Custom policies via register()
- evaluate() returns per-policy actions, check() returns strictest

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | /workspace | Create workspace |
| GET | /workspace?agent_id=&mission_id= | List workspaces |
| GET | /workspace/{id} | Get workspace |
| DELETE | /workspace/{id} | Destroy workspace |
| POST | /workspace/{id}/lock | Lock |
| POST | /workspace/{id}/release | Release |
| GET | /workspace/{id}/status | Status + policy check |
| GET | /workspace/{id}/artifacts | List artifacts |

## Events

| Event | Trigger |
|---|---|
| workspace.created | New workspace |
| workspace.opened | Workspace activated |
| workspace.locked | Write protection enabled |
| workspace.released | Lock released |
| workspace.archived | Workspace archived |
| sandbox.created | Sandbox created for agent |
| sandbox.destroyed | Sandbox destroyed |
| artifact.created | New artifact (v1) |
| artifact.updated | New version of existing artifact |
| git.branch_created | Feature branch created |
| git.commit_created | Commit recorded |

## Example: Two Agents Working in Parallel

```
Mission: "Build API"
  ├─ CoderAgent → workspace_1
  │   └─ git branch: feature/backend
  │   └─ commit: "Add API endpoints" (hash: a1b2c3d4)
  │   └─ artifacts: [api.py v1]
  │   └─ sandbox: {root: /tmp/hermes/ws1/coder, env: {DEBUG: "true"}}
  │
  ├─ ReviewerAgent → workspace_2
  │   └─ git branch: feature/review
  │   └─ commit: "API review complete" (hash: e5f6g7h8)
  │   └─ sandbox: {root: /tmp/hermes/ws2/reviewer, read_only: true}
  │
  └─ Merge: feature/backend → main ✅
     Merge: feature/review → main ✅
```

## Integration Points

- **AgentSupervisor (HOS-043)**: creates workspace on task assignment, releases on completion
- **Mission Graph (HOS-041)**: workspace tied to mission_id + node_id
- **Event Bus (HOS-034)**: publishes all lifecycle events

## Validation

- pytest: 48/48 passed
- Thread safety: concurrent workspace creation (20 threads), sandbox creation (15 threads), artifacts (10 threads)
- 1028+ total architecture tests (HOS-000 through HOS-045)
