# Audit de conformité — Hermes Ollama vs cahier des charges v4.0

**Date :** 2026-07-26
**Référence :** `CAHIER_DES_CHARGES_HERMES_OLLAMA.md` v4.0 consolidée —
le document normatif versionné dans ce dépôt, lu intégralement
(1 195 lignes) avant toute conclusion.
**Base auditée :** branche `claude/hermes-ollama-specs-v4-fa08ou`,
643 tests au vert.

---

## 0. Avertissement — ce que la version précédente de cet audit affirmait de faux

Un premier audit daté du 2026-07-25 a été mené contre une version
*condensée* du cahier des charges, fournie à titre indicatif dans une
conversation. Il annonçait comme constat principal un « glissement de
vocabulaire » : le sigle HSE désignant deux choses opposées, les rôles
d'Atlas et Swift échangés, un agent Sentinel manquant.

**Rien de cela n'était vrai du document normatif.** Celui-ci dit
`## 17. Sécurité (Aegis)` et `## 20. Auto-évolution (HSE)` — un seul sens
au sigle — et ses fiches agents §9.1 listent exactement les dix agents du
code, avec les bons rôles. Le code et la spécification étaient cohérents
depuis le début.

La faute est de méthode : auditer contre un document sans établir lequel
fait foi fabrique des divergences imaginaires *et* masque les vraies,
puisqu'on croit tenir la cause. Le présent document repart du bon
référentiel.

Conséquence conservée : le renommage `hse_*` → `evolution_*`
(commit `bd5103e`) reste en place — décision utilisateur, justifiée par la
lisibilité et non par la raison invoquée à l'époque.

---

## 1. Synthèse

| Verdict | Sections |
|---|---|
| **Conforme, vérifié** | §9 agents · §9.2 bus · §10 routage · §11 mémoire · §13 tâches · §14.1 fichiers · §15 workflows · §17 sécurité · §20 auto-évolution · §21 monitoring |
| **Conforme après les travaux du 2026-07-25** | §13 ingestion documentaire · §14 Git · §16 vérification · §22 VRAM |
| **Absent** | §12 résumé de contexte |
| **Écart assumé, à documenter** | §4.1 stack (LangChain, Watchdog, keyring, Telegram) · §23 interface |
| **Non vérifié** | §25 installation |
| **Mesuré, corrigé** | §22.1 latences — T1 et T3 passent après le correctif du raisonnement par `task_type` (§3.2.3) |

Le projet couvre la majeure partie du corps normatif. Le seul manque qui
cassait un critère d'acceptation explicite (T8, snapshots) a été comblé
le 2026-07-26 ; les manques restants sont réels mais ne bloquent aucun
critère du §28.

---

## 2. Conforme — vérifié

| § | Exigence | Où c'est satisfait |
|---|---|---|
| **9.1** | Dix agents, rôles et always-on | `config/agents.yaml` correspond aux fiches, un pour un |
| **9.2** | Bus typé, 6 types de messages, horodaté | `core/message_bus.py`, visible dans le tableau de bord |
| **10.1** | Matrice `task_type → modèle` | `core/router.py` + `config/models.yaml` |
| **10.3** | Réutiliser un modèle déjà chargé | Le routeur consulte la VRAM et privilégie le résident |
| **11.1-11.4** | Mémoire courte / longue / documentaire / procédurale | Session agent · `episodic.py` · `semantic.py` · `skill_library.py` |
| **11.5** | Datation, dédup par hash, suppression explicite | `episodic.add_memory` |
| **11.6** | Decay Ebbinghaus | `skill_library.apply_decay`, `EBBINGHAUS_DECAY_ENABLED` |
| **13.1-13.2** | Champs et **les dix statuts** | `TaskStatus` — exhaustif, `reversible` et `to_resume` inclus |
| **14.1** | Backup avant modification + diff avant application | `file_tools.propose_write` |
| **15** | Workflows YAML, graphe, portails humains, `simulate` | `workflows/engine.py` + 2 workflows livrés |
| **17.1-17.2** | Whitelist, matrice de permissions | `aegis_engine.py`, `security.yaml`, `ALLOWED_PATHS` |
| **17.5** | Quatre niveaux d'autonomie | `security.yaml`, défaut `low` |
| **20** | Les quatre composants HSE | `self_evolution/` correspond exactement au tableau |
| **21** | VRAM, température, modèles chargés, seuils 85/90 °C | `gpu_monitor.py`, seuils dans `.env` |
| **22.2** | Températures de génération par criticité | `models.yaml` → `generation_defaults` |
| **22.4** | Ajout de modèle par `models.yaml` sans toucher au cœur | **Prouvé** : quatre modèles remplacés depuis la v4.0, zéro changement de code |

