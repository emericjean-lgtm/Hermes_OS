# Roadmap — Hermes OS

> **État réel du dépôt au 2026-08-15, après HOS-111.**
>
> La version précédente de ce fichier était figée à HOS-065B (2026-07-30) :
> quarante-cinq jalons livrés depuis n'y figuraient pas, ses métriques
> annonçaient 3 358 tests là où le dépôt en contient 4 112, et le backlog
> frontend relevé le 2026-08-13 n'y était pas reporté. Un document de
> référence en retard sur le code fait manquer du travail — c'est ce qui
> est arrivé.

---

## L'objectif

Hermes Agent (NousResearch) est le cerveau des missions. Hermes OS est son
système d'exploitation : runtime, workspace, modèles, sécurité,
persistance, observabilité et interface. Voir `VISION.md` pour la vision
longue, `CLAUDE.md` pour les règles qui priment.

Le projet est **conforme** au sens du cahier des charges §28.1 quand
Hermes sait :

| Critère §28.1 | État |
|---|---|
| Répondre à une demande simple en < 5 s | ✅ mesuré (594-615 ms au premier token) |
| Choisir automatiquement un modèle adapté | ⚠️ le catalogue est mesuré, le routage par difficulté n'est pas câblé |
| Utiliser la mémoire pertinente sans tout réinjecter | ✅ HOS-097/098 |
| Analyser un document local et en extraire une synthèse | ✅ |
| **Résumer un contexte long de manière cohérente** | ❌ **aucun module — §12 jamais construit** |
| Proposer un plan d'action explicite et validable | ✅ |
| Modifier un fichier autorisé, diff avant application | ✅ `propose_write` |
| Exécuter lint/tests et rapporter le résultat | ✅ |
| Signaler une erreur avec son contexte d'échec | ✅ |
| Demander validation avant action sensible | ✅ Aegis |
| Reprendre une mission après interruption | ✅ `snapshot_manager`, T8 vérifié |
| Garder des traces lisibles de chaque session | ✅ `audit_log` |
| Fonctionner sur des projets variés sans reconfiguration lourde | ✅ |
| Exploiter la RX 6800 sans configuration manuelle | ⚠️ vrai en usage, **non vérifié à l'installation** (§25) |

Deux critères ne sont pas tenus, un troisième n'est pas vérifiable tant
que l'installation n'a pas été rejouée sur une machine nue.

---

## Où en est le projet

| Métrique | Valeur | Mesuré le |
|---|---|---|
| Jalons HOS livrés | HOS-000 → HOS-111 | 2026-08-15 |
| Tests collectés | **4 112** | 2026-08-15 |
| — boucle courte (`pytest`) | 3 839 | |
| — intégration réelle (`pytest -m lent`) | 273 | |
| Modules Python | 669 (~112 300 lignes) | 2026-08-15 |
| Frontend `src/` | 64 fichiers (~15 400 lignes), 22 features | 2026-08-15 |
| Modèles au catalogue, tous axes mesurés | 10 | 2026-08-14 |

**Correction par rapport à l'édition précédente :** elle annonçait 796
tests backend et 2 497 dans `tests/`, pour un total de 3 358. Le chiffre
réel est 4 112 — et jusqu'à HOS-111, `pytest.ini` n'en exécutait que
1 190, soit 29 %. Les 2 869 autres n'étaient lancés par personne ; ils
cachaient 33 échecs, dont un vrai défaut fonctionnel.

---

## Ce qui reste — ordre recommandé

L'ordre n'est pas une préférence : **ACP commande le frontend**, et le
catalogue déjà payé ne sert à rien tant que le routage ne le lit pas.

