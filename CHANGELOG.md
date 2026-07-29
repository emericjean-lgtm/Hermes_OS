# Changelog — Hermes OS

> Toutes les modifications notables du projet Hermes OS.
> Format basé sur [Keep a Changelog](https://keepachangelog.com/).

---

## [HOS-040] — 2026-07-29 — Model Benchmark & Discovery Engine

### Ajouté
- **DiscoveryEngine** — découverte automatique de modèles avec connecteurs pluggables (Ollama, HuggingFace)
- **OllamaConnector** — catalogue de 12 modèles Ollama connus (qwen3, deepseek, gemma3, phi4, llama, nomic, codellama)
- **HuggingFaceConnector** — curated hot list (phi-4, Mistral-Nemo, Llama-3.1)
- **ModelRegistry** — registre central thread-safe (5000 max) avec stats par statut et source
- **CompatibilityAnalyzer** — analyse VRAM/RAM/ROCm/quantization avec recommandations de downgrade
- **BenchmarkEngine** — 5 profils (CODING, REASONING, GENERAL_CHAT, TOOL_USE, LONG_CONTEXT) avec métriques
- **CronScheduler** — planificateur in-process pour discovery/benchmark périodiques (sans dépendance externe)
- **REST API** — POST /scan, GET /models, GET /benchmarks, GET /stats
- **Tests** — 24 tests : registry, compatibility, discovery, connectors, benchmark, cron, thread safety

### Validation
- pytest : ✅ 24/24 passed (1.04s)

---

## [HOS-039] — 2026-07-29 — Runtime Simulation Engine

### Ajouté
- **SimulationEngine** — simulacres de tâches avant exécution réelle, intégration orchestrator
- **ResourcePredictor** — prédiction VRAM/RAM/durée/charge par modèle et type de tâche
- **RiskAnalyzer** — analyse de risque (échec, surcharge, instabilité, recovery) à 4 niveaux
- **Simulation models** — SimulationResult, SimulatedCandidate, ResourcePrediction, RiskAssessment, RiskLevel
- **REST API** — POST /runtime/simulation/run, GET /{id}, GET /history
- **Intégration EventBus** — publie simulation.started, simulation.completed, simulation.warning
- **simulate_before_execute()** — pont vers RuntimeOrchestrator (HOS-038)
- **Tests** — 19 tests : prédiction, risque, simulation, events, thread safety

### Validation
- pytest : ✅ 19/19 passed (0.02s)

---

## [HOS-038] — 2026-07-29 — Adaptive Runtime Orchestrator

### Ajouté
- **RuntimeOrchestrator** — couche d'orchestration finale combinant intelligence, santé, ressources, recovery
- **DecisionPipeline** — pipeline multi-facteurs : évalue les candidats, élimine les invalides, score les restants
- **PriorityManager** — 4 profils (CRITICAL/HIGH/NORMAL/BACKGROUND) avec poids et seuils adaptatifs
- **Decision models** — OrchestratedDecision, CandidateRuntime, DecisionExplanation, PriorityLevel, DecisionStatus
- **REST API** — GET /history, GET /decision/{id}, POST /evaluate
- **Intégration EventBus** — publie routing.analysis_started, routing.runtime_selected, routing.decision_created, routing.decision_failed
- **Tests** — 24 tests : priority profiles, pipeline evaluation, elimination logic, explanation, events, thread safety

### Profils de priorité
| Priorité | Intelligence | Santé | Ressources | Confiance min |
|---|---|---|---|---|
| CRITICAL | 15% | 35% | 20% | 85% |
| HIGH | 30% | 30% | 25% | 70% |
| NORMAL | 40% | 25% | 25% | 50% |
| BACKGROUND | 25% | 15% | 50% | 30% |

### Validation
- pytest : ✅ 24/24 passed (0.04s)
- compileall : ✅

---

## [HOS-037] — 2026-07-29 — Runtime Intelligence Layer

### Ajouté
- **LearningEngine** — apprentissage incrémental : enregistre les résultats, met à jour les scores, ajuste les poids
- **DecisionMemory** — stockage thread-safe des décisions passées (10000 max) avec index par runtime et type de tâche
- **PerformanceAnalyzer** — success rate, avg latency, latency stddev, stability score, resource efficiency
- **RuntimeScorer** — score composite pondéré (performance 35%, fiabilité 40%, efficacité 25%), comparaison, recommandations contextuelles
- **Intelligence models** — DecisionRecord, RuntimeScore, TaskContext, Recommendation, TaskStatus
- **REST API** — GET /runtime/intelligence/scores, GET /runtime/intelligence/{id}, GET /runtime/intelligence/recommendations?task_type=&max_latency_ms=&priority=
- **Intégration EventBus** — publie intelligence.score_updated, intelligence.recommendation_created
- **Tests** — 26 tests : decision memory, performance analysis, scoring, learning, recommendations, events, thread safety

### Validation
- pytest : ✅ 26/26 passed (0.05s)
- compileall : ✅

---

## [HOS-036] — 2026-07-29 — Runtime Recovery Engine

### Ajouté
- **RecoveryEngine** — moteur d'auto-récupération : écoute les événements runtime, match les politiques, exécute les actions
- **RecoveryPolicyEngine** — 6 politiques par défaut : restart_on_failure, fallback_on_unavailable, unload_on_resource_limit, reload_on_model_failure, notify_on_health_degraded, unload_on_overloaded
- **RecoveryActions** — 5 actions concrètes : RestartRuntimeAction, ReloadModelAction, SwitchRuntimeAction, UnloadResourceAction, NotifyAction
- **Recovery models** — IncidentType, RecoveryIncident, RecoveryAttempt, RecoveryPolicy, RecoveryStatus, ActionResult
- **REST API** — GET /runtime/recovery/history, GET /runtime/recovery/status, POST /runtime/recovery/{id}/retry
- **Intégration EventBus** — publie recovery.started, recovery.action_started, recovery.completed, recovery.failed
- **Cooldown** — empêche la répétition de politiques pour le même runtime dans une fenêtre configurable
- **Max attempts** — limite le nombre de tentatives par politique (3 par défaut)
- **Tests** — 25 tests : détection incidents, actions, policies, cooldown, history, thread safety, events

### Validation
- pytest : ✅ 25/25 passed (2.95s)
- compileall : ✅

---

## [HOS-035] — 2026-07-29 — Runtime Resource Manager

### Ajouté
- **ResourceManager** — gestionnaire centralisé CPU/RAM/GPU/VRAM avec allocation thread-safe
- **GPUMonitor** — surveillance GPU via rocm-smi (AMD), nvidia-smi (NVIDIA), ollama ps (fallback), NoopGPUMonitor pour CI
- **MemoryManager** — suivi RAM système via /proc/meminfo avec fallback psutil
- **AllocationPolicy** — DefaultAllocationPolicy (first-fit, priorité) + VramAwareAllocationPolicy (température, utilisation)
- **Resource Models** — ResourceType, ResourceStatus, ResourceSnapshot, ResourceAllocation, ResourceLimit, GPUInfo
- **REST API** — GET /runtime/resources, GET /runtime/resources/status, GET /runtime/resources/allocations, POST /runtime/resources/release
- **Intégration EventBus** — callback on_event publie vram.allocated, resource.allocation_failed, resource.released, resource.warning, vram.limit_reached
- **Tests** — 21 tests : allocation, refus surcharge, libération, événements, seuils, thread safety, mock GPU

### Validation
- pytest : ✅ 21/21 passed (0.03s)
- compileall : ✅

---

## [HOS-034] — 2026-07-29 — Runtime Event Bus & Observability

### Ajouté
- **RuntimeEventBus** — bus publish/subscribe thread-safe avec historique configurable
- **RuntimeEventModel** — modèle Pydantic immutable : id, runtime_id, event_type, severity, timestamp, source, payload, correlation_id
- **RuntimeEventType** — 16 types d'événements en 4 catégories : runtime, model, router, resource
- **RuntimeEventStore** — abstraction EventStore + implémentation SQLite avec WAL 
- **REST API** — GET /runtime/events (filtres), GET /runtime/events/{runtime_id}, POST /runtime/events
- **WebSocket** — /runtime/events/ws avec streaming temps réel et filtrage
- **useRuntimeEvents hook** — hook React WebSocket avec reconnexion automatique
- **Tests** — 24 tests : création, publication, abonnement, persistence SQLite, thread safety, event types

### Validation
- pytest : ✅ 24/24 passed
- compileall : ✅

---

## [HOS-029] — 2026-07-29 — Mission Control Dashboard (Next.js)

---

## [HOS-030] — 2026-07-29 — Mission Center & Visual Planner

---

## [HOS-031] — 2026-07-29 — Execution Center & Live Monitoring

---

## [HOS-032] — 2026-07-29 — Agent Center & Live Agent Inspector

---

## [HOS-033] — 2026-07-29 — Runtime Center & Intelligent Runtime Management

### Ajouté
- **Runtime Center** — page /runtimes avec 9 panneaux redimensionnables (react-resizable-panels)
- **RuntimeOverview** — 8 stat-cards : total, healthy, degraded, avg latency, most reliable, most used, best score, failures
- **RuntimeTable** — tableau TanStack 9 colonnes : nom, status, healthy, latence, fiabilité, performance, succès, exécutions, échecs (tri, filtre, sélection)
- **RuntimeInspector** — inspection : status, version, latence, scores, capacités, type, dernière décision
- **RuntimeDecisionExplorer** — visualisation Recharts des scores par runtime (health, reliability, performance, capability, policy) avec penalty circuit breaker
- **RuntimeHealth** — santé temps réel : statut, latence, erreurs, graphique d'évolution
- **RuntimePerformance** — graphiques Recharts : barres succès, pie exécutions, barres scores fiabilité
- **RuntimePolicies** — politiques actives : règles, priorités, runtimes autorisés/interdits, préférence local/cloud
- **RuntimeEvents** — timeline temps réel : 8 types d'événements runtime avec filtres
- **RuntimeControls** — barre d'actions : refresh, health check, reset circuit, disable, enable
- **RuntimeClient** — 13 endpoints : list, get, health, metrics, decisions, policies, events, refresh, healthCheck, resetCircuit, disable, enable, export
- **Hooks runtime** — 10 hooks : useRuntimeList (10s), useRuntime (10s), useRuntimeHealth (5s), useRuntimeMetrics (10s), useRuntimeDecisions (15s), useRuntimeDecision, useRuntimePolicies, useRuntimeEvents (5s), useRuntimeControl
- **Types runtime** — RuntimeDetail, RuntimeDecisionInfo, RuntimePolicyInfo, RuntimePolicyRuleInfo, RuntimeEvent, RuntimeControlAction

### Validation
- Build Next.js 16 : ✅ (Turbopack, 5.6s)
- TypeScript strict : ✅
- Pages : 11 statiques (dont /runtimes)

### Ajouté
- **Agent Center** — page /agents avec 8 panneaux redimensionnables (react-resizable-panels)
- **AgentOverview** — 8 stat-cards : total, actifs, complétés, échecs, sous-agents, succès, durée moyenne, runtimes
- **AgentTable** — tableau TanStack : nom, état, runtime, mission, durée, retries, progression (tri, filtre, sélection)
- **AgentInspector** — panneau d'inspection : état, runtime, durée, retries, fallback, erreur, scores fiabilité/performance, historique des transitions, circuit breaker, sous-agents
- **AgentGraph** — visualisation React Flow mission → agents → sous-agents avec couleurs par état
- **AgentTimeline** — timeline temps réel : événements created/ready/running/completed/failed/paused/recovered
- **AgentPerformance** — graphiques Recharts : barres durée par agent, pie runtimes, histogramme
- **AgentHermesCard** — carte Hermes Agent : statut connexion, sessions, capacités, connect/disconnect, créer sous-agent
- **AgentControls** — barre d'actions : pause, resume, cancel, retry, recover, duplicate
- **AgentClient** — 17 endpoints : list, get, statistics, graph, timeline, performance, control, hermes
- **Hooks agents** — 9 hooks : useAgents (5s), useAgent (5s), useAgentStatistics (15s), useAgentGraph (10s), useAgentTimeline (5s), useAgentPerformance (15s), useHermesStatus, useAgentControl
- **Types agent** — AgentInfo, AgentDetail, AgentStatisticsResponse, AgentGraphData, AgentTimelineEvent, AgentPerformanceData

### Validation
- Build Next.js 16 : ✅ (Turbopack, 5.6s)
- TypeScript strict : ✅
- Pages : 11 statiques (dont /agents)

### Ajouté
- **Execution Center** — page /execution avec 6 panneaux redimensionnables (react-resizable-panels)
- **ExecutionOverview** — état global, progression, durée, runtime, agents, tâches
- **LiveGraph** — DAG temps réel React Flow avec mise à jour WebSocket (couleurs par statut, mini-map, zoom)
- **TaskTable** — tableau TanStack des tâches actives (tri, filtre, statut, runtime, agent, durée, retries)
- **ExecutionTimeline** — timeline temps réel avec événements WebSocket, auto-scroll, filtres par type, sévérité
- **PerformanceCharts** — graphiques Recharts : barres durée tâches, pie runtime usage, line latence trend
- **ExecutionControls** — barre de contrôle : pause, resume, cancel, recover, retry failed, export logs, tick
- **ExecutionClient** — API client complet avec données sample pour développement hors-ligne
- **Hooks execution** — `useExecutionOverview()`, `useExecutionTasks()`, `useExecutionPerformance()`, `useExecutionGraph()`, `useExecutionStatistics()`, `useExecutionTimeline()`, `useExecutionControl()`
- **Types execution** — `ExecutionOverviewResponse`, `ExecutionTask`, `ExecutionTimelineEvent`, `ExecutionPerformanceData`, `ExecutionStatisticsResponse`

### Dépendances ajoutées
- `recharts` — graphiques de performance
- `react-resizable-panels` — panneaux redimensionnables

### Validation
- Build Next.js 16 : ✅ (Turbopack, 5.6s)
- TypeScript strict : ✅
- Pages : 11 statiques (dont /execution)

### Ajouté
- **Mission Center** — page /missions complète avec 5 panneaux intégrés
- **MissionListTable** — liste des missions avec TanStack Table (tri, recherche, filtrage)
- **MissionForm** — création de mission avec react-hook-form + zod (titre, description, objectif, priorité, stratégie, planificateur)
- **MissionDetails** — panneau détaillé : statistiques, progression, plan d'exécution
- **MissionActions** — barre d'actions contextuelles : start/pause/resume/cancel/duplicate/delete/sync Freebuff
- **VisualPlanner** — visualisation DAG avec React Flow (mini-map, zoom, contrôles, couleurs par statut)
- **Mission Planner API** — `MissionPlanner` client avec generateSampleGraph() pour démo
- **Hooks missions** — `useMissionList()`, `useMission()`, `useMissionPlan()`, `useMissionGraph()`, `useCreateMission()`, `useStartMission()`, `usePauseMission()`, `useResumeMission()`, `useCancelMission()`, `useDeleteMission()`, `useDuplicateMission()`, `useSyncFreebuff()`
- **Types enrichis** — `CreateMissionRequest`, `MissionPlan`, `ExecutionGraphData`, `GraphNode`, `GraphEdge`, `PlanningStrategy`, `PlannerType`

### Dépendances ajoutées
- `@xyflow/react` — Visual Planner DAG
- `@tanstack/react-table` — Mission list table
- `react-hook-form` + `@hookform/resolvers` + `zod` — Formulaire création
- `@dnd-kit/core` + `@dnd-kit/sortable` — Préparation drag & drop futur

### Intégration Freebuff
- Planificateur Freebuff disponible dans le formulaire de création
- `syncWithFreebuff()` — synchronisation mission → Freebuff
- `FreebuffSyncResult` — prompt, réponse, plan, date

### UX
- Loading skeletons, empty states, error states
- Animations transitions, hover states
- Formulaire avec validation temps réel
- Actions contextuelles selon le statut de la mission

### Validation
- Build Next.js 16 : ✅ (Turbopack, 4.1s)
- TypeScript strict : ✅
- 10 pages statiques maintenues

### Ajouté
- `frontend/src/types/mission-control.ts` — 30+ types TypeScript correspondant aux modèles Pydantic HOS-028
- `frontend/src/lib/mission-control.ts` — `MissionControlClient` client REST fortement typé (20 endpoints)
- `frontend/src/hooks/use-dashboard.ts` — 17 hooks TanStack Query (auto-refresh 5s/15s/30s)
- `frontend/src/hooks/use-events.ts` — WebSocket hook avec reconnexion automatique
- `frontend/src/store/dashboard-store.tsx` — store contextuel (sidebar, filtres événements, refresh)
- `frontend/src/components/layout/` — Sidebar, Topbar, StatusBar, DashboardLayout
- `frontend/src/components/dashboard/` — 7 composants : HealthCard, StatisticsCard, RuntimeTable, MissionList, EventTimeline, FreebuffCard, HermesCard
- `frontend/src/app/dashboard/page.tsx` — Dashboard principal avec grille complète
- 6 pages placeholder : /missions, /runtimes, /agents, /memory, /skills, /events, /settings
- `frontend/src/app/providers.tsx` — QueryClientProvider avec configuration optimisée
- Lien "Dashboard" dans le header de la page Chat existante

### Composants

| Composant | Rôle |
|---|---|
| `HealthCard` | État système, version, uptime, sous-systèmes, chargement/erreur/empty states |
| `StatisticsCard` | Missions, agents, runtimes, mémoire, skills, événements |
| `RuntimeTable` | Tableau responsive des runtimes avec barres de score |
| `MissionList` | Missions récentes avec progression, priorité, runtime, durée |
| `EventTimeline` | Timeline temps réel via WebSocket, filtres par sévérité |
| `FreebuffCard` | Intégration Freebuff : statut, projets, dernière sync |
| `HermesCard` | Intégration Hermes Agent : statut, sessions, capacités |
| `Sidebar` | Navigation complète 10 sections + responsive (collapse) |
| `Topbar` | Recherche, indicateur santé, notifications |
| `StatusBar` | Statut système, version, uptime, connexion WebSocket |

### Validation
- Build Next.js 16 : ✅ (Turbopack, 2.9s)
- TypeScript strict : ✅
- Routes : 10 pages, toutes statiquement générées

---

## [HOS-028] — 2026-07-29 — Mission Control API

### Ajouté
- `backend/api/` package complet
- `MissionControlRouter` — agrège 38 routes REST
- `MissionControlAPI` — point d'entrée FastAPI
- WebSocket `/ws/events` — streaming temps réel des SystemEvent
- 30 Pydantic models pour validation requests/réponses
- Filtrage WebSocket par sources (query param `?sources=runtime,memory`)

### Tests
- 63 tests API (REST + WebSocket) — `tests/api/test_mission_control_api.py`

---

## [HOS-027] — 2026-07-29 — Mission Control Service Layer

### Ajouté
- `backend/services/` package
- `MissionControlService` — façade centrale agrège tous les sous-systèmes
- 9 façades : Mission, Runtime, Exécution, Mémoire, Skills, Événements, Hermes, Freebuff, Système
- `health()`, `diagnostics()`, `statistics()`, `status()`

### Tests
- 63 tests — `tests/architecture/test_mission_control_service.py`
- 630 total architecture tests

---

## [HOS-026] — 2026-07-29 — Freebuff Adapter

### Ajouté
- `FreebuffAdapter` avec `FreebuffSession`, `FreebuffProject`, `FreebuffPrompt`, `FreebuffResponse`
- Pipeline Mission → FreebuffPrompt → TaskPlan → ExecutionGraph
- 4 modes de connexion : API, TERMINAL, CLI, MCP

### Tests
- 44 tests — `tests/integrations/test_freebuff_adapter.py`

---

## [HOS-025] — 2026-07-29 — System Event Bus

### Ajouté
- `SystemEventBus` — bus central pub/sub unifié
- `SystemEventType` — 9 familles : RUNTIME, AGENT, MISSION, EXECUTION, MEMORY, SKILL, SYSTEM, OBSERVABILITY, INTEGRATION
- `EventFilter` — filtrage par type, source, sévérité, temps
- `EventHistory` — historique configurable avec export JSON
- Helpers de mapping depuis HOS-013

### Tests
- 44 tests — `tests/architecture/test_system_event_bus.py`

---

## [HOS-024] — 2026-07-29 — Mission Execution Engine

### Ajouté
- `ExecutionEngine` — moteur d'orchestration complet
- `ExecutionScheduler` — identification des tâches prêtes, groupes parallèles
- 9 états : IDLE → INITIALIZING → RUNNING ↔ PAUSED → COMPLETED/FAILED/CANCELLED
- Intégration Supervisor + Lifecycle + DecisionEngine + Router

### Tests
- 37 tests — `tests/architecture/test_execution_engine.py`

---

## [HOS-023] — 2026-07-29 — Hermes Agent Adapter

### Ajouté
- `HermesAgentAdapter` — pont complet Hermes OS → Hermes Agent
- Mapping : RuntimeDecision → ModelRouter, UnifiedMemory → EchoAgent, TaskPlan → Hermes Tasks
- 7 capacités : CHAT, CHAT_STREAM, TOOLS, MEMORY, SKILLS, SUBAGENTS, DELEGATION

### Tests
- 35 tests — `tests/integrations/test_hermes_adapter.py`

---

## [HOS-022] — 2026-07-29 — Adaptive Skill Orchestrator

### Ajouté
- `AdaptiveSkillOrchestrator` avec 4 stratégies de sélection
- `SkillRepository` / `InMemorySkillRepository`
- Résolution de dépendances, limites de tokens, bundles

### Tests
- 24 tests — `tests/architecture/test_skill_orchestrator.py`

---

## [HOS-021] — 2026-07-29 — Unified Memory

### Ajouté
- `UnifiedMemory` — façade mémoire unifiée
- `MemoryBackend` abstrait + `InMemoryBackend`
- 7 scopes : SESSION, MISSION, AGENT, PROJECT, USER, GLOBAL, EXPERIENCE
- Import/Export JSON, événements, statistiques

### Tests
- 33 tests — `tests/architecture/test_unified_memory.py`

---

## [HOS-020] — 2026-07-29 — Multi-Agent Supervisor

### Ajouté
- `MultiAgentSupervisor` — orchestration centrale missions + agents
- `MissionState` : 8 états avec transitions
- `tick()` — boucle de progression
- Intégration TaskPlanner + ExecutionGraph + Lifecycle

### Tests
- 28 tests — `tests/architecture/test_supervisor.py`

---

## [HOS-019] — 2026-07-29 — Agent Lifecycle Manager

### Ajouté
- `AgentLifecycleManager` — machine à états 10 états
- Transitions validées, thread-safe
- `on_event()` callback pour observabilité
- `check_timeouts()`, `cleanup()`

### Tests
- 33 tests — `tests/architecture/test_lifecycle.py`

---

## [HOS-018] — 2026-07-29 — Task Planning Engine

### Ajouté
- `TaskPlanner` avec 4 stratégies : SEQUENTIAL, BALANCED, PARALLEL, CONSERVATIVE
- `PlanningValidator` — dépendances, cycles, capacités
- Production directe d'ExecutionGraph

### Tests
- 30 tests — `tests/architecture/test_task_planner.py`

---

## [HOS-017] — 2026-07-29 — Execution Graph

### Ajouté
- `ExecutionGraph` — DAG thread-safe
- Détection de cycles (Kahn), tri topologique
- `GraphExecutionPlan` avec niveaux de parallélisme
- Sérialisation JSON

### Tests
- Tests intégrés dans les modules ultérieurs

---

## [HOS-016] — 2026-07-29 — Runtime Policy Engine

### Ajouté
- `RuntimePolicy` — politique immuable avec règles
- `RuntimePolicyEngine` — évaluation par contexte d'exécution
- Règles : capability_required, provider_allowed, latency_max, reliability_min

### Tests
- Tests intégrés dans RuntimeDecisionEngine

---

## [HOS-015] — 2026-07-29 — Runtime Decision Engine

### Ajouté
- `RuntimeDecisionEngine` — score composite 0-1000
- 6 facteurs : Health + Reliability + Performance + Capability + Policy - CircuitPenalty
- `RuntimeDecision` immutable avec explication

### Tests
- Tests intégrés dans la suite architecture

---

## [HOS-014] — 2026-07-29 — Runtime Performance Analyzer

### Ajouté
- `RuntimePerformanceAnalyzer` — analyse des événements runtime
- `RuntimePerformanceMetrics` — scores de fiabilité et performance
- Classement des runtimes

### Tests
- Tests intégrés

---

## [HOS-013] — 2026-07-29 — Runtime Event Bus & Observability

### Ajouté
- `RuntimeEventBus` — bus événements runtime
- `RuntimeObservability` — métriques agrégées
- 11 types d'événements

### Tests
- Tests intégrés

---

## [HOS-012] — 2026-07-29 — Runtime Recovery & Failover

### Ajouté
- `RuntimeRecoveryManager` — gestion des pannes runtime
- `CircuitBreaker` — 3 états : CLOSED → OPEN → HALF_OPEN
- `ExecutionTrace` — traçage des fallbacks

### Tests
- Tests intégrés

---

## [HOS-011] — 2026-07-29 — Runtime Health Monitor

### Ajouté
- `RuntimeHealthMonitor` — AVAILABLE/DEGRADED/UNAVAILABLE/UNKNOWN
- `RuntimeMetrics` — compteurs d'exécution, taux d'échec

### Tests
- Tests intégrés

---

## [HOS-010] — 2026-07-29 — Runtime Execution Router

### Ajouté
- `RuntimeRouter` — routage avec fallback et recovery
- Résolution : actif → fallback → préférence → sélecteur
- Publication d'événements sur toutes les étapes

### Tests
- Tests intégrés

---

## [HOS-009] — 2026-07-29 — Runtime Selection & Context

### Ajouté
- `ActiveRuntimeContext` — gestion du runtime actif + fallback
- `RuntimeSelector` — sélection par règles extensibles

### Tests
- Tests intégrés

---

## [HOS-008] — 2026-07-28 — SDS Runtime Wiring

### Ajouté
- `init_runtime_registry_in_holder()` — initialisation registry + factory
- Intégration dans le lifespan FastAPI

---

## [HOS-007] — 2026-07-28 — Runtime Registry & Factory

### Ajouté
- `RuntimeRegistry` — registre thread-safe
- `RuntimeFactory` — builders par type
- `RuntimeLifecycle` — initialize/health_check/shutdown

---

## [HOS-006] — 2026-07-28 — Ollama Connector

### Ajouté
- `OllamaClientProtocol` — contrat client Ollama
- `OllamaClient` — client HTTP configurable
- `FakeOllamaClient` — mock pour tests
- Support chat + chat_stream + timeout

---

## [HOS-005] — 2026-07-28 — HermesOllamaRuntime

### Ajouté
- Premier runtime agentique réel basé sur Ollama
- Implémente RuntimeInterface, capacité Chat

---

## [HOS-004] — 2026-07-28 — StubRuntime

### Ajouté
- Premier runtime de démonstration
- `StubRuntime` conforme à `RuntimeInterface`
- `StubChatCapability` conforme à `ChatCapability`
- Publication RUNTIME_STARTED / RUNTIME_STOPPED

---

## [HOS-003] — 2026-07-28 — SDS Wiring

### Ajouté
- Câblage FastAPI complet
- Forward EventBusImpl → EventHub
- Proxy legacy `agent.message`

---

## [HOS-002] — 2026-07-28 — EventBusImpl

### Ajouté
- Bus d'événements SQLite
- Publication/abonnement par topic
- TopicPattern("*") pour forwarding wildcard

---

## [HOS-001] — 2026-07-28 — RAL Interfaces

### Ajouté
- `RuntimeInterface` Protocol
- `ChatCapability` Protocol
- `CapabilitySet`, `ChatResponse`
- RuntimeStatus enum

---

## [HOS-000] — 2026-07-28 — Foundation

### Ajouté
- Projet Hermes OS initial
- Structure SDS legacy
- 48 tests de base
