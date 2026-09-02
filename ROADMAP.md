# Roadmap — Hermes OS

> **État réel du dépôt au 2026-09-02, après HOS-212.**
>
> Ce fichier était figé à HOS-120 (2026-08-15) : **quatre-vingt-douze
> jalons livrés depuis n'y figuraient pas**, dont toute la campagne Studio
> (HOS-190 à HOS-212) — scintillement, quadrillage, calibration du
> décodeur, chaînage de plans, production vidéo complète.
>
> C'est la deuxième fois. L'édition précédente s'ouvrait déjà sur le même
> constat, en 2026-08-15, pour quarante-cinq jalons. Un document de
> référence en retard fait manquer du travail — et il le refait dès qu'on
> cesse de le tenir.
>
> **Métriques mesurées le 2026-09-02, après réparation** : **4 868 tests
> verts** en 5 min sur les deux arbres — 2 274 dans `backend/tests`,
> 2 594 dans `tests/`. Ce second arbre ne se collectait plus depuis
> HOS-175 : la commande documentée dans `CLAUDE.md` passait un chemin en
> argument, ce qui **écrase** `testpaths` et n'en exécutait qu'un sur
> deux. Voir I.5.

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

## I. Convergence Hermes OS 2 — cahier des charges du 2026-08-30

> Un cahier de 111 points, inspiré d'Agent OS, d'OpenRouter et d'OmniRoute,
> visant un système agentique hybride *local-first, cloud-capable,
> verification-first*.
>
> **Ses 111 points ont été confrontés au code réel les 2 et 3 septembre**,
> sondes automatiques puis lecture. Le résultat n'est pas une liste de
> tâches : **près de la moitié existe déjà**, une partie n'existe qu'à
> moitié, et une poignée seulement manque vraiment. Trois points que
> j'avais d'abord classés « existe » se sont révélés incomplets une fois
> comparés à l'implémentation d'Agent OS — c'est là que se trouvent les
> gains les plus rentables.

> Le cahier **adapté** — celui qui fait foi désormais — vit dans
> `docs/cahier-des-charges-hermes-2.md` : il porte le modèle de menaces
> tiré de la suite adverse d'Agent OS, ce qu'on reprend de leur code et
> ce qu'on en change, et ce qui est écarté avec le motif.

### I.0 Agent OS, source lue le 2026-09-02

Archive `agent-os-main.zip`, version 2026-07-03, 11,5 Mo.

**C'est une application Next.js en TypeScript** : 369 fichiers `.ts`,
124 `.tsx`, environ 67 000 lignes, contre 1 112 lignes de Python. Le
cahier ne le mentionne nulle part et c'est le fait qui commande toute la
stratégie : **aucune ligne de son code n'est reprenable.** Ce qui se
transfère est son modèle de données et ses invariants.

| Brique | Fichier | Lignes | Test |
|---|---|---|---|
| Contract | `src/lib/contract.ts` | 320 | `m4-contract.test.ts` |
| Run Ledger | `src/lib/ledger.ts` | 401 | `m1-ledger.test.ts` |
| Checkpoints | `src/lib/checkpoints.ts` | 345 | `m6-checkpoints.test.ts` |
| Loop engine | `src/lib/loopEngine.ts` | 237 | — |
| Sandbox | `src/lib/sandbox.ts` | 32 | — |

Stockage `node:sqlite`, migrations SQL explicites. **Zéro occurrence
d'OmniRoute** : le cahier avait raison, ce n'est pas une dépendance
d'Agent OS. OpenRouter apparaît dans 26 fichiers.

### I.1 Les trois gains cachés sous un « ça existe déjà »

C'est la partie la plus rentable de cette analyse, et elle a failli être
manquée : une sonde qui trouve un module ne dit pas qu'il fait le travail.

**Les checkpoints ne sauvegardent pas la même chose.**
`core/snapshot_manager.py` (347 l.) sérialise l'**état de base** — tâches,
exécutions — pour reprendre une mission. Agent OS crée une **référence
git** `refs/agent-os/checkpoints/<id>` sur un commit détaché, via un
index temporaire qui ne touche jamais celui de l'utilisateur, avec repli
système de fichiers, manifeste de contenu et vérification d'intégrité par
re-hachage. **Hermes ne sait pas annuler une modification de fichier.**
Les deux sont complémentaires, pas redondants.

