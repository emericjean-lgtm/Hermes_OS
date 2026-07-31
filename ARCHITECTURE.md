# Hermes OS — Architecture Reference

> **Document de référence** pour l'architecture globale d'Hermes OS.
> Couvre HOS-000 à HOS-028.

---

## 1. Architecture Globale

```mermaid
graph TB
    subgraph "External"
        HTTP[HTTP / WebSocket]
        CLI[CLI / MCP]
        UI[Next.js / Hermes Agent Dashboard]
    end

    subgraph "Service Layer (HOS-027/028)"
        MC[MissionControlService]
        API[MissionControlRouter]
    end

    subgraph "Agent Layer (HOS-017/018/019/020/024)"
        EG[ExecutionGraph]
        TP[TaskPlanner]
        LM[AgentLifecycleManager]
        SUP[MultiAgentSupervisor]
        EE[ExecutionEngine]
    end

    subgraph "Memory Layer (HOS-021)"
        UM[UnifiedMemory]
        MB[MemoryBackend]
        IB[InMemoryBackend]
    end

    subgraph "Skill Layer (HOS-022)"
        SK[AdaptiveSkillOrchestrator]
        SR[SkillRepository]
    end

    subgraph "Event Layer (HOS-013/025)"
        REB[RuntimeEventBus]
        SEB[SystemEventBus]
    end

    subgraph "Runtime Abstraction Layer (HOS-009/010/011/012/014/015/016)"
        REG[RuntimeRegistry]
        SEL[RuntimeSelector]
        CTX[ActiveRuntimeContext]
        HEALTH[RuntimeHealthMonitor]
        PERF[RuntimePerformanceAnalyzer]
        DEC[RuntimeDecisionEngine]
        REC[RuntimeRecoveryManager]
        POL[RuntimePolicyEngine]
        RTR[RuntimeRouter]
    end

    subgraph "Concrete Runtimes"
        STUB[StubRuntime]
        OLLAMA[OllamaRuntime]
        OPENAI[OpenAI / etc.]
    end

    subgraph "Integrations (HOS-023)"
        HA[HermesAgentAdapter]
    end

    HTTP --> API
    CLI --> MC
    UI --> API
    API --> MC

    MC --> SUP
    MC --> EE
    MC --> UM
    MC --> SK
    MC --> SEB
    MC --> RTR
    MC --> DEC
    MC --> HA
    MC --> FB

    SUP --> EG
    SUP --> LM
    SUP --> TP
    EE --> SUP
    EE --> LM
    EE --> RTR

    RTR --> CTX
    RTR --> SEL
    RTR --> REC

    DEC --> REG
    DEC --> SEL
    DEC --> HEALTH
    DEC --> PERF
    DEC --> REC
    DEC --> POL

    SEL --> REG
    HEALTH --> REG
    PERF --> REB
    REC --> REG
    REC --> SEL

    UM --> MB
    MB --> IB
    SK --> SR
    SEB --> REB

    REG --> STUB
    REG --> OLLAMA
    REG --> OPENAI

    HA --> OLLAMA
```

---

## 2. Kernel Hermes OS

### 2.1 HOS-000 — Foundation (SDS)

Le noyau historique SDS (Software Defined Services) comprend :

- **EventBusImpl** — bus d'événements SQLite
- **RuntimeHolder** — singleton runtime legacy
- **SDS Router** — routes FastAPI `/api/hermes-os/*`
- **Forward EventBusImpl → EventHub** — pont vers le legacy

### 2.2 HOS-001 — RAL Interfaces

Le Runtime Abstraction Layer (RAL) commence avec les contrats fondamentaux :

```python
class RuntimeInterface(Protocol):
    name: str
    version: str
    status: RuntimeStatus
    capabilities: CapabilitySet | None

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def get(self, name: str) -> Any | None: ...

class ChatCapability(Protocol):
    async def chat(self, messages, *, runtime_ctx=None) -> ChatResponse: ...
```

### 2.3 HOS-002 — EventBusImpl

Implémentation concrète du bus d'événements :

- Stockage SQLite
- Publication/abonnement par topic
- `TopicPattern("*")` pour le forwarding wildcard

