# Dynamic Skill Distribution Engine Architecture (HOS-048)

## Overview

The Skill Distribution Engine dynamically assigns skills to agents based on mission requirements. Instead of agents loading all skills upfront, they receive only the skills necessary for their assigned task — optimized by historical performance, category match, and technology overlap.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    SkillDistributor                               │
│               (Mission → Agents → Skills)                         │
├──────────────┬──────────────┬──────────────┬─────────────────────┤
│ SkillSelector│   SkillCache │  SkillLoader │ SkillProfiler       │
│ (6-factor    │  (LRU/TTL/   │ (lazy/hot    │ (load/memory/       │
│  scoring)    │   Priority)  │  reload)     │  token/success)     │
├──────────────┴──────────────┴──────────────┴─────────────────────┤
│                  SkillRegistry                                    │
│         (index: category, domain, tag, status)                    │
├──────────────────────────────────────────────────────────────────┤
│           DependencyResolver                                      │
│    (transitive deps, topological sort, cycle detection)           │
└──────────────────────────────────────────────────────────────────┘
```

## Components

### SkillRegistry (`skill_registry.py`)
Thread-safe registry with 4 indexes:
- By category (coding, reasoning, writing, analysis, security, deployment, testing, documentation, general)
- By domain (backend, frontend, devops, data, ai_ml, security, architecture, infrastructure)
- By tag (arbitrary keywords)
- By status (active, deprecated, experimental, disabled)

### SkillSelector (`skill_selector.py`)
Multi-factor scoring (0.0–1.0):

| Factor | Weight | Description |
|---|---|---|
| Category match | 30% | Does the skill category match requested categories? |
| Technology overlap | 20% | Jaccard-like: matching techs / total skill techs |
| Tag keyword match | 10% | Tag present in task description? |
| Description relevance | 15% | Word overlap between task desc and skill desc |
| Historical success rate | 15% | success_count / usage_count |
| Quality score | 10% | Configurable quality metric |

### SkillDependencyResolver (`dependency_resolver.py`)
- Transitive dependency collection (BFS)
- Topological sort (Kahn's algorithm)
- Cycle detection (DFS with 3-color marking)
- Version conflict detection

### SkillLoader (`skill_loader.py`)
- Lazy loading with initialization hooks
- Hot reload (unload + reload without restart)
- Per-agent, per-mission instance tracking
- Complete unload and stats

### SkillCache (`skill_cache.py`)
- LRU eviction (least recently used)
- TTL expiration (configurable per entry)
- Priority-based eviction (alternative strategy)
- Hit rate computation
- Batch invalidation

### SkillProfiler (`skill_profiler.py`)
- Exponential moving average for all metrics
- Tracks: load time, memory, tokens, duration, failure rate
- Max memory watermark

### SkillDistributor (`skill_distributor.py`)
- Distributes skills across agents for a mission
- Loads with cache-awareness (skip cached)
- Unloads per agent or per mission
- History and stats

## Pipeline

```
Mission → Agent tasks → Selector → [SkillSelections per agent]
                                      ↓
                            DependencyResolver → [resolved order]
                                      ↓
                            Distributor.load → [SkillInstances]
                                      ↓
                            Cache.put → [LRU/TTL entries]
```

## Integration Points

| Layer | Integration |
|---|---|
| **Mission Planner** | Categories and technologies from the planning pipeline feed the Selector |
| **Knowledge Graph** | Past mission skill usage enriches success_rate and quality_score |
| **Retrieval Engine** | Semantic task → skill matching (future) |
| **Runtime Intelligence** | Performance history feeds the Profiler |
| **Experience Manager** | Lessons from past missions update skill quality scores |

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/skills` | List skills (filter: category, domain, status, tag) |
| `GET` | `/skills/{id}` | Skill detail + loaded instances + profile |
| `POST` | `/skills/select` | Auto-select skills for a task description |
| `POST` | `/skills/load` | Load a skill for an agent |
| `POST` | `/skills/unload` | Unload all instances of a skill |
| `GET` | `/skills/cache` | Cache stats (size, hit rate, strategy) |
| `GET` | `/skills/statistics` | Global stats (registry, cache, loader, profiler, distributor) |

## Example: Three agents, different skills

```
Mission: "Build a full-stack web app with authentication"

Agent Coder (backend):
  → python-coding (score 0.85, FastAPI + SQLAlchemy)
  → db-design (score 0.72, PostgreSQL schema)
  Memory: 20MB, Tokens: 1500

Agent Designer (frontend):
  → react-ui (score 0.88, React + TypeScript components)
  → Memory: 10MB, Tokens: 500

Agent Auditor (security):
  → security-audit (score 0.95, Bandit + OWASP checks)
  → Memory: 15MB, Tokens: 800

Total: 3 agents, 4 skills, 45MB, 2800 tokens
```

## Thread Safety

All components use `threading.RLock()`:
- Registry: concurrent reads + serialized writes
- Selector: history + selection atomic
- Resolver: graph operations atomic
- Loader: load/unload atomic
- Cache: eviction + access atomic
- Profiler: profile update atomic
- Distributor: distribution history atomic