**La mémoire n'a pas de confiance.** `MemoryEntry` porte `source_type` et
`source_id` — d'où vient l'information. Agent OS contraint au niveau du
schéma : `CHECK(trust IN ('trusted','quarantined'))`, avec l'invariant
écrit en majuscules « origine non humaine **forcée** en quarantaine,
`promoted_by=null` ». Dans Hermes, une mémoire produite par un agent
devient un fait immédiatement.

**La vérification est booléenne.** Chaque contrôle de
`mission/verification.py` rend `-> bool`. Agent OS distingue
`passed | failed | unavailable` avec le commentaire *« never conflate
unavailable with passed »*, et un critère a quatre états :
`unmet | met | unverifiable | violated`. Le cas s'est produit en
production le 2026-08-30 : `img07` était `indetermine` — le relecteur
n'avait pas pu conclure — et cet état n'avait nulle part où aller dans
une vérification à deux valeurs.

### I.2 Confrontation, par état

> Le sondage **point par point des 111**, avec la preuve de chaque
> verdict, vit dans `docs/sondage-cahier-111-points.md`. Ce qui suit en
> est le résumé.

Sondes sur `backend/` et `frontend/src`, hors tests, puis lecture des
cas ambigus. Les comptes bruts d'une recherche textuelle produisent des
faux positifs sur les mots courants — `scope`, `score`, `pipeline` — et
ont été revérifiés à la main.

#### Ce qui existe et tient

Checkpoints d'état · `AdaptiveRouter` · journal et audit · exécution
git-aware · bus d'événements · MCP · Health Center · admission de
ressources · bancs de modèles · gouvernance de coût · doctor ·
niveaux d'autonomie · self-evolution · multi-agent séquentiel et
parallèle · ordonnanceur de chargement · modèle chaud · apprentissage
historique · budget de contexte · invariants de sécurité · recherche
globale · notifications · Operator · palette de commandes · Mission DAG ·
`DecisionExplainer` (« pourquoi ce modèle »).

#### Ce qui existe à moitié

| Point | Ce qui manque |
|---|---|
| Evidence graph | états à deux valeurs au lieu de quatre |
| Approbation | ✅ HOS-224 — le diagnostic était faux sur deux points : l'expiration existait, et le module *est* branché dans `AegisAgent`. Le vrai manque était la canonisation et la portée |
| Abstraction cloud | `OpenRouterClient` réel (287 l.) mais **zéro test**, pas d'interface `CloudProvider` |
| Quota / disjoncteurs | présents, **zéro test**, pas de `QuotaBroker` |
| Secret broker | un fichier, pas de redaction systématique |
| Sandbox | `sandbox_manager` en mémoire, ne valide pas de chemin réel |
| Model trust | pas alimenté par l'historique des runs |
| Architecture plugin | un fichier, pas de manifeste ni de permissions |
| Agent Room | embryon |
| Agents CLI externes | `hermes_agent_cli` seul, pas d'abstraction |
| Promotion mémoire | pas de quarantaine, donc rien à promouvoir |

#### Ce qui manque vraiment

Mission Contract · Run Ledger et lineage · Context Relay · Loop
Engineering · Cloud Data Firewall · détecteur d'expansion de périmètre ·
rôles d'agent découplés du modèle · Council / MoA · `QuotaBroker` ·
Agent Control Room · Kanban · replay de run · Radar · tests de chaos ·
compression de contexte · onboarding premier démarrage · configuration
utilisateur survivant aux mises à jour.

### I.3 Ce qui est écarté, et pourquoi

**Le pool de comptes multiples chez un même fournisseur (§21).** Le
cahier dit qu'il faut respecter les conditions des fournisseurs, puis
décrit un mécanisme dont la finalité est d'agréger des quotas gratuits en
faisant tourner plusieurs comptes. C'est une violation des CGU de la
plupart d'entre eux. Le routage **multi-fournisseurs**, la santé, les
quotas et les disjoncteurs sont retenus ; la multiplication de comptes ne
l'est pas.

**SEO, Leads, CRM, Music, Games (§54-55, §52).** Le cahier les classe en
extensions au §86 puis les réintroduit dans sa liste finale. Ils
n'entrent pas tant que l'architecture de plugins (§87) n'existe pas :
une extension sans point d'extension est une fonctionnalité de plus dans
le noyau.