| # | Chantier | Pourquoi à ce rang |
|---|---|---|
| 0 | Committer HOS-110 et HOS-111 | en cours, rien ne doit rester non commité |
| 1 | **Débloquer ACP** — ou décider de l'abandonner | verrou de tout le chantier C et de J-3 |
| 2 | Routage par difficulté + coût de bascule | indépendant, peu coûteux, exploite un catalogue déjà payé |
| 3 | Frontend — Mission Center, Autonomous Center | dépend de 1 |
| 4 | Installation et distribution (`.exe`) | indépendant, gros, jamais commencé |
| 5 | Dette v1.0 (Phase 9) | 13 lignes, aucune bloquante isolément |
| 6 | §12 — résumé de contexte | critère d'acceptation non tenu, le plus coûteux |
| 7 | Telegram, voix | confort, une fois le reste stable |

---

## A. Livré le 2026-08-15 ✅

| Réf. | Contenu |
|---|---|
| HOS-110 | Bancs vision et raisonnement entrés au dépôt, avec leurs tests (35 + 14) |
| HOS-111 | `pytest.ini` sur les deux répertoires, 33 tests réparés, `tests/integration` marqué `lent` |
| HOS-112 | Délai de garde, fixtures rendues hermétiques, garde réseau de session, cinq tests d'ordre stabilisés |
| HOS-113 | Étape de mission bornée ; deux « défauts » de HOS-112 réfutés et amendés ; vrai blocage ACP localisé |

**Boucle courte : 3 841 passés, 3 ignorés, code de sortie 0.**
Commits `794f7df`, `a684c02`, `dee1e28`, `de93d24`, `f67c031`.

### HOS-112 — une suite qui pend ne dit rien ✅ partiellement

Découvert le 2026-08-15 en tentant de confirmer HOS-111. Deux exécutions
de `pytest` se sont figées : 92 minutes pour l'une, 15 pour l'autre, en
consommant respectivement 58 et 12 secondes de CPU. Elles n'échouaient
pas — elles attendaient.

**Le garde-fou d'abord.** `pytest.ini` déclare `timeout = 60`. C'est le
point le plus important : sans lui ce défaut restait invisible, parce
qu'une suite bloquée ne produit aucun message. C'est le pendant exact de
la règle du projet — on ne croit pas un succès sur parole, et on ne lit
pas un silence comme du travail en cours.

**Cause : un fixture qui en masque un autre.** `backend/tests/conftest.py`
fournit un `client` hermétique qui injecte `FakeOllamaClient`.
`test_chat_audit.py` définissait **son propre fixture du même nom**, sans
doublure : chaque `POST /chat` partait vers un vrai Ollama. Même schéma
pour `test_documents_endpoint.py`, dont un test atteignait la vraie
`OllamaEmbeddingFunction` — laquelle ouvre son propre `httpx.Client`,
hors de portée du client injecté.

**Et une famille de tests instables.** À chaque exécution, deux tests
d'ordre chronologique rendaient un verdict tiré au sort, jamais les
mêmes. Cause unique : **l'horloge Windows avance par pas de ~15,6 ms**,
donc deux créations consécutives partagent leur horodatage et le tri
devient une égalité. Cinq tests corrigés par des dates distinctes ; deux
faux positifs écartés sur lecture. Un défaut de production au passage :
`list_projects` triait sans départage, la liste pouvait se réordonner
d'un affichage à l'autre.

**État : `backend/tests` est verte — 1 239 passés, 2 ignorés, 2 min 34,
plus aucun blocage.**

### T-0 — la boucle courte est verte ✅

**3 836 passés, 3 ignorés, 4 min 28** sur les deux répertoires. Une garde
de session (`conftest.py`) refuse désormais toute connexion vers un
service réel pendant la boucle courte, et les tests `lent` en sont
exemptés. `VISION.md` promettait des tests sans réseau depuis le début ;
c'est maintenant vérifié à chaque exécution plutôt qu'affirmé.