### 2.4 HOS-003 — SDS Wiring

Câblage FastAPI :

- `lifespan` initialise EventBusImpl → RuntimeHolder
- `SDS_ROUTER` expose les endpoints SDS
- Tests d'intégration SDS

---

## 3. Runtime Abstraction Layer (HOS-004 → HOS-016)

### 3.1 StubRuntime (HOS-004)

```mermaid
classDiagram
    class RuntimeInterface {
        <<Protocol>>
        +name: str
        +version: str
        +status: RuntimeStatus
        +capabilities: CapabilitySet
        +start()
        +stop()
        +get(name)
    }
    class StubRuntime {
        +name: str
        +version: str
        +capabilities: CapabilitySet
        +start()
        +stop()
        +get(name)
    }
    class ChatCapability {
        <<Protocol>>
        +chat(messages, runtime_ctx)
    }
    class StubChatCapability {
        +chat(messages, runtime_ctx)
    }

    RuntimeInterface <|.. StubRuntime
    ChatCapability <|.. StubChatCapability
    StubRuntime --> StubChatCapability : provides
```

Premier runtime concret. Publie `RUNTIME_STARTED` / `RUNTIME_STOPPED`.

### 3.2 HermesOllamaRuntime (HOS-005)

Runtime agentique réel basé sur Ollama :

- Implémente `RuntimeInterface`
- Capacité `Chat` complète
- Configuration via `RuntimeConfig`

### 3.3 OllamaClient (HOS-006)

```mermaid
classDiagram
    class OllamaClientProtocol {
        <<Protocol>>
        +chat(messages)
        +chat_stream(messages)
        +health()
    }
    class OllamaClient {
        +endpoint: str
        +timeout: float
        +chat(messages)
        +chat_stream(messages)
        +health()
    }
    class FakeOllamaClient {
        +chat(messages)
        +chat_stream(messages)
        +health()
    }

    OllamaClientProtocol <|.. OllamaClient
    OllamaClientProtocol <|.. FakeOllamaClient
```

Client HTTP configurable, mocké en tests.

### 3.4 RuntimeRegistry & RuntimeFactory (HOS-007/008)

```mermaid
classDiagram
    class RuntimeRegistry {
        +register(name, runtime)
        +get(name)
        +list_available()
        +find_name(runtime)
    }
    class RuntimeFactory {
        +register_builder(type, builder)
        +create(type, **kwargs)
        +available_types()
    }
    class RuntimeLifecycle {
        +initialize(runtime)
        +health_check(runtime)
        +shutdown(runtime)
    }
```

### 3.5 ActiveRuntimeContext & RuntimeSelector (HOS-009)

```mermaid
classDiagram
    class ActiveRuntimeContext {
        +active_runtime
        +fallback_name
        +set_active(name)
        +set_fallback(name)
    }
    class RuntimeSelector {
        +select(capability, preference, preferred_name)
        +list_compatible(capability, preference)
    }
```

### 3.6 RuntimeRouter (HOS-010)

Point d'exécution central :

1. Tente le runtime actif
2. Fallback configuré
3. Préférence explicite
4. Sélecteur automatique

### 3.7 RuntimeHealthMonitor (HOS-011)

```python
class RuntimeHealthMonitor:
    def check_runtime(self, name) -> RuntimeHealthStatus: ...
    def is_available(self, name) -> bool: ...
    def is_error_prone(self, name) -> bool: ...
```

États : `AVAILABLE`, `DEGRADED`, `UNAVAILABLE`, `UNKNOWN`.

### 3.8 RuntimeRecoveryManager & CircuitBreaker (HOS-012)

```mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN : N failures
    OPEN --> HALF_OPEN : timeout elapsed
    HALF_OPEN --> CLOSED : success
    HALF_OPEN --> OPEN : failure
```

### 3.9 RuntimeEventBus & RuntimeObservability (HOS-013)