**OmniRoute comme couche.** Adaptateur derrière la même interface
qu'OpenRouter, jamais dépendance. Ses chiffres — 200+ fournisseurs,
dizaines de tiers gratuits — sont des annonces, pas des mesures.

**Rebâtir ce que Hermes Agent fait déjà.** L'agent embarque plus de 70
compétences et des connecteurs Telegram, Discord, Slack, WhatsApp,
Signal, e-mail. La section H prévoit Telegram : **vérifier d'abord ce que
l'agent fait**, sinon c'est la violation exacte que
`test_hermes_agent_is_the_brain.py` empêche.

### I.4 Ordre retenu

Trois écarts au cahier d'origine, et le troisième vient de la lecture du
code d'Agent OS le 2026-09-02.

**Une phase 0 réelle avant tout** — faite, voir I.5.

**Le cloud derrière la traçabilité.** Sans Ledger, il reproduit ce qu'a
produit la nuit du 29 au 30 août : des heures de calcul dont on ne sait
plus rendre compte.

**La sécurité avant la traçabilité.** Leur suite adverse `m8` a montré
que trois manques que j'avais classés « confort » sont des **contrôles**
— détail dans `docs/cahier-des-charges-hermes-2.md` §2 :

- la quarantaine mémoire est la défense contre l'**injection de prompt**,
  pas une question de qualité de données ;
- un agent qui travaille sur un workspace peut modifier la configuration
  qui le **gouverne lui-même** — hooks, serveurs MCP, `CLAUDE.md` ;
- l'état utilisateur vit dans le dépôt, donc la première mise à jour
  efface base, mémoire et **snapshots**.

| # | Jalon | Pourquoi à ce rang | Effort |
|---|---|---|---|
| **0** | ✅ **Fait le 2026-09-02** — deux arbres de tests réparés | voir I.5 | — |
| 1 | ✅ **Fait (HOS-215)** — état hors du dépôt, 26,6 Mio migrés | 18 Mo de base, 8,2 de bus, 2,2 de snapshots dans le dépôt. Tout ce qui suit se construirait dans un dossier qu'une mise à jour efface | petit, bloquant |
| 2 | ✅ **Fait (HOS-216)** — origine non humaine en quarantaine | défense contre l'injection de prompt ; une mémoire d'agent devient un fait immédiatement | petit |
| 3 | ✅ **Fait (HOS-217)** — dix fichiers gouvernants surveillés | un agent peut planter des hooks ou un serveur MCP dans le dépôt qu'il traite | moyen |
| 4 | ✅ **Fait (HOS-218)** — canary, report 512, silence, coût | répond à §14 et §22 d'un coup ; transposable presque tel quel | moyen |
| 5 | ✅ **Fait (HOS-221)** — Contract tri-état + Run Ledger + lignée, branchés sur `MissionExecutor` | le manque le plus coûteux, démontré en production | 56 gardes |
| 6 | ✅ **Fait (HOS-222)** — verdict tri-état, instantané qui sait dire qu'il n'a pas lu | un « on ne sait pas » n'est pas un « c'est bon » — ni un « c'est mauvais » | 19 gardes |
| 7 | ✅ **Fait (HOS-223)** — commit détaché + repli vérifié, couplé à l'état de mission | Hermes ne savait pas annuler une modification | 28 gardes |
| 8 | ✅ **Fait (HOS-224)** — empreinte canonique + discriminants + portée d'arborescence bornée | l'expiration existait ; la description entrait dans l'identité, et deux appelants la font écrire par le modèle. `approval_engine` reste **délibérément** débranché : deux portes vivantes valent moins qu'une | 37 gardes |
| 9 | ✅ **Fait (HOS-225)** — onze causes classées sur indices nommés, remède par cause, `INCONNUE` reste `NULL` | le retry changeait de modèle à *toute* reprise — le bon remède pour un cas sur onze | 34 gardes |
| 10 | ✅ **Fait (HOS-226)** — `CloudCapability` dans le RAL, OpenRouter en adaptateur, registre-goulet | prémisse corrigée : le client avait 9 tests. `CloudProvider` n'existait nulle part | 29 gardes |
| 11 | ✅ **Fait (HOS-227)** — classification à indices nommés, quatre verdicts, politique par projet, goulet avant l'envoi | fuite mesurée : le nom de l'utilisateur et celui de son client partaient dans chaque prompt cloud | 28 gardes |
| 12 | **QuotaBroker** — fournisseur/clé/modèle, reset, cooldown, verrou, candidat suivant | disjoncteur et santé runtime existent ; il manque le courtier. Doit consommer la **taxonomie J9** : `429 → QUOTA → fournisseur B`, jamais `429 → même fournisseur → 429` | moyen |
| 13 | **Context Relay + rôles découplés** — planification / exécution / vérification / réparation | 16 Gio imposent le séquentiel, ce qui rend l'architecture *utile* : planificateur cloud → exécutant local → vérificateur cloud. Le contexte doit passer sans perdre mission, run, contrat, critères, mémoire autorisée, outils, artefacts, preuves | moyen |
| 14 | **Loop Engineering** — contrat → exécuteur → vérificateur → diagnostic → réparateur → reprise | **assembler, pas recréer** : contrat (J5), vérificateur tri-état (J6), checkpoint (J7), taxonomie (J9), Ledger (J5) existent | moyen |
| 15 | **Model Trust nourri par les causes** | déjà branché sur succès/durée. Le travail est de le nourrir **par cause** (J9), type de tâche, vérification, coût, latence. Reste une donnée décisionnelle : **Aegis reste au-dessus** | petit |
| 16 | **Installation / mise à jour / retour arrière** | Hermes a maintenant de l'état critique. Sauvegarde → migration → installation → validation → *commit*, avec retour arrière, et sans toucher au `preserve_set()`. Auto-vérification après installation | gros |
| 17 | **Mission Control** — une **vue** du runtime, jamais un second runtime | agents, mission, **trace d'exécution vivante** (le « messy middle »), Control Rooms, artefacts, analytics. Toutes les données viennent des systèmes réels — aucun compteur fabriqué par le frontend | moyen |
| 18 | **Architecture de plugins + manifeste de permissions** | identité, version, compatibilité, permissions, outils, MCP, événements consommés/produits, stockage. **Aegis applique les permissions du plugin** | moyen |
| 19+ | **Plugins** : Goal Mode, Kanban, Model Council, Paperclip, Voice/Jarvis, Studios, Radar, SEO, Leads | hors cœur. Chacun utilise les primitives Hermes plutôt que de refaire missions, mémoire ou exécution | — |

