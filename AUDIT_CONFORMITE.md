# Audit de conformité — Hermes Ollama vs cahier des charges condensé

**Date :** 2026-07-25
**Base auditée :** branche `claude/hermes-ollama-specs-v4-fa08ou`, 520 tests au vert
**Référence :** cahier des charges condensé (30 sections), à lire avec
`CAHIER_DES_CHARGES_HERMES_OLLAMA.md` (version longue historique)

Méthode : lecture du code réel (`backend/`, `config/`), exécution de la
suite de tests, interrogation des endpoints du backend en fonctionnement.
Aucune conformité n'est déclarée sur la seule foi d'un nom de fichier ou
d'un commentaire.

---

## 1. Synthèse

| Verdict | Sections |
|---|---|
| **Conforme** | §5 modèles, §10-11 gestion de projet/états, §17-18 sécurité, §19 journalisation, §20 bus, §21 routage, §26 API interne, §27 extensibilité |
| **Conforme après correction (cette passe)** | §22 optimisation VRAM |
| **Vocabulaire tranché et appliqué** (cette passe) | §17 « HSE » → moteur Aegis + auto-évolution, §6 Atlas/Swift/Sentinel |
| **Implémenté (cette passe)** | §13 ingestion documentaire (hors OCR), §14 Git (lecture + écriture), §6 parallélisation, §12 mémoire projet, §16 vérification, §8 chaîne de développement |
| **Partiel** | §23 interface |
| **Absent** | *(plus aucun manque de code — voir §6 pour ce qui reste)* |