```mermaid
classDiagram
    class RuntimeEventBus {
        +publish(event)
        +subscribe(handler)
        +get_events()
        +clear()
    }
    class RuntimeEvent {
        +event_type: str
        +runtime_name: str
        +timestamp: float
        +severity: Severity
        +message: str
        +metadata: dict
    }
    class RuntimeObservability {
        +metrics: dict
    }
```

### 3.10 RuntimePerformanceAnalyzer (HOS-014)

Analyse les événements pour produire :

- `success_rate`
- `reliability_score` (0-100)
- `performance_score` (0-100)
- Classement des runtimes

### 3.11 RuntimeDecisionEngine (HOS-015)

```mermaid
flowchart LR
    A[Capability] --> B{Decision Engine}
    REG --> B
    HEALTH --> B
    PERF --> B
    REC --> B
    POL --> B
    B --> C[RuntimeDecision]
    C --> D[selected_runtime]
    C --> E[confidence]
    C --> F[candidate_scores]
```

Score composite (0-1000) : Health + Reliability + Performance + Capability + Policy - CircuitPenalty.

### 3.12 RuntimePolicyEngine (HOS-016)

Règles extensibles pour contrôler :

- Runtimes autorisés par contexte
- Préférences local/cloud
- Priorités par type de tâche

---

## 4. Agent Layer (HOS-017 → HOS-020, HOS-024)

### 4.1 ExecutionGraph (HOS-017)

```mermaid
classDiagram
    class ExecutionGraph {
        +add_node(node)
        +add_edge(edge)
        +get_node(id)
        +list_nodes()
        +topological_sort()
        +generate_plan()
        +validate()
    }
    class AgentNode {
        +id: str
        +name: str
        +type: NodeType
        +status: NodeStatus
        +runtime_capability: str
    }
    class AgentEdge {
        +source: str
        +target: str
        +condition: str
    }
    class GraphExecutionPlan {
        +execution_order
        +levels
        +dependencies
    }
```

DAG thread-safe avec détection de cycles, validation, plan d'exécution.

### 4.2 TaskPlanner (HOS-018)

```mermaid
flowchart LR
    M[TaskMission] --> P[TaskPlanner]
    T[PlannedTasks] --> P
    P --> PLAN[TaskPlan]
    P --> G[ExecutionGraph]
    P --> EXPLAIN[Explanation]
```

4 stratégies : `SEQUENTIAL`, `BALANCED`, `PARALLEL`, `CONSERVATIVE`.

### 4.3 AgentLifecycleManager (HOS-019)

```mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> READY
    READY --> SCHEDULED
    READY --> RUNNING
    SCHEDULED --> RUNNING
    RUNNING --> PAUSED
    RUNNING --> COMPLETED
    RUNNING --> FAILED
    RUNNING --> CANCELLED
    RUNNING --> TIMEOUT
    PAUSED --> RUNNING
    PAUSED --> CANCELLED
    COMPLETED --> [*]
    FAILED --> [*]
    CANCELLED --> [*]
    TIMEOUT --> [*]
```

Machine à états thread-safe avec callback `on_event(agent_id, from_state, to_state)`.

### 4.4 MultiAgentSupervisor (HOS-020)

```mermaid
flowchart LR
    M[MissionContext] --> SUP[MultiAgentSupervisor]
    T[PlannedTasks] --> SUP
    SUP --> PLAN[TaskPlan]
    SUP --> INST[AgentInstances]
    SUP --> TICK[tick()]
    PLAN --> EG[ExecutionGraph]
    EG --> TICK
    TICK --> AGENT[create → start → complete]
```

### 4.5 ExecutionEngine (HOS-024)

Moteur d'exécution complet :

```
start(mission, tasks) → ExecutionContext
tick() → description des changements
pause() / resume() / cancel() / recover()
get_status() → snapshot d'avancement
get_result() → ExecutionResult
```

---

## 5. Memory Layer (HOS-021)

### 5.1 UnifiedMemory

