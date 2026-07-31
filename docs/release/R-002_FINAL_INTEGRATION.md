# R-002 — Final Integration & Production Wiring

**Date** : 30 juillet 2026
**Nature** : intégration uniquement — aucune fonctionnalité nouvelle, aucun moteur nouveau, aucune architecture nouvelle
**Point de départ** : conclusions de l'audit RC3 (`docs/release/HERMES_OS_RC3_AUDIT.md`)

## Résumé

RC3 avait établi que les sous-systèmes de Hermes existent, sont testés et fonctionnent
individuellement, et que le problème restant était exclusivement un problème d'assemblage.
R-002 a raccordé ce qui ne l'était pas.

Le fil conducteur : **des coutures d'injection présentes, complètes, et jamais appelées.**
`GraphExecutor` acceptait un `execute_node` et personne ne le fournissait. `register_klaatcode()`
documentait son propre site d'appel et ce site n'existait nulle part. `AgentSupervisor` et
`AgentRegistry` ne s'étaient jamais rencontrés. `RuntimeOrchestrator.register_runtime()`
n'était appelé par personne. Aucune de ces corrections n'a demandé une ligne de logique métier
nouvelle — seulement de brancher des composants existants.

| | Avant R-002 | Après R-002 |
|---|---|---|
| Pipelines de mission | **2 concurrents** | **1 partagé** |
| `POST /api/v1/missions` | `nodes: 0`, `/start` bascule un libellé | DAG de 7 nœuds, 7 exécutés, 100 % |
| Agents enregistrés | 0 | **10** |
| Outils enregistrés | 0 | **16** |
| Serveurs MCP | 0 | **2** |
| Runtimes vus par le coordinateur | 0 | 1 |
| Runtimes vus par l'orchestrateur | 0 | 1 |
| Centres du Cockpit avec données fabriquées | 8 | **0** |
| Services construits | 32 | **34** |
| Tests backend | 3 306 | **3 321**, 0 échec |

---

## Phase 1 — Fusion des moteurs de mission

### Le problème

Deux surfaces, deux implémentations disjointes :

* `/api/v1/autonomous` → `AutonomousEngine` → `AutonomousOrchestrator`, qui **construisait son
  propre** `MissionExecutor` et son propre `RealTaskExecutor` à l'instanciation ;
* `/api/v1/missions` → `GraphExecutor` (le DAG HOS-041), dont le point d'injection
  `execute_node` n'était fourni par personne et retombait donc sur sa valeur par défaut :

  ```python
  self._execute_node = execute_node or (lambda n: True)
  ```

  — « chaque nœud réussit, sans rien faire ». Pire, `execute_step()` n'était appelé par aucune
  route : `POST /missions/{id}/start` se contentait de `start_mission()`, qui bascule le statut
  en `running` et annonce les nœuds racines. Une mission créée par la voie documentée restait
  à 0 % indéfiniment, **sans message d'erreur**.

Le service nommé `mission_executor` dans le composition root construisait en réalité un
`GraphExecutor` ; le vrai moteur de tâches n'était pas un service du tout.

### Le raccordement

1. **`task_executor` et `execution_engine` deviennent des services** du composition root
   (`service_registry.py`). Il n'existe plus qu'un moteur de tâches dans le processus.
2. **`AutonomousEngine` reçoit `mission_executor`** et le transmet à son orchestrateur, au lieu
   d'en fabriquer un.
3. **`backend/mission/node_execution.py`** (nouveau, 90 lignes) : l'adaptateur qui traduit un
   `MissionNode` en `TaskExecution` et déroule la séquence `prepare()` → `execute_task()` —
   exactement celle qu'utilise `AutonomousOrchestrator`. Il n'exécute rien lui-même. Si aucun
   moteur n'est câblé, il renvoie **échec**, pas succès.
4. **Le Mission Planner est invoqué** par `POST /missions` quand l'appelant ne fournit pas de
   graphe : `planner.plan(PlanningRequest(...))` puis `planner.build_mission(...)`. Le planner
   était construit (il figurait parmi les 32 services) et le routeur ne le référençait jamais.
   L'injection se fait depuis le *route binder du planner*, pas celui des missions : les binders
   s'exécutent au fil de la construction et le planner est bâti après l'exécuteur de graphe dont
   il dépend — l'injecter dans l'autre sens créerait un cycle `mission_executor ↔ mission_planner`.
