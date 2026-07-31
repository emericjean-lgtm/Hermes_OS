# HERMES OS — Audit final « Release Candidate 3 »

**Date** : 30 juillet 2026
**Auditeur** : audit logiciel indépendant (posture adverse)
**Périmètre** : 489 modules backend (79 818 lignes), 102 sources frontend (14 040 lignes), 130 fichiers de tests
**Hypothèse de départ imposée** : *le système prétend être terminé ; il faut prouver qu'il ne l'est pas.*

## Méthode

Aucun résultat de ce rapport ne provient d'un test existant, du `CHANGELOG` ou du `ROADMAP`.
Chaque constat vient d'une exécution réelle :

- application assemblée par le vrai `create_app()`, cycle `lifespan` exécuté (`TestClient` en gestionnaire de contexte) ;
- inférence réelle via Ollama (une mission mesurée à 19 522 ms) ;
- table de routage énumérée depuis `app.routes`, pas depuis la documentation ;
- charge et mémoire mesurées par `tracemalloc` + `perf_counter` (jamais `time.monotonic()`, dont la granularité est de 15,6 ms sous Windows) ;
- points chauds localisés par `cProfile` en régime stationnaire, pas par lecture de code.

Les seuls doublures utilisées sont `tests/support/fake_inference.py`, qui remplace uniquement
l'appel HTTP sortant vers Ollama pour les mesures de charge (16 min → 0,57 s sur la suite
unitaire). Toutes les vérifications fonctionnelles passent par le vrai chemin d'exécution.

**Trois défauts de sonde de ma part** sont signalés comme tels plus bas (§ Sondes défectueuses)
plutôt que comptés comme défauts produit : c'est une exigence de l'exercice.

---

## 1. Notes par axe

| # | Axe | Note | Justification en une ligne |
|---|-----|------|----------------------------|
| 1 | Architecture & assemblage | **92 / 100** | 32/32 services construits, 30 routeurs montés, 0 cycle, 0 dépendance manquante, 0 service isolé. |
| 2 | Exécution réelle | **78 / 100** | `/autonomous/start` exécute réellement (Ollama, 19,5 s) ; `/missions` n'exécute rien. |
| 3 | Intégrations | **71 / 100** | 28 groupes d'API répondent 200, mais 4 registres sont vides au démarrage et 4 préfixes annoncés n'ont aucune route. |
| 4 | API & contrats | **80 / 100** | 198 couples méthode+chemin cohérents ; une dérive de contrat TS↔API corrigée, une divergence de sémantique de sujet d'événement corrigée. |
| 5 | Cockpit & UX | **58 / 100** | 4 Centres sur 16 affichent encore des données fabriquées ; 5 Centres n'ont aucun hook. |
| 6 | Performance & mémoire | **90 / 100** | Débit désormais **plat** (956 msn/s à 3 600 missions contre 256 avant) ; croissance mémoire 1,4 Kio/mission contre 10,0. |
| 7 | Sécurité | **83 / 100** | Évasion de sandbox corrigée, MCP en JSON-RPC réel avec délais bornés ; pas d'authentification sur l'API. |
| 8 | Robustesse | **79 / 100** | Erreurs de champ traduites en 422 ; la télémétrie ne peut plus faire échouer une mission ; runtime indisponible remonté honnêtement. |
| 9 | Tests & qualité | **85 / 100** | 3 293 tests passent, 0 échec ; 2 modules KTransformers ne s'importent toujours pas ; 13 tests de non-régression RC3 ajoutés. |

**Note globale pondérée : 79 / 100.**

---

## 2. Ce que le système fait réellement

Il faut le dire clairement, parce que c'est le point où RC1 et RC2 échouaient : **le cœur
d'exécution est réel et joignable par HTTP.**

