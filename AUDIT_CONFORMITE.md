# Audit de conformité — Hermes Ollama vs cahier des charges condensé

**Date :** 2026-07-25
**Base auditée :** branche `claude/hermes-ollama-specs-v4-fa08ou`, 378 tests au vert
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
| **Divergence de nommage** (fonction présente, nom différent) | §6 Atlas, §6 Swift, §17 « HSE » |
| **Partiel** | §6 Kronos (pas de parallélisation), §12 mémoire, §13 base documentaire, §23 interface |
| **Absent** | §14 Git, §16 vérification (lint/build/tests), §6 Sentinel, §8 workflow de développement complet |

L'écart le plus coûteux n'est pas une fonctionnalité manquante : c'est le
**glissement de vocabulaire** entre le cahier des charges et le code (§2).
Il fait croire à des manques qui n'existent pas, et masque des manques qui
existent.

---

## 2. Divergences de nommage — à trancher en priorité

### 2.1 « HSE » désigne deux choses opposées

| Source | Signification | Emplacement |
|---|---|---|
| Cahier des charges §17 | **H**ermes **S**ecurity **E**ngine — moteur déterministe : permissions, risques, commandes, fichiers, secrets ; Phi4 consulté seulement en cas de doute | — |
| Code | **H**ermes **S**elf-**E**volution — extraction de compétences depuis les tâches terminées | `backend/self_evolution/`, outils `hse_process_task` / `hse_progression` |

**Le moteur de sécurité du §17 existe bel et bien** : c'est
`backend/security/aegis_engine.py`. Sa docstring décrit exactement le §17
(« rules engine on purpose, not an LLM call »), l'avis de
`phi4-reasoning:14b` ne peut qu'annoter un verdict, jamais le modifier.

→ **Rien à développer. Il faut choisir un vocabulaire.** Recommandation :
garder « moteur Aegis » pour la sécurité, renommer l'auto-évolution en
« HSE » explicité (*Self-Evolution*) partout, ou l'appeler autrement.
Laisser les deux sens coexister est le vrai risque.

### 2.2 Atlas et Swift ont échangé leurs rôles

| Agent | Rôle au cahier des charges §6 | Rôle réel dans `config/agents.yaml` |
|---|---|---|
| **Atlas** | Gestion documentaire : indexation, RAG, résumé, OCR, classification | *Developer agent* — analyse, génère, refactorise du code (`role: code`) |
| **Swift** | Exécution : fichiers, Git, Docker, terminal, scripts | Classification d'intention rapide (`role: swift`) |

Le rôle documentaire du CDC est en réalité assuré par **Minerva**
(recherche/RAG) et **Echo** (mémoire/indexation), deux agents absents du
cahier des charges. Le rôle d'exécution du CDC n'est couvert que
partiellement, par `backend/tools/file_tools.py` (écriture fichier sous
Aegis) — ni Git, ni Docker, ni terminal.

### 2.3 Sentinel n'existe pas comme agent

Le §6 le liste (surveillance, logs, performances, GPU, mémoire, alertes).
Le code a `backend/monitoring/gpu_monitor.py` et l'endpoint
`/system/status`, exposés dans le tableau de bord — la **fonction** est là,
l'**agent** non. À trancher : créer l'agent, ou retirer Sentinel du CDC et
assumer que le monitoring est un service, pas un agent.

### 2.4 Agents présents dans le code, absents du cahier des charges

`minerva` (recherche/RAG), `echo` (mémoire), `hermes_scribe` (rédaction),
`hermes_eyes` (vision). Tous fonctionnels et exposés en MCP. Le CDC devrait
les intégrer plutôt que les ignorer.

---

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

### 5.3 §13 Base documentaire — moitié présente

`memory_index(doc_id, text, ...)` prend du **texte déjà extrait**. Le
découpage, les embeddings, l'indexation et la recherche sémantique
fonctionnent. Il manque toute la couche d'entrée : PDF, DOCX, OCR,
images. Le §9 (« Import → OCR → Découpage → Embeddings ») s'arrête donc à
mi-parcours.

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

1. **Trancher le vocabulaire** (§2) — coût quasi nul, débloque toute
   lecture ultérieure du projet. À faire avant toute nouvelle feature.
2. **Ingestion documentaire** (§13) — valeur immédiate, risque faible,
   aucune interaction avec la sécurité.
3. **Module Git** (§14) — valeur élevée ; à cadrer (lecture seule d'abord,
   écriture derrière Aegis ensuite).
4. **Parallélisation des workflows** (§6) — gain de performance, périmètre
   contenu au moteur.
5. **Exécution de code** (§16) — le plus utile *et* le plus risqué.
   À ne faire qu'après 1-4, et strictement derrière `mandatory_validation`.
6. **Décision interface** (§23) — décision produit, pas technique.