```mermaid
classDiagram
    class UnifiedMemory {
        +store(content, scope, ...)
        +update(entry_id, ...)
        +delete(entry_id)
        +search(query)
        +clear_scope(scope)
        +export()
        +import_json()
        +get_statistics()
    }
    class MemoryBackend {
        <<abstract>>
        +store(entry)
        +get(entry_id)
        +delete(entry_id)
        +search(query)
    }
    class InMemoryBackend {
        +store(entry)
        +get(entry_id)
        +search(query)
    }
    class MemoryEntry {
        +id: str
        +scope: MemoryScope
        +title: str
        +content: str
        +tags: frozenset
        +importance: int
    }

    UnifiedMemory --> MemoryBackend
    MemoryBackend <|.. InMemoryBackend
```

7 scopes : `SESSION`, `MISSION`, `AGENT`, `PROJECT`, `USER`, `GLOBAL`, `EXPERIENCE`.

---

## 6. Skill Layer (HOS-022)

```mermaid
classDiagram
    class AdaptiveSkillOrchestrator {
        +analyse_mission(description)
        +select_skills(capabilities, tags)
        +load_bundle(bundle_id)
        +recommend(mission)
        +explain_selection()
    }
    class SkillDescriptor {
        +id: str
        +name: str
        +capabilities: frozenset
        +dependencies: frozenset
        +estimated_tokens: int
    }
    class SkillSelection {
        +selected_skills
        +rejected_skills
        +total_tokens
        +explanation
    }
```

4 stratégies : `MINIMAL`, `BALANCED`, `EXHAUSTIVE`, `PERFORMANCE`.

---

## 7. Event Layer (HOS-025)

### 7.1 SystemEventBus

```mermaid
flowchart LR
    R[RuntimeEventBus] --> SEB[SystemEventBus]
    M[Memory Events] --> SEB
    S[Skill Events] --> SEB
    SUP[Supervisor Events] --> SEB
    L[Lifecycle Events] --> SEB
    E[Execution Events] --> SEB
    SEB --> SUB1[Subscriber 1]
    SEB --> SUB2[Subscriber 2]
    SEB --> HIST[EventHistory]
```

9 familles : `RUNTIME`, `AGENT`, `MISSION`, `EXECUTION`, `MEMORY`, `SKILL`, `SYSTEM`, `OBSERVABILITY`, `INTEGRATION`.

---

## 8. Mission Control (HOS-027/028)

### 8.1 MissionControlService

```mermaid
flowchart TB
    subgraph "MissionControlService"
        M[Mission Facade]
        R[Runtime Facade]
        EX[Execution Facade]
        ME[Memory Facade]
        SK[Skills Facade]
        O[Observability Facade]
        I[Integration Facade]
        S[System Facade]
    end

    M --> SUP[MultiAgentSupervisor]
    R --> REG[RuntimeRegistry]
    R --> DEC[RuntimeDecisionEngine]
    EX --> EE[ExecutionEngine]
    ME --> UM[UnifiedMemory]
    SK --> AOS[AdaptiveSkillOrchestrator]
    O --> SEB[SystemEventBus]
    I --> HA[HermesAgentAdapter]
    S --> ALL[All subsystems]
```

### 8.2 Routes API (HOS-028)

Toutes les routes sous `/api/v1/` :

| Groupe | Méthodes |
|---|---|
| Missions | `GET/POST /missions`, `GET /missions/{id}`, `POST /missions/{id}/{start,pause,resume,cancel}` |
| Runtimes | `GET /runtimes`, `GET /runtimes/{health,metrics}`, `GET /runtimes/{name}[/{health,metrics}]` |
| Execution | `GET /execution`, `POST /execution/{start,pause,resume,cancel}` |
| Memory | `GET/POST /memory`, `GET/PATCH /memory/{entry_id}`, `GET /memory/{search,statistics}` |
| Skills | `GET /skills`, `POST /skills/{select,recommend}`, `GET /skills/statistics`, `POST /skills/bundles/{id}/load` |
| Events | `GET /events`, `GET /events/{statistics,export}`, `POST /events/{publish,clear}` |
| Hermes | `GET /hermes/{status,sessions}`, `POST /hermes/{connect,disconnect,task}` |
| System | `GET /{health,status,diagnostics,statistics,version}`, `POST /tick` |
| WebSocket | `ws://host/ws/events` — streaming SystemEvent |

---

## 9. Intégrations