```
POST /api/v1/autonomous/start  {"user_request": "Analyse the authentication module"}
→ 200
  status              : completed
  execution_summary   : "1/1 task(s) completed on ollama in 19522ms"
  decisions           : 4 décisions réelles (agent, runtime, tool, skill)
  timeline            : plan_created → décisions horodatées
```

19 522 ms d'inférence Ollama véritable, un runtime qui a réellement servi, un rapport dérivé
des résultats obtenus. C'est la capacité annoncée, et elle fonctionne.

Le problème de RC3 n'est plus « le système simule » — c'est **« le système sait faire, mais
plusieurs surfaces ne le branchent pas »**.

---

## 3. Anomalies

Criticité : **Critique** (bloque la mise en production) · **Majeure** (fonctionnalité annoncée
inopérante) · **Mineure** (défaut réel, contournable) · **Cosmétique**.
Coût estimé = effort de développement, hors revue et recette.

### 3.1 Anomalies corrigées dans cet audit

| ID | Criticité | Anomalie | Cause racine | Coût |
|----|-----------|----------|--------------|------|
| RC3-01 | **Majeure** | Aucun événement de cycle de vie de mission n'atteignait le bus. 4 des 5 événements (`execution.started`, `.planning`, `.task_started`, `.completed`) étaient enregistrés dans une liste privée et jamais diffusés. Le flux temps réel du Cockpit ne pouvait voir ni le début ni la fin d'une mission. | `MissionExecutor` acceptait `on_event` (« the shared event dispatcher »), le stockait — et ne l'appelait jamais. L'en-tête de section indiquait littéralement « EventBus simulation ». | 0,5 j |
| RC3-02 | **Majeure** | Débit dégradé de 983 à 256 missions/s sur 3 600 missions (facteur 3,8), avec fuite de ~10 Kio par mission jamais libérés. | Six collections du chemin d'exécution croissaient pour la durée de vie du processus, et `get_progress()`/`is_all_done()`/`build_plan()` parcourent chacune leur registre une fois par tâche : le coût devenait O(missions exécutées). `cProfile` : `task_scheduler.py:169` = 374 014 appels de générateur pour 300 missions, 45 % du temps total. | 1,5 j |
| RC3-03 | **Majeure** | `execute_task()` balayait linéairement toutes les tâches jamais enregistrées pour en retrouver une — dans un dictionnaire déjà indexé par `task_id`. | `list(self._scheduler._tasks.values())` puis boucle, au lieu d'un accès direct. Aucun accesseur `get_task()` n'existait. | 0,25 j |
| RC3-04 | **Majeure** | La boucle d'apprentissage autonome était morte : après six missions réussies, le Centre Mémoire affichait toujours `episodic.total = 0`. | Deux bogues empilés : (a) rien n'appelait `set_memory_manager()`, la branche était morte en production ; (b) quand elle s'exécutait, elle passait un `dict` alors que `record_episode()` attend un `EpisodicMemory`, et un `except: pass` nu avalait le `TypeError`. | 0,5 j |
| RC3-05 | **Mineure** | `execution.task_completed` était publié deux fois pour la même tâche après correction de RC3-01 — tout abonné comptait chaque tâche en double. | Deux couches annoncent le même jalon sur le même sujet : `RealTaskExecutor` (fin du travail, avec runtime/modèle/durée/jetons) et `MissionExecutor` (validation réussie). | 0,25 j |
| RC3-06 | **Mineure** | Le panneau KlaatCode affichait un badge `variant="success"` « MCP Connected » **inconditionnellement**, y compris quand rien n'était lié — alors que `/api/v1/mcp/servers` renvoie `count: 0`. | Badge codé en dur, aucun appel au statut réel. | 0,25 j |
| RC3-07 | **Mineure** | Les panneaux KlaatCode et Oh My Pi affichaient 7 et 9 outils écrits à la main, identiques que l'agent soit installé ou non. `klaatcodeClient` et `ohmypiClient` étaient **complets et jamais utilisés** — aucun hook ne les appelait. | Constantes `MOCK_CAPABILITIES` au niveau module ; couche client présente mais non branchée. | 0,5 j |
| RC3-08 | **Mineure** | Dérive de contrat TS↔API sur `OhMyPiCapability` : le type déclarait `category`, `requires_workspace`, `requires_sandbox` — trois champs que l'endpoint n'a jamais envoyés — et omettait `requires_lsp`, qu'il envoie. | Les données fabriquées satisfaisaient le mauvais type, donc `tsc` ne pouvait rien détecter. La dérive n'est apparue qu'en branchant l'agent réel. | 0,25 j |
| RC3-09 | **Cosmétique** | Deux imports morts dans `mission_executor.py` (`ExecutionTimeline`, `AgentAssignment`). | Refactorisations antérieures. | 0,05 j |

