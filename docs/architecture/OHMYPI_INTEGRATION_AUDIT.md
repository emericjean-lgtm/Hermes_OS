# HOS-055A — Audit & Plan d'Intégration Oh My Pi dans Hermes OS

> **Date :** 2026-07-29  
> **Type :** Audit d'architecture — aucune modification de code  
> **Statut :** ✅ Terminé

---

## 1. Analyse Architecture Oh My Pi

### 1.1 Identité

| Attribut | Valeur |
|---|---|
| **Dépôt** | `can1357/oh-my-pi` |
| **Abréviation** | `omp` |
| **Origine** | Fork avancé de `Pi` (Mario Zechner / `earendil-works/pi`) |
| **Auteur principal** | `@can1357` |
| **Site** | `omp.sh` |
| **Licence** | Open source |
| **Lignes de code** | ~55 000 Rust + TypeScript |

### 1.2 Stack Technique

| Couche | Technologie | Rôle |
|---|---|---|
| **Core natif** | Rust (~55K lignes) | Performance critique : regex, glob, AST parsing, PTY, token counting, isolation |
| **Agent & TUI** | TypeScript / Bun | Session tree, tool dispatch, prompt routing, MCP, editor hooks |
| **N-API Bridge** | `@oh-my-pi/pi-natives` | Rust → Node.js via Node-API, zéro fork/exec sur les hot paths |
| **AST** | tree-sitter (`ast-grep`) | Parsing structurel multi-langages |
| **Shell** | `pi-shell` (Rust) | PTY allocation, isolation |
| **Syntaxe** | `syntect` (Rust) | Coloration syntaxique |
| **Tokens** | `tiktoken-rs` (Rust) | Comptage de tokens |
| **Installation** | curl, Homebrew, Bun, PowerShell | Multi-plateforme (macOS, Linux, Windows natif) |

### 1.3 Structure du Projet

```
oh-my-pi/
├── crates/                     # Rust core
│   ├── pi-natives/            # N-API addons
│   ├── pi-shell/              # PTY terminal
│   ├── pi-ast/                # AST via tree-sitter
│   └── pi-iso/                # Workspace isolation
├── packages/
│   ├── coding-agent/          # Agent TypeScript principal
│   │   ├── src/
│   │   │   ├── tools/         # 32+ outils intégrés
│   │   │   ├── exec/          # Exécution Python/JS
│   │   │   ├── task/swarm/    # Sous-agents parallèles
│   │   │   ├── memories/      # Mémoire persistante
│   │   │   ├── hindsight/     # Auto-apprentissage
│   │   │   └── internal-urls/ # URLs virtuelles (pr://, agent://, ...)
│   └── tui/                   # Interface terminal (TUI)
└── docs/
```

### 1.4 Modes d'Exécution

| Mode | Commande | Usage |
|---|---|---|
| TUI interactive | `omp` | Terminal UI complète |
| One-shot CLI | `omp -p "prompt"` | Tâche unique |
| RPC Server | `omp --mode rpc` | JSONL RPC pour intégrations |
| ACP (Editor) | Via Zed / ACP | Agent intégré dans l'éditeur |
| Node SDK | `import { agent } from '@oh-my-pi'` | Utilisation programmatique |

### 1.5 Fournisseurs LLM (40+)

OpenAI, Anthropic, Gemini, xAI, Ollama, LM Studio, Cursor OAuth, GitHub Copilot OAuth, DeepSeek, Groq, Together AI, Fireworks, Mistral, Cohere, Replicate, Cerebras, etc.

Avec fallback chains, round-robin credential rotation, et routing automatique.

---

## 2. Analyse Fonctionnelle Oh My Pi

### 2.1 Outils intégrés (32+)

| Catégorie | Outils | Spécificité |
|---|---|---|
| **Fichiers** | read, write, edit, glob, grep | Hash-anchored patches |
| **AST** | ast_edit, ast_grep | tree-sitter structurel |
| **LSP** | lsp_diagnostics, lsp_rename, lsp_goto_def | Language Server Protocol |
| **Debugger** | debug_attach (DAP) | lldb, dlv, debugpy |
| **Shell** | shell_exec, shell_spawn | PTY isolation |
| **Browser** | browser_navigate, browser_screenshot | Playwright |
| **Git** | git_diff, git_log, git_branch | Via CLI |
| **GitHub** | pr_create, pr_review, issue_search | API REST |
| **Web** | web_search, web_fetch | Web scraping |
| **Notebook** | notebook_create, notebook_execute | Python/JS cells |
| **Agent** | subagent_spawn, subagent_collect | Swarm parallèle |

### 2.2 Capacités Uniques