L'écart le plus coûteux n'était pas une fonctionnalité manquante : c'était
le **glissement de vocabulaire** entre le cahier des charges et le code.
Il faisait croire à des manques inexistants (le moteur de sécurité du §17
était là depuis le début, sous le nom d'Aegis) tout en masquant les vrais
(§14 Git, §16 exécution). Ce point est traité en §2 — les décisions y sont
actées et appliquées au code, pas seulement documentées.

---

## 2. Vocabulaire — TRANCHÉ le 2026-07-25

Les décisions ci-dessous sont actées et appliquées au code. Elles priment
sur toute formulation antérieure du cahier des charges.

### 2.1 « HSE » est retiré du vocabulaire du projet — RÉSOLU

Le conflit : le cahier des charges §17 disait HSE = *Hermes **Security**
Engine* (moteur déterministe), le code disait HSE = *Hermes
**Self-Evolution*** (extraction de compétences). Deux sens opposés pour
un même sigle.

**Décision :**

| Concept | Nom retenu | Emplacement |
|---|---|---|
| Moteur de sécurité déterministe (ex-§17 « HSE ») | **moteur Aegis** | `backend/security/aegis_engine.py`, outil `security_evaluate` |
| Extraction de compétences (ex-« HSE » du code) | **auto-évolution** (*self-evolution*) | `backend/self_evolution/`, outils `evolution_*` |

Le sigle « HSE » n'apparaît plus nulle part dans le code. « Aegis » l'a
emporté pour la sécurité parce qu'il était déjà cohérent partout et qu'il
est plus distinctif ; l'auto-évolution a cédé le sigle parce qu'elle est
le concept le plus récent et le moins structurant.

**Renommages appliqués** (surface publique — changement cassant assumé) :

| Avant | Après |
|---|---|
| outil MCP `hse_process_task` | `evolution_process_task` |
| outil MCP `hse_progression` | `evolution_progression` |
| `POST /hse/process/{task_id}` | `POST /evolution/process/{task_id}` |
| `GET /hse/progression` | `GET /evolution/progression` |
| `backend/api/routes/hse.py` | `backend/api/routes/evolution.py` |
| paramètre `run_hse` | `run_evolution` |
| clé de réponse `"hse"` | `"evolution"` |

Impact réel limité : aucun outil `hse_*` ne figurait dans la liste
`tools.include` de l'intégration Telegram. Le plugin du tableau de bord,
seul consommateur externe de `/hse/progression`, a été mis à jour et
vérifié en fonctionnement.

Vérifié : `/hse/progression` répond 404, `/evolution/progression` répond
200 avec les vraies données, `tools/list` du serveur MCP n'expose plus
aucun `hse_*`, le panneau *Self-Evolution* du tableau de bord fonctionne.
378 tests au vert.

### 2.2 Atlas et Swift — le code fait foi, le CDC s'aligne

**Décision : les rôles du code sont conservés tels quels.** Ils sont
implémentés, testés et en service ; ceux du cahier des charges sont pour
partie aspirationnels. Renommer un agent qui fonctionne pour libérer un
nom au profit d'un exécuteur qui n'existe pas encore serait du churn pur.

Le cahier des charges §6 doit donc être corrigé ainsi :

| Agent | Rôle officiel (retenu) |
|---|---|
| **Atlas** | Agent de développement — analyse, génère, refactorise du code |
| **Swift** | Classification d'intention rapide (pré-passe de routage) |
| **Minerva** | Recherche & RAG sur documents locaux *(à ajouter au CDC)* |
| **Echo** | Mémoire & compétences — indexation, rappel *(à ajouter au CDC)* |
| **Hermes Scribe** | Rédaction & documentation *(à ajouter au CDC)* |
| **Hermes Eyes** | Vision — images et captures d'écran *(à ajouter au CDC)* |
| **Sentinel** | *N'est pas un agent* — le monitoring est un service (`backend/monitoring/`, `/system/status`) |

Le rôle documentaire que le CDC attribuait à Atlas est en réalité couvert
par Minerva + Echo. Le rôle d'exécution qu'il attribuait à Swift n'existe
pas encore (voir §5.2 : pas d'outil d'exécution).

### 2.3 Pourquoi ce glissement s'était produit

Pour mémoire, l'écart constaté avant décision : le CDC attribuait à Atlas
la gestion documentaire (indexation, RAG, OCR) et à Swift l'exécution
(fichiers, Git, Docker, terminal). Le code avait fait diverger ces deux
noms vers, respectivement, l'agent de développement et le classifieur
d'intention — et avait ajouté quatre agents que le CDC ne mentionnait pas
(Minerva, Echo, Scribe, Eyes). Sentinel, lui, n'a jamais été implémenté
comme agent : seule sa fonction existe, sous forme de service de
monitoring.

## 3. Conforme — vérifié

### §5 Architecture IA — correspondance exacte

Les 7 rôles du tableau du CDC sont dans `config/models.yaml`, aux modèles
prescrits : Hermes 4 14B (orchestrateur), Qwen3.5 9B (conversation),
Qwen3-Coder 30B (développement), DeepSeek R1 14B (raisonnement/QA),
Phi4 Reasoning 14B (sécurité), Gemma4 12B (vision), Nomic (embeddings).
Aucun nom de modèle n'est codé en dur ailleurs.

### §11 États d'une tâche — surensemble

`TaskStatus` (`backend/tasks/task_manager.py`) définit 10 états là où le
CDC en liste 8, dont `reversible`, `partially_successful` et `to_resume`
— utiles et absents du CDC.

### §17-18 Sécurité

`aegis_engine.py` + `permission_matrix.py` + `config/security.yaml` :
matrice de permissions, `mandatory_validation` pour les actions critiques,
niveaux d'autonomie, `ALLOWED_PATHS`. Le hook `pre_tool_call` d'Hermes
Agent y est branché — vérifié en conditions réelles : un appel `terminal`
natif a bien été bloqué en `require_human_validation`.

### §20 Bus inter-agents

`backend/core/message_bus.py` — chaque message porte origine, destination,
type, payload, horodatage, `task_id`, `project_id`. Désormais visible dans
le tableau de bord (panneau *Agent activity*).

### §21 Gestion des modèles

`backend/core/router.py` : matrice `task_type → rôles candidats`, sélection
du premier rôle dont le modèle tient dans la VRAM disponible, repli sur le
plus petit sinon, avec une `reason` traçable.

### §27 Extensibilité

`config/agents.yaml` est un registre déclaratif avec `enabled: false` pour
les agents non encore implémentés. Ajouter un agent = une entrée de config
+ une classe. Conforme à l'intention.

---

## 4. Corrigé pendant cet audit

### §22 Optimisation VRAM — les modèles « toujours chargés » ne l'étaient pas

**Constat.** `config/models.yaml` décrivait `swift` et `embedding` comme
« Kept loaded at all times », mais rien ne l'appliquait :

- `OllamaClient` envoyait un unique `keep_alive` global (`10m`) pour
  *tous* les modèles, y compris `swift` ;
- le chemin embeddings (`OllamaEmbeddingFunction`, qui contourne
  volontairement `OllamaClient`) n'envoyait **aucun** `keep_alive` — donc
  `nomic-embed-text` retombait sur le défaut court d'Ollama.

Conséquence : après un creux d'activité, chaque classification et chaque
requête RAG payait un rechargement à froid — exactement ce que le §22
(« conserve les modèles rapides en mémoire ») cherche à éviter.

**Correctif.** Drapeau structuré `always_loaded: true` sur les rôles
concernés dans `models.yaml` ; `OllamaClient` résout `keep_alive` par
modèle (`-1` = épinglé) ; `OllamaEmbeddingFunction` transmet désormais son
`keep_alive`. Drapeau explicite plutôt qu'inféré de `tier: turbo` :
`double_check` est turbo lui aussi, et épingler un troisième modèle
mangerait la marge que le budget 16 Go n'a pas.

7 tests de non-régression ajoutés (`test_always_loaded_models.py`), dont
deux qui vérifient la valeur **sur le fil** et pas seulement dans le
helper. Suite complète : 378 au vert.

---

## 5. Manques réels, par ordre de valeur

### 5.1 §14 Gestion Git — FAIT le 2026-07-25 (lecture + écriture)

**Était :** aucun module Git. Ni lecture, ni branche, ni commit, ni PR,
ni rollback — et « jamais directement sur la branche principale » n'était
appliqué par aucun code.

**Ajouté (lecture seule) :** `backend/tools/git_tools.py`, les outils MCP
`git_status` / `git_log` / `git_branches` / `git_diff`, et les routes
`GET /git/*`. Aucune dépendance nouvelle : le binaire `git` est déjà
requis pour utiliser ce dépôt, ce qui évite d'ajouter GitPython pour
quatre commandes de lecture.

Trois points de conception qui méritent d'être connus :

1. **Ce n'est pas `system_command`.** Aegis classe `system_command` en
   `mandatory_validation` parce que l'exécution shell arbitraire est
   illimitée. Ici, chaque commande est une **liste argv constante écrite
   dans le fichier**, lancée avec `shell=False` ; la seule valeur fournie
   par l'appelant est le chemin du dépôt, qui passe par le contrôle
   `ALLOWED_PATHS` *avant* que git ne soit invoqué. Il n'y a aucune
   interpolation de chaîne dans une commande, donc rien à injecter.
   Classer `git status` en `system_command` imposerait une validation
   humaine à chaque lecture — ce qui entraînerait l'utilisateur à cliquer
   « oui » machinalement, exactement l'inverse du but de la catégorie.
   Un test vérifie l'invariant (`shell=False`, argv toujours une liste).

2. **La règle « jamais sur la branche principale » est déjà codée**, alors
   qu'aucune écriture n'existe encore : `is_protected_branch()` reconnaît
   `main`, `master`, `production`, `prod`, y compris sous forme qualifiée
   (`refs/heads/main`, `origin/main`). Une future écriture qui se
   contenterait de comparer la chaîne `"main"` passerait à côté d'une ref
   qualifiée — c'est précisément le cas que le §14 veut empêcher. Le
   champ `protected` est exposé sur `/git/status`, donc un appelant sait
   *avant* d'agir.

3. **Sortie bornée** : `git diff` est tronqué à 20 000 caractères, parce
   que cette sortie finit généralement dans une fenêtre de contexte LLM.

Vérifié en réel sur ce dépôt même : `status` détecte exactement les
fichiers modifiés et non suivis, `log` et `branches` renvoient les vraies
données, `C:/Windows` est refusé en `403`, un dossier non-dépôt en `400`.
35 tests, construits sur de **vrais dépôts jetables** avec le vrai binaire
git — le risque de ce module est le parsing de la sortie de git, et un
mock n'aurait fait que confirmer mes propres suppositions de format.

**Phase 2 (écriture) — FAITE le 2026-07-25.** `create_branch`,
`commit`, `push`, `revert_commit`, `create_pull_request`, exposés en MCP
(`git_*`) et en REST (`POST /git/*`).

Le modèle de sécurité tient en trois niveaux :

1. **Interdictions dures**, refusées par le module *avant* même de
   consulter Aegis, parce que le CDC les formule comme des interdits et
   non comme des permissions à arbitrer : commiter sur une branche
   protégée, pousser sur une branche protégée (§14), et créer une branche
   portant un nom protégé. Un refus arbitré serait un prompt qu'on finit
   par valider machinalement ; un interdit n'est pas négociable.
2. **`git_critical`** pour l'ouverture de pull request — action tournée
   vers l'extérieur (elle publie et notifie des gens), donc
   `mandatory_validation` à *tout* niveau d'autonomie (§18).
3. **`git_operation`** pour le reste. Avec l'`autonomy_level: low` livré
   par défaut, cela signifie déjà `require_human_validation` : rien de
   mutant ne se produit sans supervision, sans configuration
   supplémentaire. Vérifié en réel.

Deux absences volontaires, testées comme telles :

- **Aucun paramètre `force`** sur `push`. Le §18 range la « suppression
  Git critique » parmi les interdits permanents, et un `force=True`
  mettrait le cas destructeur à une frappe du cas sûr. Un test vérifie
  que le paramètre n'existe pas.
- **Aucun `git reset --hard`.** Le rollback du §14 est assuré par
  `revert_commit`, qui *ajoute* un commit annulant un autre : réversible,
  et incapable de perdre du travail déjà commité. Un test vérifie que
  l'historique grandit au lieu de rétrécir.

Vérifié en conditions réelles à travers la couche MCP : commit sur `main`
refusé (`deny`), push vers `main` refusé, création d'une branche nommée
`main` refusée, et création d'une branche ordinaire renvoyant
`require_human_validation` du fait de l'autonomie basse. 27 tests
supplémentaires (18 sur les garde-fous, 9 sur la surface REST).

### 5.2 §16 Vérification (lint / build / tests) — FAIT le 2026-07-25

**Était :** le registre d'actions ne contenait aucun outil d'exécution.
Hermes ne pouvait ni lancer les tests, ni compiler, ni linter — ce qui
bloquait mécaniquement le §16 entier, le §8 (*Compilation → Tests*) et le
rôle d'exécution attendu de Swift.

**Fait :** `backend/tools/verification.py`, les outils MCP
`verification_runners` / `verification_run`, et les routes
`GET /verification/runners` + `POST /verification/run`.

#### Ce que ce module ne fait pas

**Il n'exécute pas de commandes.** L'appelant *nomme* un runner déclaré
dans `config/verification.yaml` et ne peut rien transmettre d'autre : ni
commande, ni argument, ni variable d'environnement, ni shell. Aucun
chemin de code ne transforme une entrée d'appelant en jeton exécutable.
Un test vérifie la **signature** de `run()` elle-même et échouerait si
quelqu'un ajoutait un paramètre `args` « par commodité » — c'est
exactement ainsi qu'une whitelist redevient un shell.

Deux règles écrites dans le fichier de config et vérifiées par des tests :
aucun runner ne prend d'argument fourni par l'appelant (`npm run
<script>` avec un script au choix rendrait joignable tout le
`package.json` — le nom est donc figé), et aucun n'invoque de shell, de
`-c` ou de `-e`.

#### Ce qu'il fait malgré tout

Lancer `pytest` dans un dossier exécute le `conftest.py` et les tests
**de ce dossier**. La commande est figée, mais le code qui tourne
appartient au projet cible. C'est de la vraie exécution — d'où une
nouvelle catégorie `verification_run` dans `config/security.yaml` :

- `mutating: true` — une suite de tests écrit (caches, couverture,
  artefacts). La marquer non mutante l'aurait rendue auto-autorisée à
  *tous* les niveaux d'autonomie, ce qui serait faux.
- `path_based: true` — confinée à `ALLOWED_PATHS`.
- `min_autonomy_for_auto_allow: high`, et non `medium` : à
  l'`autonomy_level: low` livré, **chaque appel exige une validation
  humaine**. Passer l'autonomie à `high` est la façon dont un opérateur
  choisit délibérément des vérifications automatiques ; ce n'est pas le
  défaut.

Trois limites supplémentaires : délai maximal (une suite bloquée ne peut
pas retenir un thread indéfiniment), troncature de sortie **conservant la
tête *et* la queue** (la ligne « N failed » est tout en bas ; une
troncature naïve jette la seule ligne qui compte), et `shell=False` avec
argv figé.

Vérifié en réel : les 7 runners listés ; `POST /verification/run` sur ce
dépôt renvoie `ran=false`, `require_human_validation` (« needs autonomy
level 'high'… current level is 'low' ») ; un runner hors whitelist est
refusé en `400` avec la liste des noms valides ; et avec l'autonomie
relevée **en mémoire seulement**, une suite jetable est réellement
exécutée et rapporte `1 failed, 1 passed` — `config/security.yaml` reste
à `low`. 18 tests ajoutés.

**§8 refermé, et le §6 enfin exploité.** `new-app` a été étendu : il
génère désormais aussi une suite de tests (`scaffold_tests`), l'écrit
derrière un troisième portail humain (`save_tests`), puis l'exécute
réellement (`verify`, runner `pytest`). La chaîne « Compilation → Tests »
du §8 est donc complète.

Deux effets notables :

- **Le workflow a maintenant de vraies vagues parallèles**, alors
  qu'aucun n'en avait : `review_code` et `scaffold_tests` ne dépendent
  tous deux que de `scaffold`, et `save_code`/`save_tests` se présentent
  ensemble — soit une seule ronde d'approbation pour les deux écritures
  au lieu de deux successives. Vérifié par `simulate` : vagues 5 et 6.
- **L'arête `verify → backlog` est `always`, pas `on_success`.** Une
  vérification refusée ou en échec est précisément ce que la tâche de
  backlog doit consigner. Au niveau d'autonomie livré, `verify` renvoie
  `ran: false` ; le rapport doit le dire tel quel plutôt que de laisser
  croire que le code est vérifié — c'est écrit dans le brief du nœud
  `report`.

### 5.3 §13 Base documentaire — RÉSOLU le 2026-07-25 (sauf OCR)

**Était :** `memory_index(doc_id, text, ...)` ne prenait que du texte
**déjà extrait**. Toute la couche d'entrée manquait, donc le §9
(« Import → Découpage → Embeddings ») s'arrêtait à son premier mot.

**Ajouté :** `backend/documents/extractor.py` + l'outil MCP
`documents_index` + les routes `POST /documents/index` et
`GET /documents/formats`. On passe désormais un **chemin de fichier** ;
lecture (sous Aegis), extraction, découpage, embeddings et indexation
s'enchaînent.

Formats couverts : `.pdf`, `.docx`, et toute la famille texte (`.md`,
`.txt`, `.json`, `.yaml`, `.csv`, plus une trentaine d'extensions de
code). Deux dépendances pures Python ajoutées (`pypdf`, `python-docx`),
importées **paresseusement** : sans elles, la famille texte fonctionne
toujours et PDF/DOCX échouent avec un message d'installation, au lieu de
casser l'import de tout le module.

Codes d'erreur volontairement distincts, parce qu'ils appellent des
réactions différentes : `403` (Aegis refuse), `404` (fichier absent),
`415` (format jamais supporté), `501` (format supporté, bibliothèque
manquante), et un `indexed: false` explicite avec `reason` quand un PDF
scanné ne contient aucune couche de texte — plutôt que d'indexer un
document vide qui ne matcherait jamais.

Vérifié en réel : le cahier des charges long (59 305 caractères) indexé en
19 chunks, retrouvé ensuite par recherche sémantique avec son
`source_path` ; un chemin hors `ALLOWED_PATHS` refusé en `403`. 30 tests
ajoutés (408 au total).

**Reste non fait — l'OCR.** Les images sont refusées avec un renvoi
explicite vers `analyze_image` : ce projet a déjà un modèle de vision
(gemma4) qui lit des schémas et des captures d'écran, pas seulement des
glyphes. Ajouter une pile tesseract serait une dépendance système plus
lourde pour un résultat plus étroit. À reconsidérer seulement si des PDF
scannés en volume deviennent un vrai besoin.

### 5.4 §6 Kronos — parallélisation FAITE le 2026-07-25

**Était :** `engine.py` exécutait les nœuds un par un. Les dépendances,
priorités et la reprise après portail étaient déjà là ; seule la
simultanéité manquait.

**Fait :** la boucle calculait déjà `_ready_nodes()`, c'est-à-dire
l'ensemble des nœuds dont tous les prédécesseurs sont terminés — soit
exactement une *vague* parallélisable. Elle les exécute désormais
ensemble via `asyncio.gather`. Par construction, aucun nœud d'une vague
ne dépend d'un autre de la même vague, donc la résolution des
placeholders `$steps.` ne peut pas courir après un résultat manquant.

Quatre points de conception :

1. **Concurrence bornée** (`workflow_max_parallel`, défaut 4). Les nœuds
   appellent des outils adossés à des LLM : un éventail non borné
   demanderait à Ollama de tenir plusieurs modèles à la fois et ferait
   swapper un budget VRAM de 16 Go — transformant un gain de
   parallélisme en perte. Régler à `1` restaure exactement l'ancien
   comportement séquentiel ; un test le vérifie.
2. **Ordre des résultats déterministe.** Les résultats sont réécrits dans
   l'ordre de la vague, pas dans l'ordre d'arrivée : le dictionnaire est
   persisté, et un ordre dépendant de quel outil a fini en premier
   rendrait deux runs identiques non reproductibles.
3. **Isolation des échecs.** Un nœud qui échoue ne fait pas perdre les
   résultats de ses voisins de vague — `return_exceptions=True`, et une
   exception qui s'échapperait de `_execute_node` (ce serait un bug du
   moteur) devient un nœud `failed` portant le message, plutôt que la
   perte du run entier.
