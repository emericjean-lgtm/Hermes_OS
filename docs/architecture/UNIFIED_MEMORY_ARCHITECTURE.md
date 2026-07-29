# Unified Memory & Knowledge Graph Architecture (HOS-047)

## Overview

The Unified Memory is the permanent brain of Hermes OS. It enables the system to learn from every mission, rapidly retrieve similar past experiences, build a navigable Knowledge Graph, and feed intelligence back into all other layers (Runtime Intelligence, Mission Planner, Agent Supervisor).

## Five Memory Types

```
┌─────────────────────────────────────────────────────────────┐
│                    Memory Manager                           │
│                      (Orchestrator)                         │
├────────────┬────────────┬───────────┬──────────┬────────────┤
│  Working   │  Episodic  │ Semantic  │Procedural│  Document  │
│  Memory    │  Memory    │  Memory   │ Memory   │  Memory    │
├────────────┴────────────┴───────────┴──────────┴────────────┤
│              Knowledge Graph (Neo4j-ready)                  │
├─────────────────────────────────────────────────────────────┤
│  Embedding Index  │  Retrieval Engine  │  Experience Mgr    │
└─────────────────────────────────────────────────────────────┘
```

### Working Memory (`working_memory.py`)
- Active mission context
- Current conversations
- Agent states
- Runtime decisions
- Auto-cleaned at mission end
- Thread-safe, singleton

### Episodic Memory (`episodic_memory.py`)
- Mission records (successes, failures)
- Incidents and recoveries
- Benchmarks history
- Decision history
- Queryable by mission_id, agent_id, outcome, tags, date range

### Semantic Memory (`semantic_memory.py`)
- Concepts, technologies, frameworks
- Architectures, models, tools, patterns
- Fast category-based lookup
- Tag-based search

### Procedural Memory (`procedural_memory.py`)
- Validated workflows
- Best practices
- Effective templates
- Resolution strategies
- Versioned procedures

### Document Memory (`document_memory.py`)
- Markdown, PDF, code, README indexes
- Architecture docs, specifications
- Content + metadata indexing
- RAG-ready structure

## Knowledge Graph (`knowledge_graph.py`)

The Knowledge Graph connects all entities in Hermes OS:

```
Mission ──▶ Task ──▶ Agent ──▶ Runtime ──▶ Model
  │            │        │                    │
  │            │        │                    ▼
  │            │        └──────────────▶ Skill
  │            │
  │            ▼
  └────────▶ Workspace ──▶ Document ──▶ Benchmark
                             │
                             ▼
                          Decision ──▶ Incident ──▶ Solution
```

### Graph Operations
- `add_node(entity_type, entity_id, properties)` — Add any entity
- `add_edge(source, target, relation_type, properties)` — Create relationship
- `traverse(start_id, depth, direction)` — Navigate the graph
- `find_paths(from_id, to_id, max_depth)` — Pathfinding
- `get_neighbors(node_id, relation_types)` — Direct connections
- `get_subgraph(entity_ids, depth)` — Extract subgraph

### Relation Types
- `HAS_TASK`, `ASSIGNED_TO`, `USES_RUNTIME`, `USES_MODEL`
- `PRODUCED`, `CONTAINS`, `BENCHMARKED`
- `CAUSED`, `RESOLVED_BY`, `SIMILAR_TO`
- `DEPENDS_ON`, `VALIDATED_BY`

## Embedding Index (`embedding_index.py`)

Abstraction layer supporting multiple local embedding models:

- Nomic Embed Text v1.5
- BGE-large-en-v1.5
- E5-large-v2
- Extensible via provider pattern

### Operations
- `embed(texts)` — Generate embeddings
- `add(entities)` — Index with embeddings
- `search(query, top_k)` — Semantic search
- `delete(entity_id)` — Remove from index
- `rebuild()` — Full reindex

## Retrieval Engine (`retrieval_engine.py`)

Hybrid search combining:

1. **Graph traversal** — Navigate relationships
2. **Embedding similarity** — Semantic vector search
3. **Keyword matching** — Full-text search
4. **Filter-based** — Metadata filtering

### Search Modes
- `semantic` — Pure embedding similarity
- `graph` — Graph traversal based
- `hybrid` — Combined scoring (default)
- `keyword` — Exact/partial text match

### Result Format
```python
{
    "results": [...],
    "scores": [...],
    "justification": "graph + semantic + keyword",
    "search_time_ms": 12
}
```

## Experience Manager (`experience_manager.py`)

Learns from completed missions to improve future decisions:

- Extract lessons from mission outcomes
- Identify frequent error patterns
- Compute best practices from historical data
- Propose improvements for the Mission Planner
- Compute success rates per agent/runtime/model

### Operations
- `extract_lessons(mission_id)` — Post-mortem analysis
- `get_recommendations(context)` — Context-aware suggestions
- `get_patterns(category)` — Recurring patterns (errors, successes)
- `compute_stats()` — Aggregate statistics

## Memory Manager (`memory_manager.py`)

Central orchestrator — all other layers pass through it.

```python
class MemoryManager:
    working_memory: WorkingMemory
    episodic: EpisodicMemory
    semantic: SemanticMemory
    procedural: ProceduralMemory
    document: DocumentMemory
    knowledge_graph: KnowledgeGraph
    embedding_index: EmbeddingIndex
    retrieval: RetrievalEngine
    experience: ExperienceManager
```

## Event Bus Events

| Event | Trigger |
|---|---|
| `memory.created` | Any memory entry created |
| `memory.updated` | Entry modified |
| `memory.deleted` | Entry removed |
| `memory.indexed` | Document indexed for RAG |
| `graph.updated` | Knowledge graph modified |
| `experience.learned` | Lesson extracted from mission |
| `retrieval.completed` | Search executed |

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/memory/search?q=&mode=hybrid&top_k=10` | Hybrid search |
| `GET` | `/memory/graph?node_id=&depth=2` | Graph traversal |
| `GET` | `/memory/experiences?mission_id=` | Lessons learned |
| `POST` | `/memory/index` | Index document/content |
| `POST` | `/memory/search` | Advanced search with filters |
| `GET` | `/memory/statistics` | Memory stats (counts, sizes) |

## Layer Integrations

| Consumer | Integration Point |
|---|---|
| **Mission Planner** | Search similar missions, get recommendations |
| **Runtime Intelligence** | Retrieve past performance data |
| **Discovery Engine** | Enrich benchmarks with historical data |
| **Agent Supervisor** | Retrieve relevant agent experiences |
| **Workspace Manager** | Find related artifacts |
| **Policy Engine** | Consult past audit records |

## Example: Experience Reuse

```
New Mission Request: "Build authentication system with OAuth2"

1. RetrievalEngine.search("OAuth2 authentication") → finds 3 similar missions
2. ExperienceManager.get_recommendations(context) → suggests:
   - Use FastAPI + python-jose (proven 94% success rate)
   - Avoid manual token refresh (87% error rate)
   - Delegate to auth-specialist agent (avg 4.2h vs 11h generic)
3. MissionPlanner uses recommendations → optimizes DAG
4. RuntimeRecommender → suggests llama3.1:8b (best auth perf)
```

## Future Migration Path

The Knowledge Graph uses an in-memory adjacency list with a stable API. Migration to Neo4j or another distributed graph database requires only swapping the `KnowledgeGraph` implementation — all consumers use the same interface.

## Performance Characteristics

| Component | Complexity | Thread Safety |
|---|---|---|
| Working Memory | O(1) access | RLock |
| Episodic Memory | O(log n) query | RLock |
| Semantic Memory | O(n) search, O(1) insert | RLock |
| Knowledge Graph | O(V+E) traversal | RLock |
| Embedding Index | O(d·n) similarity | RLock |
| Retrieval Engine | Combined | RLock |