| Capacité | Description | Présent dans Hermes ? |
|---|---|---|
| **LSP Integration** | Renommage, diagnostics, autocomplétion via Language Server Protocol | ❌ Non |
| **DAP Debugging** | Debugger réel (lldb, dlv, debugpy) — step, inspect stack, variables | ❌ Non |
| **AST Editing** | tree-sitter structural edits (pas de regex sur texte brut) | ❌ Non |
| **Hashline Anchors** | Ancres content-hash pour diffs fiables sans whitespace matching | ❌ Non |
| **Python/JS Execution Engine** | Exécute du code réel avec callbacks vers les outils de l'agent | ❌ Non |
| **Virtual URL Scheme** | `pr://`, `issue://`, `agent://`, `skill://` — tout comme fichiers | ❌ Non |
| **40+ LLM Providers** | Routing multi-providers avec fallback chains | Partiel (HOS-038) |
| **Subagent Swarms** | Fan-out de sous-agents en worktrees isolés | Partiel (HOS-044) |
| **Auto-Learning (Hindsight)** | Compression de contexte automatique | Partiel (HOS-047) |
| **TUI Interactive** | Terminal UI riche | ❌ Non (Cockpit web) |
| **ACP/Editor Embedded** | Intégré dans Zed, VS Code via ACP | ❌ Non |
| **Rust Native Core** | 55K lignes Rust, N-API, zéro overhead fork/exec | ❌ Non |

---

## 3. Comparaison Hermes ↔ Oh My Pi

### 3.1 Matrice Fonctionnelle

| Fonctionnalité | Hermes OS | Oh My Pi | Recommandation |
|---|---|---|---|
| **Planification mission** | HOS-042 (DAG, templates) | ❌ Non | ✅ Garder Hermes |
| **Orchestration agents** | HOS-043 (Supervisor) | Partiel (subagent swarms) | ✅ Garder Hermes pour l'orchestration |
| **Collaboration agents** | HOS-044 (messages, délégation, consensus) | Partiel (swarm collect) | ✅ Garder Hermes |
| **Édition de code** | HOS-054 (KlaatCode MCP) | ✅ **Excellent** (LSP + AST + hashline) | 🔄 **Utiliser Oh My Pi** |
| **Analyse de code** | HOS-054 (KlaatCode analyze) | Partiel (LSP diagnostics) | 🔄 Fusionner |
| **Débogage réel** | ❌ Non | ✅ **Excellent** (DAP, lldb, dlv, debugpy) | 🔄 **Utiliser Oh My Pi** |
| **AST structurel** | ❌ Non | ✅ tree-sitter multi-langages | 🔄 **Utiliser Oh My Pi** |
| **Exécution code** | HOS-050 (Execution Engine) | ✅ Python/JS avec tool callbacks | 🔄 Complémentaire |
| **Workspace isolation** | HOS-045 (Workspace Manager) | ✅ `pi-iso` (Rust) | ⚠️ Double — adapter |
| **Git workflow** | HOS-045 (GitWorkspace) | ✅ Via CLI + PR tools | ⚠️ Double — adapter |
| **Memory** | HOS-047 (5 types + KG) | ✅ `memories/` + `hindsight/` | 🔄 **Fusionner les deux** |
| **Knowledge Graph** | HOS-047 (graphe navigable) | ❌ Non | ✅ Garder Hermes |
| **Politique/approbation** | HOS-046 (Policy Engine) | ❌ Non | ✅ Garder Hermes |
| **Skill distribution** | HOS-048 (Dynamic Skills) | ❌ Non | ✅ Garder Hermes |
| **MCP Platform** | HOS-049 (Tool Registry, MCP) | ✅ Support MCP | 🔄 Oh My Pi comme MCP Provider |
| **Runtime selection** | HOS-038 (Orchestrator) | ✅ 40+ LLM providers routing | 🔄 **Oh My Pi supérieur** — adapter |
| **Benchmark** | HOS-040 (Discovery Engine) | ❌ Non | ✅ Garder Hermes |
| **Simulation** | HOS-039 (Simulation Engine) | ❌ Non | ✅ Garder Hermes |
| **Cockpit Web** | HOS-051 (Next.js) | ❌ Non (TUI terminal) | ✅ Garder Hermes (web) + Oh My Pi (TUI) |
| **Event Bus** | HOS-034 (centralisé) | ❌ Non | ✅ Garder Hermes |
| **KTransformers** | HOS-052 (inference engine) | ❌ Non | ✅ Garder Hermes |
| **Documentation** | HOS-053 (Alexandrie) | ❌ Non | ✅ Garder Hermes |

### 3.2 Synthèse Décisionnelle