**Trois fichiers certifiaient une herméticité qu'ils n'avaient pas** :
`test_alexandrie_integration.py` (« *CI-safe* » alors que `hybrid_search`
fait de vraies requêtes HTTP avec retries), `test_autonomous_real_wiring.py`
(« *Fully hermetic… no real Ollama* »), et le fixture de `test_chat_audit.py`
qui masquait l'hermétique de `conftest.py` en portant le même nom.

### T-1 — traité, et deux tiers réfutés ✅ (HOS-113)

Cette ligne annonçait **trois** défauts de production. La lecture du code
en a réfuté deux ; l'erreur venait d'un diagnostic tiré d'un vidage de
pile, sans vérification de ce qu'il valait en production. Le détail est
amendé au CHANGELOG plutôt que réécrit.

| Réf. | Verdict |
|---|---|
| T-1a | ⚠️ **Défaut de couplage, pas d'exécution.** En production une seule application existe et le composition root installe le moteur voulu. `reset_engine()` donne une couture explicite ; la forme de fond rejoint **M-8**, même défaut |
| T-1b | ✅ **Réel, corrigé.** `as_completed` sans délai — et une seconde attente non vue : sortir d'un `with ThreadPoolExecutor` joint tous les fils. Les deux traitées. `STEP_TIMEOUT_S = 1200` s, au-dessus des 900 s d'un agent, avec un test qui tient la relation |
| T-1c | ❌ **Pas un défaut.** Un fil démon par *instance* d'exécuteur, arrêté par `close()`, que le `shutdown()` du bootstrap appelle bien. Les 55 fils étaient 55 exécuteurs construits par des tests qui n'arrêtaient jamais leur application |

### T-2 — l'ordre chronologique, correctif de fond 🟡

Les pauses de 20 ms posées en HOS-112 rendent les tests déterministes ;
elles ne suppriment pas l'ambiguïté. La vraie réponse est de persister une
**séquence explicite** plutôt que de se fier à l'horloge, comme
`test_turn_order_survives_a_shared_timestamp` le fait déjà pour les
conversations. Changement de schéma par module concerné (episodic,
snapshots, tâches, projets, objectifs).

---

## B. Cahier des charges — ce qui n'est pas tenu

| § | Exigence | État |
|---|---|---|
| **12** | Résumer automatiquement un contexte trop long, tronquer sans perte critique | ❌ **aucun module.** Critère d'acceptation §28.1 explicite |
| 17.1 | `secret_scanner` — les secrets ne doivent jamais apparaître en clair | ⚠️ `audit_log.redact()` couvre les logs ; **rien ne scanne les fichiers** (T12) |
| 22.1 | Recherche < 500 ms (T5) | ⏳ jamais mesuré |
| **25** | Installation et déploiement | ❌ **jamais exécuté**, et écrit pour Linux/ROCm alors que la machine cible est Windows 11 |
| 15 | `config/triggers.yaml` — planification de workflows | ⬜ absent |
| 24.1 | `GET /agents`, `GET /logs`, `GET /system/gpu` | ⬜ absents |

`AUDIT_CONFORMITE.md` date du 2026-07-26 — 45 jalons avant aujourd'hui.
**Il doit être rejoué**, pas relu : plusieurs de ses verdicts portent sur
du code qui a changé depuis.

---

## C. Frontend — retours utilisateur après la refonte SODIUM

Relevés le 2026-08-13 (`docs/frontend-backlog.md`), statut revérifié le
2026-08-15. **Calendrier : après ACP** — ACP change ce qu'il y a à
afficher (pensées en streaming, demandes d'approbation, sessions
reprises), refaire l'UI avant reviendrait à la refaire deux fois.

### Résolus depuis

| Point | Résolu par |
|---|---|
| Une tâche lancée disparaît en changeant d'onglet | ✅ HOS-102 |
| Persistance des conversations | ✅ HOS-101 |
| Retrouver une conversation passée, titrée | ✅ HOS-101 (`/resume`) |
| Contexte par modèle selon l'usage réel | ✅ Modelfiles par modèle |

### Ouverts