Les jalons 1 à 4 sont **petits et bloquants**. Les construire après le
Contract reviendrait à bâtir la traçabilité dans un dossier effaçable,
au-dessus d'une mémoire empoisonnable.

### Deux fils rouges qui traversent J10 → J19

Ils ne sont pas des jalons : ils sont des **contraintes** que chaque
jalon doit respecter, et contre lesquelles chacun se relit.

#### 1. Contrat d'événements — un événement, plusieurs consommateurs

Le runtime émet des événements **métier** stables ; le frontend les
consomme. Le danger est de construire Mission Control avec des
événements taillés pour lui : on obtiendrait cinq systèmes qui
enregistrent séparément la même chose.

    mission.created      model.selected       approval.requested
    run.started          model.switched       approval.granted
    tool.started         provider.fallback    verification.started
    tool.completed       retry.requested      verification.completed
    checkpoint.created   checkpoint.restored  mission.completed / failed

Un seul flux alimente Mission Control, l'Operator, le Ledger, les
analytiques, l'audit et le débogage.

Hermes en a déjà une partie — `mission.unverified`, `mission.non_mesuree`,
`mission.checkpoint`, `mission.sans_filet`, `execution.retry` avec sa
cause. La règle **complète et normalise**, elle ne recommence pas.

#### 2. La chaîne cloud, sécurité et vérification sont inséparables

Le flux ne doit jamais devenir `Agent → OpenRouter`. Il est :

    Agent → Contrat → Politique → Aegis → Pare-feu de données
          → Routeur fournisseur/quota → CloudCapability → Modèle
          → Vérification → Ledger

C'est la colonne vertébrale du Hermes OS final, et chaque jalon de J11 à
J15 en construit un segment. Aucun ne doit pouvoir être court-circuité :
un chemin qui saute le pare-feu ou la vérification n'est pas une
optimisation, c'est une régression.