| Décision | Composants | Justification |
|---|---|---|
| **Garder Hermes** | Mission Planner, Agent Supervisor, Policy Engine, Knowledge Graph, Event Bus, Cockpit, Benchmark, Simulation | Fonctionnalités uniques d'orchestration/gouvernance/observabilité |
| **Utiliser Oh My Pi** | Édition code (LSP+AST), Débogage (DAP), Exécution Python/JS, LLM Routing (40+), AST structurel | Supériorité technique native (Rust, N-API, LSP, DAP) |
| **Créer adaptateur** | Workspace, Git, Memory, Runtime routing | Fonctionnalités présentes des deux côtés → pont nécessaire |
| **Fusionner** | Code analysis (KlaatCode + Oh My Pi LSP), Memory (Hermes KG + Oh My Pi hindsight) | Complémentarité : union des forces |
| **Ignorer** | TUI (Oh My Pi) vs Cockpit web (Hermes) | Chacun son interface, pas de conflit |

---

## 4. Rôle Optimal dans Hermes

### 4.1 Proposition : Oh My Pi comme **Agent Spécialisé + MCP Tool Provider**

Oh My Pi doit devenir un **agent spécialisé de niveau supérieur** à KlaatCode, complémentaire :

```
┌─────────────────────────────────────────────────────────────┐
│                    Hermes OS (orchestration)                 │
│                                                             │
│  Mission Planner → Agent Supervisor → Task Dispatcher       │
│                                            │                │
│                    ┌───────────────────────┼───────────┐    │
│                    │                       │           │    │
│               KlaatCodeAgent          OhMyPiAgent      │    │
│               (analyse MCP)          (édition LSP)     │    │
│                    │                       │           │    │
│               Code Analysis          LSP/DAP Edit      │    │
│               Diagnostics            AST structural    │    │
│               Validation             Debug real        │    │
│               Cost Guard             Python/JS exec    │    │
│                                      LLM routing 40+   │    │
│                                      Subagent swarms   │    │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Justification du Rôle

| Rôle | Oui/Non | Raison |
|---|---|---|
| **MCP Tool Provider** | ✅ OUI | Exposer les 32+ outils Oh My Pi via MCP pour tous les agents Hermes |
| **Agent spécialisé** | ✅ OUI | Comme KlaatCodeAgent, mais avec capacités Rust/LSP/DAP |
| **Runtime spécialisé** | ⚠️ Partiel | Le routing LLM 40+ providers pourrait servir de Runtime |
| **Moteur de calcul** | ❌ NON | Pas un moteur mathématique |
| **Module recherche** | ❌ NON | Pas un moteur de recherche |
| **Bibliothèque interne** | ⚠️ Partiel | La couche Rust via N-API pourrait être utilisée en interne |

### 4.3 Complémentarité KlaatCode ↔ Oh My Pi

| Tâche | KlaatCode | Oh My Pi |
|---|---|---|
| Analyse de projet | ✅ analyze_project | LSP diagnostics |
| Génération de plan | ✅ generate_code_plan | — |
| **Édition de code** | edit_file (basic) | ✅ **LSP-wired + AST + hashline** |
| **Débogage** | — | ✅ **DAP (lldb, dlv, debugpy)** |
| **AST edits** | — | ✅ **tree-sitter** |
| **Exécution code** | — | ✅ **Python/JS + callbacks** |
| Diagnostics | ✅ run_diagnostics | ✅ LSP diagnostics |
| Validation | ✅ validate_changes | LSP + tests |
| LLM routing | CostGuardAdapter | ✅ **40+ providers** |
| Navigation projet | ✅ inspect_code | ✅ LSP goto-def |

---

## 5. Découpage Recommandé HOS-055B/C/D

### HOS-055B — Oh My Pi Agent & MCP Adapter

Créer l'agent spécialisé et l'adaptateur MCP :

```
backend/agents/specialized/ohmyfi/
├── __init__.py
├── ohmyfi_agent.py          # Agent spécialisé Oh My Pi
├── ohmyfi_profile.py        # Profil avec capacités (LSP, DAP, AST, etc.)
├── ohmyfi_capabilities.py   # Task types et mappings
└── ohmyfi_mcp_adapter.py    # Expose 32+ outils Oh My Pi via MCP