### Matrice d'acceptation §28

| Test | État | Preuve |
|---|---|---|
| T2 routage code tracé | ✅ | `router.py`, `reason` tracée |
| T4 downgrade si VRAM insuffisante | ✅ | Repli sur le plus petit candidat |
| T6 diff avant application | ✅ | `propose_write` |
| T7 validation humaine sur suppression | ✅ | Vérifié en réel : `file_delete` = `mandatory_validation` |
| T9 lint + tests après modification | ✅ | Depuis le 2026-07-25 (§16) |
| T12 secret ciblé → validation | ⚠️ partiel | `secret_modification` est en validation obligatoire ; `audit_log.redact()` couvre désormais la détection sur ce qui est journalisé, mais il n'y a toujours pas de `secret_scanner` sur les fichiers |
| **T8 reprise après interruption** | ✅ | `snapshot_manager` — vérifié en réel le 2026-07-26 |
| **T11 3 tentatives + backoff** | ✅ | `ollama_client.py` — vérifié en réel contre un port fermé |
| T1 premier token < 1 s | ✅ | Mesuré via Hermes : `qwen3:1.7b` à 766 et 978 ms, raisonnement activé |
| T3 réutilisation du modèle chargé | ✅ | §10.3 vérifié ; latence Tier 2 ramenée de 4 223 ms à **594-615 ms** (budget 3 s) par le raisonnement par `task_type` — §3.2.3 |
| T5 recherche < 500 ms | ⏳ | Non mesuré |

---

## 3. Manques réels

### 3.1 §19.3 — Snapshots & rollback — FAIT le 2026-07-26

`backend/core/snapshot_manager.py` + `POST /snapshots`,
`GET /snapshots`, `GET /snapshots/{id}/preview`,
`POST /snapshots/{id}/restore`, et quatre outils MCP.

