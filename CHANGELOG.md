# Changelog — Hermes OS

> Toutes les modifications notables du projet Hermes OS.
> Format basé sur [Keep a Changelog](https://keepachangelog.com/).

---

## [HOS-029] — 2026-07-29 — Mission Control Dashboard (Next.js)

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