backend/integrations/ohmyfi/
├── __init__.py
└── ohmyfi_client.py         # Wrapper headless omp CLI
```

**Capacités exposées :**
- `lsp_edit_file` — édition avec renommage LSP
- `ast_edit` — édition structurelle AST
- `debug_attach` — débogage DAP
- `code_execute` — exécution Python/JS avec callbacks
- `llm_route` — routing 40+ providers

**Intégrations :** AgentSupervisor, CapabilityMatcher, TaskDispatcher, EventBus, Memory

**Tests :** minimum 40 tests

### HOS-055C — Oh My Pi Deep Integration

Intégrations avancées :

1. **LSP/Diagnostics Bridge** — Oh My Pi LSP → Validation Engine HOS-050
2. **Memory Sync** — Oh My Pi `hindsight/` ↔ Hermes Unified Memory HOS-047
3. **Runtime Routing Bridge** — Oh My Pi 40+ LLM providers → Runtime Orchestrator HOS-038
4. **Workspace Bridge** — Oh My Pi `pi-iso` ↔ Hermes Workspace Manager HOS-045
5. **Subagent Bridge** — Oh My Pi swarms → Hermes Multi-Agent Collaboration HOS-044

### HOS-055D — Oh My Pi Cockpit & Finalization

1. **Frontend Oh My Pi Center** — panneau Cockpit : statut agent, outils LSP/DAP, session live, logs
2. **End-to-end tests** — mission complète Hermes → Oh My Pi
3. **Documentation** — architecture finale, exemple complet
4. **Performance benchmarks** — comparaison Oh My Pi vs KlaatCode sur tâches identiques

---

## 6. Architecture d'Intégration Finale

```
┌──────────────────────────────────────────────────────────────────┐
│                     Hermes OS (orchestration)                     │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │Mission Planner│  │Agent Supervisor│  │   Policy Engine     │   │
│  │   (DAG)      │  │  (lifecycle)  │  │   (ALLOW/DENY)      │   │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘   │
│         │                 │                      │               │
│         ▼                 ▼                      ▼               │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │              Task Dispatcher                              │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │    │
│  │  │KlaatCodeAgent│  │ OhMyPiAgent  │  │ Other Agents  │   │    │
│  │  │ (analysis,   │  │ (LSP, DAP,   │  │ (coder,       │   │    │
│  │  │  diagnostics)│  │  AST, exec)  │  │  reviewer,...) │   │    │
│  │  └──────┬───────┘  └──────┬───────┘  └──────────────┘   │    │
│  └─────────┼─────────────────┼──────────────────────────────┘    │
│            │                 │                                    │
│            ▼                 ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │                   MCP Platform                            │     │
│  │  ┌──────────────┐  ┌──────────────────────────────────┐ │     │
│  │  │KlaatCode MCP │  │       Oh My Pi MCP               │ │     │
│  │  │(7 tools)     │  │  (32+ tools: LSP, DAP, AST, ...) │ │     │
│  │  └──────────────┘  └────────────┬─────────────────────┘ │     │
│  └─────────────────────────────────┼───────────────────────┘     │
│                                    │                              │
│  ┌─────────────────────────────────┼───────────────────────┐     │
│  │         Integrations            │                        │     │
│  │  ┌──────────┐ ┌──────────┐ ┌───┴──────┐ ┌──────────┐   │     │
│  │  │Workspace │ │ Memory   │ │Runtime   │ │Knowledge │   │     │
│  │  │ Manager  │ │ Sync     │ │Routing   │ │Graph     │   │     │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │     │
│  └──────────────────────────────────────────────────────────┘     │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │              Oh My Pi Runtime (Rust + TypeScript)         │    │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────────────┐  │    │
│  │  │pi-natives│ │pi-shell│ │pi-ast  │ │40+ LLM Providers│  │    │
│  │  │(N-API)  │ │(PTY)   │ │(tree-  │ │(routing)        │  │    │
│  │  │         │ │        │ │ sitter)│ │                 │  │    │
│  │  └────────┘ └────────┘ └────────┘ └──────────────────┘  │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

---

## 7. Synthèse

### Forces d'Oh My Pi pour Hermes
- **Édition de code professionnelle** : LSP-wired renaming, AST structural edits, hashline anchors
- **Débogage réel** : DAP (lldb, dlv, debugpy) — pas de print() debugging
- **Exécution native** : Python/JS avec callbacks vers les outils de l'agent
- **LLM routing avancé** : 40+ providers avec fallback chains
- **Performance Rust** : 55K lignes Rust, N-API, zéro overhead

### Forces d'Hermes pour Oh My Pi
- **Planification structurée** : Mission DAG avec dépendances
- **Gouvernance** : Policy Engine, approval workflow
- **Knowledge Graph** : Graphe navigable de toutes les entités
- **Observabilité** : Event Bus centralisé, WebSocket temps réel
- **Cockpit web** : Dashboard de supervision

### Conclusion
**Oh My Pi complète KlaatCode** en apportant des capacités d'édition/débogage/exécution de niveau production que KlaatCode ne possède pas. KlaatCode reste le spécialiste de l'analyse, des diagnostics et de la validation. Ensemble, ils couvrent l'intégralité du cycle de développement logiciel autonome.

---

*Rapport HOS-055A — Ne pas coder. Passage à HOS-055B après validation.*