### Une note sur les prémisses de ce tableau

Quatre lignes ont été écrites à partir d'un sondage qui ne regardait que
`backend/tests/`, et se sont révélées fausses en construisant :

- **jalon 8** annonçait « ni hash canonique, ni portée, ni expiration ;
  appelée depuis un seul fichier ». L'expiration existait, le module
  *était* branché dans `AegisAgent`, sur le chemin réel des requêtes. Et
  le remède proposé — rebrancher `policy/approval_engine.py` — aurait
  créé une seconde porte de gouvernance vivante.
- **jalon 10** annonçait « le client existe sans un seul test ». Il en a
  neuf, réels, dans `tests/` — l'arbre qui n'était plus collecté depuis
  HOS-175.
- **jalon 15** annonçait « à brancher, pas à écrire ». C'est déjà
  branché.
- **jalon 12** annonçait des disjoncteurs non testés. Ils le sont, dans
  `tests/architecture/`.

Le point commun est le même que celui de HOS-111 : **un sondage qui
ne regarde qu'un des deux arbres de tests conclut faux.** Les prémisses
restantes (11, 13, 14, 16, 18) n'ont pas encore été revérifiées de cette
façon — elles le seront au moment de les construire, avant d'écrire une
ligne.

**La méthode, énoncée pour de bon** : mesurer → réutiliser → compléter →
tester → exposer. Jamais supposer → réécrire → doubler. J10 en a fourni
un contre-exemple immédiat : sa première version créait un paquet
`backend/cloud/` parallèle, alors que le RAL avait déjà
`adapters/hermes_ollama.py` et qu'un fournisseur distant **est** un
runtime. Ce qui lui manquait était une *capacité*, pas une arborescence.

### I.4bis Ce que la lecture d'Agent OS a corrigé

**La suite adverse manquait à ma lecture du cahier.** Le §75 demandait
des « tests de chaos » sans les nommer. Leur `m8` les nomme : injection
de prompt, empoisonnement de mémoire, exfiltration d'environnement,
échappement de chemin par lien symbolique, configuration hostile,
descriptions MCP, boucles de budget. C'est une liste de courses, pas un
principe.

**Deux points où Hermes est devant**, et qu'il ne faut donc pas
« améliorer » en copiant :

- *les sessions d'agent* — ils paient ~28 s de démarrage à froid par tour
  et le contournent par un serveur global chaud ; HOS-138 tient une
  session ACP **par mission**, 220 Mio mesurés, tours sérialisés ;
- *le bus d'événements* — le leur est une seconde table `run_events` ;
  celui de Hermes est durable, rejouable par plage et par motif, avec des
  identifiants idempotents. Le Ledger portera les runs, pas les
  événements.

### I.5 Jalon 0 — fait le 2026-09-02

**La cause racine n'était pas la configuration.** `pytest.ini` déclare
`testpaths = backend/tests tests` depuis HOS-111, avec un commentaire qui
raconte précisément cet incident. C'est `CLAUDE.md` qui documentait
`pytest backend/tests` — et **un chemin en argument écrase `testpaths`**.
La commande documentée était plus étroite que la configuration, et
l'angle mort s'est rouvert le jour où on l'a écrite.

Trois défauts dans l'arbre abandonné :

| Défaut | Depuis | Correction |
|---|---|---|
| `WhisperProvider` importé mais supprimé | HOS-175, 22 jours | tests réécrits sur `PiperLocal` / `WhisperLocal` |
| `test_execute_single_task` bloquait 16 min | — | la garde ne couvrait qu'une sortie d'inférence sur trois |
| `test_get_goal`, même blocage | — | même cause |

Le deuxième est le plus instructif : `fake_inference.install()` ne
patchait que `_default_chat`, alors que `execute()` choisit entre trois
producteurs — Hermes Agent en sous-processus, la boucle d'outils sur
workspace, ou l'appel simple. **Le premier est le cas par défaut.** La
garde protégeait le chemin qu'on n'emprunte pas.

`tests/` passe de « ne se collecte pas » à **2 594 verts en 1 min 40**.
Trois gardes posées, dont une qui surveille `CLAUDE.md` et échoue si un
chemin y est réintroduit en argument.

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