4. **Les portails de validation bloquent toujours.** Un nœud en attente
   n'est pas emporté par un voisin parallèle : il reste
   `awaiting_validation` et tout son aval reste `skipped`.

`simulate()` expose maintenant `execution_waves` et `max_parallel` (MCP et
REST) : `execution_order`, à lui seul, ne permettait pas de voir si un
workflow se parallélisera.

**Constat honnête sur le gain réel :** les deux workflows livrés sont des
chaînes strictement linéaires — `new-app` donne huit vagues d'un nœud,
`full-code-review` quatre. **Ils ne gagnent donc rien.** La capacité est
vérifiée de bout en bout sur un graphe en éventail créé pour l'occasion
(3 analyses en une vague, run réel `completed`), mais tirer parti du §6
demandera d'écrire des workflows réellement branchés. 9 tests ajoutés,
dont ceux qui mesurent le recouvrement effectif plutôt que le seul
résultat — un test qui ne vérifierait que les résultats passerait aussi
bien contre l'ancien moteur séquentiel.

### 5.5 §23 Interface — 11 vues attendues, 1 page réelle

`frontend/src/app/page.tsx` fait 105 lignes. Le tableau de bord réel est
aujourd'hui le plugin Hermes Agent (`config/hermes_agent_dashboard/`,
6 panneaux : système, lancement, projets, tâches, auto-évolution, activité
des agents). À trancher : abandonner le frontend Next.js et assumer le
plugin comme interface unique, ou le développer. Maintenir les deux à
moitié est le pire scénario.

