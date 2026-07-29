# Knowledge Graph Architecture (HOS-047)

## Overview

The Hermes OS Knowledge Graph is a directed graph connecting all entities in the system — Missions, Tasks, Agents, Runtimes, Models, Skills, Workspaces, Documents, Benchmarks, Decisions, Incidents, and Solutions. It enables rich navigation, relationship discovery, and contextual reasoning.

## Entity Types

```
┌──────────────────────────────────────────────────────────────┐
│                       ENTITY LAYER                           │
├──────────┬──────────┬──────────┬──────────┬─────────────────┤
│ Mission  │   Task   │  Agent   │ Runtime  │     Model       │
├──────────┼──────────┼──────────┼──────────┼─────────────────┤
│  Skill   │Workspace │ Document │Benchmark │    Decision     │
├──────────┼──────────┼──────────┼──────────┼─────────────────┤
│ Incident │ Solution │ Pattern  │ Lesson   │                 │
└──────────┴──────────┴──────────┴──────────┴─────────────────┘
```

## Relation Types

### Mission Relations
```
Mission ──HAS_TASK──▶ Task
Mission ──SIMILAR_TO──▶ Mission
Mission ──PRODUCED──▶ Decision
```

### Task Relations
```
Task ──ASSIGNED_TO──▶ Agent
Task ──DEPENDS_ON──▶ Task
Task ──VALIDATED_BY──▶ Agent
Task ──PRODUCED──▶ Document
```

### Agent Relations
```
Agent ──USES_RUNTIME──▶ Runtime
Agent ──HAS_SKILL──▶ Skill
Agent ──COLLABORATED_WITH──▶ Agent
```

### Runtime Relations
```
Runtime ──USES_MODEL──▶ Model
Runtime ──BENCHMARKED──▶ Benchmark
```

### Decision Relations
```
Decision ──CAUSED──▶ Incident
Decision ──BASED_ON──▶ Lesson
```

### Incident Relations
```
Incident ──RESOLVED_BY──▶ Solution
Incident ──SIMILAR_TO──▶ Incident
```

## Graph Data Structure

```python
class KnowledgeGraph:
    _nodes: Dict[str, KnowledgeNode]     # node_id → node
    _edges: Dict[str, KnowledgeEdge]     # edge_id → edge
    _adjacency: Dict[str, List[str]]     # node_id → [target_node_ids]
    _reverse_adj: Dict[str, List[str]]   # node_id → [source_node_ids]
    _indexes: Dict[str, Set[str]]        # entity_type → {node_ids}
```

### Node Schema
```python
@dataclass
class KnowledgeNode:
    id: str
    entity_type: EntityType
    entity_id: str          # FK to source table
    properties: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
```

### Edge Schema
```python
@dataclass  
class KnowledgeEdge:
    id: str
    source_id: str
    target_id: str
    relation_type: RelationType
    properties: Dict[str, Any]
    weight: float           # 0.0–1.0, default 1.0
    created_at: datetime
```

## Traversal Algorithms

### BFS/DFS Traversal
```python
def traverse(start_id, max_depth=2, direction="outgoing"):
    """Breadth-first traversal from start node."""
```

### Pathfinding
```python
def find_paths(from_id, to_id, max_depth=5):
    """Find all paths between two nodes (BFS-based)."""
```

### Subgraph Extraction
```python
def get_subgraph(entity_ids, depth=1):
    """Extract connected subgraph around given entities."""
```

### Centrality
```python
def get_central_nodes(limit=10):
    """Nodes with highest degree (in+out edges)."""
```

## Indexes

- **Type index**: `entity_type → Set[node_id]` — Fast lookup by entity type
- **Relation index**: `relation_type → Set[edge_id]` — Fast lookup by relation
- **Adjacency**: Bidirectional for O(1) neighbor access

## Query Examples

### Find all agents used in a mission
```python
mission_id = "m_abc123"
graph.traverse(mission_id, direction="outgoing")
# → Mission → Tasks → Agents
```

### Find similar past missions
```python
graph.get_neighbors(current_mission_id, ["SIMILAR_TO"])
# → [mission_123, mission_456]
```

### Trace incident to root cause
```python
graph.traverse(incident_id, direction="incoming", max_depth=3)
# → Incident ← Decision ← Task ← Mission
```

### Find optimal agent for a task type
```python
# Traverse: Task type → Past Tasks → Agents → Success rate
graph.get_subgraph([task_type_node], depth=2)
# Filter by edge property "success_rate"
```

## Thread Safety

All graph operations are protected by `threading.RLock()`, allowing concurrent reads and serialized writes.

## Graph Statistics

```python
stats = {
    "node_count": 1234,
    "edge_count": 4567,
    "type_distribution": {
        "Mission": 42,
        "Task": 387,
        "Agent": 15,
        "Runtime": 8,
        "Model": 23,
        ...
    },
    "most_central": ["agent_coder_01", "runtime_ollama"],
    "largest_component": 892  # nodes in largest connected component
}
```

## Future: Neo4j Migration Path

The `KnowledgeGraph` class exposes a clean interface. Migration to Neo4j requires:

1. Implement `Neo4jKnowledgeGraph` with the same interface
2. Cypher translation layer for traversal queries
3. Replace in-memory adjacency with Neo4j driver
4. Zero changes to consumers (MemoryManager, RetrievalEngine)

```python
# Current
graph = KnowledgeGraph()
graph.add_node(...)

# Future (same API)
graph = Neo4jKnowledgeGraph(uri="bolt://localhost:7687")
graph.add_node(...)  # ← identical call
```
