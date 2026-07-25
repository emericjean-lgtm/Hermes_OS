# Audit de conformité — Hermes Ollama vs cahier des charges condensé

**Date :** 2026-07-25
**Base auditée :** branche `claude/hermes-ollama-specs-v4-fa08ou`, 408 tests au vert
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
| **Implémenté (cette passe)** | §13 ingestion documentaire (hors OCR, voir §5.3) |
| **Partiel** | §6 Kronos (pas de parallélisation), §12 mémoire, §23 interface |
| **Absent** | §14 Git, §16 vérification (lint/build/tests), §8 workflow de développement complet |

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

### 5.1 §14 Gestion Git — absent

Aucun module Git dans `backend/`. Ni lecture de dépôt, ni branche, ni
commit, ni PR, ni rollback. C'est le manque le plus visible : le CDC y
consacre une section entière, et « jamais directement sur la branche
principale » est une règle qu'aucun code n'applique aujourd'hui.

### 5.2 §16 Vérification (lint / build / tests) — impossible en l'état

Le registre d'actions (`get_tool_registry()`) ne contient **aucun outil
d'exécution**. Hermes ne peut donc ni lancer les tests, ni compiler, ni
linter. Cela bloque mécaniquement :

- le §8 (workflow de développement : *Compilation → Tests*),
- le §16 en entier,
- le rôle d'exécution attendu de Swift (§6).

C'est aussi la limite assumée du workflow `new-app` livré récemment : il
**écrit** une application, il ne l'**exécute** pas.

Point de vigilance : ajouter l'exécution de code est le changement le plus
sensible du lot. Il doit passer par Aegis avec `mandatory_validation`, pas
être branché directement.

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

### 5.4 §6 Kronos — pas de parallélisation

`backend/workflows/engine.py` exécute les nœuds séquentiellement. Le CDC
demande explicitement la parallélisation. Les dépendances, priorités et la
reprise après portail de validation sont, elles, bien là.

### 5.5 §23 Interface — 11 vues attendues, 1 page réelle

`frontend/src/app/page.tsx` fait 105 lignes. Le tableau de bord réel est
aujourd'hui le plugin Hermes Agent (`config/hermes_agent_dashboard/`,
6 panneaux : système, lancement, projets, tâches, auto-évolution, activité
des agents). À trancher : abandonner le frontend Next.js et assumer le
plugin comme interface unique, ou le développer. Maintenir les deux à
moitié est le pire scénario.

### 5.6 §12 Mémoire — deux niveaux sur trois

Mémoire permanente (`episodic.py`, entrées datées et dédupliquées) et
mémoire documentaire (`semantic.py`) sont là. La **mémoire projet**
(architecture, roadmap, décisions) n'a pas de structure propre : elle
n'existe que comme entrées mémoire scopées par `project_id`.

---

## 6. Ordre de traitement recommandé

1. ~~**Trancher le vocabulaire** (§2)~~ — **fait le 2026-07-25.** Sigle
   « HSE » retiré, rôles d'agents actés. Reste à répercuter dans le
   cahier des charges lui-même (§6 et §17), qui est le document de
   l'utilisateur, pas du dépôt.
2. ~~**Ingestion documentaire** (§13)~~ — **fait le 2026-07-25.** PDF,
   DOCX et famille texte ingérables par chemin, sous Aegis. OCR écarté
   au profit du modèle de vision déjà présent (voir §5.3).
3. **Module Git** (§14) — valeur élevée ; à cadrer (lecture seule d'abord,
   écriture derrière Aegis ensuite). **Prochaine étape recommandée.**
4. **Parallélisation des workflows** (§6) — gain de performance, périmètre
   contenu au moteur.
5. **Exécution de code** (§16) — le plus utile *et* le plus risqué.
   À ne faire qu'après 2-4, et strictement derrière `mandatory_validation`.
6. **Décision interface** (§23) — décision produit, pas technique.
