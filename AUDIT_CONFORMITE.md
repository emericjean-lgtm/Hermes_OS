# Audit de conformité — Hermes Ollama vs cahier des charges v4.0

**Date :** 2026-07-26
**Référence :** `CAHIER_DES_CHARGES_HERMES_OLLAMA.md` v4.0 consolidée —
le document normatif versionné dans ce dépôt, lu intégralement
(1 195 lignes) avant toute conclusion.
**Base auditée :** branche `claude/hermes-ollama-specs-v4-fa08ou`,
611 tests au vert.

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
| **Absent** | §12 résumé de contexte · §18 log d'audit structuré · §19.3 snapshots/rollback · §24.2 WebSocket · §17.1 `secret_scanner` |
| **Écart assumé, à documenter** | §4.1 stack (LangChain, Watchdog, keyring, Telegram) · §23 interface |
| **Non vérifié** | §22.1 latences · §25 installation |

Le projet couvre la majeure partie du corps normatif. Les manques réels
sont peu nombreux, mais l'un d'eux — les snapshots — **casse un critère
d'acceptation explicite** (§28, T8).

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
| T12 secret ciblé → validation | ⚠️ partiel | `secret_modification` est en validation obligatoire, mais **aucun `secret_scanner`** ne détecte un secret ailleurs |
| **T8 reprise après interruption** | ❌ | **Aucun snapshot d'état** — voir §3.1 |
| **T11 3 tentatives + backoff** | ❌ | **Aucun retry** dans `ollama_client.py` |
| T1 premier token < 1 s | ⏳ | Non mesuré |
| T3 réutilisation du modèle chargé | ⏳ | Logique présente, non mesurée en conditions réelles |
| T5 recherche < 500 ms | ⏳ | Non mesuré |

---

## 3. Manques réels

### 3.1 §19.3 — Snapshots & rollback *(le plus grave)*

Le CDC exige un `snapshot_manager` sauvegardant l'état (tâches, contexte,
fichiers modifiés) toutes les N étapes, permettant reprise et annulation.

**Rien de tel n'existe.** Le seul « snapshot » du code est
`GpuMonitor.snapshot()` — de la télémétrie, sans rapport. Les seules
sauvegardes sont les backups de fichiers de `propose_write`.

Pourquoi c'est le plus grave : **T8 est un critère d'acceptation
explicite**, la réversibilité est le principe de conception n°4 (§7), et
le §19.2 promet « interruption de session → sauvegarde d'état » puis
« redémarrage → reprise au dernier point sûr ». Trois endroits du
document s'appuient dessus.

*Nuance :* les runs de workflow, eux, **sont** reprenables
(`run_store.py`, reprise après portail via `run_id`). La reprise existe
donc pour les workflows, pas pour les sessions ni les tâches.

### 3.2 §18 — Log d'audit structuré

Le §18 spécifie un format JSON précis : `routing_decision`,
`context_used`, `files_modified`, `tests_run`, `duration_ms`,
`tokens_used`, `tokens_per_second`, `vram_used_gb`, `result` — stocké en
table `audit_log` et en fichiers sous `data/logs/`.

**Il n'y a pas de table `audit_log`.** Les traces existent, dispersées :
bus de messages, historique des tâches, runs de workflow. Aucune ne porte
le format du §18, et les métriques de performance (`tokens_per_second`,
`duration_ms`) ne sont mesurées nulle part — ce qui explique aussi
pourquoi le §22.1 est invérifiable.

### 3.3 §24.2 — WebSocket

Cinq événements sont spécifiés (`system.metrics` toutes les 2 s,
`chat.token`, `agent.message`, `task.update`, `validation.request`).
**Aucune implémentation** : une seule mention, en commentaire, dans
`message_bus.py`. La statusbar temps réel du §23.1 en dépend.

### 3.4 §12 — Résumé automatique de contexte

Exigé : « résumer automatiquement le contexte trop long », « tronquer
intelligemment sans perte d'information critique ». **Aucun module.**

### 3.5 §17.1 — `secret_scanner`

L'arborescence §8.1 le prévoit, le §17.1 exige que les secrets
n'apparaissent jamais en clair dans les logs. **Absent.** La protection
repose aujourd'hui sur le fait que peu de choses sont journalisées.

### 3.6 §19.1 — Robustesse Ollama

« Ollama indisponible : attendre, retenter 3 fois (backoff), puis
notifier » (T11). `ollama_client.py` **ne réessaie pas** : une requête
échoue directement.

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

1. **`snapshot_manager` (§19.3)** — seul manque qui casse un critère
   d'acceptation, et trois sections du CDC s'appuient dessus.
2. **Retry Ollama avec backoff (§19.1, T11)** — quelques lignes, effet
   direct sur la fiabilité quotidienne.
3. **Log d'audit §18** — le format est déjà spécifié ; il débloquerait
   aussi la mesure des latences du §22.1, aujourd'hui invérifiables.
4. **WebSocket (§24.2)** — nécessaire à la statusbar temps réel.
5. **`secret_scanner` (§17.1)** — à cadrer : détection par motifs, ou
   redaction à l'écriture des logs.
6. **Résumé de contexte (§12)** — le plus coûteux, le moins urgent tant
   que les sessions restent courtes.

Non traité et assumé : §22.1 latences et §25 installation demandent de
**mesurer et d'exécuter**, pas de lire. Les compter conformes sur la
seule foi du code serait exactement l'erreur que relate le §0.