### 5.6 §12 Mémoire — FAIT le 2026-07-25

**Était :** le stockage existait (`memory_long` avec sa colonne
`project_id`), mais rien ne distinguait les trois niveaux du §12 : `type`
est une chaîne libre, sans vocabulaire ni validation, donc « architecture
de ce projet » et « préférence permanente de l'utilisateur » étaient des
lignes indiscernables. Et rien ne permettait de charger la mémoire d'un
projet *comme un tout* avant de travailler dessus.

**Fait :** `backend/memory/project_memory.py` ajoute le vocabulaire du
§12 (`architecture`, `roadmap`, `decision`, `documentation` pour le
niveau projet ; `preference`, `habit`, `rule`, `history` pour le
permanent) et une lecture groupée, exposée en MCP
(`memory_project_brief`, `memory_known_types`) et en REST
(`GET /memory/project/{id}`, `GET /memory/types`).

Trois partis pris :

- **Aucune validation qui rejette un type inconnu.** Un vocabulaire qui
  casse les données existantes au moment de son introduction est une
  migration, pas un vocabulaire. Un type hors liste est classé
  `unclassified` et **remonte dans `other`** plutôt que d'être ignoré —
  un type mal orthographié rendrait sinon l'entrée invisible, le pire
  échec possible pour une mémoire.