| Center | Point | Détail |
|---|---|---|
| Assistant | Sélection automatique du modèle | Le catalogue mesuré existe (HOS-108), le routage par palier aussi (HOS-109), mais **l'Assistant n'a pas de mode auto** : le classifieur n'a aucun appelant. Câbler ou retirer |
| Mission | **Voir la décomposition réelle** | L'UI affiche `Nœuds : 0/7` — jamais *quelles* tâches. Le DAG est construit côté backend, il n'est pas exposé |
| Mission | Résultats plus poussés | Artefacts vérifiés, outils réellement appelés, verdict de `MissionVerification`. La distinction « rapporté réussi » / « vérifié sur disque » est ce qui différencie ce produit — elle n'est pas à l'écran |
| Autonomous | **Audit complet requis** | Jamais retesté depuis la refonte |
| Autonomous | Fil conversationnel | Que l'agent explique où il en est, au lieu d'un compteur muet. ACP fournit la matière (`AgentThoughtChunk`) |

---

## D. ACP — le verrou

`docs/acp-integration-findings.md`, spike du 2026-08-13.

**Prouvé :** handshake, session liée à un workspace, énumération et
sélection des modèles Ollama, streaming de dizaines de `session_update`,
et `request_permission` réellement appelé avant édition — le
human-in-the-loop du §17 n'est pas à construire, seulement à brancher.

**Bloqué :** permission accordée, **l'agent ne poursuit pas**. Aucun
`write_text_file`, aucune erreur, le `prompt` ne rend jamais la main —
testé jusqu'à 900 s. Trois hypothèses déjà écartées par la mesure.