### 3.2 Anomalies restantes (non corrigées, avec justification)

| ID | Criticité | Anomalie | Pourquoi non corrigée | Coût estimé |
|----|-----------|----------|-----------------------|-------------|
| RC3-10 | **Majeure** | **Aucune surface ne décompose un objectif en DAG puis l'exécute.** `POST /api/v1/missions` exige que le *client* fournisse `nodes` et `edges` : sans eux la mission naît avec `nodes: 0, edges: 0`, et `POST /missions/{id}/start` ne fait que basculer le libellé en `running` — la progression reste à zéro indéfiniment. Le service `mission_planner` est bien construit (il figure dans les 32) mais `backend/mission/routes.py` ne le référence jamais. À l'inverse, `/autonomous/start` exécute réellement, mais sur **une seule tâche**, sans DAG. | Brancher le planificateur sur la création de mission, puis relier le graphe au `MissionExecutor`, change le comportement de l'API et ajoute une capacité absente. C'est du **développement de fonctionnalité**, explicitement hors périmètre. | 5–8 j |
| RC3-11 | **Majeure** | **Registres vides au démarrage** : l'application assemblée expose `agents: 0`, `tools: 0`, `skills: 0`, `mcp/servers: 0`, et un seul runtime — `stub` (`capabilities: ["chat"]`). Une mission lancée via `/missions` n'aurait donc aucun agent à qui s'adresser. Les agents *rapportent* pourtant `installed: true` (KlaatCode v2.3.5, 7 outils ; Oh My Pi, 9 outils). | Peupler les registres au démarrage est une décision de conception (quels agents, quels runtimes, sous quelle politique) et non la correction d'un défaut ponctuel. | 2–3 j |
| RC3-12 | **Majeure** | **4 Centres sur 16 affichent encore des données entièrement fabriquées** : `autonomous-center` (`MOCK_GOAL`, `MOCK_SESSION`, `MOCK_DECISIONS`, `MOCK_TIMELINE`), `code-intelligence-center`, `deployment-center`, `model-intelligence-center`. Le cas le plus grave est le Centre Autonome : c'est la capacité phare, son API backend est **entièrement réelle et vérifiée**, et l'interface montre malgré tout des données inventées. | Pour `autonomous` et `model-intelligence`, la correction demande un nouveau client + de nouveaux hooks (il n'existe ni `autonomousClient` ni client de modèles) : faisable, mais c'est de l'ajout de couche. Pour `code-intelligence` et `deployment`, **aucune route backend n'existe** (préfixes vides), donc la correction exige d'abord d'écrire l'API. | 1,5 j (autonomous) · 1 j (model-intelligence) · 4–6 j (les deux autres, API incluse) |
| RC3-13 | **Majeure** | **4 préfixes annoncés n'ont aucune route** : `/api/v1/ktransformers`, `/api/v1/code-intelligence`, `/api/v1/knowledge-graph`, `/api/v1/model-intelligence` — 0 route chacun. Les capacités correspondantes existent côté backend (`ktransformers` est dans les 32 services construits) mais ne sont pas exposées. | Exposer une API absente est du développement. | 3–5 j |
| RC3-14 | **Mineure** | **L'ordonnancement par priorité est inopérant.** `_priority_value()` renvoie la même valeur pour toute tâche, donc le tri de la file prête est un no-op : les tâches d'une mission `CRITICAL` ne passent jamais devant celles d'une mission `LOW`. L'API accepte pourtant `priority` (`backend/execution/routes.py:50`). | Ce n'est pas une faute de frappe mais un **manque de modèle** : `priority` vit sur `ExecutionMeta` (par mission) et `TaskExecution` n'en porte aucune — il n'y a rien à trier. Propager la priorité de la mission vers chaque tâche est un changement de comportement. Documenté dans le code (`task_scheduler.py`, `_priority_value`) comme limitation connue. | 1 j |
| RC3-15 | **Mineure** | `backend/mission/routes.py` conserve les missions dans un `dict` **global de module** (`_missions`) : jamais purgé (croissance illimitée) et partagé entre toutes les instances d'application du processus. | Un plafond silencieux supprimerait des missions visibles par l'utilisateur — une perte de données pire que la fuite. La bonne correction est la persistance ou une rétention explicite et documentée : c'est une décision produit. | 1–2 j (persistance) |
| RC3-16 | **Mineure** | **11 des 32 services ne peuvent pas être sondés** : `/system/health` les classe `unknown — no statistics accessor exposed` (`event_hub`, `runtime_discovery`, `runtime_intelligence`, `runtime_simulation`, `runtime_event_bus`, `mission_executor`, `mission_planner`, `conversation_manager`, `explainability`, `model_intelligence`, `system_monitor`) tout en renvoyant `status: "healthy"` pour l'ensemble. Un tiers du système est invisible à la surveillance, mais l'agrégat se déclare sain. | Ajouter un accesseur de statistiques à onze services est un travail d'instrumentation, pas une correction de bogue. La distinction `unknown` vs `unhealthy` est déjà remontée honnêtement dans la charge utile. | 1,5 j |
| RC3-17 | **Mineure** | Aucune authentification ni autorisation sur l'API : les 198 couples méthode+chemin sont ouverts, y compris `/workspace`, `/policy/rules`, `/security/*` et l'exécution d'outils. | L'ajout d'un schéma d'authentification est une fonctionnalité de sécurité, pas la correction d'un défaut. À trancher avant toute exposition hors poste local. | 3–5 j |
| RC3-18 | **Mineure** | `tests/architecture/test_ktransformers.py` et `test_ktransformers_integration.py` **ne s'importent pas** (`KTCache`, `KTKernelWrapper` absents) et interrompent la collecte de la suite complète. Ce sont des prototypes morts déjà signalés en RC1/RC2. | Les modules KT eux-mêmes ne s'importent pas (`KTCacheStats` a disparu de `kt_models`). Les réparer, c'est ressusciter un prototype ; les supprimer, c'est décider d'abandonner la piste KTransformers. Décision produit. | 0,5 j (suppression) · 3 j (remise en état) |
| RC3-19 | **Cosmétique** | `/system/assembly` rapporte `event_topics_registered: 0`, ce qui se lit comme « aucun sujet enregistré ». **Ce n'est pas un défaut** : le champ compte les sujets *nouvellement ajoutés*, et les 84 sujets collectés figurent déjà dans la liste blanche statique de 179 entrées. Le nom du champ induit en erreur. | Renommer un champ de réponse JSON casse les consommateurs. | 0,1 j |
| RC3-20 | **Cosmétique** | `frontend/AGENTS.md` impose de lire `node_modules/next/dist/docs/` avant d'écrire du code — **ce répertoire n'existe pas** (Next 15.1.0). La consigne est donc inapplicable telle quelle. | Consigne de dépôt, pas code applicatif. | 0,05 j |

**Total du reste à traiter : environ 28 à 42 jours-développeur**, dont ~20 à 33 jours de
développement de fonctionnalités (RC3-10 à RC3-13, RC3-17) qui ne relèvent pas d'un audit.

---

## 4. Correctifs appliqués

Périmètre respecté : aucune fonctionnalité nouvelle, aucun sous-système réécrit, aucune
architecture saine modifiée.

### 4.1 Diffusion réelle des événements de mission (RC3-01, RC3-05)

`backend/execution/mission_executor.py` — `_publish()` enregistre **et** diffuse :

```python
def _publish(self, event_type: str, data: dict[str, Any],
             dispatch: bool = True) -> None:
    event = {"type": event_type,
             "timestamp": datetime.now(timezone.utc).isoformat(), **data}
    self._events.append(event)
    if not dispatch or self._on_event is None:
        return
    try:
        self._on_event(event_type, event)
    except Exception:
        # La télémétrie ne doit jamais faire échouer la mission qu'elle décrit.
        logger.warning("event dispatch failed for %s", event_type, exc_info=True)
```

Le site `execution.task_completed` passe `dispatch=False`, car `RealTaskExecutor` annonce déjà
ce jalon avec plus de détail. L'en-tête « EventBus simulation » a été remplacé par
« Event publication ».

### 4.2 Bornage des six collections (RC3-02)

| Module | Collection | Croissance | Plafond |
|--------|-----------|------------|---------|
| `mission_executor.py` | `_events` | 5 / mission | `deque(maxlen=2000)` |
| `task_scheduler.py` | `_tasks` + `_dependencies` | ~1 / tâche | `MAX_RETAINED_TASKS = 512` |
| `decision_engine.py` | `_decisions` | 4 / mission | `deque(maxlen=2000)` |
| `validation_engine.py` | `_history`, `_results`, `_criteria` | 1 / tâche | `MAX_RETAINED_VALIDATIONS = 2000` |
| `agent_coordinator.py` | `_assignments` | 1 / tâche | `MAX_RETAINED_ASSIGNMENTS = 2000` |
| `autonomous_memory_loop.py` | `_learnings` | 1 / mission | `deque(maxlen=1000)` |

L'éviction de l'ordonnanceur est **O(1) amortie** et privilégie le travail terminé : une
extraction en tête qui tombe sur une tâche encore en file la fait tourner en queue, dans la
limite de `_EVICT_RESCUE_LIMIT = 16`, de sorte que le plafond reste une borne mémoire dure
même si tout est en attente. Les `_dependencies` sont purgées avec leur tâche, sinon elles
devenaient la nouvelle fuite.

`deque` ne supporte pas le découpage : `get_decisions()` et `get_learnings()` utilisent
`itertools.islice`.

### 4.3 Recherche de tâche en O(1) (RC3-03)

`TaskScheduler.get_task()` ajouté ; `MissionExecutor.execute_task()` l'utilise au lieu de
copier puis parcourir le registre.

### 4.4 Une optimisation envisagée puis **retirée** — et pourquoi

J'avais d'abord rendu `get_progress()`/`is_all_done()` O(tâches en vol) grâce à un ensemble
« non encore terminales » et un compteur des terminales. **Mon propre test de correction l'a
invalidée** : la marche aléatoire comparant le résultat au balayage naïf a produit 192
divergences sur 400 pas.

La cause est réelle, pas artificielle : les appelants écrivent `task.status` directement
autant qu'ils passent par `update_task()`, et une tâche en échec revient à `PENDING` lors
d'une reprise (`mission_executor.py:163`) ; rien n'interdit non plus de réexécuter une tâche
déjà `COMPLETED`. Tout compteur entretenu dérive donc silencieusement.

J'ai retiré l'optimisation et conservé le balayage **prouvablement exact**, en faisant du
plafond de rétention le levier : le balayage est désormais O(512), c'est-à-dire constant, au
lieu de O(missions exécutées). Le gain mesuré est identique et le risque sémantique est nul.
La marche aléatoire rejouée donne **0 divergence sur 400 pas**.

### 4.5 Boucle d'apprentissage rebranchée (RC3-04)

`service_registry.py` : `_make_autonomous_engine` ferme la boucle ; dépendances passées à
`("event_dispatcher", "memory_manager", "evolution_engine")`. Dans
`autonomous_memory_loop.py`, l'écriture épisodique construit un vrai `EpisodicMemory` et
l'échec éventuel est **journalisé** au lieu d'être avalé.

### 4.6 Cockpit : deux panneaux débranchés des données fabriquées (RC3-06 → RC3-08)

- 4 hooks ajoutés (`useKlaatCodeStatus`, `useKlaatCodeCapabilities`, `useOhMyPiStatus`, `useOhMyPiCapabilities`) pour deux clients qui existaient déjà, complets, et que rien n'appelait ;
- 68 lignes de capacités fabriquées supprimées de `ohmypi-panel.tsx`, 58 de `klaatcode-panel.tsx` ;
- le badge « MCP Connected » distingue désormais *chargement* / *erreur* / *lié* / *installé mais non lié* / *non installé* ;
- états de chargement, d'erreur et de vacuité explicites sur les deux grilles d'outils ;
- `OhMyPiCapability` aligné sur ce que l'API renvoie réellement ; la catégorie d'affichage est **dérivée** du nom (`lsp_edit` → `lsp`) avec un commentaire indiquant qu'elle est dérivée et non reçue.

### 4.7 Code mort (RC3-09)

Deux imports inutilisés retirés de `mission_executor.py` ; `import random` mort et une
docstring périmée (« 4. Execute (simulated) ») corrigés dans `autonomous_orchestrator.py`.

---

## 5. Métriques avant / après

### 5.1 Débit et mémoire

Même sonde, même machine, même graine ; `tracemalloc` + `perf_counter`.

| Charge | Avant | Après | Gain |
|--------|-------|-------|------|
| 100 missions | 972 msn/s | 1 043 msn/s | +7 % |
| 500 missions | 701 msn/s | 1 040 msn/s | **+48 %** |
| 1 000 missions | 453 msn/s | 1 009 msn/s | **×2,2** |
| Régime soutenu (missions 1 600–3 600) | 334 → 273 → 256 msn/s | 976 → 971 → 934 → 956 msn/s | **×3,7** |
| Croissance mémoire | +10,0 Kio/mission (constante) | +1,4 Kio/mission, tendant vers 0 | **×7** |
| Tas maximal | 15,7 Mo à 1 600 missions | 8,4 Mo à 3 600 missions | −47 % pour 2,25× la charge |

Le point décisif n'est pas le gain brut mais la **forme de la courbe** : le débit passe de
*décroissant* (983 → 256, facteur 3,8) à **plat** (1 043 → 956 sur 3 600 missions, dispersion
de 8 %). La croissance du tas par bloc de 500 missions décroît vers zéro à mesure que les
plafonds se remplissent : +560, +387, +213, +172 Kio.

### 5.2 Localisation du point chaud

| Élément | Avant | Après |
|---------|-------|-------|
| `task_scheduler.py:169` (générateur de `is_all_done`) | 374 014 appels / 300 missions — 45 % du temps | borné à O(512) |
| `execute_task()` recherche de tâche | balayage linéaire du registre complet | accès direct, 2,3 µs/appel mesurés sur 10 000 |
| `get_session()` (corrigé plus tôt en RC3) | balayage O(n) | index O(1), 2,3 µs/appel |

### 5.3 Diffusion des événements

| | Avant | Après |
|---|-------|-------|
| Événements de mission générés | 5 | 5 |
| Événements atteignant un abonné | **1** (émis par `RealTaskExecutor`, pas par l'exécuteur de mission) | **5** |
| Doublons sur `execution.task_completed` | — (le second n'était pas diffusé) | **0** |

### 5.4 Vérité affichée par le Cockpit

| | Avant RC3 | Après RC3 |
|---|-----------|-----------|
| Centres/panneaux affichant des données fabriquées | 9 | **4** |
| Composants définissant des constantes `MOCK_*` | 8 | **4** |
| Centres avec états chargement/erreur explicites | 1 | **6** |

### 5.5 Suite de tests

| | Avant | Après |
|---|-------|-------|
| Tests backend | 3 293 réussis, 3 ignorés, 0 échec (8 min 52 s) | **3 306 réussis, 3 ignorés, 0 échec** (8 min 39 s) |
| Modules de test qui ne s'importent pas | 2 (KTransformers) | 2 — inchangé, cf. RC3-18 |
| `tsc --noEmit` | 0 erreur | **0 erreur** |
| Build frontend | succès | **succès**, 14 pages statiques |
| Vitest | 65 / 65 | **65 / 65** |
| Tests de non-régression RC3 | — | **+13** (`tests/integration/test_rc3_bounds_and_events.py`) |

Les 13 nouveaux tests verrouillent les bornes de rétention (contre les **constantes publiées
des classes**, afin qu'un réglage de plafond ne casse pas le test — seule sa suppression le
casse), l'exactitude de `get_progress()` sous écriture directe de statut et retour arrière
depuis un état terminal, la nature non balayante de `get_task()`, la diffusion des quatre
événements de cycle de vie, l'unicité de l'annonce de complétion, et le fait qu'un abonné qui
lève une exception ne peut pas faire échouer la mission.

---

## 6. Sondes défectueuses (erreurs de l'auditeur, pas du produit)

L'exercice impose de ne rien prendre au pied de la lettre — y compris mes propres mesures.

1. **Faux « 9 intégrations manquantes ».** Ma première sonde de la phase 3 devinait les noms
   d'endpoints (`/alexandrie/stats`, `/memory/stats`…) et concluait à 9 routes absentes. La
   table de routage réelle montre 19 routes sous `alexandrie`, 37 sous `runtime`, 8 sous
   `execution`. Corrigé en énumérant `app.routes` au lieu de deviner. Résultat réel : **28
   groupes, 28/28 en 200**.
2. **Faux « API autonome inaccessible ».** J'ai envoyé `{"goal": ...}` là où le schéma attend
   `user_request`, obtenu 405/422, et failli conclure que l'exécution autonome n'était pas
   joignable par HTTP. Avec le bon champ, elle exécute réellement (19,5 s sur Ollama). C'était
   la découverte la plus importante de l'audit, et je l'ai presque manquée par une erreur de sonde.
3. **Optimisation invalidée par mon propre test** — cf. § 4.4. Signalée ici parce que
   c'est le cas où l'audit s'est corrigé lui-même avant de livrer du code faux.

---

## 7. Décision

### GO POUR RC4 — NO GO pour v1.0

**Argumentation.**

Ce qui justifie le GO RC4 : le socle est sain et vérifié sur l'application réelle. 32/32
services construits, 30 routeurs montés, aucun cycle de dépendance, aucune dépendance
manquante, aucun service isolé. 3 293 tests passent sans échec. Le frontend compile et se
construit sans erreur. Et surtout, la capacité phare **fonctionne réellement de bout en bout
par HTTP** : inférence Ollama véritable, décisions réelles, rapport dérivé du travail
effectué. Les défauts corrigés ici étaient tous du même type — des coutures d'injection
présentes et jamais appelées — et non des défauts de conception. Après correction, le système
tient une charge soutenue à débit plat et mémoire stable, ce qui n'était pas le cas au début
de cet audit.

Ce qui interdit le v1.0 : **trois écarts entre ce que le système annonce et ce qu'il fait.**

1. **Deux surfaces de mission, aucune complète** (RC3-10). `/missions` accepte un objectif,
   répond `200`, bascule en `running` — et n'exécute rien : ni planification, ni tâche, ni
   progression. `/autonomous` exécute vraiment mais sur une seule tâche, sans DAG. Un
   utilisateur qui crée une mission par la voie documentée obtient un objet qui ne fera jamais
   rien, sans aucun message d'erreur. C'est le défaut le plus grave restant, parce qu'il est
   silencieux.
2. **Registres vides** (RC3-11). 0 agent, 0 outil, 0 compétence, un seul runtime `stub`. Le
   système est assemblé mais non peuplé.
3. **Le Cockpit affiche encore des données fabriquées sur 4 Centres sur 16** (RC3-12), dont le
   Centre Autonome — celui dont l'API est intégralement réelle. Une interface qui invente des
   chiffres devant un backend qui en produit de vrais est un problème de confiance, pas
   d'esthétique.

Aucun de ces trois points ne pouvait être corrigé dans le cadre de cet audit sans développer
des fonctionnalités, ce qui était explicitement exclu. Ils constituent le contenu naturel de
RC4.

**Condition de sortie de RC4 vers v1.0** — trois critères vérifiables :

1. une mission créée par `POST /api/v1/missions` produit un DAG non vide et son exécution
   fait réellement progresser la mission jusqu'à un état terminal ;
2. les registres d'agents, d'outils, de compétences et de runtimes sont peuplés au démarrage,
   et au moins un runtime réel (non `stub`) est actif ;
3. aucun composant du Cockpit ne définit de constante `MOCK_*` ; chaque Centre distingue
   *chargement*, *vide* et *erreur*.

Chemin critique estimé : **8 à 13 jours-développeur** pour ces trois critères
(RC3-10 : 5–8 j, RC3-11 : 2–3 j, RC3-12 partiel : 1,5–2 j), les autres anomalies restantes
étant acceptables en v1.0 sous réserve d'être documentées — à l'exception de RC3-17
(authentification), qui doit être tranchée avant toute exposition réseau.

---

## Annexe A — Fichiers modifiés

| Fichier | Nature |
|---------|--------|
| `backend/execution/mission_executor.py` | diffusion réelle des événements, tampon circulaire borné, recherche O(1), imports morts |
| `backend/execution/task_scheduler.py` | plafond de rétention, éviction O(1) amortie, `get_task()`, limitation connue documentée |
| `backend/execution/validation_engine.py` | bornage des trois collections |
| `backend/execution/agent_coordinator.py` | bornage des affectations |
| `backend/autonomous/decision_engine.py` | historique borné, `islice` pour le découpage |
| `backend/autonomous/autonomous_memory_loop.py` | apprentissages bornés, écriture épisodique corrigée et journalisée |
| `backend/autonomous/autonomous_orchestrator.py` | rétention bornée, index O(1), code mort |
| `backend/core/bootstrap/service_registry.py` | fermeture de la boucle d'apprentissage |
| `frontend/src/hooks/use-api.ts` | 4 hooks pour deux clients inutilisés |
| `frontend/src/features/tools/klaatcode-panel.tsx` | capacités réelles, badge de statut honnête, états explicites |
| `frontend/src/features/tools/ohmypi-panel.tsx` | capacités réelles, états explicites, catégorie dérivée |
| `frontend/src/types/hermes.ts` | `OhMyPiCapability` aligné sur l'API réelle |
| `tests/integration/test_rc3_bounds_and_events.py` | **nouveau** — 13 tests de non-régression |

## Annexe B — Commandes de vérification

```bash
python -m pytest tests/ backend/tests/ -q --timeout=180 -p no:randomly --ignore=tests/architecture/test_ktransformers.py --ignore=tests/architecture/test_ktransformers_integration.py
```

```bash
python -m pytest tests/integration/test_rc3_bounds_and_events.py -q -p no:randomly
```

```bash
cd frontend && npx tsc --noEmit && npm run build && npx vitest run
```
