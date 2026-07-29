# MCP & External Tools Platform Architecture (HOS-049)

## Overview

The Tools Platform provides a centralized, secure, and observable layer for using external tools. MCP (Model Context Protocol) is treated as one connector among several types of external integrations.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     ToolExecutor                                  │
│            (Pipeline: Policy → Sandbox → Execute)                 │
├──────────────┬──────────────┬──────────────┬─────────────────────┤
│  ToolRouter  │  ToolPolicy  │ ToolSandbox  │    ToolHealth       │
│  (auto-      │  (govern     │ (isolate     │  (monitor)          │
│   selection) │   ance)      │  execution)  │                     │
├──────────────┴──────────────┴──────────────┴─────────────────────┤
│                     ToolRegistry                                  │
│          (index: type, category, status, tag)                     │
├──────────────────────────────────────────────────────────────────┤
│                     ToolMemory                                    │
│          (Knowledge Graph: Agent → Tool → Mission → Result)       │
└──────────────────────────────────────────────────────────────────┘
```

## Components

### ToolRegistry (`tool_registry.py`)
Thread-safe with 4 indexes: by ToolType (8 types), ToolCategory (7 categories), ToolStatus (4 states), and tags.

### ToolPolicy (`tool_policy.py`)
- ALLOW / DENY / REVIEW_REQUIRED verdicts
- Rules: admin requires review, timeout limits, disabled tools denied
- Configurable per-tool rules

### ToolSandbox (`tool_sandbox.py`)
- Path validation (allowed/denied)
- Network control (allowed hosts)
- Environment variables
- Memory/disk/duration limits
- Integration with Workspace Manager (HOS-045)

### ToolExecutor (`tool_executor.py`)
Pipeline: `Policy → Sandbox → Execute → Metrics → Result`
- Pluggable executor functions per tool
- Cancellation support
- History (1000 entries)

### ToolRouter (`tool_router.py`)
- Category inference from action keywords
- Type preference bonus
- Health-aware scoring
- Fallback to any available tool

### ToolHealth (`tool_health.py`)
- Health checks with configurable check functions
- Latency tracking
- Error counters
- All-check support

### ToolMemory (`tool_memory.py`)
Records into Knowledge Graph:
```
Agent → Tool → Mission → Result → Performance → Experience
```

## MCP Platform

See [MCP_ARCHITECTURE.md](MCP_ARCHITECTURE.md)

## Connectors (7)

| Connector | Actions |
|---|---|
| `GitHubConnector` | repo, branches, commits, PRs, issues, create_branch, commit, create_pr, create_issue |
| `GitLabConnector` | project, branches, commits, MRs, issues, create_branch, commit, create_mr, create_issue |
| `DockerConnector` | images, containers, logs, start, stop, remove |
| `DatabaseConnector` | schema_inspect, query, list_tables (PG + SQLite) |
| `FilesystemConnector` | read, write, list, search, stat |
| `RestAPIConnector` | GET, POST, PUT, DELETE, HEAD |
| `BrowserConnector` | navigate, extract_text, screenshot, click, fill |

## Execution Pipeline

```
ToolRequest → ToolPolicy.evaluate()
    → ALLOW/DENY/REVIEW_REQUIRED
    → ToolSandbox.validate()
    → ToolExecutor (registered fn)
    → ToolResult
    → ToolHealth.record_execution()
    → ToolMemory.record() → Knowledge Graph
```

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/tools` | List tools (filter: type, category, status, tag) |
| `GET` | `/tools/{id}` | Tool detail + health instance + memory stats |
| `POST` | `/tools/register` | Register a new tool |
| `POST` | `/tools/execute` | Execute a tool action |
| `POST` | `/tools/select` | Auto-select best tool |
| `GET` | `/tools/health` | Health overview |
| `GET` | `/tools/metrics` | Global metrics |
| `GET` | `/mcp/servers` | List MCP servers |
| `POST` | `/mcp/connect` | Connect to MCP server |
| `POST` | `/mcp/disconnect` | Disconnect from MCP server |

## Example: Fix a GitHub bug

```
1. Mission Planner → "Fix login bug"
2. Agent Coder → SkillSelector → "github-tool" skill
3. ToolRouter.select("fix github bug") → GitHubConnector (0.8)
4. ToolPolicy.evaluate() → ALLOW
5. ToolSandbox.create_for_agent("github", "coder-agent", "ws-001")
6. ToolExecutor.execute → GitHubConnector.create_branch("fix/login")
7. GitHubConnector.commit → SHA: def456
8. ToolMemory.record → Knowledge Graph updated
9. Audit log → policy.audit.created
```
