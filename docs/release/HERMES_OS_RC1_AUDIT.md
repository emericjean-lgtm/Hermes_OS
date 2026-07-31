# Hermes OS v1.0 — Audit Release Candidate 1

> ## ⚠️ Statut : les 5 anomalies critiques de ce rapport sont levées
>
> **HOS-066B (2026-07-30)** a réalisé l'assemblage que ce rapport identifiait
> comme manquant. Le verdict 🔴 NO GO ci-dessous décrit l'état **au 2026-07-29**
> et reste le diagnostic de référence ; il ne décrit plus le dépôt.
>
> | Réf. | Anomalie critique | État |
> |---|---|---|
> | C-1 | Aucun composition root → 16 endpoints en `503` | ✅ 32/32 sous-systèmes instanciés, 0 × 5xx |
> | C-2 | 9 sous-systèmes sans surface HTTP | ✅ `APIRouter` délégant aux handlers existants |
> | C-3 | Deux namespaces API divergents | ✅ `/api/v1` canonique, legacy en 307 |
> | C-4 | 8 Centers du Cockpit inatteignables | ✅ 17/17 ids de sidebar résolvent |
> | C-5 | `/mcp` en `421` derrière Docker/nginx | ✅ hôtes de déploiement autorisés |
>
> Voir [`../architecture/COMPOSITION_ROOT_ARCHITECTURE.md`](../architecture/COMPOSITION_ROOT_ARCHITECTURE.md),
> [`../architecture/DEPENDENCY_REPORT.md`](../architecture/DEPENDENCY_REPORT.md)
> et l'entrée `[HOS-066B]` du `CHANGELOG.md`.
> Les anomalies **majeures et mineures** listées plus bas restent en grande
> partie ouvertes : voir la Phase 9 de `ROADMAP.md`.