### 9.1 HermesAgentAdapter (HOS-023)

Pont entre Hermes OS et Hermes Agent (NousResearch) :

```mermaid
flowchart LR
    RAL[RuntimeInterface] --> HA[HermesAgentAdapter]
    UM[UnifiedMemory] --> HA
    SK[SkillOrchestrator] --> HA
    HA --> BA[BaseAgent]
    HA --> MR[ModelRouter]
    HA --> OC[OllamaClient]
```

Mapping : `RuntimeDecision → ModelRouter`, `UnifiedMemory → EchoAgent.remember()`, `TaskPlan → Hermes Tasks`.

---

## 10. Flux d'exécution typique

```mermaid
sequenceDiagram
    participant User
    participant API as API (HOS-028)
    participant MC as MissionControl (HOS-027)
    participant TP as TaskPlanner (HOS-018)
    participant SUP as Supervisor (HOS-020)
    participant EG as ExecutionGraph (HOS-017)
    participant LM as Lifecycle (HOS-019)
    participant DEC as DecisionEngine (HOS-015)
    participant RTR as RuntimeRouter (HOS-010)
    participant RT as Runtime

    User->>API: POST /missions
    API->>MC: create_mission()
    MC->>TP: create_plan()
    TP-->>MC: TaskPlan + ExecutionGraph
    MC->>SUP: create_mission()
    SUP-->>MC: MissionInstance
    MC-->>API: 201 Created

    User->>API: POST /missions/{id}/start
    API->>MC: start_mission()
    MC->>SUP: start_mission()
    SUP-->>MC: RUNNING

    loop tick()
        SUP->>EG: get_ready_tasks()
        EG-->>SUP: [task_A, task_B]
        SUP->>LM: create_agent(ctx)
        SUP->>DEC: select_runtime("chat")
        DEC-->>SUP: RuntimeDecision(ollama)
        SUP->>RTR: chat(messages)
        RTR->>RT: chat(messages)
        RT-->>RTR: ChatResponse
        RTR-->>SUP: response
        SUP->>LM: complete_agent(id)
        SUP->>EG: mark_completed(task_A)
    end

    SUP-->>MC: MISSION_COMPLETED
    MC-->>API: 200 OK
```

---

## 11. Dépendances entre modules

```mermaid
graph TD
    HOS004[StubRuntime] --> HOS001[RAL Interfaces]
    HOS005[HermesOllamaRuntime] --> HOS001
    HOS005 --> HOS006[OllamaClient]
    HOS006 --> HOS001
    HOS007[Registry/Factory] --> HOS001
    HOS008[SDS Wiring] --> HOS002[EventBusImpl]
    HOS008 --> HOS007
    HOS009[Context/Selector] --> HOS007
    HOS010[Router] --> HOS009
    HOS011[Health Monitor] --> HOS007
    HOS012[Recovery] --> HOS007
    HOS013[Runtime Events] --> HOS002
    HOS014[Performance] --> HOS013
    HOS015[Decision Engine] --> HOS009
    HOS015 --> HOS011
    HOS015 --> HOS014
    HOS015 --> HOS012
    HOS016[Policy Engine] --> HOS015
    HOS017[ExecutionGraph] --> HOS001
    HOS018[TaskPlanner] --> HOS017
    HOS019[Lifecycle] --> HOS001
    HOS020[Supervisor] --> HOS018
    HOS020 --> HOS019
    HOS021[UnifiedMemory] --> HOS001
    HOS022[SkillOrchestrator] --> HOS001
    HOS023[HermesAdapter] --> HOS001
    HOS023 --> HOS021
    HOS023 --> HOS022
    HOS024[ExecutionEngine] --> HOS020
    HOS024 --> HOS010
    HOS024 --> HOS015
    HOS025[SystemEventBus] --> HOS013
    HOS027[MissionControl] --> HOS020
    HOS027 --> HOS024
    HOS027 --> HOS015
    HOS027 --> HOS021
    HOS027 --> HOS022
    HOS027 --> HOS025
    HOS027 --> HOS023
    HOS027 --> HOS026
    HOS028[API] --> HOS027
```