Ce que débloque ACP, en un seul chantier : la délégation (HOS-094,
aujourd'hui structurellement impossible en one-shot CLI), la reprise de
mission, l'approbation humaine, et le fil conversationnel d'Autonomous.

**Piège à retenir :** ACP écrase l'exception d'un handler client en
`RequestError: Internal error`, sans trace ni nom de méthode. Tout
handler doit journaliser sa propre exception avant de la laisser
remonter, faute de quoi la moindre erreur d'intégration est indébogable.

---

## E. Installation et distribution

Presque rien n'existe. C'est le chantier le plus neuf du projet.

| Réf. | Action |
|---|---|
| I-1 | **Installateur `.exe`** — packaging du backend Python, du frontend, du venv et de la configuration |
| I-2 | Sort d'Ollama : prérequis vérifié à l'installation, ou embarqué |
| I-3 | Les Modelfiles custom (`num_ctx` par modèle) doivent être créés à l'installation — sans eux l'agent tourne à 4096 et répond qu'il n'a pas d'outils |
| I-4 | §25 à réécrire pour Windows 11 + AMD (le texte actuel décrit Ubuntu/ROCm) |
| M-3 | **Installer Center** — annoncé au périmètre du Cockpit, n'existe pas. Implémenter ou retirer |
| I-5 | Rejouer l'installation sur une machine nue — c'est le seul moyen de valider §25 et le dernier critère §28.1 |

**Décisions à prendre avant de coder** (voir « Décisions en attente »).

---

## F. Modèles et performance

Le catalogue est complet : dix modèles, tous axes mesurés, aucune
capacité déclarée sans mesure (`docs/model-selection.md`).

| Réf. | Action | État |
|---|---|---|
| P-1 | **Coût de bascule modèle → modèle** | ⬜ jamais mesuré. Le chargement à froid est connu (~6,5 s) ; le prix d'un échange sous `OLLAMA_MAX_LOADED_MODELS=1` ne l'est pas |
| P-2 | **Accélérer chargement/déchargement** | ⬜ dépend de P-1. Leviers : `keep_alive`, résidence choisie, préchargement du rôle suivant, ordre d'éviction |
| P-3 | Routage par difficulté à partir des notes /100 | ⬜ le catalogue existe, le routeur ne le lit pas |
| P-4 | Consolider `ModelRouter` et `AdaptiveRouter` | ⬜ deux routeurs, un seul devrait décider |
| P-5 | Synthèse vocale (Piper) | ⬜ `gemma4` couvre l'entrée audio ; aucun modèle n'écrit de la parole |
| — | DFlash | ✅ clos : mesuré à +11 %, non adopté, drafter supprimé |

---

## G. Dette v1.0 — Phase 9

| Réf. | Action | Priorité |
|---|---|---|
| M-9 | `pytest.ini` sur les deux répertoires | ✅ **HOS-111** |
| M-1 | Modèles Pydantic sur les 19 corps `dict = Body(...)` (500 → 422) | 🟠 |
| M-7 | Consolider les 6 duplications (`agent`/`agents`, `evolution`/`self_evolution`, 2 registries…) | 🟠 |
| M-13 | Borner `mcp<2` dans `requirements.txt` | ✅ **déjà satisfait** — `mcp==1.28.1`, plus strict que la borne demandée ; la ligne était périmée |
| M-8 | Verrouiller et borner `mission/routes.py::_missions` | ✅ **HOS-120** — reste à faire : la **persistance** (au redémarrage le registre est vide) |
| J-3 | Boucles d'outils par agent spécialisé — **prérequis de la décomposition multi-tâches**, et dépendant d'ACP | 🟠 |
| J-2 | Adaptateurs vLLM et llama.cpp (aujourd'hui `RuntimeUnavailableError`) | 🟠 |
| M-6 | Câbler les 4 adaptateurs HOS-065B et `approval_explainer` (testés, jamais utilisés) | 🟡 |
| J-4 | Câbler le `WorkspaceManager` dans l'exécuteur pour des artefacts sur disque | 🟡 |
| J-5 | Validation réelle de syntaxe/politique/sécurité des sorties générées | 🟡 |
| J-6 | Diffuser les résultats vers les 5 couches de mémoire | 🟡 |
| cos-1 | Supprimer les 321 imports inutilisés et les 15 composants frontend morts | ⚪ |
| M-14 | `ci_scorer.py` orphelin — décision prise : **supprimer**, `CodeIntelligenceRouter` fait déjà le même calcul | ⚪ |

**Reste de P-002 (namespace d'API)** : retrait des 62 chemins racine
conservés pour compatibilité ; schéma OpenAPI de `POST /verification/run`
(débloquerait le bouton du Validation Center) ; homonymie `/skills`
historique vs HOS.

---

## H. Telegram

La passerelle existe (écart assumé §4.1 — Hermes Agent plutôt que
`python-telegram-bot`).

| Réf. | Action |
|---|---|
| T-1 | Rapports d'échec de mission **avec preuve disque**, pas le compteur de tâches |
| T-2 | Boucle de reprise bornée |
| T-3 | Répondre avec une piste plutôt qu'un constat |

---

## Décisions en attente

Aucune ne bloque aujourd'hui ; toutes bloqueront le moment venu.

**Frontend / ACP**
1. Persistance des conversations : infinie, ou purgée après N jours / N conversations ?
2. Le fil Autonomous montre-t-il *toutes* les pensées de l'agent, ou seulement décisions et appels d'outils ? (Le premier est volumineux et coûte du contexte à l'affichage.)
3. Approbations humaines ACP : bloquantes dans l'UI, ou file d'attente consultable ?
4. La décomposition d'une mission est-elle modifiable avant lancement, ou seulement consultable ?

**Installation**
5. Backend empaqueté (PyInstaller/Nuitka) ou venv déployé par l'installeur ?
6. Interface : Electron/Tauri, ou serveur local ouvert dans le navigateur ?
7. Ollama embarqué dans l'installeur, ou prérequis vérifié puis installé séparément ?

---

## Historique — jalons livrés

### Phases 1 à 6 — fondation, RAL, agents, services, frontend, observabilité ✅

| Phase | HOS | Contenu |
|---|---|---|
| 1 | 000-003 | SDS : EventBus, RuntimeHolder, wiring FastAPI |
| 2 | 004-016 | Runtime Abstraction Layer : registre, routeur, santé, recovery, politiques |
| 3 | 017-024 | Agent Layer : DAG, planificateur, cycle de vie, mémoire unifiée, moteur d'exécution |
| 4 | 025-028 | Services : bus système, Freebuff, Mission Control + API |
| 5 | 029-033 | Frontend Next.js, Centers Mission / Execution / Agent / Runtime |
| 6 | 034-038 | Observabilité : event bus, resource manager, recovery, intelligence, orchestrateur |

### Phase 7 — Cockpit, intégrations, sécurité, noyau autonome ✅

HOS-051 à HOS-065B, puis HOS-066B (composition root : 32/32 sous-systèmes
instanciés, 0 × 5xx) et P-002 (namespace `/api/v1` unifié).

**Audits release** : RC1 2026-07-29 (65/100, NO GO) · RC2 2026-07-30
(71/100, NO GO — « la plateforme est solide ; la capacité centrale n'est
pas implémentée ») · **R-001 2026-07-30 : R-1 levé** — l'exécution est
réelle, `random.random() > 0.15` remplacé par `RealTaskExecutor` qui lève
plutôt que de fabriquer un succès.

### Phase 8 — exécution réelle, vérification, modèles ✅ (HOS-066 → HOS-111)

| HOS | Ce qui a été livré |
|---|---|
| 066C | Escalade cloud OpenRouter, local d'abord, repli automatique |
| 067-072 | Centers reconnectés au moteur réel : Autonomous, Missions, Execution, Agent, Model Intelligence, Runtime |
| 073-077 | Assistant : streaming réel, mémoire de conversation, choix du modèle, contexte, pièces jointes |
| 078-079 | Recherche web réelle dans l'Assistant ; restauration du parc de modèles |
| **080-082** | **Refonte visuelle complète — direction SODIUM** |
| 083-084 | Couche Workspace/Filesystem : Aegis dynamique, outils fichiers réels, câblage chat *et* missions |
| **085** | **Hermes Agent redevient le cerveau des missions** — le garde-fou `HERMES_AGENT_BYPASS_DETECTED` |
| 086-088 | `memory_search` retrouve ce que `memory_remember` a écrit ; ids projet canoniques ; routage par capacité |
| 089-093 | Les cinq faux succès : contexte servi, timeout de boucle, contexte dégradé détectable, vérification contre le disque |
| 094 | Délégation mesurée : mécaniquement fonctionnelle, **structurellement incompatible** avec le CLI one-shot → motive ACP |
| 095-096 | Aucune heuristique ne prédit la capacité agentique — seule la mesure le fait. Sondes sous verrou exclusif |
| 097-098 | RAG sait dire « rien de pertinent » ; `UnifiedMemory` a un socle durable |
| 099-100 | La boucle se ferme : une vérification en échec produit une seconde tentative, qui s'exécute réellement |
| 101-102 | Conversations persistées, listables, titrées ; la tâche ne disparaît plus au changement d'onglet |
| 103 | Hermes OS a son propre environnement Python |
| 104-108 | Catalogue de modèles mesuré sur sept axes ; dix instruments de mesure corrigés |
| 109 | Réutiliser un modèle résident ne doit pas répondre avec un plus faible |
| 110-111 | Bancs vision/raisonnement au dépôt ; `pytest.ini` couvre enfin les deux répertoires |

---

## Légende

- ✅ **Terminé** — code + tests + documentation
- ⚠️ **Partiel** — fonctionne, mais pas au niveau spécifié
- ⬜ **À faire** — identifié, spécifié
- ❌ **Manquant** — exigé par le cahier des charges, jamais construit
- ⏳ **Non vérifié** — peut-être vrai, jamais mesuré
