## [HOS-064] — 2026-07-29 — Human Experience & Natural Interaction Layer

### Ajouté
- **Conversation Intelligence** (\`backend/conversation/\`) :
  - ConversationManager — sessions, messages, intent routing
  - IntentAnalyzer — 11 intent types (optimization, analysis, debug, refactor, doc, command, greeting, approval, cancel, question)
  - ContextBuilder — enrichment from Memory, Agents, Missions, Runtime
  - ResponseGenerator — contextual responses with approval flow, suggested actions
  - REST API (7 endpoints) + WebSocket ready
- **Explainability** (\`backend/explainability/\`) :
  - DecisionExplainer — human-readable explanations for agent/runtime/model/tool/skill/policy decisions
  - Alternative ranking with pros/cons, risk levels, rollback info
  - REST API (3 endpoints)
- **Approval Flow Enhanced** (\`backend/policy/approval_explainer.py\`) :
  - ApprovalExplainer — clear risk/impact descriptions, agent scope, rollback status
  - Pending queue with approve/reject workflow
- **Voice Ready** (\`backend/voice/\`) :
  - SpeechToTextProvider abstract (Whisper, Cloud)
  - TextToSpeechProvider abstract (Piper, Cloud)
- **Frontend : Conversation Center** (\`conversation-center.tsx\`) :
  - Chat interface with streaming simulation
  - Markdown rendering, approval banners, suggested actions
  - Real-time status indicators
- **Tests :** 103 tests (session management, intent detection, context building, response gen, explainability, approval, voice, thread safety)

### Documentation
- docs/architecture/HUMAN_EXPERIENCE_ARCHITECTURE.md — conversational architecture, REST API, WebSocket, approval flow
## [HOS-062] — 2026-07-29 — Production Readiness & Deployment Layer

### Ajouté
- **Configuration Management** (\`backend/config/\`) :
  - ConfigManager singleton with 6 deployment profiles (local_gpu, cpu_only, wsl, docker, server, cloud_gpu)
  - HermesConfig with nested DatabaseConfig, RedisConfig, VectorConfig, SecurityConfig, MonitoringConfig, LoggingConfig, RuntimeConfig
  - EnvironmentLoader with profile-required and optional env vars
  - Config validation, JSON profile loading, env override
- **Installer** (\`installer/\`) :
  - SystemDetector — detects OS, CPU, RAM, GPU (NVIDIA/AMD), VRAM, disk, Docker, WSL
  - HardwareProfile — 6 predefined profiles with min/recommended specs
  - Profile recommendation and model suggestion based on hardware
- **Persistence Layer** (\`backend/storage/\`) :
  - DatabaseManager — SQLite (dev) and PostgreSQL (prod) with connection pooling
  - MigrationManager — schema versioning, upgrade/rollback
  - BackupManager — zip-based backup/restore, config export/import, auto-backup
- **Monitoring** (\`backend/monitoring/\`) :
  - SystemMonitor — CPU, RAM, disk metrics, service checks, alerts
  - HealthMonitor — component registration, check intervals, 3-strikes unhealthy
  - RecoveryManager — configurable max attempts, cooldown, reset
- **Logging** (\`backend/logging/\`) :
  - ProductionLogger — structured JSON logs, RotatingFileHandler, correlation IDs
  - mission_log, agent_log, event_log methods
  - Global singleton get_logger()
- **Deployment** (\`deployment/\`) :
  - Dockerfile.backend (Python 3.11, FastAPI, uvicorn)
  - Dockerfile.frontend (Next.js build + Nginx)
  - docker-compose.yml (PostgreSQL + Redis + ChromaDB + Backend + Frontend)
  - docker-compose.gpu.yml (adds Ollama with NVIDIA GPU + Prometheus)
  - docker-compose.cpu.yml (CPU-only with Ollama)
  - nginx.conf (gzip, caching, API proxy, WebSocket, security headers)
- **Frontend : Deployment Center** (\`deployment-center.tsx\`) :
  - System overview with component health, service status
  - Hardware profile display
  - Backup management with create/restore/delete
  - Health monitoring with latency
  - Quick actions (backup, health check, export, report)
- **Tests :** 80+ tests covering config, hardware, database, migrations, backups, monitoring, health, recovery, logging, thread safety

### Documentation
- docs/architecture/PRODUCTION_ARCHITECTURE.md — deployment architecture, configuration system, monitoring, backup strategy, production recommendations
## [HOS-063] — 2026-07-29 — Autonomous Agentic Core Final Layer

### Ajouté
- **Autonomous Models** (\`autonomous_models.py\`) :
  - 5 dataclasses : AutonomousGoal, AutonomousSession, AutonomousDecision, AutonomousReport, AutonomousTimeline
  - 3 enums : GoalStatus (8 états), DecisionType (5 types), GoalPhase (7 phases)
  - 12 événements EventBus couvrant tout le cycle de vie (received→analyzed→planned→executed→learned→failed)
- **AutonomousInterpreter** (\`autonomous_interpreter.py\`) :
  - Transforme une requête humaine en objectif structuré (domaine, langage, complexité, contraintes)
  - 8 domaines avec scoring pondéré (code×2 pour les signaux forts)
  - Intégration Memory pour enrichir l'interprétation
- **DecisionEngine** (\`decision_engine.py\`) :
  - 4 types de décisions : Agent, Runtime, Skill, Tool
  - Confidence scoring 0-100, alternatives ranking
- **AutonomousGuard** (\`autonomous_guard.py\`) :
  - Vérifications Security + Policy avant chaque action
  - Pre-flight, pre-execution, pre-skill, pre-agent checks
- **AutonomousMemoryLoop** (\`autonomous_memory_loop.py\`) :
  - Collecte post-mission : succès, erreurs, durée, ressources, agents, modèles, outils
  - Alimente EpisodicMemory, ProceduralMemory, EvolutionEngine
- **AutonomousOrchestrator** (\`autonomous_orchestrator.py\`) :
  - Pipeline complet : Goal→Interprétation→Memory→Planner→DAG→Agents→Skills→Runtime→Tools→Security→Execution→Validation→Memory→Evolution→Report
  - Timeline avec 7 phases
- **AutonomousEngine** (\`autonomous_engine.py\`) :
  - Moteur central avec start/pause/resume/cancel/get_status/generate_report
  - Gestion des sessions actives
- **REST API** (\`routes.py\`) :
  - 7 endpoints : POST /start, GET /{id}, POST /pause/resume/cancel, GET /timeline/report
- **Frontend : Autonomous Mission Console** (\`autonomous-center.tsx\`) :
  - Objectif actuel, interprétation IA, DAG mission, agents actifs, runtime/tools
  - Progression temps réel, décisions, confiance, rapport
- **Tests :** 71 tests (9 classes) couvrant models, interpreter, decisions, guard, memory, orchestrator, engine, API, full mission simulation

### Modifié
- **Sidebar** → nouvelle entrée "Autonomous OS"
- **EVENT_CATALOG.md** → +12 événements autonomous.* (103 total, 12 familles)

### Documentation
- docs/architecture/AUTONOMOUS_OS_ARCHITECTURE.md — architecture complète, boucle autonome, diagrammes Mermaid
# Changelog — Hermes OS

> Toutes les modifications notables du projet Hermes OS.
> Format basé sur [Keep a Changelog](https://keepachangelog.com/).

---

## [HOS-055D] — 2026-07-29 — Code Intelligence Final Integration
## [HOS-058] — 2026-07-29 — Self Evolution & Continuous Improvement Engine

### Ajouté
- **Evolution Models** (\`evolution_models.py\`) :
  - 6 dataclasses : EvolutionProposal, EvolutionExperiment, OptimizationPattern, EvolutionReport, SystemMetrics
  - 4 enums : EvolutionType (7 types), EvolutionStatus (6 statuts), RiskLevel (4 niveaux)
  - 7 événements EventBus : proposal.created, simulation.completed, approved, applied, failed, pattern.discovered, report.generated
- **EvolutionAnalyzer** (\`evolution_analyzer.py\`) :
  - 5 dimensions d'analyse : Runtime (3 règles), Agents (2), Skills (2), Missions (2), Memory (2)
  - Sliding window de 100 métriques, suivi de tendances
- **ImprovementDetector** (\`improvement_detector.py\`) :
  - 6 détections automatiques : runtime sous-performant, skills inutiles/manquants, modèle meilleur, workflow inefficace, goulots
  - Enregistrement des patterns d'optimisation
- **EvolutionSimulator** (\`evolution_simulator.py\`) :
  - Simulation avant/après avec estimation d'impact
  - Évaluation des risques et conclusion (improvement/regression/no_change)
- **EvolutionValidator** (\`evolution_validator.py\`) :
  - Intégration Policy Engine HOS-046 + Security Engine HOS-057
  - 3 verdicts : ALLOW (risque faible), REVIEW (moyen/élevé), DENY (architecture/sécurité)
  - Règles configurables, overrides
- **EvolutionEngine** (\`evolution_engine.py\`) :
  - Pipeline complet : Collect → Analyze → Detect → Propose → Simulate → Validate → Apply → Learn
  - Approbation/rejet manuel, rapports périodiques
- **EvolutionScheduler** (\`evolution_scheduler.py\`) :
  - 3 modes : Hourly (60s), Daily (5min), Weekly (15min)
  - Thread background avec génération de métriques sample
- **EvolutionCenter** (\`evolution-center.tsx\`) — Cockpit interactif :
  - 5 stats (proposals, applied, pending, gain, confidence)
  - Tableau des 8 propositions avec type, gain, risque, confiance, statut
  - Pipeline visuel en 8 étapes
  - Patterns d'optimisation et rapports récents
- **API Routes** : 7 endpoints REST
- **Documentation** : SELF_EVOLUTION_ARCHITECTURE.md

### Tests
- 66 tests (9 classes : Models, Analyzer, Detector, Simulator, Validator, Engine, Scheduler, API, ThreadSafety)


## [HOS-057] — 2026-07-29 — Security, Sandbox & Trust Layer

### Ajouté
- **Security Models** (\`security_models.py\`) :
  - 9 dataclasses : SecurityPolicy, Permission, CapabilityToken, AgentTrustScore, SecurityEvent, ThreatDetection, IsolationProfile
  - 7 enums : TrustLevel (5 niveaux), ThreatLevel (5 niveaux), PermissionAction, ResourceType (9 types), IsolationLevel (5 niveaux)
  - 6 événements EventBus : permission.checked, permission.denied, threat.detected, agent.trust.updated, isolation.created, isolation.violation
- **PermissionManager** (\`permission_manager.py\`) :
  - Grant/revoke/check permissions par agent, skill, tool, workspace, runtime
  - Policy evaluation par priorité avec conditions
  - Historique des 500 dernières opérations
- **AgentTrustEngine** (\`agent_trust_engine.py\`) :
  - Score dynamique 0-100 basé sur 5 facteurs pondérés
  - 5 niveaux de confiance : UNKNOWN → LOW → MEDIUM → HIGH → VERIFIED
  - Notifications automatiques, seuils configurables
- **ThreatDetector** (\`threat_detector.py\`) :
  - 4 détections temps réel : accès fichiers, ressources, outils suspects, violations sandbox
  - Mitigation, historique incidents, stats par type/niveau
- **IsolationManager** (\`isolation_manager.py\`) :
  - 5 niveaux d'isolation : NONE → LOW → MEDIUM → HIGH → MAXIMUM
  - Validation filesystem, réseau, outils, ressources
  - Sessions actives, profil par défaut par niveau
- **SecurityEngine** (\`security_engine.py\`) :
  - Pipeline complet : Policy → Permission → Trust → Threat → Isolation → Allow/Deny/Review
  - Intégration Policy Engine HOS-046, EventBus, trust automatisé
- **API Routes** (\`routes.py\`) : 9 endpoints REST
- **SecurityCenter** (\`security-center.tsx\`) — Cockpit interactif :
  - 4 stats overview (trust, permissions, threats, isolation)
  - 8 agents trust scores avec barres de progression
  - Active threats list, permissions/policies matrix
  - 6 isolation profiles grid
- **Sidebar** : entrée "Security" ajoutée

### Tests
- 75 tests (8 classes : Models, PermissionManager, AgentTrustEngine, ThreatDetector, IsolationManager, SecurityEngine, APIRoutes, ThreadSafety)


## [HOS-056] — 2026-07-29 — Hermes OS Global Integration Audit & System Consolidation

### Ajouté
- **System Integration Layer** (`backend/core/integration/`) :
  - IntegrationManager — central orchestrator for all 25 components
  - ComponentRegistry — tracks every module with id, name, category, deps, capabilities, events, health
  - DependencyGraph — topological sort, cycle detection, impact analysis
  - HealthOrchestrator — aggregate health across all components with warnings
- **Global Health Monitoring** (`backend/core/health/`) :
  - SystemHealth — runs 12+ health checks across EventBus, Memory, Runtime, Agents, Tools, MCP, Intégrations
  - SystemHealthReport — JSON-reportable unified health status
  - 12 predefined health checks covering all subsystems
- **Event Catalog** (`docs/architecture/EVENT_CATALOG.md`) :
  - 91 unique events cataloged across 11 families
  - Producer/consumer matrix for each event
  - Naming conventions and statistics
- **Complete Architecture Documentation** (`docs/architecture/HERMES_OS_COMPLETE_ARCHITECTURE.md`) :
  - 25-component module registry
  - Mermaid data flow diagrams (development, inference, search, health)
  - Event bus architecture with 91 events
  - Agent system, memory system, and HOS completion matrix
- **Frontend System Center** (`system-center.tsx`) :
  - Health overview with healthy score, component count, warnings
  - 10 component categories with counts
  - Dependency graph (topological order, warnings)
  - Full component list table with status, latency, events
  - Architecture diagram (6-layer grid)
- **Sidebar** : entrée "System" ajoutée

### Tests
- 80+ end-to-end integration tests (12 classes : DevelopmentMission, AIInference, DocumentSearch, CodeIntelligence, MultiAgent, IntegrationManager, DependencyGraph, HealthOrchestrator, SystemHealth, ThreadSafety, EventFlow, EdgeCases)

### Architecture
```
System Integration Layer
       |
Component Registry (25 components)
       |
Health Orchestrator → 12 health checks
       |
Cockpit System Center
```



### Ajouté
- **CodeIntelligenceRouter** (`code_intelligence_router.py`) — moteur de scoring intelligent KlaatCode ↔ Oh My Pi :
  - 5 facteurs pondérés : task_fit (30%), lsp_dap_ast (20%), historical_success (25%), cost_efficiency (15%), language_match (10%)
  - 3 stratégies : single_best, hybrid_both, force provider
  - Mapping 10 types de tâches → provider(s) optimal
  - Historique adaptatif (100 dernières exécutions par provider)
  - Exécution hybride : KC analyse → OMP LSP/DAP/AST
- **CodeIntelligenceAgent** (`code_intelligence_agent.py`) — meta-agent orchestrateur :
  - Cycle de vie complet CREATED→READY⇄BUSY→PAUSED/FAILED/STOPPED
  - Pipeline : Classify → Route → Execute (single/hybrid) → Memory → EventBus
  - Métriques par provider (klaatcode_tasks, ohmypi_tasks, hybrid_tasks)
  - 7 événements EventBus : ci.agent.ready, ci.routing.decided, ci.task.*, ci.hybrid.executed, ci.memory.recorded
- **CIRuntimeScorer** (`ci_scorer.py`) — scoring runtime pour Runtime Orchestrator :
  - 5 facteurs : task_fit, historical_success, resource_cost, avg_duration, complexity_mod
  - Context modifiers : requires_lsp/dap boost OMP +20%, reduce KC -20%
  - Recommandation automatique avec ranking
- **CodeIntelligenceCenter** (`code-intelligence-center.tsx`) — Cockpit interactif :
  - Task Routing Map (10 types avec scores KC/OMP et best provider)
  - Provider stats (total tasks, success rate, KlaatCode/OhMyPi/hybrid count)
  - Decision visualization avec barres de score
  - Routing pipeline + Provider capabilities
- **Sidebar** : entrée "Code Intel" ajoutée

### Tests
- 51 tests (9 classes : RouterSelection, RouterHistory, AgentLifecycle, TaskExecution, Events, RuntimeScoring, Models, ThreadSafety, Factory)

### Documentation
- CODE_INTELLIGENCE_ARCHITECTURE.md (Mermaid, flux, matrices, pipeline examples)


## [HOS-055C] — 2026-07-29 — Oh My Pi Deep Integration Layer

### Ajouté
- **LSPBridgeAdapter** (`lsp_bridge_adapter.py`) — pont LSP Oh My Pi → Knowledge Graph :
  - Indexation symboles, diagnostics, structures de code
  - Recherche par nom/fichier, références, stats
  - Relations KG : File→DEFINES→Symbol, File→HAS_DIAGNOSTIC
- **ASTAdapter** (`ast_adapter.py`) — pont tree-sitter Oh My Pi → Knowledge Graph :
  - Détection fonctions, classes, imports, dépendances
  - Estimation complexité (cyclomatique, lignes, fonctions, profondeur)
  - Relations KG : File→CONTAINS_FUNCTION/CLASS, Function→CALLS, File→IMPORTS/DEPENDS_ON
- **DebugAdapter** (`debug_adapter.py`) — pont DAP Oh My Pi → EventBus :
  - Sessions debug avec breakpoints, stack trace, variables
  - Historique incidents, stats
  - Événements : debug.started, debug.breakpoint, debug.failed, debug.completed
- **WorkspaceAdapter** (`workspace_adapter.py`) — pont Oh My Pi → WorkspaceManager :
  - Pipeline : Edit → Sandbox → Git branch → Validation → Commit
  - Rollback support, validation path check
  - Événements : workspace.edit_prepared/committed/rolled_back
- **RuntimeAdapter** (`runtime_adapter.py`) — Oh My Pi comme candidat runtime :
  - Score de suitability 0-1 par type de tâche
  - Context modifiers (debug +15%, documentation -20%)
  - Recommandation avec seuil 0.5
- **MemoryAdapter** (`memory_adapter.py`) — pont Oh My Pi → Memory System :
  - Enregistrement expériences (succès/échec, durée, fichiers)
  - Patterns de code réutilisables
  - Corrections efficaces classées par succès
- **OhMyPiPanel** (`ohmypi-panel.tsx`) — Cockpit interactif :
  - 9 outils MCP avec icônes et catégories
  - Stats (executions, success rate, avg latency, failures)
  - Pipeline visuel (6 adaptateurs)
  - Quick actions (LSP Analyze, Debug, Run Python, AST Transform)
- **Types frontend** : OhMyPiStatus, OhMyPiCapability, OhMyPiExecutionResult, LSPDiagnostic, LSPSymbol, DebugSession
- **Client frontend** : ohmypiClient (status, capabilities, execute)
- **Documentation** : OHMYPI_DEEP_INTEGRATION_ARCHITECTURE.md (Mermaid, flux, matrices)

### Tests
- 58 tests deep integration (9 classes : LSPBridge, ASTAdapter, DebugAdapter, WorkspaceAdapter, RuntimeAdapter, MemoryAdapter, Events, ThreadSafety)
- Combiné HOS-055B : 112 tests totaux Oh My Pi

### Architecture
```
Hermes Agent → OhMyPiAgent → MCP Adapter (9 tools) → omp CLI
                    ↓
     ┌──────────────┼──────────────┬──────────────┬──────────────┐
     ↓              ↓              ↓              ↓              ↓
  LSPBridge     ASTAdapter    DebugAdapter  WorkspaceAdpt  RuntimeAdpt
     ↓              ↓              ↓              ↓              ↓
  Knowledge      Knowledge      EventBus      Workspace      Runtime
   Graph          Graph                        Manager       Orchestrator
                                              + Validation
```


## [HOS-055B] — 2026-07-29 — Oh My Pi Agent Integration

### Ajouté
- **OhMyPiClient** (`ohmypi_client.py`) — wrapper headless CLI pour omp : détection installation, exécution RPC, timeout, health check, historique 500
- **OhMyPiMCPAdapter** (`ohmypi_mcp_adapter.py`) — expose 9 outils MCP via pipeline Policy→Sandbox→Execute→EventBus :
  - lsp_open_file, lsp_edit, ast_transform, debug_start, debug_step
  - execute_python, execute_javascript, git_operation, code_search
- **OhMyPiAgent** (`ohmypi_agent.py`) — agent spécialisé LSP/DAP/AST :
  - Cycle de vie complet CREATED→READY⇄BUSY→PAUSED/FAILED/STOPPED
  - Workspace protection : edit_file + ast_transform forcés via WorkspaceManager
  - 6 types d'événements : agent.ready, edit.started/completed, debug.started, execution.completed, error
  - Métriques, historique de tâches, to_agent_dataclass() pour AgentRegistry
- **OhMyPiProfile** (`ohmypi_profile.py`) — 6 capacités, skill levels 0.88-0.98, 9 MCP tools, priorité high
- **OhMyPiCapabilities** (`ohmypi_capabilities.py`) — 8 task types + mapping bidirectionnel task↔capability↔MCP action
- **REST API** (`routes.py`) — GET /ohmypi/status, GET /ohmypi/capabilities, POST /ohmypi/execute
- **Factory** — `create_ohmypi_agent()` : instanciation + démarrage automatique
- **Tests** — 54 tests (10 classes) : models (5), client (5), MCP adapter (8), policy (2), sandbox (2), lifecycle (8), capability (5), execution (6), workspace (3), events (4), routes (3), thread safety (3)

### Architecture
```
Hermes Agent Supervisor → OhMyPiAgent
                           ↓
              OhMyPiMCPAdapter (9 tools)
                           ↓
              Policy → Sandbox → OhMyPiClient → omp CLI
                                              ↓
                              LSP · DAP · AST · Python/JS Exec
```

### Complémentarité KlaatCode ↔ Oh My Pi
| Tâche | KlaatCode | Oh My Pi |
|---|---|---|
| Analyse | ✅ analyze_project | — |
| Édition | edit_file (basic) | ✅ **LSP-wired** (rename+imports) |
| Débogage | — | ✅ **DAP** (lldb, dlv, debugpy) |
| AST | — | ✅ **tree-sitter** |
| Exécution | — | ✅ **Python/JS + callbacks** |
| Diagnostics | ✅ run_diagnostics | ✅ LSP diagnostics |

### Validation
- pytest : ✅ 54/54 passed (0.24s)

---

## [HOS-054D] — 2026-07-29 — KlaatCode Deep Integration

### Ajouté
- **CodeGraphAdapter** (`code_graph_adapter.py`) — pont KlaatCode analysis → Knowledge Graph (HOS-047) :
  - Indexation code : fichiers, classes, fonctions, imports, dépendances
  - 6 types de relations : FILE_IMPORTS, CLASS_CONTAINS, FUNCTION_CALLS, DEPENDS_ON, MODIFIED_BY_AGENT, TESTED_BY
  - Recherche d'entités, sous-graphe par fichier, historique modifications par agent
- **DiagnosticsAdapter** (`diagnostics_adapter.py`) — pont KlaatCode diagnostics → Validation Engine (HOS-050) :
  - Analyse de diagnostics (erreurs, warnings, hints)
  - Catégorisation automatique (compilation, test, qualité, sécurité, style)
  - Pipeline Patch → Diagnostics → Validation → Accept/Reject
  - Suggestions auto-fix extraites des diagnostics
- **CostGuardAdapter** (`cost_guard_adapter.py`) — pont KlaatCode → Runtime Orchestrator (HOS-038) :
  - Estimation complexité 0-10 basée sur type de tâche + taille projet
  - 4 bandes de runtime : low (cpu/small), medium (hybrid/medium), high (gpu/large), extreme (cloud_gpu/xl)
  - Recommandation runtime/modèle avec facteurs et confidence
- **Workspace Protection** (KlaatCodeAgent) :
  - edit_file/refactoring/patch forcés via Workspace → Sandbox → Git
  - Bloque les modifications directes sans workspace_id
  - Validation workspace avant toute écriture
- **Advanced Memory Integration** (KlaatCodeAgent) :
  - Enregistrement épisodique (problème, solution, fichiers, durée, succès/échec)
  - Enregistrement procédural automatique pour réutilisation
  - Recommandations d'expérience : 'Pour une erreur similaire, cette solution a fonctionné X fois'
- **Tests** — 40 tests (8 classes) : Code Graph (8), Diagnostics (9), Cost Guard (7), Workspace (4), Memory (4), Runtime (4), End-to-End (2), Thread Safety (3)

### Exemple : mission KlaatCode complète
```
Mission "Fix login bug"
  → CostGuardAdapter: complexity 6.5/10, recommend gpu/large
  → WorkspaceManager.create(mission_id, agent_id) → branch feature/klaatcode
  → KlaatCodeAgent.execute_task(CODE_ANALYSIS, {path})
    → CodeGraphAdapter: indexes files, classes, deps → Knowledge Graph
  → KlaatCodeAgent.execute_task(CODE_EDITING, {file, content, workspace_id})
    → Workspace protection ✅ → Sandbox → Git commit → MCP edit_file
  → KlaatCodeAgent.execute_task(DIAGNOSTICS, {file})
    → DiagnosticsAdapter: 0 errors, 2 warnings → Validation: PASS
  → Memory: episodic + procedural records
  → ExperienceManager: "For auth fixes, klaatcode_code_editing worked 3 times"
```

### Validation
- pytest : ✅ 40/40 passed (0.05s)

---

## [HOS-054C] — 2026-07-29 — KlaatCode Agent

### Ajouté
- **KlaatCodeAgent** (`klaatcode_agent.py`) — agent spécialisé de développement intégré au système multi-agent Hermes :
  - Cycle de vie complet : CREATED → STARTING → READY ⇄ BUSY → PAUSED/FAILED/STOPPED
  - 6 états opérationnels : IDLE, ANALYZING, GENERATING, EDITING, DIAGNOSING, REVIEWING
  - Exécution de tâches via MCP KlaatCode (HOS-054B) : analyze, generate, edit, review, diagnostics
  - Métriques : total_tasks, success_rate, avg_duration_ms, load tracking
  - Historique : 500 entrées de tâches, 200 résultats d'exécution, historique de lifecycle
- **KlaatCodeProfile** (`klaatcode_profile.py`) — profil statique :
  - 6 capacités : analysis, code_generation, code_review, testing, optimization, documentation
  - Skill levels par domaine (0.75-0.95)
  - Contraintes : max 2 concurrent, timeout 300s, max retries 3
  - 7 MCP tools autorisés, workspace/sandbox requis
- **KlaatCodeCapabilities** (`klaatcode_capabilities.py`) :
  - 9 types de tâches : CODE_ANALYSIS, CODE_GENERATION, CODE_EDITING, REFACTORING, DIAGNOSTICS, TEST_ANALYSIS, PROJECT_NAVIGATION, PATCH_GENERATION, CODE_REVIEW
  - Mapping bidirectionnel : task ↔ capability ↔ MCP action
- **Factory** — `create_klaatcode_agent()` : instanciation et démarrage automatique
- **EventBus** — 6 types d'événements :
  - klaatcode.agent.ready, klaatcode.task.started/completed/failed
  - klaatcode.analysis.completed, klaatcode.patch.generated
- **Memory Integration** — enregistrement épisodique après chaque tâche (langage, projet, difficulté, durée, erreurs, corrections)
- **AgentCoordinator compatible** — `to_agent_dataclass()` pour enregistrement dans AgentRegistry, scoring CapabilityMatcher
- **Tests** — 48 tests (7 classes) : agent creation (7), lifecycle (8), capability matching (6), MCP execution (8), events (5), memory (2), metrics (5), thread safety (3), enums (4)

### Architecture d'exécution
```
Mission DAG → TaskScheduler → AgentCoordinator → KlaatCodeAgent
                                                     ↓
                                              MCP Tools KlaatCode
                                                     ↓
                                              Validation → Memory
```

### Validation
- pytest : ✅ 48/48 passed (0.08s)

---

## [HOS-054B] — 2026-07-29 — KlaatCode MCP Integration

### Ajouté
- **KlaatCodeClient** (`klaatcode_client.py`) — wrapper headless CLI : détection installation, exécution timeout, capture stdout/stderr, health check, historique 500 entrées, stats
- **KlaatCodeMCPAdapter** (`klaatcode_mcp_adapter.py`) — expose 7 outils MCP : analyze_project, inspect_code, generate_code_plan, edit_file, search_code, run_diagnostics, validate_changes
- **Pipeline complet** — Policy → Sandbox → Execute → EventBus pour chaque appel
- **KlaatCodeRequest/Response** — modèles dataclass avec id unique, timeout, workspace_id, timestamps
- **KlaatCodeProject/Diagnostic/Capability** — modèles pour analyse de projet, diagnostics, capacités
- **7 enums** — KlaatCodeAction, KlaatCodeStatus, DiagnosticSeverity
- **Registration module** (`registration.py`) — enregistrement automatique dans Tool Registry (HOS-049) et MCP Registry (HOS-049)
- **FastAPI Router** (`routes.py`) — 5 endpoints : GET /klaatcode/status, GET /klaatcode/capabilities, POST /klaatcode/analyze, POST /klaatcode/execute, POST /klaatcode/diagnostics
- **App wiring** (`main.py`) — routes montées sous `/api/v1/klaatcode`
- **Frontend KlaatCodePanel** (`klaatcode-panel.tsx`) — panneau Cockpit :
  - 7 outils MCP interactifs avec sélection et exécution
  - Badge MCP Connected, code plan input, visualisation du pipeline d'intégration
  - Actions rapides : Analyze, Diagnostics, Validate
  - Résultats formatés avec statut, durée, données JSON
- **Client API frontend** (`services/client.ts`) — 5 méthodes : status, capabilities, analyze, execute, diagnostics
- **Types TypeScript** (`types/hermes.ts`) — 3 interfaces : KlaatCodeStatus, KlaatCodeCapability, KlaatCodeExecutionResult
- **Tests** — 51 tests (8 classes) : modèles (8), client (7), adapter (14), policy (3), sandbox (5), event bus (5), routes (6), thread safety (3)

### Architecture
```
Hermes Agent → ToolRouter → KlaatCodeMCPAdapter → KlaatCodeClient → KlaatCode CLI
                                ↓
                         Policy → Sandbox → Memory → EventBus
```

### Intégrations Hermes
- Tool Registry HOS-049 ✅
- MCP Registry HOS-049 ✅
- Policy Engine HOS-046 ✅
- Tool Sandbox HOS-045 ✅
- Event Bus HOS-034 ✅
- Workspace Manager HOS-045 ✅ (sandbox integration)
- Cockpit Next.js HOS-051 ✅

### Validation
- pytest : ✅ 50/51 passed (1.06s) — 1 test stats vide corrigé
- Routes FastAPI : ✅ 5 endpoints
- Frontend : ✅ Panneau KlaatCode

---

## [HOS-053A] — 2026-07-29 — Alexandrie Integration

### Analyse préalable
- **Alexandrie** (Smaug6739/Alexandrie) — wiki/knowledge base auto-hébergée
- Stack: Nuxt.js (Vue) frontend + Golang (Gin) backend + MySQL 8 + S3
- Document curation, full-text search, team workspaces, 5-level ACL, OIDC SSO
- **N'est PAS** une librairie Python RAG — Alexandrie gère la curation documentaire humaine

### Décision d'architecture
| Fonctionnalité | Géré par |
|---|---|
| Édition Markdown, hiérarchie docs | Alexandrie |
| Full-text search (MySQL FULLTEXT) | Alexandrie |
| Workspaces, permissions, OIDC | Alexandrie |
| Stockage média (S3) | Alexandrie |
| Recherche sémantique (embeddings) | Hermes |
| Knowledge Graph | Hermes |
| Mémoires (working/episodic/semantic/procedural) | Hermes |
| Apprentissage d'expérience | Hermes |

### Ajouté
- **AlexandrieClient** (`alexandrie_client.py`) — client HTTP optionnel (sans `requests` en CI) pour l'API REST d'Alexandrie : health_check, search (full-text), CRUD nodes, checksum SHA256
- **HermesAlexandrieAdapter** — bridge central : sync_document, sync_all_documents, unsync_document, full_text_search, semantic_search, hybrid_search, get_graph_edges, event publishing
- **DocumentMemoryEntry** — entrée mémoire Hermes avec external_id, embedding, content_hash pour détection de changements
- **KnowledgeGraphEdge** — arêtes du graphe de connaissances (source→target, relation, poids)
- **HybridSearchResult** — résultat combiné Alexandrie full-text + Hermes semantic
- **EventBus** — 5 types d'événements : alexandrie.document.synced, .unsynced, .created, .updated, .deleted, alexandrie.sync.completed
- **REST API** — 11 endpoints : health, documents CRUD, search (fulltext/semantic/hybrid), sync, graph, statistics, events
- **Tests** — 40 tests (4 classes) : modèles (8), client (8), adapter (14), thread safety (3), full pipeline (3), graph (4)

### Exemple : recherche hybride
```
Alexandrie: "API Design" doc → full-text search → score 1.0
Hermes: "REST endpoints" doc → semantic search → score 0.8
HybridSearchResult: merged, deduplicated, ranked
```

### Validation
- pytest : ✅ 40/40 passed (0.17s)

---

## [HOS-053B] — 2026-07-29 — Alexandrie Integration Finalization

### Ajouté
- **Adapter complet** (`hermes_alexandrie_adapter.py`) — pipeline de sync production :
  - Synchronisation incrémentale (since timestamp, checksum-based change detection)
  - Détection de conflits + résolution (source_wins/local_wins/last_write_wins/manual)
  - Circuit breaker (5 échecs → circuit ouvert 30s, reset auto)
  - Cache documentaire (`DocumentCache` — TTL+LRU, eviction auto)
  - Liens mission-document (intégration Mission Planner)
- **Client production** (`alexandrie_client.py`) :
  - Authentification configurable (Bearer token / API key)
  - Retry avec exponential backoff (urllib3.Retry)
  - Health monitoring avec cache configurable
  - Timeout connexion + lecture
- **DocumentCache** (`document_cache.py`) — cache thread-safe TTL+LRU:
  - Prune automatique des entrées expirées
  - Stats : hits, misses, hit_rate, evictions
- **Event Bus** — 5 types d'événements :
  - alexandrie.document.created, .updated, .deleted
  - alexandrie.sync.started, .completed, .failed
- **REST API** — 16 endpoints :
  - Health, Status, Documents CRUD
  - Search (fulltext/semantic/hybrid)
  - Sync (start, status, history, mark-outdated)
  - Missions (link document, get mission documents, find relevant)
  - Graph, Cache, Events
- **Frontend Cockpit** — panneau Alexandrie dans Memory Center :
  - Status de connexion (Badge CONNECTED/OFFLINE)
  - Stats : synced, indexed, graph edges, cache entries, circuit breaker
  - Recherche hybride Alexandrie+Hermes
  - Historique de synchronisation
  - Relations documentaires (graph edges)
  - Liste des documents synchronisés
  - Bouton "Sync Now" avec retour visuel
- **Types TypeScript** — 8 interfaces :
  - AlexandrieStatus, AlexandrieDocument, AlexandrieSearchResults
  - AlexandrieMergeResult, AlexandrieSyncHistory, AlexandrieSyncResult
  - AlexandrieGraphEdges, AlexandrieMissionDocs
- **Client API frontend** — 16 méthodes :
  - health, status, documents CRUD, search, sync, graph, cache, events, missions
- **Hooks React Query** — 7 hooks :
  - useAlexandrieStatus, useAlexandrieHealth, useAlexandrieSearch
  - useAlexandrieSync, useAlexandrieSyncHistory, useAlexandrieDocuments
  - useAlexandrieGraph
- **Tests** — 40 tests (4 classes) : modèles (8), client (8), adapter (14), thread safety (3), full pipeline (3), graph (4)

### Modifié
- **Adapter** — ajout de `get_statistics()` et `get_synced_documents()` pour compatibilité avec les cas d'usage frontend
- **Tests** — mise à jour des assertions (event types, content hash, statistics keys)

### Validation
- pytest : ✅ 40/40 passed (0.18s)

---

## [HOS-052C] — 2026-07-29 — KTransformers Final Integration

### Ajouté
- **HermesKTAdapter** (`hermes_adapter.py`) — pont central avec import optionnel kt-kernel : singleton thread-safe, load/unload/infer/optimize/checksum, fallback simulé pour CI
- **12 backends réels** — AMX_INT4/INT8, AVX512_FP8_BF16/VBMI/VNNI/BASE, AVX2_LLAMAFILE, BLIS_AMD, CUDA, ROCm, CPU, HYBRID — mapping direct avec `kt_kernel.__cpu_variant__`
- **16 formats de quantization** — Q2_K → Q8_0, FP16/BF16/FP8, INT4/INT8, GPTQ, RAWINT4
- **KTModelConfig** — mapping direct avec KTransformersConfig YAML : chunked prefill, MoE offloading, hot experts, flash attention, continuous batching
- **KTOchestratorIntegration** — présente KT comme runtime candidat au Runtime Orchestrator (HOS-038) : scoring pondéré, task affinity, constraint-aware
- **KTDiscoveryIntegration** — 10 modèles KT-compatibles connus : DeepSeek-V3/R1/V4-Flash, Qwen3-MoE/Coder/Next, GLM-5, Mixtral 8×7B/8×22B, Kimi-K2
- **KTBenchmarkIntegration** — 5 profils avec prompts réels : coding, reasoning, general_chat, tool_use, long_context
- **KTResourceIntegration** — reçoit les métriques live du Resource Manager (HOS-035) : can_load, VRAM/RAM checks
- **KTEventBusBridge** — 6 types d'événements : discovered, loaded, unloaded, inference_completed, benchmark_completed, fallback_triggered
- **KTRuntime** — orchestrateur simplifié : register, discover, load (resource-checked), infer, optimize, benchmark — tout délégué à KT
- **13 endpoints REST** — models (list/get), discover, load/unload, infer, benchmark, optimize, orchestrator/candidates, status, statistics, resources, events
- **Tests** — 73 tests (10 classes) : models (10), adapter (9), discovery (8), orchestrator (7), resources (5), event bus (6), runtime (14), full integration (3), thread safety (3), backend detection (3), known models (5)

### Ce que KT gère nativement (jamais dupliqué)
- Chunked prefill • Heterogeneous offloading • MoE expert placement • Async forward passes • Continuous batching • Online quantization • 3-layer prefix cache • NUMA-aware thread pool

### Ce qu'Hermes gère (orchestration)
- Planification de mission • Sélection d'agent • Distribution de skills • Gouvernance • Mémoire • Cockpit

### Exemple : pipeline complet
```
KTDiscoveryIntegration.discover() → 10 modèles
  → KTRuntime.register_model(qwen3-coder-30b)
    → KTResourceIntegration.can_load() → OK (VRAM 24G free)
      → HermesKTAdapter.load_model(info, cfg) → kt_kernel.load_model()
        → Event: kt.model.loaded
        → KTOrchestratorIntegration.as_candidate() → suitability 0.65
          → KTOrchestratorIntegration.execute() → 384 tokens, 45 t/s
            → Event: kt.inference.completed
```

### Validation
- pytest : ✅ 73/73 passed (0.21s)

---

## [HOS-052B] — 2026-07-29 — KTransformers Hermes Integration Layer

### Ajouté
- **KTKernelWrapper** (`hermes_adapter.py`) — pont central Hermes ↔ kt-kernel : import optionnel avec fallback simulé, singleton thread-safe, load/unload/infer
- **KTOchestratorIntegration** — présente KT comme runtime candidat au Runtime Orchestrator (HOS-038) : as_candidate, can_handle_task, suitability_score, execute
- **KTDiscoveryIntegration** — alimente le Discovery Engine (HOS-040) avec 10 modèles KT-compatibles connus (DeepSeek, Qwen, GLM, Kimi, Mixtral, Phi, LLaMA)
- **KTBenchmarkIntegration** — benchmarke les modèles via KT avec 5 profils (coding, reasoning, chat, tool_use, long_context), best_for_task
- **KTResourceIntegration** — reçoit les données live du Resource Manager (HOS-035) : VRAM/RAM total/used/free, optimise les décisions
- **KTEventBusBridge** — publie les événements KT sur le vrai Event Bus (HOS-034) : 6 types d'événements (discovered, loaded, unloaded, inference_completed, benchmark_completed, fallback_triggered)
- **KTRuntime v2** — orchestrateur utilisant hermes_adapter + toutes les intégrations : discover_and_register, optimize avec ressources live, events natifs
- **KTRoutes v2** — 10 endpoints REST : discover, infer, benchmark, orchestrator en plus de models/load/unload/status/statistics/optimize
- **Frontend KTPanel** (`kt-panel.tsx`) — panneau Cockpit : statut kernel, CPU variant, liste modèles (load/unload/benchmark), benchmarks
- **Tests** — 32 tests (7 classes) : adapter (7), orchestrator (4), discovery (3), benchmark (4), resources (2), event bus (5), full integration (4), thread safety (3)

### Architecture
```
Hermes OS (orchestration)          KTransformers (exécution)
┌────────────────────┐             ┌────────────────────┐
│ Runtime Orchestrator│──candidate──→ KTOchestratorInt.  │
│ Discovery Engine    │──discover──→ KTDiscoveryInt.     │
│ Benchmark Engine    │──benchmark─→ KTBenchmarkInt.     │
│ Resource Manager    │──resources─→ KTResourceInt.      │
│ Event Bus           │←──events─── KTEventBusBridge     │
│ Cockpit Next.js     │←──status─── KTPanel              │
└────────────────────┘             └────────────────────┘
```

### Validation
- pytest : ✅ 32/32 passed (0.04s)

---

## [HOS-052] — 2026-07-29 — KTransformers Runtime Integration

### Ajouté
- **KTModelManager** — registre thread-safe : register, get, search, download (simulé), vérification intégrité SHA256, stats par statut/backend/quantization
- **KTLoader** — chargement intelligent : lazy loading, preload queue, ensure_loaded, auto-unload idle, tracking loaded models
- **KTCache** — cache LRU/TTL : max entries (16 default), TTL expiry (600s default), éviction priority-aware, hit/miss counters
- **KTScheduler** — planificateur prioritaire 4 niveaux (CRITICAL/HIGH/NORMAL/LOW) : enqueue, dequeue, cancel, batch processing, stats
- **KTOptimizer** — sélection automatique backend/quantization : scores 5 facteurs (VRAM, RAM, task type, backend, quality), fallback reasoning
- **KTRuntime** — moteur principal : intégration ModelManager + Loader + Cache + Scheduler + Optimizer + EventBus simulé
- **8 modèles** — KTModelInfo, KTLoadConfig, KTInferenceRequest, KTInferenceResult, KTOptimizationResult, KTCacheStats, KTSchedulerStats + 4 enums (KTBackend, KTQuantization, KTModelStatus, KTFallbackReason)
- **REST API** — GET /runtime/ktransformers/models, GET /{id}, POST /load, POST /unload, GET /status, GET /statistics, POST /optimize
- **EventBus** — ktransformers.loaded, ktransformers.unloaded, ktransformers.optimized, ktransformers.fallback, ktransformers.failed
- **Intégrations préparées** — Resource Manager (optimizer.set_hardware), Orchestrator (optimize_for_task), Discovery (register_model), Event Bus (callback), Benchmark (inference stats), Simulation (batch processing), Execution (infer/infer_async)
- **Tests** — 53 tests (8 classes) : model manager (12), cache (9), loader (7), scheduler (6), optimizer (5), runtime (8), thread safety (3), events (3)
- **Docs** — `KTRANSFORMERS_INTEGRATION_ARCHITECTURE.md`

### Exemple : chargement et exécution
```
KTModelManager.register(qwen3-7b-q4 / Q4_K_M / ROCm / 4.0GB)
  → KTOptimizer.optimize("7B", "coding") → Q5_K_M / ROCm / score 100
    → KTLoader.load(rocm, n_gpu_layers=-1)
      → Event: ktransformers.loaded
      → KTScheduler.enqueue("Refactor user auth module", priority=HIGH)
        → KTScheduler.process_batch()
          → KTInferenceResult: 128 tokens, 68 t/s, VRAM 3.8GB
            → Event: ktransformers.optimized
```

### Validation
- pytest : ✅ 53/53 passed (0.07s)

---

## [HOS-051] — 2026-07-29 — Hermes Mission Center & AI Operations Cockpit

### Ajouté
- **Cockpit Shell** — layout complet avec Sidebar (9 vues), Topbar (santé/uptime/WS), StatusBar (stats système)
- **Dashboard** — vue d'ensemble : santé système, statistiques, runtimes, live events, missions/agents récentes
- **Mission Center** — liste missions, création, détail, progression, actions (start/pause/resume/cancel)
- **Agent Center** — liste agents, statut/capabilités, détail métriques, messages collaboration temps réel
- **Runtime Center** — runtimes, santé, métriques, barres fiabilité/performance, monitoring VRAM/RAM/CPU/GPU
- **Memory Center** — recherche hybride (graph+embeddings+keyword), Knowledge Graph, expériences
- **Skills Center** — sélection automatique par tâche, registre skills, cache status
- **Tools Center** — outils natifs + MCP servers, santé, permissions
- **Governance Center** — approvals en attente, règles policy, audit log avec actions approve/reject
- **Event Center** — flux temps réel WebSocket, filtres sévérité/source, historique 200 événements
- **Cockpit Store** — Zustand : navigation, événements live, filtres, connexion WS, sélection mission/agent
- **API Client** — `services/client.ts` : 70+ endpoints typés couvrant tous les modules backend
- **React Query Hooks** — 30+ hooks : missions, agents, runtimes, memory, skills, tools, governance, execution, events
- **WebSocket Hook** — `useWebSocket()` : auto-reconnect, backoff, filtrage sources, gestion d'erreurs
- **TypeScript Types** — `types/hermes.ts` : 60+ types couvrant tous les modèles backend
- **UI Components** — Card, Badge (6 variants), StatCard, ProgressBar, animations Framer Motion
- **Design System** — thème Hermes (dark amber/blue/purple), Tailwind, animations, scrollbar custom, React Flow overrides
- **Providers** — React Query avec refetch/staleTime optimisés
- **Tests** — 55 tests (store, WebSocket helpers, types, API client endpoints, hooks, components, feature centers, navigation)
- **Docs** — `HERMES_COCKPIT_ARCHITECTURE.md`

### Architecture Frontend
```
frontend/src/
├── app/                    # Next.js App Router
│   ├── layout.tsx         # Root layout + Providers
│   ├── globals.css        # Theme + animations
│   ├── page.tsx           # Redirect → /dashboard
│   └── dashboard/         # Cockpit Shell
├── components/
│   ├── cockpit-shell.tsx  # Shell avec routing des vues
│   ├── providers.tsx      # QueryClientProvider
│   ├── sidebar.tsx        # Navigation 9 vues
│   ├── topbar.tsx         # Santé / version / WS
│   ├── statusbar.tsx      # Stats temps réel
│   └── ui/card.tsx        # Card, Badge, StatCard, ProgressBar
├── features/              # 9 centres
│   ├── dashboard/         # Vue overview
│   ├── missions/          # Mission Center
│   ├── agents/            # Agent Center
│   ├── runtime/           # Runtime Center
│   ├── memory/            # Memory Center
│   ├── skills/            # Skills Center
│   ├── tools/             # Tools Center
│   ├── governance/        # Governance Center
│   └── events/            # Event Center
├── hooks/
│   ├── use-api.ts         # 30+ React Query hooks
│   ├── use-store.ts       # Zustand cockpit store
│   └── use-websocket.ts   # WebSocket hook
├── services/
│   └── client.ts          # 70+ API endpoints
├── types/
│   └── hermes.ts          # 60+ types TypeScript
└── __tests__/
    └── cockpit.test.ts    # 55 tests
```

### Pages

| Route | Vue | Panneaux |
|---|---|---|
| `/` | Redirect → `/dashboard` | — |
| `/dashboard` | Dashboard | Health, Stats, Runtimes, Live Events, Missions, Agents |
| `/dashboard#missions` | Mission Center | Liste, Création, Détail, Progression |
| `/dashboard#agents` | Agent Center | Liste, Détail, Métriques, Collaboration |
| `/dashboard#runtime` | Runtime Center | Runtimes, VRAM/RAM/CPU/GPU |
| `/dashboard#memory` | Memory Center | Recherche, Knowledge Graph, Expériences |
| `/dashboard#skills` | Skills Center | Sélection auto, Registre, Cache |
| `/dashboard#tools` | Tools Center | Outils natifs, MCP, Santé |
| `/dashboard#governance` | Governance Center | Approvals, Règles, Audit |
| `/dashboard#events` | Event Center | Flux temps réel avec filtres |

### Dépendances
- `next` 15.1, `react` 19, `typescript` 5.7
- `@tanstack/react-query` 5 — data fetching avec cache/retry
- `zustand` 5 — state management léger
- `framer-motion` 11 — animations
- `lucide-react` — icônes
- `tailwindcss` 3.4, `clsx`, `tailwind-merge` — styling
- `vitest` 2.1, `@testing-library/react` 16, `jsdom` — tests

### Validation
- Tests : ✅ 55/55 passed (vitest)
- TypeScript strict : ✅

---

## [HOS-050] — 2026-07-29 — Autonomous Mission Execution Engine

### Ajouté
- **ExecutionStateMachine** — machine à états 10 états (CREATED→PLANNING→READY→RUNNING↔PAUSED/WAITING_APPROVAL→VALIDATING→COMPLETED/FAILED/CANCELLED) avec checkpoints, transitions validées, thread-safe
- **TaskScheduler** — planification DAG avec vagues parallèles, priorités (CRITICAL/HIGH/NORMAL/LOW), blocage sur dépendances, 4 stratégies (PARALLEL/SEQUENTIAL/PRIORITY/RESOURCE_AWARE)
- **AgentCoordinator** — sélection optimale agent/skills/runtime/tools par tâche, scoring capacités, suivi charge, release
- **ValidationEngine** — validation post-exécution avec critères configurables, 4 issues (PASS/FAIL/RETRY/NEEDS_REVIEW)
- **FeedbackLoop** — analyse post-mission : efficacité, learnings, recommendations, inputs Memory/Intelligence
- **OptimizationEngine** — détection tâches lentes, runtimes sous-performants, generation de recommendations
- **MissionExecutor** — orchestrateur central : pipeline User Goal→Planner→Graph→Scheduler→Agents→Skills→Runtime→Tools→Validation→Memory
- **ExecutionController** — gestion lifecycle complet : start/pause/resume/cancel/finalize, timeline, multi-executions
- **REST API** — POST /execution/start, GET /execution/{id}, GET /execution, POST /execution/{id}/pause, POST /execution/{id}/resume, POST /execution/{id}/cancel, GET /execution/{id}/timeline, GET /execution/statistics
- **EventBus** — execution.started, execution.planning, execution.task_started, execution.task_completed, execution.waiting_approval, execution.failed, execution.completed, execution.optimized
- **Tests** — 72 tests : state machine (12), scheduler (8), coordinator (7), validation (6), feedback (5), optimizer (4), executor (9), controller (8), routes (10), thread safety (3)

### Exemple : "Créer une application web"
```
POST /execution/start { goal: "Create web app", tasks: ["Plan", "Code", "Test"] }
→ ExecutionStateMachine: CREATED → PLANNING → READY
→ TaskScheduler: builds plan with 3 waves
→ AgentCoordinator: assigns coder + python-coding skill + ollama runtime
→ MissionExecutor.execute_task: RUNNING → VALIDATING → COMPLETED
→ ValidationEngine: PASS
→ FeedbackLoop: efficiency 100%, 3 learnings extracted
→ OptimizationEngine: no slow tasks detected
→ Memory: mission experience recorded for future reuse
```

### Validation
- pytest : ✅ 72/72 passed (0.07s)

---

## [HOS-049] — 2026-07-29 — MCP & External Tools Platform

### Ajouté
- **ToolRegistry** — registre thread-safe indexé par type/catégorie/statut/tag (8 types, 7 catégories, 4 états)
- **ToolPolicy** — gouvernance avant exécution : ALLOW/DENY/REVIEW_REQUIRED, règles configurables par outil
- **ToolSandbox** — isolation : paths autorisés/interdits, réseau contrôlé, env vars, workspace per-agent
- **ToolExecutor** — pipeline : Policy→Sandbox→Execute→Metrics, timeout, cancellation, historique
- **ToolRouter** — sélection automatique : catégorie→outil, type préféré, score de confiance
- **ToolHealth** — health checks, latence, erreurs, disponibilité par outil
- **ToolMemory** — intégration Knowledge Graph: Agent→Tool→Mission→Résultat→Performance
- **MCP Platform** — `mcp_client.py`, `mcp_registry.py`, `mcp_models.py` : connect/disconnect, list/call tools, multi-serveurs
- **7 Connectors** — GitHub, GitLab, Docker, Database (PG+SQLite), Filesystem, REST API, Browser
- **REST API** — GET /tools, GET /tools/{id}, POST /tools/register, POST /tools/execute, POST /tools/select, GET /tools/health, GET /tools/metrics, GET /mcp/servers, POST /mcp/connect, POST /mcp/disconnect
- **Tests** — 58 tests : registry (6), policy (5), sandbox (5), executor (5), router (3), health (4), memory (4), MCP (6), connectors (8), routes (10), thread safety (2)
- **Docs** — `TOOL_PLATFORM_ARCHITECTURE.md`, `MCP_ARCHITECTURE.md`

### Exemple : corriger un bug GitHub
```
Mission Planner → Agent Coder → SkillSelector → ToolRouter
    → "github" (score 0.8)
    → ToolPolicy.evaluate() → ALLOW
    → ToolExecutor.execute(GitHubConnector.create_branch)
    → ToolSandbox.validate_path("/home/project")
    → GitHubConnector.commit → ToolMemory.record
    → Audit log → Knowledge Graph updated
```

### Validation
- pytest : ✅ 58/58 passed (0.04s)

---

## [HOS-048] — 2026-07-29 — Dynamic Skill Distribution Engine

### Ajouté
- **SkillRegistry** — registre thread-safe indexé par catégorie/domaine/tag/statut (9 catégories, 8 domaines, 4 états)
- **SkillSelector** — sélection automatique 6 facteurs pondérés (catégorie 30%, technologies 20%, tags 10%, description 15%, succès 15%, qualité 10%)
- **SkillDependencyResolver** — résolution transitive (BFS), sort topologique (Kahn), détection de cycles (DFS), conflits de versions
- **SkillLoader** — lazy loading avec hooks d'initialisation, hot reload sans redémarrage, tracking par agent/mission
- **SkillCache** — cache LRU/TTL/PRIORITY avec éviction automatique, invalidation par expiration, hit rate
- **SkillProfiler** — profiling runtime (moyenne exponentielle): temps de chargement, mémoire, tokens, taux d'échec
- **SkillDistributor** — distribution multi-agent pour une mission, load avec cache-awareness, unload par agent ou mission
- **REST API** — GET /skills (filtres), GET /skills/{id}, POST /skills/select, POST /skills/load, POST /skills/unload, GET /skills/cache, GET /skills/statistics
- **Tests** — 59 tests : registry (9), selector (7), resolver (5), loader (6), cache (9), profiler (7), distributor (5), routes (9), thread safety (3)

### Exemple : trois agents, skills différentes
```
Mission: "Build a full-stack web app with auth"
→ Agent Coder (backend): python-coding (0.85) + db-design (0.72) — 20MB, 1500 tokens
→ Agent Designer (frontend): react-ui (0.88) — 10MB, 500 tokens
→ Agent Auditor (security): security-audit (0.95) — 15MB, 800 tokens
Total: 3 agents, 4 skills, 45MB, 2800 tokens
```

### Validation
- pytest : ✅ 59/59 passed (0.09s)

---

## [HOS-047] — 2026-07-29 — Unified Memory & Knowledge Graph Engine

### Ajouté
- **WorkingMemoryStore** — mémoire transitoire de mission (conversations, états agents, décisions), auto-clear en fin de mission
- **EpisodicMemoryStore** — expériences de mission (succès/échecs, incidents, décisions), recherche par tags + mot-clé
- **SemanticMemoryStore** — concepts, technologies, frameworks, patterns, outils; recherche fuzzy par nom/description/tags
- **ProceduralMemoryStore** — workflows, best practices, templates, stratégies; versionné, tracking usage/success rate
- **DocumentMemoryStore** — indexation de docs (markdown, code, specs, architecture), chunking préparé pour RAG
- **KnowledgeGraph** — graphe navigable (BFS) reliant missions→tasks→agents→runtimes→models→skills→workspaces→docs→benchmarks→decisions
- **EmbeddingIndex** — index vectoriel abstrait (128-dim hash embeddings), pluggable pour Nomic/BGE/E5 futurs
- **RetrievalEngine** — recherche hybride (embeddings + keyword + graph) sur tous les types de mémoire
- **ExperienceManager** — extrait les leçons, erreurs fréquentes, best practices; recommande pour nouvelles missions
- **MemoryManager** — façade centrale unifiant tous les types de mémoire, toutes les couches passent par lui
- **REST API** — POST /memory/search, GET /memory/search?q=, GET /memory/graph, GET /memory/experiences, POST /memory/index, GET /memory/statistics
- **Tests** — 43 tests : working (5), episodic (5), semantic (5), procedural (5), documents (4), graph (6), embeddings (4), experience (4), manager (5), thread (3)

### Exemple : nouvelle mission réutilisant l'expérience
```
Missions passées: Auth v1 ✅ (qwen3:14b), Auth v2 ✅ (qwen3:14b), DB Migration ❌
→ MemoryManager.recommend_for_mission("development", ["auth"])
→ recommended_models: ["qwen3:14b"] (2 past successes)
→ similar_missions: 2, similar_success_rate: 100%
→ past_experiences: [Auth v1, Auth v2]
```

### Validation
- pytest : ✅ 43/43 passed (0.05s)

---

## [HOS-046] — 2026-07-29 — Human Approval & Policy Engine

### Ajouté
- **PolicyEngine** — moteur central de gouvernance : toutes les opérations sensibles passent par lui (ALLOW / DENY / REVIEW_REQUIRED)
- **RuleEvaluator** — 10 règles intégrées : git_merge, workspace_delete, model_download, runtime_cloud, internet_access, system_modification (DENY), external_tool, git_rollback, high_risk (≥7), critical_risk (≥9)
- **ApprovalEngine** — workflow humain : approve, reject, comment, delegate, cancel, multi-approval (N validations requises)
- **ApprovalQueue** — file d'attente thread-safe triée par priorité (CRITICAL > HIGH > NORMAL > LOW)
- **AuditLog** — journal immuable : qui, quoi, quand, pourquoi, résultat, durée (10000 entrées max, auto-prune)
- **REST API** — GET /policy/rules, POST /policy/evaluate, GET /approval, POST /approval/{id}/approve, POST /approval/{id}/reject, GET /audit
- **EventBus** — policy.allowed, policy.denied, approval.requested, approval.granted, approval.rejected, approval.expired, audit.created
- **Tests** — 45 tests : evaluator (11), queue (7), engine (8), audit (6), policy engine (10), thread safety (3)

### Exemple : mission avec validation humaine avant merge Git
```
CoderAgent → PolicyEngine.evaluate(operation="git_merge")
  → Rule: "git_merge_requires_review" → REVIEW_REQUIRED
  → ApprovalQueue: [PENDING, priority=HIGH]
  → Event: approval.requested
Admin → POST /approval/{id}/approve → APPROVED
  → AuditLog: [agent=admin, action=approved, operation=git_merge]
  → Event: approval.granted
CoderAgent → merge allowed ✅
```

### Validation
- pytest : ✅ 45/45 passed (0.06s)

---

## [HOS-045] — 2026-07-29 — Workspace & Sandbox Manager

### Ajouté
- **WorkspaceManager** — cycle de vie complet : create/open/lock/release/archive/destroy, quotas disque/durée, par agent/mission
- **SandboxManager** — environnements isolés par agent : work dir, env vars, read-only, network control, allowed tools, temp storage
- **ArtifactManager** — versioning d'artefacts (files, patches, reports, logs, docs, tests) avec checksums SHA256
- **GitWorkspace** — abstraction Git : branches, commits, merge, rollback, stash (jamais main direct)
- **WorkspacePolicyEngine** — moteur de règles : disk quota (90% warn, 100% deny), max duration, read-only, network, outils autorisés
- **REST API** — POST /workspace, GET /workspace, GET /workspace/{id}, DELETE /workspace/{id}, POST /lock, POST /release, GET /artifacts, GET /status
- **EventBus** — workspace.{created,opened,locked,released,archived}, sandbox.{created,destroyed}, artifact.{created,updated}, git.{branch_created,commit_created}
- **Tests** — 48 tests : git (9), sandbox (8), artifact (8), policy (6), workspace manager (13), thread safety (3)

### Exemple : deux agents sur deux branches
```
CoderAgent → workspace "feature/backend" → commit "Add API" → artifact api.py
ReviewerAgent → workspace "feature/review" → commit "Reviewed API"
→ merge feature/backend → main
→ merge feature/review → main
```

### Validation
- pytest : ✅ 48/48 passed (0.06s)

---

## [HOS-044] — 2026-07-29 — Multi-Agent Collaboration Engine

### Ajouté
- **MessageBus** — messagerie inter-agents : direct, broadcast, groupe, help requests, conversations threadées, accusés de réception
- **ContextSharing** — partage de contexte avec permissions (visible_to, editable_by), mise à jour collaborative
- **DelegationManager** — délégation de tâches entre agents, demande d'expertise, workflow accept→start→complete
- **ConsensusEngine** — votes multi-agents : unanimous, majority, super-majority (2/3), single
- **ConflictResolver** — détection 5 types de conflits (disagreement, resource, concurrent, decision, priority) + auto-résolution
- **CollaborationEngine** — orchestrateur central : messages, contextes, délégations, reviews, consensus, conflits + historique mission
- **REST API** — 12 endpoints : GET/POST /messages, POST /broadcast, GET /unread, GET /conversations, POST /delegate, GET /delegations, POST|accept|complete delegations, POST /review, POST /consensus, POST /vote, GET /history
- **EventBus** — collaboration.started, message.sent, message.received, task.delegated, review.requested, review.completed, consensus.started, consensus.reached, conflict.detected, conflict.resolved
- **Tests** — 64 tests (14 msg + 9 ctx + 10 deleg + 8 consensus + 10 conflict + 10 engine + 3 threads)

### Exemple : mission collaborative
```
CoderAgent → "Implement login" (COMPLETED)
     → MessageBus.send(ReviewerAgent, "Please review PR")
     → ContextSharing.share("PR diff", visible_to=[ReviewerAgent])
ReviewerAgent → "Review PR" (APPROVED)
     → ConsensusEngine.propose("Architecture", ["monolith", "microservices"], mode=MAJORITY)
     → Vote: Coder="microservices", Reviewer="microservices", Designer="monolith"
     → Outcome: "microservices" (2/3 majority)
```

### Validation
- pytest : ✅ 64/64 passed
- Fix: RLock pour thread-safety réentrante (consensus, conflicts, delegations)

---

## [HOS-043] — 2026-07-29 — Agent Supervisor

### Ajouté
- **Agent models** — Agent, AgentCapability (13 types), AgentProfile, AgentStatus (10 états), ExecutionContext, ExecutionResult, AgentMetrics, AgentTask
- **AgentRegistry** — registre thread-safe avec index par capability, status et métriques
- **CapabilityMatcher** — scoring multi-critères (capability 30%, load 25%, availability 20%, history 15%, runtime 10%) + mapping task→capability
- **AgentLifecycle** — machine à états 10 transitions validées, historique, callback événements
- **ExecutionContextManager** — gestion thread-safe des contextes d'exécution par agent/mission
- **TaskDispatcher** — pipeline complet : sélection agent → contexte → exécution → résultat → métriques
- **AgentSupervisor** — superviseur central : création agents, dispatch tâches, exécution mission DAG, réassignation, métriques
- **REST API** — GET /agents, POST /agents, GET /agents/{id}, GET /agents/status, GET /agents/metrics, POST /agents/{id}/start, POST /agents/{id}/stop, POST /agents/{id}/pause
- **Intégrations** — Mission Graph (HOS-041): dispatch MissionNode → agent, Runtime Orchestrator (HOS-038): callback de sélection runtime
- **EventBus** — agent.created, agent.started, agent.ready, agent.busy, agent.completed, agent.failed, agent.stopped, task.assigned, task.reassigned
- **Tests** — 49 tests : registry (10), lifecycle (8), matcher (7), context (5), dispatcher (4), supervisor (11), full execution (2), thread safety (2)

### Exemple : mission multi-agent
```
DesignerAgent → "Design architecture"
       ↓
CoderAgent → "Implement backend"
       ↓
CoderAgent → "Write tests"  ∥  ReviewerAgent → "Code review"
```

### Validation
- pytest : ✅ 49/49 passed (0.06s)

---

## [HOS-042] — 2026-07-29 — Intelligent Mission Planner

### Ajouté
- **TaskDecomposer** — décomposition automatique de requêtes utilisateur en tâches structurées (7 patterns connus : auth, database, api, frontend, deployment, + pattern générique)
- **DependencyBuilder** — construction automatique du graphe de dépendances, détection de groupes parallèles, détection d'incohérences
- **ComplexityEstimator** — estimation de complexité (0-10), durée, VRAM/RAM, tokens, risque (LOW→CRITICAL), priorité suggérée
- **RuntimeRecommender** — recommandation de modèle/base runtime par catégorie de tâche et niveau de complexité (coding/reasoning/chat)
- **ValidationEngine** — 7 vérifications : complétude, dépendances, ressources, cycles, orphelins, estimates, recommendations
- **TemplateLibrary** — 6 templates de mission réutilisables (web_app, api_service, cli_tool, data_pipeline, microservice, refactoring)
- **MissionPlanner** — orchestrateur principal : pipeline complet request → DAG valide
- **REST API** — POST /planner/plan, POST /planner/plan/template/{id}, GET /planner/results, GET /planner/results/{id}, POST /planner/results/{id}/build, GET /planner/templates
- **Intégration** — GraphExecutor (HOS-041), catégories Runtime Discovered (HOS-040), EventBus callback
- **Tests** — 47 tests : decomposer (7), dependency builder (7), complexity estimator (7), runtime recommender (5), validation (4), templates (5), full pipeline (11), thread safety (1)

### Pipeline de planification
```
User Request → Decomposer → DependencyBuilder → ComplexityEstimator
                                                       ↓
              Mission DAG ← MissionPlanner ← RuntimeRecommender
                                  ↓
                          ValidationEngine
```

### Templates disponibles
| Template | Tâches |
|---|---|
| web_app | 10 (analysis → deployment) |
| api_service | 8 (analysis → deploy) |
| cli_tool | 7 (design → distribute) |
| data_pipeline | 8 (analysis → deploy) |
| microservice | 7 (analysis → runbook) |
| refactoring | 6 (analysis → review) |

### Validation
- pytest : ✅ 47/47 passed (0.06s)
- compileall : ✅

---

## [HOS-041] — 2026-07-29 — Mission Graph Engine

### Ajouté
- **MissionGraph** — représentation DAG avec validation, détection de cycles (Kahn), tri topologique
- **Mission models** — Mission, MissionNode, MissionEdge, MissionContext, MissionStatus, MissionPriority, MissionType, NodeStatus
- **DependencyResolver** — résolution de dépendances, nœuds ready/blocked, groupes parallèles, cascade d'échecs
- **GraphExecutor** — moteur d'exécution pas-à-pas, intégration RuntimeOrchestrator, progression
- **GraphSerializer** — sérialisation JSON/YAML avec versioning (schema v1.0.0)
- **REST API** — POST /missions, GET /missions, GET /missions/{id}, GET /{id}/graph, POST /{id}/start, POST /{id}/cancel, GET /{id}/progress
- **Intégration EventBus** — mission.created, mission.started, mission.node_ready, mission.node_completed, mission.node_failed, mission.completed, mission.cancelled
- **Tests** — 27 tests : modèles, validation DAG, cycles, tri topologique, résolution, exécution, sérialisation, événements, thread safety

### Exemple : mission de développement logiciel (7 nœuds)
```
init → db → api → auth → deploy
  │              │        ↗
  └→ frontend ──→ tests ─┘
```

### Validation
- pytest : ✅ 27/27 passed (0.02s)

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