- **Les quatre sections sont toujours présentes**, même vides, pour que
  l'appelant affiche une structure stable sans tester l'absence de clés.
- **La mémoire permanente n'est pas fondue dans le brief projet**, bien
  qu'elle s'applique aussi : mélanger les deux est la façon dont une
  décision propre à un projet finit par être appliquée partout.

La **mémoire courte** (§12, conversation en cours) reste volontairement
hors périmètre : le runtime d'agent possède déjà sa session, et la
dupliquer ici créerait deux sources de vérité pour le même tour.

#### Bug préexistant trouvé au passage — dérive de schéma

En testant en conditions réelles, toute requête mémoire scopée projet
échouait : `no such column: memory_long.project_id`. La table avait été
créée **avant** l'ajout de `project_id` au modèle, et
`Base.metadata.create_all()` ne crée que les tables *manquantes* — il ne
touche jamais une table existante. `memory_long` était la seule table
concernée ; toutes les autres avaient bien leur colonne.

Le bug était invisible depuis les tests, qui construisent une base neuve
à chaque fois et voyaient donc toujours le schéma courant. Autrement dit :
la fonctionnalité était cassée en production et verte en CI.

`init_db()` réconcilie désormais les colonnes manquantes, **en ajout
seulement** : colonnes nullables uniquement, jamais de suppression, de
renommage ni de changement de type — donc aucune perte possible, ce qui
la rend sûre à exécuter à chaque démarrage sans outil de migration. Une
colonne `NOT NULL` manquante est *signalée* et laissée telle quelle :
elle demande un défaut et une décision de backfill, c'est-à-dire une
vraie migration, pas quelque chose à improviser au boot. `init_db`
importe aussi explicitement tous les modules de modèles, pour que le
schéma ne dépende plus de l'ordre des imports de l'appelant — le couplage
invisible qui avait laissé `memory_long` dériver.