> **Date de l'audit :** 2026-07-29
> **Périmètre :** dépôt complet (`backend/`, `frontend/`, `tests/`, `deployment/`, `installer/`, `docs/`)
> **Volumétrie :** 480 modules Python (~104 400 lignes), 102 fichiers TypeScript (~13 750 lignes), 127 fichiers de tests
> **Méthode :** exécution réelle — démarrage de l'application, 3 133 tests, build de production frontend, serveur uvicorn réel sondé route par route — complétée par de l'analyse statique (AST, pyflakes, `tsc`, graphe d'imports)

---

## 0. Synthèse exécutive

L'audit sépare deux constats qu'il faut lire ensemble.

**Le premier est excellent.** Les sous-systèmes d'Hermes OS sont réellement implémentés, et de bonne qualité. 3 117 tests passent, la logique métier est propre, les verrous sont posés (149 fichiers utilisent `Lock`/`RLock`), les collections critiques sont bornées (33 `deque(maxlen=…)`), la dette de surface est quasi nulle (0 marqueur `TODO`/`FIXME` réel, 2 `print()`, 0 `console.log`), et le `docker-compose` est valide. Ce n'est pas un prototype.

**Le second est bloquant.** Au début de l'audit, **l'application ne démarrait pas** (`NameError` dans le lifespan), **aucune route Hermes OS n'était servie** (70 routes exposées, zéro appartenant aux HOS), **le frontend ne compilait pas** (6 dépendances non déclarées) et **la suite de tests ne terminait jamais** (un test WebSocket bloquait indéfiniment). La cause n'est pas un manque de code : c'est un **défaut d'assemblage**. Chaque sous-système est construit et testé en isolation, avec ses dépendances injectées par les tests, mais **rien n'assemble ces sous-systèmes en une application**.

Le motif est systématique et vérifiable :

| Point d'injection prévu par le code | Appelé en production ? | Appelé par les tests ? |
|---|---|---|
| `create_agent_routes(supervisor)` | ❌ jamais | ❌ jamais |
| `create_memory_routes(manager)` | ❌ jamais | ❌ jamais |
| `create_policy_routes(engine)` | ❌ jamais | ❌ jamais |
| `create_mission_routes(executor)` | ❌ jamais | ❌ jamais |
| `RuntimeOrchestrator().configure(…)` | ❌ jamais | ✅ oui |
| `IntegrationManager()` (HOS-056) | ❌ jamais | ✅ oui |
| `MissionControlRouter(service)` (HOS-028) | ❌ jamais | ✅ oui |

Les tests construisent chacun leur propre `FastAPI()` et y montent le routeur à tester (`tests/architecture/test_sds_wiring.py:104`, `tests/api/test_mission_control_api.py:219`, …). La suite est donc verte alors que le produit assemblé ne fonctionne pas — exactement le risque que `backend/tests/test_smoke_live_server.py` documente dans son en-tête, et ce fichier est le seul à l'avoir détecté.

**25 anomalies ont été corrigées** pendant cet audit, dont les 6 critiques qui empêchaient tout démarrage, tout build et toute exécution complète de la CI. **27 anomalies subsistent, dont 5 critiques** : elles demandent du code d'assemblage et des décisions d'architecture, ce qui sort du mandat « aucune nouvelle fonctionnalité ».

**Décision : 🔴 NO GO pour RC2** — justification au §14.

### État avant / après, mesuré

| Indicateur | Avant | Après |
|---|---|---|
| Démarrage de l'application | 🔴 `NameError` | ✅ démarre |
| Routes servies (chemins distincts) | 70 (dont **0** HOS) | **182** (dont 109 HOS + 8 SDS) |
| `tests/` (architecture, API, intégrations, sécurité, production) | 2357 passés, 10 échecs, 2 erreurs de collecte, **1 blocage infini** | ✅ **2366 passés, 0 échec** |
| `backend/tests/` (legacy Hermes) | 645 passés, 24 échecs, 45 erreurs | **751 passés, 16 échecs** (un seul cause racine : C-1) |
| Frontend `tsc --noEmit` | 🔴 72 erreurs | ✅ **0** |
| Frontend `next build` | 🔴 échec | ✅ **14 pages** |
| Frontend `vitest` | 🔴 37 échecs / 65 | ✅ **65 / 65** |
| `pyflakes` noms indéfinis | 9 | ✅ **0** |
| Durée `backend/tests` | 520 s | **136 s** (−74 %) |
| Suite smoke end-to-end | 30 échecs / 412 s | 16 échecs / **28 s** (−93 %) |

---

## 1. Architecture — score **60 / 100**

### 1.1 Conformité aux critères demandés

| Critère | Résultat | Détail |
|---|---|---|
| Aucune dépendance circulaire | ⚠️ 1 cycle bénin | `backend.api` ↔ `backend.api.router` (l'`__init__` réexporte le module qui l'importe). Les 3 autres cycles vus en première passe sont des faux positifs : imports différés en corps de fonction. |
| Tous les composants enregistrés | ❌ **non** | Aucun composition root — voir **C-1** |
| Tous les adaptateurs réellement utilisés | ❌ **non** | 5 adaptateurs référencés uniquement par leurs tests — voir **M-6** |
| Aucun module orphelin | ⚠️ 19 restants | 34 → 19 après câblage des routeurs — voir §1.4 |
| Aucun service instancié plusieurs fois | ✅ conforme | Motif singleton `_x: Optional[T] = None` + accesseur, cohérent sur 32 occurrences |
| Tous les EventBus cohérents | ❌ **non** | 26 des 28 topics RAL rejetés silencieusement par l'`EventHub` legacy — voir **M-2b** |
| Interfaces prévues utilisées | ✅ | `RuntimeInterface` (Protocol), `MemoryBackend`, `EventBusInterface` respectés |
| Aucune duplication fonctionnelle | ❌ **non** | 6 duplications structurelles — voir **M-7** |
| Responsabilités non mélangées | ⚠️ | Deux conventions de routage incompatibles cohabitent — voir **C-2** |
| Dépendances découplées | ✅ | Couplage moyen 1,4 sous-système ; les couches basses (`core`, `memory`, `ral`) sont bien les plus importées |
| Patterns respectés | ✅ | Façade, Registry, Adapter, Circuit Breaker, Protocol — présents et correctement formés |

### 1.2 Matrice des dépendances

35 sous-systèmes. La matrice 35×35 étant illisible, voici sa forme utile : fan-out (sous-systèmes importés) et fan-in (importateurs). Une ligne `0 / 0` désigne un **îlot totalement isolé**.

| Sous-système | Fan-out | Fan-in | Importe |
|---|---|---|---|
| `api` | 14 | 1 | agent, agents, core, documents, events, memory, monitoring, projects, security, self_evolution, services, tasks, tools, workflows |
| `mcp_server` | 11 | 2 | agents, core, documents, memory, monitoring, projects, security, self_evolution, tasks, tools, workflows |
| `integrations` | 10 | 4 | agent, agents, connectors, core, events, execution, memory, ral, skills, workspace |
| `agents` | 8 | 6 | connectors, core, integrations, memory, mission, projects, security, tasks |
| `services` | 6 | 1 | agent, events, integrations, memory, ral, skills |
| `core` | 5 | **12** | connectors, memory, security, tasks, workflows |
| `memory` | 5 | **12** | core, projects, security, tasks, workflows |
| `self_evolution` | 4 | 2 | agents, core, memory, tasks |
| `tools` | 4 | 3 | agents, core, runtime, security |
| `workflows` | 3 | 4 | core, mcp_server, memory |
| `agent` | 2 | 3 | integrations, ral |
| `monitoring` | 2 | 2 | connectors, core |
| `projects` | 2 | 4 | core, memory |
| `sds` | 2 | 1 | connectors, ral |
| `security` | 2 | 6 | core, memory |
| `connectors` | 1 | 6 | ral |
| `policy` | 1 | 1 | explainability |
| `ral` | 1 | 6 | connectors |
| `tasks` | 1 | 6 | memory |
| `runtime` | 0 | 2 | — feuille, correct |
| `events` | 0 | 3 | — feuille, correct |
| `config` | 0 | 1 | — feuille, correct |
| `documents` | 0 | 2 | — feuille, correct |
| `mission` | 0 | 2 | — feuille, correct |
| `skills` | 0 | 2 | — feuille, correct |
| `workspace` | 0 | 2 | — feuille, correct |
| `execution` | 0 | 1 | — feuille, correct |
| `explainability` | 0 | 1 | — feuille, correct |
| **`autonomous`** | **0** | **0** | 🔴 îlot isolé (HOS-063) |
| **`conversation`** | **0** | **0** | 🔴 îlot isolé (HOS-064) |
| **`evolution`** | **0** | **0** | 🔴 îlot isolé (HOS-058) |
| **`model_intelligence`** | **0** | **0** | 🔴 îlot isolé (HOS-065) |
| **`voice`** | **0** | **0** | 🔴 îlot isolé (HOS-064) |
| **`logging`** | **0** | **0** | 🔴 îlot isolé (HOS-062) |
| **`storage`** | 1 | **0** | 🔴 jamais importé (HOS-062) |

**Lecture.** `core` et `memory` sont les hubs, avec 12 importateurs chacun : la hiérarchie de couches est saine. Mais **7 sous-systèmes livrés comme HOS complets ne sont ni importés ni importateurs** — ils sont totalement déconnectés du système (**M-12**).

### 1.3 Surface HTTP réellement servie

Mesurée en instanciant l'application et en énumérant les **chemins distincts** de
`app.routes` (203 entrées de route au total, un même chemin pouvant porter plusieurs
méthodes HTTP) :

| Groupe | Avant | Après |
|---|---|---|
| Legacy Hermes (`/chat`, `/memory`, `/tasks`, …) | 64 | 64 |
| `/api/hermes-os/*` (SDS, HOS-003) | **0** | 8 |
| `/api/v1/*` (HOS-030 → HOS-065) | **5** (klaatcode seul) | **109** |
| `/mcp` | 1 | 1 |
| **Total (chemins distincts)** | **70** | **182** |

### 1.4 Modules orphelins restants (19)

| Modules | Nature |
|---|---|
| `{autonomous,conversation,evolution,execution,explainability,model_intelligence,security,skills,tools}/routes.py` | Convention `handle_*` sans `APIRouter` → non montables (**C-2**) |
| `model_intelligence/model_{autonomous,evolution,memory,runtime}_adapter.py` | Adaptateurs HOS-065B jamais câblés (**M-6**) |
| `runtime/ktransformers/kt_{cache,loader,model_manager,optimizer,scheduler}.py` | Prototypes HOS-052/052B morts, imports cassés (**M-5**) |
| `policy/approval_explainer.py` | Livrable HOS-064 jamais câblé (**M-6**) |
| `agents/atlas.py` | Code mort, 20 lignes, aucune référence (**mn-8**) |

---

## 2. Backend — score **66 / 100**

| # | Sévérité | Anomalie | Preuve | État |
|---|---|---|---|---|
| A-1 | 🔴 | `get_runtime_registry` non importé → `NameError` dans le lifespan : **l'application ne démarrait pas** | `STARTUP FAILED: NameError` | ✅ corrigé |
| A-2 | 🔴 | `SDS_ROUTER` et 19 routeurs HOS complets et testés, jamais montés → 404 sur toute l'API Hermes OS | 70 → 182 chemins | ✅ corrigé |
| C-1 | 🔴 | **Aucun composition root** : aucun service instancié au démarrage | 16 endpoints → `503 not initialized` | ⛔ ouvert |
| C-2 | 🔴 | **9 sous-systèmes sans aucune surface HTTP** | modules `handle_*` sans `APIRouter` | ⛔ ouvert |
| C-5 | 🔴 | **`/mcp` renvoie 421 derrière Docker/nginx** — voir §8 | `Host: hermes-backend:8000` → `421 Invalid Host header` | ⛔ ouvert |
| A-3 | 🟠 | `import time` manquant : le circuit breaker Alexandrie lève `NameError` au moment précis où il doit protéger | pyflakes | ✅ corrigé |
| A-4 | 🟠 | `os.statvfs` inexistant sous Windows et `except OSError` ne rattrape pas l'`AttributeError` → System Monitor mort | 2 tests | ✅ corrigé |
| A-5 | 🟠 | `DatabaseConfig(name=":memory:")` → `sqlite:///:memory:.db`, base inouvrable | 3 tests | ✅ corrigé |
| A-6 | 🟠 | `replay(until=…)` inclusif : un événement pile sur la borne est rejoué par deux fenêtres adjacentes | 1 test | ✅ corrigé |
| A-7 | 🟠 | `get_last_checkpoint()` : `max()` renvoie le **premier** ex æquo → mauvais checkpoint | 1 test | ✅ corrigé |
| A-8 | 🟠 | `time.monotonic()` = **15,6 ms** de résolution sous Windows → tout chargement de skill < 15 ms profilé à **0 ms**, ce qui aplatit les moyennes servant à classer les skills | `time.get_clock_info` vérifié | ✅ corrigé |
| A-17 | 🟠 | `/api/v1/alexandrie/health` = **22,4 s** quand Alexandrie est absent (3 retries × backoff 1/2/4 s + 5 s de connect) — rendait la suite smoke inexploitable | mesuré | ✅ corrigé (→ 4,1 s) |
| A-18 | 🟠 | Harnais MCP cassé par la montée de version du SDK : `Host: mcp-test` → `421` | 24 tests | ✅ corrigé |
| M-1 | 🟠 | Validation d'entrée absente : 19 corps `dict = Body(...)`, **3 `response_model` sur 195 routes** | `POST /api/v1/missions {}` → **200** ; `{"type":"x"}` → **500** (attendu 422) | ⛔ ouvert |
| M-2a | 🟠 | Dispatch WebSocket via `asyncio.get_event_loop()` + `ensure_future` depuis un thread étranger → événements perdus silencieusement | `api/router.py:306`, `runtime/events/routes.py:57` | ⛔ ouvert |
| M-2b | 🟠 | L'`EventHub` legacy rejette **26 des 28** topics RAL | `WARNING unknown event type 'runtime.started', not published` | ⛔ ouvert |
| M-8 | 🟠 | `mission/routes.py:_missions` : dict module-level non borné, sans verrou, sans persistance | fuite mémoire + perte au redémarrage | ⛔ ouvert |
| M-11 | 🟠 | `bus.publish` monkey-patché dans une factory de routes → double emballage si appelée deux fois | `runtime/events/routes.py:63` | ⛔ ouvert |
| M-13 | 🟠 | `requirements.txt` : `mcp>=1.0` sans borne haute → la 1.26.0 a introduit la protection DNS-rebinding, cause de A-18 **et** de C-5 | — | ⛔ ouvert |
| mn-1 | 🟡 | 59 `except Exception: pass`, dont `send_event` qui masque tout échec d'envoi WebSocket | grep | ⛔ ouvert |
| mn-2 | 🟡 | 8 noms indéfinis dans des annotations (inoffensifs grâce à `from __future__ import annotations`, mais cassent `get_type_hints()`) | pyflakes | ✅ corrigés |
| mn-3 | 🟡 | 2 `print()` dans des handlers d'exception de production | grep | ✅ corrigés |
| mn-9 | 🟡 | `Task was destroyed but it is pending` (`sse_starlette`) à l'arrêt : ordre d'arrêt imparfait | sortie pytest | ⛔ ouvert |
| mn-10 | 🟡 | `chromadb` et `sqlalchemy` requis à l'import de `backend.main` (via `agents/echo.py` → `memory/semantic.py`) : sans eux l'application ne démarre pas et 25 fichiers de tests ne collectent pas. Aucune dégradation gracieuse. | collecte pytest | ⛔ ouvert |
| cos-1 | ⚪ | 321 imports inutilisés hors `__init__.py`, 20 variables locales inutilisées, 7 f-strings sans placeholder | pyflakes | ⛔ ouvert |

**Sur les 321 imports inutilisés.** Vérification menée sur le plus gros contributeur (`services/mission_control.py`, 44 occurrences) : aucun de ces 44 noms n'est réimporté par `services/__init__.py`, `api/hos_routes.py` ni par les tests. Ce sont donc de vrais imports morts, pas des ré-exports porteurs. Ils n'ont **pas** été supprimés : 321 éditions sur ~150 fichiers noieraient les correctifs importants dans le diff d'une RC de stabilisation. À traiter en passe mécanique dédiée.

### 2.1 Thread safety, concurrence, fuites

| Contrôle | Résultat |
|---|---|
| Verrous | ✅ 149 fichiers avec `Lock`/`RLock`, sections critiques correctement encadrées |
| Deadlocks | ✅ aucun ; `RLock` là où la réentrance est possible ; aucun verrou tenu pendant un appel réseau |
| Race conditions | ⚠️ **M-8** (`_missions` sans verrou), **M-11** (patch de `publish` non idempotent) |
| Fuites mémoire | ⚠️ **M-8** ; 37 collections non bornées (contre 33 `deque(maxlen=…)` correctes) |
| Tests de concurrence | ✅ présents et passants (`TestSecurityThreadSafety`, `TestThreadSafety`, 4 × 10 threads) |
| Blocage de la boucle d'événements | ✅ correct — les routes d'intégration sont déclarées `def` (threadpool), pas `async def` |

---

## 3. Frontend — score **58 / 100**

| # | Sévérité | Anomalie | État |
|---|---|---|---|
| A-9 | 🔴 | 6 dépendances importées mais non déclarées (`@xyflow/react`, `@tanstack/react-table`, `react-resizable-panels`, `zod`, `react-hook-form`, `@hookform/resolvers`) → **build impossible** | ✅ corrigé |
| A-10 | 🔴 | 3 pages utilisent une API inexistante de `react-resizable-panels` (`Group`/`Separator`/`orientation` au lieu de `PanelGroup`/`PanelResizeHandle`/`direction`) | ✅ corrigé |
| A-11 | 🔴 | `dashboard/layout.tsx` importe `CockpitShell` en nommé alors qu'il est en défaut, et ne rend jamais `{children}` ; `page.tsx` réexporte le layout comme page → **route `/dashboard` cassée** | ✅ corrigé |
| C-3 | 🔴 | Deux clients API divergents : `lib/*` → `/api/hermes-os`, `services/client.ts` → `/api/v1` (97 endpoints appelés) | ⛔ ouvert |
| C-4 | 🔴 | **14 Centers inatteignables** : 8 ne sont même pas importés par `cockpit-shell.tsx` (autonomous, code-intelligence, conversation, deployment, evolution, models, security, system) ; **Installer Center absent du dépôt** | ⛔ ouvert |
| A-12 | 🟠 | `RuntimeEvents.tsx` : hook inexistant (`useRuntimeEventStream`), champ inexistant (`connectionState`), forme d'événement incompatible (`runtime_id`/`event_type` vs `runtime`/`type`) | ✅ corrigé |
| A-15 | 🟠 | 37 tests utilisaient `require()` avec l'alias Vite `@/` — non résoluble par CommonJS, tous en échec | ✅ corrigé (→ `await import()`) |
| M-10 | 🟠 | `eslint`/`eslint-config-next` absents des devDependencies alors qu'`eslint.config.mjs` existe et que `pnpm lint` est déclaré → **le lint ne peut pas tourner** | ⛔ ouvert |
| A-13 | 🟡 | `types/mission-control.ts` : union `severity` amputée de `DEBUG`/`CRITICAL`, que le backend émet réellement | ✅ corrigé |
| A-14 | 🟡 | `use-websocket.ts` : `useRef()` sans argument initial (invalide avec les types React 19) | ✅ corrigé |
| mn-4 | 🟡 | 15 composants jamais référencés (`ActivityPanel`, 6 cartes `dashboard/`, `kt-panel`, `klaatcode-panel`, `ohmypi-panel`, 8 centers) | ⛔ ouvert |
| mn-5 | 🟡 | Deux types `RuntimeEvent` divergents (`types/mission-control.ts`, `hooks/use-runtime-events.ts`) | ⚠️ contourné dans le composant |
| cos-2 | ⚪ | `reactflow@11` déclaré mais jamais importé (remplacé par `@xyflow/react@12`) | ✅ supprimé |
| cos-3 | ⚪ | `frontend/AGENTS.md` demande de lire `node_modules/next/dist/docs/` — répertoire inexistant en Next 15.1.0 | ⛔ ouvert |

**Points conformes.** Next.js 15.1.0 App Router, React Query v5 (`refetchInterval` configuré), Zustand (`useCockpitStore`, store plat, sélecteurs), WebSocket avec reconnexion et backoff, dark mode par variables CSS, `useMemo` correctement appliqué aux listes filtrées/fusionnées. Aucun `console.log`. Aucune erreur React au build. Bundle partagé 106 kB, page la plus lourde 316 kB.

---

## 4. Runtime — score **70 / 100**

| Composant | État |
|---|---|
| Ollama (`HermesOllamaRuntime`) | ✅ implémenté + testé |
| StubRuntime | ✅ runtime par défaut au démarrage |
| llama.cpp | ⚠️ variantes CPU mappées (`avx512_*`, `avx2_llamafile`, `blis_amd`) mais pas de runtime dédié |
| KTransformers | ✅ HOS-052C fonctionnel (`KTRuntime` + `HermesKTAdapter`, fallback simulé sans `kt_kernel`) ; ⚠️ 5 modules prototypes morts (**M-5**) |
| vLLM | ❌ **absent** — classé « Futur HOS-039 » dans la ROADMAP alors qu'il figure au périmètre à tester |
| Runtime Router / Discovery / Benchmarks / Optimizer / Fallback / Policies | ✅ implémentés ; `/api/v1/runtime/*` répond 200 |
| Sélection par tâche / modèle / matériel / VRAM / RAM | ⚠️ **capacité présente, jamais activée** : `RuntimeOrchestrator` n'est **jamais** instancié ni `configure()` en production (uniquement dans `tests/architecture/test_runtime_orchestrator.py:51`). Les callbacks de scoring restent à `lambda rid: None` : la sélection tourne en mode dégradé **silencieux**. La VRAM est bien prise en compte dans le code (69 références). |

---

## 5. Agents — score **65 / 100**

| Composant | État |
|---|---|
| Agent Supervisor | ⚠️ **deux** implémentations concurrentes, toutes deux en usage (`agent/supervisor.py::MultiAgentSupervisor`, 3 réf. ; `agents/agent_supervisor.py::AgentSupervisor`, 13 réf.) |
| Agent Lifecycle | ⚠️ **deux** implémentations (`agent/lifecycle.py`, 4 réf. ; `agents/agent_lifecycle.py`, 3 réf.) |
| Agent Registry | ⚠️ **deux** implémentations (`core/agent_registry.py`, 25 réf. ; `agents/agent_registry.py`, 5 réf.) |
| KlaatCode Agent | ✅ intégré et monté (`/api/v1/klaatcode/*` → 200) |
| Oh My Pi Agent | ✅ intégré et monté (`/api/v1/ohmypi/*` → 200) |
| Code Intelligence Agent | ✅ présent (`agents/specialized/code_intelligence/`) |
| Collaboration / Delegation / Consensus / Conflict Resolution | ✅ implémentés, routes montées — ⚠️ **503** (C-1) |
| Context Sharing | ✅ `execution_context.py`, `capability_matcher.py` |
| Transitions / événements / mémoire / métriques / reprise d'erreur | ✅ couverts (machine à 10 états, tests de transition passants) |
| `agents/atlas.py` | ⚪ code mort, 20 lignes, aucune référence |

---

## 6. Mémoire — score **72 / 100**

| Composant | État |
|---|---|
| Working / Episodic / Semantic / Procedural / Document Memory | ✅ implémentés (7 scopes `UnifiedMemory`) |
| Embedding Index / Retrieval Engine | ✅ ChromaDB + `OllamaEmbeddingFunction` |
| Knowledge Graph | ✅ implémenté |
| Experience Manager | ✅ implémenté |
| Recherche hybride / graph traversal / recommandations / apprentissage | ✅ couverts par les tests |
| **Exposition HTTP** | ⚠️ `/api/v1/memory/*` monté mais **503** (C-1) |
| Dépendance dure | ⚠️ **mn-10** — `chromadb`/`sqlalchemy` requis à l'import, sans dégradation gracieuse |

---

## 7. Sécurité — score **68 / 100**

| Composant | État |
|---|---|
| Permission Manager | ✅ implémenté + testé |
| Trust Engine (`AgentTrustEngine`) | ✅ implémenté + testé |
| Threat Detector | ✅ implémenté + testé |
| Isolation Manager | ✅ implémenté + testé (4 niveaux) |
| Policy Engine | ✅ implémenté ; routes montées mais **503** (C-1) |
| Human Approval | ✅ implémenté ; `/api/v1/approval` monté mais **503** (C-1) |
| Sandbox | ✅ `tools/tool_sandbox.py` |
| Workspace Protection | ✅ `workspace/` + verrouillage |
| MCP Permissions / Tool Governance | ✅ `tools/tool_policy.py`, `mcp/` |
| **Escalade de privilèges** | ✅ **aucune trouvée** ; les tests couvrent refus et overrides de policy |
| **Permissions incohérentes** | ✅ **aucune trouvée** |
| **Validations oubliées** | 🟠 **oui — M-1.** Sur les routes montées, un corps JSON arbitraire n'est pas validé. Ce n'est pas une faille d'autorisation (il n'y a pas d'authentification multi-utilisateur en v1.0, cf. ROADMAP HOS-040), mais c'est une surface d'entrée non contrôlée : une erreur client produit un `500` et une trace serveur au lieu d'un `422`. |
| **Surface HTTP du Security Engine** | 🔴 **inexistante** — `security/routes.py` est en convention `handle_*` (**C-2**). Le Security Center n'a aucun backend joignable. |

---

## 8. Production — score **60 / 100**

| Contrôle | Résultat |
|---|---|
| Configurations | ✅ 6 profils de déploiement, `ConfigManager`, `EnvironmentLoader`, validation |
| Dockerfile backend / frontend | ✅ présents |
| docker-compose (`.yml`, `.cpu.yml`, `.gpu.yml`) | ✅ **`docker compose config` valide** ; postgres 16, redis, chromadb, backend, frontend + 7 volumes nommés |
| nginx.conf | ✅ présent |
| PostgreSQL | ✅ chemin implémenté (`_init_postgresql`) + compose |
| SQLite | ✅ corrigé (A-5) ; WAL + `foreign_keys=ON` |
| Monitoring | ✅ corrigé (A-4) ; 84/84 tests passants |
| Logging | ⚠️ implémenté mais **îlot isolé** (fan-in 0) |
| Recovery / Backup / Restore | ✅ implémentés + testés |
| Update / Rollback | ✅ `MigrationManager` (corrigé via A-5) |
| **MCP en déploiement** | 🔴 **C-5.** `FastMCP` (mcp 1.26.0) active par défaut la protection DNS-rebinding avec `allowed_hosts=['127.0.0.1:*','localhost:*','[::1]:*']`. Vérifié sur l'application réelle : `Host: localhost:8000` → **200** ; `Host: hermes-backend:8000` (nom de service du compose) → **421** ; `Host: hermes.local` → **421** ; `Host: localhost` sans port → **421**. **Toute la surface MCP est donc injoignable dans le déploiement Docker documenté.** |
| Installer | ⚠️ 2 modules seulement (`system_detector.py`, `hardware_profile.py`). Ni API, ni routes, ni Installer Center. La « Intelligent Installer & Deployment Platform » est en réalité une brique de détection matérielle. |
| Portabilité Windows | ✅ après A-4. 3 dépendances POSIX résiduelles correctement gardées (`/proc/meminfo`, `/proc/stat`, `os.getloadavg`) ; `os.statvfs` ne l'était pas → corrigé |

---

## 9. Cockpit — score **55 / 100**

| Contrôle | Résultat |
|---|---|
| WebSocket temps réel | 🔴 **cassé sur deux plans indépendants** : (a) le forwarder wildcard du lifespan pousse tous les événements du bus vers l'`EventHub`, qui **rejette silencieusement 26 des 28 topics** (**M-2b**) ; (b) les deux dispatchers WS utilisent `asyncio.get_event_loop()` + `ensure_future` depuis un thread potentiellement étranger, ce qui perd l'événement sans erreur (**M-2a**) |
| Synchronisation des vues | ✅ store Zustand unique, sélecteurs, `activeView` |
| Performances | ✅ `useMemo` sur fusion/filtrage ; bundle correct |
| Cohérence des données | ⚠️ deux formes d'événement runtime divergentes (**mn-5**, contournées côté composant) |
| Rafraîchissements | ✅ `refetchInterval: 5000` |
| Navigation | ⚠️ **9 Centers atteignables sur 23 annoncés** (**C-4**) |
| Indicateurs / statistiques | ✅ implémentés ; ⚠️ alimentés par des endpoints en **503** (C-1) |

---

## 10. Documentation — score **64 / 100**

| Document | État |
|---|---|
| `CHANGELOG.md` | ⚠️ 69 entrées HOS, mais **HOS-059, 060, 061, 065, 065B absents** alors que HOS-065/065B existent en code et en documentation d'architecture. Ordre non monotone (064 → 062 → 063 → 055D → 058). Aucun en-tête de version sémantique (`[Unreleased]`, `1.0.0-rc1`). 74 backticks échappés rendus littéralement → **corrigés**. |
| `ROADMAP.md` | 🟠 **fortement désynchronisé** : annonce « ~18 000 lignes » (réel ~118 000), « ~60 fichiers Python » (réel 480), « ~693 tests » (réel 3 133), « 10 pages frontend » (réel 11 routes / 23 Centers annoncés). Le tableau « Métriques projet » est malformé. HOS-036/037/038 figurent simultanément en ✅ et en 📅 Planifié. |
| `ARCHITECTURE.md` | ✅ 19 diagrammes Mermaid, structure cohérente |
| Mermaid | ✅ 38 blocs, syntaxe valide |
| `README.md` | ✅ cohérent |
| Doc API | ⚠️ OpenAPI généré, mais **3 `response_model` sur 195 routes** → schémas de réponse quasi absents (**M-1**) |
| Docs d'intégration | ✅ 27 documents d'architecture ; ⚠️ `docs/integrations/` ne couvre que Freebuff et Hermes Agent (ni Alexandrie, ni KlaatCode, ni Oh My Pi, ni KTransformers, documentés ailleurs) |
| `package.json` (racine) | ⚪ annonçait « Next.js 16 » pour un projet en 15.1.0 → **corrigé** |

---

## 11. Performance — score **80 / 100**

| Détection demandée | Résultat |
|---|---|
| Copies inutiles | ✅ rien de significatif |
| Allocations inutiles | ✅ rien de significatif |
| Collections jamais vidées | 🟠 37 collections non bornées, dont `_missions` (**M-8**) — contre 33 `deque(maxlen=…)` correctes |
| Caches incohérents | ✅ health check avec TTL 30 s, correct |
| Index dupliqués | ✅ aucun |
| Recherches O(n²) | ✅ aucune ; tri topologique et détection de cycles (DFS 3-couleurs) corrects |
| Boucles inutiles | ✅ aucune |
| Appels réseau redondants | ✅ mitigés par le cache de health |
| Blocages CPU | ✅ aucun ; les handlers synchrones passent par le threadpool |
| Contention des locks | ✅ faible ; aucun verrou tenu pendant une I/O |
| **Latence** | ✅ **A-17 corrigé** : `/api/v1/alexandrie/health` 22,4 s → 4,1 s. Effet mesuré sur la suite end-to-end : **412 s → 28 s** et 14 échecs par `ReadTimeout` supprimés. |

---

## 12. Dette technique

### 12.1 Nettoyage — état remarquablement propre

| Recherche | Résultat |
|---|---|
| `TODO` / `FIXME` / `XXX` / `HACK` | ✅ **0 marqueur réel** (les 2 occurrences sont la valeur d'énumération `TaskStatus.TODO`) |
| `print()` en production | ✅ 2 trouvés → **corrigés** |
| `console.log` / `console.debug` | ✅ **0** |
| Logging temporaire | ✅ aucun |
| Commentaires obsolètes | ✅ aucun ; les commentaires existants sont substantiels et expliquent le *pourquoi* |
| Code mort | 🟠 5 modules KT + `agents/atlas.py` + 15 composants frontend |
| Imports inutilisés | 🟡 321 (backend) ; 0 (frontend après correctifs) |
| Fichiers inutilisés | 🟠 19 modules orphelins |
| Anciens prototypes | 🟠 `kt_{cache,loader,model_manager,optimizer,scheduler}.py` — **imports cassés** (`KTCacheStats` n'existe plus dans `kt_models`) : ces 5 modules ne s'importent même pas |
| Adaptateurs obsolètes | 🟠 `test_ktransformers_integration.py` teste l'API HOS-052B (`KTKernelWrapper`, `get_kernel_wrapper`, `is_kernel_available`, `cpu_variant`, `KTRuntimeCandidate`) supprimée par HOS-052C |

### 12.2 Duplications fonctionnelles (M-7)

| Duplication | Occurrences | Les deux en usage ? |
|---|---|---|
| `backend/agent/` vs `backend/agents/` | 2 supervisors, 2 lifecycles | ✅ oui |
| `core/agent_registry.py` vs `agents/agent_registry.py` | 25 réf. vs 5 réf. | ✅ oui |
| `backend/evolution/` vs `backend/self_evolution/` | 2 moteurs d'évolution | ✅ oui |
| `SkillSelection` | `skills/orchestrator.py:105` et `skills/skill_models.py:109` | ✅ oui |
| `RuntimeEvent` (TS) | `types/mission-control.ts` et `hooks/use-runtime-events.ts` | ✅ oui |
| **Création de mission** | `mission/routes.py` (non validée, **montée**) vs `api/hos_routes.py` (validée Pydantic, **non montée**) | La version **non validée** est celle qui sert |

La dernière ligne est la plus symptomatique : la couche API validée et documentée (HOS-028, `api/models.py`, `MissionCreateRequest`) est celle qui n'est pas montée ; la couche non validée est celle qui répond.

### 12.3 Tests

| Contrôle | Avant | Après |
|---|---|---|
| `tests/` | 2357 passés, 10 échecs, 2 erreurs de collecte, **1 blocage infini** | ✅ **2366 passés, 1 ignoré, 0 échec** |
| `backend/tests/` | 645 passés, 24 échecs, 45 erreurs | **751 passés, 2 ignorés, 16 échecs** |
| Frontend (vitest) | 28 passés, 37 échecs | ✅ **65 passés, 0 échec** |
| **Total** | — | **3 117 passés / 3 133** |
| Nature des 16 échecs restants | — | **Une seule cause racine : C-1.** Ce sont exactement les 16 endpoints qui répondent `503 not initialized`, et `503` est un 5xx : l'assertion `test_no_route_returns_5xx` fait donc correctement son travail. |
| Test instable | 🔴 `test_websocket_accepts_connection` bloquait indéfiniment sur `ws.receive_text()` alors que son propre commentaire indique que le handler n'émet rien → **la CI ne terminait jamais** | ✅ corrigé |
| Test non portable | 🟡 `test_capture_pytest_baseline_script_is_executable` : NTFS n'a pas de bit d'exécution POSIX | ✅ corrigé (skip Windows) |
| `pytest.ini` | 🟠 **M-9 : `testpaths = backend/tests` uniquement.** Un `pytest` nu n'exécute que 767 tests sur 3 133 : **les 2 366 tests de `tests/`, dont toute l'architecture HOS, ne tournent pas par défaut.** `scripts/test-backend.mjs` hérite du même périmètre. | ⛔ ouvert |
| Couverture perdue | 🟠 **M-4** : `test_ktransformers_integration.py` est mort depuis HOS-052C — perte réelle de couverture sur la couche d'intégration KT | ⛔ ouvert |
| Dépendances oubliées | 🟠 `pytest`, `pytest-asyncio`, `sqlalchemy`, `chromadb` absents de l'environnement fourni ; `pytest-timeout` a dû être ajouté pour diagnostiquer le blocage | ⛔ ouvert |

**Non-régression vérifiée.** Le montage des 19 routeurs HOS aurait pu casser les routes legacy. Contrôle explicite sur un serveur uvicorn réel : `/system/status`, `/system/models`, `/tasks`, `/workflows`, `/verification/runners`, `/memory/types` répondent tous **200**. Les échecs que ces routes présentaient dans la suite smoke étaient dus au `ReadTimeout` provoqué par A-17, et ont tous disparu après sa correction.

---

## 13. Correctifs appliqués (25)

Aucune fonctionnalité n'a été développée. Aucune architecture saine n'a été réécrite. Chaque correctif répare une anomalie constatée, reste localisé, et a été validé par exécution.

### Backend (16)

| Fichier | Correctif |
|---|---|
| `backend/main.py` | Import manquant `get_runtime_registry` — l'application ne démarrait pas |
| `backend/main.py` | Montage de `SDS_ROUTER` + 19 routeurs HOS sous `/api/v1` (70 → 182 chemins) |
| `backend/integrations/alexandrie/hermes_alexandrie_adapter.py` | `import time` manquant (circuit breaker) |
| `backend/integrations/alexandrie/alexandrie_client.py` | Session dédiée sans retry pour les sondes de santé (22,4 s → 4,1 s) |
| `backend/monitoring/system_monitor.py` | `os.statvfs` → `shutil.disk_usage` (+ `import shutil`) |
| `backend/config/config_models.py` | Prise en charge du sentinelle SQLite `:memory:` |
| `backend/ral/event_bus_impl.py` | `replay(until=…)` rendu exclusif (fenêtre semi-ouverte) |
| `backend/execution/execution_state.py` | `get_last_checkpoint()` : départage déterministe des ex æquo |
| `backend/skills/skill_profiler.py` | `time.monotonic()` → `time.perf_counter()` (×2) |
| `backend/services/mission_control.py` | Uptime via `perf_counter` (×4 sites) |
| `backend/model_intelligence/benchmark_scheduler.py` | `print()` → `logger.warning(exc_info=True)` |
| `backend/storage/database_manager.py` | `print()` → `logger.error(exc_info=True)` |
| `backend/skills/routes.py`, `backend/tools/routes.py`, `backend/skills/dependency_resolver.py` | 5 noms d'annotation indéfinis importés |
| `backend/sds/runtime.py` | `RuntimeInterface` sous `TYPE_CHECKING` (préserve l'acyclicité) |
| `backend/sds/routes.py` | Suppression d'un ré-import masquant |

### Frontend (7)

| Fichier | Correctif |
|---|---|
| `frontend/package.json` | +6 dépendances manquantes, −1 inutilisée (`reactflow`) |
| `frontend/src/app/{agents,execution,runtimes}/page.tsx` | API réelle de `react-resizable-panels` |
| `frontend/src/app/dashboard/layout.tsx` + `page.tsx` | Import par défaut, `{children}` rendu, contrat `PageProps` respecté |
| `frontend/src/components/runtimes/RuntimeEvents.tsx` | Hook correct, `connectionState` dérivé, normalisation d'événement, `title` valide |
| `frontend/src/hooks/use-websocket.ts` | `useRef(undefined)` |
| `frontend/src/types/mission-control.ts` | Union `severity` alignée sur le backend |
| `frontend/src/__tests__/cockpit.test.ts` | 37 `require()` → `await import()` |

### Tests & documentation (5)

| Fichier | Correctif |
|---|---|
| `tests/api/test_mission_control_api.py` | Suppression du `receive_text()` bloquant — **débloque la CI** |
| `tests/architecture/test_foundation_sanity.py` | Skip du bit d'exécution POSIX sous Windows |
| `backend/tests/conftest.py` | Host MCP `mcp-test` → `localhost:8000` (protection DNS-rebinding du SDK) — **débloque 24 tests** |
| `CHANGELOG.md` | 74 backticks échappés |
| `package.json` | Version Next.js corrigée (16 → 15) |

### Vérification finale

```
tests/                    2366 passés, 1 ignoré, 0 échec     (avant : 10 échecs, 2 erreurs, 1 blocage)
backend/tests/             751 passés, 16 échecs             (avant : 645 passés, 24 échecs, 45 erreurs)
frontend vitest             65 passés, 0 échec               (avant : 37 échecs)
frontend tsc --noEmit        0 erreur                        (avant : 72 erreurs)
frontend next build         14 pages générées                (avant : échec)
pyflakes undefined names     0                               (avant : 9)
application                  démarre, 182 chemins            (avant : NameError, 70 chemins)
suite smoke E2E             16 échecs en 28 s                (avant : 30 échecs en 412 s)
```

---

## 14. Décision finale

### Score global : **65 / 100**

| Axe | Score |
|---|---|
| Architecture | 60 |
| Backend | 66 |
| Frontend | 58 |
| Runtime | 70 |
| Agents | 65 |
| Mémoire | 72 |
| Sécurité | 68 |
| Production | 60 |
| Cockpit | 55 |
| Documentation | 64 |
| Performance | 80 |
| Dette technique / Tests | 68 |

### Décompte des anomalies

| Classe | Trouvées | Corrigées | **Restantes** |
|---|---|---|---|
| 🔴 **Critiques** | 11 | 6 | **5** |
| 🟠 **Majeures** | 23 | 10 | **13** |
| 🟡 **Mineures** | 12 | 6 | **6** |
| ⚪ **Cosmétiques** | 6 | 3 | **3** |
| **Total** | **52** | **25** | **27** |

**Améliorations recommandées (non bloquantes) : 12** — supprimer les 321 imports inutilisés, les 19 modules orphelins et les 15 composants frontend morts ; consolider les 6 duplications ; ajouter `eslint` ; borner les 37 collections ; enrichir les `response_model` ; élargir les topics de l'`EventHub` ; documenter les intégrations Alexandrie/KlaatCode/Oh My Pi/KTransformers ; corriger `pytest.ini` ; ajouter des en-têtes de version sémantique au CHANGELOG ; compléter les entrées HOS-059 → 065B ; retirer la consigne périmée de `frontend/AGENTS.md`.

### Les 5 anomalies critiques restantes

| # | Anomalie | Pourquoi elle n'a pas été corrigée ici |
|---|---|---|
| **C-1** | **Aucun composition root.** Aucun service (`AgentSupervisor`, `MemoryManager`, `PolicyEngine`, `GraphExecutor`, `WorkspaceManager`, `ApprovalManager`, `TaskPlanner`, `RuntimeOrchestrator`) n'est instancié au démarrage. Les points d'injection `create_*_routes(service)` et `configure(...)` existent et ne sont jamais appelés. Résultat : 16 endpoints en `503`, et l'orchestrateur runtime tourne avec des callbacks de scoring nuls. | Instancier et ordonner 8+ services avec leurs dépendances, leurs chemins de stockage, leur cycle de vie et leur arrêt propre **est** le travail d'assemblage manquant. Ce n'est ni localisé ni sans risque, et cela suppose des décisions d'architecture (ordre d'initialisation, propriété des ressources, comportement en cas d'échec partiel). |
| **C-2** | **9 sous-systèmes sans surface HTTP.** `autonomous`, `conversation`, `evolution`, `execution`, `explainability`, `model_intelligence`, `security`, `skills`, `tools` exposent des fonctions `handle_*(...)` sans `APIRouter`. Ils ne sont pas montables. Security Center, Skills Center, Tools Center, Evolution Center, Autonomous Center, Conversation Center et Model Intelligence Center n'ont donc **aucun backend joignable**. | Écrire 9 couches d'adaptation HTTP (routage, validation, codes de statut, sérialisation) est du développement de fonctionnalité, explicitement hors mandat. |
| **C-3** | **Contrat frontend/backend divergent.** `services/client.ts` appelle 97 endpoints sur `/api/v1` ; `lib/*` en appelle d'autres sur `/api/hermes-os`. Après câblage une partie répond, le reste est en 404 — précisément les endpoints de C-2 (`/execution/*`, `/skills/*`, `/tools/*`, `/mcp/*`, `/statistics`, `/version`). | Dépend de C-2. Unifier les deux clients suppose de choisir un préfixe canonique : décision d'architecture. |
| **C-4** | **14 Centers du Cockpit inatteignables.** 8 ne sont pas importés par `cockpit-shell.tsx` ; l'**Installer Center n'existe pas** dans le dépôt alors qu'il est annoncé comme livré. | Créer un Center absent est du développement de fonctionnalité. Câbler les 8 autres n'a pas de sens tant que C-2 laisse leur backend injoignable. |
| **C-5** | **Surface MCP injoignable en déploiement.** `FastMCP` (mcp 1.26.0) n'autorise par défaut que `Host: 127.0.0.1:*`, `localhost:*`, `[::1]:*`. Vérifié : `hermes-backend:8000` (nom de service du `docker-compose`) → **421**, `hermes.local` → **421**, `localhost` sans port → **421**. | Choisir la liste d'hôtes de confiance est une décision de configuration de sécurité (et dépend de la topologie de déploiement retenue), pas un correctif mécanique. Remède : passer `transport_security=TransportSecuritySettings(allowed_hosts=[…])` à `FastMCP` dans `backend/mcp_server/server.py`, et **borner `mcp` dans `requirements.txt`** (**M-13**). |

### Verdict : 🔴 **NO GO**

**Justification.**

Le critère d'une Release Candidate n'est pas « le code existe et les tests passent », c'est « le produit assemblé fait ce qu'il annonce ». Les correctifs de cet audit ont franchi la première marche, et elle était indispensable : l'application démarre, le frontend compile, la CI se termine, 3 117 tests passent, 182 chemins sont servis au lieu de 70, la suite end-to-end est 15× plus rapide. C'est un progrès réel et substantiel.

Mais il reste un écart de **nature**, pas de degré, entre le périmètre annoncé et ce qui fonctionne :

- Sur les 29 HOS listés comme livrés, **7 sous-systèmes sont des îlots totalement déconnectés** (fan-in 0 *et* fan-out 0) : Autonomous Core, Conversation, Evolution, Model Intelligence, Voice, Logging, Storage.
- **9 sous-systèmes n'ont aucune surface HTTP** : 7 Centers du Cockpit sur 23 n'ont pas de serveur en face.
- **16 endpoints** parmi ceux qui existent répondent `503 not initialized`.
- Le **temps réel du Cockpit est cassé sur deux plans indépendants** (26/28 topics filtrés par l'`EventHub` ; dispatch WS depuis un thread étranger), ce qui vide de sens l'exigence « WebSocket temps réel ».
- La **surface MCP est injoignable** dans le déploiement Docker documenté.
- La couche API **validée** (HOS-028) n'est pas celle qui est montée ; celle qui répond accepte `POST /missions {}` avec un `200` et renvoie `500` sur une énumération invalide.

Passer en validation terrain avec ces points signifierait exposer à des testeurs un Cockpit dont la moitié des écrans n'a pas de serveur, un flux temps réel qui perd silencieusement la quasi-totalité de ses événements, et un MCP inaccessible dès qu'on quitte `localhost`. Le retour terrain serait dominé par ces manques d'assemblage et n'apprendrait rien sur la qualité réelle des sous-systèmes — laquelle est bonne.

**Ce NO GO porte sur l'assemblage, pas sur la conception.** Aucune des 5 anomalies critiques restantes n'exige de réécrire un sous-système : toutes exigent de les brancher.

### Chemin le plus court vers un GO

| Ordre | Action | Effort | Lève |
|---|---|---|---|
| 1 | Écrire le composition root dans le lifespan de `backend/main.py` : instancier les 8 services et appeler les `create_*_routes(...)` / `configure(...)` **déjà prévus par le code**. `IntegrationManager` (HOS-056) est le point d'ancrage naturel. | 1–2 j | **C-1** (16 × 503 → 200, et 16 échecs de tests → 0) |
| 2 | Ajouter un `APIRouter` aux 9 modules `handle_*` — les fonctions existent, c'est du mapping HTTP, pas de la logique métier. | 2–3 j | **C-2**, débloque C-3 et C-4 |
| 3 | Passer `transport_security` avec les hôtes de déploiement à `FastMCP` ; borner `mcp<2` dans `requirements.txt`. | 0,5 j | **C-5**, **M-13** |
| 4 | Élargir `EVENT_TYPES` de l'`EventHub` aux 28 topics RAL ; capturer la boucle avec `asyncio.get_running_loop()` à la connexion et dispatcher via `run_coroutine_threadsafe`. | 0,5 j | **M-2a**, **M-2b** — rend le temps réel réel |
| 5 | Unifier les deux clients frontend sur un préfixe unique ; router les 8 Centers orphelins ; décider du sort de l'Installer Center (implémenter ou retirer du périmètre annoncé). | 1–2 j | **C-3**, **C-4** |
| 6 | Corriger `pytest.ini` (`testpaths = backend/tests tests`) pour que la CI exécute réellement les 3 133 tests. | 5 min | **M-9** |
| 7 | Modèles Pydantic sur les 19 corps `dict = Body(...)` — les modèles existent déjà dans `api/models.py` pour les missions. | 1–2 j | **M-1** |
| 8 | Porter ou retirer `test_ktransformers_integration.py` ; supprimer les 5 modules KT morts. | 0,5 j | **M-4**, **M-5** |
| 9 | Resynchroniser `ROADMAP.md`, compléter `CHANGELOG.md` (HOS-059 → 065B). | 0,5 j | Documentation |

Les étapes 1 à 4 suffisent à transformer ce NO GO en GO : elles ne créent aucune fonctionnalité, elles branchent ce qui existe déjà.

---

## Annexe A — Reproduire cet audit

```bash
# Dépendances absentes de l'environnement fourni
python -m pip install pytest==8.3.2 pytest-asyncio==0.24.0 "sqlalchemy>=2.0" "chromadb>=0.5" pytest-timeout pyflakes

# Backend
python -m pytest tests --timeout=180 --timeout-method=thread   # attendu : 2366 passés
python -m pytest --timeout=300 --timeout-method=thread          # attendu : 751 passés, 16 échecs (C-1)
python -m pyflakes backend/ | grep "undefined name"             # attendu : vide

# Surface HTTP réellement servie
python -c "from backend.main import create_app; print(len({r.path for r in create_app().routes}))"

# Frontend
cd frontend && pnpm install && npx tsc --noEmit && npx next build && npx vitest run
```

## Annexe B — Index des 27 anomalies restantes

| Réf. | Sév. | Titre | Emplacement |
|---|---|---|---|
| C-1 | 🔴 | Aucun composition root | `backend/main.py` (lifespan) |
| C-2 | 🔴 | 9 sous-systèmes sans `APIRouter` | `{autonomous,conversation,evolution,execution,explainability,model_intelligence,security,skills,tools}/routes.py` |
| C-3 | 🔴 | Deux clients API divergents | `frontend/src/services/client.ts`, `frontend/src/lib/*` |
| C-4 | 🔴 | 14 Centers inatteignables, Installer Center absent | `frontend/src/components/cockpit-shell.tsx`, `frontend/src/features/` |
| C-5 | 🔴 | `/mcp` → 421 hors localhost (Docker, nginx, LAN) | `backend/mcp_server/server.py` |
| M-1 | 🟠 | Validation absente, 500 au lieu de 422 | 19 routes, 7 modules |
| M-2a | 🟠 | Dispatch WS depuis un thread étranger | `api/router.py:306`, `runtime/events/routes.py:57` |
| M-2b | 🟠 | `EventHub` rejette 26/28 topics | `core/event_hub.py:37` |
| M-4 | 🟠 | Module de tests KT mort (couverture perdue) | `tests/architecture/test_ktransformers_integration.py` |
| M-5 | 🟠 | 5 prototypes KT aux imports cassés | `runtime/ktransformers/kt_*.py` |
| M-6 | 🟠 | 5 adaptateurs testés mais jamais câblés | `model_intelligence/model_*_adapter.py`, `policy/approval_explainer.py` |
| M-7 | 🟠 | 6 duplications fonctionnelles | §12.2 |
| M-8 | 🟠 | `_missions` non borné, sans verrou, non persisté | `mission/routes.py:21` |
| M-9 | 🟠 | `pytest` n'exécute que 24 % des tests | `pytest.ini:4` |
| M-10 | 🟠 | `eslint` absent, `pnpm lint` cassé | `frontend/package.json` |
| M-11 | 🟠 | `bus.publish` monkey-patché | `runtime/events/routes.py:63` |
| M-12 | 🟠 | 7 îlots totalement isolés | §1.2 |
| M-13 | 🟠 | `mcp>=1.0` sans borne haute (cause de C-5) | `backend/requirements.txt` |
| mn-1 | 🟡 | 59 `except Exception: pass` | backend |
| mn-4 | 🟡 | 15 composants frontend morts | `frontend/src/{components,features}` |
| mn-5 | 🟡 | Deux types `RuntimeEvent` | frontend |
| mn-8 | 🟡 | `agents/atlas.py` mort | backend |
| mn-9 | 🟡 | Tâche `sse_starlette` pendante à l'arrêt | backend |
| mn-10 | 🟡 | `chromadb`/`sqlalchemy` durs à l'import de `main` | `agents/echo.py` → `memory/semantic.py` |
| cos-1 | ⚪ | 321 imports inutilisés, 20 locales, 7 f-strings | backend |
| cos-3 | ⚪ | `AGENTS.md` pointe vers un répertoire inexistant | `frontend/AGENTS.md` |
| cos-6 | ⚪ | CHANGELOG : trous HOS-059→065B, ordre non monotone, pas de version sémantique ; ROADMAP désynchronisée | `CHANGELOG.md`, `ROADMAP.md` |