5. **`POST /missions/{id}/start` déroule le DAG** jusqu'à un état terminal, avec un plafond de
   passes documenté.

### Preuve

```
POST /api/v1/missions   → nodes: 7, edges: 6, planned: true, validation_issues: []
POST /missions/{id}/start → status: completed, nodes_executed: 7, progress_pct: 100.0
```

Et la preuve que le travail a réellement eu lieu, mesurée sur le compteur du moteur lui-même :

```
114,3 s au chronomètre pour 7 nœuds
task_executor: executions=7, failures=0, avg_duration_ms=16331.5,
               total_tokens=1881, simulated=false
```

Sept inférences Ollama véritables, 1 881 jetons réellement produits.

L'identité est vérifiée par test : `autonomous.orchestrator.mission_executor is
container.get("execution_engine")`.

---

## Phase 2 — Bootstrap complet

### Ce qui était vide

Un Hermes intégralement assemblé servait `agents: 0`, `tools: 0`, `skills: 0`,
`mcp/servers: 0`, et un `AgentCoordinator` qui affectait les tâches contre quatre catalogues
vides (`agents_registered: 0`).

### Ce qui a été branché — et d'où viennent les données

`backend/core/bootstrap/registry_seeding.py` (nouveau). **Aucune ressource n'est inventée.**
Chaque entrée provient d'une source déclarée et vérifiable :

| Registre | Source réelle | Résultat |
|---|---|---|
| Agents | les 10 entrées `enabled: true` de `config/agents.yaml`, déjà instanciées par `AgentRegistry` | **10** |
| Outils | `get_tool_definitions()` des adaptateurs MCP KlaatCode (7) et Oh My Pi (9) | **16** |
| MCP | `register_klaatcode()` — la fonction existante, dont la docstring montrait le site d'appel — plus l'équivalent Oh My Pi | **2 serveurs, 7 outils MCP** |
| Runtimes | ce que le registre SDS a réellement démarré | **1** |
| Modèles | `config/models.yaml`, déjà chargé | 6 |
| Compétences | **rien** | **0** |

**Sur les compétences.** Le dépôt ne contient aucune instanciation de `SkillDefinition` — zéro
occurrence dans tout `backend/`. Le registre de compétences est donc légitimement vide, et le
remplir aurait signifié fabriquer des capacités que le coordinateur aurait ensuite sélectionnées.
Il est rapporté à zéro, avec une note explicite dans le rapport de bootstrap.

### Trois défauts découverts en branchant

1. **Noms d'outils corrompus.** `KlaatCodeAction` est un `(str, Enum)`, et sous Python 3.11
   `str()` d'un tel membre rend `KlaatCodeAction.ANALYZE_PROJECT`, pas sa valeur. Les définitions
   interpolaient `f"klaatcode.{name}"` et produisaient
   `klaatcode.KlaatCodeAction.ANALYZE_PROJECT`. Personne ne l'avait vu **parce que ces
   définitions n'étaient enregistrées nulle part**. Corrigé dans les deux adaptateurs
   (`getattr(name, "value", str(name))`) ; les noms publics sont désormais
   `klaatcode.analyze_project`, `ohmypi.lsp_edit`.
2. **Double enregistrement.** Les registres d'outils et MCP sont des globales de module qui
   survivent à une application : un processus qui en construit deux (chaque exécution de tests)
   enregistrait tout deux fois — 23 outils pour 16 noms distincts, 2 serveurs KlaatCode. Le
   seeding est désormais idempotent par nom, et un test le verrouille.
3. **Mauvais registre MCP.** Le premier branchement enregistrait dans une instance fraîche de
   `MCPRegistry` alors que `GET /mcp/servers` sert la globale de `backend.tools.routes`. Le
   seeding réussissait et l'endpoint affichait toujours zéro.

### Ordonnancement

Le registre de runtimes SDS est peuplé par le `lifespan`, donc **après** la construction du
composition root. `HermesBootstrap.seed_runtime_registries()` est rappelé depuis le `lifespan`
une fois les runtimes installés, sinon le coordinateur conservait `runtimes_available: 0` pour
la durée du processus.

---

## Phase 3 — Cockpit 100 % réel

Huit composants affichaient des données fabriquées. **Il n'en reste aucun.**

| Composant | Ce qui était affiché | Ce qu'il affiche maintenant |
|---|---|---|
| `autonomous-center` | `MOCK_GOAL`, `MOCK_SESSION`, `MOCK_DECISIONS`, `MOCK_TIMELINE` : une mission inventée sur un runtime « ktransformers », quatre décisions écrites à la main, une frise de 8 étapes toutes vertes, et une carte « Pipeline Flow » avec cinq ✓ codés en dur (Security Validation ✓, Policy Check ✓…) vrais quoi qu'il arrive. Les boutons Start/Pause/Cancel étaient inertes. | `/api/v1/autonomous/*` en entier : objectif réel, décisions réelles avec leurs justifications, frise réelle, boucle d'apprentissage réelle, et des contrôles qui appellent vraiment pause/resume/cancel |
| `model-intelligence-center` | `MOCK_MODELS` (5 modèles inventés), `MOCK_DECISIONS` ; « Recommend » dormait `600 + Math.random() * 400` ms puis renvoyait `MOCK_DECISIONS[0]` ; « Run Full Benchmark » dormait 1 500 ms sans rien faire ; l'onglet Optimizer était du texte statique | `/models`, `/models/ranking`, `/models/recommend`, `/models/benchmarks` ; l'Optimizer est dérivé du classement réel |
| `deployment-center` | Un « NVIDIA A100 80GB », 81 920 Mo de VRAM, un « AMD EPYC (8C/16T) » et « Linux 6.2.0 » — sur n'importe quelle machine ; 12 composants sains inventés ; 6 services inventés ; 3 sauvegardes inventées ; « Create backup » dormait 1 500 ms, ajoutait une entrée de `Math.random() * 20 + 30` Mo et annonçait **« Backup created successfully »** pour une opération qui n'avait pas lieu | `/system/health`, `/system/assembly`, `/system/statistics`, `/runtime/resources`. L'onglet Sauvegardes indique qu'aucune API de sauvegarde n'existe |
| `conversation-center` | `mockSessionId` tiré de `Math.random()`, une fonction `generateMockResponse()` de 78 lignes qui associait des mots-clés à des réponses françaises pré-écrites avec des confiances inventées, et des délais de 800–1 400 ms pour simuler la réflexion | `/conversation/start`, `/message`, `/approve`, `/cancel` — classification d'intention et validation réelles |
| `code-intelligence-center` | `MOCK_STATUS` (142 tâches, 92,3 % de réussite, répartition 68/53/21) et `MOCK_TASK_TYPES` ; cliquer exécutait un bloc `// Simulate routing` côté navigateur puis éteignait un spinner après 800 ms | Les deux fournisseurs réels via leurs propres endpoints, **et l'énoncé explicite** qu'aucune route `/api/v1/code-intelligence` n'existe (voir « Ce qui n'a pas été fait ») |
| `klaatcode-panel` | 7 outils écrits à la main ; badge `variant="success"` « MCP Connected » **inconditionnel** | `/klaatcode/capabilities` et `/klaatcode/status` ; le badge distingue chargement / erreur / lié / installé-non-lié / absent |
| `ohmypi-panel` | 9 outils écrits à la main | `/ohmypi/capabilities` |
| `RuntimeHealth` | Un graphe de 10 valeurs `Math.random() * 100` sous des étiquettes « -50s … -5s » : il ressemblait à un historique de latence et n'était que du bruit | La latence réelle par runtime, avec la mention qu'aucune série historique n'est exposée |

### Deux dérives de contrat révélées

Les données fabriquées satisfaisaient des types qui ne correspondaient pas à l'API, ce qui
rendait la dérive invisible pour `tsc` :

1. **`ResourceStatus`** déclarait `cpu_percent`, `ram_total_gb`, `vram_total_gb`, `gpu_temp_c`
   — **aucun** de ces champs n'est renvoyé par `/api/v1/runtime/resources`. Conséquence : les
   **neuf** jauges du Centre Runtime lisaient `undefined` et retombaient silencieusement sur
   zéro. Corrigé, et le Centre Runtime réécrit sur les champs réels.
2. **`OhMyPiCapability`** déclarait `category`, `requires_workspace`, `requires_sandbox` —
   jamais envoyés — et omettait `requires_lsp`, qui l'est. **`OhMyPiStatus`** était déclaré à
   plat alors que l'endpoint enveloppe la charge utile dans `{"status": {...}}`.

---

## Phase 4 — Participation réelle des composants

Sonde : une mission DAG et un objectif autonome, puis on demande à chaque composant si **ses
propres compteurs** ont bougé. Aucun composant n'est crédité au motif d'avoir été construit.

**8 / 15 participent** : Autonomous Engine, Execution Engine, Task Executor, Mission Planner,
Memory, EventBus, Security, Oh My Pi.

**7 ne bougent pas**, avec des causes distinctes :

| Composant | Cause | Statut |
|---|---|---|
| Runtime Orchestrator | `register_runtime()` n'était appelé par personne : `known_runtimes: 0` | **Branché** (`known_runtimes: 1`), mais toujours pas *consulté* : le choix du runtime se fait via l'affectation du coordinateur, pas via `orchestrator.select()`. Y toucher changerait le chemin de sélection — au-delà d'un branchement |
| Model Intelligence | Ses trois adaptateurs (`ModelAutonomousAdapter`, `ModelEvolutionAdapter`, `ModelMemoryAdapter`) ne sont **construits nulle part** dans le dépôt | Signalé, non branché : les appeler depuis le chemin d'exécution ajoute un flux de données |
| Knowledge Graph, Alexandrie | Les missions n'alimentent pas le graphe ni ne lient de documents | Signalé — ce serait un flux nouveau |
| Policy | Les règles existent mais ne sont pas évaluées pendant une mission | Signalé |
| Evolution | Reçoit bien `ingest_metrics` via la boucle mémoire ; `total_proposals` ne monte que s'il détecte quelque chose | Comportement normal |
| KlaatCode | Non sollicité par ces deux missions particulières | Normal |

---

## Phase 5 — Faux positifs

Balayage de tout `backend/` sur `TODO`, `FIXME`, `placeholder`, `mock`, `fake`, `dummy`,
`simulated`, `stub`, `hardcoded success`, `random success`, `random duration` :
**84 occurrences dans 33 modules de production**.

La grande majorité est légitime et a été conservée : les moteurs de simulation HOS-039
(`backend/runtime/simulation/*`), l'état `SIMULATED` du cycle de vie des propositions
d'évolution, la valeur `TaskStatus.TODO`, la substitution `$steps.<node>.<key>` du moteur de
workflows, les docstrings décrivant les doublures de test, et les docstrings R-001 qui
décrivent le comportement *supprimé*.

**Quatre fabrications réelles ont été corrigées :**

1. **Trois agents annonçaient un succès sans avoir travaillé.** `KlaatCodeAgent`,
   `OhMyPiAgent` et `CodeIntelligenceAgent` retombaient, quand aucun adaptateur MCP n'était lié,
   sur `success = True` avec `{"status": "simulated"}` :

   ```python
   else:
       # Fallback: simulate execution for CI / no KlaatCode
       data = {"status": "simulated", "action": mcp_action}
       success = True
   ```

   Une mission tournant sans ces agents installés déclarait donc **chaque tâche réussie**. Les
   trois signalent désormais un échec et la raison.

2. **Durée fabriquée dans un rapport d'exécution.** `ExecutionReport.total_duration_ms` valait
   `42.0 * progress["total"]` — une constante par tâche, annotée `# simulated`. Ce rapport est
   passé directement à `self._feedback.analyze()` : **la boucle de rétroaction apprenait sur un
   nombre inventé.** Elle somme maintenant les durées mesurées, et `runtimes_used`,
   `skills_used`, `tools_used`, codés en dur à vide, sont renseignés depuis les affectations
   réelles.

3. **Rapports mélangés entre missions.** En corrigeant le point 2, la somme portait sur tout le
   registre du planificateur, partagé par toutes les missions du processus. `prepare()`
   mémorise désormais les tâches de son exécution et `finalize()` ne rapporte que celles-là.

4. Les données fabriquées du Cockpit (Phase 3), dont deux simulations de latence par
   `Math.random()`.

---

## Phase 6 — Tests

`tests/integration/test_r002_integration.py` — **15 tests**, tous verts en 8,7 s. Ils vérifient
les propriétés que R-002 visait, contre l'application réellement assemblée :

* un seul moteur d'exécution, partagé — vérifié par identité d'objet, et le crochet
  `execute_node` du DAG est bien lié (pas le `lambda n: True`) ;
* `task_executor` et `execution_engine` sont des services du composition root ;
* tous les registres du Cockpit sont peuplés, et les agents enregistrés sont **ceux déclarés**
  dans `config/agents.yaml` ;
* aucun nom d'outil ne contient de `repr` d'énumération ;
* le seeding est idempotent quand un second app est construit dans le même processus ;
* une mission créée par HTTP est décomposée en DAG **et exécutée** jusqu'à 100 % ;
* le graphe expose ce que chaque nœud a réellement fait ;
* le compteur du moteur bouge — pour les deux surfaces ;
* les événements de cycle de vie atteignent un abonné ;
* la durée rapportée est mesurée, et la constante de 42 ms n'est pas revenue.

Ces tests remplacent uniquement l'appel HTTP sortant vers Ollama (sept inférences réelles
prennent deux minutes, ce n'est pas un budget de test). Planner, DAG, ordonnanceur,
coordinateur, validateur et bus d'événements sont réels.

### Des tests qui verrouillaient le défaut

Corriger le point 1 de la Phase 5 a fait échouer **20 tests existants** : ils construisaient les
agents nus et affirmaient que l'exécution réussissait — c'est-à-dire qu'ils vérifiaient
précisément le succès fabriqué. Plutôt que d'annuler la correction, `tests/support/stub_agents.py`
fournit un adaptateur qui *répond réellement*, de sorte que l'assertion devient « étant donné
quelque chose qui exécute, l'exécution réussit ». Le repli de production continue de signaler
un échec. C'est la même convention que `tests/support/fake_inference`.

---

## Phase 7 — Nettoyage

Effectué : imports morts des fichiers touchés par R-002 (`Query`, `AutonomousReport`,
`ExecutionTimeline`, `AgentAssignment`), `import random` mort et docstring périmée dans
l'orchestrateur, 78 lignes de conversation simulée, 68 + 58 lignes de capacités fabriquées,
les constantes `MOCK_*` des huit composants.

**Non effectué, et c'est à signaler** : `pyflakes` relève **340 avertissements dans le code de
production**, dont **314 imports inutilisés** — aucun dans un `__init__.py`, donc ce ne sont pas
des ré-exports délibérés. Ni `ruff` ni `autoflake` ne sont installés dans cet environnement, et
modifier 314 sites à la main sans outil de vérification présente un rapport risque/bénéfice
défavorable. La remédiation sûre est d'ajouter `ruff` aux dépendances de développement et de
lancer `ruff check --select F401 --fix` avec la suite de tests comme garde-fou. **Coût estimé :
0,5 j.**

---

## Ce qui n'a pas été fait, et pourquoi

R-002 interdit absolument les fonctionnalités nouvelles. Les points suivants relèvent du
développement, pas du branchement :

| Point | Pourquoi c'est hors périmètre | Coût estimé |
|---|---|---|
| **API Code Intelligence** | Aucune route `/api/v1/code-intelligence`, aucun service `code_intelligence` construit. Le Centre affiche désormais les deux fournisseurs réels et énonce le manque au lieu de le combler par une simulation | 3–4 j |
| **API KTransformers / Knowledge Graph / Model Intelligence** | Préfixes annoncés sans aucune route. Les capacités existent côté backend mais ne sont pas exposées | 3–5 j |
| **Adaptateurs Model Intelligence** | Les trois classes ne sont construites nulle part. La Phase 7 demande de supprimer les adaptateurs inutilisés, mais supprimer trois modules non triviaux est irréversible et ils peuvent être destinés à un branchement ultérieur : **signalés pour décision** plutôt que supprimés | 0,5 j (suppression) · 2 j (branchement) |
| **Consultation du Runtime Orchestrator** | Il connaît maintenant les runtimes mais la sélection passe par le coordinateur. Le faire arbitrer changerait le chemin de sélection | 1–2 j |
| **Ordonnancement par priorité** (RC3-14) | `TaskExecution` ne porte pas de priorité ; elle vit sur `ExecutionMeta`. Toujours inerte | 1 j |
| **Persistance des missions** (RC3-15) | `backend/mission/routes.py` conserve les missions dans un dict global non borné. Un plafond silencieux perdrait des missions visibles par l'utilisateur : c'est une décision produit | 1–2 j |
| **Authentification** (RC3-17) | Les 199 routes restent ouvertes | 3–5 j |
| **Instrumentation des 11 services muets** | Un tiers du système ne peut pas être sondé (`unknown — no statistics accessor exposed`) et l'agrégat se déclare quand même `healthy` | 1,5 j |

---

## Vérification

```
services  : 34 / 34 | routers: 30
failures  : {} | router_failures: {}
cycles    : [] | missing: {} | isolated: []
registries: agents=10 tools=16 mcp_servers=2 mcp_tools=7 runtimes=1 skills=0
            coordinator{agents=10 runtimes=1 tools=16} orchestrator_runtimes=1
health    : healthy | healthy=23 unknown=11
routes    : 199 sous /api/v1
```

| Suite | Résultat |
|---|---|
| `pytest tests/ backend/tests/` | **3 321 réussis, 3 ignorés, 0 échec** (9 min 12 s) |
| `tests/integration/test_r002_integration.py` | **15 / 15** (8,7 s) |
| `tsc --noEmit` | **0 erreur** |
| `npm run build` | **succès**, 14 pages statiques |
| `vitest` | **65 / 65** |

Les deux modules de test KTransformers restent non collectables (`KTCache`, `KTKernelWrapper`
absents) — prototypes morts identifiés dès RC1, inchangés.

## Annexe — Fichiers

**Nouveaux** : `backend/mission/node_execution.py`,
`backend/core/bootstrap/registry_seeding.py`, `tests/integration/test_r002_integration.py`,
`tests/support/stub_agents.py`, `tests/integration/conftest.py`.

**Modifiés (backend)** : `core/bootstrap/service_registry.py`, `core/bootstrap/bootstrap.py`,
`main.py`, `mission/routes.py`, `mission/graph_executor.py`, `autonomous/autonomous_engine.py`,
`execution/mission_executor.py`, `agents/specialized/{klaatcode,ohmypi,code_intelligence}/*_agent.py`,
`tools/connectors/klaatcode/klaatcode_mcp_adapter.py`,
`tools/connectors/oh_my_pi/ohmypi_mcp_adapter.py`.

**Modifiés (frontend)** : `services/client.ts`, `hooks/use-api.ts`, `types/hermes.ts`,
`features/autonomous/autonomous-center.tsx`, `features/models/model-intelligence-center.tsx`,
`features/deployment/deployment-center.tsx`, `features/conversation/conversation-center.tsx`,
`features/code-intelligence/code-intelligence-center.tsx`,
`features/runtime/runtime-center.tsx`, `features/tools/{klaatcode,ohmypi}-panel.tsx`,
`components/runtimes/RuntimeHealth.tsx`.

## Commandes

```bash
python -m pytest tests/integration/test_r002_integration.py -q -p no:randomly
```

```bash
python -m pytest tests/ backend/tests/ -q --timeout=600 -p no:randomly --ignore=tests/architecture/test_ktransformers.py --ignore=tests/architecture/test_ktransformers_integration.py
```

```bash
cd frontend && npx tsc --noEmit && npm run build && npx vitest run
```