Vérifié en réel : la base en service a reçu sa colonne au redémarrage,
sans perte, et le brief projet renvoie ses sections correctement
groupées. 23 tests ajoutés (18 mémoire projet, 5 réconciliation).

---

## 6. Ordre de traitement recommandé

1. ~~**Trancher le vocabulaire** (§2)~~ — **fait le 2026-07-25.** Sigle
   « HSE » retiré, rôles d'agents actés. Reste à répercuter dans le
   cahier des charges lui-même (§6 et §17), qui est le document de
   l'utilisateur, pas du dépôt.
2. ~~**Ingestion documentaire** (§13)~~ — **fait le 2026-07-25.** PDF,
   DOCX et famille texte ingérables par chemin, sous Aegis. OCR écarté
   au profit du modèle de vision déjà présent (voir §5.3).
3. ~~**Module Git** (§14)~~ — **fait le 2026-07-25.** Lecture et
   écriture, avec les interdits §14/§18 appliqués de façon déterministe.
4. ~~**Parallélisation des workflows** (§6)~~ — **fait le 2026-07-25.**
   Reste à en tirer parti : les workflows livrés sont linéaires.
5. ~~**Exécution de code** (§16)~~ — **fait le 2026-07-25**, derrière une
   whitelist de runners et une validation humaine au niveau d'autonomie
   livré.
6. **Décision interface** (§23) — décision produit, pas technique.