**Ce qui est capturé, et ce qui ne l'est délibérément pas.** Les tâches
et les runs de workflow (l'état durable), plus un `context` libre fourni
par l'appelant. Les *contenus* de fichiers ne sont **pas** recopiés :
`propose_write` sauvegarde déjà chaque fichier avant écrasement, dans ce
même `data/snapshots/`. Les dupliquer doublerait le coût disque et
créerait deux chemins de restauration pouvant diverger. Le snapshot
enregistre les *chemins* touchés, pas les octets.

**La restauration est destructive, et traitée comme telle :**

- classée `data_migration`, donc validation humaine obligatoire à *tout*
  niveau d'autonomie (§17.3 liste « migration de données ») ;
- jamais automatique — ni au démarrage, ni après un plantage. Restaurer
  sans demander serait précisément le genre d'action que le §17 encadre ;
- `preview_restore` montre ce qui changerait avant d'accepter, le même
  contrat « diff d'abord » que le §14.1 impose aux écritures ;
- **les tâches créées après le snapshot ne sont pas supprimées.**
  Restaurer n'est pas « remettre le monde exactement comme avant » :
  effacer du travail postérieur ferait *perdre* des données à un outil de
  récupération.

Les snapshots sont du JSON lisible au `cat`, sans table ni migration —
ce qui compte pour un mécanisme dont la raison d'être est de rattraper un
état cassé, y compris si ce module est lui-même en panne.

`StepCounter` déclenche un snapshot toutes les N étapes
(`SNAPSHOT_EVERY_STEPS`, 0 pour désactiver), et `prune_snapshots` borne
le répertoire — le §3.7 ne budgète que ~2-5 Go pour logs et snapshots
réunis.

**T8 vérifié en réel**, pas seulement en test : une tâche passée à
`cancelled`, restauration refusée (`require_human_validation`), approuvée
via la file, relancée — la tâche est revenue à `todo`. 19 tests.

### 3.2 ~~§18 — Log d'audit structuré~~ — **fait le 2026-07-26**

Le §18 spécifie un format JSON précis : `routing_decision`,
`context_used`, `files_modified`, `tests_run`, `duration_ms`,
`tokens_used`, `tokens_per_second`, `vram_used_gb`, `result` — stocké en
table `audit_log` et en fichiers sous `data/logs/`.

`backend/core/audit_log.py` implémente les deux destinations, avec
`redact()` appliqué **à l'écriture** (un secret arrivé sur le disque a
déjà fuité ; filtrer à l'affichage serait du théâtre). `/chat` est
instrumenté ; `GET /logs`, `/logs/{session_id}` et `/logs/latency`
exposent la lecture. 28 tests.

Un champ supplémentaire hors §18 : **`first_token_ms`**. Le §22.1 budgète
le *premier token*, pas la durée totale — un seul chiffre ne distingue
pas un chargement lent d'un modèle lent, et les deux appellent des
corrections opposées. La mesure ci-dessous montre pourquoi c'était
nécessaire.

### 3.2.1 §22.1 — premières latences réellement mesurées

Mesuré le 2026-07-26 via `/logs/latency`, RX 6800, `qwen3.5:9b` (Tier 2,
budget **< 3 s au premier token**), modèle **déjà chargé** en VRAM :

| requête | premier token | total | tokens | débit |
|---|---|---|---|---|
| « Capitale de l'Espagne ? » | 9 541 ms | 9 673 ms | 9 | 68,4 t/s |
| « Capitale de la Belgique ? » | 17 501 ms | 17 751 ms | 17 | 67,8 t/s |
| « Capitale du Portugal ? » | 20 911 ms | 22 186 ms | 86 | 67,5 t/s |

**T3 est en échec, pas « non vérifié » : 3 à 7× le budget.** Le débit
(~68 t/s) est bon ; la latence est presque intégralement du
time-to-first-token.

### 3.2.2 Diagnostic — la cause est la phase de raisonnement, pas le tier

Mesuré **directement contre Ollama**, sans passer par Hermes, pour que le
routeur ne soit pas une variable. Modèle préchauffé, ordres entrelacés
(le premier essai plaçait `think=False` en dernier, donc sur le modèle le
plus chaud — biais corrigé). `qwen3.5:9b`, même prompt :

| configuration | 1er token (tout) | 1er token de **contenu** | raisonnement |
|---|---|---|---|
| `think=False` | 675 ms | **675 ms** | 0 car |
| `think=True` | 657 ms | **4 223 ms** | 943 car |
| `think=False` (2) | 705 ms | **705 ms** | 0 car |
| non précisé (défaut Hermes) | 633 ms | **4 405 ms** | 936 car |
| `think=False` (3) | 697 ms | **697 ms** | 0 car |

**Le premier token arrive en ~660 ms dans tous les cas.** L'écart est
intégralement la phase de raisonnement qui précède le contenu :
`chat_stream` ne yield que `message.content`, donc l'utilisateur ne voit
rien pendant ~3,5 s. Sans raisonnement, ~690 ms — soit **6× mieux et très
largement dans le budget de 3 s**.

Cause secondaire confirmée : le chargement à froid coûte ~6,4 s, et le
rôle `standard` n'est pas `always_loaded`. Combiné au raisonnement, c'est
ce qui produisait les 9,5 à 20,9 s du tableau précédent.

**L'hypothèse « mauvais tier » est écartée.** Mesuré en conditions
réelles via Hermes, `qwen3:1.7b` (Tier 1, budget 1 s) répond en 766 et
978 ms au premier token de contenu, raisonnement activé : **T1 passe**.
Le routeur avait d'ailleurs correctement privilégié le modèle résident
(§10.3).

### 3.2.3 Correctif — raisonnement par `task_type` — fait le 2026-07-26

Arbitrage retenu : le raisonnement reste actif là où il change la
réponse, et disparaît là où il n'ajoute que du silence. Déclaré en
configuration (`config/models.yaml` → `thinking`), conformément au §22.4
« ajouter/retirer sans toucher au cœur » :

```yaml
thinking:
  default: false
  by_task_type:
    reasoning: true        # + verification, planning,
    ...                    #   code_analysis, code_generation, code_refactor
```

La valeur résolue est portée par `RoutingDecision` — pas recalculée par
chaque appelant — et enregistrée dans le `routing_decision` du log
d'audit. Un `task_type` absent de la table prend le défaut *et se voit*
dans les logs, au lieu d'être silencieusement dégradé.

`select_model` a quatre chemins de sortie qui construisaient chacun le
dataclass à la main ; ils passent désormais par un constructeur unique.
Renseigner le champ sur trois chemins sur quatre aurait livré une valeur
juste seulement parfois — exactement la forme du bug `first_token_ms`
ci-dessus.

**Mesuré en réel après correctif**, `qwen3.5:9b` en Tier 2, modèle chaud :

| `task_type` | raisonnement | 1er token de contenu |
|---|---|---|
| `writing` | non | **594 ms** / **615 ms** |
| `conversation` | non | **577 ms** |
| `extraction` | non | **519 ms** |
| `planning` | oui | 6 137 ms |
| `code_analysis` | oui | 42 160 ms |

**T3 passe** : 594-615 ms contre 3 s de budget, soit ~7× de marge, là où
la mesure d'avant donnait 4 223 ms. Le raisonnement reste coûteux — c'est
le prix assumé, désormais payé uniquement sur les tâches qui en tirent
quelque chose.

### 3.2.4 Le raisonnement est diffusé au lieu d'être caché — fait le 2026-07-26

Le §22.1 est tenu sur les tâches sans raisonnement, mais celles qui en
gardent restent longues par construction : `code_analysis` mesuré à 42 s
avant le premier mot visible. Le raisonnement existait pourtant depuis le
début, dans `message.thinking` — `chat_stream` le jetait.

`chat_events` le remonte, étiqueté. **`chat_stream` devient un filtre
strict par-dessus** et garde son contrat octet pour octet : les dix
agents qui parsent la réponse en JSON (classification, vérification,
extraction) ne doivent jamais voir de raisonnement se mélanger à
l'answer. C'est l'invariant le plus épinglé par les tests.

Côté HTTP, `include_thinking` est **opt-in** : sans lui le corps reste du
texte brut. Avec, il passe en NDJSON (`{"kind","text"}` par ligne). Un
appelant ne peut pas se mettre à recevoir du raisonnement sans l'avoir
demandé.

Le `Timer` distingue les deux : `tokens_used` et `tokens_per_second`
continuent de ne compter **que le contenu**. Y laisser entrer le
raisonnement aurait laissé ces champs identiquement nommés et typés en
mesurant autre chose — le débit aurait paru *meilleur* précisément sur
les requêtes qui font le plus attendre. Nouveau champ `first_thinking_ms`
à côté de `first_token_ms`, qui garde son sens (premier token de
contenu).

**Vérifié dans le navigateur**, pas seulement en test — `code_analysis` :

| repère | mesure |
|---|---|
| premier raisonnement affiché | **625 ms** |
| premier mot de la réponse | 18 903 ms |
| silence supprimé | **18,3 s** |

Le panneau s'ouvre pendant l'attente, se replie seul dès le premier mot,
et reste consultable (5 549 caractères conservés). `<details>` natif :
clavier et lecteurs d'écran sans code supplémentaire.

Constat au passage : la page envoyait toujours `conversation`, où le
raisonnement est désactivé — le panneau était donc **inatteignable depuis
l'interface**. Un sélecteur de `task_type` a été ajouté ; sans lui le
correctif n'aurait rien corrigé d'observable.

Reste non traité : le **chargement à froid** (~6,5 s à la première
requête). C'est un sujet distinct — le rôle `standard` n'est pas
`always_loaded` (§22, budget VRAM de 16 Go).

Constat associé : une requête a produit **0 token en 59,7 s** tout en
étant enregistrée `result: "success"`. Corrigé — un flux sans token est
désormais `result: "empty"` avec son motif. C'est le même défaut que
partout ailleurs dans cet audit : du code qui affirme une réussite qu'il
n'a pas constatée.

### 3.3 ~~§24.2 — WebSocket~~ — **fait le 2026-07-26**

Les cinq événements du §24.2 sont diffusés sur `GET /ws`, filtrables
(`/ws?types=task.update,validation.request`). Chaque trame est
`{"type","payload","timestamp"}`.

Aucun de ces événements n'est une information nouvelle : le bus, Kronos,
la file d'approbation et le moniteur GPU les produisaient déjà. Ce module
ne fait que les acheminer.

**La publication est synchrone et ne lève jamais.** Quatre des cinq
producteurs sont des fonctions sync sans boucle d'événements
(`message_bus.publish`, `kronos.update_task`, `approvals.record_pending`).
La garantie est *structurelle* — le corps de `publish()` est enveloppé une
fois, dans le hub — et non une promesse répétée à chaque site d'appel :
Kronos qui persiste une tâche fait un vrai travail, prévenir un tableau de
bord n'en est pas un, et ne doit jamais pouvoir le coûter.

**Un client lent est isolé, et les pertes sont annoncées.** File bornée
par abonné ; en saturation les événements les *plus anciens* sont
abandonnés et un `stream.dropped` dit combien. Un flux qui saute des
événements en silence est pire qu'un flux qui admet un trou : le lecteur
n'a aucun moyen de savoir que l'image est incomplète.

Deux choix de conception méritent d'être notés :

- **`task.update` est publié depuis Kronos, pas depuis la route REST.**
  Les tâches changent aussi via les outils MCP et les étapes de workflow ;
  un tableau de bord alimenté par la seule route manquerait précisément
  les changements faits par un agent de sa propre initiative — le cas qui
  a motivé cette vue.
- **Une re-demande de validation n'est pas republiée.** `record_pending`
  dédoublonne déjà les lignes `pending` ; republier laisserait un agent
  qui boucle enterrer la file sur le tableau de bord. Le bus, lui,
  journalise chaque tentative — c'est la distinction voulue.

Un filtre inconnu est **refusé** plutôt qu'ignoré : un client filtrant sur
une faute de frappe resterait sinon sur une socket muette, indiscernable
d'un système au repos.

**Les cinq vérifiés en réel**, pas seulement en test :

| événement | déclencheur | observé |
|---|---|---|
| `system.metrics` | ticker 2 s | 2 trames en 4,5 s, VRAM et charge réelles |
| `chat.token` | `POST /chat` | 4 trames, `kind` + `text` |
| `task.update` | create / patch / delete | 3 trames, `change` correct |
| `agent.message` | bus | 6 trames sur 3 tentatives |
| `validation.request` | `file_delete` refusé | 1 trame — et **0** sur 3 re-demandes identiques |

Le ticker métriques ne tourne que tant qu'un client est connecté :
interroger le GPU toutes les 2 s pour une salle vide réveillerait la carte
pour rien.

36 tests backend.

**Une vue consomme le canal.** Un panneau « Activité » (`ActivityPanel`)
affiche les tâches, les messages inter-agents et les demandes de
validation en direct, avec une jauge VRAM alimentée par
`system.metrics`.

`chat.token` n'est **pas** souscrit : un événement par token, des
centaines par réponse, chasseraient toute autre ligne du panneau en une
seconde — et la réponse est déjà affichée à côté. Ne souscrire qu'à ce
qui est affiché évite aussi que le backend mette en file un flux que ce
client jetterait aussitôt.

L'état de connexion est visible en permanence : « en direct »,
« connexion… » ou « déconnecté ». Une vue de supervision qui laisse un
affichage figé passer pour du temps réel est pire que pas de vue du tout.
La reconnexion est automatique, avec backoff plafonné.

**Vérifié dans le navigateur :**

| test | résultat |
|---|---|
| tâche créée **hors de la page** (curl) | apparaît en direct — le cas qui a motivé la vue |
| refus `file_delete` | les trois lignes : `user → aegis`, `validation.request`, `aegis → user · ESCALATION` |
| chat de ~30 tokens | **0 ligne** dans le panneau (exclusion confirmée) |
| backend coupé | l'état cesse d'afficher « en direct » |
| backend relancé | retour à « en direct » seul, historique conservé, nouveaux événements reçus |
| jauge VRAM | 7,93 / 17,16 Go, modèle chargé affiché |

Non couvert : le frontend n'a pas de harnais de test (`package.json`
n'expose que `dev`, `build`, `start`, `lint`). Le panneau est donc
vérifié par exécution, pas par des tests automatisés — en mettre en place
serait une tâche à part.

### 3.4 §12 — Résumé automatique de contexte

Exigé : « résumer automatiquement le contexte trop long », « tronquer
intelligemment sans perte d'information critique ». **Aucun module.**

### 3.5 §17.1 — `secret_scanner`

L'arborescence §8.1 le prévoit, le §17.1 exige que les secrets
n'apparaissent jamais en clair dans les logs. **Absent.** La protection
repose aujourd'hui sur le fait que peu de choses sont journalisées.

### 3.6 §19.1 — Robustesse Ollama — FAIT le 2026-07-26

`ollama_client.py` retente désormais trois fois avec backoff exponentiel
borné (0,5 s puis 1 s, plafonné à 4 s) et lève un `OllamaUnavailableError`
nommé — pas une erreur httpx brute — pour qu'un appelant distingue
« le serveur d'inférence est mort » de « le modèle a refusé la requête ».
Seule la première mérite d'être retentée.

**Ce qui n'est délibérément pas retenté :**

- **Un flux déjà commencé.** `chat_stream` est un générateur : si la
  connexion tombe après le premier token, l'appelant l'a déjà. Relancer
  la requête *dupliquerait* la réponse — pire qu'un échec propre. Un
  verrou `started` rend cette garantie explicite, et le message
  correspondant dit pourquoi. Tester ce cas a demandé un flux qui *lève*
  en cours d'itération : un corps simplement tronqué se termine
  proprement et n'aurait rien prouvé.
- **Une erreur HTTP.** Un 404 sur un modèle absent répondra identiquement
  trois fois ; retenter ne ferait que retarder l'erreur et masquer sa
  cause derrière « 3 tentatives échouées ».

**T11 vérifié en réel** contre un port fermé : trois tentatives, échec en
7,7 s, message nommant l'URL, le nombre de tentatives et `ollama ps`.
Génération réelle contrôlée après coup — aucune régression. 12 tests.

### 3.7 Manques mineurs

- `config/triggers.yaml` (§15, planification de workflows) — absent
- `config/projects.yaml` (§8.1) — absent, les projets vivent en base
- `GET /agents`, `GET /logs`, `GET /system/gpu` (§24.1) — absents

---

## 4. Écarts assumés — décisions, pas oublis

| § | Spécifié | Réalité | Justification |
|---|---|---|---|
| 4.1 | LangChain / LangGraph | Moteur de workflow écrit à la main | Plus simple, sans dépendance lourde, pour un graphe de quelques nœuds |
| 4.1 | `python-telegram-bot` | Passerelle Hermes Agent | Fonctionne, déjà authentifiée, rien à maintenir |
| 4.1 | Watchdog (surveillance fichiers) | Absent | Aucun besoin exprimé |
| 4.1 | keyring | `.env` seul | Mono-utilisateur, machine personnelle |
| 23 | 11 vues Next.js + design indigo | Plugin tableau de bord Hermes Agent, 9 panneaux | Tranché le 2026-07-25 : le Next.js aurait exigé de reconstruire l'authentification qu'Hermes Agent fournit déjà |

Ces écarts sont défendables. Ils n'étaient simplement **écrits nulle
part** — d'où leur présence ici.

---

## 5. Ce que l'audit a rendu au cahier des charges

L'**Annexe B** posait une question ouverte sur les modèles 1-bit
« Bonsai ». Elle a reçu sa réponse le 2026-07-25 : le modèle est réel
(sorti le 14/07), mais son format `Q2_0_g128` vient d'un fork de
llama.cpp et **ne charge pas sur Ollama standard**. Testé, constaté,
consigné dans l'annexe.

De même, `gemma4` n'est plus prospectif : sorti, installé, promu au rôle
`vision`. Les tableaux §5.1 et §9.1 ont été alignés sur
`config/models.yaml` — qui fait foi pour les tags exacts, conformément au
principe directeur du document.

---

## 6. Ordre de traitement recommandé

1. ~~**`snapshot_manager` (§19.3)**~~ — **fait le 2026-07-26**, T8 vérifié.
2. ~~**Retry Ollama avec backoff (§19.1, T11)**~~ — **fait le 2026-07-26.** — quelques lignes, effet
   direct sur la fiabilité quotidienne.
3. ~~**Log d'audit §18**~~ — **fait le 2026-07-26.** Le format est déjà spécifié,
   et il débloquerait la mesure des latences du §22.1 (T1, T3, T5),
   aujourd'hui invérifiables faute d'instrumentation. *Il l'a fait, et le
   verdict n'est pas celui qu'on espérait : voir §3.2.1.*
4. ~~**Latence du premier token (§22.1, T3)**~~ — **diagnostiqué et
   corrigé le 2026-07-26** (§3.2.2 et §3.2.3). T1 et T3 passent.
   Le raisonnement est également diffusé à l'affichage (§3.2.4) :
   18,3 s de silence supprimées sur `code_analysis`. Reste ouvert, plus
   petit : le chargement à froid du rôle `standard` (~6,5 s).
5. ~~**WebSocket (§24.2)**~~ — **fait le 2026-07-26**, les cinq
   événements vérifiés en réel (§3.3). Reste à en brancher une vue.
6. **`secret_scanner` (§17.1)** — le socle existe : `audit_log.redact()`
   couvre déjà la détection par motifs sur ce qui est journalisé. Reste à
   l'appliquer aux *fichiers* (T12).
7. **Résumé de contexte (§12)** — le plus coûteux, le moins urgent tant
   que les sessions restent courtes.

Non traité et assumé : §25 installation demande d'**exécuter**, pas de
lire. La compter conforme sur la seule foi du code serait exactement
l'erreur que relate le §0.
