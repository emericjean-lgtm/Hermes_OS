## HOS-299 — §15.5 lot 2 : la preuve d'exécution atteignait déjà l'écran, et s'y faisait effacer par son propre absence de mesure (2026-09-12)

§15.5 (Explainability / Resource visibility / Proofs), lot 2. Continuation
officielle après HOS-298, sur la famille « Execution proofs » que ce
premier lot avait laissée ouverte.

### Le double système de mission, vérifié

HOS-298 avait laissé une incertitude : brancher un écran sur
`mission/verification.py` supposait de confirmer que le système de
mission servi par `hos_routes.get_mission` est bien celui qu'alimente
`mission/graph_executor.py`. Vérifié directement sur le process réel :
`hos_routes.py` n'est monté par aucun routeur — `grep` sur `main.py` et
`core/bootstrap/*.py` ne trouve aucune référence, et son `operationId`
n'existe pas dans le schéma OpenAPI du serveur en marche. C'est la façade
morte que `docs/HERMES_OS_ROADMAP_STATE.md` documente déjà depuis
HOS-072 sous « dettes acceptées » (0 route sur 423). Un seul système de
mission existe réellement : `mission/routes.py`, dont l'exécuteur est
injecté par `_make_graph_executor` (`core/bootstrap/service_registry.py`)
— le vrai `GraphExecutor` de production, pas une façade.

### Le défaut, mesuré avant correction

Ce système unique atteignait déjà l'écran, et depuis longtemps :
`mission-center.tsx` consomme `/api/v1/missions/{id}/report`, qui sert
`mission.metadata["verification"]` — posé par `GraphExecutor._verify_workspace`
à la complétion d'une mission — via `VerificationReport`
(`verification-report.tsx`), câblé depuis HOS-174/177 (26/08), avant même
l'ouverture de §15.5. `mission/verification.py` (HOS-092) n'était donc pas
« diagnostiqué mais non branché », contrairement à ce que le lot précédent
affirmait — l'affirmation n'avait pas été vérifiée contre le code
frontend réel, exactement l'erreur que ce dépôt existe pour ne pas
commettre une seconde fois.

Le vrai défaut était ailleurs, dans ce chemin déjà câblé. `MissionVerification`
(le type TS, `types/hermes.ts`) ne portait ni `verdict`, ni
`mesure_impossible`, ni `indetermines` — trois champs que
`MissionVerification.as_dict()` sert pourtant sur chaque rapport, confirmé
en interrogeant `/report` d'une mission réelle. Et `VerificationReport`
ne testait que `v == null` avant de tomber dans son calcul de
`contredite`, qui vaut `false` partout quand rien n'a été mesuré.

Mesuré en runtime réel, backend et frontend démarrés en process (pas en
test) : une mission sans `project_id` — le cas le plus courant, tout
mission sans workspace lié — revient avec `measured: false, verdict:
"indisponible", workspace: null`, et l'écran affichait **« Confirmé sur
le disque : 0 fichier(s) touché(s) »**, bandeau vert de succès — le faux
positif exact que ce module existe pour empêcher (HOS-092), reformulé par
la couche UI plutôt que lu depuis le backend, en violation directe de la
règle §9 de ce chantier.

### Ce qui a été livré

`VerificationReport` teste désormais `v.measured === false` explicitement,
avant tout calcul de contradiction, et distingue deux bandeaux neutres :
aucun workspace lié (le cas courant, message inchangé), et workspace lié
devenu illisible (`mesure_impossible`, HOS-222 — bandeau d'alarme distinct,
nomme le workspace). Aucun des deux ne parle de fichiers touchés ni de
succès. Le relevé (`Mesures`) affiche désormais une case « Indéterminés »
quand `indetermines` n'est pas vide, plutôt que de la taire — un fichier
illisible n'est ni créé, ni modifié, ni supprimé, et le silence sur ce
point revenait à le compter comme « rien » (HOS-222). `types/hermes.ts`
porte les trois champs manquants.

Démontré en runtime réel de bout en bout sur le process tournant, backend
(`uvicorn`, port 8010) et frontend (`next dev`, port 3010) : une mission
liée à un workspace scratch (`project_id` réel, validé) a fait écrire
`hermes-agent` un fichier réel en 60,6 s (`qwen3.5` local, Ollama) ;
`verify()` a mesuré `created: ["proof.txt"], verdict: "reussi"` ; le
Mission Center affiche « Confirmé sur le disque : 1 fichier(s)
touché(s) » avec le chemin réel. Une seconde mission sans `project_id` a
confirmé la correction : bandeau neutre « Aucune vérification disque »
au lieu du faux vert d'avant. Projet et workspace scratch supprimés après
capture des preuves.

### Vérification

Frontend : `verification-report.test.tsx`, 7 tests neufs (absence de
mesure sans workspace, absence de mesure avec workspace illisible —
distincte de la précédente —, aucune mention de « 0 fichier » dans les
deux cas, preuve confirmée quand mesurée, fichiers indéterminés affichés,
case « Indéterminés » absente quand vide, bandeau d'alarme sur
contradiction réelle). Mutation vérifiée en repassant le garde à
`if (v == null)` seul : 2 tests rougissent exactement sur les assertions
`measured === false` / `mesure_impossible`, les 5 autres restent verts ;
garde restauré, 7/7 verts. Suite complète : 174/174 (`vitest run`), contre
167 avant cette passe — delta exact des 7 tests ajoutés. `npx tsc
--noEmit` : aucune erreur.

Backend : aucune ligne de production modifiée — `mission/verification.py`,
`graph_executor.py` et `mission_models.py` restent tels que HOS-092/116/222
les ont laissés, avec leurs propres tests (`test_mission_report_verification.py`,
`test_verification_tri_etat.py`) déjà verts. Suite complète relancée sans
argument de chemin (`testpaths`) pour la régression ; résultat consigné
dans le rapport de fin de chantier.

### Ce qui reste hors périmètre

A-8/`DecisionExplainer`, G-3 (Centers autres qu'Operations et Mission),
G-16/G-17/G-20/G-21/G-25/G-43/G-44, #24, G-45 (explicitement non traité,
découvert pendant T-28) — hors trajectoire par construction de ce
chantier. `verification_chat_tools` côté chat n'a pas de consommateur
frontend et n'a pas été touché : le contrat Chat/Cowork (T-28) place
cette famille sur le contrat Mission/Cowork, pas Chat. Cowork n'a
toujours pas de Center propre — Mission Center reste la seule surface
démontrée pour cette preuve.

## HOS-298 — §15.5 : le routage et la comptabilité physique d'un run avaient déjà leur colonne, jamais leur écran (2026-09-12)

§15.5 (Explainability / Resource visibility / Proofs), premier lot.
Chantier ouvert après T-28/HOS-297.

### Le défaut, mesuré avant correction

Deux capacités réelles s'arrêtaient avant l'écran. `_decision_en_json`
(HOS-242, `backend/execution/mission_executor.py`) calcule déjà, par
tâche, ce que le routeur a demandé contre ce qui a réellement servi — et
nomme un repli ou une substitution quand les deux divergent — et
`Run.decision` le porte jusqu'à `/api/v1/operations/{missions/{m}/runs,
runs/{r}/lignee}` via `vue_operations._run_en_dict`. `RunWire`, côté
frontend, ne portait pas le champ : la donnée traversait le réseau et
s'arrêtait au typage.

La comptabilité physique par run (R-6, HOS-260) allait moins loin encore :
`Registre.mesurer()` écrit bien `vram_reservee_octets`,
`vram_machine_debut_octets`, `vram_machine_pic_octets` et `exclusif` en
base, avec leur sémantique `None` = non mesuré (jamais `0`) — mais
`_run_en_dict` s'arrêtait avant ces quatre colonnes. Aucune route ne les a
jamais servies ; aucun écran n'a donc jamais pu les afficher.

### Ce qui a été rejeté

Toucher `DecisionExplainer` (A-8, 3 routes montées, 0 appel) : il produit
une explication générique qu'aucune décision réelle n'alimente encore, et
le brancher aurait exigé une seconde autorité de décision quand une
provenance réelle — `Run.decision` — attend déjà côté registre. G-3
(provenance ailleurs que ce Center) et l'ensemble « Execution proofs »
(`mission/verification.py`, `mission.unverified`) sont restés hors
périmètre : chacun exige sa propre vérification de branchement
(l'un touche une autre famille de gap, l'autre un système de mission dont
il restait à confirmer qu'il est bien celui que `graph_executor.py`
alimente) — un seul chemin correctement démontré valait mieux qu'un
premier lot élargi sans cette vérification.

### Ce qui a été livré

`backend/services/vue_operations.py::_run_en_dict` sert désormais les
quatre colonnes R-6, `None` compris. `RunWire` (`client.ts`) porte
`decision` et les quatre champs physiques. L'Operations Center
(`operations-center.tsx`), dans la lignée d'un run déjà dépliée, montre :

- **routage** — silencieux quand le routeur a obtenu ce qu'il demandait ;
  cite le repli ou la substitution quand il a dévié (`DecisionDeRoutage`) ;
- **consommation physique** — la réservation exacte quand mesurée ;
  l'écart machine (pic − début) **seulement** quand `exclusif === true`,
  étiqueté « majorant » ; sinon « non attribuable » ou « attribution
  inconnue », jamais un écart tu ou montré comme s'il l'était
  (`ConsommationPhysique`).

Chaque section reste sous le bloc `<Source de={bloc.source} />` déjà en
place — l'explication affichée cite la route qui l'a produite sans code
neuf, exactement le critère de passage que §15.5 pose.

### Vérification

Backend : 4 tests neufs dans `test_vue_operations.py` (passthrough R-6,
`None` préservé, `exclusif=False` distinct de `None`, `decision`
préservé) ; 35/35 verts. Mutation vérifiée en retirant les quatre lignes
ajoutées à `_run_en_dict` : les trois gardes R-6 rougissent avec
`KeyError`, remises elles repassent au vert.

Frontend : 5 tests neufs dans `operations-center.test.tsx` (repli affiché,
silence sans divergence, écart affiché seulement si exclusif, « non
attribuable » si partagé, rien affiché — jamais un zéro — si non mesuré) ;
21/21 verts sur ce fichier, 167/167 sur la suite complète. Mutation
vérifiée par un `throw` inséré dans `ConsommationPhysique` : les cinq
gardes neuves échouent sur l'erreur injectée, retiré elles repassent au
vert. `npx tsc --noEmit` : aucune erreur.

Suite complète (`pytest`, sans argument de chemin ; `vitest run`) : voir
le rapport de fin de chantier.

### Ce qui reste hors périmètre

A-8/`DecisionExplainer` (aucune décision réelle ne l'alimente encore),
G-3 (provenance dans les Centers autres qu'Operations), G-16/G-17/G-20/
G-21/G-25/G-43/G-44 et #24 (hors trajectoire par construction de ce
chantier), la famille « Execution proofs »
(`mission/verification.py`/`mission.unverified`/`verification_chat_tools`)
— diagnostiquée réelle et persistée (`mission.metadata["verification"]`,
corrélée par `mission_id`) mais dont le branchement à un écran suppose de
confirmer d'abord que le système de mission que `hos_routes.get_mission`
sert est bien celui que `mission/graph_executor.py` alimente ; G-45,
explicitement non traité (découvert pendant T-28, hors trajectoire ici).

## HOS-296 — la promotion d'un souvenir avait déjà sa route, jamais son écran (2026-09-12)

G-10. Ferme le gap §8 : « la promotion d'un souvenir n'a aucune route
HTTP ».

### Le défaut, mesuré avant correction

L'énoncé du gap était faux sur un point précis : la route existait déjà.
`backend/api/routes/memory.py` porte `POST /memory/{memory_id}/promote`
depuis HOS-250, avec son contrat complet — `MemoryPromoteRequest`,
`promu_par` obligatoire et non vide, 404/409/422 distincts, chaîne réelle
jusqu'à `episodic.promouvoir()` — et 19 tests dans
`test_memoire_promotion.py`, tous verts avant cette passe. `backend/main.py`
la monte deux fois : nue (`/memory/{id}/promote`) et sous
`/api/v1/memory/{id}/promote` (`mount_legacy_under_api`). Confirmé sur le
processus en marche.

Ce que le diagnostic de ce chantier a trouvé à sa place : `_LEGACY_ROUTERS`
inclut `backend.api.routes.memory` (chemin épisodique, `EchoAgent` →
`episodic.py`) — distinct de `backend.memory.routes` (mémoire unifiée,
`MemoryManager`), que le Memory Center appelle déjà pour la recherche et
le graphe. Le premier n'avait aucun consommateur : `test_pas_de_backend_orphelin.py`
portait `/memory` et `/memory/{memory_id}/promote` dans `ORPHELINS_CONNUS`
depuis HOS-265. Le vrai gap n'était donc pas HTTP — il était produit : une
route montée, gouvernée, testée, sans un seul appelant. Le principe posé
par G-16 (HOS-295) s'applique mot pour mot.

### Ce qui a été rejeté

Réimplémenter la promotion, ou lui fabriquer un second contrat côté
route : la chaîne existante (garde-fou `PromotionRefusee`, refus de double
promotion `DejaPromue`, persistance vérifiée par relecture) est correcte
et déjà mesurée — la reconstruire aurait dupliqué une autorité au lieu de
la brancher. Un écran dédié à la seule promotion aurait aussi été un
appelant fabriqué pour la forme : le Memory Center existe déjà, sert déjà
la mémoire, et n'affichait tout simplement pas la provenance — le gap G-3
adjacent (« quarantaine/provenance non affichées »).

### Ce qui a été livré

Un panneau **Quarantaine** dans l'onglet Mémoire du Memory Center, sous
les Expériences. `memoryClient.list()` (`GET /memory`) rend chaque entrée
avec sa provenance ; le panneau filtre `en_quarantaine === true` et
affiche origine, projet, type et contenu. Le bouton « Promouvoir » demande
l'acteur via `window.prompt` — le même patron que le renommage de session
du pont (`cerveau-center.tsx`) — et appelle `memoryClient.promote(id,
promu_par)` (`POST /memory/{id}/promote`). Une saisie annulée ne mute
rien ; un refus de l'API (404/409/422) s'affiche sur l'entrée concernée,
jamais un succès silencieux.

`ORPHELINS_CONNUS` perd `/memory` et `/memory/{memory_id}/promote` — la
dette rétrécit de 113 à 111 entrées. Mutation vérifiée :
retirer l'appel réel du client fait rougir
`test_aucune_route_neuve_sans_appelant_frontend` exactement sur ces deux
chemins ; le restaurer les rend verts.

Vérifié en navigateur, bout en bout, sur le processus réel : une entrée
`agent` insérée directement dans `hermes.db` apparaît en quarantaine dans
le Cockpit, le clic sur « Promouvoir » émet le `POST` réel (`200 OK`),
l'entrée disparaît du panneau après invalidation de la requête, et
`GET /api/v1/memory` la rend avec `en_quarantaine: false`,
`promu_par: "emeric-verification-navigateur"` — **avant et après un
redémarrage complet du processus backend**. Six tests frontend neufs
(`memory-center.test.tsx`) : rendu d'une entrée en quarantaine, exclusion
d'une entrée déjà promue, état vide, mutation appelée avec l'acteur saisi,
saisie annulée sans mutation, erreur API affichée sur l'entrée.

### Ce qui reste hors périmètre

G-3 (quarantaine/provenance dans les autres écrans que Memory Center),
G-21 (la mémoire de l'agent, côté `tools/memory_tool.py`, échappe
entièrement à cette provenance — chemin distinct, non touché ici), et
T-28/§15 (le contrat produit plus large de la validation mémoire). Aucun
n'était dans le périmètre du gap G-10 tel qu'énoncé.

## HOS-295 — la dette d'orphelins n'avait jamais été revérifiée (2026-09-12)

G-16. Chantier de mesure et de classification, pas de suppression massive.

### Le défaut

`test_pas_de_backend_orphelin.py` avait gelé 120 routes `/api/v1` sans
appelant frontend le 2026-09-07 (HOS-265), et rien depuis ne revérifiait
que ce gel restait exact. Mesuré à nouveau : 314 routes (306 avant), 118
entrées dans la dette. `_motif`, la fonction qui décide si une route a un
appelant, cherchait un chemin suivi d'un guillemet, d'une apostrophe, d'un
backtick ou de `?`/`&` — mais pas de `$`. Or le patron dominant du client
frontend pour une query string optionnelle est
`` `/route${condition ? `?x=${v}` : ""}` `` : le `$` d'interpolation suit
immédiatement le chemin, sans jamais fermer de guillemet avant. Quatre
routes réellement appelées (`/collaboration/history`,
`/filesystem/browse`, `/models/benchmarks`, `/operations/checkpoints`) et
une cinquième par le même patron (`/logs`) étaient donc classées
orphelines par un défaut de la sonde, pas par absence réelle d'appelant.

Une tentative de correction plus large — retirer les commentaires du texte
scanné pour éviter qu'un commentaire mentionnant un chemin de fichier
(`data/logs/`) ne soit pris pour un appel réel — a été essayée et
abandonnée : une regex de bloc de commentaire traverse les frontières de
fichier sur ce dépôt et a supprimé du vrai code, fabriquant 37 nouveaux
faux orphelins en un instant. `/logs/{session_id}` reste donc classé
orphelin dans la dette malgré un « match » de sonde trompeur — vérifié à
la main, aucun appelant réel n'existe.

### Décision

Corriger `_motif` (ajouter `$` aux terminateurs acceptés), pas réécrire la
sonde. Retirer de la dette exactement les 5 entrées dont l'appelant réel a
été confirmé par lecture directe du site d'appel, pas par confiance dans
le nouveau chiffre. Pour les 113 entrées restantes, aucune n'a été
supprimée sans preuve suffisante d'un appelant absent, d'un chemin
indirect absent et d'un contrat documenté absent : `/healthz`, `/readyz`,
`/system/status` sont des conventions de sonde d'infra ; `/legacy/*` est
un pont de compatibilité documenté (P-002) ; `/collaboration/*` est
fonctionnel et testé mais délibérément non câblé au pipeline de mission,
déjà documenté comme tel (HOS-070, initiative séparée et plus large que
ce chantier) ; `/studio/*` et une partie de `/git/*` ont des appelants
opérateur réels dans `scripts/`, pas dans le frontend. Aucune de ces
routes n'appartient à G-16 : les supprimer aurait été une réduction de
chiffre sans preuve, exactement ce que ce chantier interdisait.

### Ce qui a été livré

`_motif` accepte `$` en fin de chemin. Nouveau test
`test_l_interpolation_ne_masque_pas_un_appelant_reel` : vérifie
explicitement que les 5 routes réintégrées ne repassent pas orphelines —
neutraliser le `$` dans `_motif` le fait rougir avec
`test_aucune_route_neuve_sans_appelant_frontend`, restaurer le `$` les
rend verts (mutation vérifiée). Dette : 118 → 113 entrées sur 314 routes.
Documentation en commentaire pour `/logs/{session_id}`, seule entrée dont
le statut « orphelin » et le résultat brut de la sonde divergent, pour
qu'un futur lecteur ne la retire pas sur la foi du chiffre.

## HOS-294 — `assigned_tools` planifié, jamais invoqué (2026-09-12)

G-11. Ferme le chantier opérationnel #5.

### Le défaut

`AgentCoordinator._select_tools` recommande des outils par correspondance
de mots-clés entre le titre d'une tâche et le catalogue de plugins MCP
(klaatcode/oh_my_pi). Le constat d'origine (HOS-069,
`task_executor.py:31`) : rien n'invoque jamais cette recommandation — les
deux seuls chemins d'exécution réels vivent dans un espace de noms
disjoint. Hermes Agent choisit ses propres outils par son propre MCP
(HOS-085 l'interdit à Hermes OS) ; la boucle locale de Hermes OS
(`_run_tool_loop`, le seul chemin où elle possède réellement sa propre
boucle) n'offre qu'un jeu fixe `workspace_*`/`verification_*`, sans
rapport avec le catalogue de plugins.

Ce que le constat d'origine ne disait pas, et que cette passe a mesuré :
ce champ jamais invoqué atteignait quand même l'opérateur. Vue nominative
sur `mission_executor.py`, `execute_task` renvoyait
`"tools": task.assigned_tools` aux côtés de `"agent"`/`"runtime"`/`"model"`
— trois champs qui rapportent, eux, ce qui a réellement servi, pas ce qui
avait été demandé. `finalize()` agrégeait la même recommandation dans
`ExecutionReport.tools_used`, un champ nommé « used » et jamais rempli par
une mesure. Ce rapport est le producteur documenté de
`FeedbackLoop.get_memory_input`/`get_intelligence_input` (Memory,
Knowledge Graph, Runtime Intelligence) — actuellement sans appelant, donc
sans dommage constaté aujourd'hui, mais un champ qui ment sur ce qui a
tourné ne devient dangereux que le jour où quelqu'un le branche, pas le
jour où on le corrige.

### Décision

Deux voies fermaient G-11. Invoquer réellement `assigned_tools` — rejeté :
sur le chemin hermes-agent cela violerait HOS-085 (Hermes OS choisissant
les outils du cerveau) ; sur le chemin local cela exigerait un second pont
d'outils vers un catalogue que ce chemin ne peut de toute façon pas
exécuter, une architecture nouvelle et disproportionnée pour une dette
classée *technical debt* et non *architectural* dans
`HERMES_OS_MASTER_ROADMAP.md`. Arrêter de faire passer la recommandation
pour une mesure — retenu : c'est le changement minimal, et
`_run_tool_loop` mesurait déjà un signal réel voisin
(`tool_calls_made`, un compte) sans jamais le faire remonter jusqu'au
rapport.

### Ce qui a été livré

`_run_tool_loop` capture désormais aussi les **noms** des outils
réellement appelés (`tools_invoked`, dédupliqués en ordre de première
apparition — un outil appelé trois fois est un outil qui a tourné, pas
trois). `TaskExecution` gagne un champ `tools_used`, peuplé par
`MissionExecutor` depuis les métadonnées réelles de l'outcome, sur le même
idiome que `model_used`/`provider_used` (HOS-241/242) : ce qui a réellement
servi, distinct de ce qui avait été demandé. `execute_task` et
`finalize()` rapportent désormais `tools_used`, jamais `assigned_tools`.
Sur le chemin hermes-agent, `tools_used` reste honnêtement vide — Hermes
OS n'observe pas ce que le cerveau invoque sur sa propre connexion MCP, et
le repêcher depuis `assigned_tools` aurait reproduit exactement G-11.
`assigned_tools` lui-même n'a pas bougé : il reste le texte indicatif
documenté dans le prompt, jamais une invocation.

### Preuves

`backend/tests/test_g11_outils_reellement_invoques.py`, 6 tests neufs.
Niveau `MissionExecutor` : le rapport par tâche et le rapport agrégé
portent ce qu'un exécuteur scripté déclare avoir réellement invoqué, pas
ce qu'un outil enregistré et keyword-matché sur le titre de la tâche
aurait fait recommander par le coordinateur — les deux listes sont
délibérément différentes dans le montage pour qu'une confusion se voie ;
mutation vérifiée à la main (`tools`/`tools_used` repointés sur
`assigned_tools`) : 3 des 6 tests rougissent exactement sur l'assertion
attendue, remis au vert ensuite. Cas limite : sans `tools_invoked` dans les
métadonnées (le chemin hermes-agent), le rapport reste `[]`, jamais
repêché depuis `assigned_tools`. Niveau `RealTaskExecutor` : la boucle
locale, exercée contre un vrai workspace et un vrai Aegis (fixture
existante de `test_real_task_executor.py`), rapporte les noms réels
appelés ; un second montage vérifie qu'un outil appelé deux fois
(`workspace_exists`, `workspace_exists`, `workspace_read`) ne compte
qu'une fois dans `tools_invoked` tout en laissant `tool_calls_made` à 3.

Aucun test existant modifié dans son intention. Suite complète : voir le
rapport de fin de chantier.

### Limites dites

- `assigned_tools`/`AgentCoordinator._select_tools` restent en place,
  décoratifs par construction : les retirer toucherait cinq fichiers de
  test qui construisent des `TaskExecution(assigned_tools=[...])` sans
  rapport avec ce chantier, pour un gain qui n'est pas celui que G-11
  visait (le rapport mentait, pas le champ lui-même).
- `FeedbackLoop.get_memory_input`/`get_intelligence_input` restent sans
  appelant — `tools_used` y arrive maintenant honnête, mais brancher ces
  méthodes est un chantier distinct, non ouvert ici.
- Le chemin hermes-agent ne rapporte toujours aucun outil réellement
  utilisé, par construction (HOS-085) : c'est un vide honnête, pas une
  mesure manquante à combler.

## HOS-293 — Un verdict agentique est une mesure datée (2026-09-12)

G-15. Ferme le chantier opérationnel #4.

### Le défaut

`agentic_probe.py` mesure si un modèle sait piloter la boucle d'outils de
Hermes Agent et persiste le verdict sous `db/agentic_probe_results.json`,
indexé par le seul **tag** du modèle (`measured_success_for(model)`).
Rien dans cette clé ne dépend de ce que le tag désigne réellement.

Deux événements changent cela sans changer le tag :

- `ollama pull`/`ollama create` remplaçant les poids sous le même nom ;
- un Modelfile édité pour servir un autre `num_ctx`.

Dans les deux cas, mesuré sur le magasin réel : le verdict stocké reste en
place, `measured_success_for` continue de répondre `True` pour un modèle
qui n'est plus celui qui a été sondé, et ce `True` atteint sans obstacle
le prédicat de production
(`service_registry._agentic_capable_for`/`_agentic_capable_cached`) puis
la décision du routeur (`RealTaskExecutor._agentic_model`, T-29/HOS-263) —
qui garde alors un modèle choisi sur une preuve qui n'en est plus une.

Le même défaut de principe existait déjà et avait été fermé une fois,
ailleurs : `hermes_agent_bridge.NegociationRuntime` met en cache la
négociation de capacités du pont sous l'**empreinte du runtime** (version
+ commit de l'agent installé), justement pour qu'une mise à jour la périme
d'elle-même. Le magasin de sondes n'avait jamais reçu le même traitement.

### Ce qui a été livré

Chaque entrée du magasin porte désormais une **empreinte** mesurée avec
elle :

- `digest` — lu sur `/api/tags`, un hash de contenu que le pull remplace
  quand les poids changent, et qui ne dépend jamais d'une horloge ;
- `num_ctx` — parsé dans le texte `parameters` que `/api/show` renvoie
  (`PARAMETER num_ctx …` du Modelfile), la même valeur qu'`ollama show
  --modelfile` afficherait.

`measured_success_for` la revérifie à **chaque lecture** contre ce
qu'Ollama sert maintenant pour ce tag : un écart rend `None` — non prouvé,
et non pas prouvé faux, la distinction à trois états que T-29 avait déjà
posée pour un motif voisin — plutôt que la valeur périmée. `save_result`
applique la même règle en écriture : si l'empreinte stockée diffère de
celle mesurée maintenant, la série repart à zéro avant d'accumuler le
nouvel essai, pour ne jamais faire état d'un taux de succès qu'aucun
modèle unique n'a produit. Une empreinte introuvable (Ollama injoignable,
tag absent de son catalogue) échoue **ouvert** — traitée comme « ne peut
pas être vérifiée », jamais comme « a changé » — parce que le seul
appelant réel a déjà réussi un `/api/show` sur exactement ce modèle avant
de poser la question ; un échec de vérification à ce stade est un aléa
réseau, pas une preuve.

Aucun TTL introduit : l'invalidation suit un changement d'état réel
(poids, `num_ctx`), jamais une horloge — la distinction que CLAUDE.md fait
explicitement pour ce chantier. Un aller-retour vers une empreinte
bit-identique, sans sonde enregistrée pendant l'écart, redevient
indiscernable d'un état qui n'a jamais changé : c'est le contrat choisi
(l'empreinte fait foi, pas un compteur de générations que ce magasin ne
tient pas), documenté dans le code plutôt que supposé.

### Preuves

Chemin réel démontré de bout en bout, pas seulement au niveau du module :
un modèle mesuré capable (`True`) dont les poids changent sous le même
tag redevient `None` au prédicat de production
(`service_registry._agentic_capable_for`), et `RealTaskExecutor._agentic_model`
substitue alors le repli — mesuré capable entre-temps sous sa propre
empreinte — là où l'ancien code aurait conservé la décision sur la foi
d'un verdict périmé (`backend/tests/test_preuve_agentique.py::test_le_repli_ne_defait_plus_une_decision_sur_une_preuve_perimee`).

Redémarrage inter-processus : trois interprètes Python distincts
partageant `HERMES_DATA_DIR` — l'un mesure sous une empreinte, le second
lit après un changement de poids simulé et obtient `None`, le troisième
remesure sous la nouvelle empreinte et obtient un verdict qui ne mélange
pas l'ancienne série
(`test_linvalidation_dempreinte_survit_au_redemarrage`).

15 tests neufs entre `backend/tests/test_agentic_probe.py` et
`backend/tests/test_preuve_agentique.py`, chacun rouge sur le code
d'avant cette passe puis vert après — vérifié explicitement par un
`git stash` du seul fichier corrigé. Aucun test existant modifié dans son
intention ; l'aide `_ollama_bouchonne` a gagné un paramètre optionnel
(`model`/`digest`/`num_ctx`) qui, laissé à sa valeur par défaut, reproduit
exactement le comportement précédent pour les 14 tests qui ne le
demandent pas.

Suite complète : voir le rapport de fin de chantier. `data/db/hermes.db`
et toute donnée utilisateur inchangées ; aucune autorité de sécurité
touchée ; aucun réseau réel appelé en test (Ollama, quand il répond dans
cet environnement, ne connaît aucun des tags synthétiques utilisés).

### Limites dites

- Aucune route HTTP, aucun outil MCP n'exposent ce magasin : les seuls
  consommateurs réels sont `service_registry._agentic_capable_cached`
  (le chemin de mission) et `scripts/sonder_modeles.py` (l'écriture). Il
  n'y avait rien d'autre à démontrer sur ces deux surfaces-là.
- `current_fingerprint` ajoute jusqu'à deux appels HTTP à Ollama par
  vérification ; `_agentic_capable_cached` en fait déjà un pour les
  capacités déclarées. Les trois ne sont pas fusionnés — un gain de
  performance mineur, hors périmètre de G-15, qui porte sur la justesse
  de l'invalidation et non sur son coût.
- Les entrées écrites avant cette passe ne portent aucune empreinte et
  restent donc dignes de confiance sans contrôle jusqu'à leur prochaine
  écriture — une migration explicite plutôt qu'une invalidation générale
  rétroactive, qui aurait effacé silencieusement tout le catalogue déjà
  sondé par G-14.

## HOS-292 — Valider un dossier n'a jamais dit qui peut y toucher (2026-09-11)

A-4. Ferme le chantier opérationnel #3.

### Le défaut

Enregistrer et valider un projet élargissait la liste blanche d'Aegis
pour **toute** action, y compris celles qui ne nommaient aucun projet.
`_dynamic_allowed_paths` rendait `active_validated_project_roots()` —
l'union de tous les projets actifs et valides — et la passait en
`extra_allowed_paths` à chaque appel, quel que soit le projet demandé.

Mesure du 2026-09-11, deux projets synthétiques tous deux actifs et
valides, lecture de `ws-b/secret.txt` :

    project_id=A      -> deny    (le rétrécissement fonctionnait déjà)
    project_id=None   -> allow   (et le contenu de B était rendu)

Sur la base réellement servie — `%LOCALAPPDATA%\HermesOS\db\hermes.db`,
pas celle du dépôt — cette union comptait **60 racines**, dont
`C:\Users\emeri\Skill360 Industry` et sept dossiers directement sous
`C:\Users\emeri`. Un `files_read(chemin)` MCP sans `project_id` les
atteignait toutes. C'est ce que voulait dire « portée projet validée,
non **autorisée** » : la validation prouve qu'un dossier existe et qu'on
peut y écrire ; elle n'a jamais dit *qui* peut y toucher.

La surface MCP rendait le défaut le plus grave, parce que c'est la seule
où `project_id` est littéralement un argument que le modèle écrit.

### Ce qui a été livré

L'habilitation devient **nominative**. `_workspace_grant` n'accorde que
la racine du projet que l'action nomme, et seulement tant qu'il est
`ACTIVE` + `validation_status="valid"`. Une action qui ne nomme aucun
projet ne porte aucune habilitation de workspace ; il lui reste la liste
blanche statique, celle qu'un humain a écrite dans la configuration et
que ce jalon ne touche pas.

Le prédicat « ce projet autorise-t-il, en ce moment ? » était écrit
**trois fois** — dans `store.active_validated_project_roots`, dans
`conversation/routes._active_validated_project_root` et dans
`service_registry._workspace_project_for`, les deux dernières se
décrivant elles-mêmes comme « la même vérification, répétée ». Il vit
désormais dans `projects.store.authorized_root`, et les trois y
délèguent. Trois copies d'une règle de sécurité sont trois occasions de
diverger.

### Deux défauts absorbés en chemin

**L'offre d'outils était gardée, l'exécution ne l'était pas.** Les
schémas `workspace_*` ne sont proposés au modèle que si un projet
autorisé est lié — mais rien n'empêchait `execute_workspace_tool` de
s'exécuter quand même. Avec `project_root=""`, `resolve_in_project`
résout sous le **répertoire courant**, c'est-à-dire la racine du dépôt
Hermes OS, couverte par `ALLOWED_PATHS` par défaut. Le refus ne tenait
qu'à un `project_id` vide tombant sur « projet inconnu », donc sur une
*validation humaine en attente* : un accord donné par distraction aurait
ouvert le dépôt à une conversation sans projet. Les deux exécuteurs —
workspace et runners de vérification — re-résolvent maintenant la racine
depuis le magasin et refusent franchement sinon. Ils n'autorisent rien :
`file_tools` repasse par Aegis pour chaque opération.

**Un `project_id` introuvable court-circuitait la frontière.**
`_resolve_decision` rendait `REQUIRE_HUMAN_VALIDATION` **sans jamais
appeler le moteur**, et `_apply_human_consent` transforme un
`REQUIRE_HUMAN_VALIDATION` approuvé en `ALLOW`. Mesuré, `ALLOWED_PATHS`
réduit à un seul dossier, cible hors de toute liste blanche :

    project_id='inexistant-xyz'  -> require_human_validation
    puis un seul accord humain    -> allow

Un projet qui n'existe pas ouvrait n'importe quel chemin du disque au
premier « oui ». Le commentaire de `_apply_human_consent` promettait
pourtant l'inverse — « A DENY is never upgraded: those come from the
hard boundaries » — et il disait vrai : la frontière n'était simplement
jamais consultée, donc il n'y avait pas de DENY à ne pas relever. Le
moteur est désormais interrogé d'abord ; un DENY reste un DENY, et la
suspicion (§17.3) ne s'applique plus qu'à un chemin que le moteur aurait
laissé passer.

Le `''` compte double : c'est ce que **MCP** transmet pour un argument
`project_id` omis, mesuré sur une vraie session streamable-HTTP. Tout
appel MCP non nommé déposait donc un accord en attente au lieu d'être
refusé — et polluait la file de validation de l'opérateur. Ne nommer
aucun projet n'est pas nommer un projet inconnu.

### Le panneau Projet, cassé puis réparé par la mesure

Trouvé au navigateur, pas en relisant du code : le panneau affichait
« statut git indisponible » sur un workspace pourtant validé.
`gitClient.status` appelait `/git/status?repo_path=…` **sans**
`project_id` — légitime sous l'union, refusé sous l'habilitation
nominative. Relevé : `403 Forbidden` avant, `400 Bad Request` après,
c'est-à-dire la vraie réponse de git sur un dossier qui n'est pas un
dépôt. Le paramètre est passé ; `createPullRequest` avait la même forme
et le reçoit aussi.

C'est le genre de régression qu'aucune suite verte n'attrape : les deux
appels étaient corrects, seule leur *autorisation* avait changé.

### Preuves

- **Serveur en marche**, chaîne produit complète (POST /projects →
  POST /validate → GET /files, /files/content, /files/apply) : 19/19.
  Même fichier, même instant — 200 en nommant le projet, 403 sans.
- **Vrai client MCP** en streamable-HTTP contre `/mcp` : 14/14. Les 12
  outils fichiers sont publiés ; `files_read` sans `project_id` refuse,
  avec le bon `project_id` rend le contenu, avec celui d'un autre projet
  valide refuse.
- **Au navigateur** : workspace enregistré → `unvalidated`, les deux
  lectures en 403 ; après « Valider ce workspace » → `valid`, 200 en
  nommant, 403 sans. Puis un tour de chat réel sur un jeton écrit sur le
  disque *entre deux tours* — `JETON-5B5BE8AF74EF` — rendu exactement,
  donc la lecture est réelle et non devinée.
- **Après redémarrage**, deux processus distincts sur le même SQLite :
  le projet actif+valide autorise encore, celui archivé avant le
  redémarrage n'autorise plus, et une action anonyme reste refusée —
  aucune élévation implicite.
- **14 mutations adversariales**, chacune rouge puis verte : union
  restaurée, garde du chat retirée, frontière réduite à un préfixe de
  chaîne, Aegis contourné depuis `file_tools`, outil MCP lisant le
  disque en direct, mutation sans accord, traversée non normalisée,
  liste statique supprimée, outils offerts sans projet, route HTTP
  lisant en direct, projet non autorisé passé pour autorisé, projet
  inconnu court-circuitant la frontière, `''` traité en projet inconnu,
  DENY redevenu négociable.

La mutation « traversée non normalisée » a d'abord laissé **toute** la
suite verte : les tests de traversée existants résolvaient le chemin
eux-mêmes avant de le passer, si bien qu'aucun n'exerçait le `.resolve()`
d'Aegis. Or MCP et HTTP transmettent la chaîne brute de l'appelant, et
`<racine_a>/../ws-b/secret.txt` est lexicalement « intérieur à A ». La
garde était bonne, personne ne la tenait.

### Ce que ce jalon ne prouve pas

Quand un projet est lié **et** que Hermes Agent est prêt, le chat est
servi par le harnais (ACP), pas par les outils de Hermes OS : la lecture
est alors faite par les outils propres à l'agent, bornés par la
frontière du client ACP et le hook `pre_tool_call` (HOS-141), **pas par
Aegis**. Ce qui relève de HOS-292 sur ce chemin, et qui est acquis,
c'est *quel* workspace est remis à l'agent — `authorized_root` en décide,
avec le même prédicat que partout ailleurs. Ce qu'il fait à l'intérieur
relève d'une autre autorité, par construction : Hermes Agent est le
cerveau et possède sa boucle d'outils.

Conséquence pratique à ne pas oublier : lier un projet est précisément
ce qui bascule vers le harnais, donc la surface d'outils de chat gardée
par Aegis est le **repli**, pas le cas courant.

## HOS-291 — On prenait un filet qu'on ne savait pas rendre (2026-09-11)

A-3. Ferme le chantier opérationnel #2.

### Le défaut

`GraphExecutor._prendre_le_filet` pose un point de reprise avant que
**toute** mission touche au disque. Le Center « Supervision » les
affiche. Et `restaurer()` avait, depuis HOS-223, **zéro appelant** :

    checkpoint.prendre     1 appelant  (graph_executor)
    checkpoint.lister      2 appelants (vue_operations, sante)
    checkpoint.apercu      0
    checkpoint.restaurer   0     ← A-3
    checkpoint.supprimer   0
    route de restauration  aucune ; `/operations/checkpoints` est en GET

C'est la forme la plus coûteuse de capacité fantôme : elle n'est pas
absente, elle est **visible**. Un opérateur qui lit « 4 points de
reprise » en conclut qu'il peut annuler, et découvre le contraire au
moment où il en a besoin.

### Ce qui a été livré

La lecture reste où elle était. `routes/operations.py` est en lecture
seule **par contrat** — deux gardes le tiennent, et son en-tête dit
pourquoi : une vue qui écrit devient un second chemin vers l'état. La
mutation vit donc sur son propre routeur, `routes/checkpoints.py`, comme
`routes/snapshots.py` le fait déjà pour la moitié « état » :

    GET  /api/v1/checkpoints/{id}/apercu      ne mute rien
    POST /api/v1/checkpoints/{id}/restaurer   passe par Aegis

Le panneau « Points de reprise » du Center Supervision déplie l'aperçu et
porte le bouton. Il est là et pas ailleurs parce que c'est là que les
points de reprise sont listés : un bouton « revenir » sur un autre écran
que celui qui montre **à quoi** revenir se choisirait à l'aveugle.

### La restauration est en deux temps, et c'est le contrat

`data_migration` est `mandatory_validation` dans `config/security.yaml`.
Le premier appel ne restaure donc **jamais** : Aegis dépose un accord
dans la file que le Security Center sert déjà, et l'opérateur le décide.
Un refus rend `200` avec `restaure: false` et son verdict — réserver un
`4xx` ferait lire une gouvernance qui fonctionne comme une panne.

Mesuré au navigateur, chaîne complète : clic → HTTP → Aegis → accord en
attente, **workspace inchangé** → décision humaine → second clic →
`src/app.py` réécrit, `LISEZMOI.md` recréé, `src/genere_apres.py`
supprimé, accord passé à `used`. Puis un **second processus** (PID
distinct) relit le workspace restauré, retrouve le point de reprise, et
ne trouve aucun accord réutilisable.

### Trois défauts trouvés en chemin, sur le chemin même d'A-3

**Un accord n'identifiait pas son point de reprise.** L'empreinte
d'approbation ignore la description depuis HOS-224 : elle ne retient que
`action_type`, le chemin canonique et les **discriminants**. Ni
`checkpoint.restaurer` ni `snapshot_manager.restore_snapshot` n'en
passait. Mesuré :

    checkpoint A (« il y a 5 min »)   28460aea9e6e…
    checkpoint B (« il y a 3 sem. »)  28460aea9e6e…   même empreinte
    snapshot de ce matin              c388eae7bd12…
    snapshot d'il y a six mois        c388eae7bd12…   même empreinte

Un « oui » pour revenir cinq minutes en arrière autorisait donc de
revenir trois semaines en arrière — sur un geste qui détruit tout ce qui
a été fait depuis. C'est exactement le défaut que HOS-224 avait corrigé
pour `git_tools` (« une approbation pour *Commit on feature/x* n'autorise
pas *Commit on main* »), reproduit ici faute de discriminant. Les deux
appelants en portent un.

**Un état refusé était annoncé repris.** `restore_snapshot` *rend* un
refus, il ne le lève pas — c'est écrit dans son contrat. Et
`_restaurer_l_etat` ne lisait pas ce retour : tout appel qui ne levait pas
comptait comme repris. Trouvé sur le chemin réel, pas en relisant du
code : les fichiers étaient revenus, l'accord de la moitié état était
**encore en attente dans la file**, la réponse annonçait
`etat_repris: true`, et la tâche était restée `done` là où l'instantané
la portait à `todo`. Un faux succès sur une restauration est le pire
endroit possible pour en avoir un — l'opérateur croit être revenu en
arrière et repart de l'état cassé.

**Une copie abîmée rendait une 500.** `repli_fichiers` vérifie les
empreintes avant d'écrire quoi que ce soit, et lève `RepliCorrompu` : la
protection était bonne, sa traduction manquait. Un point de reprise
inutilisable rend maintenant `409`, et rien n'a été écrit.

### Une sonde corrigée avant le code

La première sonde de cette passe affirmait qu'un workspace hors
`ALLOWED_PATHS` produirait un `DENY` dur. **Faux, et c'est la sonde qui
avait tort** : `data_migration` est `path_based: false`, donc la liste
blanche n'est jamais consultée pour cette catégorie. Le contrôle réel est
*entièrement* la validation humaine obligatoire. Enregistré comme **A-22**
plutôt que corrigé : basculer la catégorie en `path_based` refuserait du
même coup **toute** restauration d'instantané, qui passe
`target_path=None` — mesuré `deny`. C'est une décision de politique, pas
un effet de bord d'A-3.

### Portée réelle, et ce qui reste ouvert

Le seul producteur de points de reprise prend `avec_etat=False` : **aucun
point de reprise de production ne porte d'instantané**. La moitié
fichiers — la seule qui existe aujourd'hui — est donc close de bout en
bout. Le couple, lui, demande deux accords distincts (deux empreintes),
ce qui est mesuré, dit honnêtement à l'opérateur, et enregistré en
**A-23** au lieu d'être masqué.

### Une seconde sonde corrigée, la mienne cette fois

La suite de référence a été mesurée au commit de base dans une copie de
travail neuve, pour ne pas avoir à annoncer un chiffre par soustraction.
Elle a rendu **1 échec** — et l'échec était dans l'instrument : git
convertit les fins de ligne à la sortie, `plugin.yaml` passe de 304 à 310
octets et `__init__.py` de 4795 à 4914, et
`test_le_depot_reste_la_source_du_plugin_installe` compare des octets. Le
plugin installé est **identique au dépôt principal**, vérifié par `cmp`.

Référence réelle : **6218** au commit de base, **6231** ici, 13 tests
ajoutés. Aucune régression. La fragilité de la garde est enregistrée en
**A-25** — son contrat est juste, son instrument est trop strict d'un
cran.

**A-24** : `prune_snapshots` et `StepCounter` n'ont aucun appelant de
production. Le §19.3 demande un instantané tous les N pas ; `every` vaut
10 et personne ne compte. Rien ne borne la croissance : 26 instantanés
sur la machine réelle pour un `keep` de 20.

## HOS-290 — Le pare-feu ne voyait pas la clé de son propre fournisseur (2026-09-11)

A-10. Ferme §4.

### Le défaut, en un caractère

    _SECRET_PATTERNS :  \bsk-[A-Za-z0-9]{16,}\b

`-` n'est pas dans la classe. Une clé OpenRouter s'écrit
`sk-or-v1-<64 hexadécimaux> ` : après `sk-`, le moteur lit `or`, bute sur
le tiret, et `{16,}` échoue. Le pare-feu reconnaissait la clé d'OpenAI et
laissait passer celle d'**OpenRouter — le seul fournisseur cloud que ce
dépôt appelle réellement**.

Relevé au commit `25ddb52`, avant correctif, sur `pare_feu.examiner` :

    sk-<32 alnum>                        REFUSE     (A-1, correct)
    sk-or-v1-<64 hex>                    AUTORISE   ← le défaut
    … nue, début, milieu, fin,
      guillemets, deux-points, point,
      URL — 8 placements               8× AUTORISE

A-1 (HOS-255) avait mesuré ce défaut **en passant**, l'avait consigné
dans sa propre docstring et ne l'avait pas corrigé : c'était un défaut de
**détection**, quand A-1 traitait le **routage**. Les deux sont
maintenant fermés, et les deux fichiers de garde restent séparés parce
qu'ils prouvent deux choses différentes — l'un qu'aucun chemin n'échappe
au pare-feu, l'autre que le pare-feu voit ce qu'il doit voir.

### Une ligne, dans le scanner qui existait déjà

`pare_feu.py` ne porte aucun détecteur : il délègue à
`audit_log.redact`, qu'il nomme « le plus proche d'un `secret_scanner`
que ce dépôt possède ». Le correctif vit donc là, et nulle part ailleurs.
Ni second scanner, ni détecteur OpenRouter dédié, ni règle parallèle dans
le pare-feu.

    \bsk-(?:[a-z0-9]{1,8}-){0,3}[A-Za-z0-9]{16,}\b

Les segments intermédiaires sont les étiquettes de fournisseur qui vivent
entre le schéma et l'entropie (`or-v1-`, et `ant-`/`proj-` ailleurs). Ils
sont **bornés** — trois au plus, huit caractères chacun — pour que la
règle reste une forme de clé et non « tout ce qui contient sk- ». Le
plancher d'entropie de 16 caractères est conservé tel quel : c'est lui
qui garde la prose dehors.

### Le risque réel du correctif était le faux positif

Un pare-feu qui refuse tout est un pare-feu qu'on désarme dans la
semaine — la leçon du canary (HOS-218). Sept textes que quelqu'un écrit
vraiment en parlant d'OpenRouter sont donc vérifiés **non bloquants** :

    le préfixe sk-or identifie OpenRouter
    le format d'OpenRouter est sk-or-v1-<hex>
    un profil risk-reward intéressant
    identifiant sk-abc123 dans le ticket
    extrait : sk-or-v1-0123abcd (tronqué)
    ne colle jamais ta clé OpenRouter ici
    lis OPENROUTER_API_KEY dans l'environnement

La mutation qui abaisse le plancher d'entropie à 1 fait rougir ces
gardes-là : elles sont causales, pas décoratives.

### La preuve est à la socket, pas au joint de test

`httpx.MockTransport` prouve qu'aucune requête n'est **construite**. Il
ne prouve pas qu'aucun octet n'atteint une socket, puisqu'il remplace
précisément la couche qui la tient. La preuve finale laisse donc
`transport=None` — le vrai transport réseau — et pointe `base_url` sur un
serveur HTTP local qui compte les connexions acceptées :

    chat         secret    →  0 requête   REFUS avant émission
    chat         légitime  →  1 requête   réponse reçue, message intact
    chat_events  secret    →  0 requête   REFUS avant émission
    aucun corps reçu ne contient la clé

### Mutations

Cinq, toutes rouges, aucune conservée :

    A  motif OpenRouter retiré            16 rouges
    B  plancher d'entropie ramené à 1      4 rouges  (les faux positifs)
    D  `_filtrer` retiré de chat          10 rouges
    E  `_filtrer` retiré de chat_events    7 rouges
    F  le refus n'interrompt plus l'envoi 12 rouges

F est celle qui compte : elle démontre que `appels == 0` mesure bien le
refus, et non l'absence de serveur.

### Preuves

Suite backend complète verte. Aucun secret réel n'a été lu ni écrit :
toutes les clés des tests sont fabriquées dans leur propre fichier.
`data/db/hermes.db` intacte, aucune donnée utilisateur touchée, aucune
autorité de sécurité ajoutée — Aegis et le pare-feu restent ce qu'ils
étaient.

### Le document qui manquait est arrivé pendant la passe

Le brief nommait `docs/HERMES_OS_OPERATIONAL_ROADMAP.md` et
`docs/HERMES_OS_CLAUDE_CODE_PROMPT_PROTOCOL.md` comme sources à lire
d'abord. Ni l'un ni l'autre n'existait dans l'arbre local, et je l'ai
signalé plutôt que de supposer leur contenu. Ils étaient sur `origin/main`,
poussés après `25ddb52` : `main` local était **en retard de quatre
commits**, tous purement documentaires. Intégrés en avance rapide — aucun
recouvrement avec le correctif, donc aucun conflit possible.

La roadmap opérationnelle est désormais la source d'ordre : elle impose un
chantier actif unique, et elle portait déjà G-41 et les deux limites de
couverture déclarées en HOS-289. Elle passe A-10 en 🟢, §4 en 🟢, et
A-3 devient le chantier actif.

### Écart consigné, non traité

Le motif `key=value` de `redact` liste `api[_-]?key`, `access[_-]?key`,
`private[_-]?key` mais **pas `key` seul** : `OPENROUTER_KEY: <valeur>`
n'est donc pas caviardé *par cette règle-là*. Ici la valeur est prise par
la règle de forme, donc rien ne fuit ; mais une clé d'une autre forme
derrière un nom en `…_KEY` passerait. Hors périmètre A-10 (défaut de
nommage, pas de format OpenRouter), inscrit comme gap.
## HOS-289 — Les vingt Centers jamais ouverts (2026-09-11)

G-40. Vingt-deux Centers n'avaient jamais ete regardes. Plutot que vingt-deux
audits indistincts, un instrument : chercher la signature du defaut deja
trouve deux fois, puis n'ouvrir que ce qu'il designe.

### L'instrument, calibre avant d'etre cru

La signature de HOS-288 : **un tableau d'objets pose dans le JSX et rendu par
`.map()`, dont toutes les valeurs sont des litteraux**. Un descripteur de
presentation — colonnes, onglets, tuiles — *reference* quelque chose ; une
donnee inventee ne reference rien.

Calibre sur le Security Center d'avant G-39, ou il retrouve les trois blocs
connus. Sans ce calibrage il n'aurait rien prouve. Resultat sur 26 fichiers :

    system-center.tsx        risque 9   3 blocs litteraux
    evolution-center.tsx     risque 3   1 bloc litteral
    les 24 autres                       0

### Ce que le premier instrument voyait

**System Center** — douze lignes de composants ecrites en dur, avec des
latences (« 1.5 ms »), des compteurs d'evenements et des etats « healthy ».
L'une d'elles nommait `policy.engine`, supprime en G-38. Le fichier portait
pourtant un commentaire affirmant qu'une passe anterieure avait derive les
compteurs du registre vivant : elle avait corrige les constantes **nommees**
et laisse le tableau inline. Le meme demi-nettoyage qu'au Security Center.

`/system/health` rend `detail` — chaque sous-systeme, son etat, la raison
quand il est inconnu. Ni latence ni compteur par sous-systeme : ces deux
colonnes n'avaient aucune source. Le tableau rend desormais la charge utile
reelle, 34 sous-systemes, vus dans le navigateur.

**Evolution Center** — quatre « patterns d'optimisation » : « 12x, succes
85 %, +22 % ». `/evolution/patterns` rend 404 ; rien n'agrege de motif. La
carte explique maintenant l'absence au lieu de la combler.

Deux blocs litteraux du System Center ont ete **conserves** : l'ordre
topologique et les couches d'architecture decrivent une structure, pas un
etat. La regle du brief tient dans les deux sens — ne pas supprimer une
donnee statique sans avoir determine si elle est legitimement descriptive.
Ils sont declares comme tels, et de-perimes au passage (`Policy Engine` y
figurait encore).

### Ce que le premier instrument NE voyait pas

Un compteur n'a pas besoin d'un tableau pour etre invente. Le detecteur ne
lisait que les `.map()` ; trois lignes de prose lui echappaient, dans le
System Center :

    Aucune dependance cyclique detectee
    25 composants dans l'ordre topologique
    42 aretes de dependance suivies

`ServiceHealthProbe.health()` rend `status`, `services`, `by_status`,
`unhealthy`, `silent`, `detail`. **Ni arete, ni ordre, ni detection de
cycle.** Les deux compteurs n'avaient aucun producteur — la liste juste a
cote en montrait onze, pas 25 — et la troisieme ligne garantissait une
analyse qui n'existe pas. Le sous-titre du Center promettait la meme chose :
« et graphe de dependances ».

Un second passage, sur la prose cette fois, a rapporte neuf lignes. Six
etaient legitimes et le rester : la narration VRAM du Studio cite une mesure
reelle, son « releve toutes les 2 s » correspond a `refetchInterval: 2000`,
et une ligne d'`operations-center` etait un commentaire. Une ne l'etait pas.

### Un nombre qui avait cesse d'etre vrai

Le Tools Center oppose les outils **declares**, qui ne s'executent pas, aux
outils MCP, qui s'executent. Le contraste portait un chiffre : « 71 outils ».
`_ALL_TOOLS` en compte **81**. Le detail par famille — 12 fichiers, 9 git,
7 memoire — etait exact ; seul le total avait derive, dix outils Studio plus
tard, affiche avec la meme assurance que le reste. Une garde tient desormais
le lien au serveur : le chiffre ne peut plus bouger seul.

### Les gardes, et ce que les mutations ont appris

Onze mutations, onze rouges. Deux ont d'abord trouve **vert** :

- **l'exemption se prenait avec un mot.** Un bloc declare « description »
  etait exempte sans autre examen : poser `{/* description */}` au-dessus
  des quatre patterns inventes suffisait a les faire passer. L'exemption
  exige maintenant aussi que **tout nombre du bloc reste hors du rendu** —
  un descriptif decrit une structure, ses valeurs sont des chaines, et le
  seul nombre qu'il porte legitimement alimente une mise en page. Un nombre
  qui atteint le texte, ou qui ne sert a rien, est une quantite.
- **la garde pouvait etre videe sans bruit.** Une garde parametree sur un
  corpus vide est verte. Le corpus se decouvre par un motif de nom : un
  renommage, et elle s'applique a trois fichiers en silence. Un plancher
  rend cet effondrement bruyant.

Une troisieme garde a du etre **retrecie apres avoir signale mon propre
texte**. Elle cherchait les mots « arete », « cyclique », « ordre
topologique » dans l'ecran, et a rejete la phrase qui *nie* la capacite —
« aucune route n'en publie les aretes ni ne signale les cycles ». Un mot ne
dit pas si la phrase affirme ou dement ; un nombre colle au mot, si. La
garde ne porte plus que sur le chiffre.

### Ce qui a ete ouvert dans le navigateur

Les vingt-deux Centers du rail, un par un, via le `click()` programmatique
diagnostique en G-39. Tous rendent, aucun en etat d'erreur. Sur 304 requetes
API observees : **aucun 404, aucun 5xx**, et aucune vers `/approval`,
`/audit` ou `/policy/*` — le retrait de G-38 tient aussi sur le chemin reel.
Les trois corrections verifiees a l'ecran : 34 sous-systemes reels avec
leurs vraies raisons, l'absence de motifs expliquee, « 81 outils ».

### Ce qui reste non observe

- **Les onglets secondaires.** Chaque Center a ete ouvert sur sa vue par
  defaut ; les Centers a onglets (System, Governance, Skills) n'ont eu que
  le premier, sauf System dont l'onglet « Composants » portait la
  correction.
- **La classe « affirmation de capacite sans producteur » n'a pas de
  garde.** Le cas trouve ici est corrige et son chiffre tenu, mais aucune
  regex ne separe une affirmation d'une negation sans se tromper — la
  tentative l'a prouve sur mon propre texte. Une garde qui se trompe la
  ferait desactiver ; l'absence est inscrite plutot que maquillee.
- **Les ecrans a etat vide.** Beaucoup de Centers rendent peu parce que le
  systeme est au repos. Un ecran qui affiche correctement zero ligne est
  indiscernable, a l'oeil, d'un ecran qui n'affiche rien — seules les
  requetes observees le departagent, et elles l'ont fait ici.

### Les documents de suivi, remis a jour — et ce qu'ils montraient

Meme demarche appliquee au suivi lui-meme : non pas « quel document est
vieux », mais **quel document affirme quelque chose de faux**.

- **`ROADMAP.md`** — son tableau de mesures etait arrete au 2026-08-15 :
  « HOS-000 → HOS-111, 4 112 tests, 669 modules, 22 features ». Reel au
  2026-09-11 : **HOS-289, 6 466 tests collectes, 770 modules, 26
  features**. 178 numeros de jalon hors du tableau. Le fichier porte deja
  deux notes racontant ses deux decrochages precedents ; c'est le
  troisieme, avec la meme cause — il n'est pas sur le chemin d'une passe
  de roadmap, qui commence par l'etat.

### Le trou de suivi, trouve en remettant le suivi a jour

J'avais d'abord ecrit dans `ROADMAP.md` que le detail des jalons manquants
se lisait dans ce CHANGELOG, « qui, lui, n'a jamais decroche ». **C'etait
faux, et l'ecrire aurait mis dans un document de suivi exactement le genre
d'affirmation que cette passe traque dans les ecrans.** Mesure :

    entrees `## HOS-` de CHANGELOG.md        HOS-190 → HOS-289  (90)
    numeros HOS-112 → HOS-189 cites nulle part      66 sur 78
    numeros de cette plage portes par git           71

HOS-114 a HOS-118, par exemple, sont nommes par des commits et par aucun
document. **Ces jalons ont eu lieu ; c'est le suivi qui les a perdus.**

Rien n'a ete reconstruit : reecrire 66 entrees apres coup produirait un
recit, pas un releve. Le fait est consigne, et `git log --all --grep
HOS-1` reste la seule source pour cette periode.
- **`timeline.md`** — sa courbe de suite s'arretait a « 3703 (079) ». Le
  saut a 6190 est en grande partie **un artefact de mesure, pas une
  croissance** : jusqu'a HOS-111, `pytest.ini` n'executait que 1 190 des
  4 112 tests collectes. Une courbe lue a travers cette frontiere flatte.
  Le flake recurrent qu'il signale n'est pas apparu au relevé du
  2026-09-11 — ce qui est **une execution verte, pas une correction**.
- **`frontend-map.md`** — quatre affirmations demeneies par le code depuis.
  La plus nette : « the expand/collapse sidebar is gone entirely; there is
  no collapsed state anymore », alors que le rail porte une epingle
  (`railPinned`, `--rail-w-expanded`). Aussi : 22 Centers (25 montes),
  « 82/82 passing, 5 fichiers de test » (153 sur 13), et la lecture de
  sante du 2026-08-10.
- **`backend-map.md`** — « ~62 real tool functions » pour le serveur MCP.
  **Le meme chiffre qui avait derive dans le Tools Center**, dans un autre
  document, trouve en verifiant celui-ci. 81. L'ecran est desormais tenu
  par une garde ; **le document ne l'est pas**, et il le dit.

`docs/frontend-backlog.md` a ete laisse tel quel : c'est un releve date du
2026-08-13, revu le 08-15, qui renvoie explicitement la suite a
`ROADMAP.md` §C. Un instantane date n'est pas perime, il est situe.

### Preuves

**6190 passed, 3 skipped, 273 deselected, 0 failed** (7 min 18 s) sur
l'arbre final ; G-39 en comptait 6134, et les 56 de plus sont exactement
la garde neuve. `tsc` propre, 153 tests vitest. Onze mutations verifiees
une a une, base et etat restaure a zero rouge. `data/db/hermes.db` intacte
(mtime 2026-09-02), les 207 demandes historiques non touchees, aucune
autorite backend creee.
## HOS-288 — La verification transversale apres Policy (2026-09-11)

G-39. Le retrait de G-38 tient, et la verification a trouve autre chose.

### Ce que le depot porte encore, mesure

    imports de `backend.policy`                      0
    clients frontend visant une route absente        0  (131 chemins / 338 routes)
    entrees d'orphelins designant une route disparue 0  sur 118
    requetes vers /approval, /audit, /policy/*       0  observees au navigateur
    Aegis, journal §18, Run Ledger, Event Bus        200 les quatre

Les deux seules mentions de `backend/policy/` en code non-test sont des
commentaires qui **documentent** le retrait. Une reference historique n'est
pas une reference active, et la distinction est le sujet meme de la passe.

### La trouvaille : une securite inventee

Le Security Center portait **trois tableaux ecrits en dur** :

    quatre menaces    « Unauthorized file access · agent.unknown_dev · 3 occurrences »
    six politiques    « tool.exec: allow (Safety First) », « workspace.sandbox: deny »
    six profils       « Default LOW », « Air Gap MAX », avec sessions/memoire/CPU

Les routes reelles rendent `[]`, `[]` et `total_profiles: 0`.

Pire : `useSecurityThreats()` etait **deja appele et sa donnee liee puis
jetee**. Le reseau montrait un appel qui reussit pendant que l'ecran
montrait autre chose — et quatre menaces affichees avec un badge « high »
sont indiscernables de detections.

Un commentaire du fichier dit qu'une passe anterieure avait retire les
mocks. Elle avait retire les mocks **NOMMES** (`MOCK_STATUS`,
`MOCK_TRUST_SCORES`) et laisse les tableaux litteraux **inlines dans le
JSX**. On cherche `MOCK_` ; on ne cherche pas un tableau d'objets. C'est
pour cela qu'une garde les cherche desormais — et elle a demande deux
calibrages : la premiere version attrapait les descripteurs legitimes
(colonnes d'un tableau, onglets), la seconde se faisait tromper par
`"agent.unknown_dev"`, qu'elle lisait comme un acces de propriete. Les
chaines sont maintenant retirees avant de chercher une reference vivante.
Verifie contre la version d'avant : elle attrape les trois blocs.

Les trois cartes disent desormais ce qu'on sait et pourquoi : « aucune
detection, jamais aucune menace », « la politique reellement appliquee est
la matrice d'Aegis », « aucune route n'enumere les profils ».

### Un document de reference qui se trompait

`security-systems.md` — le fichier ecrit pour empecher qu'on confonde les
systemes de permission — affirmait que `PolicyEngine` avait « de vrais
appelants » dans `recovery_engine`, `workspace_manager` et
`runtime_decision`. **Aucun des trois n'importait `backend.policy`.** Ils
ont leurs propres moteurs, qui portent le meme nom : `RecoveryPolicyEngine`,
`WorkspacePolicyEngine`, et celui de HOS-016. Quatre objets appeles
« PolicyEngine », et le document cense les distinguer les confondait.

Un lecteur qui lui aurait fait confiance aurait cru que G-38 cassait trois
sous-systemes. Il n'en a casse aucun — 344 → 338 routes, rien d'autre perdu.

Corriges aussi : `backend-map.md` (ligne decrivant le module comme
« live »), `POLICY_ENGINE_ARCHITECTURE.md` (124 lignes ouvrant sur « The
Policy Engine **is** the central governance authority for Hermes OS. All
sensitive operations must pass through it » — supprime), un commentaire de
`security.py` au present, et le sous-titre du Governance Center, qui
annoncait encore « moteur de politiques ».

### La limite de preuve des trois dernieres passes, levee

Depuis G-34 je rapportais que la navigation du cockpit ne repondait pas a
l'automatisation, et je le signalais comme non observe plutot que de le
taire. Diagnostique ici : le clic atteint bien le bouton — position exacte,
rien qui l'intercepte, `elementFromPoint` rend le bouton lui-meme — mais
l'evenement synthetique du panneau ne declenche pas le gestionnaire React.
Un `click()` programmatique bascule la vue immediatement.

**L'application n'avait rien ; c'est l'instrument qui ne mordait pas.**
Trois passes ont porte une reserve qui n'avait pas lieu d'etre, faute
d'avoir cherche la cause plutot que constate l'effet.

### Le Governance Center, vu sur le chemin reel

Les trois onglets, dans le navigateur :

    Approbations  207 demande(s) — /api/v1/security/approvals
                  `skill_install` en tete, avec la raison d'Aegis
    Regles        20 categorie(s) — niveau « high » (derogation d'execution)
    Audit         6 entree(s) — /api/v1/logs (journal §18), avec le modele
                  choisi par le routeur et les durees

Aucune trace de l'ancien etat vide. Le Security Center corrige ne contient
plus aucune des chaines inventees.

### Ce qui reste non observe

Le rendu des autres Centers : cette passe a verifie le Governance Center
et le Security Center, pas les vingt autres. Rien n'indique un probleme
ailleurs, et rien ne le dement non plus.

### Trouvaille mineure, consignee

Trois fichiers de test portent une sequence d'echappement invalide —
`test_garde_workspace.py` (`\.`), `test_livrables_vides.py` (`\e`),
`test_thinking_stream.py` (`\u`). Revelee par la garde qui analyse tout le
depot. Non corrigee : hors perimetre, inscrite dans les gaps.

### Preuves

Suite backend : 6134 passed, 3 skipped, 273 deselected, 0 failed. `tsc`
propre, 153 tests vitest. Sept gardes neuves. `data/db/hermes.db` intacte,
et les 206 demandes historiques non touchees.

## HOS-287 — Le retrait de `backend/policy/` (2026-09-11)

G-38. La proposition de G-37 est executee. Le module n'existe plus : neuf
fichiers, 1346 lignes, et le `ServiceSpec` qui les construisait.

### Ce qui est parti

    backend/policy/                    9 modules
    tests/architecture/test_policy.py  45 tests, exclusivement HOS-046
    ServiceSpec `policy_engine`        + ses deux fabriques
    ComponentInfo `policy.engine`      du registre de composants
    governanceClient.rules / .evaluate
    usePolicyRules
    /approval/* des orphelins connus   les routes n'existent plus

### Ce qui n'a pas bouge, et c'est le resultat

    routes montees          344 -> 338   exactement -6
    sous-systemes           23  -> 22    exactement le service retire
    /policy/rules, /policy/evaluate, /approval,
    /approval/{id}/approve, /approval/{id}/reject, /audit   -> 404
    /security/approvals     200, 212 demandes — identique
    /security/autonomy      200 — identique
    /logs (journal §18)     200, 6 entrees — identique
    /health                 200
    aucune autre route perdue

Et a l'execution, dans le navigateur : **aucune requete** ne part vers
`/approval`, `/audit` ou `/policy/*`. Le cockpit demarre, la file d'Aegis
s'affiche avec ses 207 demandes en attente, l'etat est nominal.

Ce n'etait pas acquis : un module monte au bootstrap, declarant trois
evenements et servant six routes, peut tres bien avoir un consommateur
qu'aucune lecture ne montre. Le retrait le prouve mieux que l'audit.

### Ce que la suppression a revele

**Deux dependances que mon balayage initial avait manquees**, parce qu'il
excluait `tests/` — je cherchais les chemins runtime et j'ai filtre trop
large :

- une classe `TestApprovalExplainer` de dix tests, **cachee dans un
  fichier de conversation de 99 tests** ;
- `test_policy_routes_are_bound`, dans le test d'assemblage.

Un module ne se retire proprement qu'en cherchant aussi la ou l'on ne
s'attend pas a le trouver. Les deux ont ete trouvees par la suite qui
refusait de collecter, pas par une relecture.

### Le compte des tests se tient exactement

6187 -> 6130 collectes, soit **-57**. Chaque test manquant a son origine :

    45  tests/architecture/test_policy.py (fichier supprime)
    10  TestApprovalExplainer + test_concurrent_approvals
     3  test_no_route_returns_5xx[...] — PARAMETRE sur les routes montees
     1  la garde de contradiction, renommee (remplacee par deux)
    ---
    59  disparus, +2 ajoutes = -57
     1  test_policy_routes_are_bound, deselectionne : 274 -> 273

Les trois cas de fumee sont ceux que je n'avais pas prevus : ils sont
**generes depuis les routes elles-memes**, et retirer trois routes `GET`
en retire trois. Un ecart de tests non explique aurait ete le seul vrai
risque de cette passe — c'est ainsi qu'une suppression emporte
silencieusement une couverture qu'on croyait garder.

### La garde change de forme

`test_la_contradiction_mesuree_est_inscrite` lisait les dix regles pour
tenir au dossier le fait qui justifiait tout : `internet_access_allowed:
allow` contre `network_call` qui exige « high »,
`system_modification_denied: deny` contre `system_config` qui demande un
humain. Ces regles n'existent plus ; ce qu'il faut garder est leur
ABSENCE. Elle devient deux gardes : le repertoire reste supprime et le
`ServiceSpec` ne revient pas, d'une part ; la politique en vigueur tient
encore ce qui a ete mesure, d'autre part — si Aegis changeait d'avis sur
ces deux actions, la justification tomberait et devrait etre re-tranchee
plutot qu'heritee.

Les autres gardes de G-37 sont inchangees et toujours vertes :
`set_policy_engine` sans appelant, Aegis toujours injecte, le cockpit qui
ne lit aucune surface sans producteur et lit les trois autorites reelles.

### Ce qui n'est pas touche

Aegis, `security/approvals.py`, `core/audit_log.py`, le Governance Center,
et les 206 demandes historiques — inchangees, comptees apres coup :
196 `file_read`, 8 `verification_run`, 2 `file_edit`, 1 `skill_install`.

### Preuves

Suite backend : 6127 passed, 3 skipped, 273 deselected, 0 failed. `tsc`
propre, 153 tests vitest. `data/db/hermes.db` intacte.

## HOS-286 — L'audit de `backend/policy/` (2026-09-11)

G-37. **REJECT comme autorite.** Les trois responsabilites du module sont
re-attribuees a leur proprietaire reel, et aucune n'est perdue :

    evaluation de politique -> Aegis (`config/security.yaml` +
                               `AegisEngine`, relu a chaque evaluation)
    file d'approbation      -> Aegis (`security/approvals.py`, SQLite) —
                               deja ferme en G-36
    journal d'audit         -> `core/audit_log.py` (§18, SQLite +
                               fichiers, redaction a l'ecriture)

### Ce qui l'etablit

- `set_policy_engine` n'est **jamais appele**. `set_security_engine`, si —
  `service_registry` y injecte `AegisSecurityAdapter`. Le seul appelant de
  `PolicyEngine.evaluate` est `autonomous_guard`, derriere
  `if self._policy_engine:`, donc mort. Les autres `.evaluate(` du depot
  appartiennent a d'autres moteurs : politiques de reprise runtime,
  `ToolPolicy` des connecteurs, disjoncteurs.
- Les trois evenements que son `ServiceSpec` declare produire —
  `approval.requested`, `approval.granted`, `audit.created` — comptent
  **zero occurrence** sur le bus durable. Le bus ne porte que
  `runtime.started` (20) et `run.turn.emitted` (5).
- Il porte **dix regles en dur**, jamais evaluees, dont deux
  **contredisent** la politique en vigueur : `internet_access_allowed:
  allow` contre `network_call` qui exige « high », et
  `system_modification_denied: deny` contre `system_config` qui demande un
  humain — pas un refus.
- Sa file et son journal sont **en memoire** : zero entree, rien ne
  survit a un redemarrage. Ses dix regles sont des constantes de code
  (`_register_builtins`) : aucune route ne les cree, ne les modifie ni ne
  les supprime, et un redemarrage rend exactement les memes.
- Le journal du §18, lui, porte **six entrees reelles** du 2026-08-14,
  ecrites par les tours de chat — et **aucun lecteur**.

### Le meme defaut, trois fois, sur le meme ecran

Le Governance Center avait trois onglets, et les trois lisaient
`backend/policy/` :

    approbations  file en memoire sans producteur  -> file d'Aegis (SQLite)
    regles        dix regles qu'aucun chemin        -> matrice Aegis, celle
                  n'evalue, et qui contredisent        qu'Aegis relit a
                  la politique en vigueur              chaque evaluation
    audit         anneau en memoire, 0 entree       -> journal du §18

Ce n'etait pas une surface manquante : c'etait un consommateur branche sur
la mauvaise source. Ni le compteur d'orphelins ni le typage ne pouvaient
le voir, puisque les deux surfaces existaient — et l'ecran affichait une
politique de securite **qui ne gouvernait rien**, avec la credibilite que
donne la forme d'une vraie donnee.

### Ce que le cockpit montre desormais

`GET /security/autonomy` rend la matrice entiere a cote du niveau, avec
pour chaque categorie son **effet au niveau courant**. Servie la plutot
que par une route neuve : c'est le meme sujet que `level` et
`always_validated`, et la meme source — la `PermissionMatrix` qu'Aegis
interroge. Une seconde route inviterait a une seconde lecture.

L'effet est calcule par le backend, jamais recalcule a l'ecran : les deux
divergeraient au premier changement de seuil. Une garde le confronte au
**moteur** plutot qu'a lui-meme — pour chaque categorie et chaque niveau,
le verdict d'`AegisEngine` doit s'accorder avec ce que l'ecran annonce.

### Ce qui n'est pas fait, et pourquoi

`backend/policy/` n'est **pas supprime**. Le module n'a plus aucun
consommateur produit, mais sa suppression touche le `ServiceSpec`, le
bootstrap, trois routeurs montes et leurs tests. C'est une passe a part, et
une decision qui n'appartient pas a un audit : le brief demandait de
« proposer sa suppression propre », pas de l'executer.

**Proposition.** Retirer le `ServiceSpec` `policy_engine` et son
`route_binder` ; supprimer `backend/policy/` (8 modules, 1346 lignes) ;
retirer `governanceClient.rules`, `.evaluate` et `usePolicyRules` du
frontend ; retirer `/policy/*` et `/approval/*` des orphelins connus.
Aucun autre module n'importe `backend.policy` — mesure.

### Les gardes, et ce qu'elles tiennent

Pas « ce module ne doit pas exister ». La seule propriete qui compte est
qu'il **ne redevienne pas une autorite**, ni par cablage ni par affichage.
Et chaque garde a sa moitie inverse, sans quoi elle serait satisfaite par
un depot ou plus rien ne garde : `set_policy_engine` doit rester sans
appelant **et** Aegis doit rester injecte ; le cockpit ne doit lire aucune
surface sans producteur **et** doit lire les trois autorites reelles.

### Deux gardes absentes, trouvees par mutation

La garde des trois autorites cherchait le **nom** `useAutonomy`. Un mutant
qui remplace l'appel par un objet fige — en gardant le nom dans un cast de
type — la laissait verte pendant que l'ecran n'interrogeait plus rien.
Elle cherche desormais l'APPEL.

Et la garde qui confronte l'effet affiche au moteur n'itere que sur les
categories reelles : aucune du fichier actuel n'est mutante, non
obligatoire et **sans seuil declare**, si bien que cette branche n'etait
jamais exercee. Une categorie ajoutee demain sans
`min_autonomy_for_auto_allow` se serait affichee « autorisee » la ou le
moteur demande un humain. La garde exerce maintenant une categorie de
sonde pour cette branche precise.

### Preuves

Neuf mutations, neuf rouges — dont « une seconde autorite cablee » et
« plus aucune autorite ». Suite backend : 6184 passed, 3 skipped, 274
deselected, 0 failed. `tsc` propre, 153 tests vitest. Les 206 demandes
historiques d'Aegis ne sont pas touchees. `data/db/hermes.db` intacte.

## HOS-285 — L'approbation raccordee, la pose gouvernee (2026-09-11)

G-36. **ADOPT.** La chaine complete fonctionne sur le chemin reel :
demande -> approbation Aegis -> decision humaine -> autorisation ou refus
-> pose reelle -> provenance et audit -> resultat visible.

### Laquelle des deux files, et pourquoi

G-35 avait trouve deux files d'approbation sans trancher. Mesure du
2026-09-11 :

                          Aegis                    Policy (HOS-046)
    stockage              SQLite                   dict EN MEMOIRE
    producteur reel       AegisAgent, sur le       aucun —
                          chemin de requete        `set_policy_engine`
                                                   n'est jamais appele
    survit au redemarrage oui                      non
    lu par le cockpit     NON                      oui

Elles ne font pas la meme chose et **ne sont pas fusionnees** : la premiere
est un jeton de passage (une fois, quinze minutes, empreinte exacte), la
seconde une demande de workflow (multi-approbateurs, delegation). Mais une
seule est branchee, et c'est elle qui garde les actions reelles.

La preuve de l'ecart tient en une mesure : la file d'Aegis portait **206
demandes `pending` du 2026-08-10 au 2026-09-02** qu'aucun ecran ne pouvait
montrer, pendant que le Dashboard affichait « File d'approbation vide ».
Un mois de decisions en attente, invisibles — non pas parce qu'une surface
manquait, mais parce que le cockpit en lisait une autre.

C'est le cas le plus net de la serie : ni le compteur d'orphelins ni le
typage ne pouvaient le voir, puisque les deux surfaces existaient.

### Le contrat d'Aegis impose l'enchainement

« Approving here does **not** replay the action » : une approbation
autorise LA PROCHAINE TENTATIVE IDENTIQUE, une fois.

    1. demande       -> REQUIRE_HUMAN_VALIDATION, rien n'est pose
    2. l'humain decide dans le cockpit
    3. on redemande  -> l'approbation est consommee, et seulement la
                        quelque chose s'ecrit

Ce n'est pas un detour d'implementation : une file qui rejouerait des
actions stockees aurait besoin d'un repartiteur capable de tout
reexecuter, ce qu'une barriere de securite ne doit pas posseder.

### Les huit preuves, mesurees

Foyer de substitution pour le disque des Skills ; Aegis, sa file SQLite,
le vrai gateway lance par le pont, le scanner de l'agent et le disque sont
reels.

    1. demande                  -> approbation_requise, disque VIDE
    2. visible dans la file d'Aegis (`skill_install`)
    3. refus utilisateur        -> approbation_requise, disque VIDE
    4. accord puis nouvel essai -> posee, `docker` conforme,
                                   sha256:916f3198efaa5a18 des deux cotes
    5. provenance               -> source=skills.sh confiance=community
                                   verdict=safe ; audit : INSTALL docker
    6. cockpit                  -> « Install skill ... · skill_install ·
                                   hermes-os.cockpit » en tete du Dashboard
    7. processus NEUF           -> pose ET decisions retrouvees ;
                                   l'accord est passe a `used`
    8a. conflit (deja posee)    -> sans_effet, disque inchange
    8b. danger, nom libre       -> bloquee_par_le_scanner, disque VIDE,
                                   audit : BLOCKED docker 25_findings

**L'approbation humaine n'est pas un contournement du scanner** : Aegis
autorise la DEMANDE, le scanner de l'agent garde la POSE.

Le 8b l'a d'abord cache. La competence dangereuse s'appelle aussi
`docker`, et sur un foyer ou ce nom etait pris `do_install` sort sur
« deja installee » AVANT d'atteindre le scanner : on mesurait un conflit
en croyant mesurer une securite. Refait sur un foyer neuf, le blocage est
la, avec ses 25 findings.

### Le resultat vient du disque

`skills.manage install` rend `{"installed": true}` dans tous les cas —
`do_install` est annote `-> None` et rend `None` sur chacun de ses
chemins, succes compris. Le verdict rendu est donc tire d'un **diff du
disque** pris de part et d'autre de la demande : une clef neuve dans le
verrou dont le dossier verifie son empreinte, une ligne `BLOCKED` neuve,
ou rien. Il n'est deduit ni de l'identifiant demande, ni d'un nom calcule,
ni d'un booleen.

### Ce que la politique dit, et ou

`skill_install` entre dans `config/security.yaml` avec
`mandatory_validation: true` — jamais auto-autorise, quel que soit
`autonomy_level`. La raison est mesuree et non invoquee : G-35 a montre
que le scanner de l'agent laisse passer un verdict `dangerous` quand la
source est `builtin`, et `actual-setup` est posee avec cinq findings
critiques dont un `env_exfil_curl`. Une seconde barriere, humaine, est
exactement ce que §17.3 appelle.

`path_based: false` : la cible est un identifiant de hub, pas un chemin.
La marquer `path_based` la ferait refuser faute de `target_path`, avant
meme d'atteindre l'humain. Ce qui distingue deux demandes est porte par le
discriminant `identifiant` — sans lui, approuver la pose d'une Skill
autoriserait celle d'une autre (HOS-224).

### Trois contrats perimes, et une garde qui grandissait toute seule

G-26 interdisait toute mutation de Skill, pour une raison exacte —
« install n'ecrit pas de facon verifiable ». G-35 a corrige le diagnostic :
c'est le COMPTE RENDU qui ne vaut rien. Les trois gardes sont rescopees
plus etroitement qu'avant : un seul module a le droit de demander, il doit
passer par Aegis, `MUTATIONS_CONNUES` doit nommer ce que la methode ecrit,
et une route mutante doit deleguer a ce module.

Et une quatrieme a rougi sans defaut :
`test_le_catalogue_ne_pretend_pas_dire_ce_qui_est_installe` decoupait le
fichier **jusqu'a la fin**, si bien que tout composant ajoute plus bas y
entrait. La surface de demande, definie apres, faisait rougir le catalogue
pour un `skillsClient` qui n'etait pas le sien. Une garde bornee par la fin
du fichier grandit toute seule ; celle-ci s'arrete desormais au composant
suivant.

Deux consequences honnetes de la passe, traitees plutot que contournees :
le contrat de mutation de G-23 admet un troisieme MAGASIN (`skills/`, a
cote de `state.db` et `config.yaml`) sans changer de semantique — il est
stocke, il survit au redemarrage, il ne vise aucun tour vivant ; et
`/approval/*` entre dans les orphelins connus, seul ajout que cette liste
ait recu, parce que retirer l'appelant d'une file sans producteur n'est
pas l'abandonner, c'est cesser d'afficher une file qui ne decrit rien.
Supprimer `backend/policy/` serait une decision distincte : il sert aussi
les regles et le journal d'audit, que le cockpit lit vraiment. **G-37**.

### Deux gardes absentes, trouvees par mutation

Les deux portaient sur ce que le brief nomme « un frontend affichant une
decision qui n'est pas celle reellement appliquee ».

Inverser le booleen de `governanceClient.approve` — « Approuver » envoie
un refus — ne rougissait rien. Aucun test d'ecran ne peut l'attraper : il
simule justement le client. La garde porte donc sur le client lui-meme.

Et l'ecran de gouvernance pouvait lister les demandes deja decidees comme
« en attente », ce qui ferait redemander une decision qu'Aegis ne
reprendrait pas — une approbation consommee passe a `used`.

### Preuves

Treize mutations, treize rouges. Suite backend : 6174 passed, 3 skipped,
274 deselected, 0 failed. `tsc` propre, 153 tests vitest dont 4 neufs sur
l'ecran de gouvernance. `data/db/hermes.db` intacte ; l'installation reelle
de l'agent n'est pas touchee — les competences de mesure vivent sous un
`HERMES_HOME` de substitution relie au code reel par une jonction.

## HOS-284 — La temperature du GPU, mesuree (2026-09-10)

Le champ existait depuis HOS-035. `allocation_policy` refusait une
admission au-dessus de `max_gpu_temp_c`, `resource_manager` publiait une
alerte a 85 degC, la barre d'instruments avait un thermometre pret a
s'afficher. **Rien ne remplissait `temperature_celsius`** : seule la
branche `nvidia-smi` le posait, et sur cette machine — AMD RX 6800 —
`nvidia-smi` n'existe pas.

Encore le meme motif : un controle qui ne pouvait pas se declencher, et un
composant d'interface que personne n'avait jamais vu. Ni l'un ni l'autre
n'etait casse ; ils attendaient une mesure qui n'arrivait jamais.

### D'ou vient le chiffre

De `atiadlxx.dll`, l'AMD Display Library posee **par le pilote**. Pas
d'outil tiers, pas de service a lancer, pas de paquet a ajouter : la carte
est lue par la bibliotheque de son propre pilote, en `ctypes`. Mesure du
jour : `rocm-smi`, `amd-smi` et `nvidia-smi` sont tous absents ;
`atiadlxx.dll` est presente et `ADL2_Main_Control_Create` rend `0`.

`ADL2_OverdriveN_Temperature_Get` et `ADL2_Overdrive6_Temperature_Get`
rendent tous deux `-8` (*not supported*) sur RDNA2. PMLog est le seul
chemin, et c'est pour cela qu'il est le seul implemente.

### Les capteurs n'ont pas ete lus dans une entete

`ADL2_New_QueryPMLogData_Get` rend 256 capteurs dont douze sont declares
supportes ici. Prendre un index dans une documentation aurait ete
exactement la supposition que ce depot paie cher — un mauvais index rend
un nombre parfaitement credible. Ils ont ete identifies en **chargeant la
carte** :

    t(s)   [1]clk  [23]W   [8]     [27]
       0      243     26     28      29     repos
       3     2080    135     32      39     charge : horloge et puissance
      12     2026    139     37      44     sautent ; [8] et [27] montent
      15        0      7     30      30     fin : la puissance retombe
      36        0      7     28      29     d'un coup, la temperature non

**L'inertie est le discriminant.** Une puissance passe de 139 W a 7 W en
moins de trois secondes ; une temperature non. Et `[27] >= [8]` a chacun
des vingt-cinq releves — la jonction est plus chaude que le bord, c'est
physique. `[8]` est donc le bord, `[27]` la jonction.

### Deux garde-fous, parce qu'un mauvais index est credible

- la valeur doit tomber dans une plage physiquement plausible : un index
  qui glisserait sur une horloge (2026) ou une puissance (139) echoue ;
- la jonction doit etre au moins aussi chaude que le bord : un index qui
  intervertirait les deux echoue.

`None` veut dire « non mesuree », jamais « froide ». La sonde ne rend
aucun chiffre par defaut — une garde le verifie sur l'arbre syntaxique,
parce que c'est exactement la faute que A-15 a corrigee sur la VRAM.

### La temperature n'est pas l'occupation

Elle est posee **apres** la chaine de sondes VRAM, pas dans l'une d'elles :
une carte dont l'occupation n'est pas lisible a tout de meme une
temperature lisible, et `occupation_mesuree=False` ne dit rien du
thermometre. Une mesure amont — `nvidia-smi` — n'est jamais ecrasee : les
deux chemins doivent dire la meme chose.

### Ce que la barre affiche

`VRAM 4 % · RAM 44 % · 29 degC`, a cote des deux autres contraintes.
L'infobulle porte les deux grandeurs : « GPU 29 degC au bord, 30 degC a la
jonction ». Le thermometre ne disparait plus quand la mesure manque — il
affiche `––`, ce que la barre annonce dans son propre commentaire depuis
le debut, et un cadran absent se lirait « rien a surveiller ».

### Verification de bout en bout

Par HTTP, pendant une inference reelle : **37/44 degC en charge**, retour a
**29/30 degC** ensuite, VRAM a 3,78 Gio. La barre est passee de 27 a
29 degC entre deux relevés — la valeur suit la carte.

Une garde absente, trouvee par mutation : intervertir les deux index ne
rougissait rien. L'echange rompt l'invariant, la sonde rend `None`, et une
garde qui TOLERE `None` ne voit plus rien — le filet du module masquait
l'erreur qu'il devait signaler. La garde ajoutee dit : si le pilote publie
les deux index interroges, la sonde DOIT rendre un couple.

### Preuves

Dix mutations, dix rouges. Suite backend : 6155 passed, 3 skipped, 274
deselected, 0 failed. `tsc` propre, 149 tests vitest. Aucune dependance
ajoutee — une garde d'arbre syntaxique interdit a ce module d'importer
autre chose que la bibliotheque standard.

## HOS-283 — Le cycle de vie des Skills, verifie (2026-09-10)

G-35. **ADOPT sur la verification, DEFER sur le declenchement**, et les
deux verdicts sont mesures plutot que supposes.

### Le dossier existait, et personne ne le lisait

L'agent tient deja le dossier complet du cycle de vie de ses Skills, sur
son disque, sous `<HERMES_HOME>/skills/.hub/` : `audit.log` (une ligne par
INSTALL, BLOCKED, UNINSTALL) et `lock.json` (source, identifiant, niveau de
confiance, verdict du scanner, empreinte, findings avec leur severite).

Aucun module de Hermes OS ne l'ouvrait. C'est le defaut le plus frequent de
ce depot sous sa forme la plus pure : la donnee de gouvernance est
produite, complete, datee — et sans lecteur.

### Le chemin reel, mesure de bout en bout

Hub reel (5493 entrees), scanner reel, quarantaine reelle, sur un
`HERMES_HOME` de substitution. Cinq issues, cinq empreintes disque
differentes, **une seule reponse RPC** :

    official/devops/actual-setup      posee   INSTALL ... dangerous
    skills-sh/mindrally/.../docker    posee   INSTALL ... safe
    skills-sh/bobmatnyc/.../docker    RIEN    BLOCKED ... dangerous 25_findings
    docker, skill-docker, openclaw-*  RIEN    aucune ligne
    la meme, deja posee, sans --force RIEN    aucune ligne

`skills.manage install` rend `{"installed": true}` dans les cinq cas.

Deux verdicts `dangerous`, deux issues opposees : la premiere est passee
parce que sa source est `builtin`, la seconde a ete bloquee parce qu'elle
est `community`. Et `actual-setup` est posee avec **cinq findings
critiques**, dont un `env_exfil_curl`. La politique de l'agent l'autorise ;
rien ne le montrait. L'ecran montre desormais le verdict ET la confiance
cote a cote — separement, ils ne veulent rien dire.

### La verification tient a l'octet

`content_hash` est une SHA-256 canonique sur (chemin POSIX, octets),
ordonnee par la **chaine** du chemin — l'agent porte le commentaire de
l'incident que l'ordre lui a coute : trier des `Path` est insensible a la
casse sous Windows, et chaque competence installee se declarait perimee
pour toujours.

Recalculee dans `backend/skills/gouvernance.py`, elle rend **exactement**
celle du verrou sur les deux competences posees. Un octet ajoute apres
coup fait basculer l'etat en `alteree` — verifie sur le disque, puis dans
le navigateur, le badge de l'onglet passant a 1.

Reimplementee plutot qu'importee : `plugin_compat` desactive au 2026-09-14
tout code externe qui importe les internes de l'agent. Une empreinte de
gouvernance ne doit pas mourir avec une date.

### Trois ecarts, trois noms, aucun deduit d'un autre

    conforme            l'empreinte recalculee egale celle enregistree
    alteree             le dossier a change depuis le scan
    annoncee_absente    le verrou l'annonce, le dossier n'est pas la

Et ce que la vue ne peut PAS voir est affiche plutot que tu : un refus
silencieux n'ecrit ni fichier ni ligne d'audit, donc aucun lecteur *a
posteriori* ne peut le distinguer d'une operation jamais demandee. Sans
cette phrase, le journal se lirait comme exhaustif et une passe suivante
« reparerait » l'absence en inventant une ligne.

### Pourquoi le declenchement reste DEFER

`do_install` est annote `-> None` et rend `None` sur **tous** ses chemins,
succes compris : il n'y a aucune valeur de retour a corriger en amont.
G-26 avait donc raison de refuser le bouton. La verification leve cette
objection — Hermes OS peut desormais dire ce qui a reellement ete ecrit.

Ce qui la remplace est plus dur, et c'est une **decouverte de cette
passe** : il y a **deux files d'approbation**, et le cockpit regarde la
mauvaise. La file vivante, celle qu'Aegis remplit (`record_pending`,
servie par `/security/approvals`), n'a **aucun appelant frontend** — elle
figure dans les orphelins connus depuis le 2026-09-07. Celle que le
Dashboard affiche est `/approval`, servie par `backend/policy/`, alimentee
seulement par `autonomous_guard`.

Router une installation de Skill vers la file vivante la rendrait
invisible ; la router vers l'autre ne garderait rien. C'est exactement le
motif que G-26 avait nomme pour le `pending` de l'agent — « le producteur
existe, l'approbateur est injoignable » — un etage plus haut, et cette fois
chez nous. **G-36** ouvert.

### Deux gardes qui se sont mordues

**Une garde absente, trouvee par mutation.** Remplacer `source` par
`source or "official"` ne rougissait rien : aucune garde n'exercait une
entree de verrou incomplete. Une competence de provenance inconnue se
serait affichee `official` — une provenance FABRIQUEE, exactement ce que
G-27 a passe une passe entiere a refuser sur l'inventaire.

**Un commentaire qui declenche la garde qu'il explique.**
`test_tout_ce_qui_vit_sous_la_racine_est_preserve` cherche dans tout
`backend/` un appel a l'accesseur de racine suivi d'un litteral de
dossier. Mon helper s'appelait `_racine()` : la garde a exige que `.hub`
entre dans `preserve_set()` — or `.hub` vit chez l'agent, sous
`%LOCALAPPDATA%\hermes`, et la mise a jour de Hermes OS ne le voit meme
pas. L'y inscrire aurait ete une fausse promesse. Renomme `_competences()`
— un meilleur nom de toute facon. Puis le commentaire qui *expliquait* le
motif l'a redeclenche, parce que la garde lit le texte source. Une garde
ecrite sur une forme se fait piquer par la prose qui la decrit.

### Preuves

Dix-huit mutations, dix-huit rouges : tout declare conforme, un dossier
absent qui passe pour pose, l'empreinte qui ignore le contenu ou l'ordre
canonique, la confiance deduite du verdict, la source manquante devenue
officielle, le journal qui perd les blocages, les findings recopies, le
lecteur qui cree le dossier du hub, une route qui declenche une
installation, l'ecran qui affirme `conforme` quoi qu'il arrive. Base et
restauration a zero.

Suite backend : 6137 passed, 3 skipped, 274 deselected, 0 failed.
Frontend : `tsc` propre, 149 tests verts dont 8 neufs sur cet onglet.
`data/db/hermes.db` intacte ; l'installation reelle de l'agent n'a pas ete
touchee — les competences de mesure sont posees sous un `HERMES_HOME` de
substitution. Les deux depots propres.

## HOS-282 — La relation Run ↔ Skill, montree (2026-09-10)

G-34. **ADOPT.** L'onglet **Runs ↔ Skills** du Skills Center sert
`GET /skills/observations` et montre quel Run a mute quelle Skill. C'est la
premiere surface produit de la relation construite de G-29 a G-33, et elle
ne calcule rien : elle met cote a cote trois lectures dont aucune ne lui
appartient.

### Trois proprietaires, et l'ecran n'en est aucun

La mutation vient de l'observateur installe chez l'agent, la relation
`turnId -> run` du bus durable de Hermes OS, et ce qu'*est* le Run du Run
Ledger. Rien n'est recopie d'un magasin dans l'autre : c'est la meme
posture qu'en HOS-274 (les competences), HOS-275 (leur provenance) et
HOS-281 (les mutations). Aucun registre neuf, aucune seconde verite.

### Mesure sur la chaine reelle

Bus durable reel, Run Ledger reel, quatre Runs reellement ouverts, chemin
ACP reel, observateur reellement installe. Un processus **neuf** relit
tout — c'est la preuve de redemarrage :

    RUN 0654af85...  perdu   g34-alpha (created), g34-partagee (created)
    RUN 8d1a5993...  perdu   g34-partagee (edited)
    RUN 1c9276d1...  perdu   g34-concurrent-c    | deux tours reellement
    RUN e3e9d384...  perdu   g34-concurrent-d    | concurrents, sans melange
    run-hors-ledger-g34      g34-hors-ledger  -> « absent du Run Ledger »
    sans Run                 g34-hors-run     -> « aucune etiquette »
                             g34-etrangere    -> « etiquette non resolue »

`g34-partagee` porte la moitie du contrat qu'aucune passe precedente
n'avait exercee : **un meme Skill mute par deux Runs differents**. La vue
« Par Skill » l'affiche `2 mutation(s) · 2 Run(s)`, verifie dans le
navigateur.

Les quatre Runs s'affichent `perdu`. Ce n'est pas un defaut : la
reconciliation du Ledger les a marques ainsi parce que le processus qui les
avait ouverts n'existait plus. Le Ledger parle, la donnee n'est pas figee.

Ce qui est substitue, et cela seul : le disque des Skills de l'agent. Y
poser sept competences de demonstration serait l'ecriture non justifiee
sous `%LOCALAPPDATA%\hermes` que le brief interdit. Le bus et le Ledger,
qui appartiennent a Hermes OS, sont les vrais.

### Quatre absences, quatre libelles distincts

Le coeur de la passe. Un ecran qui range ce qu'il ne sait pas au meme
endroit que ce qu'il sait detruit a l'affichage cinq passes de mesure :

| ce qui manque | ce que l'ecran dit |
|---|---|
| le tour n'avait pas de `turnId` | « aucune etiquette » |
| l'etiquette n'est pas de Hermes OS, ou est elaguee | « etiquette non resolue » |
| le Run n'est pas dans le Ledger | « absent du Run Ledger » |
| le Ledger n'a pas pu etre lu | « registre indisponible » |

Les deux dernieres se confondraient sans le drapeau `registre_lisible` :
une panne de base ferait dire « Run inconnu » de Runs parfaitement
enregistres — une affirmation fausse nee d'une panne.

Les mutations non rattachees sont **ecartees** du groupement, jamais
rangees sous une clef « inconnu » qui se lirait comme un vrai Run. La vue
est une **partition**, pas une liste filtree : `runs` et `non_rattachees`
couvrent exactement les observations lues, et aucune des deux ne peut etre
obtenue en taisant l'autre.

### Un contrat perime, et deux gardes qui le laissaient passer

L'onglet Agent affirmait « Aucune competence n'est rattachee a un Run ».
G-33 l'a rendu faux **sans que rien ne rougisse**, parce que c'etait une
affirmation d'ecran et non une lecture de donnee.

`CORRELATION_IMPOSSIBLE` reste exacte, et sa portee est celle qu'elle a
toujours eue : les **enregistrements de l'agent** ne portent ni `task_id`
ni `session_id`, 0 sur 75. Ce qui a change est qu'une relation vit
desormais ailleurs. La phrase de l'ecran est donc bornee a l'inventaire —
aucun fichier de competence installee ne nomme un Run — et renvoie a
l'onglet ou la relation existe.

Deux gardes de G-27 ont ete rescopees pour la meme raison : leur **nom**
decrivait le depot entier la ou leur mesure ne portait que sur
l'inventaire. Un nom de garde qui deborde sa mesure est une affirmation
gratuite qui vieillit sans prevenir.

### Une garde absente, et un instrument faux

**La garde.** `test_un_ledger_illisible_ne_se_lit_pas_comme_un_run_inconnu`
passait le couple `(False, {})` en dur : elle mesurait ce que la vue fait
du drapeau, jamais la fonction qui le pose. Remplacer `return False, {}`
par `return True, {}` dans `_detail_des_runs` laissait tout vert. Trouve
par mutation, jamais par relecture.

**L'instrument.** Trois mutations frontend sont revenues vertes. Verifie
plutot que cru : le motif `Tests\s+(\d+) failed` ne franchit pas les codes
ANSI que vitest intercale, et rendait 0 pour une suite rouge. La mutation
10, rejouee a la main, faisait bien echouer sa garde. C'est la lecon de
`CLAUDE.md` appliquee a un instrument qu'on ecrit soi-meme : un resultat
invraisemblable se verifie avant de se conclure.

### Preuves

Quatorze mutations, quatorze rouges — melange de deux Runs, rattachement au
mauvais Skill, relation inventee quand `turnId` manque, ecran qui aplatit
les groupes, ecran qui donne un Run aux orphelines, ecran qui cesse
d'appeler la route, route declaree derriere `/{skill_id}`. Base et
restauration a zero.

Suite backend : 6115 passed, 3 skipped, 274 deselected, 0 failed.
Frontend : `tsc` propre, 141 tests verts dont 9 neufs sur cet ecran.
`data/db/hermes.db` intacte. Les deux depots propres.

## HOS-281 — L'observateur installe, et la boucle fermee (2026-09-10)

G-33. **ADOPT.** Le plugin tourne pour de vrai, sous
`%LOCALAPPDATA%\hermes\plugins\hermes-os-observateur-skills`, active par
`plugins.enabled`, et `scan_plugin` rend « aucun import interne » — sa
condition de survie au retrait du 2026-09-14, dans quatre jours.

### La chaine, avec l'observateur reellement installe

    phase 1 (Hermes OS)  RUN-ALPHA -> ffb603fc...   RUN-BETA -> 9039b9d6...
    phase 2 (agent)      g33-une   turn=ffb603fc...
                         g33-deux  turn=ffb603fc...
                         g33-trois turn=9039b9d6...
    phase 3 (NOUVEAU     RUN-ALPHA  ['g33-deux', 'g33-une']
             processus)  RUN-BETA   ['g33-trois']

Plusieurs Skills dans un Run, plusieurs Runs, redemarrage : lus par un
processus neuf, groupes correctement.

### Ce que l'agent fait quand le plugin ne marche pas

Les trois defaillances, avec les Skills verifiees **sur le disque** :

    plugin absent      non charge   0 fait   Skills ecrites
    plugin desactive   charge, off  0 fait   Skills ecrites
    callback qui leve  charge, on   0 fait   Skills ecrites

Et deux tours concurrents gardent chacun leur etiquette. L'observateur ne
peut pas bloquer l'agent — G-28 l'avait etabli par construction, G-33 le
mesure avec le plugin en place.

### L'installation, par les mecanismes de l'agent

Le repertoire est copie, et l'activation passe par `_set_plugin_enabled`,
l'ecrivain de config de l'agent lui-meme. Editer `config.yaml` a la main
aurait marche aussi, et aurait ete une seconde facon de faire la meme chose.
Diff structurel apres coup : **aucune clef perdue**, une ajoutee
(`plugins.disabled`, la liste de refus vide), et `plugins.enabled` a gagne
exactement l'observateur.

### Le patch, adopte

`turn-id.patch` est desormais un **commit** du depot de l'agent
(`fb6335dd14`, sur `693641aa8b`), et non plus un arbre de travail sale. Le
repertoire `integrations/hermes-agent/observateur-skills/` reste la source
du plugin : l'installation en est une copie, et un test compare les octets
pour qu'il n'existe jamais deux versions du meme observateur.

### Trois lectures, un seul proprietaire

`backend/skills/observations.py` est la **troisieme** fois que Hermes OS lit
le disque de l'agent — apres les competences (HOS-274) et leur provenance
(HOS-275) — et la posture ne change pas : lire, jamais ecrire, jamais
copier. Le fait appartient au plugin, la relation `T -> R` au bus de Hermes
OS, et aucun des deux ne migre dans l'autre.

Les observations non rattachees sont **ecartees** du groupement plutot que
rangees sous une clef « inconnu » : une telle clef se lirait comme un Run et
finirait affichee a cote des vrais.

### Quatre contrats perimes, reecrits

G-28, G-29 et G-30 gardaient « l'observateur n'est pas installe », « le
backend ne le nomme pas », « le README dit qu'il est inerte ». G-33 leve les
trois. Ils n'etaient ni faux ni casses : perimes. Ce qui les remplace est
plus etroit et plus utile — un seul module a le droit de nommer le plugin
(celui qui le LIT), le backend n'ecrit jamais dans le dossier des plugins de
l'agent, et l'installation ne doit pas diverger du depot.

La garde « le backend ne s'installe pas lui-meme » n'est pas une precaution
de style : un backend qui reparerait le plugin au demarrage en deviendrait
le mainteneur, et reinstallerait un plugin qu'un operateur avait peut-etre
retire expres.

### Une garde absente, trouvee par mutation

Vider le `turn_id` **rendu** par le lecteur ne rougissait rien : le
rattachement se fait sur le fait brut, si bien qu'un ecran affichant « quel
tour a produit ceci » aurait montre du vide pendant que le Run, lui, restait
juste. Le champ rendu est desormais verifie.

### Preuves

Dix mutations, dix rouges. Depot Hermes OS propre, depot de l'agent propre —
un seul commit, aucun debris de travail. `data/db/hermes.db` intacte ; les
mesures sont passees par des `HERMES_HOME` de substitution, sauf
l'installation elle-meme, qui est le sujet de la passe.
### Un releve que son propre script n'ecrivait pas

Trouve parce que le patch de l'agent a change son empreinte
(`0.21.0+693641aa8b43` -> `+fb6335dd142b`) et reveille la garde de G-19.
Son message dit « relancez `scripts/registre_gateway.py` » — et le relancer
ne reparait rien : `chemin_releve()` visait `etat.racine()/db/`, l'etat
d'execution, alors que le test, cette entree et la roadmap nomment tous
`config/gateway_registre.json`. Le script etait le seul dissident.

Le relevé est une **mesure datee**, pas de l'etat : sa place est dans le
depot, a cote du test qui la compare au runtime installe. Cible corrigee ;
le dump ecrit dans l'etat d'execution, que personne ne lisait, retire. Le
jeu des 206 methodes est identique — le patch turnId n'ajoute aucune RPC,
ce qui est exactement ce que G-31 promettait.

Le defaut ne pouvait pas se voir avant : tant qu'aucune empreinte ne
changeait, la garde restait verte au-dessus d'un script qui ecrivait a cote.

## HOS-280 — La correlation Run ↔ Skill, etablie (2026-09-10)

G-32. **ADOPT.** La relation que G-29 avait mesuree impossible existe, de
bout en bout, sur deux processus et par-dela un redemarrage.

    phase 1 (Hermes OS)  Run lie          : RUN-Z
                         requete ACP      : _meta.hermes.turnId = 2a374b49...
                         relation ecrite  : RUN-Z
    phase 2 (agent)      Skill g32-une   -> client_turn_id = 2a374b49...
                         Skill g32-deux  -> client_turn_id = 2a374b49...
    phase 3 (NOUVEAU     etiquette lue -> Run retrouve : RUN-Z
             processus)  etiquette etrangere          : (aucun)

Aucune identite ne change de proprietaire : Hermes OS garde `run_id`,
l'agent garde `task_id` et `session_id`, et l'etiquette est une **troisieme**
identite, opaque, que Hermes OS frappe et reconnait.

### Ce que la mesure a corrige dans ma lecture

Le chemin traverse `_run_coro`, qui pousse la coroutine vers une boucle d'un
**autre thread** par `run_coroutine_threadsafe`. J'ai conclu — a voix haute —
qu'un `ContextVar` n'y survivrait pas et que le design par contexte etait
mort. Mesure : il survit. `call_soon_threadsafe` copie le contexte de
l'appelant. La lecture du code disait le contraire, et c'est la mesure qui a
tranche.

### D'ou vient le Run, et pourquoi ce n'est pas une devinette

`execute_task` resout `self._runs.get(sm._meta.execution_id)` — la table que
`_ouvrir_le_run` a posee a l'ouverture. Une **correspondance enregistree**,
pas le dernier Run ni le plus recent : G-29 avait REJETE ces trois
raccourcis, et des tests les interdisent maintenant.

Detail qui boucle : `run_de()`, l'accesseur que G-29 avait trouve **sans
aucun appelant**, decrivait deja exactement cette table. La donnee etait la ;
il manquait le chemin.

### Ou vit la relation

Sur le **bus durable**, parce que `backend/runs/registre.py` a deja tranche :
« le registre porte les runs ; le bus porte les evenements ; `run_id` les
relie ». Une table `turns` serait le second magasin d'evenements que ce meme
commentaire refuse. Topic `run.turn.emitted`, ajoute a l'enum ferme comme sa
docstring l'exige — « new topics must be added here rather than using raw
strings ».

**Retention de sept jours** (`EventBusImpl(retention_days=7)`) : la relation
est interrogeable une semaine, puis elaguee. C'est la politique du bus, et la
changer serait une decision de bus, pas une raison de batir un magasin
parallele.

### La regle qui tient tout le reste

Une etiquette n'est posee que si sa relation a ete **ecrite**. Sans Run lie —
le chat, une tache hors mission — ou sans bus, `etiquette_du_tour()` rend
`""`, et la requete ACP ne porte **aucune clef `_meta`** : elle est octet
pour octet celle d'avant. Une etiquette sans relation promettrait une
correlation que personne ne pourrait resoudre — la moitie d'un contrat, que
G-31 refusait deja de livrer.

### Deux contrats perimes, reecrits

G-30 et G-31 gardaient « Hermes OS ne pose pas `_meta` » et « aucun module ne
frappe d'etiquette ». G-32 leve les deux, par instruction explicite et sur
une chaine demontree. Ils n'etaient ni faux ni casses : **perimes**. Ils
disent desormais la condition — `_meta` seulement pour un Run lie, et une
seule source de frappe.

### Deux gardes que des mutations ont trouvees absentes

**La reprise refrappait une etiquette.** Un processus d'agent qui meurt en
plein tour est repris : session rouverte, message renvoye. C'est le meme tour
logique, et lui donner une seconde etiquette ferait paraitre deux tours la ou
un Run n'en a demande qu'un. Rien ne le gardait.

**La liaison du Run pouvait fuir.** Sans `finally`, une tache qui leve
laisserait son Run lie, et la suivante — d'un autre Run, ou d'aucun — en
heriterait. La contamination aurait ete silencieuse et l'etiquette aurait
pointe le mauvais Run.

Les deux mutations restaient vertes tant que les tests perimes masquaient
l'absence : elles ne rougissaient que par eux. Les reecrire a decouvert les
trous.

### L'observateur de G-28 a maintenant un lecteur

Le prealable pose en G-28 — « rien ne lit la relation » — est leve :
`correlation.run_du_tour()` la lit. L'observateur reste **non installe** dans
cette passe, comme le brief l'exigeait, mais la raison de l'attendre a
disparu. Son installation est le jalon suivant, avec l'adoption amont de
`turn-id.patch`, toujours local.

### Vingt rouges que j'ai failli ne pas voir

La suite de cette passe a rendu **20 echecs**, et je ne les ai pas lus : la
commande etait `pytest -q | tail -4`, qui n'ecrit que quatre lignes dans le
fichier de sortie. Le « exit 0 » que j'y voyais etait celui de `tail`, pas de
pytest. J'etais a un pas de commiter une suite rouge en la croyant verte.

Les vingt venaient tous de ce changement, en deux familles.

**Trois doubles de test** dont le `tour()` n'acceptait pas le `turn_id`
ajoute au contrat du client — dix-neuf tests les partagent. Le vrai client le
declare avec un defaut, donc rien de reel ne cassait.

**Un test qui epingle l'enum des topics a une specification** : « exactly the
28 topics defined by HOS-001 + D-20 ». Ce n'est pas une liste qui pousse
toute seule — ce test existe pour qu'ajouter un topic soit un acte delibere
et enregistre. J'avais lu la docstring de l'enum (« new topics must be added
here rather than using raw strings ») comme une invitation a ajouter ; elle
dit seulement de ne pas employer de chaine libre. `run.turn.emitted` est
donc inscrit dans la specification, avec sa raison, et le compte passe a 29.

### Preuves

Suite complete 6092 passed, 3 skipped, 274 deselected ; tsc et vitest
verts.

Onze mutations, onze rouges : injection disparue, `_meta` pose sans
etiquette, etiquette rendue sans relation, etiquette derivee du `run_id`,
`session_id` employe comme etiquette, etiquette etrangere associee au dernier
Run, Run devine, table creee, topic hors de l'enum, reprise qui refrappe, et
liaison qui fuit.

`data/db/hermes.db` intacte — le Run Ledger vit dans
`%LOCALAPPDATA%\\HermesOS\\db\\hermes_os.db`, et le bus dans son propre
fichier.

## HOS-279 — Le contrat turnId, implemente chez l'agent (2026-09-10)

G-31. G-30 avait classe la restitution **ADAPT** : trois lignes a trois
coutures existantes, que Hermes OS ne pouvait pas ecrire. Cette passe les a
ecrites chez l'agent et a mesure la chaine complete. **ADOPT.**

### La chaine, mesuree

Reelle a chaque maillon sauf un — le corps du tour, ou le modele deciderait
d'appeler `skill_manage`, remplace par une mutation deterministe. C'est la
*decision* du modele qu'on substitue, pas le mecanisme :

    _meta -> MessageRouter reel -> HermesACPAgent.prompt() reel
          -> _run_agent_turn reel (copy_context + ExitStack)
          -> skill_manage reel -> _emit_skill_lifecycle reel -> plugin reel

    g31-a              turn='A'
    g31-b              turn='B'
    g31-c1             turn='C'   ┐ deux Skills,
    g31-c2             turn='C'   ┘ un seul tour
    g31-sans           turn=None
    g31-meta-vide      turn=None    `_meta` sans `hermes`
    g31-hermes-vide    turn=None    `hermes` sans `turnId`
    g31-hors-tour      turn=None    hors de tout tour
    g31-x              turn='X'   ┐ deux tours
    g31-y              turn='Y'   ┘ concurrents

La clef est **absente**, pas vide, quand aucun `turnId` n'est fourni : une
chaine vide se lirait « correle a rien » et inviterait un consommateur a la
remplir. Apres redemarrage, un tour sans `turnId` n'herite d'aucune identite
precedente, alors que `A B C X Y` etaient sur le disque. Et `.usage.json` ne
porte aucun champ de tour — **rien n'est persiste pour la correlation**.

### Une couture que G-30 avait mal nommee

G-30 designait `agent/turn_context.py`. La mesure a corrige :
`acp_adapter/server.py:_run_agent_turn` est le *« Executor-thread body of one
turn, run inside `contextvars.copy_context()` so ContextVar writes are
isolated from concurrent sessions »*. L'isolation entre tours concurrents y
est deja **architecturale** — ce n'est pas une propriete que le patch
ajoute, c'est une propriete dont il herite — et la fonction porte un
`ExitStack` ou les autres contextes de tour sont lies. Lier ailleurs aurait
ete lier sur le thread de la boucle, hors du contexte copie.

### La provenance, et sa limite

`integrations/hermes-agent/contrat-correlation/turn-id.patch` est le
`git diff` exact contre le checkout de l'agent a **`693641aa8b`** (v0.21.0) :
83 lignes, trois fichiers, zero changement de protocole, aucune methode
nouvelle.

**Le patch vit dans un checkout local.** `hermes update` fait un `git pull`
avec autostash : le patch est mis de cote puis reapplique, au mieux, et un
changement amont conflictuel l'echouerait en laissant un autostash
orphelin. Ce n'est pas une base durable — c'est pourquoi il est versionne
ici, et pourquoi la seule fin correcte est son adoption amont.

### La suite de l'agent, mesuree des deux cotes

Avant et apres, par `git stash` sur la meme commande : **6 echecs, 232
passes, 3 ignores**, jeu d'echecs identique. Les six sont des limitations
Windows preexistantes — symlinks, `fcntl`, `PosixPath`. La suite large de
l'agent n'est pas executable sous Windows, et ce n'est pas cette passe qui
l'a rendue telle.

### Un defaut trouve dans l'observateur de G-28

La sonde de mesure a perdu **un fait sur deux** quand deux tours concurrents
ont emis en meme temps. Cause : `state.get(...)` puis `state.set(...)` —
chaque appel est atomique chez l'agent, la **paire** ne l'est pas, et les
deux threads avaient lu la meme liste avant que l'un ecrive.

L'observateur de G-28 avait exactement la meme forme. Corrige : une clef par
fait, avec horodatage, PID et rang, et une facade `mutations()` qui les rend
ordonnes — la forme des clefs est un detail du plugin, et l'exposer
obligerait tout lecteur a la connaitre. Le plafond `FAITS_MAX` disparait
avec la liste : c'est au consommateur de drainer, un observateur ne decide
pas ce qui merite d'etre oublie.

Un observateur qui perd silencieusement la moitie de ce qu'il observe est
pire qu'absent : il donne une trace qu'on croit complete.

### Cinq gardes trouvees par des mutations

Trois mutations sont restees **vertes** au premier passage, et une
quatriemme a rougi pour la mauvaise raison :

- la garde sur les identites ne regardait que deux formes de ligne : la
  substitution glissee dans le `return` de `_client_turn_id` passait ;
- la garde sur l'emplacement de la liaison verifiait une **presence**, pas
  un emplacement ;
- la garde sur la localite du patch cherchait « checkout local » dans le
  document entier, ou la phrase figure deux fois — **cinquieme** fois de
  cette serie qu'une chaine presente deux fois satisfait une garde ;
- et le mutant « la liaison quitte le corps du tour » ecrivait
  `if client_turn_id and False`, ce qui **supprime** la liaison au lieu de
  la deplacer : il ne creait pas le defaut qu'il nommait.

La garde finale porte sur la **pile du tour** : toute liaison doit etre
enregistree par `_bind_guarded(stack, ...)`, et cette pile n'existe que dans
`_run_agent_turn`. Elle ne regarde pas l'en-tete du hunk — git y met le nom
de la **classe**, pas de la methode, et les deux hunks affichent
`class HermesACPAgent`.

L'extraction de la fonction depuis le patch a demande trois bornes
successives, chacune fausse pour une raison differente : une ligne de
contexte absente des ajouts, un `def` en colonne 0 qui n'existe pas parce
que le hunk suivant modifie une **methode**, et une indentation qui ne
s'arrete pas parce qu'un hunk voisin commence aussi par des lignes
indentees. La borne juste est le **hunk** — la frontiere que le diff porte
lui-meme.

### Ce que Hermes OS ne fait toujours pas

Il n'envoie pas de `_meta`, et la raison a change. G-30 disait : l'agent ne
restitue pas. Ce n'est plus vrai sur un agent patche. Deux raisons
subsistent : le patch est **local**, donc un client ne pourrait pas
distinguer « pas de mutation » de « pas de restitution » ; et **rien ne lit
la relation** — le prealable de G-28, toujours non leve.

### Preuves

Douze mutations, douze rouges. Suite complete 6073 passed, 3 skipped,
274 deselected ; tsc et vitest verts. `data/db/hermes.db` intacte ; le depot de
l'agent ne porte que les trois fichiers du patch, sans debris.

## HOS-278 — L'etiquette de tour existe deja, a moitie (2026-09-10)

G-30. G-29 concluait qu'il faudrait un identifiant de tour fourni par le
client. Cette passe est allee voir si le runtime peut le porter. **Le
transport existe, nativement, et il est mesure.**

    le transport, cote ACP           ADOPT    natif, mesure
    la restitution dans l'evenement  ADAPT    trois points amont
    le contrat complet, aujourd'hui  bloque   non livrable ici
    la meme chose cote Gateway       REJECT   canal privilegie
    un registre propre a Hermes OS   REJECT   seconde verite

### `_meta` arrive deja au handler de l'agent

`PromptRequest` d'ACP v0.11.2 (`PROTOCOL_VERSION = 1`) porte `_meta`,
*« reserved by ACP to allow clients and agents to attach additional metadata
to their interactions »*. Et le routeur le **deplie en arguments nommes** :

    params = {k: getattr(model_obj, k) for k in model.model_fields if k != "field_meta"}
    if meta := getattr(model_obj, "field_meta", None):
        params.update(meta)
    return await func(**params)

Mesure sur le runtime installe, en envoyant
`_meta: {"hermes": {"turnId": "run-42#tour-3"}}` :

    kwargs recus : {"message_id": null, "hermes": {"turnId": "run-42#tour-3"}}

La signature de l'agent est `prompt(self, prompt, session_id, **kwargs)` :
la metadonnee **arrive**, et l'agent l'ignore. L'espace de noms n'est pas
invente non plus — `acp_adapter/provenance.py` decrit deja une *« additive
Hermes extension under ACP `_meta.hermes` »*, dans le sens sortant. La
proposition emprunte le meme chemin en sens inverse.

### Ce qui manque, et ou exactement

Trois coutures, toutes existantes :

1. `acp_adapter/server.py:prompt()` — lire `kwargs["hermes"]["turnId"]` ;
2. `agent/turn_context.py` — le lier au tour, a cote de
   `set_current_write_origin`, deja lie la par le meme mecanisme ;
3. `tools/skill_usage.py:_emit_skill_lifecycle` — le restituer, absent
   quand il est absent.

Zero changement de protocole, aucune methode nouvelle. Hermes OS ne peut
pas ecrire ces trois lignes : **ADAPT ne veut donc pas dire
« constructible maintenant »**. La specification est ecrite, la demande est
formulee, le contrat reste bloque amont.

### La propriete qui le distingue de tout ce que G-29 a ecarte

Le `turnId` voyage **dans l'evenement**, pas dans une table partagee. Rien a
garder entre l'emission et la lecture, rien a perdre au redemarrage.
`SessionsDeMission._identifiants` etait volatile, le Ledger n'a pas de
colonne de session, `audit_log` a six lignes : un contrat qui dependrait
d'un etat partage heriterait des trois.

### Les options ecartees

`messageId` est marque **UNSTABLE** — *« may be removed or changed at any
point »* — et l'agent l'echoerait dans la `PromptResponse`, pas dans les
evenements Skill.

`_hosted_task` du Gateway est le precedent le plus proche : `prompt.submit`
accepte **deja** une enveloppe cliente portant `turn_id`, `task_id`,
`room_id`. Mais `_hosted_submit_error` exige `session["source"] ==
"bot_room"` **et** un `_hosted_terminal_callback` **appelable** — un objet
Python qui ne traverse pas JSON-RPC. Canal interne au processus, pas ouvert
a un client.

### Une mesure qui corrige G-29 au passage

Sur le chemin ACP, le `task_id` de l'agent **est** son `session_id` :
`run_conversation(..., task_id=session_id)`. G-29 disait que `task_id`
n'etait pas un `run_id` ; G-30 ajoute qu'il n'est meme pas un identifiant de
tour. Un evenement Skill de chat ou de mission porte donc aujourd'hui deux
fois la meme valeur.

### Et une phrase de HOS-277 corrigee

HOS-277 ecrivait « aucune methode du runtime ne le permettrait ». C'etait
trop fort : le protocole accepte la metadonnee, et elle arrive. Ce qui
manque est la restitution. La roadmap porte la correction.

### Quatre gardes satisfaites par un doublon

Quatre fois dans cette passe, une garde a ete verte alors que le defaut
etait present, parce que la chaine cherchee figurait deux fois pour deux
raisons :

- `correlation_id` accusait `events/system_event_bus.py`, un champ anterieur
  ou Hermes OS groupe SES propres evenements ;
- « ne le touche pas » servait aussi au cas « session reprise » du tableau,
  si bien que vider la section 7 ne rougissait pas ;
- `{"hermes": {"turnId": ...}}` figurait dans la ligne d'ENTREE de la
  mesure, si bien que supprimer le RESULTAT ne rougissait pas ;
- et deux mutants ecrits pour la section 7 ne creaient pas le defaut qu'ils
  nommaient.

Chaque fois, c'est la mutation qui a vu, jamais la relecture. Les gardes
portent desormais sur des sections et sur des reperes uniques.

### Ce qui est livre

`integrations/hermes-agent/contrat-correlation/README.md` — la decision, la
mesure, les trois coutures, les cinq identites et leurs proprietaires, les
neuf cas de falsification, et la demande a formuler amont. **Un seul
fichier, et un test verifie qu'il n'y en a pas d'autre** : un module Python
dans ce dossier deviendrait, a la premiere relecture distraite, une
implementation.

Hermes OS n'envoie toujours pas de `_meta`. Poser le champ pendant que
l'agent le jette livrerait la moitie d'un contrat, et la moitie suivante
serait tentee de deviner le reste. Un test garde l'abstention.

### Preuves

Suite complete 6063 passed, 3 skipped, 274 deselected ; tsc et vitest
verts.

Douze mutations, douze rouges. `data/db/hermes.db` intacte ; aucune ecriture
dans les magasins de Hermes Agent ; le plugin observateur de G-28 reste non
installe.

## HOS-277 — La correlation Run ↔ Skill : ou elle se perd (2026-09-10)

G-29. G-28 avait pose un prealable a l'installation de l'observateur : *un
lecteur reel de la relation*. Cette passe est allee voir si cette relation
peut seulement exister. Elle ne le peut pas, et l'endroit exact ou elle se
perd est mesure.

    PRESENT       oui   l'agent emet task_id + session_id (G-28)
    PROPAGATED    NON   c'est ici que ca casse
    CALLED        n/a
    PERSISTENT    NON
    RESTART-SAFE  NON

    la relation Run ↔ Skill                           DEFER
    la deduire du temps, du compteur ou de l'unicite   REJECT

### Rien n'est propage vers l'agent

Le mode jetable lance l'agent avec exactement huit drapeaux : `--query
--model --provider --base_url --max_turns [--toolsets] --quiet
--usage-file`. **Aucun identifiant de tache.** Le `task_id` que Hermes OS
tient ne sert qu'a son propre bus d'evenements — `TASK_STARTED`,
`TASK_COMPLETED`.

Et `session/prompt` ne transporte que `{sessionId, prompt}`. Y ajouter un
champ serait inventer une API que le serveur ignorerait **en silence**, ce
qui est pire que la refuser.

Le `task_id` qui arrive dans un evenement Skill est donc **genere par
l'agent**. Les deux portent le meme nom et ne designent pas la meme chose.

### Ce qui remonte, remonte trop tard

`_extract_session_id` recupere bien le `session_id` de l'agent, depuis
stdout ou le fichier d'usage — mais a la **completion**, donc apres les
evenements Skill du tour. Et il n'est ecrit nulle part : ni dans le Ledger,
ni ailleurs. Il traverse `ChatResponse.metadata` et disparait.

### Le plafond de granularite est la session, pas le Run

    cle_de_session({'project_id': 'P1', 'mission_id': 'M-alpha'}) -> 'projet:P1'
    cle_de_session({'project_id': 'P1', 'mission_id': 'M-beta'})  -> 'projet:P1'

Deux missions d'un meme projet **partagent la session**, et c'est delibere :
`cle_de_session` groupe par projet pour qu'une campagne de 26 sections garde
sa continuite. Un `session_id` ne designe donc pas une mission.

Et une mission porte plusieurs Runs — `runs.tentative`, `runs.parent` — si
bien que meme une session 1:1 avec une mission ne designerait jamais un Run.

### Rien n'est persiste, et un commentaire l'affirmait

`SessionsDeMission._identifiants` est un dictionnaire **en memoire** : une
instance neuve le trouve vide. Son commentaire annoncait pourtant la survie
« apres un redemarrage du backend ». G-29 etait venu y chercher une clef de
jointure durable ; batir dessus aurait pris une table volatile pour une
trace. Le commentaire est corrige — ce qu'il apporte vraiment (reprendre le
contexte apres un processus d'agent mort) reste dit.

La table `runs` porte **29 colonnes**, aucune de session. Et `audit_log` a
exactement les colonnes qu'il faudrait — `session_id`, `task_id`,
`project_id` — pour **six lignes**, toutes des verifications manuelles
d'aout, `task_id` toujours `NULL`.

### Pourquoi DEFER et non REJECT

Rien n'est faux dans l'architecture. Les frontieres d'autorite sont nettes,
et c'est precisement parce qu'elles le sont qu'aucune des deux parties ne
peut fabriquer l'identite de l'autre. Il manque une donnee que seul l'amont
peut fournir.

REJECT, en revanche, sur les trois raccourcis a portee de main —
« l'evenement le plus proche dans le temps », « la seule session ouverte »,
« le dernier Run demarre ». Ils produiraient des associations confiantes et
fausses ; des tests les interdisent maintenant.

### Le chantier suivant n'est pas dans Hermes OS

La relation deviendrait possible si l'agent acceptait — et renvoyait — une
**etiquette de tour fournie par le client** : un champ que Hermes OS pose
sur `session/prompt` et que `on_skill_lifecycle` restitue. C'est une demande
a formuler en amont, pas une capacite a construire ici. Tant qu'elle
n'existe pas, l'observateur de G-28 reste non installe : sans relation, il
n'aurait rien a correler.

### Deux gardes ecrites de travers, et ce qu'elles ont appris

La garde contre les heuristiques temporelles balayait le **texte** des
fichiers. Elle accusait `backend/bridge/hermes_agent_bridge.py` a cause du
litteral `"session.most_recent"` — un nom de methode RPC dans la matrice de
capacites. Reecrite sur les identifiants de l'arbre syntaxique, elle regarde
ce que le module *fait* plutot que ce qu'il *contient*.

La garde sur les charges utiles, elle, accusait
`mcp_server/server.py:_skill_to_dict` et son `source_task_id`. Or c'est
l'entite `Skill` **du distributeur** de Hermes OS : ce champ relie une
competence de Hermes OS a une tache de Hermes OS, une relation ou il EST
l'autorite. HOS-274 avait fixe que les deux magasins ne se confondent pas ;
une garde qui les confond accuse le mauvais. Recentree sur les trois
surfaces qui servent les competences de **l'agent**.

### Le trou qu'une mutation a trouve

La mutation « la route affirme un `run_id` » est restee **verte** au premier
essai : toutes les gardes regardaient les modules qui *calculent*, aucune ne
regardait la charge utile rendue. Une surface pouvait donc fabriquer la
relation au dernier metre, et l'interface l'aurait affichee comme un fait.
`test_la_route_des_competences_de_l_agent_ne_rend_aucune_relation` existe a
cause de ce vert.

### Preuves

Suite complete 6049 passed, 3 skipped, 274 deselected ; tsc et vitest
verts.

Dix mutations, dix rouges : un `task_id` pousse vers l'agent, un `run_id`
dans le prompt ACP, la table volatile declaree durable, la session keyee par
mission seule, une colonne de session au Ledger, une relation declaree dans
la provenance, un Run devine par le plus recent, une route qui affirme un
`run_id`, la roadmap qui perd sa mesure, et le backend qui nomme le plugin
non installe.

`data/db/hermes.db` intacte ; aucune ecriture dans les magasins de
Hermes Agent.

## HOS-276 — L'observateur de Skills : legitime, et pas installe (2026-09-10)

G-28. G-27 laissait une porte nommee : `on_skill_lifecycle` est un hook
**plugin** documente, et un plugin Hermes OS le recevrait avec son identite
complete. Cette passe l'a ouverte pour voir, sur un `HERMES_HOME` de
substitution.

    le point d'observation et son proprietaire      ADOPT
    l'installation dans l'agent reel, aujourd'hui   DEFER

### La chaine, demontree

Avec le fichier versionne dans ce depot, trois mutations reelles :

    created  g28-depot-a  task='tache-1'  session='sess-depot'  prov='local'
    created  g28-depot-b  task='tache-2'  session='sess-depot'  prov='local'
    patched  g28-depot-a  task='tache-4'  session='sess-depot'  prov='local'

`task_id` **differe d'une mutation a l'autre**. C'est exactement la clef de
jointure qui manquait a G-27 — 0 des 75 enregistrements natifs la porte — et
elle arrive ici entiere, avec le nom local de la Skill, non anonymise. Deux
appels a `bump_use` intercales n'ont rien laisse : `loaded` est ecarte. Un
**nouveau processus** relit l'etat integralement.

### Pourquoi ADOPT sur la legitimite

L'observateur ne peut pas devenir une autorite **par construction du hook**,
pas par discipline : `_emit_skill_lifecycle` ignore la valeur de retour, et
chaque callback est isolee. Mesure des trois cas de defaillance :

    plugin absent      non charge   has_hook=False   mutation OK, enregistrement natif ecrit
    plugin desactive   charge       has_hook=False   mutation OK, enregistrement natif ecrit
    callback qui leve  charge       has_hook=True    mutation OK, enregistrement natif ecrit

L'agent reste proprietaire du contenu et du cycle natif dans les trois cas.

### Pourquoi DEFER sur l'installation

**Aucun consommateur.** G-27 a livre la lecture de provenance ; rien dans
Hermes OS ne montre encore une relation Run ↔ Skill. Installer aujourd'hui
produirait un fichier d'etat qui grossit et que personne ne lit — le
producteur sans lecteur que ce depot passe son temps a defaire. C'est le
defaut anti-orphelin pris par l'autre bout.

**Les internes de l'agent changent dans quatre jours.**
`plugin_compat.COMPAT_REMOVAL_DATE = 2026-09-14` : ce jour-la, tout plugin
externe important un module interne est **desactive**. Celui-ci n'en importe
aucun — `scan_plugin()` rend « aucun », et un test le garde — donc il
survit. Mais le runtime d'apres n'a pas ete mesure, et installer la veille
d'un changement structurel, c'est se donner un premier suspect au prochain
incident.

Prealables, dans cet ordre : une surface produit qui lit la relation, puis
le runtime post-2026-09-14 mesure et `scan_plugin()` rejoue dessus.

### Le contrat, mesure sur v0.21.0

    action                    created | edited | patched | installed | loaded
    skill_name                le nom local, NON anonymise
    provenance                installed | agent_created | external | local | unknown
    task_id / session_id      str, parfois ""
    use_count / reused / reuse_after_patch
    telemetry_schema_version  "hermes.observer.v1"

`loaded` part a **chaque invocation de Skill** — `skill_commands`,
`skills_tool`, `cron/scheduler_prompt` ; les quatre autres sont des
mutations, donc rares. `PluginState` plafonne a 10 Mio et refuse d'ecrire
au-dela : l'observateur ne retient que les mutations et borne sa liste, car
un observateur qui remplit son quota cesse d'observer sans le dire.

`agent/skill_commands.py` appelle `bump_use(skill_name, task_id=task_id)`
**sans** `session_id`. Un fait peut donc arriver sans session, et le
completer fabriquerait la correlation que G-27 a refuse d'inventer.

### Ce qui est livre

`integrations/hermes-agent/observateur-skills/` — manifeste, code et
README — **non installe**, et le README le dit en premiere ligne. C'est le
fichier exact qui a produit la mesure ci-dessus : garder la demonstration
plutot que son souvenir evite a la passe suivante de re-deriver le contrat.

Vingt-deux tests le tiennent, dont ceux qui gardent ses proprietes
d'observateur : aucun import hors bibliotheque standard (condition de survie
au 2026-09-14), aucun appel qui muterait une Skill, un seul hook au
manifeste, un retour toujours `None`, et un etat persiste plutot
qu'accumule en memoire.

### Ce que ce contrat ne permettra toujours pas

Rattacher une Skill a une **Mission** ou a un **Run** de Hermes OS. Le
`task_id` livre est celui de la tache de l'agent, pas d'un Run du Ledger.
Les relier demanderait une correspondance qui n'existe nulle part
aujourd'hui — c'est le sujet suivant, pas celui-ci.

### Preuves

Quinze mutations, quinze rouges, couvrant les neuf classes demandees :
plugin absent, plugin non charge, evenement perdu, mauvaise session, mauvais
`task_id`, provenance inventee, import des internes de l'agent, seconde
autorite, et relation perdue apres redemarrage — plus l'usage note comme une
mutation, les faits non bornes, un README qui laisserait croire le plugin
pose, et une correlation tiree des compteurs.

Suite complete 6037 passed, 3 skipped, 274 deselected ; tsc et vitest
verts.

Aucun octet des magasins reels : `.usage.json` porte toujours sa mtime du
1er septembre, `.bundled_manifest` celle du 9, les 74 `SKILL.md` sont
intacts, `plugins/` ne contient que les trois d'origine, et
`%LOCALAPPDATA%\hermes\plugin-data` **n'existe pas**. `data/db/hermes.db`
intacte.

## HOS-275 — La provenance des Skills, mesuree et bornee (2026-09-10)

G-27. G-26 avait conclu que la provenance n'existait pas sur la surface de
lecture. C'etait vrai de la **RPC**, et faux du **disque** : l'agent tient
trois fichiers qui la portent reellement.

    origine d'une competence installee   ADOPT    trois fichiers, lus
    systeme/upstream + integrite         ADOPT    empreinte recalculee
    generee par l'agent                  ADOPT    `created_by: "agent"`
    posee par le hub                     ADOPT    lock.json (vide ici)
    modification directe hors workflow   ADOPT    vue par l'empreinte
    persistance + redemarrage            ADOPT    demontres
    « utilisateur »                      REJECT   `null` couvre deux cas
    « apprise », « approuvee »           REJECT   aucun champ ne les porte
    correlation session / Run / Mission  REJECT   0/75, emise puis agregee
    ledger porteur d'une relation        DEFER    pas de clef de jointure

### Ce que l'agent persiste vraiment

    .bundled_manifest   69 entrees `nom:hash` — et 69/69 encore intactes
    .hub/lock.json      VIDE : aucune competence n'est passee par le hub
    .usage.json         75 enregistrements, dont 5 `created_by: "agent"`

`created_by` est **ecrit par `skill_manage`**, jamais deduit. La chaine
complete a ete demontree sur un `HERMES_HOME` de substitution, sans ecrire
un octet dans le foyer reel :

    creation au premier plan          -> created_by: null
    creation sous BACKGROUND_REVIEW   -> created_by: "agent"
    nouveau processus                 -> relit les deux

Persistance et redemarrage acquis. Sur l'installation : **60 systeme
intactes, 4 generees par l'agent, 1 en conflit**.

### Le piege que cette passe ferme

`skill_usage.is_agent_created()` ne lit **jamais** `created_by`. Malgre son
nom, il rend « ni bundled ni hub ». Mesure sur la substitution :

    g27-avant-plan     created_by=None     is_agent_created=True   <- faux
    g27-revue-de-fond  created_by='agent'  is_agent_created=True

`list_agent_created_skill_names()`, qui lit l'enregistrement, exclut la
premiere a juste titre. Deux fonctions voisines, deux methodes opposees. Un
garde interdit son usage cote Hermes OS, et une mutation le mesure.

### Trois refus, et leur raison

**« Utilisateur » n'est pas disponible.** `created_by: null` couvre a la
fois « creee au premier plan, donc a l'utilisateur » et « aucune origine
enregistree ». Les deux produisent le meme octet. La categorie s'appelle
donc `sans_marqueur` et n'affirme rien.

**« Apprise » et « approuvee » n'existent pas.** Aucun champ ne les porte,
et la file d'approbation n'a jamais servi (G-26 : `pending/` n'existe pas).

**La correlation a un Run est impossible.** `skill_manage` transmet bien
`task_id` et `session_id` a `record_created` / `bump_patch`, mais `_apply`
n'ecrit que `created_by` : les deux partent dans le hook
`on_skill_lifecycle`, consomme ici par le relais de metriques partagees qui
« emet un fait sans son identite locale » et n'agrege que des compteurs a
dimensions bucketisees. Mesure : **0 des 75 enregistrements** les porte, et
`telemetry/shared_metrics` ne contient aucun nom de competence.

Sans clef de jointure, le Run Ledger ne peut porter aucune relation. La
table `skills` de `hermes.db` a bien une colonne `source_task_id` — elle est
**vide**, et la remplir avec les competences de l'agent en ferait la seconde
verite que HOS-274 est alle fermer. Le chemin existe et il est nomme :
`on_skill_lifecycle` est un hook **plugin** documente, et un plugin Hermes
OS le recevrait avec son identite complete — mais cela demanderait
d'installer du code dans l'agent, decision qui n'appartient pas a une passe
de diagnostic.

### Le conflit de clef, rendu tel quel

Le magasin est indexe par nom de frontmatter dans 74 cas sur 75. Une
competence dont le dossier et le `name:` different porte donc **deux
enregistrements** : `documentation-verification` (`created_by: "agent"`,
jamais utilisee) et `Documentation & Identity Verification` (`created_by:
null`, trois usages) designent le meme dossier.

On ne tranche pas. `conflit` est une categorie a part entiere, rendue avec
ses deux valeurs. Preferer l'une serait exactement l'inference que G-27
interdit.

### Ce que le Gateway expose, et pourquoi ca ne suffit pas

`commands.catalog` rend `{usage, origin}` par competence. Mais son `origin`
ne consulte jamais `created_by` : il rend `hub` / `bundled` / `local`. Les
5 `local` de cette installation *sont* les 5 `created_by: "agent"` — par
**coincidence**, puisque aucune competence n'a ete ecrite a la main. En
conclure une equivalence serait l'inference que G-27 interdit. La provenance
se lit donc sur le disque, ou le marqueur est ecrit.

### Une categorie sans sa preuve est une affirmation

Chaque provenance rendue porte le fichier qui la soutient, et l'infobulle de
l'ecran le montre : `.bundled_manifest 7e829b4f / disque 7e829b4f`. C'est la
regle que le brief posait et que rien n'appliquait : une interface qui
affirme sans pouvoir montrer sa source n'est pas une lecture.

### Une mutation refaite

La mutation « provenance deduite de la localisation » importait d'abord
`skill_usage` depuis le venv de Hermes OS. Elle rougissait — sur une
`ImportError`, pas sur le defaut qu'elle nommait. Reecrite pour appliquer la
**meme regle** sans importer, elle touche les trois tests de comportement
attendus. Un mutant qui ne cree pas le defaut ne mesure pas la garde.

### Preuves

Suite complete 6015 passed, 3 skipped, 274 deselected.

Douze mutations, douze rouges : empreinte ignoree, cache de processus figeant
la lecture, modification directe invisible, champ de correlation vide,
`created_by` nul passant pour generee, recopie dans `hermes.db`, provenance
deduite de la localisation, categorie sans preuve, conflit tranche en
silence, route taisant l'absence de correlation, ecran affirmant
« utilisateur », et appel au piege `is_agent_created`.

`data/db/hermes.db` intacte ; rien n'a ete ecrit sous `%LOCALAPPDATA%\hermes`
— la demonstration est passee par un `HERMES_HOME` de substitution.

## HOS-274 — Les Skills : une verite de trop, et un faux succes (2026-09-09)

G-26. La passe devait etablir le cycle des Skills du cerveau. Elle a
d'abord trouve que Hermes OS en affichait deja une liste, et que cette
liste etait fausse.

    population installee      ADOPT    le disque, CORRIGE — 65 noms
    catalogue du hub          ADOPT    5493 entrees, pagination du runtime
    detail d'une entree       ADAPT    du hub seulement
    installation              REJECT   `installed: true` sans verification
    creation / edition /
    suppression               DEFER    outil de l'agent, pas methode RPC
    pending / diff / approve  DEFER    file reelle, approbateur injoignable
    rafraichissement a chaud  DEFER    `reload` ne rafraichit pas `list`

### Hermes OS annoncait vingt competences que l'agent ne sert pas

`backend/skills/registre.py` lit les competences de l'agent depuis
HOS-153, et le Skills Center les affiche. Il lisait
`hermes/hermes-agent/skills` — celles livrees avec le **depot** de
l'agent — au lieu du dossier **actif** `hermes/skills` que le runtime
resout, et il ignorait le champ `platforms:` que chaque `SKILL.md`
declare :

    registre.py (avant)   60 noms
    skills.manage list    65 noms
    en commun             40

Quarante sur soixante-cinq. L'ecran montrait `imessage`, `findmy` et
`apple-notes` a un agent **Windows** qui ne les chargera jamais, et taisait
vingt-cinq competences qu'il porte vraiment.

Corrige : le foyer suit `HERMES_HOME` comme `hermes_constants.get_hermes_home()`,
et la lecture honore `platforms:`. Les deux concordent desormais
**exactement** — 65 contre 65, aucun ecart dans un sens ni dans l'autre.
Lire `platforms:` n'est pas reimplementer la resolution du runtime : c'est
lire un champ que le fichier declare. Le reste de cette resolution reste au
runtime, et c'est pourquoi la RPC demeure l'autorite.

### La surface qui n'a pas ete livree

`vue_skills` sait lire la population installee par RPC. Elle ne le fait
pas, et la route a ete retiree apres avoir ete ecrite : Hermes OS la lisait
deja sur le disque, avec les descriptions et sans payer six secondes de
gateway. En offrir une seconde aurait fabrique la verite concurrente que
cette passe venait de fermer. Une surface negociable qu'on choisit de ne
pas offrir est aussi un resultat.

Le premier jet ouvrait un onglet Skills au Center Cerveau, en ignorant que
le Skills Center existait. Le catalogue y a ete deplace ; l'onglet du
Cerveau a disparu.

### Cinq actions, sept absentes

    list search install browse inspect                repondent
    create edit delete pending diff approve reject    4017

`4017` n'est pas `-32601`, et la nuance decide : la methode existe, elle a
ete construite **sans** ces gestes. Cote agent la machinerie complete
existe pourtant — `skill_manager_tool.py` cree, edite, patche et supprime —
mais comme **outil que l'agent s'appelle a lui-meme**, jamais comme methode
que Hermes OS peut demander. Meme forme que les approvals de G-23.

### Le faux succes d'`install`

`_skills_install` appelle `do_install` et **jette sa valeur de retour**.
`do_install` rend `None` sur six chemins — sources absentes, identifiant
irresoluble, bundle non recupere, nom non resolu, deja installee sans
`--force`, et **installation bloquee par le scanner de securite**. Le
gateway repond `{"installed": true}` dans tous les cas.

Mesure : `skill-qui-nexiste-absolument-pas-hos274` rend `installed: true`.
Ni quarantaine, ni ligne d'audit : `.hub/quarantine` et `.hub/audit.log`
sont restes vides. Rien n'a ete recupere, rien examine, rien pose. Le meme
runtime, interroge par `inspect`, rend honnetement `{}` — il *sait* que ce
nom n'existe pas ; c'est le chemin d'installation qui ne le dit pas.

### La persistance est reelle, la fraicheur ne l'est pas

Mesure sur un `HERMES_HOME` de substitution, sans ecrire un octet dans le
vrai :

    processus qui ecrit la skill   scan True  / liste False
    nouveau processus              scan True  / liste True

`skills.manage list` passe par `banner.get_available_skills()`, memoise
**pour la vie du processus** sans TTL ni signature, alors que le scanner
qu'il enveloppe se re-declenche des que les dossiers changent. Et
`skills.reload` ne rattrape pas : il annonce `added=['hos274-reload']`
pendant que `list` continue de l'ignorer dans le meme processus. Deux RPC
de la meme surface se contredisent — raison de plus de garder le disque
comme source de la population installee.

### Le pending existe, et il est hors de portee

Contrairement aux approvals du Gateway (G-23, process-locales en memoire),
`write_approval` est **adosse a des fichiers** :
`<hermes_home>/pending/skills/*.json`, avec `stage_write`, `list_pending`,
`get_pending`, `discard_pending` et `skill_pending_diff`. De l'etat
inter-processus, donc — exactement ce qui manquait a G-23.

Mais aucune RPC ne l'expose ; `%LOCALAPPDATA%\hermes\pending` **n'existe
pas** ; la porte est fermee par defaut, `skills.write_approval` etant
absent de `config.yaml` ; et `config.get` refuse cette cle — `4002 unknown
config key`. L'approbation elle-meme, `apply_skill_pending`, s'appelle en
intra-processus depuis le `/skills approve` de la CLI. L'activer depuis
Hermes OS mettrait chaque ecriture de Skill dans une file que rien, cote
cockpit, ne pourrait vider.

### Ce qui n'existe pas sur la surface de lecture

La distinction utilisateur / systeme / generee. `skill_provenance` est un
`ContextVar` de processus (`foreground` / `background_review`), pas une
donnee portee par la skill ; le ledger `.curator_ledger.jsonl` enregistre
un acteur par mutation mais aucune RPC ne l'expose. La question du brief a
une reponse mesuree, et c'est « non ».

### Deux gaspillages que seule la verification au navigateur a montres

Les requetes du catalogue repartaient toutes les dix secondes malgre
`staleTime: Infinity` : le client porte un `refetchInterval` global, et
`staleTime` ne desarme pas un intervalle. Ce n'etait pas cosmetique — le
catalogue passe par le hub **distant**, et chaque appel fait reecrire a
l'agent un index de 705 Ko. Les trois requetes coupent desormais
l'intervalle explicitement. Mesure apres correction, temoin compris :
`/health`, `/missions` et `/runtime/resources` repollent deux fois en
22 s, les trois routes Skills zero.

La recherche, elle, partait **a chaque frappe** : cablee sur `onSearch`,
« obsidian » declenchait huit appels au hub, un par prefixe, chacun une cle
React Query distincte donc aucun deduplique. Debouncee a 400 ms — mesure :
huit frappes, **une requete**, portant le terme complet.

### Une correction incidente, hors brief mais trouvee en chemin

L'onglet Permissions du Center Cerveau etait imbrique sous le garde de
`useAgentVue` : une panne du gateway le faisait disparaitre. Or son journal
est **local a Hermes OS** et reste parfaitement lisible — et c'est
precisement quand le cerveau ne repond plus qu'on veut savoir ce qu'on lui
a refuse. Sorti du garde, avec une garde structurelle qui l'y maintient.

Au passage, et note plutot que lisse : `browse`, `search` et `inspect` sont
des lectures **qui font ecrire l'agent**. C'est lui qui ecrit son cache,
par son propre chemin ; Hermes OS ne touche pas son disque. « Lecture
seule » decrit ici l'autorite, pas l'absence d'effet.

### Trois tests ecrits puis jetes, et un quatrieme corrige par mutation

Deux affirmaient leurs propres constantes : l'un relisait un litteral JSON
que je venais d'ecrire pour « consigner » la mesure d'`install`, l'autre
verifiait qu'une action n'appartenait pas a une liste que le test portait
lui-meme. Aucun ne pouvait rougir. Un troisieme gardait le *nom d'un
bouton* dans le composant — une garde ecrite sur une forme se contourne en
renommant ; elle porte maintenant sur la route.

Le quatrieme etait pire parce qu'il passait : `HERMES_HOME` est pose sur
cette machine, donc la lecture n'atteignait jamais le repli, et la mutation
qui reintroduisait `hermes-agent` restait **verte**. La relecture n'a rien
vu ; la mutation, si. Troisieme fois dans ce depot.

### Preuves

Douze mutations, douze rouges. Suite complete 5998 passed, 3 skipped,
274 deselected ; `tsc` et `vitest` verts ; `data/db/hermes.db` intacte ;
74 `SKILL.md` de l'agent inchanges.

## HOS-273 — Interrompre le tour que l'utilisateur regarde (2026-09-09)

G-24. Quatre capacites, quatre verdicts, et un seul chemin qui atteint
vraiment un tour ACP en cours.

    interruption      ADOPT    demontree de bout en bout
    permissions ACP   ADOPT    deja livree en HOS-271, correlee et journalisee
    steering          DEFER    aucun mecanisme n'injecte dans un tour actif
    approvals Gateway REJECT   process-locales, sans producteur (G-23)

### L'interruption : ADOPT

`session/cancel` est le mecanisme natif d'ACP. Le contrat, lu dans
`acp_adapter/server.py` : notification sans reponse, `get_session` sur
l'etat **vivant** du processus, `cancel_event.set()` et
`request_hard_interrupt`. Et surtout — **retour silencieux quand la session
est inconnue**. L'absence d'erreur ne prouve donc rien.

Trois mesures, meme demande et meme modele :

    sans annulation               50 s    9898 caracteres
    cancel a t+12s                12 s       0 caractere
    cancel a t+12s, MAUVAIS id   195 s   14120 caracteres

Le controle est reel *et* correle : un identifiant errone laisse le tour
aller au bout. C'est exactement ce que le Gateway ne faisait pas — il
rendait `interrupted` en agissant sur une session qu'il venait de
materialiser lui-meme (G-23).

De bout en bout, par la route HTTP :

    reference                    217 s   564 caracteres
    POST /cancel a t+15s          17 s     0 caractere

### Deux faux controles corriges, tous deux deja livres

**`POST /conversation/{id}/cancel`** marquait la conversation `CANCELLED`
cote Hermes OS, appendait un message et rendait `"success": true,
"status": "cancelled"` — **sans jamais toucher le tour**, qui continuait a
ecrire.

**Le bouton « stop » de l'Assistant** n'appelait que `abort()` sur le
`fetch`. Le navigateur cessait de lire ; l'agent continuait — sur le GPU,
dans le workspace, dans l'historique. Echap donnait l'illusion d'arreter.

Les deux affirmaient avoir arrete quelque chose. Aucun ne le faisait. Ils
etaient la avant cette passe, et c'est la mesure de G-23 qui a appris a les
reconnaitre.

### Ce que `tour_interrompu` dit, et ne dit pas

Il dit que l'ordre est **parti** vers une session vivante. Pas que le tour
s'est arrete : `session/cancel` ne repond pas, et l'agent rend
silencieusement pour une session qu'il ne connait plus. Un booleen
d'emission, jamais une interruption constatee — et l'interface ne le
presente pas autrement.

### Le steering : DEFER

Aucun mecanisme n'injecte une instruction dans un tour **actif**. Ce
qu'ACP offre est `cancel` puis un nouveau prompt : le serveur conserve
`interrupted_prompt_text` et rattache la demande annulee au tour suivant.
C'est un enchainement « arreter puis redemander », pas une injection — un
geste produit different, qui merite d'etre concu comme tel plutot que
maquille en steering.

Rien n'est donc livre pour le steering. Le brief le demandait
explicitement : aucune facade tant que le mecanisme n'est pas demontre.

### Preuves

Huit mutations, huit rouges — mauvais identifiant, session terminee,
processus mort, cle inconnue, autre session interrompue, route qui affirme
sans demander, bouton qui ne coupe que la lecture, et annulation qui
emprunterait le Gateway.

Suite complete verte, `tsc` et `vitest` verts, `data/db/hermes.db` intacte.

## HOS-272 — ACP et Gateway : REJECT, mesure a l'appui (2026-09-09)

G-23. Le chat passe par ACP, les controles natifs (`approval.*`,
`session.steer`, `session.interrupt`) vivent dans le Gateway. Question :
peut-on faire converger les deux ?

### Ce qui rend la convergence tentante

Les deux transports **partagent le magasin**. Mesure :

    sessionId ACP                       a877725d-b76b-4cce-adb0-953983069969
    present dans session.list Gateway   oui, tel quel
    session.resume(id ACP)              OK

Un identifiant ACP est donc un identifiant de session **stockee** que le
Gateway sait reprendre. On tient la, apparemment, la passerelle.

### Ce que la mesure a reellement montre

Pendant qu'un tour ACP tournait vraiment — 3242 fragments streames,
`POEME.md` de 344 octets ecrit sur le disque — le Gateway a ete interroge
sur le meme identifiant :

    session.resume(id ACP)   -> OK, handle d50a9c14
    running vu par Gateway   -> False
    approval.pending         -> {"approvals": []}
    session.steer            -> {"status": "queued", "text": "arrete"}
    session.interrupt        -> {"status": "interrupted"}

Le tour ACP s'est **termine normalement** et a ecrit son fichier.

`resume` n'avait pas attache le tour en cours : il avait materialise une
**seconde session vivante** dans le processus Gateway, a partir de la meme
ligne stockee. Le steer a ete mis en file pour elle, l'interruption l'a
interrompue, elle. Le tour reel n'a jamais rien su.

**Une ligne stockee, deux sessions vivantes, deux processus.** Les
controles agissent sur la vivante de *leur* processus, et rendent un succes
franc.

### Decision : REJECT

Pas DEFER. « Convergence non demontree » serait trop doux pour ce qui a ete
mesure : la convergence par identifiant partage **produit des succes HTTP
confiants qui ne touchent rien**. C'est le defaut fondateur de ce depot —
`success: True, 5/5` au-dessus d'un workspace vide — sous une forme neuve,
et il serait entre par la porte qu'on croyait ouvrir.

Pas ADAPT non plus : un adaptateur devrait atteindre l'etat en memoire du
processus ACP depuis le processus Gateway, et il n'existe aucun canal entre
eux. Le seul moyen d'atteindre un tour en cours est le transport qui le
porte.

### Le chemin qui existe vraiment

ACP a son controle natif : `acp_adapter/server.py` expose
`async def cancel(session_id)` avec un `cancel_event`, et gere le texte de
steering apres une annulation. L'interruption du chat passe donc par
**ACP**, adressee a l'identifiant ACP.

Notre client ne l'emet pas encore. C'est un chantier — pas une convergence,
et pas une autorite nouvelle : on utiliserait la commande que Hermes Agent
fournit pour le transport qu'on emprunte.

### Ce qui a ete livre

Aucune fonctionnalite. Une **garde**, parce que la mesure a montre que le
faux succes est a portee de main : rien n'empechait de cabler un bouton
« Interrompre » sur `session.interrupt`, qui aurait repondu `interrupted`
sans jamais toucher le tour affiche a l'ecran.

Quatre tests fixent la ligne de partage : aucun controle de **tour vivant**
n'est offert comme mutation, aucune route du pont ne le cable, le service
ne le relaie pas, et le contrat de mutation ne porte que sur de l'etat
**stocke** — `state.db` ou `config.yaml`. C'est d'ailleurs pourquoi les
trois mutations existantes fonctionnent : brancher, renommer et basculer un
toolset n'ont jamais vise le vivant.

Cinq mutations, cinq rouges.

## HOS-271 — Le chat interactif existait, et il etait injoignable (2026-09-09)

G-22. Le chantier demandait de construire un chemin Chat pour produire
approbations, steering et interruption. La premiere mesure a change la
question : **ce chemin existe deja**.

### Ce qui existait

Une conversation liee a un projet ouvre une session Hermes Agent **vivante
par ACP** — pas par le gateway. `backend/conversation/harnais.py` la tient,
`hermes_agent_acp.py` la parle, et le flux NDJSON arrive au frontend.

Mieux : l'agent y demande des permissions. Avant chaque **edition de
fichier**, il adresse un `session/request_permission` au client et
**attend** ; `HermesAgentACP._repondre` tranche sur la politique de Hermes
OS — hors du dossier confie, ou fichier gouvernant, refus.

Mesure sur un tour reel : **quatre decisions, trois refus**. L'agent a
tente `/home/user/NOTE.md`, `/home/emeri/NOTE.md`, puis un troisieme chemin
hors workspace — trois refus — avant d'ecrire au bon endroit. Le controle
agit vraiment, et c'est le meme tatonnement que l'incident du 2026-08-21.

Et il etait **invisible** : un `logger.warning` pour les refus, rien du
tout pour les accords.

### Le defaut qui rendait ce chemin injoignable

`harnais.disponible()` sonde le backend par un `requests.get` **synchrone**
sur son propre `/health`. Appelee depuis le handler de conversation d'un
uvicorn mono-worker, la sonde bloque la boucle qui doit y repondre :
`ReadTimeout` a tous les coups, et le harnais **toujours** ecarte.

Le backend se demandait s'il etait vivant pendant qu'il servait la requete
qui posait la question.

Le journal du serveur le disait mot pour mot — « chat servi en direct (sans
harnais) : le backend de Hermes OS ne repond pas » — et personne ne l'avait
lu. C'est pourquoi le chemin ACP fonctionnait parfaitement depuis un
processus separe et jamais depuis l'Assistant.

Deporte par `asyncio.to_thread`, le chemin est emprunte. La preuve tient a
la signature du flux :

    avant   {'tool_calls': 1, 'tool_result': 1, 'content': 14, 'done': 1}
    apres   {'thinking': 46, 'content': 10, 'done': 1}

`tool_calls`/`tool_result` est la boucle d'outils de Hermes OS ;
`thinking`/`content` est le harnais. Et une decision de permission apparait
au journal, corrigee a la session ACP qui l'a produite.

### Ce qui est livre

Le journal des decisions d'ecriture, et l'ecran qui les montre. Quatre
issues distinguees, parce qu'elles ne disent pas la meme chose :

    accordee                  l'agent a ecrit, avec l'option retenue
    refusee_hors_workspace    il sortait du dossier confie
    refusee_protege           il touchait un fichier qui definit le travail
    sans_option               aucune option acceptable n'etait proposee

Le journal **observe** : la decision reste dans l'adaptateur ACP, ou elle a
toujours ete, et une garde sur l'arbre syntaxique lui interdit d'y toucher.
La trace durable va au bus d'evenements, journal de Hermes OS.

### Ce que ce journal ne prouve pas

`session/request_permission` ne porte que sur les **editions de fichiers**.
Le terminal de l'agent ne demande aucune permission : il execute. Un refus
visible ne prouve donc pas qu'une ecriture a ete empechee — l'agent peut
reessayer par la, et l'a deja fait. L'ecran le dit.

### Approvals, steering, interruption

Le producteur est desormais reel **pour les permissions d'edition**. Les
trois capacites du gateway (`approval.*`, `session.steer`,
`session.interrupt`) restent hors d'atteinte : elles vivent dans le
processus **gateway**, et le chat passe par **ACP**. Deux transports, deux
files. Les brancher demanderait de faire passer le chat par le gateway —
un autre chantier, et cette passe ne le simule pas.

### Preuves

Chaine mesuree de bout en bout : requete HTTP -> backend -> session ACP
vivante -> tour reel -> streaming -> demande de permission -> decision
Hermes OS -> journal -> API, avec `NOTE.md` verifie sur le disque et
l'identifiant de session ACP porte par la decision.

Huit mutations, huit rouges apres correction d'une assertion qui construisait
son attendu a partir des constantes qu'elle devait epingler : rendre les deux
refus identiques ne la faisait pas rougir, puisque l'attendu se collapsait
avec eux. Epinglee sur les litteraux — ce que l'API et l'interface
consomment.

Un test ecrit dans la meme passe s'est aussi trompe de cible : il remplacait
`_publier`, c'est-a-dire la fonction **qui porte** la protection, et testait
donc son propre bouchon. Corrige en faisant tomber le bus.

## HOS-270 — Les approbations n'ont pas de producteur ; les toolsets, si (2026-09-09)

Le chantier demandait les approbations en priorite. Elles ne sont pas
integrables aujourd'hui, et ce n'est pas l'API qui manque.

### Pourquoi les approbations sont bloquees

Le runtime les expose : `approval.pending`, `approval.received`,
`approval.respond` repondent toutes les trois. Trois mesures expliquent
pourquoi cela ne suffit pas.

**Le mecanisme est en memoire, dans le processus.** `_gateway_queues` est
un dict de module de `tools/approval.py`, et chaque entree porte un
`threading.Event` qui **bloque un fil de l'agent**. Une approbation
n'existe que pendant qu'un tour tourne dans ce processus-la. Rien n'est
persistant, rien ne traverse.

**Le chemin mission ne peut pas en produire.** `cli.py` pose
`HERMES_SINGLE_QUERY_SESSION=1` pour tout `--query` — exactement ce que
Hermes OS lance — et la porte prend alors le chemin deterministe
d'`approvals.single_query_mode`. Sa docstring dit le pourquoi : « without
this marker the gate would wait the full timeout, fail closed and push the
agent toward workarounds ». L'agent se protege lui-meme d'une porte que
personne n'ecouterait ; ce n'est pas un defaut, c'est la bonne decision.

**Le gateway du pont pourrait en produire, mais n'en produit pas.**
`tui_gateway/server.py` pose `HERMES_GATEWAY_SESSION=1` et enregistre
`register_gateway_notify` : un tour lance **la** produirait des
approbations repondables. Le pont ne lance aucun tour — il n'emet que des
RPC de lecture.

Mesure sur session vivante : `approval.pending` rend `{"approvals": []}`,
`approval.respond` rend `{"resolved": 0}`.

Un panneau branche aujourd'hui serait donc **vide par construction**, et
son bouton ne resoudrait jamais rien. La condition prealable est le
**chat** — faire passer des tours par le gateway du pont ; les approbations
viendront avec, et pas avant. Un test interdit nommement de les declarer
mutation entre-temps.

C'est le troisieme piege de cette forme, apres `delegation.pause` et le
lancement de subagent : une methode qui repond parfaitement et sur laquelle
il n'y a rien a brancher.

### Les toolsets, eux, portent

`tools.configure` appelle `save_config` : il ecrit `config.yaml`, que
**tous** les processus agent relisent — missions comprises. C'est
exactement ce qui manquait a la pause de delegation.

    clic « inactif » sur a2a
    config.yaml   76a3fbd37f6d4498 -> 0529eab3053f65c6
    processus neuf : a2a = True

Troisieme mutation du contrat G-18, et la premiere qui ne touche pas
`state.db` — le contrat vaut pour tout etat natif de l'agent, pas seulement
sa base.

### Deux verifications qui ont failli passer pour des conclusions

**Une fausse alerte de perte.** Un `diff` de lignes entre la sauvegarde et
le fichier reecrit montrait deux entrees de modele disparues. Comparaison
**des structures** : zero cle perdue — les deux lignes avaient simplement
change de place dans un YAML re-serialise. Un diff de lignes est le mauvais
instrument pour un fichier qu'un programme reecrit, et il m'a fait annoncer
une perte qui n'existait pas.

Ce que le round-trip fait reellement : il **materialise des defauts
implicites** — `known_builtin_toolsets`, `known_plugin_toolsets`, et la
liste des toolsets actifs passee de `['coding']` a la liste complete. Rien
n'est retire ; mais le premier basculement **fige les defauts du jour**, et
un defaut amont qui changerait plus tard ne s'appliquerait plus. C'est une
consequence a connaitre avant de cliquer.

**Une course reelle.** Desactiver `a2a` a echoue au premier essai —
« toolset inconnu du runtime » — et reussi au second. `a2a` est un toolset
de **plugin**, et `valid_toolsets` depend de
`_get_plugin_toolset_keys()`, donc de la decouverte des plugins dans le
processus gateway interroge. La course existe.

Elle n'est pas maquillee : le runtime rend `200` avec le nom dans `unknown`
et `changed` vide, et le service en fait un **refus** avec sa raison, que
l'interface affiche. Le lire comme un succes aurait montre un basculement
qui n'a pas eu lieu — le pire des deux comportements.

### Preuves

Clic reel dans Cerveau · Outils : `config.yaml` change d'empreinte, et un
processus neuf voit le toolset actif. Le refus s'affiche quand le runtime
refuse. Etat d'origine restaure a la fin (`a2a` desactive, verifie).

Huit mutations, huit rouges — dont « une approbation entre au contrat »,
qui garde le blocage lui-meme.

### Ce qui reste

Le steering et l'interruption butent sur la meme condition que les
approbations : ils exigent un tour **vivant**. Le chat est donc la
prochaine capacite a traiter, et il en debloque trois d'un coup —
approbations, steering, interruption. Les autres surfaces sans
consommateur : `mcp` (11 methodes), `groups` (18, endpoint non configure),
`projects` (15), `learning`, `skills`.

## HOS-269 — Deux tranches choisies par la mesure, deux ecartees par elle (2026-09-09)

G-20. Le registre expose 206 methodes. La question n'etait pas « lesquelles
sont faciles a brancher » mais « lesquelles valent quelque chose une fois
branchees ». Deux candidates evidentes ont ete **ecartees par la mesure
avant d'ecrire une ligne**.

### Ce qui a ete ecarte, et pourquoi

**`delegation.pause`** semblait la tranche ideale : une methode, une valeur
d'operateur claire, dans les priorites du chantier. `_spawn_paused` est un
**global de module dans le processus gateway**. Mesure :

    connexion A : delegation.pause(True)  -> paused = True
    connexion B : delegation.status        -> paused = False

Un bouton du cockpit aurait donc bride le gateway du pont — un processus ou
**aucune mission ne tourne**, les missions passant par `hermes_agent_cli`.
C'est exactement « une UI qui simule une mutation ». Non integree, et le
contrat de mutation ne la porte pas ; un test l'interdit nommement.

**Le lancement d'un subagent** n'existe pas comme RPC. Verifie dans le
source : c'est `delegate_tool.py`, un **outil que l'agent appelle
lui-meme**, avec `MAX_DEPTH = 1`. Hermes OS peut observer
(`delegation.status`, `spawn_tree.list`) et piloter un enfant existant
(`subagent.steer`, `interrupt`) — jamais en creer. Ce qui est coherent avec
la regle qui prime sur tout : le cerveau decide, l'OS n'ordonne pas.

**`groups` / Bot-a-Bot** existe — 18 methodes, protocole v2 — mais
`groups.capabilities` rend `endpoint: {available: false, reason:
not_configured}` et `groups.list` rend zero salon. Le raccorder afficherait
une surface vide sur une transport non configure. PLANNED.

**Memory** reste sans couture : aucune methode `memory.*` dans les 206. La
capacite vit dans `tools/memory_tool.py` et son magasin, cote agent, et
figure dans les toolsets actifs. Hermes OS ne peut ni la lire ni l'ecrire
par le pont — donc ni lui appliquer sa provenance, ni sa quarantaine, ni sa
promotion. Le blocage est franc et documente ; fabriquer une API `memory.*`
serait exactement ce que G-19 interdit.

### Les deux tranches retenues

Les sessions, ou la valeur etait immediate : le cockpit affichait un
inventaire de conversations **qu'on ne pouvait pas ouvrir**.

**Lire une session.** `session.history` est `live=True` : lire exige
d'activer d'abord. Les deux gestes appartiennent a l'agent ; Hermes OS les
demande dans l'ordre, avec le handle runtime pour le second. L'activation
n'ecrit rien (G-18), ce qui laisse la lecture dans une **vue**.

**Renommer une session.** Deuxieme mutation du contrat G-18, et elle en
verifie l'extensibilite : meme enchainement, meme regle — un refus du
runtime est un resultat. Un titre vide est refuse **avant tout envoi** :
`session.title` sans titre *lit* le titre au lieu de l'ecrire, donc envoyer
une chaine vide n'aurait rien fait tout en laissant croire le contraire.

### Ce que la persistance prouve, et ce qu'elle ne prouve pas

G-18 avait pris le md5 de `state.db` comme preuve de mutation. Mesure sur
le renommage : **le fichier principal ne bouge pas** — `9d72b1aff221f33c`
avant et apres — et un processus neuf lit pourtant le nouveau titre.
L'ecriture vit dans le WAL, qui fait partie de la base.

Le md5 du fichier principal est donc un signal **suffisant et non
necessaire**. La conclusion de G-18 tient — `session.branch` avait bien
change le fichier — mais l'argument « `session.resume` n'ecrit rien parce
que l'empreinte est identique » etait plus faible que presente : un WAL
aurait pu absorber une ecriture de service. Ce qui reste etabli pour
`resume` est ce qui compte : son handle est ephemere et la session stockee
est intacte. La preuve fiable d'une mutation est la **relecture par un
processus neuf**, et c'est elle qui est utilisee ici.

### Un defaut trouve par la console, pas par l'oeil

Le lecteur d'historique affichait correctement, et React signalait
« Each child in a list should have a unique key ». Mesure sur une session
reelle : un message `tool` n'a **ni `row_id`, ni `text`, ni `timestamp`** —
il porte `name`, `args`, `context`. Deux d'entre eux collisionnaient donc
sur une cle `undefined`, et leur contenu ne s'affichait pas du tout.

Corrige : cle composite, et les appels d'outil sont rendus pour ce qu'ils
sont — leur nom et leurs arguments. Un panneau qui montre la conversation
sans montrer les outils appeles raconte la moitie de ce qui s'est passe.

### Preuve

Cockpit, Cerveau · Sessions, clics reels :

- **Lire** sur « Refusal to create file » — une session de sondage de
  HOS-264 — affiche le fil : la consigne, l'appel d'outil, la reponse, et
  le raisonnement replie sous « voir le raisonnement » ;
- **Renommer** — le titre change dans la liste sans rechargement, et un
  processus neuf le relit : `20260906_080847_290a7c` porte desormais
  « G-20 renomme depuis le cockpit ».

Sept mutations, sept rouges apres correction d'un mutant qui visait le nom
de la methode cliente la ou la regle anti-orphelin cherche une URL — la
meme erreur qu'en HOS-267, et le meme correctif.

### Ce qui reste

Douze surfaces exactes restent sans consommateur. Le classement par valeur
plutot que par nombre de methodes donne, pour la suite : le steering et
l'interruption (mais ils exigent une session **vivante**, donc le chat), les
approbations (`approval.pending` est lisible tout de suite), puis les
toolsets — dont il faudra d'abord mesurer si `tools.configure` est durable
ou process-local, comme la pause l'etait.

## HOS-268 — La matrice mesurait notre vocabulaire, pas le runtime (2026-09-09)

G-19. HOS-267 avait consigne qu'il restait a verifier les noms sondes,
apres la decouverte que le fork existait sous `session.branch`. Cette passe
les confronte tous au registre reel.

### Le releve

`tui_gateway.server` tient un dictionnaire `_methods`. On le vide, avec
**l'interpreteur de l'agent** — le notre n'a aucune de ses dependances.

    206 methodes enregistrees sur v0.21.0
    le pont en sondait 62

Deux pieges rencontres en construisant le releveur, tous deux du genre qui
donne un inventaire partiel avec l'assurance d'etre complet :

- une premiere version lisait les decorateurs sur l'arbre syntaxique et
  n'en voyait que **110 sur 206**, faute de connaitre `_room_method`,
  `_rpc` et leurs pareils. Un inventaire partiel est pire qu'aucun ;
- `print` ne ressort pas : `hermes_bootstrap` detourne `stdout`, qui est le
  canal JSON-RPC. Mesure : `stdout` vide, la liste entiere sur `stderr`. Le
  releve passe donc par un fichier — dependre d'un flux qu'un autre
  programme possede, c'est dependre de son implementation.

### Ce que la confrontation a montre

Sur les trois surfaces declarees absentes, **les trois noms avaient ete
inventes** :

    session.fork     n'existe pas -> mais le fork existe : session.branch
    memory.list      n'existe pas -> et aucune methode memory.* n'existe
    memory.manage    n'existe pas
    subagent.start   n'existe pas -> et rien ne lance de subagent

Les deux dernieres absences se confirment, mais elles ne prouvaient rien
avant : mesurer l'absence d'un nom qu'on vient d'inventer ne dit rien du
runtime. Elles sont desormais etablies contre les 206.

Et la sous-couverture etait massive :

    mcp        11 methodes,  1 declaree
    browser     5 methodes,  1 declaree
    session    30 methodes,  5 declarees
    groups     18 methodes,  0 declaree   (le Bot-a-Bot existe)
    projects   15 methodes,  2 declarees

La matrice annoncait « 15 completes sur 18 ». Reconstruite depuis le
registre : **19 sur 19**. Elle ne mesurait pas le runtime, elle mesurait
notre vocabulaire.

### Absent ne disait pas une chose, mais deux

« Absente » melangeait « le runtime ne sait pas le faire » et « le runtime
le fait sans nous laisser le demander ». `SANS_RPC` porte la seconde, avec
ce qui a ete cherche :

- **memory** — aucune methode `memory.*`. La capacite existe comme **outil
  interne** (`tools/memory_tool.py`), et figure dans les toolsets actifs que
  `groups.capabilities` publie. L'agent s'en sert ; Hermes OS ne peut ni la
  lire ni l'ecrire par le pont ;
- **spawn de subagent** — rien ne lance de subagent. `spawn_tree.*` lit
  l'arbre, `subagent.steer`/`interrupt` pilotent un enfant existant,
  `handoff.*` transfere. Un subagent nait de l'agent lui-meme — ce qui est
  coherent avec la regle qui prime sur tout : le cerveau decide, l'OS
  n'ordonne pas.

**Corriger la matrice ne devait pas faire disparaitre l'absence.** `memory`
s'affichait « absente » tant qu'un faux nom la representait ; retirer ce nom
l'aurait effacee de l'ecran, remplacant une absence mal nommee par un
silence — pire, puisqu'un operateur en conclurait qu'elle est disponible.
La negociation porte donc `sans_rpc`, et le panneau l'affiche. Une mutation
a trouve ce trou : supprimer le champ ne faisait rougir personne.

### Ce qui rend le defaut impossible a refaire

Le releve est verse au depot (`config/gateway_registre.json`), date et
empreint. Trois gardes :

- tout nom declare doit exister dans le registre — c'est celle qui aurait
  attrape `session.fork` le premier jour ;
- une surface `SANS_RPC` ne doit avoir **aucune** methode dans le registre
  entier, et doit dire ce qui a ete cherche ;
- le releve doit correspondre a l'agent installe, sans quoi les noms sont
  valides contre un inventaire perime — meme lecon que G-15.

Six mutations, six rouges. Deux ont dû etre reecrites : l'une ne vidait que
la premiere phrase d'une justification qui restait longue, l'autre visait le
nom d'une methode cliente la ou la garde cherche une URL. Un mutant qui ne
cree pas le defaut ne mesure pas le garde-fou.

Deux tests de HOS-265 ont rougi : ils verifiaient « une capacite partielle
n'est pas complete » **sur `delegation` et `memory`**, c'est-a-dire sur des
donnees de la matrice plutot que sur la regle. Decouples d'une surface
d'essai : la propriete ne doit pas dependre de la surface qui se trouve
etre partielle aujourd'hui.

### Ce que cela ne change pas

Aucune des surfaces nouvellement exactes n'est **integree** pour autant :
`groups`, `mcp` et les vingt-cinq methodes de session que le pont ignorait
restent PLANNED, faute de consommateur frontend. La matrice dit desormais la
verite sur ce que le runtime expose ; elle ne dit pas que Hermes OS s'en
sert.

## HOS-267 — Qui est autorite sur l'etat de Hermes Agent (2026-09-09)

G-18. HOS-266 avait laisse les mutations PLANNED faute d'avoir tranche
cette question. Cette passe la tranche par la mesure, et integre une
mutation reelle de bout en bout.

### La question etait mal posee, et la mesure l'a montre

Le brief supposait que « reprise de session » etait une mutation de l'etat
persistant. Mesure sur le vrai runtime :

    session.resume
      state.db      119574528 octets, md5 de802a3a4846ea8f  ->  IDENTIQUE
      state.db-wal                                          ->  change
      state.db-shm                                          ->  change

`state.db` **ne bouge pas**. Seuls `-wal` et `-shm` changent, ce qui est la
comptabilite de lecture de SQLite. `session.resume` n'ecrit rien : il lit
une ligne et materialise une session **vivante en memoire**, dans le
processus gateway. Et ce handle-la meurt avec lui :

    resume            -> handle 2c356026, session.status OK
    gateway tue       ->
    session.status    -> 4001 session not found
    session stockee   -> toujours la

Ce n'est donc pas une mutation mais une **activation runtime**. La
presenter comme durable serait un mensonge d'interface.

### Trois choses, trois proprietaires

    la conversation stockee          Hermes Agent      state.db, durable
    la session vivante               le gateway        ephemere
    le recit de ce qu'on a demande   Hermes OS         son bus d'evenements

C'est la confusion entre les deux premieres qui rendait G-18 difficile. Une
fois separees, le contrat s'ecrit tout seul : **Hermes OS demande, il
n'ecrit pas.** `state.db` fait 114 Mio, avec son schema, son WAL et ses
transactions ; deux programmes qui l'ecrivent, c'est la base de
l'utilisateur qui arbitre.

Hermes OS ne revendique que la troisieme ligne. Tracer sa propre demande
dans son propre journal n'est pas posseder l'etat de l'agent — c'est
repondre de ses actes, ce qu'aucune autre couche ne peut faire a sa place.
Ne rien tracer laisserait une ecriture reelle sans trace cote OS, seule
ecriture du depot que le journal ignorerait.

Deux gardes structurelles le tiennent : aucun module Hermes OS n'ouvre
`state.db`, et `hermes_home` ne sert qu'a poser un `cwd` et un
environnement, jamais a ecrire.

### Une mutation reelle, et pourquoi celle-la

`session.branch` ecrit vraiment :

    state.db avant   c4c41511df13983c
    session.branch   -> cle 20260909_071909_89f792, parent 20260906_075837_a9239a
    state.db apres   0537fc9dd00a2370          CHANGE
    processus neuf   -> la session est retrouvee

Elle est **additive** : le parent reste intact. C'est ce qui la rend
integrable maintenant, alors qu'une mutation destructive demanderait une
autre conversation — reprise, confirmation, tracabilite du contenu perdu.
`MUTATIONS_CONNUES` n'en porte donc aucune, et un test l'interdit.

Brancher exige une session vivante (`session.branch` est `live=True`), d'ou
l'enchainement : on demande d'abord l'activation, puis la branche. Les deux
gestes appartiennent a l'agent ; Hermes OS ne fait que les demander dans
l'ordre — et la branche porte le **handle runtime**, jamais la cle stockee.

### Le fork existait, sous un autre nom

HOS-265 avait conclu « `session.fork` absent, donc pas de fork ». C'etait
vrai du nom et faux de la capacite : le fork s'appelle `session.branch`. La
negociation disait vrai sur ce qu'elle mesurait ; c'est la **liste des noms
a sonder** qui etait fausse, et une liste ecrite de memoire ne vaut pas
mieux qu'une specification lue de memoire. Corrige : `fork` passe
d'ABSENTE a COMPLETE, 16 surfaces sur 18.

### Un chiffre exact qui mentait, corrige

HOS-266 affichait « 100 servis sur 200 ». Or `session.list` **plafonne a
200 cote gateway** : 200 etait le plafond, pas un decompte, et se lisait
comme un total. On demande desormais une page de plus que ce qu'on affiche —
ce que le runtime rend en trop prouve qu'il en reste — et l'interface dit
« 100 affichees, et il en reste ». C'est tout ce qu'on peut honnetement
dire.

Cette correction a rendu deux tests de HOS-266 rouges : ils affirmaient le
contrat qu'elle remplace. Reecrits sur la nouvelle propriete, plus stricte —
l'un d'eux interdisait **tout** parametre, ce qui a cesse d'etre tenable
des qu'une pagination honnete a exige un `limit` ; il nomme desormais ce
qui est permis plutot que d'interdire une forme.

### Preuve de bout en bout

Clic reel dans le cockpit, Cerveau · Sessions, bouton « Brancher » :

    state.db avant   12993fe87e7e73af
    clic             -> « Branche creee : ... (20260909_072434_48f2b3)
                        — 2 message(s) repris du parent 20260906_082256_56a2a0 »
    state.db apres   912543614484295e          CHANGE
    processus neuf   -> session retrouvee, titre et compteur exacts

La branche apparait dans la liste sans rechargement. Un refus du runtime
revient en `200` avec `applique: false` et sa raison — un refus est un
resultat, pas une panne, et l'interface les distingue.

Dix mutations, dix rouges. Deux ont dû etre reecrites parce qu'elles ne
creaient pas le defaut qu'elles pretendaient creer : l'une remplacait la
gestion d'erreur de la branche alors qu'aucun test n'atteignait ce chemin —
tous etaient refuses des l'activation, et le trou de couverture etait reel ;
l'autre renommait la methode cliente sans retirer l'URL, que la regle
anti-orphelin cherche. Un mutant qui ne cree pas le defaut ne mesure pas le
garde-fou.

### Ce qui reste PLANNED, et pourquoi

Activer un toolset et creer un Bot ecrivent aussi dans l'etat de l'agent, et
le contrat les couvre desormais — il suffirait de les declarer. Elles ne le
sont pas parce qu'aucune interface ne les demande encore, et qu'une entree
dans `MUTATIONS_CONNUES` sans appelant serait l'orphelin que HOS-265
interdit. Le contrat est pose ; l'extension est un geste, pas un chantier.

Les mutations destructives — supprimer une session, reinitialiser un profil —
restent hors contrat tant que la question de la reprise n'est pas tranchee.

## HOS-266 — Le pont demande, et cinq surfaces atteignent le cockpit (2026-09-09)

HOS-265 avait pose le pont et sa regle anti-orphelin, puis conclu : dix-sept
surfaces « negociees et visibles, ce qui n'est pas integre ». Cette passe en
integre cinq, de bout en bout.

### Ce qui manquait au pont

Il savait **negocier** — dire ce que le runtime peut faire — et rien
d'autre. Il ouvrait un gateway, posait ses questions, le tuait. Six
secondes par question, et aucune session ne survivait : ni steer, ni
approbation, ni evenement pendant le tour.

Les capacites etaient donc visibles et **inertes**. Le cockpit affichait
« sessions : complete » sans pouvoir montrer une seule session — exactement
la demi-promesse que la regle anti-orphelin sanctionne, un cran avant
l'orphelin franc.

`_Connexion` garde le processus ouvert, correle les reponses par
identifiant, et met les evenements de cote dans une file bornee a 500 —
un flux, pas un journal ; le Run Ledger reste la seule memoire durable. Le
temoin de flux y est pose comme dans l'adaptateur, puisque ce processus-ci
est un agent.

### Cinq surfaces, mesurees avant d'etre dessinees

Les charges utiles ont ete relevees sur le vrai gateway **avant** d'ecrire
une ligne d'interface :

    session.list        200 sessions   id, titre, apercu, date, messages, source
    tools.list           62 toolsets   nom, description, tool_count, enabled
    profiles.list         1 profil     modele, fournisseur, skills, defaut
    delegation.status     —            actifs, en pause, profondeur, enfants
    cron.manage           0 routine    —

`backend/services/vue_agent.py` en fait des surfaces produit. C'est une
**vue** : une garde sur l'arbre syntaxique lui interdit d'ecrire, comme
`vue_operations` en porte une depuis HOS-235.

Une seule route, `/bridge/agent`, sert les cinq. Le gateway coute six
secondes a froid et le pont n'en garde qu'un : cinq routes frontend
l'auraient rouvert cinq fois.

### Deux facons de mentir, ecartees

**Une panne n'est pas un vide.** `disponible` porte la difference, comme
`negociee` la porte pour la negociation. Sans elle, un gateway injoignable
se lirait « aucune session » — faux et rassurant, la pire combinaison.

**Un chiffre exact peut mentir.** Le runtime sert 200 sessions, le cockpit
en montre 100 : il affiche « 100 servis sur 200 », jamais « 100 ». Et une
borne de delegation absente reste `None`, pas `0` — `0` dirait « aucune
delegation permise », ce qui est une affirmation.

### Lecture seule, et c'est une decision

Reprendre une session, activer un toolset, creer un Bot : ces gestes
ecrivent dans l'etat de l'agent. Les poser demanderait de trancher d'abord
qui, de Hermes OS ou de l'agent, en est autorite — la question meme que la
regle qui prime sur tout rend delicate. Tant qu'elle n'est pas ecrite, un
bouton qui pretendrait le faire serait un bouton sans backend.

`skills.manage` et `cron.manage` savent aussi ecrire selon l'action passee.
La vue ne leur transmet **aucun** parametre, et un test le garde : un futur
`action` devra etre un geste delibere, pas un oubli.

### Preuve

Center « Cerveau », cinq onglets, verifie au navigateur :

- **Sessions** — « 100 servis sur 200 », et les sessions reelles y sont,
  dont les sondages de HOS-264 (`Create AGENTIC_PROBE.md with probe ok #27`) ;
- **Outils** — « 8 actifs sur 63 » : `coding` actif avec 31 outils,
  `delegation` et `file` actifs, le reste inactif. C'est la distinction qui
  compte, un toolset present et desactive n'etant pas un outil disponible ;
- **Delegation** — 0 actif, profondeur max 1, enfants max 10, et la note
  que `subagent.start` n'existe pas dans ce runtime ;
- **Bots** et **Routines** servent leurs donnees reelles.

Six mutations, six rouges — dont « le frontend cesse d'appeler la vue »,
qui fait rougir la regle anti-orphelin, et « la vue d'ensemble demande deux
fois la meme surface ».

### Ce qui reste PLANNED

Chat et streaming, fork, memory, approvals, MCP, browser, l'auto-
apprentissage des skills. Le chat exige de tenir une session vivante et de
relayer les evenements jusqu'au navigateur : `_Connexion` en pose la
moitie — les evenements sont deja collectes — et rien ne les transporte
encore. `fork` et `memory` n'ont toujours aucune methode amont.

## HOS-265 — Un pont qui negocie, et une regle qui interdit l'orphelin (2026-09-07)

Migration de Hermes Agent v0.20.0 vers v0.21.0, etablissement du pont
unique Hermes OS <-> Hermes Agent, et la regle qui empeche cette passe —
comme toutes les suivantes — de livrer du backend que personne n'appelle.

### La migration

Installe : v0.20.0, checkout `fa83af3f9a`, 2026-08-13. Cible demandee :
« v0.21.0 ». **Ce tag n'existe pas** : l'amont etiquette en CalVer
(`v2026.8.31`) et ne publie aucun tag semver. C'est `origin/main` qui
declare `version = "0.21.0"`, et le commit de release `29112bef09
chore: release v0.21.0 (2026.8.31)` y est bien contenu.

Avance rapide propre — 0 commit local, 31 918 commits de retard — vers
`693641aa8b`. L'etat persistant vit **hors** du checkout, dans
`%LOCALAPPDATA%\hermes` : 63 sessions, 559 fichiers de skills, 4 memoires,
5 taches cron, 11 plugins, 18 instantanes, 30 fichiers de telemetrie.
Compte avant / apres : identique, ligne pour ligne. `config.yaml` sauvegarde
en `.avant-HOS-265` selon la convention du depot.

Dependances resynchronisees avec l'interpreteur **de l'agent**, jamais
`.venv` — c'est la frontiere de HOS-103, et `hermes update` est precisement
ce qu'il ne faut pas lancer ici. Trois paquets ajoutes
(`firecrawl-anydoc`, `snowballstemmer`, `nemo-relay` 0.7.2 -> 0.8.4).

Regression mesuree plutot que supposee : suite complete de Hermes OS
**5877 passed, 3 skipped** avant comme apres — identique. Et une vraie
tache agentique par le chemin reel apres migration : `lfm2.5-2.6b-125k`,
succes en 47 s, artefact verifie sur le disque.

### Le transport, choisi sur mesure

L'adaptateur existant lance l'agent en **un coup** par tache : un
sous-processus, une requete, une reponse, puis il meurt. Cela suffit a
executer un nœud de mission et a rien d'autre — ni session qui dure, ni
evenement pendant le tour, ni steer, ni approbation.

Le gateway `tui_gateway` parle JSON-RPC sur stdio, emet `gateway.ready` au
demarrage, et vit. C'est le transport retenu. L'API HTTP/SSE reste
disponible mais n'apporte rien ici : la surface web de Hermes OS a deja la
sienne, et en ajouter une seconde ferait deux chemins pour une execution.

### Negocier, parce que supposer a deja coute

Le gateway offre un discriminant net :

    methode.qui.nexiste.pas  ->  error -32601 "unknown method: ..."
    session.status           ->  error  4001  "session not found"

`-32601` prouve une absence. Tout le reste — resultat **ou** erreur
applicative — prouve une presence : une erreur metier signifie que la
methode existe et a examine ses arguments. Confondre les deux rendrait la
moitie du gateway invisible, la plupart des methodes repondant par une
erreur quand on les appelle a vide.

Mesure sur v0.21.0 : **54 methodes presentes, 8 absentes**. Et les absences
comptent autant que les presences. Une lecture de la documentation aurait
suppose les trois suivantes ; elles n'existent pas sous ces noms :

    session.fork      ABSENTE  -> le fork n'a pas de RPC
    memory.*          ABSENTE  -> aucune API memoire cote agent
    subagent.start    ABSENTE  -> un subagent se lance lui-meme

Le pont regroupe ces methodes en 18 surfaces produit et rend **trois**
etats par surface : complete, partielle, absente. `delegation` est
partielle — on peut piloter un subagent, pas en lancer un. La premiere
version de la table omettait `subagent.start`, ce qui affichait
`delegation` complete ; le docstring citait pourtant ce cas exact comme la
raison d'etre du troisieme etat. La table a ete corrigee pour dire ce que
la mesure dit.

Resultat servi au cockpit : **15 surfaces completes sur 18**.

### Le pont n'est pas une autorite

Hermes OS garde Mission, Run Ledger, lignage, verification, Aegis,
workspace, provenance, `ResourceManager`, l'admission VRAM,
`AdaptiveRouter` et le RAL. Le pont rapporte et relaie. Une garde sur
l'**arbre syntaxique** l'interdit de toucher a ces noms.

Sa premiere version cherchait ces noms dans la source entiere et rougissait
sur le docstring du pont — qui les cite precisement pour dire qu'il n'y
touche pas. Septieme garde-fou de cette serie ecrit sur une **forme**
plutot que sur une propriete, et le premier ou la prose declenchait
elle-meme le faux positif.

### Une negociation est une mesure datee

Meme lecon que G-15. Le cache est indexe sur l'**empreinte du runtime**
(version + commit) : mettre l'agent a jour l'invalide tout seul. Le magasin
vit sous `db/`, comme celui des sondes et pour la meme raison — un fichier
pose a la racine d'etat serait efface par la prochaine mise a jour.

Une panne de gateway n'est pas un runtime sans capacite : `negociee` porte
la difference, et une panne n'ecrase jamais une mesure persistee.

### Le troisieme lanceur d'agent, attrape par un garde existant

La suite complete a rougi au premier essai, sur
`test_tout_lancement_d_agent_passe_par_l_adaptateur_surveille` — un garde
pose en HOS-218/A-2 : « la protection ne vaut que tant qu'il n'existe qu'un
endroit ou un agent est lance ».

Il avait raison. Le pont lance le **vrai** gateway avec
`os.environ.copy()`, c'est-a-dire tous les secrets de la machine, et rien
n'examinait sa sortie. C'etait un second lanceur ne sans surveillance,
exactement comme les replis cloud etaient nes sans pare-feu (A-1) — et
cette fois le depot s'en est apercu tout seul.

Le temoin est desormais pose comme dans l'adaptateur, la sortie du gateway
passe par la meme `SurveillanceFlux`, et une fuite **coupe la negociation
immediatement** au lieu de la rendre. Sans cette derniere condition, un
gateway qui recrachait le temoin faisait quand meme attendre les 45 s du
delai — quarante-cinq secondes a laisser tourner un processus dont on
savait deja qu'il exfiltrait.

L'inscription du pont dans la liste des lanceurs autorises est doublee
d'un test de **comportement** : le temoin doit etre reellement pose dans
l'environnement du gateway, et une sortie qui le recrache doit lever. Une
ligne de liste blanche sans cela n'est qu'un tampon.

### La regle anti-orphelin

HOS-235 avait livre huit routes correctes, testees, sur une surface que
rien ne montait : `GET /api/v1/operations` rendait `404`, et leurs tests
passaient parce qu'ils montaient le routeur eux-memes. Le meme motif a
produit les trois defauts les plus couteux du depot.

`test_pas_de_backend_orphelin.py` ferme la porte : toute route `/api/v1`
doit avoir un appelant dans `frontend/src`, ou figurer dans une dette
constatee et gelee. Une route neuve sans appelant fait rougir la suite.

**Mesure du jour : 120 routes sur 306 — 39 pour cent — n'ont aucun
appelant frontend.** Ce n'est pas une norme, c'est une dette qui doit
retrecir.

Le chiffre a ete faux deux fois avant d'etre juste, et les deux fois c'est
l'instrument qui mentait :

- 144, parce que le motif remplacait `{id}` par du vide et fabriquait
  `/agents//pause` — 32 faux orphelins ;
- 112, parce que la fin du motif n'etait pas ancree : `/bridge/capabilities`
  se trouvait a l'interieur de `/bridge/capabilities/refresh`, si bien que
  toute route prefixe d'une autre heritait d'un appelant qu'elle n'avait
  pas. Huit orphelins reels etaient caches ainsi.

Le second n'a pas ete trouve en relisant du code : une **mutation** —
« le frontend cesse d'appeler la route du pont » — est restee verte. Le
harnais a fait ce que la relecture n'avait pas fait.

### La chaine, prouvee de bout en bout

Interaction reelle dans le cockpit, Runtime Center, panneau « Capacites du
cerveau agentique » :

    Hermes Agent -> pont -> GET /api/v1/bridge/capabilities -> bridgeClient
      -> useBridgeCapabilities -> panneau -> clic « Re-negocier »
      -> POST .../refresh -> gateway relance -> mesure persistee

Le panneau affiche `Hermes Agent 0.21.0 · 693641aa8b43`, `15/18 completes`,
et nomme les absences : `fork` absente (manque `session.fork`), `memory`
absente, `delegation` partielle (manque `subagent.start`). Le clic a bien
declenche une negociation reelle — horodatage du magasin a 15 s au moment
du controle, contre plusieurs minutes avant.

Dix mutations, dix rouges apres correction de l'ancrage.

### Ce qui reste PLANNED, et pourquoi

Le brief demandait la parite produit sur seize surfaces. Une seule est
demontree de bout en bout. Les autres sont **negociees et visibles**, ce qui
n'est pas la meme chose qu'integrees, et elles restent PLANNED :

- `fork` et `memory` n'ont pas de methode cote agent — rien a raccorder ;
- `delegation` ne sait pas lancer un subagent depuis le pont ;
- chat/streaming, sessions, steering, approvals, tools, skills, learning,
  MCP, cron, profiles, browser sont **presentes** au gateway et n'ont ni
  service, ni client, ni surface produit. Les declarer integrees serait
  exactement ce que la regle anti-orphelin vient interdire.

Le flux d'auto-apprentissage des skills (`run -> proposition -> diff ->
approbation -> Skill persistante`) n'est pas commence. `learning.frames` et
`skills.manage` repondent, ce qui rend le chantier possible ; il n'est pas
fait.

## HOS-264 — La sonde mesurait la convention de chemin, pas le modele (2026-09-06)

G-14. HOS-263 avait deplace le magasin de sondes hors de `%TEMP%` et
conclu : « deplacer le magasin empeche la prochaine perte ; il ne restaure
pas celle-ci. Sonder reellement le catalogue reste a faire. » Cette passe
sonde — et decouvre en le faisant que la sonde ne mesurait pas ce qu'elle
annoncait.

### Le contrat, trace de bout en bout

    sonder_modeles.py -> probe() -> agent reel, tache reelle
                                          |
                                  verdict lu sur le disque
                                          |
                                    save_result() -> db/agentic_probe_results.json
                                          |
                                 measured_success_for()  >= 2 essais, >= 60 %
                                          |
                                  _agentic_capable_for()  (bootstrap)
                                          |
                                   _agentic_model() -> modele engage

Le protocole existait deja, entier : `scripts/sonder_modeles.py` (HOS-142),
un modele a la fois sous verrou exclusif, trois essais par defaut,
persistance a chaque essai. G-14 n'etait pas un outil manquant mais un
magasin vide.

**Ce que `False` veut dire, precisement.** Trois producteurs, et ils ne
disent pas la meme chose : l'exception d'acces a Ollama rend `None`
(« on ne sait pas ») ; `agentic_disqualifie` rend `False` (preuve negative
structurelle — pas de chat, pas d'outils, sous le plancher de parametres,
debordement CPU, contexte servi trop court) ; sinon le verdict mesure passe
tel quel, `True`, `False` ou `None`. Le predicat fusionne les deux premiers
sens de `False` — disqualifie et mesure-incapable — ce qui est sans effet
sur la politique, les deux etant des preuves negatives, et un test garde que
le disqualifieur prime sur une mesure positive.

### Le faux echec

Premier essai reel, reponse brute conservee — `lfm2.5-2.6b-125k` :

    write  /home/user/AGENTIC_PROBE.md      [Failed to write file: mkdir...]
    write  /c/Users/emeri/AGENTIC_PROBE.md  0.9s
    read   AGENTIC_PROBE.md
    "The file has been created successfully."    8 messages, 6 tool calls

Six appels d'outils, le bon contenu, un fichier reellement ecrit. Verdict
enregistre : **echec** — parce que la sonde regardait dans son workspace
temporaire, et que le modele avait ecrit dans le repertoire personnel.

La consigne disait « Create a file named AGENTIC_PROBE.md **in your working
directory** ». Le sous-processus recoit bien le workspace en `cwd`, mais
rien ne le **dit** au modele, qui devine — d'abord une convention Linux,
puis le repertoire personnel. La sonde mesurait donc « ce modele devine-t-il
la convention de chemin de cette machine », pas « ce modele sait-il piloter
une boucle d'outils ».

Ce n'est pas une severite qu'on assume : la **production** nomme le
repertoire. `_build_messages` donne a Hermes Agent, mot pour mot :

    Your working directory is '<racine>' and you have real filesystem
    access to it. Inspect before you write: do not guess paths.

La sonde etait donc plus severe que le chemin qu'elle pretend mesurer. Une
sonde plus severe que la production mesure la sonde. La consigne reprend
desormais cette phrase, verbatim, et un test lie les deux formulations : si
l'une derive, il rougit.

**Rien n'est affaibli.** Le verdict se lit toujours sur le disque, a
l'endroit nomme. Mesure de controle : consigne bavarde qui raconte un succes
sans rien ecrire — echec, comme avant. Un narrateur ne produit toujours
aucun fichier.

Meme modele, meme verification disque, chemin nomme : succes en 43 s contre
un echec en 52 s. C'est le sixieme defaut de mesure du catalogue, et le
sixieme a produire un **faux echec**.

### La campagne

Dix-huit essais reels, six modeles, un a la fois sous verrou exclusif :

    modele                essais   verdict   duree/essai
    gpt-oss-20b-64k        3/3      True       45-64 s
    qwen3.6-35b-128k       3/3      True       61-83 s
    ornith-9b-256k         3/3      True       44-54 s
    muse-glimmer-64k       3/3      True      159-257 s
    gemma4-12b-256k        3/3      True       84-85 s
    lfm2.5-2.6b-125k       2/3      True       31-38 s

Le seul echec des dix-huit appartient au **repli** — celui que la regle
d'avant T-29 tenait pour « connu-bon ». Les durees de muse-glimmer, quatre a
cinq fois celles des autres, sont la signature du debordement que
`CLAUDE.md` decrit pour un dense de 27,9 Md sur 16 Go.

Ces chiffres ne contredisent pas HOS-096, qui notait `gemma4:12b` a 0/3 : ce
tag n'existe plus, et surtout la mesure d'alors a ete prise avec la consigne
qui faisait deviner le chemin. Les verdicts d'origine ayant ete effaces avec
`%TEMP%`, la comparaison est impossible — on ne peut pas savoir combien de
ces 0/3 etaient des faux echecs. C'est peut-etre ainsi que le repli est
devenu le seul « connu-bon » : il etait le plus petit, donc le plus enclin a
repondre vite, pas necessairement le plus capable.

### Une preuve asymetrique fabrique la pathologie qu'elle devait fermer

Mesure intermediaire, quatre modeles sondes sur six :

    muse-glimmer-64k  ->  lfm2.5-2.6b-125k   SUBSTITUE
    gemma4-12b-256k   ->  lfm2.5-2.6b-125k   SUBSTITUE

La politique T-29 est intacte et se comporte comme ecrit — « non prouve +
repli prouve capable -> substitue » — mais rendre le repli prouve **avant**
les autres remet un 2,7 Md a la place d'un 27,9 Md. La regle n'est pas en
cause : c'est l'ensemble de preuves qui etait asymetrique. La correction
n'est donc pas de changer la politique, c'est de finir de sonder. Apres les
six : les deux substitutions disparaissent, et les cinq decisions du routeur
survivent toujours.

C'est la raison mesuree pour laquelle le catalogue a ete sonde en entier
plutot qu'en partie.

### Le maillon qui restait ouvert entre le disque et le predicat

`_agentic_capable_for` est `lru_cache`e sur le seul nom du modele — « the
answer only changes when the model itself is replaced ». C'etait vrai tant
que rien n'ecrivait de verdict. Ca ne l'est plus : un backend deja lance
servait `None` jusqu'a son redemarrage, et la preuve persistante n'atteignait
jamais le predicat. La cle porte desormais l'empreinte du magasin —
`st_mtime_ns` et taille, un `stat` par question posee une fois par tache.
Aucune autorite nouvelle, aucun crochet sans appelant.

### Preuves

Chaine complete, mesuree sur le vrai bootstrap, processus neuf : magasin ->
`measured_success_for` -> predicat -> `_agentic_model`, **6 modeles sur 6
prouves capables et conserves**, 5 decisions de routeur sur 5 maintenues.
Survie au redemarrage prouvee par deux interpreteurs distincts, l'un
ecrivant, l'autre lisant.

Dix mutations, dix rouges. La premiere version de l'une d'elles est restee
verte et ne prouvait rien : elle rendait une cle absente du magasin, donc
n'introduisait aucun heritage. Reecrite pour reproduire le defaut historique
— un frere de famille qui herite d'un verdict — elle est rouge, attrapee par
un garde-fou qui existait deja. Une mutation qui ne cree pas le defaut ne
mesure pas le garde-fou : c'est la premiere fois de cette serie que le
mutant, et non le garde-fou, etait en cause.

### Ce qui reste

`qwen3-embedding:0.6b`, seul modele du catalogue non sonde : il est ecarte
par un disqualifieur structurel — un modele d'embedding n'est pas un modele
de chat, quoi qu'il annonce a Ollama — et le sonder mesurerait un refus
connu d'avance.

Un verdict est une mesure **datee**, pas une propriete du modele : changer
le `num_ctx` d'un Modelfile, remplacer des poids sous le meme tag ou mettre
l'agent a jour peut l'invalider sans que rien ne le dise. Consigne **G-15**.

## HOS-263 — Un repli ne defait une decision que s'il est mieux prouve (2026-09-06)

T-29 / G-12. §6.1 (HOS-262) avait rendu le routage juste ; `_agentic_model`
annulait ensuite **la totalite** de ses decisions — mesure, **0 sur 5**
survivait au chemin agentique, qui est le chemin normal d'une mission liee
a un workspace.

### La premisse fausse

La regle disait : « substituer un repli **connu-bon** a tout modele non
prouve ». Mesure sur les six modeles du catalogue, en interrogeant le
prédicat reel du bootstrap :

    modele                chat  tools  params  offload  ctx servi  mesure
    gpt-oss-20b-64k       True  True    20.9    None     None      None
    qwen3.6-35b-128k      True  True    34.7    None     None      None
    ornith-9b-256k        True  True     9.0    None     None      None
    muse-glimmer-64k      True  True    27.9    None     None      None
    gemma4-12b-256k       True  True    11.9    None     None      None
    lfm2.5-2.6b-125k      True  True     2.7    None     None      None

**Aucun n'est disqualifie** : tous passent chat, outils, parametres,
debordement et contexte servi. Ils sont simplement **non sondes** — et le
repli `lfm2.5-2.6b-125k` l'est autant que les autres.

La substitution echangeait donc un inconnu contre un autre inconnu, en
jetant le seul signal mesure du systeme : la note par type de tache du
routeur. Le repli est de surcroit le plus faible du catalogue sur ces
memes notes — 0,28 en code contre 1,00 pour `gpt-oss`.

### Ou la decision devenait non contraignante

    task → TaskType → AdaptiveRouter → modele choisi
                                          ↓
                                    _agentic_model()   ← ici
                                          ↓
                          admission ResourceManager → RAL → execution

`_agentic_model` est le seul point du chemin ou la decision pouvait etre
defaite, et il le faisait sur une absence de preuve.

### La correction

`ModelProfile.agentic_capable` rend un booleen et ecrasait la difference
entre « mesure incapable » et « jamais mesure ». Les disqualifieurs
structurels sont extraits dans `agentic_disqualifie` — sans changer le
resultat d'`agentic_capable` — et le predicat du bootstrap rend desormais
les **trois** etats : `False` quand un controle ecarte, sinon le verdict
mesure (`True`, `False` ou `None`).

La regle devient :

    modele choisi     repli            decision
    prouve capable    n'importe quoi   conserve
    prouve incapable  prouve capable   substitue   (le cas legitime)
    prouve incapable  non prouve       substitue   (le choix est exclu)
    non prouve        prouve capable   substitue   (la preuve l'emporte)
    non prouve        non prouve       **conserve** — c'etait G-12

La derniere ligne est toute la correction : echanger un inconnu contre un
autre inconnu ne reduit aucun risque.

**Rien n'affaiblit HOS-096.** Un modele non sonde reste *non prouve* et le
demeure ; `ModelProfile.agentic_capable` rend toujours `False` pour lui, et
un test le garde. Ce qui change est ce qu'on en fait quand l'autre option
ne vaut pas mieux.

Aucune autorite nouvelle : `AdaptiveRouter` reste seul a choisir sur le
chemin Mission, `ResourceManager` seul a admettre, le RAL seul a router le
fournisseur. `_agentic_model` ne rend toujours que deux choses — ce qu'on
lui a donne, ou le repli configure — et un test l'interdit d'en choisir une
troisieme.

### Preuve sur le chemin reel

    tache                            routeur              engage
    ecrire les tests unitaires       gpt-oss-20b-64k      gpt-oss-20b-64k
    analyser la faille de securite   qwen3.6-35b-128k     qwen3.6-35b-128k
    resumer ce document              ornith-9b-256k       ornith-9b-256k
    concevoir l'architecture         qwen3.6-35b-128k     qwen3.6-35b-128k
    classer ces tickets              ornith-9b-256k       ornith-9b-256k

**5 sur 5**, contre 0 sur 5 avant. Trois modeles distincts pour cinq types
de tache : la decision de §6.1 atteint enfin l'execution.

La conservation est journalisee au meme titre que la substitution — « on a
conserve la decision » est un fait d'execution autant que « on l'a
defaite », et c'etait celui qui manquait.

### Trois mutations qui restaient vertes, et pourquoi

Sur dix, trois ne faisaient rougir aucun test — les trois portant sur le
**predicat**, et mes gardes y etaient syntaxiques :

- « le predicat rend a nouveau un booleen » — le test cherchait `return
  None` parmi les retours de la fonction. Le `return None` du gestionnaire
  d'exception satisfaisait l'assertion a lui seul ;
- « un disqualifieur devient non prouve » — le test verifiait
  `ModelProfile`, une couche **en dessous** de ce qui decide ;
- « un modele non prouve devient capable » — rien ne le testait.

Les trois sont reecrits sur le comportement du vrai predicat, Ollama et la
sonde remplaces. Et il a fallu, en plus, donner un identifiant neuf a
chaque cas : `_agentic_capable_for` est `lru_cache`e, et trois tests
passaient au vert sur une valeur memoisee par le premier.

C'est le sixieme garde-fou de cette serie de passes dont une mutation
revele qu'il ne gardait pas ce qu'on croyait, et toujours pour la meme
raison : une assertion ecrite sur une **forme** plutot que sur une
propriete.

### La cause racine, trouvee en poursuivant un test qui refusait de passer

Le garde-fou `test_agentic_model_floor` est devenu rouge, et sa docstring
disait pourquoi : « the fallback itself comes from **measured probe
data** (HOS-095) ». Ma correction supposait le contraire.

Mesure : le magasin de sondes vit dans
`%TEMP%/agentic_probe_results.json`, **et le fichier n'existe plus**.
`_probe_store_path` lisait `getattr(settings, "data_dir", None) or
tempfile.gettempdir()` — or `Settings` n'a **jamais** eu d'attribut
`data_dir`. La branche etait morte ; le magasin atterrissait toujours dans
le repertoire temporaire du systeme, que Windows vide.

Tous les verdicts que ce projet a mesures ont donc disparu : `lfm2.5-2.6b`
a 3/3, `gemma4:12b` a 0/3, `devstral` a 1/3 — les chiffres memes sur
lesquels le repli agentique avait ete choisi. C'est **la** cause de G-12 :
la regle etait juste quand elle a ete ecrite, et sa premisse s'est effacee
sans que rien ne le dise.

Le magasin va desormais la ou va le reste de l'etat durable — la racine de
`backend/core/etat.py`, celle de la base, des instantanes et de la
memoire, qui honore `HERMES_DATA_DIR`. Une mesure qui coute des minutes
par modele, prise sous verrou exclusif, ne se range pas dans un repertoire
que le systeme efface.

Sous `db/`, et non a la racine de cet etat : un garde-fou de HOS-232 l'a
dit des le premier essai, en lisant le code plutot qu'une liste.
`preserve_set()` enumere des **dossiers**, et un fichier pose directement
a la racine n'y serait pas — une mise a jour l'aurait efface, ce qui
aurait refabrique exactement la perte que ce deplacement corrige. Le
defaut se serait reproduit un cran plus loin, avec un an de moins pour
s'en apercevoir.

Le garde-fou, lui, posait sa premisse dans sa docstring sans l'etablir
dans son montage : `capable.get` rendait `None` pour le repli. Le montage
l'etablit desormais, le plancher est inchange sous cette premisse, et un
cas s'ajoute — celui ou plus rien n'est prouve.

### Ce qui reste vrai, et ce qui ne l'est pas

Que les modeles du catalogue sachent piloter la boucle d'outils n'est
**pas** demontre — cette passe ne le pretend pas. Sonder reellement le
catalogue (`agentic_probe.py`, trois essais minimum, un modele a la fois)
reste le seul moyen de trancher, et c'est hors perimetre. Consigne
**G-14** : tant que la sonde n'a rien mesure, le systeme applique une
decision fondee sur la note metier et non sur une capacite agentique
verifiee. Deplacer le magasin empeche la prochaine perte ; il ne restaure
pas celle-ci.

## HOS-262 — Le type de tache decide enfin du modele (2026-09-05)

§6.1. Le routeur classait juste et n'etait jamais ecoute : un filtre place
apres lui eliminait tous les modeles competents.

### Mesure, catalogue reel, cinq types de tache

`AdaptiveRouter` est l'autorite de selection du chemin mission. Ses
profils portent des notes **par type de tache**, versees depuis le magasin
de mesures (HOS-144) et fortement discriminantes :

    gpt-oss-20b-64k      code_generation 1.00
    lfm2.5-2.6b-125k     code_generation 0.28

Il recommandait pourtant `lfm2.5-2.6b-125k` — le plus petit modele du
catalogue, 2,7 Md — pour **les cinq** taches essayees, y compris
« analyser la faille de securite » et « concevoir l'architecture ». Motif
rendu : « Low VRAM footprint ».

### La cause : une troisieme estimation de capacite

Ni le classement ni les notes. `rank_models` filtre sur
`predict_vram_usage`, qui multipliait l'empreinte **mesuree** par
`task.complexity + 1.0`, soit 1,3 a 2,0. Et `task.complexity` est le
**nombre de mots du titre de la tache** (`_infer_complexity` : >30 mots
-> 0,8 ; >15 -> 0,5 ; sinon 0,3).

La longueur d'une phrase decidait donc si un modele tenait sur la carte :

    modele                declare   « predit »   plafond   verdict
    gpt-oss-20b-64k        13 342     17 344     15 000    elimine
    qwen3.6-35b-128k       14 008     18 210     15 000    elimine
    muse-glimmer-64k       13 373     17 384     15 000    elimine
    ornith-9b-256k         13 824     17 971     15 000    elimine
    gemma4-12b-256k        12 533     16 292     15 000    elimine
    lfm2.5-2.6b-125k        2 099      2 728     15 000    seul retenu

Le classement etait juste : sans ce filtre, `gpt-oss` sort a 0,672 contre
0,434 — l'ecart de 0,238 vient de son `task_score` de 1,00 contre 0,28.

Le motif « Low VRAM footprint » **attribuait mal la cause** : le modele
n'avait pas ete choisi pour sa sobriete, les autres avaient ete elimines.

### Pourquoi le multiplicateur etait faux, mesure

Le cache KV est alloue a la taille de la **fenetre**, pas a celle du
prompt. A-18 l'a mesure : 2,02 Gio a `num_ctx` 16384 et 4,33 a 131072 —
c'est le contexte servi qui compte, et il est deja dans le chiffre
declare. R-6 a mesure ce que l'usage y ajoute : entre un cache vide et un
cache rempli de 3 210 jetons, 14,954 -> 15,115 Gio, soit **+1 %**. Le
multiplicateur en inventait jusqu'a +100 %.

C'etait donc une **troisieme** autorite de capacite, apres `ResourceManager`
(R-3) et l'empreinte declaree (A-18) — et c'est elle qui gagnait.

### Apres correction

    tache                                    modele choisi        motif
    ecrire les tests unitaires               gpt-oss-20b-64k      Excellent task fit (100%)
    analyser la faille de securite           qwen3.6-35b-128k     Excellent task fit (100%)
    resumer ce document                      ornith-9b-256k       Excellent task fit (100%)
    concevoir l'architecture                 qwen3.6-35b-128k     Excellent task fit (100%)
    classer ces tickets                      ornith-9b-256k       Excellent task fit (100%)

Le role influence enfin la selection — c'est la question meme de §6.1, et
la reponse etait « non » jusqu'ici.

### Un repli qui ne se voyait pas

`_agentic_model` substitue tout modele non prouve agentique par
`_HERMES_AGENT_FALLBACK_MODEL`. Le magasin de sondes etant vide sur cette
machine, cela vise **la totalite** des decisions : mesure apres
correction, le routeur classe cinq taches sur trois modeles differents, et
**0 sur 5** survit au chemin agentique.

C'est delibere (HOS-096 : un modele non mesure est *non prouve*, pas
capable) et le registre enregistre bien le modele qui a **servi**. Ce qui
manquait est que la substitution se **voie** : le repli de *runtime* etait
trace depuis HOS-242, celui de **modele** ne l'etait pas. Deux cles s'y
ajoutent, `modele_demande` et `substitution`, nommees seulement quand
l'ecart est constate.

Le fait que le repli soit lui-meme le modele le plus faible du catalogue —
0,28 sur le code — et lui aussi non prouve, est consigne en **G-12**, non
corrige : le trancher demande de decider si un modele non sonde peut
piloter la boucle, ce qui est une question de §7.

### A-19 ferme en chemin, parce que cette passe le faisait sortir

Mesure dans le meme arbre, la meme base : `test_au_dela_la_plus_ancienne_
terminee_quitte_le_cache` echouait **0 fois sur 20** avant les
modifications de §6.1 et **5 fois sur 20** apres — non parce que §6.1
touche aux missions, mais parce qu'a cette echelle un changement d'octets
ailleurs suffit a deplacer un tirage.

Cause : `MagasinMissions` ordonnait sur `cree_le` seul. L'horloge de
Windows a une granularite d'environ 15,6 ms — cinq missions enregistrees
d'affilee portent le **meme** horodatage, et SQLite les rend alors dans un
ordre qu'il ne garantit pas. Or `_RegistreMissions` documente un FIFO
(« Ordonne par insertion ») et son `__len__` hydrate le cache depuis ces
requetes.

`ORDER BY cree_le DESC, rowid DESC` — `rowid` est l'ordre d'insertion et
il est unique. Le contrat annonce devient vrai au lieu d'etre probable.
25 executions, 25 vertes. Deux tests pinnent desormais l'ordre a
horodatage egal.

### Les mutations

Dix, dix rouges. La premiere version de l'une d'elles restait verte :
« la substitution n'est plus publiee » vidait la **valeur** en gardant la
**cle**, et le test cherchait la cle parmi les chaines de la fonction. Une
cle presente et vide ne trace rien. Reecrit sur le comportement — un
`execute` reel, et la valeur relue dans les metadonnees.

C'est le cinquieme garde-fou de cette serie de passes dont une mutation
revele qu'il ne gardait pas ce qu'on croyait, et toujours pour la meme
raison : une assertion ecrite sur une **forme** plutot que sur une
propriete.

### Ce qui n'est pas ferme

`_get_records_for_task` rend `[]` en dur : la fiabilite vaut 0,5 pour
tous les modeles et les mesures d'execution n'entrent jamais dans le
classement. De meme, `_compute_speed_score` rend 0,000 pour les six
profils. Deux dimensions sur cinq de `compute_model_score` sont donc
inertes. Consigne **G-13**, non corrige : les brancher change la
ponderation et demande sa propre mesure.

## HOS-261 — Une empreinte n'est pas une propriete du modele (2026-09-05)

A-18, trouve en fermant R-6. Le rapport notait « l'empreinte declaree du
role `swift` est 2,1x trop basse » et laissait la question ouverte. Elle
ne l'etait pas tout a fait : la mesure de R-6 et la valeur declaree ne
portaient pas sur la meme chose.

### Ce que la mesure de R-6 comparait sans le savoir

`config/models.yaml` declare `swift: vram_gb 2.05` avec le commentaire
« measured at this num_ctx » et `num_ctx: 16384`. La sonde de R-6 avait
charge le tag **sans** passer d'options, donc au `PARAMETER num_ctx
131072` de son Modelfile. Deux fenetres, deux caches KV, deux empreintes.

Remesure au compteur canonique (A-15), carte videe entre chaque, meme
tag, residence confirmee par `/api/ps` en inventaire seulement :

    num_ctx  16384 -> 2,02 Gio      (context_length: 16384)
    num_ctx 131072 -> 4,33 Gio      (context_length: 128000)

La valeur declaree est donc **juste a son contexte**. Ce n'etait pas une
valeur obsolete.

### Le vrai defaut, qui est ailleurs

`_vram_gb_for` est indexe par **tag**, jamais par role. Il ne sait pas
quel contexte sera servi — et le harnais de Hermes Agent passe par `/v1`,
**qui ne transporte pas `num_ctx`** (c'est le sujet meme de
`backend/runtime/context_guard.py` : « Nothing in the request can override
it »). Sur ce chemin, Ollama applique le Modelfile : 131072.

Reserver 2,05 Gio pour une charge de 4,33 — l'ecart de couverture est de
2,28 Gio par tache. Demontre sur cas controles :

    carte a  8,00 Gio : 2 reservations accordees -> 16,66 Gio -> deborde de 0,68
    carte a 10,00 Gio : 2 reservations accordees -> 18,66 Gio -> deborde de 2,68

Le plafond de 90 % de la politique protegeait le chiffre **declare**, pas
le chiffre **servi**.

Aggravant, et c'est ce qui rend le defaut atteignable au quotidien :
`_HERMES_AGENT_FALLBACK_MODEL` **est** ce tag, et `_agentic_model`
substitue vers lui tout modele non prouve agentique — mesure sur cette
machine, `agentic_capable` est faux pour les quatre tags interroges, donc
toute tache agentique y atterrit.

### L'audit de la table entiere

Douze roles, sept tags. Le contexte declare par le role a ete compare a
celui que le Modelfile du tag sert reellement :

    role                 tag                    vram_gb  ctx role  ctx tag  ratio
    advanced_analysis    qwen3.6-35b-128k        13.68    131072   131072    1.0x
    code                 gpt-oss-20b-64k         13.03     65536    65536    1.0x
    code_agentic         gpt-oss-20b-64k         13.03     65536    65536    1.0x
    orchestrator         gpt-oss-20b-64k         13.03     65536    65536    1.0x
    reasoning            qwen3.6-35b-128k        13.68    131072   131072    1.0x
    reasoning_escalation muse-glimmer-64k        13.06     65536    65536    1.0x
    security             qwen3.6-35b-128k        13.68    131072   131072    1.0x
    standard             ornith-9b-256k          13.50    262144   262144    1.0x
    vision               gemma4-12b-256k         12.24    262144   262144    1.0x
    swift                lfm2.5-2.6b-125k         2.05     16384   131072    8.0x
    double_check         lfm2.5-2.6b-125k         2.05     16384   131072    8.0x

Un seul tag, deux roles. C'est aussi pourquoi `vision` tombait juste dans
la mesure de R-6 et `swift` non : les deux etaient homogenes pour l'un,
pas pour l'autre.

### Consequence sur R-3 : aucune, et c'est demontre

R-3 derive sa capacite du **maximum** des roles — 13,68 Gio,
`qwen3.6-35b-128k`, dont le contexte declare et le contexte servi
coincident. Le seul role sous-declare l'est tres en dessous de ce maximum
(2,05 -> 4,33), et la correction ne le deplace pas :
`_empreinte_de_tache_octets()` vaut 13,68 Gio avant comme apres.

R-3 n'etait donc pas fausse. L'exposition etait dans la **reservation**,
pas dans la capacite derivee — et il fallait le mesurer pour le savoir
plutot que de le supposer dans un sens ou dans l'autre.

### La correction, et la premiere version qui etait fausse

**Premiere tentative : ecraser `vram_gb` avec le pire cas.** Elle a fait
rougir `test_recommend_with_vram_constraint`, et le test avait raison. Le
**routeur** demande « quel modele tient dans ce budget », en sachant qu'il
le servira au `num_ctx` du role : pour lui, 2,05 est la bonne reponse.
Porter 4,33 dans ce champ faisait echouer toute recommandation sous
4,33 Gio et privait le catalogue de son seul modele leger.

Deux consommateurs posent deux questions differentes, et un seul chiffre
ne peut pas repondre aux deux. D'ou deux champs :

    vram_gb      2.05   ce que ce **role** coute a son propre num_ctx
                        -> ce que le **routeur** lit
    vram_gb_max  4.33   le pire cas que ce **tag** puisse servir,
        vram_gb_max_num_ctx: 131072
                        -> ce que l'**admission** retient

`vram_gb_max` est absent partout ailleurs : les neuf autres roles ont un
`num_ctx` egal a celui de leur Modelfile, et les deux chiffres y
coincident.

On retient parfois plus que necessaire sur la route native ; on ne retient
jamais moins que ce qui se charge. Meme prudence que §6.2 et A-15.

Et la table d'empreintes prend le **maximum** des roles qui partagent un
tag, plus le dernier lu : deux roles peuvent declarer le meme tag avec
deux chiffres, et l'ordre du dictionnaire decidait alors lequel servait a
reserver.

Aucune autorite nouvelle : le catalogue fournit une **estimation
declaree**, `ResourceManager` decide, R-6 observe. L'en-tete du fichier
dit maintenant laquelle des trois il est.

### Un rouge qui ne vient pas d'ici

`test_missions_persistantes.py::test_l_eviction_libere_la_memoire_sans_
rien_detruire` echoue lance seul — et il echoue **4 fois sur 4 au commit
`4d1798a`**, verifie dans un worktree. Il passe dans l'ordre de la suite
complete, avant comme apres. C'est le mecanisme de **A-19** rencontre sur
un second test : `_RegistreMissions` hydrate son cache depuis le magasin
durable et l'etat depend de ce qui a tourne avant. Hors perimetre, et
consigne comme seconde occurrence de A-19 plutot que comme un defaut
nouveau — la cause est la meme.

### Trois mutations qui restaient vertes

Sur douze, trois ne faisaient rougir aucun test, et chacune designait une
faiblesse de mes tests :

- « l'empreinte devient une constante 13.68 » — le test comparait la
  derivation au meme fichier, donc une constante figee a la valeur du jour
  y passait. Reecrit : on change le catalogue et on exige que le resultat
  bouge.
- « la table prend le dernier lu » — la garde cherchait `"max("` et
  `"_vram_by_model.get("` dans le **texte** de la fonction, et les deux
  chaines y existent ailleurs. C'est le meme motif que les gardes mortes
  de §6.2 et A-15 : une assertion ecrite sur une sous-chaine. Reecrit sur
  le comportement de la vraie fabrique — atteinte en construisant
  `_make_task_executor` avec un conteneur a deux methodes, ce qui rend
  `_vram_gb_for` testable au lieu d'etre une fermeture inatteignable. Il a
  fallu, en plus, ordonner le catalogue de test avec **le plus lourd en
  premier**, sans quoi « le dernier » et « le maximum » rendent la meme
  reponse et le test ne distingue rien.
- « un tag inconnu recoit 0.0 » — le test verifiait un dictionnaire
  reconstruit dans le test, pas la vraie fermeture. Reecrit sur
  `_vram_gb_for`. La difference reste de **contrat** et non de
  comportement — `_admettre_et_reserver` sort sur `if not vram_gb` dans
  les deux cas — et le test le dit.

### Ce qui n'est pas garanti

Que 4,33 Gio soit un pire cas absolu. C'est le pire cas **mesure** pour la
fenetre que le Modelfile sert aujourd'hui. Un Modelfile reecrit plus large
le deplacerait, et rien ne le detecterait automatiquement : le garde-fou
verifie la coherence des donnees declarees, pas la recette du tag. Consigne
**A-20**.

Et neuf des onze roles n'ont qu'un seul point de mesure, a leur contexte
declare. Le test le dit explicitement plutot que de laisser croire que
toute la table a ete remesuree.

## HOS-260 — Ce qu'un run a coute a la machine (2026-09-05)

R-6, le dernier defaut MUST HAVE de l'audit §6.1. Le registre portait les
jetons et le cout monetaire d'un run depuis HOS-221, et rien de physique :
« cette mission a-t-elle sature la carte ? » n'avait pas de reponse
conservee, alors que la telemetrie existait depuis A-15 — elle n'etait
rattachee a aucun run.

### La question qui decide de tout : que sait-on vraiment attribuer ?

La source canonique somme `GPU Process Memory` sur **tous** les
processus, et le modele vit dans le serveur Ollama, qui sert tous les runs
a la fois. Deux runs simultanes partagent le meme processus : aucun
compteur ne dit lequel a pris quoi. Le chemin agentique n'aide pas — le
sous-processus de Hermes Agent ne detient presque pas de VRAM, c'est
Ollama qui la detient pour lui.

**L'attribution exacte est donc impossible ici.** Le systeme ne pretend
pas le contraire : c'est le point de cette passe, plus que les colonnes.

### Quatre grandeurs qui ne se confondent pas

| grandeur | ce que c'est | ou |
|---|---|---|
| capacite | ce que la carte porte au total | `ResourceManager` |
| besoin declare | l'empreinte du modele, `config/models.yaml` | estimation |
| **reservation** | ce que **ce run** a fait retenir | `vram_reservee_octets` |
| **occupation observee** | ce que la **machine** portait | `vram_machine_*` |

Une reservation est une promesse, pas une mesure. Une occupation machine
est une mesure, mais pas celle du run. `exclusif` dit si l'ecart entre le
debut et le pic est attribuable — et sans lui, il ne l'est pas.

### Mesure sur la vraie carte

    run 1, succes                debut 1,148 Gio  pic 8,231 Gio  exclusif=True
    run 2, echec du runtime      debut 8,231 Gio  pic 8,231 Gio  exclusif=True
    runs 3 et 4, en meme temps                    pic 8,231 Gio  exclusif=False

Les deux runs concurrents voient le meme 8,231 Gio et **aucun des deux**
ne se le voit attribuer. C'est tout l'objet de `exclusif`, et c'est la
difference entre une donnee moins precise mais honnete et une donnee
precise et fausse.

### Ou la mesure est prise, et pourquoi seulement la

Deux points : avant l'admission — donc avant que ce run ne pousse quoi que
ce soit — et dans le `finally` d'`execute`, avant la liberation. Aucun fil
de sondage n'est ouvert pour R-6.

Consequence assumee et ecrite dans le nom : `vram_machine_pic_octets` est
le plus haut des relevés **reellement pris**, donc un **minorant** du vrai
pic. Le nommer `vram_peak_bytes` aurait laisse croire l'inverse.

Le releve final est dans le `finally` parce que c'est le seul endroit que
succes, exception, delai depasse, annulation et repli cloud traversent
tous — et un run en echec est justement celui dont on veut savoir ce que
la carte portait. `resources_used` ne convenait pas : `mission_executor`
ne l'ecrit qu'au retour normal, et le chemin `RuntimeUnavailableError`
sort avant.

### Comptabilite passive

`consommation.py` lit `ResourceManager` et ne lui demande rien : ni
`can_allocate`, ni `reserve_resources`, ni `release_resources`. Et
reciproquement, aucun module d'admission n'importe le registre. Deux
gardes structurelles tiennent les deux sens : refermer cette boucle
ferait de la trace une entree de decision, ce que R-6 s'interdit.

### Persistance

Quatre colonnes nullables sur la table `runs` existante, par le mecanisme
additif de HOS-240 — `CREATE TABLE IF NOT EXISTS` ne fait rien sur une
base deja la, et l'`INSERT` nomme d'`ouvrir()` y echouerait : plus aucun
run ne s'ouvrirait. Une correction d'observabilite aurait casse
l'execution ; c'est deja arrive.

`NULL` se lit « non mesure », jamais « zero consomme ». `mesurer()` est
separee de `constater()` pour cette raison precise : `constater` filtre
ses valeurs sur `if v` et ferait disparaitre un `0` octet — une carte au
repos — et un `exclusif=False`, qui est un fait.

L'unite est dans le nom de chaque colonne. « memory » ou « GiB » sans
definition est la maniere habituelle de perdre un facteur 1024 trois mois
plus tard.

### Deux tests a moi qui ne prouvaient pas ce qu'ils annoncaient

**Le test de concurrence etait instable** — rouge une fois sur six,
mesure. Il exigeait que les deux taches se declarent non exclusives ; or
le releve final precede la liberation, et si l'autre a deja libere, une
tache ne voit plus personne et se declare seule — ce qui est exact pour
l'instant ou elle a regarde. Exiger `False` des deux, c'est exiger une
coincidence, pas une propriete. Reecrit avec une barriere **dans** le
`chat` (donc apres l'admission) et des tenues asymetriques : la tache
courte releve forcement pendant que la longue detient sa reservation.
Dix executions, dix vertes.

**Le test d'annulation testait autre chose que son nom.** Il affirmait
qu'une `CancelledError` descend de `BaseException` et n'est retenue que
par le `finally`. Mesure : sur ce chemin, elle ressort d'`execute` en
`RuntimeUnavailableError` — elle est convertie avant. La mutation « plus
de capture sur annulation » ne faisait donc rougir aucun test, parce
qu'il n'y avait rien de distinct a retirer. Le contrat de conversion est
desormais ecrit et verifie, et un second test leve une `KeyboardInterrupt`
— une vraie `BaseException` qui traverse tous les gestionnaires — pour
prouver ce que le `finally` retient et qu'un `except Exception` perdrait.

### Les mutations

Dix, dix rouges : enregistrement supprime (9), mesure prise sur `/api/ps`
(14), gibioctets sous un nom d'octets (13), « non mesure » devenu zero
(1), le run s'attribuant toute la carte (5), persistance supprimee (7),
admission consultant le registre (1), capture retiree sur exception (5),
capture quittant le `finally` pour un `except Exception` (1), seconde
autorite de mesure (1).

### Un defaut trouve par la mesure, laisse ouvert

R-6 a rendu visible ce qu'il devait rendre visible. Carte videe entre
chaque, un modele a la fois :

    modele                 declare   occupation   ratio
    lfm2.5-2.6b-125k      2,05 Gio     4,33 Gio    2,1x
    gemma4-12b-256k      12,24 Gio    12,24 Gio    1,0x

L'empreinte declaree de `config/models.yaml` est exacte pour l'un et
**deux fois trop basse** pour l'autre. C'est la table que R-3 utilise pour
deriver la capacite : si la sous-declaration touche aussi les roles
lourds, `places_disponibles` sur-estime. Deux points ne suffisent pas a
l'affirmer. Consigne **A-18**, non corrige.

### Un second, expose et non cree

Le couple `test_runs_perdus.py` + `test_registre_missions.py` lance a la
main devient rouge avec cette passe et etait vert en `28a7ad7` — verifie
dans un worktree, pas deduit.

Mecanisme trace : `_RegistreMissions.__len__` **hydrate le cache depuis le
magasin durable au milieu du test**, et
`test_au_dela_la_plus_ancienne_terminee_quitte_le_cache` affirme ensuite
le contenu de ce cache. Or les missions ecrites par le test precedent du
meme fichier portent toutes le **meme `created_at` a la microseconde
pres** : leur ordre de relecture est une egalite tranchee par SQLite. Le
test dependait donc d'un ordre que rien ne garantit ; cette passe a
deplace le tirage, elle ne l'a pas cree.

Les commandes du projet restent vertes — `pytest -q` et `pytest -m lent`,
avant comme apres. Le defaut n'apparait que dans un ordre de fichiers
compose a la main. Consigne **A-19**, non corrige : reparer ce test
demande de decider si `__len__` a le droit d'hydrater, ce qui est une
question sur `_RegistreMissions` et non sur R-6.

## HOS-259 — Combien de taches, et qui le sait (2026-09-05)

R-3 et R-4, les deux derniers defauts MUST HAVE de l'audit §6.1 hors R-6.
Meme defaut vu de deux cotes : la concurrence etait decidee sans regarder
la machine, et decidee deux fois.

### R-3 — une constante n'est pas une capacite

`mission_max_parallel_tasks = 2` ne dit pas « la machine porte deux
taches » : il dit « quelqu'un a ecrit 2 ». Mesure : la meme constante
valait pour une carte pleine (0 place reelle) et pour une carte de 48 Gio
(7 places). Elle ne suivait rien.

Avec l'empreinte **relevee** du role `reasoning` — 13,68 Gio,
`config/models.yaml`, la meme table que l'admission utilise deja sous le
nom `_vram_gb_for` — la carte de 15,98 Gio en tient **une**. Le graphe en
lancait deux. §6.2 empechait bien la carte d'etre sur-engagee ; ce qui
restait, mesure, etait ceci :

    t1   4.2 s  REFUSEE : no VRAM admission for 'qwen3.6-35b-128k'
    t2   4.2 s  REFUSEE : no VRAM admission for 'qwen3.6-35b-128k'

Le second noeud occupait un fil, brulait son attente d'admission, puis
echouait. Le degat n'etait pas la VRAM — elle etait protegee — mais des
noeuds echoues pour une raison qui n'a rien a voir avec leur travail.

`GraphExecutor` demande desormais la borne a `ResourceManager`
(`places_disponibles`), a chaque etape, et ne la met pas en cache : une
capacite lue une fois au demarrage serait une constante de plus. Mesure
apres correction, empreinte 13,68 Gio :

    carte 15,98 Gio, 0,0 occupes -> 1 place
    carte 15,98 Gio, 0,9 occupes -> 0 place
    carte 48,00 Gio              -> 3 places
    carte 80,00 Gio              -> 5 places
    occupation non mesuree       -> 0 place   (A-15 traverse)

`places_disponibles` ne refait aucun calcul de capacite : la politique
etant lineaire en octets demandes, elle pose a `can_allocate` la question
« n taches tiennent-elles » en demandant `n x octets`. Une seule verite,
interrogee autrement — et les reservations actives comptent, comme en
§6.2.

**Jamais moins d'une place.** Une capacite nulle ne doit pas figer la
machine : c'est l'admission de `RealTaskExecutor` qui refuse alors la
tache, avec sa raison, la ou la taille reelle du modele est connue. Le
portillon ne refuse rien.

### R-4 — la borne etait celle d'un appel

`execute_step` ouvrait un `ThreadPoolExecutor` par appel. Le conteneur
n'a pourtant qu'**un** `GraphExecutor`. Deux missions concurrentes,
mesure avant correction :

    _max_parallel par mission : 2
    pic de noeuds simultanes  : 4

Quatre noeuds pour une borne de deux, sans qu'aucune ligne ne soit
fausse : chaque mission respectait sa limite, et les limites
s'additionnaient.

Le portillon est porte par l'instance de `GraphExecutor`, donc partage
par toutes les missions. C'est ce partage, et lui seul, qui empeche deux
decisions locales de s'additionner. Il enveloppe **les deux** chemins
d'`execute_step` — le pool et l'execution directe : n'en garder qu'un
laisserait deux missions a un seul noeud chacune tourner cote a cote sans
que rien ne les compte, ce qui est R-4 avec un noeud de moins.

### Ce que le portillon n'est pas

Il ne connait aucune capacite et n'en calcule aucune : la limite lui est
**passee**. Il ne classe pas, ne priorise pas, ne prempte pas, ne
reordonne pas. Il n'autorise rien non plus : le franchir ne donne aucun
droit sur la carte ; la reservation reste seule a en donner (§6.2), et
elle peut refuser apres.

Un ordonnanceur decide *qui* passe et *quand*. Celui-ci decide seulement
*combien a la fois*, sur un chiffre qu'il ne possede pas. Aucune
autorite nouvelle : le RAL choisit, `ResourceManager` sait, le graphe
repartit, `Mission` borne le temps, `QuotaBroker` le fournisseur.

### Un ecart de semantique trouve en chemin

Les deux chemins d'`execute_step` traitaient differemment un
`execute_node` qui **leve** : le pool recueillait l'exception dans
`future.result()` et notait le noeud en echec, le chemin sequentiel la
laissait remonter et emportait la marche du graphe. Deux semantiques
d'echec pour le meme rappel, selon un nombre de places — c'est-a-dire
selon la VRAM libre. Homogeneisees ici, parce que le portillon passe
desormais par les deux.

### Une mutation qui a demasque le compteur de mutations

La mutation « ne jamais rendre la place » a d'abord ete rapportee
**verte**. Elle ne l'etait pas : les tests attendaient le delai du
portillon — 1200 s par defaut — et le delai de garde de pytest tuait la
session sans imprimer de resume, que le compteur lisait « 0 rouge ».

Deux corrections : les tests bornent explicitement ce delai a 3 s, et une
garde directe verifie le compteur de places sans aucune attente — sortie
normale, sortie par exception, entree refusee. Elle echoue desormais en
3,2 s avec un message. Une garde qui pend n'est pas une garde (HOS-112).

C'est le quatrieme garde-fou de cette serie de passes dont une mutation
revele qu'il ne gardait pas ce qu'on croyait ; cette fois, c'est
l'instrument de mesure lui-meme qui mentait.

### Ce qui reste ouvert

R-6 (comptabilite VRAM/CPU par Run) et A-17. `Mission.priority` reste lu
par personne (A-14) : le portillon ne l'utilise pas, et c'est
deliberement hors perimetre — la priorite est du ressort d'un
ordonnanceur, que cette passe s'interdit d'introduire.

## HOS-258 — Ce que mesure la source d'admission (2026-09-05)

A-15, decouvert en fermant §6.2. `GPUMonitor` essayait `rocm-smi`, puis
`nvidia-smi`, puis **retombait sur `/api/ps`**. Sur cette machine —
Windows, AMD RX 6800 — les deux premiers n'existent pas : le repli etait
le chemin **normal** de l'admission, et il repondait sans erreur.

Or les deux ne repondent pas a la meme question. `rocm-smi` dit ce qui
est occupe sur la carte ; `/api/ps` dit ce que **pesent les modeles
residents d'Ollama** — sans cache KV, sans tampons de calcul, sans un
octet de ce que tient un autre processus.

### La mesure, trois etats de charge, meme carte de 15,984 Gio

    etat                     /api/ps    occupation reelle    ecart
    aucun modele              0,000            1,314        +1,314
    qwen3.6-35b resident     12,737           14,954        +2,216
    meme modele, cache KV    12,737           15,115        +2,377

L'ecart va toujours dans le meme sens et il **grandit** : `/api/ps` est
reste fige a 12,737 pendant que l'occupation montait de 161 Mio — ce qui
montait etait le cache KV, qu'il ne voit pas. Une marge forfaitaire
n'aurait donc pas suffi.

### Ce que cela donnait sur le vrai chemin

Rejoue sur `ResourceManager.can_allocate`, a l'etat 3, ou il restait
0,870 Gio :

    demande            /api/ps    occupation reelle
    1,0 Gio             ADMIS          refuse
    1,5 Gio             ADMIS          refuse
    2,0 Gio            refuse          refuse

Le modele de 1,5 Gio admis se serait charge sur 0,87 Gio libres : il
aurait deborde en memoire systeme, repondu dix fois plus lentement, et
**sans erreur**. C'est exactement la classe de defaut que `CLAUDE.md`
decrit — un succes qui n'en est pas un.

### La decision

Source canonique de l'admission : l'**occupation physique de la
machine**, definie une seule fois dans
`backend/runtime/resources/vram_physique.py` — somme de
`\GPU Process Memory(*)\Dedicated Usage` sur tous les processus. Meme
semantique que `rocm-smi`, qui reste prioritaire la ou il existe.

`/api/ps` garde son role : dire quels modeles sont residents et ce qu'ils
pesent. Il n'est plus une source de VRAM physique nulle part.

Quand aucune sonde ne repond, le moniteur ne rend plus de chiffre. Il
distingue deux etats que `available=False, total=0` confondait :

- **pas de carte** — aucune contrainte VRAM a faire respecter, admission
  inchangee, ce qui est correct sur une machine sans GPU ;
- **carte presente, occupation illisible** — `occupation_mesuree=False`,
  et la politique **refuse**. Aucune politique nouvelle : le refus
  emprunte le mecanisme existant, `_check_vram_admission` attend
  `vram_wait_s` puis leve `RuntimeUnavailableError`, et une sonde qui
  revient pendant l'attente debloque la tache d'elle-meme.

### Le drapeau devait remonter, sinon il deplacait la confusion

Une carte non mesuree porte `vram_used_bytes: 0`. Sans rien de plus, le
Cockpit l'aurait affichee « 0,0 / 16,0 Gio, 0 % » — soit une carte au
repos, la meme erreur un etage plus haut. `occupation_mesuree` entre donc
dans `get_status()`, dans le type du frontend, et dans trois aides
partagees (`vramOccupee`, `vramLibre`, `vramPourcent`) que les huit
surfaces d'affichage appellent. `formatGio(null)` rendait deja « — ».

`check_thresholds` recevait le meme zero et concluait « 0 %, sain ». Une
surveillance qui rassure sans avoir regarde est pire que pas de
surveillance : les seuils sont sautes quand l'occupation n'est pas
mesuree.

### Une affirmation de §6.2 qui ne se reproduit pas

§6.2 chiffrait la sous-declaration du compteur **par adaptateur** a un
facteur trois : 3,99 contre 12,70 Gio. **Remesure pendant A-15, carte
portant un modele de 12,74 Gio, sur trois releves espaces et stables :**

    GPU Adapter Memory\Dedicated Usage  -> 14,669 Gio
    GPU Process Memory\Dedicated Usage  -> 15,115 Gio

Soit 0,445 Gio, 2,9 %. La sonde qui avait produit le 3,99 n'a pas ete
conservee et n'est plus auditable ; le chiffre est donc **retire** du
CHANGELOG, du code et des tests plutot que repete. Ce qui reste mesure :
l'ecart existe, il va toujours dans le meme sens, et le choix du compteur
par processus ne change pas. Son ampleur annoncee, si.

### Ce que cela coute

1,60 s par mesure reelle contre 0,02 s pour `/api/ps` — PowerShell est
demarre a chaque fois. Le cache de 2 s du moniteur absorbe les appels
rapproches : cinq `poll()` de suite coutent 1,60 s au total. Une tache
vit entre 60 et 900 s ; c'est le bon echange.

### Ce qui n'est pas ferme

Sur Linux sans `rocm-smi`, aucune sonde ne repond et le registre Windows
n'existe pas : l'etat est « pas de carte detectable », donc admission
sans contrainte. Le kernel AMD publie pourtant
`/sys/class/drm/card*/device/mem_info_vram_used`, de meme semantique.
Rien ici ne permet de l'exercer, et ecrire une sonde non mesuree serait
reproduire la faute que cette passe corrige. Consigne **A-16**.

### Un rouge qui ne vient pas d'ici

La suite complete (`pytest -m ""`) n'est pas verte, et ne l'etait pas non
plus avant. `tests/integration/test_assembly.py::TestEventWiring::
test_no_real_subsystem_event_is_dropped` lance un objectif autonome reel
et attend qu'un noeud engage se termine ; le delai de garde global est de
60 s (`pytest.ini`, HOS-112).

Mesure, GPU au repos, aucun modele resident, meme test lance seul :
il depasse le delai **au commit `03f4f96` comme apres A-15**, avec des
piles identiques ligne pour ligne — le fil est bloque dans `_run_coro`
sur une inference, pas dans l'admission. Un worktree sur `03f4f96` a servi
a le verifier plutot qu'une deduction.

Le rapport §6.2 annoncait « suite complete 5979 passed » : c'etait vrai ce
jour-la, et ca ne se reproduit pas — ce test depend de quel modele le
routeur choisit et de sa vitesse. Consigne **A-17**, hors perimetre.

Ce qui est vert : boucle courte 5740 / 0, et suite lente 267 / 0 en
mettant ce seul test de cote.

### Les mutations

Huit, huit rouges : `/api/ps` remis en source (4), fail-closed supprime
(3), priorite inversee (2), carte non lue presentee comme mesuree (2),
`ResourceManager` contourne par l'agent (3), deuxieme autorite de mesure
(1), compteur par adaptateur (4), source canonique restreinte a un
processus (1).

Deux tests de §6.2 affirmaient l'ancien contrat — « le fichier
`monitoring/gpu_monitor.py` contient la chaine `GPU Process Memory(*)` ».
La requete ayant demenage dans la source canonique, ils sont **reecrits
sur la propriete** — quel compteur est interroge, et par combien de
definitions — dans la passe meme qui change le contrat, parce que la
reecriture est verifiable independamment : la meme propriete est gardee
deux fois, dans deux fichiers, et les mutations G et H la font rougir.

## HOS-257 — Verifier n'est pas reserver (2026-09-04)

§6.2. Trois defauts MUST HAVE de l'audit §6.1, fermes ensemble parce
qu'ils sont le meme defaut vu de trois cotes : une decision de ressource
prise sur une mesure incomplete.

### R-1 — le chemin le plus lourd etait le seul non controle

`task_executor` portait `if not use_cloud and runtime_id !=
"hermes-agent"`. L'exception visait precisement le consommateur le plus
lourd : un processus complet qui charge un modele et enchaine jusqu'a
douze tours sur la meme carte. Une simple completion avait une admission,
un agent n'en avait pas — et l'agent est le chemin **normal** d'une
mission liee a un workspace.

La porte est posee la ou les deux harnais convergent :
`_hermes_agent_chat_for` rend une fermeture qui couvre le jetable
(`hermes_agent_cli`) comme le persistant (ACP). Une porte par adaptateur
en aurait fait deux, et le troisieme serait ne sans.

### R-2 / A-13 — le verrou n'etait pas le probleme

`reserve_resources` existait sans appelant hors d'une route HTTP. Le
brancher tel quel n'aurait **rien regle** : la decision ignorait
`self._allocations`. Mesure avant correction, carte simulee de 16 Gio
dont 2 deja pris :

    reserve(8 Gio) -> True
    reserve(8 Gio) -> True        18 Gio promis sur 16

Le verrou serialisait bien deux decisions — mais chacune lisait un
compteur physique que la premiere n'avait pas fait bouger, un modele
reserve n'occupant la VRAM qu'une fois **charge**. Le compte des
reservations est donc entre dans la decision, au meme endroit qu'elle.

Consequence assumee : une fois le modele charge, sa consommation est
comptee deux fois — compteur physique **et** reservation — jusqu'a la
liberation. On refuse parfois une allocation qui aurait tenu, jamais
l'inverse. Meme prudence que `_check_vram_admission` : « occasionally
waiting when the model was already loaded, never the other way around ».

La liberation est dans un `finally` : succes, exception, delai depasse,
annulation, repli cloud. Une reservation qui survit a sa tache condamne
la capacite, et rien ne viendrait la reprendre — le gestionnaire n'a pas
d'expiration.

### A-12 — et le rapport §6.1 avait la conclusion a l'envers

L'audit §6.1 affirmait que l'admission lisait la bonne source et le
Cockpit la mauvaise. **C'etait l'inverse de ce que la mesure dit**, et je
l'avais deduit du fait que l'admission refusait, sans verifier ce que
chacune lisait.

Mesure, meme instant, meme carte, un modele de 11,9 Gio resident :

    GPU Adapter Memory\Dedicated Usage   ->  3,99 Gio   <- le Cockpit
    GPU Process Memory\Dedicated Usage   -> 12,70 Gio   <- la verite
    /api/ps (somme size_vram)            -> 12,80 Gio   <- l'admission

> **Amendement du 2026-09-05 (HOS-258).** Le releve par adaptateur ne se
> reproduit pas. Remesure trois fois pendant A-15, carte portant un modele
> de 12,74 Gio : adaptateur 14,669 Gio, processus 15,115 — 0,445 Gio, soit
> 2,9 %, et non un facteur trois. La sonde d'origine n'a pas ete conservee
> et n'est plus auditable. Le choix du compteur par processus reste juste ;
> le chiffre qui le justifiait ici est faux et ne doit pas etre repris.

Le compteur **par adaptateur** sous-declarait d'un facteur trois, dans le
sens dangereux — celui qui fait croire qu'il reste de la place. Le
compteur **par processus** est celui que `model_bench.gpu_dedicated_bytes`
utilise deja et que `CLAUDE.md` designe comme la seule occupation reelle.
Le moniteur systeme le lit desormais : la carte affiche 14,08 / 17,16 Gio
la ou elle annoncait 4,28.

`/api/ps` reste ce qu'il est — les poids des modeles residents, sans le
cache KV ni les tampons — et garde son role d'information sur les modeles
charges. Il n'est pas presente comme une mesure de la VRAM physique.

### Ce qui n'est pas ferme

La source de l'**admission** reste `/api/ps` quand `rocm-smi` est absent,
ce qui est le cas sur cette machine. C'est une mesure des poids seuls :
elle sous-estime par construction. Canoniser une source demande de
decider ce que `ResourceManager` lit quand `rocm-smi` manque, et cette
decision n'a pas ete prise ici. Consigne **A-15**.

### Les mutations, dont une qui a demasque une assertion morte

Cinq mutations, cinq rouges. La premiere n'a d'abord fait rougir que deux
tests sur trois : la garde structurelle cherchait
`runtime_id != "hermes-agent"` avec des guillemets doubles dans un texte
produit par `ast.unparse`, **qui les normalise en simples**. L'assertion
ne pouvait donc jamais correspondre. Corrigee, la mutation la fait rougir.

C'est le troisieme garde-fou de cette serie de passes dont une mutation
revele qu'il ne gardait rien. Le motif est constant : une assertion
ecrite sur une **forme** plutot que sur une propriete.

## HOS-256 — Deux protections declarees, jamais appelees (2026-09-04)

Fermeture de A-2, second defaut P1 de l'audit global J25.

### Le constat, retrace de bout en bout

`security/derive_workspace.py` (HOS-217) et
`security/surveillance_flux.py` (HOS-218) etaient implementes, testes, et
declares ✅ **Fait** au ROADMAP. Tracage complet — imports absolus et
relatifs, instanciations, appels, decorateurs, chaines de caracteres,
`getattr`, imports dynamiques, hooks de demarrage, injections, routes,
scripts d'operateur : **zero reference de production**. Chaque module
n'etait cite que par son propre fichier de test.

Les quelques occurrences de production que le premier tracage remontait —
`comparer`, `resume`, `enregistrer`, `relire`, `Ecart`, `Etat`, `REPORT` —
sont toutes des **homonymes** : `git_ref.py` definit son propre `Ecart`,
`maj/sante.py` son propre `Etat`, `workspace_models.py` a `REPORT` comme
membre d'enumeration. Aucun n'importe les modules de securite. Verifie un
par un plutot que suppose.

Ce n'etaient pas des protections. C'etait du code.

### Ce que la mesure a montre de pire

**HOS-218.** `hermes_agent_cli` lance le sous-processus avec
`os.environ.copy()` — **tout** l'environnement du parent, chaque secret de
la machine — plus un `OPENAI_API_KEY` explicite. Sa sortie etait decodee
et analysee pour en extraire un identifiant de session, et rien n'y
cherchait de secret. L'exposition que le canary devait detecter etait donc
maximale, et la detection absente.

**HOS-217.** Ni Aegis ni `file_tools` ne traitent specialement les dix
fichiers gouvernants. La liste blanche d'Aegis accorde la racine du
projet, et `CLAUDE.md`, `.mcp.json`, `.claude/hooks/` sont dedans.
`_est_protege` lit `.hermes/proteges.txt` — une liste **declarative**, qui
vit dans le workspace, qu'un agent peut donc reecrire, et dont la
docstring dit elle-meme qu'elle « evite une perte » et « n'est pas une
frontiere de securite ».

Les deux invariants etaient donc reels **et** non couverts. Cas A des
deux cotes : on branche.

### Ou chaque controle vit, et pourquoi la

**HOS-218 → les lanceurs d'agent.** Le temoin est plante dans
l'environnement du sous-processus et la sortie est examinee au retour.
Poser cela plus haut — dans l'executeur de tache — laisserait sans
surveillance un lanceur ajoute demain.

Le garde-fou structurel a d'ailleurs trouve **un second lanceur** avant
qu'on declare quoi que ce soit : le harnais persistant de HOS-137
(`hermes_agent_acp`) lance le meme agent, garde ouvert entre les taches,
avec `{**os.environ}`. Il porte desormais la meme surveillance — une par
session, pour que le report de 512 caracteres traverse les tours et
attrape un secret coupe en deux entre deux lignes.

La surveillance ne tue rien : le module l'a toujours dit, il rapporte et
l'appelant tranche. Ce qu'on empeche est que le resultat **serve** — un
secret recrache entrerait sinon dans le Run Ledger, dans le relais de
contexte et dans le prompt suivant. La fuite se propagerait par les
mecanismes memes qui servent a tracer.

**HOS-217 → la couture d'instantane de mission.** `_snapshot_workspace`
prend deja une empreinte au demarrage et `_verify_workspace` la confronte
a l'arrivee. La derive de gouvernance est la meme question posee sur une
autre liste de fichiers ; la poser ailleurs aurait cree un second moment
de mesure la ou il en existe un.

**Aucune politique n'est inventee.** Le resultat entre dans le verdict de
verification, qui a deja ses consommateurs — `mission.metadata`,
`mission.unverified`, `_suggest_retry`. Le module demandait exactement
cela : mesurer, et laisser quelqu'un d'autre trancher.

Un `None` signifie « non mesure », un `derive: false` signifie « mesure,
rien n'a bouge ». Confondre les deux ferait passer une absence de mesure
pour une absence de derive — la regle tri-etat de HOS-222 appliquee ici.

### Deux mutations qui n'ont pas rougi, et ce qu'elles ont appris

Six mutations posees. Deux sont d'abord restees vertes, et c'etaient les
tests qui avaient tort :

* retirer l'examen de la sortie en gardant `alerte = None` conservait la
  **forme** que le test verifiait — un `if` sur `alerte` avec un `raise`.
  La forme sans l'appel ne prouve rien ;
* retirer le releve de la ligne de base laissait tout vert parce que les
  tests appelaient `_relever_les_gouvernants` eux-memes au lieu de passer
  par `start_mission`. Un test qui appelle le garde-fou a la place du
  produit ne prouve pas que le produit l'appelle.

Les deux tests ont ete renforces, pas les assertions affaiblies. Apres
correction, les six mutations rougissent.

### Statut documentaire

Le ROADMAP disait ✅ **Fait** pour les deux depuis leur ecriture. C'etait
vrai du code et faux du systeme. Les entrees portent desormais la date de
branchement et l'endroit ou le controle vit, parce que « fait » sans « et
appele » est precisement ce que A-2 a coute.

## HOS-255 — Le goulet cloud n'etait pas le seul passage (2026-09-04)

Fermeture de A-1, le premier des deux defauts P1 de l'audit global J25.

### Ce que le commentaire affirmait, et ce que la mesure a dit

`_make_cloud_chat` examine bien avant d'envoyer, et son commentaire
disait : « c'est le seul passage par lequel un prompt part chez un
tiers ». Faux, mesure :

    base_agent.py:279        self._cloud_client.chat_events(model, messages, …)
    task_decomposer.py:489   self._cloud_client.chat_events(model, messages, …)
    grep -c pare_feu  ->  0  dans les deux fichiers

HOS-066C a livre un repli de resilience — tente quand le flux local
echoue avant d'avoir rendu un seul morceau — et il precede HOS-227
d'assez loin pour n'avoir jamais ete route a travers lui. Le declencheur
est une panne d'Ollama : sur ce materiel, une condition de routine. La
fuite que HOS-227 decrit dans sa propre docstring — le chemin absolu du
workspace, donc le nom de l'utilisateur et celui de son client —
repartait par la, non filtree.

### La cartographie avant de corriger

L'audit signalait deux lignes. Les tracer toutes en a montre **quatre**
fichiers qui parlent a OpenRouter :

| fichier | ce qu'il envoie | verdict |
|---|---|---|
| `connectors/openrouter_client.py` | tout | le seul wrapper |
| `ral/adapters/openrouter.py` | construit ce meme client | couvert |
| `model_intelligence/benchmark_scheduler.py` | ses propres prompts **constants** | rien a examiner |
| `model_intelligence/cloud_catalog.py` | `GET /models`, credits | n'envoie aucun message |

Corriger les deux lignes signalees aurait laisse la question ouverte pour
la suivante.

### Pourquoi la garde est dans le client

Router les deux replis vers `_make_cloud_chat` etait le premier reflexe.
Il ne tient pas : **ce goulet est non-streaming** et rend une reponse
complete, alors que `BaseAgent` diffuse. L'y forcer aurait fait arriver
chaque reponse d'un bloc — une regression fonctionnelle pour fermer un
trou de securite.

La garde vit donc la ou est la socket : `OpenRouterClient.chat` et
`chat_events`, les deux seules sorties de la seule classe qui parle a
OpenRouter. `chat_stream` delegue a `chat_events` et en herite. Tout
appelant present et futur y passe **par construction**, sans avoir a le
savoir.

**Aucun second pare-feu** : c'est le meme `pare_feu.examiner`, la meme et
unique autorite. Le goulet garde son role entier — publication de la
decision, courtier, quota, disjoncteur — et rien de la logique de quota
n'a bouge. Le double examen est mesure idempotent : un texte deja
caviarde rend `AUTORISE`, sans constat et sans modification.

Un refus leve `OpenRouterUnavailableError`, deja comprise par tous les
appelants comme « replie-toi sur le local ». C'est exactement ce qu'il
faut faire quand le pare-feu refuse : le travail se fait, rien ne sort.

### Le garde-fou, structurel

Deux tests « le pare-feu a ete appele » n'auraient pas attrape A-1 : le
defaut etait un **troisieme chemin** que personne n'avait pense a tester.
La garde est donc une liste blanche de fichiers autorises a parler a
OpenRouter, chacun avec sa raison ecrite. Un nouveau chemin la fait
rougir tant qu'il n'y est pas ajoute delibarement.

Mutations : filtre retire de `chat_events` -> 5 rouges ; retire de
`chat()` -> 6 rouges ; un appel direct rouvert dans `base_agent` -> la
garde structurelle rougit en nommant le fichier.

### Un defaut de detection, trouve en chemin et **non corrige**

Le pare-feu reconnait `sk-…` comme secret et **ignore `sk-or-v1-…`**, le
format de cle d'OpenRouter lui-meme :

    cle openrouter  -> autorise   aucun constat
    cle openai      -> refuse     secret
    chemin windows  -> caviarde   interne

C'est un defaut de **detection**, distinct de A-1 qui etait un defaut de
**routage**. Le fermer demande de toucher aux motifs, ce qui peut
produire des faux positifs bloquant des envois legitimes : cela merite sa
propre passe. Consigne comme A-10. Fermer A-1 ne signifie donc pas que le
pare-feu voit tout — seulement qu'on ne peut plus le contourner.

## HOS-254 — Deux evenements que le Cockpit ne pouvait pas filtrer (2026-09-04)

Passe 24, fermeture des ecarts releves par l'audit de consolidation.

### Le defaut, et pourquoi le test de la passe 20 l'avait manque

`execution.retry` et `execution.budget_depasse` sont publies par
`mission_executor` et n'etaient dans aucun catalogue. Depuis HOS-066B le
hub delivre un topic inconnu en avertissant plutot que de le jeter : rien
n'etait perdu, mais **tout abonne qui filtre par type ne les voyait
jamais** — precisement les deux signaux qu'un operateur cherche quand une
mission se comporte mal, la reprise et le budget atteint.

Le test de cablage de HOS-252 aurait du les trouver. Il ne visitait que la
**trace nominale** : ces deux topics ne se produisent que sur des chemins
d'exception. Un test de cablage qui ne visite qu'un chemin ne cable qu'un
chemin.

La verification de declaration est donc parametree sur quatre chemins
reels — nominal, echec/reprise, annulation, budget — et la liste `CHEMINS`
est desormais la vraie assertion : y ajouter un chemin qui publie un topic
non catalogue rend le test rouge sans qu'on ait a le prevoir.

Le chemin du budget passe par `MissionExecutor.prepare/execute_task`,
c'est-a-dire le chemin de production de `POST /execution/start` ; la seule
chose de test est la **valeur** du budget. Rien n'est publie
artificiellement : c'est `_refuser_pour_budget` qui emet.

Un second test garde le garde : si l'un des deux topics cessait d'etre
emis, le test parametre resterait vert — il ne verifie que la declaration
de ce qu'il voit.

### Mutations

- `execution.retry` retire du catalogue → 1 rouge, sur le chemin echec ;
- `execution.budget_depasse` retire → 1 rouge, sur le chemin budget ;
- les chemins d'exception retires de `CHEMINS`, **et** les deux topics
  retires du catalogue → **8 verts**. C'est l'angle mort de la passe 20,
  reproduit a la demande.

### Un commentaire qui contredisait son propre fichier

`mission/routes.py` affirmait encore que « la persistance reste a faire :
au redemarrage la liste est vide », douze lignes au-dessus d'une docstring
disant que `MagasinMissions` est la source de verite. HOS-245 avait rendu
durable l'existence d'une mission, HOS-252 son etat. Le premier des deux
textes est celui qu'un lecteur rencontre — et c'est ce genre d'ecart qui a
fait batir une passe entiere sur un constat faux en passe 18.

### `_memory_.db`

Retire du depot, apres avoir etabli les faits plutot que de les supposer :

- ajoute par `d5f4794`, avant HOS-215 ;
- **deja migre** : le fichier identique (meme sha256, 45 056 octets) vit
  dans la racine d'etat, sous `memoire/` ;
- aucune table metier n'a de ligne — `goals`, `sessions`, `events`,
  `metrics` sont vides ; il reste une table nommee `test` ;
- aucun test n'en depend, aucune fixture ne le charge ;
- la documentation ne le cite qu'au passe, comme exemple de ce qui vivait
  dans le depot ;
- `scripts/migrer_etat.py` le nomme dans sa table de demenagement et
  **saute une source absente** — verifie en le relancant.

L'entree du script reste : elle sert aux copies de travail anterieures a
HOS-215, qui portent encore le fichier.

En passe 23 j'avais ecrit « aucun code ne le nomme ». C'etait faux : je
n'avais cherche que dans `backend/` et `frontend/src`. Le script de
migration le nommait.

### Ce qui n'a pas ete touche

`data/db/hermes.db`, 17,7 Mio, non suivi et ignore par git, vestige
d'avant HOS-215 : ce sont des donnees d'utilisateur, et leur sort est une
decision separee.

## HOS-253 — Une mission peut disparaitre ; ce qu'elle a fait, non (2026-09-04)

Passe 22, implementation de T-21. La plus petite de la serie, et
volontairement : **aucun code de production nouveau**.

### La question, et sa reponse mesuree

La passe 19 a supprime deux missions de diagnostic. Leurs huit runs sont
restes, dont un `en_cours` : un journal dont le sujet a disparu. Que
signifie un run dont la mission n'existe plus ?

La passe 21 a trace les appels reels plutot que de lire des noms, et la
reponse etait que le contrat etait **deja tenu par la conception** :

- aucune cle etrangere entre `runs.mission` et `missions.mission_id` ;
- `MagasinMissions.supprimer` ne touche que la table `missions` ;
- `Registre` n'expose aucune suppression, et le gel terminal vit dans le
  SQL, sur chaque colonne ;
- `de_la_mission`, `reprendre` et `reconcilier` ne consultent **jamais**
  le magasin des missions — verifie sur l'arbre syntaxique de chacune ;
- le run porte son propre instantane depuis HOS-219 : objectif, modele,
  runtime, fournisseur, workspace, projet, tentative, contrat.

Il n'y avait donc rien a construire. Ce qui manquait etait que personne
ne l'ecrive et que rien ne le prouve.

### Le fait qui reformule le sujet

**Il n'existe aucune fonctionnalite de suppression de mission.** Zero
appelant de production pour `_RegistreMissions.__delitem__` : pas de
route, pas de service, pas de politique. Les huit orphelins ne viennent
pas d'un trou de conception mais d'un geste d'operateur qui a employe une
primitive de test comme outil.

D'ou la seule modification de production de cette passe : le contrat,
ecrit sur `__delitem__`. La suppression emporte la mission et son entree
de cache, **jamais ses runs** ; aucune cascade ne doit y etre ajoutee ; et
cette primitive n'est pas une fonctionnalite produit — ajouter un
`DELETE /missions/{id}` demanderait d'abord de decider d'une politique de
retention.

### Ce que la mission absente n'est pas

Ni une `Cause`, ni une condition de reconciliation, ni une raison de
transformer `EN_COURS` en `PERDU`. La reconciliation continue de decider
sur la seule preuve qui vaut : le processus porteur existe-t-il encore.
Un test le montre par symetrie — meme scenario avec et sans la mission,
resultat identique — et la raison inscrite nomme le processus disparu,
jamais la mission.

Deux chemins de reprise restent distincts et le restent : une mission
absente fait refuser explicitement la reprise de mission, tandis que
`Registre.reprendre()` continue de fonctionner par lignee du run parent,
sans qu'aucune mission soit reconstruite.

### Les gardes mordent, mesure

Trois mutations posees puis retirees :

- cascade reelle `DELETE FROM runs` dans `MagasinMissions.supprimer` →
  **14 rouges**, dont le redemarrage a deux processus ;
- reconciliation consultant le magasin des missions → **3 rouges** ;
- `Cause.MISSION_ABSENTE` ajoutee → **1 rouge**.

Une premiere version de la premiere mutation n'a fait rougir que la garde
AST : elle ouvrait un `Registre()` par defaut, donc une autre base que
celle du test. Refaite sur la vraie base partagee, elle a fait rouge le
comportement. La lecon vaut d'etre notee : une mutation qui ne rougit pas
peut accuser la mutation autant que le test.

### Les huit runs

Inchanges, et c'est verifie avant et apres : memes identifiants, memes
statuts, aucune cause inventee. `dbde3e7cbf` reste `en_cours` — son
processus porteur est mort, et la reconciliation existante le fermera au
prochain demarrage du backend, en `PERDU` / `Cause.PROCESSUS`, sans
qu'une ligne nouvelle soit necessaire. Aucun nettoyage, aucun SQL direct.

## HOS-252 — Ce qu'un test de cablage mesurait vraiment (2026-09-04)

Passe 20, implementation des quatre decisions de la passe 19. Quatre
sujets, une meme forme : la primitive existait deja et n'etait pas
branchee, ou existait et n'etait pas verifiee.

### T-17 — un test de cablage qui mesurait une mission autonome

`test_no_real_subsystem_event_is_dropped` prouvait que l'EventHub ne jette
rien, en lancant un objectif autonome complet. Mesure en passe 18 : deux
reproductions de 608 s et 531 s **sans terminer**, pour une couverture de
topics acquise a 187 s, avec un plafond de conception de ~4 800 s — budget
de mission 3 600 s, verifie entre deux taches seulement, plus le plafond
d'un noeud engage.

La preuve du cablage vit desormais dans
`backend/tests/test_cablage_des_evenements.py` : **0,4 s**, sur la vraie
chaine `GraphExecutor -> MissionExecutor -> EventDispatcher -> EventHub`.
Rien n'est simule de la publication ; la seule couture est l'exécuteur de
tache, un parametre du constructeur de `MissionExecutor` depuis toujours
et prevu pour cela. Consequence assumee : `execution.task_completed` est
attendu du cote lent, parce que c'est `RealTaskExecutor` qui le publie —
l'affirmer du cote rapide reviendrait a verifier un evenement que le test
aurait lui-meme emis.

Les topics sont **nommes un par un**, pas comptes : un `len(events) >= 26`
reste vert quand un topic disparait pendant qu'un autre apparait, ce qui
est exactement la derive surveillee.

Le test long reste, reste `lent`, et garde ce que lui seul prouve — le
chemin autonome reel, avec ses familles `autonomous.*` et `planning.*`. Il
se termine maintenant : des sa propriete demontree, il annule l'objectif
par la route de production, et l'attente restante est bornee par
`plafond_du_noeud()`. Depasser cette borne n'est pas un delai de confort,
c'est le graphe qui a franchi son propre dernier recours, et le test le
dit.

**Une derive vivante trouvee au passage.** `mission.completed` etait publie
par `graph_executor` et absent de `EVENT_TYPES`. Le commentaire du
catalogue affirmait qu'« un ancien jet nommait des topics qu'aucun
emetteur n'utilise (mission.completed) » : vrai du scan, faux du code — le
topic y passe par une variable, invisible a la collecte AST des litteraux.
Le hub le delivrait avec un avertissement, mais tout abonne qui filtre par
type — le Cockpit — ne voyait jamais la fin d'une mission. C'est
exactement le mode de defaillance decrit par HOS-066B, retrouve par le
nouveau test.

### T-18 — une annulation qui n'annulait rien

`cancel_goal` posait `goal.status = CANCELLED` et s'arretait la. **Personne
ne lisait ce champ** hors des compteurs de `get_status` : la marche du
graphe s'arrete sur `mission.status`. HOS-102 avait corrige
l'*accessibilite* de cet appel — le verrou tenu pendant toute l'inference
le rendait injoignable — pas son *effet*.

Aucune primitive nouvelle : `graph_executor.cancel_mission` existait, elle
etait effective, et c'est elle qu'on appelle. Aucun mecanisme de
terminaison de processus non plus — l'invariant « un noeud engage n'est
pas interrompu » est celui du budget missionnel (HOS-247) et il tient ici
aussi, prouve par un test qui lance un noeud, annule pendant qu'il
travaille, et verifie qu'il termine.

La reponse de la route porte desormais sa semantique : « aucune tache
nouvelle ne sera engagee ; un noeud deja engage termine son travail ». Un
operateur qui lit `success: true` ne doit pas comprendre « arrete
maintenant ».

Verifie aussi : une seule route `/missions/{id}/cancel` est reellement
montee, celle de `mission/routes.py`, qui vise `Mission`. Celle de
`api/router.py`, qui vise `MissionInstance`, n'est montee nulle part —
`mission_control.py` le documentait deja depuis HOS-072. Pas de collision.

### T-19 — le journal survivait, son sujet non

`MagasinMissions` n'etait ecrit que par `__setitem__`, c'est-a-dire une
seule fois, a l'enregistrement, avant tout demarrage. Mesure : une mission
ayant tourne 531 s et reussi six noeuds sur sept se relisait sur disque
`READY / started_at=None / tous PENDING`.

Consequence directe sur HOS-248 : `started_at` est le **t0 canonique du
budget**, et il ne franchissait pas la frontiere du processus. Une mission
reprise apres redemarrage repartait avec 3 600 s entieres. C'est le
pendant exact de HOS-245, qui avait rendu durable l'*existence* d'une
mission : ici c'est son *etat*.

Aucun second stockage. Le persisteur est un appelable injecte dans
`GraphExecutor`, de la meme forme que `on_event` et `execute_node` qui y
etaient deja, et le bootstrap y branche le magasin M-8. Points d'ecriture :
demarrage, noeud terminal, mission terminale, annulation.

`_RegistreMissions.persister()` ecrit le disque **d'abord** et le cache
seulement s'il a accepte, en laissant l'erreur remonter. `__setitem__`
garde sa tolerance pour la creation — « une correction de persistance qui
empecherait de creer une mission serait un recul » — mais il mettait le
cache a jour meme en cas d'echec : la memoire affirmait une durabilite qui
n'existait pas. Prouve par un magasin qui refuse d'ecrire.

La preuve de survie se fait dans **deux processus** : l'un ecrit, l'autre
relit, et seul le disque parle.

### T-20 — l'isolation existait, sa verification non

La passe 18 avait conclu que la suite lente ecrivait dans
`AppData/Local/HermesOS`, sur la foi de deux missions bien reelles
trouvees la. Elles venaient de sondes autonomes, qui ne chargent aucun
`conftest` ; la suite est isolee depuis HOS-215. Une passe entiere avait
ete batie sur ce constat faux.

`conftest.py` verifie desormais ce qu'il pose : chemins canonicalises des
deux cotes — `resolve()` suit liens et jonctions, `normcase` gele casse et
separateurs — et l'imbrication compte autant que l'egalite. La suite
s'arrete avant le premier test plutot que d'ecrire. Elle ne supprime rien
et ne touche a aucun reglage : ce serait pire que le probleme.

### Ce qui reste ouvert

Huit runs des deux missions de diagnostic restent en base apres la
suppression de leurs missions en passe 19. `Registre` n'expose aucune
suppression, et supprimer des lignes SQL a la main contournerait la seule
autorite du Ledger. L'incoherence est symetrique de celle que HOS-245
avait fermee — le journal survit, son sujet a disparu — et attend une
decision dediee (T-21).

## HOS-251 — Deux tests qui affirmaient le contrat d'avant (2026-09-04)

Passe 17. HOS-249/250 avaient change deux contrats ; deux tests les
affirmaient encore, laisses rouges et nommes dans le commit precedent au
titre de l'exception de `CLAUDE.md`. Ils adoptent ici les nouveaux.

### Ce qui ne devait surtout pas arriver

Les rendre verts par le symptome. `assert hits` en `assert hits == []`
aurait suffi a faire taire les deux, sans qu'aucune ligne ne demontre
*pourquoi* la reponse est vide — et une reponse vide est exactement ce
que produit une regression du filtre, un projet mal resolu, ou une base
qu'on n'a pas ouverte. Un vert obtenu ainsi aurait couvert les trois.

### T-16 — l'incident de HOS-086 tient, la premisse a change

`test_memory_search_answers_without_the_document_index` protegeait un
vrai defaut : `memory_search` interroge deux magasins independants, et la
panne de l'un ne doit pas vider ce que l'autre sait. Ce qu'il faisait
d'obsolete etait d'ecrire **sans provenance** — donc `INCONNUE`, donc en
quarantaine.

Il ecrit desormais deux memoires dans la meme seconde, par les deux
chemins reels : le chemin humain, qui pose `HUMAIN`, et l'outil MCP, qui
pose `AGENT` lui-meme. L'index documentaire tombe, une seule revient. Et
ce qui les separe est relu en base : `origine` et l'etat de quarantaine,
pas le contenu ni la fraicheur. L'ecriture de l'agent porte
`confidence=1.0` et les tags `verified`, `trusted`, `human-approved` —
verifies presents dans la ligne, donc l'assertion n'est pas creuse — et
n'obtient rien. Une promotion humaine nommee la rend visible par le meme
appel.

Une matrice a cinq origines complete au niveau de l'entree durable ce que
`test_memoire_quarantaine.py` verifiait sur l'objet `Provenance` seul.

### T-13 — l'identite vient du registre

`test_project_id_filters_tasks_memory_and_messages` passait `"proj-1"` et
`"proj-2"`. Le filtrage marchait, et c'est ce qui posait probleme : deux
orthographes du meme projet ne se voyaient pas, et un identifiant invente
rendait une liste vide — qui se lit « ce projet n'a rien memorise » — au
lieu d'un refus.

Les identifiants viennent maintenant de `projects_create`, comme en
production. Deux tests s'ajoutent : un UUID bien forme mais jamais
enregistre est refuse **et rien ne s'ecrit** — un refus qui laisserait une
ligne orpheline serait pire que pas de refus du tout — et la recherche
depuis A rend A et le permanent, jamais B, apres promotion.

### Les assertions mordent, mesure

Trois mutations posees et retirees, chacune sur le mecanisme que les
tests pretendent demontrer :

- filtre de quarantaine retire → **4 rouges** (dont `agent`, `web` et
  l'origine absente ; `humain` et `systeme` restent verts, donc la
  matrice discrimine) ;
- resolution de projet neutralisee → **1 rouge**, celui du refus ;
- portee neutralisee → **1 rouge**, celui de l'isolation A/B.

### Aucun code de production modifie

Le nouveau contrat etait deja implemente et deja garde ; il manquait des
tests qui l'affirment. Le seul autre changement est un commentaire
d'en-tete devenu faux : `memory_search` n'a plus besoin d'Ollama pour
etre teste, puisque repondre sans l'index est precisement son contrat.

## HOS-249, HOS-250 — La memoire de l'agent etait un fait des qu'il l'ecrivait (2026-09-04)

Passes 15 et 16. Le jalon 2 (HOS-216) avait pose la quarantaine ; elle
protegeait la memoire de travail et pas celle qui survit au redemarrage.

### Le defaut, mesure

`memory_remember` — l'outil MCP que l'agent appelle — ecrivait dans
`memory_long` **sans provenance**, et `memory_search` relisait la table
sans filtre. Une phrase lue sur une page web devenait donc, en un
aller-retour, un fait que l'agent citait comme le sien. C'est le chemin
exact par lequel une injection de prompt voyage, et il etait ouvert.

Rien n'a eu besoin d'etre invente pour le fermer : `Provenance.depuis()`
appliquait deja la regle, `filtrer()` existait, `ORIGINES_DE_CONFIANCE`
excluait deja `AGENT` et `WEB`. Le travail a consiste a **appliquer ces
politiques la ou elles manquaient**, pas a en ecrire de nouvelles.

### `promouvoir()` annoncait un succes sans rien ecrire

Trace ligne a ligne : `souvenir.provenance = promue` levait
`AttributeError` (propriete calculee), le repli cherchait un `metadata`
que `MemoryEntry` n'a pas, rien n'etait ecrit — et `memory.promoted`
etait publie. Une promotion qui ne promeut pas est pire qu'une absence de
promotion : on la croit. La facade leve desormais ; le seul chemin qui
persiste est `episodic.promouvoir()`, qui commit, relit, et refuse le
succes si la memoire est encore en quarantaine apres ecriture.

Chemins de promotion persistante : **0 → 1**. Outils MCP d'elevation :
**0 → 0**, et une garde AST le tient — `promu_par` n'est assigne qu'en un
seul endroit du depot.

### Ce que la promotion ne fait pas

Elle ne change pas l'origine. Une memoire ecrite par l'agent reste
`agent` pour toujours : `Provenance` separait deja « d'ou ca vient » de
« ce qu'on en fait », donc `promu_par` renseigne suffit a basculer la
seconde en laissant la premiere intacte. Sans quoi on ne saurait plus
repondre, apres coup, a « d'ou venait cette information ? ».

`promu_par` est **obligatoire et non vide**, et c'est une trace d'audit,
pas une preuve : Hermes OS n'a aucun mecanisme d'identite humaine — son
conventionnel d'accord humain existant, `POST /security/approvals/{id}`,
n'en porte pas non plus. Ce qui fait foi est le **canal** : la route est
servie par l'API locale et n'existe pas comme outil MCP. Aucune identite
n'a ete inventee pour l'occasion.

### Identite de projet

`project_id` etait une chaine libre. Il est desormais l'identifiant
canonique d'un projet enregistre ; un identifiant qui ne resout vers rien
leve `ProjetInconnu` au lieu de rendre une liste vide — une liste vide se
lit « ce projet n'a rien memorise », un refus se lit « ce projet n'existe
pas ». Meme contrat qu'Aegis sur le meme parametre.

Les lignes historiques sont migrees chemin → identifiant au demarrage,
par jointure sur `root_path`. La migration ne devine rien : une ligne qui
ne resout pas reste telle quelle avec un avertissement, et **aucune
provenance inconnue n'est transformee en provenance connue**.

### Deux tests historiques laisses rouges, delibere

`test_memory_search_answers_without_the_document_index` et
`test_mcp_server::test_project_id_filters_tasks_memory_and_messages`
affirment les contrats d'avant — « une memoire ecrite par l'agent est
relisible par l'agent » et « `project_id` est une chaine libre ». Ils ne
sont pas casses : ils sont **perimes**. Ils sont laisses intacts et
rouges, et une passe dediee les reecrira sur les contrats T-13 et T-16.
Voir l'exception nommee dans `CLAUDE.md`.

## HOS-248 — Un budget que chaque noeud remettait a zero (2026-09-03)

Passe 10. HOS-247 avait rendu le budget effectif ; il restait sans effet
la ou il comptait.

### Le defaut, decouvert par HOS-247 en s'implementant

Sa premisse — `ExecutionMeta` est l'objet d'execution *de la mission* —
etait vraie sur un chemin et fausse sur l'autre. `execution/routes.py` en
construit **un** pour toute l'execution ; `mission/node_execution.py` en
construit **un par noeud** du DAG. Sur le chemin autonome, le budget
repartait donc de zero a chaque etape et ne pouvait jamais se declencher,
un noeud etant deja plafonne a 1 200 s. Le champ etait effectif et sans
effet.

### Ce que la mesure a elimine

Trois objets etaient candidats ; deux le sont par le code lui-meme.
`ExecutionMeta` est fragmente, mesure. **`Run` l'est aussi** :
`_ouvrir_le_run` part de `prepare(meta, …)`, donc une fois par noeud — le
journal ne pouvait pas porter le budget, et le lui confier en aurait fait
un decideur.

Reste `Mission` : le seul objet mesure comme unique par mission, deja
persiste par M-8 — dont le serialiseur parcourt `fields()`, si bien qu'un
champ nouveau traverse un redemarrage **sans migration ni schema**. Et
`Mission.started_at` existait deja, pose une seule fois par tentative et
reinitialise par une reprise : le t0 n'avait pas a etre invente, et la
regle « une reprise repart avec un budget entier » est vraie sans qu'une
ligne ne la decide.

### La precedence, explicite

    mission enregistree  ->  budget de la Mission
    sinon                ->  budget de l'ExecutionMeta

Le chemin direct garde donc son budget local, ou il est legitime : un
seul `ExecutionMeta` y couvre toutes les taches. Une garde lit l'ordre
des deux lectures dans `budget_s` : les inverser rendrait tous les tests
verts sur un chemin et faux sur l'autre.

### L'horloge : un seul terme civil, lu une seule fois

Une premiere version mesurait `now() - started_at` a chaque appel. La
garde monotone de HOS-247 l'a immediatement refusee — et elle avait
raison. La mesure est donc :

    deja consomme avant cette machine   (civil, lu UNE fois a la naissance)
  + ecoule depuis sa construction       (monotone, perf_counter)

Le premier terme ne peut pas etre monotone : il traverse la frontiere du
processus, et une horloge monotone ne mesure que depuis un demarrage. Le
limiter a une lecture est ce qui met la mesure d'un noeud **en cours** a
l'abri d'un saut d'horloge — heure d'hiver, NTP. Sans registre global :
l'offset tient sur la machine d'etat elle-meme.

Effet de bord heureux : `budget_consomme_s`, la propriete la plus lue,
n'interroge plus rien du tout.

### La chaine, mesuree de bout en bout

    mission bf6fcc85, budget 10 s
      n0   consomme  0/10  ->  engage
      n1   consomme  4/10  ->  engage
      n2   consomme  8/10  ->  engage
      n3   consomme 12/10  ->  REFUSE (budget)   cause : budget

Trois `ExecutionMeta` distincts, un seul compteur. Avant ce jalon, les
quatre lisaient 0 s.

### Mesures

| | passees | ignorees | deselectionnees |
|---|---|---|---|
| standard | **5 536** | 3 | 274 |

Frontend : 126 vertes, typecheck propre. 18 gardes ajoutees, aucun test
existant modifie.


## HOS-247 — Un budget qui se declarait et que personne ne lisait (2026-09-03)

Passe 8. La decision verrouillee en passes 7 et 7.1 est implementee — et
l'une de ses premisses s'est revelee fausse en chemin.

### Le defaut

`ExecutionMeta.max_duration_seconds = 3600.0` existait depuis longtemps.
Compte sur l'arbre syntaxique : **zero lecteur** en production, quand son
voisin de dataclass `max_retries_per_task` en avait deux. Le seul plafond
reel etait `MAX_EXECUTION_PASSES x plafond_du_noeud()`, soit **33 heures**
— trente-trois fois le budget declare. Ce n'est pas un budget, c'est un
garde-boucle.

Troisieme occurrence du meme motif sur ce chantier, apres `Statut.PERDU`
declare et jamais pose (HOS-240) et `modele`/`fournisseur` servis et
jamais ecrits (HOS-241).

### Pourquoi 3 600 s, et pas un chiffre rond

`docs/essai-skills360.md` porte quatre executions reelles du meme
objectif : 566 s, 878 s, 1 084 s et **2 186 s**. La derniere est un
**succes**, 7 taches sur 7, 12 fichiers produits. Un budget de 1 800 s
l'aurait tuee a 82 % de son travail.

3 600 s, c'est 1,65 fois ce pire cas reussi, et exactement trois plafonds
de noeud. Une garde tient cette justification, pour qu'elle ne redevienne
pas un souvenir.

### Ce que ce budget n'est pas

Il ne coupe rien. Il refuse d'**engager** la tache suivante ; une tache
deja lancee va au bout de son propre plafond — 900 s pour l'agent,
1 200 s pour le noeud. C'est ce qui le distingue d'un timeout.

Et un budget atteint n'est **jamais** `PERDU` : perdu veut dire « on ne
sait pas ce qui s'est passe », ici on le sait exactement, et c'est
l'operateur qui l'a decide. `Cause.BUDGET` est ajoutee, distincte de
`QUOTA` (une limite du fournisseur) et de `RESSOURCE` (une limite de la
machine) : celle-ci est une limite qu'on tient, pas qu'on subit. Son
remede porte `reessayer=False` — reprendre consommerait immediatement le
meme budget une seconde fois.

### L'horloge

`perf_counter`, pas `datetime.now()` : une horloge civile recule a
l'heure d'hiver et sur une synchronisation NTP, et une mission serait
coupee ou prolongee par le reglage de la machine. Pas `monotonic` non
plus : mesure, il a ~16 ms de resolution sur Windows, et un budget de 1 ms
s'y lisait « 0 s consommee ». Sans importance a l'echelle d'un budget en
heures, mais un test de frontiere ne doit pas dependre de la granularite
de l'horloge.

### La premisse fausse, trouvee en chemin

La passe 7 supposait qu'`ExecutionMeta` etait l'objet d'execution **de la
mission**. Mesure, il l'est sur un chemin et pas sur l'autre :

- `execution/routes.py` en construit **un** pour toute l'execution, avec
  toutes ses taches — le budget y est bien missionnel ;
- `mission/node_execution.py` en construit **un par noeud** du DAG, chacun
  ouvrant sa propre machine d'etat — le budget y est un budget **de
  noeud**, et ne se declenchera donc jamais, un noeud etant deja plafonne
  a 1 200 s.

Aucun risque introduit : sur ce chemin, le champ reste sans effet comme
avant. Mais il ne protege pas la mission entiere, et le croire serait
exactement le genre d'illusion que ce jalon corrige ailleurs. Une garde
epingle la limite et echouera le jour ou elle disparaitra.

Un budget reellement missionnel sur le chemin autonome demande un t0
porte par la **mission**. C'est une decision que la passe 7 n'a pas
prise, et l'elargir ici aurait ete le « reparer par extension de
perimetre » que la passe 8 s'interdit explicitement.

### Deux faux positifs de sous-chaine, dans mes propres gardes

Dixieme : une garde d'ordre comparait deux `str.index` et trouvait
`self._task_executor.execute` dans la **docstring**, cinquante lignes
avant le code. Onzieme : une garde interdisant `PERDU` s'accrochait a la
docstring qui explique precisement que ce n'est jamais `PERDU`. Les deux
reecrites sur l'arbre syntaxique, corps sans docstring.

### Mesures

| | passees | ignorees | deselectionnees |
|---|---|---|---|
| standard | **5 517** | 3 | 274 |

Frontend : 126 vertes, typecheck propre. 22 gardes ajoutees, **aucun test
existant modifie**, aucun test supprime.


## HOS-246 — Le test n'etait pas bloque : l'agent cherchait sur tout le disque (2026-09-03)

Passe de fermeture ciblee. Trois points de la passe precedente, dont deux
diagnostics qui ont refute mes propres mesures.

### Le test « bloque » : cause racine, mesuree

`TestEventWiring::test_no_real_subsystem_event_is_dropped` n'est pas en
interblocage. Pile complete capturee sur les trois fils :

    task_executor.py:756  ->  _run_coro  ->  future.result(timeout=...)

C'est une attente **bornee** : 900 s par tache pour l'agent, 1200 s par
etape de graphe. Et le test progresse reellement — un dossier de mission
apparait toutes les deux a quatre minutes, `lfm2.5-2.6b-125k` est charge
en VRAM, et les processus d'agent se succedent.

Ce qui le rend interminable a ete trouve en inspectant les petits-enfants
du processus de test :

    find.exe / -name api_spec.yaml -type f   |   head -20

L'agent, cherchant une specification d'API, a lance un `find` sur **la
racine entiere**. Huit minutes et demie plus tard il tournait encore. Le
`head -20` qui aurait du le fermer ne propage pas SIGPIPE sur Windows.

Le test est donc **legitimement non mesurable ici** : il conduit une
mission autonome complete dont le nombre de noeuds n'est pas connu
d'avance, chacun borne a 900 s. Non modifie, non desactive, non marque.

### Les processus residuels : ma mesure precedente etait fausse deux fois

J'avais rapporte « 19 processus hermes-agent, dont un ne a l'heure exacte
du lancement des tests ». Les deux moities etaient fausses.

Le filtre portait sur la **ligne de commande** et attrapait trois de mes
propres shells qui mentionnaient simplement « hermes-agent ». Huitieme
faux positif de sous-chaine de ce chantier. Mesure sur l'executable :
**12**, dont **aucun** cree le jour de la campagne. Le processus ne a
19:22 etait un shell, pas un agent.

Mesure correctement, le cycle de vie du CLI est **sain** : observe sur un
vrai deroulement, un agent apparait, travaille, disparait, un autre le
remplace, et le compte reste stable. `hermes_agent_cli` attend
`communicate()` et tue le processus des que le budget expire.

### L'ambiguite, elle, est reelle — et non tranchee

40 processus ont leur repertoire courant sous `hermes_os_scratch` : des
`bash -lic "… python app.py"` et les serveurs qu'ils lancent, ecoutant sur
le port 8000, vivants depuis 37 heures. Ce ne sont pas des agents : ce
sont les **petits-enfants** que l'agent demarre en executant le code
qu'il ecrit.

Personne ne les possede. Ni Hermes OS, qui ne possede que le processus
CLI et le libere correctement. Ni l'agent, qui sort.

**Aucun faucheur n'a ete construit.** Hermes Agent est le cerveau : il
peut legitimement demarrer un serveur de developpement, et le tuer serait
detruire le travail demande. Inventer un systeme qui tue des processus
dans le dossier de travail d'un utilisateur serait a la fois une
architecture nouvelle et un risque. La decision revient au proprietaire
du depot ; ce jalon la documente et garde ce qui est demontre.

### Une documentation qui affirmait le contraire du code

`_unsandboxed_write` decrivait `ToolPolicy.evaluate()` comme une branche
inerte et affirmait que les adaptateurs MCP ne consultaient jamais leur
`ToolSandbox`. **HOS-238 avait rendu les deux affirmations fausses**, huit
jalons plus tot.

La conclusion du garde-fou tient pourtant toujours, mais pour une autre
raison, qu'il fallait ecrire : HOS-238 a ferme une porte plus etroite —
la politique refuse une ecriture dans un sandbox *declare* en lecture
seule, mais elle n'en **provisionne** aucun. Ce n'est plus « rien ne
verifie », c'est « rien ne fournit l'isolement dont la verification aurait
besoin ». Trois gardes tiennent desormais les deux moities de cette
phrase, sur le comportement et non sur le texte.

Une documentation perimee sur une decision de securite est pire qu'une
absence : elle fait croire qu'un controle manque la ou il existe, et on
finit par en ecrire un second.

### Neuvieme faux positif, entre ma correction et ma propre garde

La note de correction **citait** l'ancienne formulation ; la garde qui
interdit cette formulation s'y est accrochee. Reecrite pour decrire au
lieu de citer.

### Mesures

| | passees | ignorees | deselectionnees |
|---|---|---|---|
| standard | **5 496** | 3 | 274 |
| lente (moins le test non mesurable) | **267** | 6 | — |
| **complete** | **5 763** | 9 | **1 non mesurable** |

Frontend : 126 vertes, typecheck propre. 7 gardes ajoutees, 0 test
supprime, 0 processus tue.


## HOS-245 — Le journal survivait, son sujet non (2026-09-03)

Passe §5.2 : déblocage de spécification, mesure de la suite lente, et la
dette M-8.

### P-4 : tranché, et le dépôt le dit enfin

`ROADMAP.md` portait encore « Consolider `ModelRouter` et
`AdaptiveRouter` — **un seul devrait décider** », alors que HOS-243/244 a
livré et gardé leur séparation. Le document contredisait l'architecture
validée. Il dit maintenant ce qui a été décidé : coexistence autorisée
tant qu'aucun chemin de production ne les utilise comme autorités
concurrentes, précédence arbitrée par `backend.ral.arbitrage`.

### « 5 472 vertes » n'était pas la suite

`pytest.ini` porte `addopts = -m "not lent"` : la commande standard
**désélectionne 273 tests**. Ils ont été exécutés.

- **271 passent**, 6 sont ignorés ;
- **2 échouaient depuis longtemps** — antérieurs à HOS-240, jamais vus ;
- **1 ne finit pas**, même avec 1 200 s de délai.

Le trou de HOS-111 s'était rouvert plus petit : `testpaths` avait été
corrigé, `addopts` rouvrait la porte à côté.

### Les deux rouges : le test affirmait ce que R-002 avait supprimé

`create_code_intelligence_agent()` était appelé **sans fournisseur**, et
les tests attendaient un succès. Or R-002 P5 avait précisément retiré le
`success=True, {"status": "simulated"}` que l'agent rendait alors — les
tests avaient survécu à la correction et exigeaient toujours le
comportement retiré.

Mesuré, l'agent a **deux refus honnêtes**, et le premier masquait le
second :

    aucun fournisseur, tâche écriture  →  « provider klaatcode is not bound »
    fournisseur lié,   tâche écriture  →  « … no sandbox — refused (R-006 Phase 9) »
    fournisseur lié,   tâche lecture   →  l'exécuteur est réellement appelé

Les deux tests lient donc un fournisseur, ce qui leur fait enfin
atteindre la branche que leur propre docstring décrit. Ils vérifient
davantage qu'avant, et une troisième garde tient le refus que tous deux
masquaient. Aucun test supprimé, aucune assertion affaiblie.

### Le test qui ne finit pas

`test_no_real_subsystem_event_is_dropped` appelle
`autonomous_engine.start_goal("Build an API")` — c'est-à-dire **une
mission autonome complète**, synchrone, dont la docstring annonce
elle-même « minutes » d'inférence locale. Bloqué dans
`graph_executor._recolter_en_parallele`, 0 seconde de CPU, il n'a pas fini
en 1 200 s. Il laisse aussi de vrais sous-processus d'agent derrière lui.

Non modifié : le corriger sans décision serait exactement le vert
artificiel que cette passe interdit. Signalé comme la seule dette
mesurée de la suite lente.

### M-8 : la mission survit enfin à son propre journal

HOS-221 avait rendu le registre des **runs** durable ; HOS-240 lui avait
ajouté une réconciliation qui pose `PERDU`. Le registre des **missions**,
lui, était un `OrderedDict` en mémoire. Un run perdu désignait donc une
mission disparue — et pas seulement après un redémarrage : au-delà de
200, le FIFO en effaçait définitivement pendant que le processus tournait.

La table `missions` vit désormais dans la **même base que les runs**, avec
un document JSON qui rend la mission *reconstructible* — DAG, contexte,
énumérations et horodatages reviennent typés — et des colonnes scalaires
pour les seules questions qu'on pose en SQL.

Vérifié sur de vrais sous-processus tués par `os._exit` :

    run     : perdu | cause : processus
    mission : 'refondre le parseur'
    lien    : run.mission résout -> True
    reprise : tentative 2 | mission liée : True

### Deux défauts que j'ai introduits, et qui m'ont été rendus

**`values()` relisait toute la base.** Le test existant
`test_lister_pendant_qu_on_enregistre_ne_leve_pas` appelle `values()` deux
mille fois pendant qu'un fil écrit sans arrêt : chaque appel désérialisait
le JSON de toutes les missions accumulées. Le fichier est passé de
quelques secondes à plus de dix minutes. C'est un test écrit pour tout
autre chose — la réentrance d'un verrou — qui a démasqué une complexité
quadratique.

Le registre est borné par construction, et c'est ce qu'il a toujours
promis. Le cache est maintenant **hydraté** depuis la base au premier
parcours : après un redémarrage la liste n'est plus vide, et toute
mission évincée reste lisible par son identifiant.

**`len()` rendait le total en base.** Il rendait l'objet incohérent —
`len(r)` et `len(r.values())` ne disaient plus la même chose — et faisait
fuir chaque test dans le suivant. `len()` décrit le plan de travail ;
`total()` compte ce qui est conservé. Les confondre était l'erreur.

### Mesures

| | passées | ignorées | désélectionnées |
|---|---|---|---|
| standard | **5 489** | 3 | 274 |
| lente (moins le test bloqué) | **267** | 6 | — |
| **complète** | **5 756** | 9 | 1 non mesurable |

Frontend : 126 vertes, typecheck propre. 20 gardes ajoutées, 2 tests
réécrits, 1 fixture d'isolation, 0 test supprimé.


## HOS-244 — Le code contredisait son propre contrat (2026-09-03)

Passe chirurgicale sur §5.1. Un défaut bloquant trouvé dans HOS-243,
livré la veille : la documentation du module d'arbitrage affirmait une
règle que son code violait douze lignes plus bas.

### La contradiction

`ral/arbitrage.py` écrivait, dans sa docstring :

> Il ne peut pas la faire redescendre : défaire une assignation
> explicite serait exactement la seconde autorité que ce module supprime.

Et, dans son corps :

    elif monte is not None and runtime == MONTEE_AUTORISEE and not cloud_joignable:
        runtime, source_runtime = defaut_runtime, "repli, cloud injoignable"

Une tâche assignée à `openrouter` sans clé configurée devenait donc
`hermes-agent` — l'annulation silencieuse que le module existait pour
supprimer. Pire : elle **réussissait**, en local, et l'opérateur qui avait
demandé le cloud ne l'apprenait que dans un journal.

Ce n'était pas un défaut de documentation. C'était un défaut de
comportement, et la documentation avait raison.

### Recommandation défaite, assignation défaite

Le dépôt distingue déjà les deux, et c'est cette distinction qu'il
fallait appliquer :

- une **recommandation** vers le cloud qui n'aboutit pas est simplement
  défaite. C'est littéralement la politique de `_make_cloud_chat` —
  « cloud entièrement injoignable, **quoi que recommande AdaptiveRouter** ».
  Elle n'engageait personne. Le repli local reste autorisé, et nommé ;
- une **assignation** vers un runtime qui ne peut pas servir n'est pas
  remplacée. `Decision.impossible` est renseignée, et l'appelant lève
  `RuntimeUnavailableError` — le type que `task_executor` porte depuis
  toujours pour « the inference layer is down », retryable et jamais la
  faute de la tâche.

L'échec honnête n'est donc pas une politique nouvelle. Le message est
écrit pour que `runs.taxonomie` le classe **sans modification** :
`FOURNISSEUR`, remède `changer_de_fournisseur`, `reessayer=True`,
`changer_de_modele=False`. La machinerie de reprise de HOS-225 prend le
relais telle quelle.

L'arbitre, lui, ne lève pas : il n'exécute rien, et une exception depuis
un module qui ne fait que ranger des avis serait une décision d'exécution
déguisée.

### Le droit de monter, attribué au lieu d'être hérité

HOS-243 cherchait la montée vers le cloud sur **toutes** les
propositions. N'importe quelle source future qui aurait nommé
`openrouter` aurait donc hérité d'une autorité que personne ne lui avait
donnée.

Le droit est maintenant porté par la proposition elle-même
(`peut_monter`), faux par défaut, et accordé au seul décideur de la
tâche — c'est lui qui détient la porte d'escalade de HOS-066C. Une garde
lit le point d'appel réel : la règle est tenue là où elle s'exerce, pas
seulement là où elle est écrite.

### La frontière des deux routeurs, prouvée sur les appelants

HOS-243 la vérifiait sur les imports de deux fichiers nommés. Mesurée
cette fois en croisant les appelants réels des deux méthodes de
décision :

    core.router.ModelRouter.select_model        3 appelants
    AdaptiveModelRouter.recommend_for_text      2 appelants
    intersection                                AUCUNE

`service_registry` construit l'un et appelle l'autre : c'est une racine
de composition, elle câble et ne décide pas.

### Les gardes, vérifiées en les cassant

Chacune a été soumise à la violation qu'elle interdit, puis l'arbre
restauré. Les quatre détectent : reconstruction d'un point d'entrée
déprécié, routeur de rôles appelé depuis l'exécuteur missionnel, second
arbitrage, droit de monter accordé à une autre source.

### Mesures

7 gardes ajoutées, 4 réécrites (aucune supprimée). Suite complète :
**5 472 vertes**, 3 ignorées. Frontend : 126 vertes, typecheck propre.


## HOS-243 — Une seule autorité tranche, et elle l'écrit (2026-09-03)

Quatrième passe de consolidation, sur §5.1 : « il existe plusieurs
décideurs concurrents de routage ».

### Le compte est passé de deux à huit, en trois mesures

HOS-242 avait rapporté deux décideurs. La mesure était fausse par
méthode : elle comptait les **constructions de classes**, et manquait
tout composant obtenu par un accesseur ou un attribut. Retracés sur les
appels de méthodes, puis sur leurs définitions, **huit** composants
décident d'un runtime, d'un modèle ou d'un fournisseur.

Chaque hausse du compte venait du même défaut : chercher des noms plutôt
que des appels, puis des appels plutôt que des définitions. C'est la
troisième fois sur ce chantier qu'une cartographie se révèle incomplète
parce qu'elle cherchait la mauvaise chose.

### Huit décideurs ne sont pas un défaut

Ils répondent à huit questions, sur des chemins différents, chacun avec
ses propres données et ses propres mesures :

- `AdaptiveModelRouter` — profils mesurés, VRAM ; chemin missionnel ;
- `autonomous.DecisionEngine` — pose `assigned_runtime` sur un but ;
- `core.router.ModelRouter` — rôles de `config/models.yaml`, dont les
  tags portent les fenêtres de contexte servies ;
- `RuntimeRecommender` — planification, avant toute exécution ;
- `ral.courtier` — quel fournisseur cloud, une fois le runtime décidé ;
- `runtime.orchestrator.DecisionPipeline` — classe des candidats pour
  l'API d'observabilité ; **rien ne s'exécute sur son classement** ;
- `RuntimeDecisionEngine` — hors production (ci-dessous) ;
- `sds/routes.py` — un opérateur bascule le runtime actif par HTTP.

Le défaut était que **deux d'entre eux tranchaient la même requête** :

    runtime_id = _runtime_demande(assignment.runtime_id
                                  or task.assigned_runtime)   # ① ou ②
    ...
    runtime_demande = self._resolve_runtime(task)             # ①
    use_cloud = self._cloud_chat is not None and runtime_demande == "openrouter"
    if use_cloud:
        runtime_id = "openrouter"

Lequel l'emportait n'était écrit nulle part. C'était une **propriété
émergente de l'ordre des lignes** — dix lignes plus loin, un `elif` et un
`and` en décidaient. Une précédence qui n'est écrite nulle part ne peut
être ni discutée, ni testée, ni conservée à travers un refactoring.

### `ral.arbitrage` : l'arbitre, pas un neuvième décideur

Il ne classe aucun modèle, n'interroge aucun profil, ne mesure aucune
VRAM, ne contacte rien — deux gardes le tiennent, dont une qui refuse
qu'il devienne asynchrone. Il ne sait pas quel modèle est bon.

Il sait qui a le dernier mot, et il l'écrit. La précédence **reproduit le
comportement d'avant** : une assignation explicite l'emporte, puis le
décideur de la tâche, puis le défaut. La changer en même temps qu'on la
rendait explicite aurait rendu impossible de dire lequel des deux avait
causé une régression.

Une seule dérogation, celle qui existait déjà : le décideur peut faire
**monter** vers le cloud, et seulement si un fournisseur répond
vraiment. Il ne peut pas faire redescendre — défaire une assignation
explicite serait exactement la seconde autorité qu'on supprime.

`cloud_joignable` est un fait **passé par l'appelant**. Un arbitre qui
interrogerait lui-même les fournisseurs pourrait conclure « joignable »
sans passer par le pare-feu de données ni par le courtier : il
deviendrait une autorité de sécurité, ce que le RAL ne doit jamais être.

### La pile RAL, mesurée deux fois de plus

HOS-242 disait `RuntimeRouter`, `RuntimeDecisionEngine` et
`RuntimeSelector` « construits nulle part ». Ils **sont** appelés — mais
leurs seuls appelants sont `ExecutionEngine` et `MissionControlAPI`, dont
aucune n'est construite hors des tests, et le rappel `runtime_selector`
du superviseur n'est passé par personne.

Hors production, donc, mais par un chemin plus long que rapporté.
**Dépréciés explicitement, pas supprimés** : ils portent leurs propres
tests, et les effacer détruirait un travail mesuré sans rien corriger.
La dépréciation est dans leur docstring, là où on la lit, et une garde
échoue si un point d'entrée déprécié est reconstruit.

### Ce que la source dit maintenant

    A. cloud demandé, pas de clé  → ollama, « assignation explicite »,
                                    repli nommé
    B. cloud demandé, clé valide  → openrouter, fournisseur DeepInfra
    C. personne ne choisit        → hermes-agent,
                                    « défaut HOS-142 — aucun runtime choisi »

Le cas C est celui qui a coûté une nuit entière : `"default"` tombait
dans la boucle d'outils de Hermes OS au lieu d'aller à l'agent.

### Mesures

29 gardes ajoutées. Suite complète : **5 465 vertes**, 3 ignorées.
Frontend : 126 vertes, typecheck propre.


## HOS-242 — Le routage, mesuré : qui décide, qui exécute, qui le sait (2026-09-03)

Troisième passe de consolidation, sur §5. La question posée était
« pourquoi 13 modules contournent-ils le RAL ? ». La mesure a donné une
autre réponse.

### Les 13, classés

13 constructions réelles de `OllamaClient` en production, dans 8
fichiers — comptées sur l'arbre syntaxique, pas sur le texte.

- **5 sont de l'infrastructure** : `/api/ps`, `list_local_models`,
  `unload_model`. Aucune décision de routage : rien à router quand on
  demande à Ollama ce qu'il détient, ou qu'on lui fait libérer une carte.
- **1 est le RAL lui-même** : `sds/runtime.py` enregistre le
  constructeur `ollama` dans sa Factory. C'est la queue du chemin
  canonique, pas un contournement.
- **7 sont sur un chemin d'inférence**, et toutes reçoivent leur modèle
  d'un décideur injecté ou de leur appelant.

Aucune n'a été « faite passer par le RAL » pour améliorer un chiffre.
La cible n'était pas *tous les appels passent par le RAL*, mais *aucun
composant ne prend silencieusement une décision qui ne lui appartient
pas*.

### Ce qui n'était pas le défaut

`RealTaskExecutor` lit le runtime servi **dans la réponse**, jamais dans
la demande. `_make_cloud_chat` passe par le pare-feu de données puis par
le courtier avant tout envoi distant. La gouvernance de HOS-227 et
HOS-228 est bien sur le chemin, et deux gardes le tiennent désormais sur
l'ordre des lignes.

### Ce qui l'était : runtime et fournisseur étaient le même mot

`metadata["provider"]` valait `"ollama"` ou `"openrouter"` — c'est-à-dire
le **runtime**. Or OpenRouter n'exécute rien : il route vers un hébergeur
amont qu'il nomme dans un champ de premier niveau de sa réponse. Trois
fournisseurs pouvaient servir le même modèle avec trois latences, et
Hermes les appelait tous « openrouter ».

Le champ est désormais lu — **au champ structuré, jamais deviné**. Aucune
clé n'étant configurée sur cette installation, il n'a pas pu être observé
sur une réponse réelle : la lecture est défensive, son absence n'invente
rien, et la garde qui la tient le dit.

`runtime = ollama, fournisseur = local, modèle = qwen3.6-35b-a3b` — trois
faits distincts, là où il y en avait deux dont un dupliqué.

### Le repli distant → local était muet

Sans clé — le défaut mesuré en J17 : « 0 fournisseur configuré » — le
routeur recommandait le cloud, `_runtime_for` rendait « hermes-agent », et
**rien ne le disait**. Le registre inscrivait le runtime demandé :
l'opérateur croyait avoir payé du cloud.

Le repli reste **autorisé** — l'interdire ferait échouer toute mission sur
une installation sans clé, ce qui est le cas normal. Mais autorisé n'est
pas silencieux. Le run porte maintenant une colonne `decision` :

    {"runtime_demande": "openrouter", "runtime_servi": "ollama",
     "modele": "qwen3.6-35b-a3b", "fournisseur": "local",
     "repli": "openrouter indisponible, servi par ollama"}

Le repli n'y est nommé que lorsqu'il est **constaté** : un routeur qui n'a
rien demandé n'a pas été défait.

### Sept replis de routage retombaient en silence

Quatre dans `service_registry`, trois encore dans `task_executor` après
HOS-241. Un `except: return None` sur un rappel de décision rend « le
routeur n'a pas d'avis » et « le routeur est en panne » strictement
indiscernables — à l'endroit exact où la distinction décide du modèle qui
va tourner. Zéro subsiste, et une garde tient les deux modules ensemble.

### Deux autorités, et une pile morte

C'est la dette que cette passe **n'a pas** résorbée, et elle est
structurelle :

- `AdaptiveModelRouter` décide sur le chemin missionnel — mesures,
  VRAM, profils ;
- `core.router.ModelRouter` décide sur le chemin agentique — rôles
  déclaratifs de `config/models.yaml`.

Les deux répondent à « quel modèle », sur deux catalogues **sans aucun
lien** : le premier ne lit pas `models.yaml`, le second ne connaît pas les
profils. Ce sont bien deux autorités concurrentes.

Et `RuntimeRouter`, `RuntimeDecisionEngine`, `RuntimeSelector` — la pile
de décision du RAL — ne sont **construits nulle part** en production, pas
plus que le contrat `ral.model_router.ModelRouterInterface`, qui n'a
aucune implémentation. Le RAL déclare une autorité qu'il n'exerce pas.

Les unifier est un jalon, pas une passe : les deux décideurs sont
justifiés séparément par des mesures, et les fusionner sans mesure
recréerait exactement le genre de choix supposé que ce dépôt poursuit.

### Un septième faux positif de sous-chaîne, dans la garde elle-même

`runtime_id = "ollama"` contient « llama ». La garde qui interdit les tags
de modèles codés en dur s'y est accrochée. Réécrite pour exiger un chiffre
— un tag porte toujours une taille ou une version, une famille non.

### Mesures

Sur les 7 fichiers du chemin d'inférence :

| | avant | après |
|---|---|---|
| constructions `OllamaClient` | 6 | 6 |
| modules distinguant le fournisseur | 2 | 6 |
| replis de routage **muets** | 4 | **0** |
| replis de routage tracés | 6 | 10 |

23 gardes ajoutées. Suite complète : **5 437 vertes**, 3 ignorées.
Frontend : 126 vertes, typecheck propre.


## HOS-240, HOS-241 — Les runs qu'on perdait, et le modèle qu'on n'inscrivait pas (2026-09-03)

Deuxième passe de consolidation : les deux dettes structurantes du
journal des runs. Chacune observée **rouge** avant correction.

### `PERDU` existait dans le vocabulaire et rien ne le posait

HOS-221 l'écrivait dans son propre CHANGELOG. Neuf jalons plus tard,
c'était toujours vrai : un processus tué — `taskkill`, coupure, ou
simplement une exception qui traverse `execute_task` sans atteindre
`finalize()` — laissait ses runs `en_cours` pour l'éternité. La console
d'opérations affichait donc des runs actifs qui ne tournaient nulle part,
et le compteur « en cours » ne redescendait jamais.

**Pas un délai.** « `en_cours` depuis plus de N minutes ⇒ perdu » est
faux dans les deux sens : une mission longue sur un modèle local lent
dépasse n'importe quel N raisonnable et se ferait déclarer perdue *en
tournant*, tandis qu'un processus tué à la seconde 3 resterait `en_cours`
pendant N. Un délai mesure l'impatience de l'observateur, pas la mort du
porteur.

La preuve retenue est le porteur lui-même. Chaque run porte désormais
l'empreinte du processus qui l'a ouvert — `pid:date_de_démarrage`, écrite
une fois, à la naissance de la ligne. Ce n'est pas un battement de cœur :
rien n'est réécrit périodiquement. La date de démarrage n'est pas
décorative — les PID se réutilisent, et sans elle un nouveau processus
héritant du PID d'un mort ferait passer ses runs pour vivants.

Trois réponses et non deux : **vivant**, **mort**, **indécidable**. Une
empreinte illisible, un `psutil` absent ou un accès refusé ne prouvent
pas un décès, et les lignes ouvertes avant ce jalon n'ont aucune preuve
attachée. Elles sont comptées à part et signalées — jamais rangées avec
les morts.

`Cause.PROCESSUS` est ajoutée plutôt que réutiliser `INCONNUE`, qui
signifie « cherchée, non trouvée ». Ici la cause est constatée.

Vérifié sur le vrai `lifespan`, avec un vrai orphelin :

    réconciliation : 1 perdus, 0 vivants, 0 indécidables
    WARNING  1 run(s) perdus au démarrage
    GET /api/v1/operations → 200, nombre_en_cours: 0

### « Quel modèle a exécuté cette mission ? » n'avait pas de réponse

Pas une mauvaise réponse : **pas de réponse**. `modele` et `fournisseur`
existent comme colonnes depuis HOS-221, `vue_operations` les sert, le
Cockpit les affiche — et personne ne les écrivait. Elles valaient la
chaîne vide pour tous les runs jamais enregistrés.

`runtime`, lui, était écrit — mais à `ouvrir()`, donc **avant**
l'exécution, depuis `assigned_runtime`. C'est l'intention du
coordinateur, pas le fait.

**L'audit a réfuté sa propre prémisse.** Il cherchait des bascules
silencieuses dans `RealTaskExecutor` ; il n'y en avait pas là. Ce module
lit le runtime qui a servi **dans la réponse**, et son commentaire dit
que faire l'inverse « réintroduirait la malhonnêteté que R-001 existe
pour supprimer ». Le maillon manquant était le dernier : cette honnêteté
ne traversait pas jusqu'au registre. La correction est donc un câblage —
`Registre.constater()`, appelée avant `terminer()` parce qu'un run
terminal est gelé — et non une réécriture.

### La bascule silencieuse qui existait vraiment

`use_cloud = self._cloud_chat is not None and … == "openrouter"`. Sans
clé OpenRouter — le cas par défaut, mesuré en J17 : « 0 fournisseur
configuré » — une tâche explicitement assignée au cloud tournait en local
**sans un seul message**, et le registre inscrivait quand même
« openrouter ».

Et **six** rappels de résolution avalaient leur échec en `logger.debug`,
invisible au niveau par défaut. Deux portaient les bascules les plus
graves : `workspace_project_for`, dont l'échec fait tourner la tâche sans
outils ni pare-feu de données, et `num_ctx_for` — le piège le plus
coûteux de ce dépôt, celui qui fait dire à l'agent qu'il n'a pas d'outils
parce que les schémas ont été tronqués.

Ma première correction n'en couvrait que quatre. C'est la garde
elle-même, écrite trop étroite puis élargie à la découverte, qui a trouvé
les deux autres — elle énumère désormais les rappels au lieu de les
lister.

### Mesures

32 gardes ajoutées. Suite complète : **5 414 vertes**, 3 ignorées.
Frontend : 126 vertes, typecheck propre. Aucune régression.


## HOS-239 — Consolidation post-audit : trois défauts, une cartographie (2026-09-03)

Première passe de la mission de consolidation. Trois défauts corrigés,
chacun **observé rouge** avant correction, et une cartographie mesurée.

### La version d'OpenAPI contredisait la version produit

`FastAPI(version="1.0.0-rc1")`, écrite en dur. Une troisième valeur, à
côté de `frontend/package.json` (`0.1.0`) et de la version produit de
HOS-232 (`1.0.0`) — et c'est celle que **tout client lit** dans
`/openapi.json`.

Elle vient maintenant de `backend.maj.version`. `package.json` garde la
sienne, et c'est légitime : elle versionne le **paquet npm**, pas le
produit. Les rôles sont distincts ; les valeurs ne doivent pas se
contredire sur ce qu'est Hermes OS. Une garde AST interdit tout littéral
de version dans `main.py`.

### La cartographie backend → frontend, mesurée

25 sujets confrontés : ce que l'application sert vraiment contre ce que
`client.ts` appelle vraiment.

- **20 réellement raccordés** ;
- **3 servis sans consommateur** : `documents`, `logs`, `snapshots` ;
- **0 orphelin côté frontend** — aucun appel vers une route absente.

**Mon propre détecteur a produit cinq faux négatifs.** Il annonçait
approbations, points de reprise, Control Rooms, fournisseurs et
installation comme « backend seul » ; ils sont consommés, mais par
`operationsClient` en appels nommés que la recherche d'expression n'a pas
vus. Vérifié avant de le rapporter comme un manque — c'est exactement
l'erreur que cette mission interdit, et je l'ai commise dans l'outil de
mesure lui-même.

### Les couches événementielles, mesurées

Six noms existent. Comptés par fichiers et par publications réelles :
`SystemEventBus` (1 publication), `EventHub` (2), et quatre —
`EventDispatcher`, `EventBusImpl`, `MessageBus`, `RuntimeEventBus` — qui
**n'appellent jamais `publish` directement** dans le code de production.

Ce n'est pas six vérités concurrentes : c'est un bus durable
(`EventBusImpl`, sous la racine d'état depuis HOS-237), un concentrateur
que le frontend écoute (`EventHub`), et des façades qui délèguent. La
phrase qui l'explique tient : **un seul journal durable, un seul point de
diffusion, et des adaptateurs qui y écrivent.** Le reste du travail —
documenter producteur et consommateur pour chacun — reste à faire.

### Mesures

2 gardes ajoutées. Suite complète : **5 382 vertes**, 3 ignorées.
Frontend : 126 vertes, typecheck propre.


## HOS-236 — Les Control Rooms, et le 100 % qui n'existait pas (2026-09-03)

J17 final. Deux causes maintenaient le 🟠 : les Control Rooms, et une
vérification en navigateur non obtenue. Les deux sont levées.

### Le défaut : un agent qui n'a rien fait était noté parfait

`GET /api/v1/agents` rend `success_rate: 100.0` avec `total_tasks: 0`.
Et le Cockpit aggravait, à deux endroits d'`agent-center.tsx` :

    {(agent.success_rate ?? 100).toFixed(0)}%
    <ProgressBar value={agent.success_rate ?? 100} />

Un agent qui n'a **jamais rien exécuté** s'affichait donc à 100 %, barre
pleine. C'est le même mensonge que douze jalons ont chassé côté serveur,
à sa toute dernière étape — et le plus coûteux de sa famille, parce
qu'un taux affiché sur rien fait choisir un agent sur une réputation
qu'il n'a pas gagnée.

Zéro tâche n'est pas cent pour cent : c'est *aucune mesure*.
`_taux_mesure` rend donc un tri-état, la vue affiche « — jamais mesuré »,
et la barre de progression disparaît plutôt que de se remplir — une
barre à 100 % est une affirmation, et il n'y a rien à affirmer.

### La source canonique, et celle qu'il ne fallait pas prendre

Deux registres d'agents existent. `core.agent_registry` ne porte que les
agents Ollama configurés ; `AgentSupervisor` est celui que
`GET /api/v1/agents` sert déjà. S'être branché sur le premier aurait
donné une **seconde vérité sur ce qu'est un agent**. Une garde le tient,
sur les imports et non sur le texte.

Une Control Room assemble donc : l'identité et l'état depuis le
superviseur, les runs depuis le registre de HOS-221, la confiance depuis
son propre moteur — relayée telle quelle, puisqu'il dit déjà « unknown »
quand il ne sait pas. Aucun magasin neuf.

### La vérification en navigateur, obtenue

Les deux serveurs bloquants étaient exactement ceux de
`.claude/launch.json` — l'uvicorn du dépôt et son Next dev, identifiés
par ligne de commande avant d'y toucher. Redémarrés proprement.

Constaté sur le navigateur, en données réelles :

- **10 routes** `/operations` dans `openapi.json`, `200` sur chacune ;
- Supervision affiche 206 approbations, 3 points de reprise, 10 contrôles
  de santé, 0 fournisseur configuré ;
- « Version installée : jamais marquée » — pas la version du code ;
- « Aucun run en cours. **Mesuré, pas supposé.** » ;
- « Aucun fournisseur distant configuré. C'est le défaut. » ;
- deux points de reprise marqués **« fichiers seuls »**, un troisième
  avec état ;
- **10 Control Rooms**, chacune « — jamais mesuré » et « non
  disponible » ;
- la source sous chaque section.

### Un cinquième faux positif de sous-chaîne

Ma garde « la Control Room ne prend pas `core.agent_registry` »
s'accrochait à la docstring qui **explique** pourquoi elle ne le prend
pas. Cinquième fois sur ce chantier. Réécrite sur les imports.

### Ce qui reste volontairement hors J17

Les **analytiques** — missions, coûts, latences, taux de bascule. Elles
figurent dans la description de J17 mais **pas dans ses critères de
sortie**, et les fabriquer maintenant pour obtenir un vert serait
exactement ce que ce jalon interdit. Elles appartiennent à la vue que
J18 rendra extensible.

### Mesures

Backend : **5 361 vertes**. Frontend : **126 vertes**, typecheck propre.
7 gardes backend et 3 frontend ajoutées.


## HOS-235 — La console d'opérations, et le routeur que rien ne servait (2026-09-03)

J17 final. L'audit du frontend a donné deux surprises, l'une bonne et
l'autre grave.

### Le défaut : les huit routes de J17 étaient injoignables

HOS-234 les avait posées sur `MissionControlAPI`. Vérifié **sur le
processus en marche** : `GET /api/v1/operations` rendait `404`, et
`/openapi.json` ne contenait pas une seule route en `/api/v1/`.

`MissionControlAPI` existe, est exportée, et **aucun appelant de
production ne l'inclut dans l'application**. Le jalon était juste dans sa
forme et inexistant dans les faits — la variante la plus coûteuse de
l'orphelin, parce que ses tests passaient : ils montaient le routeur
eux-mêmes.

Les routes vivent maintenant dans `backend/api/routes/operations.py`,
listé dans `_LEGACY_ROUTERS`, c'est-à-dire sur le seul chemin que
`backend.main` sert réellement. Une garde interroge désormais
`TestClient(backend.main:app)` — l'application, pas un routeur monté pour
l'occasion — et une autre lit l'arbre syntaxique de `main` pour vérifier
que le module est bien dans la liste de montage.

### La bonne surprise : le Cockpit était déjà mûr

`FluxEvenements` est **l'unique** souscription au bus, et pousse dans
`useCockpitStore` — HOS-182 avait déjà corrigé le défaut des sockets
multiples. Le scaffolding (`CenterHeader`, `AsyncPanel`, `StatGrid`,
`Card`, `Badge`), les hooks TanStack, la navigation typée par
`satisfies` : tout existait. Rien n'a été recréé.

Et le frontend ne fabrique plus de compteurs : les `Math.random()`
restants sont des identifiants, une graine de studio, ou des
**commentaires documentant des fabrications retirées**.

### Le tri-état, jusqu'au pixel

Quatre choses s'affichent différemment, parce qu'elles ne veulent pas
dire la même chose :

- **zéro mesuré** — « Aucun run en cours. Mesuré, pas supposé. »
- **non mesurable** — un encadré ambré portant la raison, jamais un zéro.
  Un indicateur dont la source n'a pas répondu affiche « — ».
- **cause `null`** — « cause non démontrée » ;
- **cause « inconnue »** — « cherchée · non trouvée ».

Douze jalons ont travaillé côté serveur à ce qu'un « on ne sait pas » ne
se range jamais avec un « c'est bon ». Le refaire à l'affichage
l'annulerait à la dernière étape.

Trois cas particuliers portent la même règle : un contrôle de santé
`indisponible` s'affiche « sans objet » et non en rouge — une
installation neuve n'a pas de points de reprise, et le peindre en panne
ferait chercher un défaut qui n'existe pas. « Aucun fournisseur
configuré » est présenté comme **le défaut**, pas comme une panne. Et une
version jamais marquée n'est pas remplacée par celle du code.

### Une vue, jamais une seconde autorité

Toutes les routes sont en `GET`. Le modèle de lecture n'appelle rien qui
écrive et n'ouvre aucun magasin — deux gardes sur l'arbre syntaxique. La
trace vient du store, pas d'une seconde socket.

Et elle ne fabrique aucune activité : si le runtime n'émet rien, la liste
reste vide, avec la phrase qui le dit — « pas de battement de cœur
inventé ».

### Deux orphelins évités

Une garde du dépôt — `surface-api.test.ts`, que je ne connaissais pas —
a refusé `useOperationsLignee` et `useOperationsContrat` : deux hooks sans
consommateur. Elle avait raison. Ils sont maintenant branchés sur un
panneau de détail qui déplie la lignée d'un run et son contrat, critère
par critère, avec les quatre états de HOS-221 distingués visuellement.

Un contrat absent affiche « aucun contrat déposé » plutôt qu'un contrat
vide, qui se lirait « tenu ».

### Une collision de libellés

Ma vue s'appelait « Opérations » — comme le **groupe** de navigation qui
la contient. Deux entrées du même nom dans une navigation se cherchent
l'une l'autre. Renommée « Supervision ».

### Ce qui n'est pas démontré

**La vérification en navigateur.** Les deux serveurs de développement en
marche sont antérieurs à ces changements — le backend rend encore `404`
sur `/operations`, et le Cockpit sert un paquet où la vue n'existe pas.
Les redémarrer aurait demandé d'arrêter des processus qui ne sont pas les
miens.

Ce qui **est** démontré : les huit routes servies par
`backend.main:app` avec son lifespan complet, sur les données réelles —
206 approbations en attente, 3 points de reprise, 10 contrôles de santé,
0 fournisseur configuré — et dix gardes sur la vue qui prouvent le
tri-état, les quatre états d'une cause, le nommage des sources et
l'absence de fabrication.

### Mesures

Backend : **5 353 vertes**. Frontend : **123 vertes**, typecheck propre.
13 gardes ajoutées côté backend, 10 côté frontend.


## HOS-234 — Ce que douze jalons ont produit, enfin lisible (2026-09-03)

Le jalon 17. Prémisse mesurée avant d'écrire : **aucune route n'exposait**
le registre des runs (J5), le contrat, les points de reprise (J7), la
portée des approbations (J8), les causes d'échec (J9), le pare-feu (J11),
le courtier (J12), le relais (J13), la boucle (J14) ni la mise à jour
(J16). Douze jalons de travail, invisibles à toute interface.

### Ce qui existait, et qu'il ne fallait pas refaire

`MissionControlService` — 1 242 lignes — et son `MissionControlAPI`, avec
un WebSocket d'événements. La première recherche donnait « 2 routes pour
le registre, 2 pour la boucle » : c'étaient des **commentaires**, l'un
sur le registre de sessions ACP, l'autre sur la boucle d'événements
asyncio. Encore un faux positif de sous-chaîne, et la raison pour
laquelle la mesure s'est poursuivie jusqu'à trouver la vraie surface.

Les huit routes de ce jalon s'y branchent. Aucun service neuf, aucun
magasin neuf.

### Ce que le frontend faisait déjà bien

Contrairement à ce qu'on pouvait craindre, il ne fabrique plus de
compteurs. Les `Math.random()` restants sont des identifiants, une graine
de studio, ou des **commentaires documentant des fabrications retirées** :
`deployment-center` dormait 1 500 ms et rendait `Math.random() * 20 + 30`,
`model-intelligence-center` attendait 600–1 000 ms avant de répondre. Le
commentaire de `telemetry-trace.tsx` dit ce qu'on en a retenu —
« `Math.random()` would have made a prettier picture and a dishonest
one ».

Une garde le vérifie désormais plutôt que de l'espérer, en exemptant les
graines : un aléa **demandé** est le contraire d'une mesure inventée, et
la distinction est dans l'intention, donc dans le nom.

### Une vue, jamais un second runtime

Les huit routes sont en `GET` seulement, et deux gardes sur l'arbre
syntaxique le tiennent : le modèle de lecture n'appelle rien qui écrive —
`ouvrir`, `terminer`, `prendre`, `restaurer`, `appliquer`, `decide`,
`signaler_echec` — et n'importe aucun magasin.

La raison n'est pas esthétique. Une vue qui écrit devient un second
chemin vers l'état, et deux chemins vers l'état, c'est la question
« lequel fait foi ? » à chaque incident.

### Chaque section dit d'où elle vient

`source` accompagne chaque bloc : `backend.runs.registre`,
`backend.ral.courtier`, `backend.security.approvals`,
`backend.checkpoints`, `backend.maj`. Une vue qui nomme ses sources rend
la fabrication visible au relecteur suivant.

### Ce qui est absent est dit absent

Un système indisponible rend `disponible: false` **avec sa raison**,
jamais un zéro. Un zéro se lit « rien ne s'est passé » ; une
indisponibilité se lit « on ne sait pas ». C'est la règle tri-état de
HOS-222 appliquée à l'affichage — et c'est là qu'elle compte le plus,
parce que c'est là qu'un humain décide.

Une section qui lève ne fait pas tomber la vue : les autres sont
justement ce qu'on regarde quand une chose va mal.

Et « aucun fournisseur configuré » est marqué comme un **état normal** :
aucune clé n'est posée par défaut, et le taire le ferait lire comme une
panne.

### Le vocabulaire des jalons traverse jusqu'à l'affichage

Une cause non démontrée reste `null`, jamais « inconnue » (HOS-225). Les
critères invérifiables sont **séparés** des critères violés (HOS-222). Un
point de reprise dit s'il porte l'état de mission, parce que sans lui il
ne ramène que la moitié (HOS-223). Les portées d'approbation vivantes
sont listées à part des accords exacts, parce qu'une ligne qui autorise
un dossier entier ne se lit pas comme une qui autorise une action
(HOS-224).

### Une version fabriquée, retirée

`GET /api/v1/version` rendait `"0.1.0"` en dur, avec une liste de modules
arrêtée à `HOS-028` — donc une version qui ne désignait rien et une liste
fausse depuis deux cents jalons.

Elle rend maintenant la version produit (HOS-232) **et** la version
installée (HOS-233), qui peuvent différer : c'est précisément l'écart
qu'on veut voir après une mise à jour dont le marquage n'a pas eu lieu.
Le test qui gardait `"0.1.0"` est **amendé, pas supprimé** — même
propriété, valeur réelle.

### Ce qui reste hors périmètre

Les **vues React** — Agent Control Rooms, trace d'exécution vivante,
analytiques. Elles sont une pièce en soi, et elles n'étaient pas
constructibles avant : il n'y avait rien à afficher. C'est maintenant le
cas.

### Mesures

Vérifié sur l'installation réelle : 206 approbations en attente, 3 points
de reprise, 10 contrôles de santé, 0 fournisseur configuré. 20 gardes
ajoutées, 1 amendée. Suite complète : **5 340 vertes**, 3 ignorées.


## HOS-233 — Le moteur de mise à jour, pour de bon (2026-09-03)

J16.1. HOS-232 sauvegardait l'état et le restaurait ; il ne touchait pas
au code. Le moteur n'était donc pas un moteur de mise à jour — c'était un
filet. Audit d'abord, trois défauts mesurés, puis le reste.

### Le défaut que la garde de J16 n'a pas vu

`workflows` vit sous la racine d'état **réelle** — huit dossiers sur le
disque, sept déclarés dans `SOUS_DOSSIERS`. Un résidu de la migration
HOS-215, dont la classification a été annulée depuis mais dont la copie
est restée.

La garde de HOS-232 ne l'a pas trouvé **parce qu'elle lit le code et non
le disque**. Elle cherchait `racine() / "..."` dans les sources : un
dossier créé par un chemin qui n'a plus de producteur lui est invisible.

D'où les **trois sources** du jalon :

1. la liste déclarative, `preserve_set()` ;
2. l'**observation du disque** — tout répertoire présent sous la racine
   et absent de la liste est sauvegardé quand même, et signalé ;
3. le **manifeste** de la sauvegarde, qui porte les deux et fait foi au
   retour arrière.

Perdre la donnée serait pire que la sauver sans l'avoir déclarée. Mais
le silence serait pire encore — c'est ainsi que `checkpoints` est passé,
puis `workflows`.

### Le secret de l'utilisateur vit dans l'arbre de code

Mesuré : `SettingsConfigDict(env_file=".env")` résout depuis le
répertoire courant, donc **à la racine du dépôt**. La clé OpenRouter vit
dans l'arbre que la mise à jour remplace, et un remplacement naïf
l'aurait détruite.

Elle est donc **préservée en place** : ni copiée, ni remplacée. Pas
copiée parce qu'une sauvegarde de secret est un secret de plus, en clair,
dans un dossier que personne ne surveille. Pas remplacée parce qu'elle
est à l'utilisateur. Quatre gardes négatives vérifient qu'un secret de
test ne se retrouve ni dans la sauvegarde, ni dans le manifeste, ni dans
les journaux, ni dans le rapport de santé — le **nom** `.env` y figure,
lui, pour qu'un lecteur puisse vérifier qu'il a été protégé.

### Le remplacement, et ce que Hermes doit protéger en plus

Le patron vient d'Agent OS, dont l'`UPDATE.md` le dit sans détour :
*« what an update DOES replace: the app code itself »*, avec une
sauvegarde datée de l'ancienne version à côté.

Trois choses qu'ils n'ont pas à protéger, et Hermes si :

- **le dépôt git** — leur dossier d'application n'en est pas un. Ici
  `.git` porte l'historique, la branche, l'index et le travail non
  commité. Un test avant/après vérifie que `HEAD`, la branche, l'index
  et un fichier non commité survivent à une mise à jour réussie ;
- **le `.env`**, ci-dessus ;
- **`.venv` et `node_modules`** — des gigaoctets qui se reconstruisent.
  Les sauver ferait de chaque mise à jour une copie de plusieurs minutes,
  donc une mise à jour qu'on ne lance pas.

La règle tient en une phrase : **ce qui est remplacé est sauvegardé ; ce
qui est préservé en place n'est ni sauvegardé ni remplacé.** Il n'y a pas
de troisième catégorie, et c'est ce qui rend le retour arrière exact.

### L'ordre, et ce qu'il coûte de se tromper

    paquet → compatibilité → sauvegarde état → sauvegarde code
          → remplacement → migration → self-check → marquage
                                    ↘ échec → retour arrière (code puis état)

Le **paquet est validé avant toute sauvegarde** : un paquet refusé ne
doit rien coûter, et surtout pas laisser une sauvegarde orpheline.
Mesuré : un paquet sans `hermes.json` produit zéro étape et zéro
sauvegarde.

Le retour arrière remet le **code d'abord**, l'état ensuite : restaurer
un état ancien sous un code neuf donnerait le seul état que rien ne sait
lire.

### Un défaut trouvé par un test que j'écrivais

`restaurer()` sautait les dossiers absents de la sauvegarde. Une
sauvegarde vidée restaurait donc **zéro dossier** et se déclarait
réussie : une perte de données silencieuse déguisée en retour arrière.

Le test `un_echec_de_retour_arriere_est_fatal` l'a pris en défaut avant
que quiconque s'en serve. `restaurer()` vérifie maintenant, **avant
d'écrire**, que tout ce que le manifeste annonce est présent, et lève
sinon. Un backup non restauré n'est pas une preuve de rollback.

### La compatibilité : aucune mise à jour aveugle

Quatre cas décidés. Une **installation sans version** est acceptée —
c'est le cas de toutes celles qui existent, et la refuser interdirait la
première mise à jour à tout le monde. Une version **trop ancienne** est
refusée. Un **retour en arrière** est refusé par cette porte : c'est un
`restaurer()`, pas un `appliquer()`, et cette porte n'a pas les
migrations descendantes. **Réinstaller la même version** est permis :
c'est une réparation légitime.

### Les migrations : le cas A constaté, le cas B gardé

**Le mécanisme vivant est `memory/db.py::_add_missing_columns`.** Il
tourne à chaque `init_db()`, ajoute les colonnes nullables que les
modèles déclarent, et **refuse bruyamment** les non-nullables —
« Schema drift needs a real migration ». C'est lui qui a porté les
colonnes de portée d'approbation (HOS-224) sur les bases existantes. Il
est dans le self-check, puisque celui-ci appelle `init_db`.

**`MigrationManager` reste dormant.** Il a un vrai `migrate()` et des
migrations codées en dur à la version 1, et il est orphelin depuis
HOS-221. Deux moteurs de schéma sur la même base, c'est la question
« lequel fait foi ? » à chaque incident. Un test tombe si quelqu'un le
rebranche.

Aucun troisième moteur n'est écrit : il n'y a pas de besoin réel, et en
écrire un sans besoin produirait du code que rien n'exerce.

### Le self-check touche à dix invariants

Racine d'état, registre des runs, base applicative, approbations,
configuration, bus d'événements, RAL, instantanés de mission, points de
reprise, interpréteur de Hermes Agent. Chacun **ouvre** ce qu'il vérifie.

Il rend un rapport **structuré** et non un booléen : « ça ne va pas » ne
dit ni quoi restaurer ni quoi réparer. Et chaque contrôle est tri-état —
`INDISPONIBLE` n'est pas un échec, parce qu'une installation neuve n'a
pas de points de reprise et qu'en exiger un ferait échouer la première
mise à jour de tout le monde.

Sur l'installation réelle : neuf `ok`, un `sans objet`.

### L'état opérationnel est recalculé, pas restauré

Un cooldown de fournisseur décrit **maintenant**, et un retour arrière
change ce maintenant. Le restaurer réappliquerait un écart décidé pour un
incident qui appartenait à l'installation d'avant.

Constaté sur le code plutôt que décrété : le courtier (HOS-228) est déjà
sans état persistant, et son propre commentaire le dit. Il est remis à
zéro explicitement après un retour arrière, plutôt que de compter sur un
redémarrage qui n'aura peut-être pas lieu.

### Ce qui reste hors périmètre, et pourquoi

Le **téléchargement**. `appliquer()` reçoit un chemin vers un répertoire
local déjà extrait. D'où vient ce chemin est la question du canal de
distribution, qui n'existe pas — et une archive poserait en plus la
question de ce qu'on fait d'un `..` à l'intérieur, qui est un problème de
sécurité à part entière. Un test vérifie que les trois modules n'ont
gagné ni `httpx`, ni `urllib`, ni `subprocess`, ni `socket`.

### Mesures

46 gardes ajoutées, 26 amendées ou conservées. Suite complète :
**5 320 vertes**, 3 ignorées.


## HOS-232 — Mettre à jour sans perdre ce que quinze jalons ont construit (2026-09-03)

Le jalon 16. La prémisse était juste — `installer/` fait 378 lignes et ne
contient que de la détection — mais en la vérifiant, deux choses de plus
sont apparues, dont une grave.

### Le défaut : `preserve_set()` ne couvrait pas les points de reprise

HOS-215 a écrit la liste de ce qu'une mise à jour ne doit jamais toucher.
HOS-223 a créé `checkpoints` sous la même racine **deux jalons plus
tard**, hors de la liste. Rien ne l'a signalé, pour une raison simple :
**rien ne consommait `preserve_set()`**.

Une mise à jour aurait donc effacé les points de reprise — c'est-à-dire
le seul moyen d'annuler ce qu'elle aurait cassé. Le défaut que HOS-215
avait fermé, rouvert par le jalon qui construisait le filet.

La correction n'est pas d'ajouter un nom à la liste. C'est
`test_tout_ce_qui_vit_sous_la_racine_est_preserve`, qui **lit le code** —
qui écrit où sous la racine — plutôt que de relire la liste. Aucune
relecture de la liste n'aurait trouvé ce trou : il fallait regarder
ailleurs. **Une liste que rien ne vérifie contre la réalité est une liste
qui dérive.**

### Hermes OS n'avait pas de version

Trois versions existaient dans le dépôt — `SNAPSHOT_VERSION` pour le
format des instantanés, `SCHEMA_VERSION` pour le graphe de mission,
`_KT_VERSION` pour une bibliothèque tierce — et **aucune ne désignait le
produit**.

On ne revient pas à une version qu'on n'a jamais nommée. Elle est écrite
sous la racine d'état et non dans le dépôt, parce que la question « d'où
viens-je ? » se pose au moment précis où le dépôt vient d'être remplacé.
Une version illisible vaut `0.0.0` plutôt que de lever : lever
bloquerait exactement l'installation qui vient réparer.

### La séquence, et son ordre

    sauvegarde → migration → installation → validation → marquage
                                                     ↘ échec → retour arrière

**La sauvegarde d'abord** : après elle, tout est réversible. C'est le
seul échec qui arrête avant d'avoir rien touché, et c'est celui qu'il faut
arrêter — sans sauvegarde, rien ne l'est.

**Le marquage en dernier**, après la validation. Posé avant, il ferait
croire à une mise à jour réussie qui ne l'est pas, et le retour arrière
suivant repartirait du mauvais point. Une garde sur l'arbre syntaxique
tient l'ordre — par **numéro de ligne**, une première version comparant
des positions de parcours en largeur qui ne voulaient rien dire.

Mesuré de bout en bout : une installation qui saccage la base et supprime
un point de reprise avant d'échouer laisse, après retour arrière, la base
intacte, le point de reprise revenu et la version inchangée.

### Trois choix qui rendent le retour arrière honnête

**La sauvegarde porte sa propre liste.** Un retour arrière restaure ce
qui a été **sauvé**, pas ce que la version d'aujourd'hui croit qu'il
fallait sauver — une version qui aurait ajouté un dossier ne doit pas
prétendre le restaurer depuis une copie qui ne le contient pas.

**Il retire avant de copier.** Une copie par-dessus laisserait les
fichiers que la version fautive a créés, et un état mi-ancien
mi-nouveau est pire que l'un ou l'autre.

**Un retour arrière impossible est dit fort.** L'installation a échoué
*et* le retour aussi : c'est le pire cas, et le taire laisserait un état à
mi-chemin que personne ne sait diagnostiquer.

### L'auto-vérification touche à la vraie base

Elle ouvre le registre des runs. Une auto-vérification qui ne ferait
qu'importer des modules passerait sur une base corrompue — un test sur
l'arbre syntaxique l'exige.

### Ce qui n'est délibérément pas écrit

Le **remplacement du code** : télécharger une version, échanger
l'arborescence. Cela demande un canal de distribution qui n'existe pas, et
l'écrire sans lui produirait un mécanisme non éprouvable. La fonction
d'installation est donc **injectée**, ce qui rend la séquence testable
pour de bon — avec une installation qui échoue exprès. Un test vérifie
que le module n'a gagné ni accès réseau ni lancement de processus.

### Mesures

26 gardes ajoutées. Suite complète : **5 274 vertes**, 3 ignorées.


## HOS-231 — Ne pas juger un modèle sur un échec qui n'est pas le sien (2026-09-03)

Le jalon 15. La prémisse avait déjà été corrigée : `update_performance` et
`record_feedback` **sont** branchés, via
`service_registry._record_feedback` → `RealTaskExecutor.on_execution`. Ce
qui manquait était plus précis, et mesuré :

- `ModelPerformanceRecord.error_type` existe depuis HOS-062 et **n'est
  renseigné par personne**. Deux modules le relisent ; aucun ne l'écrit.
- `update_performance` compte `success=False` dans
  `historical_success_rate` **quelle qu'en soit la raison**. Un refus
  d'admission VRAM, un quota épuisé, une coupure réseau et une mauvaise
  réponse abaissaient identiquement la note du modèle.

C'est le thème central du dépôt appliqué à sa propre télémétrie : *ni un
échec sur parole*. Sur huit défauts de mesure trouvés pendant la
construction du catalogue, **cinq produisaient de faux échecs** — et ce
mécanisme-ci les aurait tous inscrits au passif du modèle.

### La table des causes imputables tient en trois entrées

`modele`, `semantique`, `verification`. Le reste décrit la machine, le
réseau ou une décision humaine, jamais la compétence de ce qui a été
appelé.

Deux absences délibérées, et ce sont les plus importantes :

**`contexte` n'y est pas.** C'est le cas le mieux documenté du dépôt.
CLAUDE.md : « une réponse tronquée n'est pas une erreur de raisonnement
et ne doit pas se noter comme telle ». Le départage de code a coupé
qwen3.6-35b en plein milieu et l'a noté comme une faute, alors que
c'était le réglage de la fenêtre qui était en cause.

**`inconnue` n'y est pas non plus.** Attribuer au modèle ce qu'on n'a pas
su expliquer est exactement la façon dont on a déjà disqualifié des
modèles compétents.

### Vide et « inconnue » ne disent pas la même chose

Une cause **vide** signifie « personne n'a transmis de cause » — un
appelant d'avant ce jalon — et son comportement est conservé : l'échec
compte, comme avant. Une cause `inconnue` signifie qu'on a cherché sans
trouver. Seul le second état veut dire qu'on a regardé, et les confondre
aurait fait disparaître en silence toutes les notes d'échec des
producteurs non migrés.

### La trace reste complète

L'échec a eu lieu : c'est le **jugement** qui est étroit, pas la trace.
Les onze lignes de l'essai — sept non imputables, deux imputables, deux
réussites — sont toutes dans l'historique. Un historique amputé rendrait
impossible de savoir qu'un modèle tombe systématiquement sur des refus de
VRAM, ce qui est une information réelle, sur autre chose que sa
compétence.

### Le chemin, de bout en bout

`RealTaskExecutor` classe l'exception avec la taxonomie de HOS-225 aux
**cinq** sites d'échec — une garde sur l'arbre syntaxique vérifie
qu'aucun n'est oublié, un site manquant laissant passer des échecs non
classés que le profileur compterait comme avant, sans que rien le dise.

Le rappel `on_execution` reçoit la cause en argument supplémentaire, et un
appelant d'avant ce jalon qui ne l'accepte pas continue de fonctionner :
la télémétrie ne fait jamais échouer le travail qu'elle décrit.

### Ce que le Trust reste

Une donnée **décisionnelle**, pas une autorité de sécurité. Aegis reste
au-dessus, et rien ici ne décide d'autoriser quoi que ce soit.

### Mesures

20 gardes ajoutées. Suite complète : **5 248 vertes**, 3 ignorées.


## HOS-230 — La boucle, assemblée et non recréée (2026-09-03)

Le jalon 14. Prémisse mesurée : **deux pilotes de reprise existent, et
aucun ne connaît de contrat.**

- `node_execution` fait tourner un `while task.status == PENDING`. Il
  reprend les pannes de **runtime**, parce que `execute_task` remet la
  tâche en attente ; il ne sait rien de ce qui devait être vrai à la fin.
- `retry_policy.decide` travaille au niveau de la **mission**, uniquement
  sur contradiction, et `graph_executor._suggest_retry` **publie** au
  lieu de relancer — avec sa raison, qui est juste : « relaunching a
  mission graph is the caller's decision (it owns scheduling, budgets and
  the operator's consent) ».

Ce module ne contredit pas ce choix. La boucle est une **bibliothèque que
l'appelant pilote**, pas un relanceur caché : `tourner()` ne part que si
quelqu'un l'appelle, et rend ce qu'elle a constaté.

### Ce n'est pas une seconde boucle agentique

La règle qui prime sur tout dans ce dépôt a déjà été violée une fois —
`RealTaskExecutor` sélectionnait Hermes Agent puis l'écrasait deux lignes
plus bas par sa propre boucle d'outils, et
`test_hermes_agent_is_the_brain.py` en garde la trace.

Cette boucle-ci ne raisonne pas, ne choisit aucun outil et **n'appelle
aucun modèle**. Elle enchaîne deux fonctions que l'appelant lui fournit
et décide seulement de continuer ou de s'arrêter, sur des verdicts et des
causes mesurés ailleurs. Un test sur l'arbre syntaxique vérifie qu'elle
n'importe ni client, ni adaptateur, ni runtime : c'est de
l'ordonnancement, pas de la cognition.

### Six arrêts, parce qu'ils n'appellent pas la même suite

`contrat_tenu`, `budget`, `cause_non_reprenable`, `inverifiable`,
`erreur`, `sans_contrat`. Les fondre en un booléen ferait chercher un
défaut de compteur là où il y a un refus assumé — exactement l'erreur que
HOS-225 avait déjà eu à corriger dans l'abandon d'une tâche.

Trois de ces arrêts portent tout l'intérêt du jalon :

**`inverifiable` arrête sans user le budget.** On ne reprend pas sur une
ignorance, et surtout on ne la range pas du côté du succès (HOS-222).
Boucler ici dépenserait le budget à re-produire une mesure qui n'aboutit
pas.

**`cause_non_reprenable` arrête au premier tour.** Réessayer un refus de
politique inonde la file d'approbation — ce que `approvals.py` décrit
déjà. La taxonomie de HOS-225 le dit, la boucle l'applique.

**`sans_contrat` refuse de tourner.** Boucler sur rien produirait des
tours qui se déclareraient réussis parce qu'aucun critère ne les
contredit : le `success: true` au-dessus de rien, en boucle.

### Le verdict du vérificateur ne suffit pas

Un vérificateur qui dit « réussi » sur un contrat à trois critères dont
un seul est tenu ne clôt rien : la **conjonction du contrat** prime, et
c'est elle qui décide. Une vérification illisible vaut `INDISPONIBLE`,
jamais `REUSSI` par défaut d'information.

### Le point de reprise est proposé, jamais appliqué

La boucle prend un point de reprise avant le premier tour — une fois, pas
un par tour — et rend son identifiant. Elle ne restaure **jamais** d'elle
-même : l'appelant décide, et la restauration passe par Aegis (HOS-223).
Une boucle qui effacerait un workspace de son propre chef serait le geste
destructeur le moins surveillé du système. Un test sur l'arbre syntaxique
vérifie qu'aucun appel de restauration n'y figure.

### Assembler, pas recréer

Tout vient d'ailleurs, et c'est le point : le contrat et sa conjonction
(HOS-221), le verdict tri-état (HOS-222), le point de reprise (HOS-223),
la cause et son remède (HOS-225), le relais et ses phases (HOS-229). Le
budget par défaut est celui de `retry_policy`, et un test le vérifie —
deux valeurs qui divergent, c'est deux politiques de reprise.

### Mesures

20 gardes ajoutées. Suite complète : **5 228 vertes**, 3 ignorées.


## HOS-229 — Ce qui doit survivre au changement de modèle (2026-09-03)

Le jalon 13. Deux manques mesurés avant d'écrire une ligne.

**Le contrat n'arrivait jamais au modèle.** HOS-221 a créé `Contrat` —
ce qui doit être vrai à la fin — **et** la colonne `contrat` du registre
des runs. Vérifié : rien n'y écrivait, rien ne l'y relisait, et
`backend.runs.contrat` n'était importé que par `verification.py`, pour
son énumération `Verdict`. Le modèle chargé de satisfaire des critères ne
les voyait pas.

**Aucune preuve de vérification n'atteignait un prompt.** `retry_policy`
construit bien un mémoire de reprise à partir du verdict, mais au niveau
de la *mission* et seulement sur contradiction. Une tâche qui vient
d'être vérifiée ne sait pas ce que la vérification a dit.

### Un relais, et pas une session

`_upstream_results_for` portait déjà la règle dans son commentaire :
« carried as plain text on purpose: it has to survive the model being
swapped between two tasks, which anything held as KV cache or a provider
session would not ». Le relais l'applique aux **phases**.

Sur 16 Gio, Hermes ne fait pas tourner quatre modèles à la fois ; il
enchaîne — planificateur cloud, exécutant local, vérificateur cloud,
réparateur local. Entre deux flèches, le modèle change, le fournisseur
peut changer, et le processus distant n'a aucune mémoire du tour
précédent. **Ce qui n'est pas écrit dans le relais n'existe pas au tour
suivant.**

### Chaque phase reçoit ce dont elle a besoin, et pas le reste

Un relais qui donnerait tout à tout le monde serait un prompt géant, et
un prompt géant sur 16 Gio est une fenêtre qui se ferme.

- **planification** : l'objectif et les outils. **Pas le contrat** — elle
  est censée le produire, et le lui donner ferait planifier contre des
  critères qu'on lui demande d'établir.
- **exécution** : le contrat, les résultats amont, les outils. Pas
  l'échec du tour précédent : une première exécution n'a rien raté.
- **vérification** : le contrat, les artefacts, les preuves — et **pas**
  le contexte de l'exécutant. Un vérificateur à qui l'on montre
  l'intention juge l'intention : c'est exactement le défaut du
  2026-08-30, où le relecteur a accepté l'image conforme au prompt et
  rejeté la bonne.
- **réparation** : tout cela, plus **ce qui a échoué** et sa cause.

Les décisions déjà prises vont à toutes les phases : une phase qui ignore
qu'une approbation a été refusée reproposera la même action.

Et « aucun artefact » est écrit comme un constat à faire remonter, pas
comme un silence.

### Le rôle `double_check`, enfin routé

Les rôles de `config/models.yaml` existaient tous — `swift`, `standard`,
`code`, `reasoning`, `double_check`… — et étaient choisis par **type de
tâche**. Rien ne les reliait à une **phase**. `double_check` est le cas
qui le montre : configuré depuis HOS-065C, et **aucune vérification n'y
était jamais routée**.

La vérification va donc à un autre rôle que l'exécution, pour une raison
simple : un modèle qui relit sa propre sortie confirme sa propre sortie.
Un test vérifie que chaque rôle nommé existe bien dans la configuration —
un rôle absent se résoudrait en silence sur autre chose, et la phase
tournerait sur un modèle que personne n'a choisi.

### La quarantaine n'est pas contournable par le relais

Le relais porte de la mémoire, et il la passe par `confiance.filtrer`.
Un souvenir d'origine non humaine n'entre pas dans un prompt parce qu'il
transite par un chemin neuf — c'était précisément le vecteur que HOS-216
ferme, et un relais non instrumenté l'aurait rouvert. Le drapeau
`inclure_quarantaine` est nommé et faux par défaut, comme celui de
`search()`.

### Ce qui reste honnêtement vide

`prepare(contrat=None)` est le défaut, et le restera jusqu'au jalon
suivant : **rien ne dérive aujourd'hui un contrat d'un objectif en
prose**. Le chemin est complet et testé de bout en bout — déposé au
registre, relu par le résolveur, inséré dans le prompt — et il attend son
appelant plutôt que d'inventer des critères que personne n'a écrits.

### Mesures

20 gardes ajoutées. Suite complète : **5 208 vertes**, 3 ignorées.


## HOS-228 — Le courtier, et la cinquième prémisse fausse (2026-09-03)

Le jalon 12. La roadmap annonçait « le disjoncteur de `task_executor`
(`_record_failure`) et la santé de runtime sont réels et branchés » — une
ligne que j'avais **moi-même écrite** deux jalons plus tôt, en corrigeant
les précédentes. Vérifiée avant d'écrire :

- `_record_failure` incrémente `self._failures`, qui n'est **lu qu'une
  seule fois**, pour une ligne de statistiques. Rien n'ouvre de circuit.
  C'est un compteur, pas un disjoncteur.
- `RecoveryManager` a une vraie logique de cooldown et de backoff, et
  **n'est instancié nulle part** hors des tests. Cinquième orphelin,
  après `approvals`, `DatabaseManager`, `MigrationManager` et le
  `backup_path` de `propose_write`.
- `has_quota`, en revanche, **est** consommé : `AdaptiveRouter` l'appelle
  via `catalog.has_budget`. Cette partie du diagnostic était juste.

Corriger une prémisse ne garantit donc pas d'avoir mesuré la suivante.

### Pourquoi pas `RecoveryManager`

Il **exécute une reprise** sur un composant — le redémarrer. Un courtier
**s'abstient de choisir** un fournisseur pendant un temps. Deux verbes
différents : le réutiliser demanderait d'enregistrer une action de reprise
vide pour n'en garder que la comptabilité de cooldown, c'est-à-dire de le
plier jusqu'à ce qu'il ne dise plus ce qu'il dit. Un test garde ce
raisonnement et tombe si quelqu'un le rebranche.

### Le cycle, fermé

    429 → QUOTA → fournisseur B          et non
    429 → même fournisseur → 429 → …

Mesuré de bout en bout : deux appels consécutifs sur un fournisseur qui
rend 429 produisent **un seul appel HTTP réel**. Le second n'est pas
tenté.

La taxonomie de HOS-225 nomme la cause ; le courtier en tire une durée
d'écart. Elles diffèrent selon la cause, et c'est tout l'intérêt :

- **quota** — 60 s, la même valeur que `remede(QUOTA).attendre_s`, et
  pour la même raison : le pool gratuit est partagé par clé et se réarme
  à la minute ou à la journée ;
- **fournisseur** et **ressource** — 10 s ; mais trois échecs consécutifs
  disent autre chose, et le circuit s'ouvre pour deux minutes ;
- **modèle, sémantique, vérification, contexte, outil, politique,
  sécurité, inconnue** — n'écartent **personne**. Un modèle qui rend une
  sortie inutilisable ne dit rien de la santé d'OpenRouter, et l'écarter
  pour ça ferait basculer sur le local une charge que le cloud servait
  très bien.

La table des causes écartantes tient en trois entrées, et un test le
vérifie : une table qui écarterait sur tout ferait basculer au premier
ennui, pour n'importe quelle raison.

### Un succès referme

Sans ça, un disjoncteur ouvert par un incident passager tue le
fournisseur jusqu'au redémarrage — ce qui ressemble exactement à un
fournisseur en panne, et se débogue mal. Un succès remet aussi le
compteur à zéro, sans quoi il additionnerait des échecs séparés par des
réussites.

### Le tri-état, encore

Un quota **non mesurable** écarte, comme un quota épuisé : on ne dépense
pas sur une mesure qu'on n'a pas. Mais une mesure périmée n'écarte plus —
s'y fier retirerait un fournisseur dont le quota s'est réarmé entre-temps,
et le pool gratuit se réarme à la minute.

### Deux refus de conception

Le courtier **ne va pas chercher** le quota lui-même : il serait alors
synchrone sur le réseau au milieu d'une décision de routage. Il le reçoit
de qui l'a mesuré.

Et il **n'a pas d'état persistant** : un redémarrage repart avec tous les
fournisseurs disponibles. Un écart est une réaction à un incident en
cours ; le faire survivre au redémarrage écarterait un fournisseur pour
une panne d'hier.

### Trace

`cloud.fournisseur_ecarte` **et** `cloud.fournisseur_retabli` : un écart
sans rétablissement visible ressemble à une panne définitive. Déclarés
dans les deux endroits que HOS-227 a mis au jour — le catalogue à côté du
producteur, que lit `collect_known_topics()`, et `BASELINE_TOPICS`, que
lit l'`EventHub`.

### Mesures

29 gardes ajoutées. Suite complète : **5 188 vertes**, 3 ignorées.


## HOS-227 — Ce qui a le droit de partir chez un tiers (2026-09-03)

Le jalon 11. Prémisse vérifiée avant d'écrire une ligne : **le pare-feu
n'existait pas**, zéro implémentation de §8.1. Ce qui existait et a été
réutilisé : `audit_log.redact()`, décrit dans son propre code comme « le
plus proche d'un `secret_scanner` que ce projet possède » (§17.1), avec
des motifs délibérément conservateurs.

### La fuite, mesurée sur le vrai prompt

`_build_messages` assemble le prompt ; quand le runtime est distant, tout
part. Construit avec le vrai assembleur, pas recopié : le chemin absolu
du workspace apparaît dans les instructions système — donc le nom de
l'utilisateur **et celui de son client**, dans chaque prompt cloud d'une
mission liée à un projet. Pas un scénario : le comportement du jour.

Six fragments partent, de sensibilités différentes — instructions système
(qui portent le chemin absolu), objectif de mission, journal de projet
relu depuis `.hermes/`, résultats amont (du texte produit par un modèle,
qui peut citer un fichier), manifeste des livrables, titre.

### Ce que « refusé par défaut » peut vouloir dire, et ce qu'il ne peut pas

Appliquée **littéralement à du texte quelconque**, la décision §8.1
refuserait tout : on ne peut pas démontrer qu'une phrase en prose n'est
pas sensible. Un pare-feu qui refuse tout est un pare-feu qu'on désarme
dans la semaine — la leçon du canary (HOS-218) et celle de la portée
d'approbation (HOS-224).

Le refus par défaut s'applique donc là où il a un sens :

- **au niveau du projet**, où `PolitiqueCloud.JAMAIS` bloque tout, quelle
  que soit la recommandation du routeur. C'est le vrai levier, à la
  granularité où quelqu'un peut réellement en décider : l'utilisateur
  sait si son dépôt client a le droit d'aller chez un tiers, le
  classificateur ne le saura jamais ;
- **au niveau du constat**, où ce qui est *démontré* sensible est
  caviardé ou refusé — jamais laissé passer parce qu'on hésite.

Et comme partout ici, un constat **nomme son indice**.

### Contexte nécessaire n'est pas contenu autorisé

C'est la distinction que le cahier demandait, et elle décide du
caviardage plutôt que du refus. Le modèle a besoin de savoir **qu'il
existe** une racine de workspace ; il n'a pas besoin de savoir chez qui.
La racine devient `<WORKSPACE>` ; le chemin relatif — `src/app.py`,
c'est-à-dire le travail — reste intact.

**Une expression régulière ne peut pas deviner où une racine s'arrête.**
Mesuré : elle la réduisait à `<WORKSPACE>` suivi du nom du projet client,
qui survivait donc au caviardage. L'appelant, lui, connaît la racine
exacte : `RealTaskExecutor` la passe désormais, et les trois écritures
sont couvertes — antislash, slash, et la forme échappée d'un `repr()`,
qui est exactement ce que le prompt contient.

### Refuser, et pas seulement retirer

Un identifiant démontré fait **refuser** l'envoi, pas caviarder. Sa
présence veut dire que le contexte assemblé contient du matériel qui
n'aurait pas dû y entrer — vraisemblablement le fichier d'où il vient.
Retirer la clé et envoyer le fichier autour serait la moitié d'une
protection.

Un secret prime aussi sur la politique « approbation » : proposer une clé
à l'accord humain ferait exister un chemin où quelqu'un de pressé la
laisse partir.

Et un envoi refusé porte **zéro message**, pour qu'un appelant distrait
qui enverrait quand même n'envoie rien.

### L'interne est caviardé, pas refusé

Adresses de courriel, adresses réseau privées : retirées, l'envoi part.
Les refuser rendrait le cloud inutilisable pour toute mission liée à un
workspace. L'adresse de boucle locale est délibérément **exclue** :
Hermes écoute dessus, elle apparaît dans des messages d'erreur normaux,
et la caviarder rendrait un diagnostic illisible sans rien protéger.

### Le contrôle est avant l'envoi

Posé dans `_make_cloud_chat`, le goulet ouvert par HOS-226 — donc vrai de
tout appelant, pas seulement de celui qu'on a pensé à instrumenter. Deux
gardes sur l'**arbre syntaxique** le tiennent : l'examen s'exécute avant
l'appel, et ce qui est envoyé est `decision.messages`, pas les messages
d'origine. La seconde vise l'erreur qui annulerait tout le module —
examiner puis envoyer l'original passerait tous les tests du
classificateur et ne protégerait de rien.

Un événement `cloud.pare_feu` est publié sur **chaque** décision, pas
seulement sur les refus : savoir que trois cents prompts sont partis
« autorisés » vaut autant que savoir que deux ont été refusés, parce que
c'est ce qui dit si le pare-feu regarde vraiment quelque chose. Son
aperçu est caviardé à la source — un rapport de fuite qui cite la valeur
serait une seconde fuite (HOS-218).

### Une asymétrie trouvée dans le garde des topics

`collect_known_topics()` assemble la liste blanche depuis des
**catalogues déclarés à côté de leurs producteurs**, et non depuis
`event_topics.BASELINE_TOPICS`. Un topic ajouté seulement au second passe
à l'exécution mais fait tomber `test_topics_publies_sont_autorises` — ce
qui est arrivé ici. `PARE_FEU_EVENTS` suit donc le patron des huit
catalogues rebranchés en HOS-181.

### Mesures

28 gardes ajoutées ; 12 faux de chat cloud mis à jour, le contrat d'un
chat **distant** portant désormais les racines. Suite complète :
**5 159 vertes**, 3 ignorées.


## HOS-226 — Un fournisseur distant est un runtime, pas une hiérarchie (2026-09-03)

Le jalon 10. Sa prémisse — « le client existe sans un seul test » —
était fausse : `OpenRouterClient` en a **neuf**, réels (compteurs
d'usage, 429 traduit en quota, SSE, échec en cours de flux, non-200 avant
le flux), dans `tests/`, l'arbre qui n'était plus collecté depuis
HOS-175. Quatrième fois que cette réparation change une conclusion.

Ce qui manquait vraiment, mesuré : `CloudProvider` n'existait **nulle
part** (zéro occurrence), **trois fichiers** codent
`https://openrouter.ai/api/v1` en dur, et `service_registry` comme
`task_executor` branchent sur la chaîne littérale `"openrouter"`.

### Une première version qui construisait un cinquième système

Elle créait un paquet `backend/cloud/` avec son protocole, son
adaptateur et son registre. C'était une arborescence parallèle : le RAL
a déjà `adapters/hermes_ollama.py`, et un fournisseur distant **est** un
runtime — il répond à `chat` comme Ollama.

Ce qu'il a en plus est une **capacité**, pas une hiérarchie :
`CloudCapability` rejoint `ChatCapability` dans
`backend/ral/capabilities.py`, et porte les trois choses qui n'existent
pas en local — un **prix**, un **quota partagé** qui s'épuise, un
catalogue qui change sans qu'on l'ait décidé.

`RuntimeOpenRouter` vit donc sous `backend/ral/adapters/`, à côté de
`hermes_ollama.py`, et suit la convention du RAL (`name`, pas
`identifiant`) plutôt que d'imposer la sienne. Un test vérifie qu'il
satisfait les deux protocoles, et qu'un paquet `backend/cloud/` n'est pas
revenu.

### Pourquoi une interface pour une seule implémentation

La règle du dépôt est contre l'abstraction spéculative. Trois faits
disent que ce n'en est pas une :

- le couplage est réel et dispersé (trois URL en dur, deux comparaisons
  littérales) ;
- le **pare-feu de données** du jalon suivant a besoin d'un goulet — la
  décision §8.1 du cahier suppose un endroit unique où « quelque chose
  part chez un tiers » se constate. Sans interface, ce contrôle serait à
  dupliquer par fournisseur, donc à oublier au second ;
- ce n'est **pas** `ChatCapability`, qui ne dit rien du prix ni du quota.

### Une correction de prix trouvée en écrivant l'adaptateur

`cloud_catalog._is_free_pricing` compare `pricing["prompt"] == "0"` — une
égalité de **chaîne**. OpenRouter rend `"0"` aujourd'hui et `"0.0"` sur
certaines entrées : celles-là s'y lisent payantes par accident. La
comparaison est ici numérique, et un prix **illisible compte comme
payant** — le sens de lecture qui ne fait pas dépenser par erreur.
`None` et `0.0` ne disent pas la même chose.

### Le tri-état, appliqué à une ressource payante

Un quota non mesurable rend `utilisable=False`. On ne dépense pas sur une
mesure qu'on n'a pas — HOS-222 appliqué à l'argent. Mais une **clé sans
plafond** n'est pas « inconnu » : la réponse a été lue, elle dit qu'il
n'y a pas de limite. Les confondre interdirait le cloud à qui en a payé
l'accès illimité.

### Ce qui n'a délibérément pas bougé

Le gate `self._cloud_chat is not None` de `task_executor` reste tel quel.
Le remplacer par une consultation du registre ferait dépendre un test
unitaire hermétique d'un état de processus — et ce champ est justement
le point d'injection que ces tests utilisent.

### Un troisième faux positif de sous-chaîne

Ma garde « la fabrique ne construit plus de client en direct »
s'accrochait à la **docstring** qui explique le changement. Réécrite sur
l'arbre syntaxique : elle regarde les imports et les noms du corps.
Troisième fois sur ce chantier — c'est un motif, pas un accident.

### Mesures

29 gardes ajoutées. Suite complète : **5 131 vertes**, 3 ignorées.


## HOS-225 — Pourquoi un run a échoué, et ce que ça change (2026-09-03)

Le jalon 9, et la dette que HOS-221 avait explicitement notée : onze
causes déclarées, aucune renseignée, avec la raison écrite dans le code —
« deviner maintenant produirait des étiquettes fausses, et une étiquette
fausse coûte plus cher qu'une case vide, parce qu'on la croit ».

La contrainte n'a pas changé. Ce qui change, c'est ce qui la porte : un
classificateur qui **enregistre son indice** peut être contredit ; une
intuition ne peut pas l'être.

### Ce que la reprise faisait, et pourquoi c'était faux

`_resolve_model` change de modèle à **toute** reprise, quelle que soit la
cause. C'est le bon remède pour exactement un cas sur onze :

- **manque de VRAM** — il faut un modèle *plus petit*, ou attendre ; un
  autre de même taille échoue pareil ;
- **fenêtre de contexte fermée** — CLAUDE.md le dit déjà : « une réponse
  tronquée n'est pas une erreur de raisonnement et ne doit pas se noter
  comme telle ». Changer de modèle ne répare rien ;
- **quota dépassé** — réessayer chez le même fournisseur échoue par
  construction ;
- **refus de politique ou de sécurité** — il ne faut **pas** reprendre.
  `approvals.py` décrivait déjà ce que produit l'autre choix : « an agent
  retrying in a loop after a refusal will re-ask », c'est-à-dire une file
  d'approbation inondée par la machine. La reprise légitime viendra de
  l'accord humain, pas de la boucle.

### La règle de classement

Trois sources, dans l'ordre de la force de preuve :
`done_reason == "length"` (le seul indice qui vienne du runtime et non
d'un message rédigé ici), puis le code HTTP (un fait, pas une
interprétation), puis les motifs de texte.

Les motifs sont écrits **depuis les messages réels du dépôt**, pas
inventés : `no VRAM admission`, `runtime 'x' timed out after Ns`,
`returned an empty completion`, `is outside ALLOWED_PATHS`,
`the local fallback also failed`. Un classificateur calibré sur des
messages imaginaires classe des messages imaginaires.

`HTTP 400 → OUTIL` vient d'un incident précis : la campagne du catalogue
comptait « 0 s par tentative », c'était un HTTP 400 jamais regardé, et il
s'était rangé sous « le modèle ne sait pas faire ».

Deux refus de classer, délibérés. Le catch-all
`runtime 'x' could not execute task y: …` enveloppe n'importe quoi et
reste `INCONNUE` : lui donner une cause donnerait une cause à toutes les
erreurs non prévues, ce qui est exactement la façon dont une taxonomie
devient du bruit. Et `KeyError: 'x'` ne démontre rien.

### `INCONNUE` ne devient jamais une étiquette

En base, une cause non démontrée reste **`NULL`**. Une colonne vide se
lit « on ne sait pas » ; une étiquette « inconnue » se lit comme un
diagnostic posé. Et l'appelant retombe alors exactement sur le
comportement d'avant ce jalon : reprendre une fois, sans rien changer
qu'on ne saurait justifier.

L'abandon distingue aussi ses deux motifs — « plafond atteint » et
« cause non reprenable ». Les confondre ferait chercher un défaut de
compteur là où il y a un refus assumé.

### Un plafond retiré parce qu'un test l'a dit

Ma première version donnait à chaque cause un plafond de tentatives, à 2
par défaut. Il **rétrécissait** silencieusement le budget que
l'opérateur avait configuré dans `max_retries_per_task` : une mission
réglée sur deux reprises n'en obtenait plus qu'une, et
`tests/architecture/test_intelligent_retry.py` l'a dit à la première
exécution de la suite complète.

Aucune mesure ne dit qu'un manque de VRAM mérite moins de tentatives
qu'un échec quelconque. L'opinion de ce module est donc binaire — on
reprend ou on ne reprend pas — et le *combien* reste au budget de la
mission, qui est le seul chiffre que quelqu'un ait décidé.

C'est le second arbre de tests qui l'a trouvé, celui qui n'était plus
collecté depuis HOS-175.

### Mesures

34 gardes ajoutées, plus le garde de HOS-221 amendé — il interdisait de
renseigner `cause` du tout ; il vérifie maintenant les deux choses qui
rendent le classement honnête : qu'il passe par la taxonomie, et qu'une
cause non démontrée reste `NULL`.

Suite complète : **5 102 vertes**, 3 ignorées.


## HOS-224 — Approuver une action, pas une phrase (2026-09-03)

Le jalon 8. La roadmap annonçait « ni hash canonique, ni portée, ni
expiration », et proposait de rebrancher `backend/policy/approval_engine.py`.
Mesuré : deux tiers de ce diagnostic étaient faux, le troisième était
juste, et la solution proposée aurait été une erreur.

`backend/security/approvals.py` **a** une expiration, **est** branché —
dans `AegisAgent._apply_human_consent`, sur le chemin réel des requêtes —
et hache bien en SHA-256. Ce qu'il n'avait pas : un hachage *canonique*,
et une portée.

### Le premier défaut : la description entrait dans l'identité

Le module le justifiait par un argument correct — « une approbation pour
*Commit on feature/x* ne doit pas autoriser *Commit on main* » — appuyé
sur une hypothèse qui n'est vraie que pour une partie de ses appelants :

> Descriptions are generated by the calling tool, not by a model.

Vrai pour `file_tools` et `git_tools`. **Faux** pour l'outil MCP
`aegis_check`, dont la description est écrite par le modèle, et pour
`POST /api/v1/security/evaluate`, où elle vient du corps de la requête.

Mesuré :

    « Write to config.json to fix the port »  ->  24aa0d0bf698
    « Write config.json (port fix) »          ->  061db3be665d

Deux empreintes pour une action. Le « oui » de l'humain ne s'appliquait
jamais, une seconde demande était déposée, et rien ne disait pourquoi.

### Le second : le chemin non plus n'était pas canonique

Quatre écritures du même fichier, quatre empreintes :

    C:/p/config.json     C:\p\config.json
    c:/p/config.json     C:/p/../p/config.json

Sur Windows ce n'est pas un cas de laboratoire. Le défaut ne va que dans
le sens sûr — il refuse au lieu d'autoriser — mais il rend la
fonctionnalité inutilisable, ce qui revient au même une fois qu'on l'a
désactivée.

### La règle retenue

L'identité d'une action est **structurée**, jamais rédigée :

    action_type + chemin canonique + discriminants triés

La description reste sur la ligne, pour que l'humain sache ce qu'il
approuve ; elle n'est plus dans l'identité. Ce qui la distinguait
légitimement devient un discriminant nommé : `git_tools` passe
`{"op": "commit", "branch": "main"}` au lieu de compter sur la phrase.
La garantie d'origine est **conservée** — commit sur `feature/x`
n'autorise ni commit sur `main`, ni push sur `main` — et elle ne dépend
plus de la formulation.

Un détail d'ordre a coûté une mesure : `os.path.normcase` reconvertit les
`/` en `\` sur Windows. Replier la casse **après** avoir uniformisé les
séparateurs rendait `c:\projet`, et la portée ne couvrait plus rien.

`ActionRequest.discriminants` est un tuple de paires, pas un dict : la
classe est `frozen=True`, donc hachable, et un dict la rendrait
inhachable pour tous ses usages présents et futurs.

### Ce qui manquait vraiment : la portée

Trente écritures dans un dossier demandaient trente approbations. Une
fonctionnalité qui exige trente clics est une fonctionnalité désactivée
— et une approbation désactivée ne protège de rien.

Une portée d'arborescence couvre un `action_type` sous une racine. Trois
bornes, et les trois sont nécessaires :

- une **racine**, sans laquelle elle couvrirait le disque — absente,
  c'est une `ValueError`, jamais un accord silencieusement plus large ;
- un **budget d'usages** plafonné à 50, sans lequel « oui pour ce
  dossier » deviendrait une permission permanente que personne n'a
  décidée ;
- une **expiration plus courte** que celle d'un accord exact (5 min
  contre 15) : elle autorise davantage, donc elle doit se périmer plus
  vite.

Et **elle ne s'obtient jamais par omission**. `decide(approved=True)`
seul donne exactement ce qu'il donnait : un accord exact, à usage unique,
quinze minutes.

Le confinement est vérifié par `empreinte.couvre`, qui canonise les deux
côtés et compare des segments de chemin : `C:/projet-bis` sous
`C:/projet` est l'évasion qu'un `startswith` laisse passer.

L'accord exact est dépensé **avant** la portée — sinon on consommerait un
budget de portée pour une action qui avait déjà son propre « oui ».

Les quatre colonnes sont nullables, et pas par commodité :
`_add_missing_columns` (`memory/db.py`) n'ajoute au démarrage que des
colonnes nullables et refuse bruyamment les autres. Une base existante
les gagne sans migration, avec `None` partout — c'est-à-dire avec le
comportement d'avant.

### Ce qui n'a délibérément pas été fait

**`backend/policy/approval_engine.py` reste débranché.** La roadmap
proposait de le rebrancher, « moins cher que de l'écrire ». Mesuré :
Aegis est la seule couche de gouvernance réellement sur le chemin des
requêtes, et `backend/policy/*` ne sert que ses propres routes. Y ajouter
une seconde porte vivante donnerait deux endroits où une action peut être
autorisée, deux files, et la question « laquelle fait foi ? » à chaque
incident. De la complexité neuve sans sécurité neuve.

Un test garde ce raisonnement et tombe si quelqu'un le rebranche — pour
qu'on relise l'argument plutôt que de le contourner.

### Un test amendé, pas supprimé

`test_a_different_action_gets_a_different_fingerprint` portait sa
troisième distinction dans la description. La propriété qu'il gardait est
juste et reste gardée ; ce qui la porte a changé.

### Mesures

37 gardes ajoutées. Suite complète : **5 068 vertes**, 3 ignorées.


## HOS-223 — Hermes sait annuler une modification (2026-09-03)

Le jalon 7. Trois constats, mesurés dans le code avant d'écrire une
ligne :

- `propose_write` déposait une sauvegarde horodatée à chaque écrasement,
  la rendait à l'appelant et la publiait dans un événement — et **rien,
  nulle part, ne la relisait**. Aucune fonction du dépôt ne restaurait
  depuis un `backup_path`. C'était un quatrième orphelin, après
  `approvals.py`, `DatabaseManager` et `MigrationManager`.
- `delete()` faisait `shutil.rmtree()` sur un répertoire sans rien
  garder du tout. `move()` non plus.
- `snapshot_manager` sauve l'état de mission et dit **explicitement**
  qu'il ne copie pas les fichiers, en déléguant à ces sauvegardes. La
  délégation pointait vers un mécanisme sans retour.

### Le chemin git, et la pièce qui détruirait du travail si elle cédait

Un point de reprise est un commit détaché sous
`refs/hermes/checkpoints/<id>`. Git fait le reste : stockage par contenu
qui déduplique, objet immuable, référence qui protège du ramasse-miettes,
et `.gitignore` honoré gratuitement — un `node_modules/` de 400 Mio
n'entre pas sans qu'on ait écrit une règle.

**Le dépôt de l'utilisateur ne sent rien.** Ni son index, ni sa branche,
ni son `HEAD`, ni son stash. Un `git add -A` sur l'index réel détruirait
le travail en cours de quelqu'un — au moment précis où il s'apprête à
lancer une mission risquée. D'où `GIT_INDEX_FILE` sur un fichier
temporaire, la pièce d'Agent OS qui vaut d'être reprise telle quelle.
Mesuré : index, `HEAD` et branche identiques avant et après.

Écart avec eux : le commit prend `HEAD` pour **parent**. Détaché sans
parent, un point de reprise n'est diffable contre rien.

Et restaurer, c'est effacer. `git checkout-index` réécrit ce qui était
là, mais ne supprime pas ce qui est apparu depuis — une restauration qui
les laisserait ne restaurerait rien, elle mélangerait deux états. Les
trois cas sont donc calculés et traités séparément.

### Le repli, pour les workspaces sans git

La production du 30 août tournait dans un dossier sans `.git`. Ne
protéger que les dépôts reviendrait à ne protéger que ce qui l'était
déjà.

Copie avec **manifeste de contenu** et vérification d'intégrité par
**re-hachage** — les deux sont d'Agent OS et les deux comptent : une
copie sans manifeste ne sait pas ce qu'elle devait contenir, un manifeste
jamais revérifié n'est qu'une déclaration. L'intégrité est vérifiée
**avant** d'écrire quoi que ce soit ; restaurer à moitié depuis une copie
abîmée laisserait un troisième état, ni l'ancien ni le nouveau.

Deux ajouts tirés de ce dépôt. Les répertoires ignorés sont ceux de
`verification.py` — une seconde liste divergerait. Et un fichier
illisible **fait échouer la prise**, il n'est pas passé sous silence :
c'est la leçon de HOS-222, un point de reprise partiel est pire
qu'absent, parce qu'on croit avoir un filet et qu'on ne l'apprend qu'en
tombant. Même raison pour le plafond de 500 Mo : lever plutôt que
dépenser silencieusement des gigaoctets à chaque mission.

### Ce que Hermes ajoute : le couple

Un checkpoint Agent OS est un état de fichiers. `snapshot_manager` sauve
l'état de mission, ce qu'ils ne font pas. Un point de reprise Hermes est
le **couple**, pris et repris ensemble.

Restaurer les fichiers sans l'état laisse une mission qui croit avoir
fini un travail que le disque ne porte plus, et qui repartira de là.
Restaurer l'état sans les fichiers fait l'inverse. L'un ou l'autre seul
fabrique une incohérence — le genre que ce dépôt met des semaines à
retrouver.

Quand l'état n'a pas pu être repris, `Restauration` le **dit** au lieu de
rendre un succès partiel : les fichiers sont déjà revenus à ce
moment-là, et lever laisserait l'appelant persuadé que rien n'a eu lieu.

### Restaurer efface, et c'est traité comme tel

Même contrat que `snapshot_manager.restore_snapshot` : un aperçu d'abord,
Aegis en `data_migration` ensuite — que `config/security.yaml` classe en
`mandatory_validation: true` à tous les niveaux d'autonomie. Et `Ecart`
garde **trois listes séparées** : fondre le destructif dans un
« 12 fichiers touchés » cacherait la seule qui détruise du travail.

### Branché, et le disant quand il ne l'est pas

`graph_executor` pose le filet avant que la mission touche au disque.
L'instantané qui existait déjà répond à « qu'est-ce qui a changé ? » ;
celui-ci répond à « comment revenir en arrière ? ».

Quand la prise échoue, la mission part quand même — l'utilisateur a
demandé un travail, pas une sauvegarde — mais `mission.sans_filet` le
dit. Un point de reprise absent en silence laisse partir avec le même
aplomb, et l'absence ne se découvre qu'en tombant. C'est la règle du
tri-état de HOS-222, appliquée à la protection plutôt qu'à la mesure.

### Deux défauts de test, dont un que j'avais déjà commis

Mes deux fixtures partageaient `tmp_path` : `depot` initialisait un dépôt
git dans le dossier que `dossier` déclarait n'en pas avoir. Et
l'assertion du `.gitignore` cherchait la sous-chaîne « ignore », que
`.gitignore` contient — **le faux positif de sous-chaîne**, exactement
celui que j'avais reproché au sondage du cahier six jours plus tôt. Elle
porte maintenant sur le chemin exact.

### Mesures

28 gardes ajoutées. Suite complète : **5 036 vertes**, 3 ignorées.


## HOS-222 — Ce qu'on n'a pas pu lire n'est ni vert ni rouge (2026-09-03)

Le jalon 6. `verification.py` était déjà exceptionnellement prudent sur
le « on ne sait pas » — `tests_echouent`, `manifeste_manque`,
`travail_deja_fait` distinguent tous soigneusement l'absence de mesure du
constat d'échec. Mais l'instrument lui-même ne savait pas dire qu'il
n'avait pas pu regarder, et deux faux verdicts en sortaient, **en sens
opposés**.

### Le faux positif : un workspace disparu passait pour du travail

`snapshot()` rendait un instantané **vide** pour un arbre illisible,
indiscernable d'un dossier réellement vide. Mesuré : un workspace de deux
fichiers devenu illisible se lisait « 2 supprimés », donc
`touched_anything`, donc **`verified: True`**.

Le module produisait exactement le faux positif qu'il existe pour
attraper. Une mission qui n'a rien fait, dans un workspace qu'on ne sait
plus lire, se déclarait vérifiée.

### Le faux négatif : deux instantanés muets devenaient une accusation

Le même défaut dans l'autre sens : deux instantanés illisibles se lisaient
« rien n'a changé », donc `contradicted: True`, donc `mission.unverified`
et une reprise suggérée — sur une mission qui avait peut-être travaillé.

C'est le jumeau de la règle centrale du dépôt. « Ne jamais croire un
succès sur parole » et « ni un échec sur parole » ont ici la même cause
et se réparent avec la même phrase : **on ne conclut pas de ce qu'on n'a
pas lu.**

### Et une empreinte constante pour tout ce qui ne se lit pas

`_fingerprint` rendait la chaîne `"unreadable"` — la même pour tous. Deux
fichiers différents comparaient donc égaux, et un fichier réécrit mais
resté illisible passait pour **inchangé**, alors qu'on ne l'avait jamais
ouvert. Elle rend `None` désormais, ce qui force l'appelant à ranger le
fichier ailleurs que dans un constat.

### Ce qui est ajouté

`WorkspaceSnapshot` porte `lisible` et `illisibles`. `WorkspaceDiff` porte
`indetermines` — une quatrième case, ni créé, ni modifié, ni supprimé.
Un fichier illisible d'un côté ou de l'autre y va : le compter comme créé,
ce que faisait la version précédente pour « illisible avant, lisible
après », donnait une preuve de travail à partir d'une permission qui
change. `touched_anything` ne les compte pas, et `summary()` ne dit plus
« rien n'a changé » quand il ne sait pas — une affirmation qu'on n'était
pas en position de faire.

`MissionVerification.verdict` nomme enfin le tri-état, et **réutilise le
vocabulaire du contrat de mission** (HOS-221) : `reussi | echoue |
indisponible`. En inventer un second aurait donné deux façons de dire
« on ne sait pas », donc une de trop, et la question « laquelle croire ? »
à chaque lecture. `verified` et `contradicted` restent à côté : les
appelants existants ne changent pas, un nouveau n'a plus à recomposer le
troisième état à partir des deux autres.

### Une alarme, et une qu'on refuse de poser

`mesure_impossible` distingue « rien à mesurer » de « ça devait être
mesurable et ça ne l'a pas été ». Seul le second émet
`mission.non_mesuree`.

Une mission sans workspace lié est le cas **normal et fréquent** ; en
faire une alarme donnerait une alarme qui sonne tout le temps, donc une
alarme débranchée dans la semaine. C'est la leçon du canary (HOS-218), et
elle vaut ici aussi. Un workspace lié qu'on n'a pas su lire, en revanche,
est un défaut d'instrument — et un instrument muet se répare.

L'événement est distinct de `mission.unverified` : celui-là dit « le
disque contredit », celui-ci dit « le disque n'a rien dit ». Les
confondre ferait passer un instrument muet pour un verdict.

### Mesures

19 gardes ajoutées ; les 48 gardes existantes de la vérification tiennent
sans modification. Suite complète : **5 008 vertes**, 3 ignorées.


## HOS-220 et HOS-221 — Le contrat, le registre, et la lignée (2026-09-03)

Le jalon 5 : « qu'est-ce qui devait être vrai à la fin ? » et « qu'est-ce
qui a été fait, avec quoi, et pourquoi le premier essai a raté ? ». Deux
questions que Hermes ne savait pas trancher, et qui ont chacune coûté
quelque chose de mesurable.

### HOS-220 — La seconde porte que HOS-215 avait laissée ouverte

`DatabaseConfig(name="hermes_os")` rendait `sqlite:///hermes_os.db` — un
chemin **relatif**, donc un fichier dans le répertoire courant, donc dans
le dépôt, que la prochaine mise à jour remplace. HOS-215 avait sorti
l'état pour `Settings` et pas pour ceci : deux défauts par défaut, un
seul traité. Un nom nu se résout maintenant sous la racine d'état ; un
chemin donné explicitement passe intact, sans quoi une base de test sur
`tmp_path` atterrirait dans l'état réel de l'utilisateur.

Le test de `tests/production` qui affirmait `sqlite:///test_db.db` est
**amendé, pas supprimé** : il gardait la bonne propriété avec la mauvaise
valeur. C'est le deuxième défaut que la remise en service de ce second
arbre de tests met au jour.

### HOS-221 — Le tri-état, et le refus de confondre une ignorance

`backend/runs/contrat.py` porte quatre états de critère et trois verdicts
de vérificateur. La règle centrale est celle qu'Agent OS met en capitales
dans `src/lib/contract.ts` : *never conflate unavailable with passed*.

Ce dépôt l'a enfreinte le 2026-08-30. `img07` était `indéterminé` — le
relecteur n'avait pas su conclure — et cet état n'avait nulle part où
aller dans une vérification qui rend `bool`. Il s'est rangé à côté des
plans jugés bons. Un contrat dont un critère est `invérifiable` n'est
maintenant **pas tenu**, et son résumé le dit en toutes lettres.

Trois refus à l'écriture, chacun visant un contrat qui serait tenu quoi
qu'il arrive : pas d'objectif, pas de critère d'acceptation, ou un
critère sans **vérificateur nommé**. Le dernier est le moins évident et
le plus utile : sans le nom du vérificateur, « invérifiable » ne dit pas
*ce qui* manque, et un rapport qui ne le dit pas ne fait pas agir.

Ce qui change par rapport à Agent OS : leurs critères s'écrivent en EARS,
une syntaxe d'exigences anglophone taillée pour un formulaire. Les
missions de Hermes viennent de l'agent. Un critère est ici un texte plus
le nom de qui doit le trancher.

### HOS-221 — Le registre, et ce qu'il aurait épargné

La nuit du 29 au 30 août, **trois fois**, la question « avec quel modèle,
et pourquoi le premier essai a raté ? » n'a pas eu de réponse sans aller
lire des fichiers JSON écrasés à chaque exécution. L'archivage du journal
a dû être écrit en pleine nuit, pendant que la production tournait.

`backend/runs/registre.py` porte le run : sa mission, son modèle, son
runtime, ses jetons, son issue, **son parent** et son rang de tentative.
`lignee()` rend la chaîne complète, et une reprise **doit dire pourquoi**
— une lignée muette ne répond pas à la question qu'on lui posera six
semaines plus tard.

L'invariant d'état est repris d'Agent OS et vit **dans le SQL**, pas en
Python : un `CASE WHEN statut IN (…terminaux…) THEN statut ELSE ? END`
qu'aucun appelant distrait ne peut contourner. Un défaut trouvé en le
mesurant : gelé sur le seul statut, un second appel réécrivait quand même
`cause` et `raison`, produisant un run figé sur `echoue` avec le motif du
mauvais appel — une trace pire que pas de trace, parce qu'elle a l'air
d'en être une. Le gel couvre maintenant **chaque colonne**.

`busy_timeout=5000` manquait à `DatabaseManager` : WAL laisse un lecteur
pendant une écriture, pas deux écrivains, et sans lui la seconde lève
« database is locked » au lieu d'attendre son tour.

### Trois choses délibérément non faites

**Pas de table `run_events`.** Hermes a déjà un bus d'événements durable,
rejouable par plage et par motif, à identifiants idempotents. Porter la
seconde table d'Agent OS créerait **deux magasins d'événements** —
l'architecture parallèle que le cahier interdit à sa propre règle 4. Le
registre porte les runs, le bus porte les événements, `run_id` les
corrèle. Un test le garde : le schéma ne contient qu'un `CREATE TABLE`.

**Pas de troisième couche SQLite.** `DatabaseManager` et
`MigrationManager` étaient orphelins — utilisés par personne hors de
`backend/storage/` — mais réels et corrects. Les doubler aurait ajouté
une couche de plus au lieu de rebrancher celle qui existait.

**La cause d'échec n'est pas devinée.** `Cause` existe et nomme onze
remèdes distincts, mais `_clore_le_run` ne la renseigne pas : classer un
échec depuis un message d'erreur demande la taxonomie qui fait l'objet de
son propre jalon. Deviner maintenant produirait des étiquettes fausses,
et une étiquette fausse coûte plus cher qu'une case vide — parce qu'on la
croit. `raison` porte l'erreur brute, qui elle est mesurée.

### Le registre est branché, et c'est le point

`approvals.py`, `DatabaseManager`, `MigrationManager` : du code réel,
correct, testé, **appelé par personne**. Un registre de runs qui finirait
comme eux ne servirait qu'à faire croire que la traçabilité existe.

`MissionExecutor.prepare()` ouvre le run, `finalize()` le clôt, et la
trace est en meilleur effort de bout en bout — une télémétrie qui casse
la mission qu'elle décrit ne vaut rien. Un test échoue si `_clore_le_run`
se met à deviner une cause ; un autre si un registre en panne fait
échouer une mission.

### Ce qui reste su et non traité

`Statut.PERDU` existe dans le vocabulaire et **rien ne le pose** : détecter
un run dont le processus a disparu demande un balayage au démarrage, qui
n'est pas construit ici. Et une exception nue levée par un exécuteur de
tâche traverse `execute_task` sans que `finalize()` soit atteint — le run
reste alors `en_cours` indéfiniment. Les deux se règlent au même endroit,
et ce n'est pas ce jalon.

### Mesures

56 gardes ajoutées. Suite complète : **4 989 vertes**, 3 ignorées.


## HOS-215 a HOS-219 - Quatre controles avant de batir quoi que ce soit (2026-09-03)

La lecture du code d'Agent OS (HOS-214) a montre que trois manques
classes « confort » sont des **controles de securite**. Ils passent donc
devant le Contract et le Run Ledger : les construire apres reviendrait a
batir la tracabilite dans un dossier effaçable, au-dessus d'une memoire
empoisonnable.

### HOS-215 — L'etat de l'utilisateur sort du depot

`data/db` 17,1 Mio, `data/eventbus` 8,2, `data/snapshots` 1,1, plus
`_memory_.db` — **tout vivait dans le repertoire de l'application**.
`.gitignore` les protegeait de git ; rien ne les protegeait d'une mise a
jour, qui remplace ce repertoire. Ce qui aurait disparu : la base, la
memoire, le bus d'evenements, et les instantanes — c'est-a-dire la
capacite de reprise elle-meme.

`backend/core/etat.py` resout une racine unique hors du depot —
`%LOCALAPPDATA%\HermesOS` sur Windows, `HERMES_DATA_DIR` primant — et
**refuse toute racine qui y retomberait**, meme demandee explicitement :
le permettre par configuration laisserait le defaut revenir par la porte
qu'on vient de fermer.

`preserve_set()` rend la liste de ce qu'une mise a jour ne doit jamais
toucher. Rendue comme une liste et non documentee en prose : un
installeur, une sauvegarde et un test peuvent la lire, et elle ne peut
pas diverger de ce que le code utilise. C'est le defaut du « preserve
set » d'Agent OS, qui vit dans un fichier Markdown.

`scripts/migrer_etat.py` a deplace **26,6 Mio**, en essai a blanc par
defaut, sans jamais ecraser un contenu different, et sans rien supprimer
avant d'avoir relu et compare.

**Une erreur de classification, trouvee par un test.** `data/workflows`
etait dans la liste des dechargements. Or ses fichiers sont **suivis par
git** : c'est du contenu livre avec l'application. Les deplacer a fait
passer `/workflows` de deux entrees a zero, et le test l'a dit
immediatement — « no workflows shipped, this test would pass vacuously ».
Le critere n'est pas « ou c'est range » mais **qui l'a ecrit** : ce que
git suit se remplace a chaque mise a jour, ce que l'utilisateur produit
doit lui survivre.

### HOS-216 — La memoire ne sert pas ce qu'elle n'a pas verifie

Ce n'est pas de la qualite de donnees, **c'est la defense contre
l'injection de prompt**. Un agent lit une page web ou un depot clone, y
trouve un texte ecrit pour lui, ce texte entre en memoire, et au tour
suivant `search()` le sert comme un fait. L'attaque n'a plus besoin de se
rejouer : elle est installee.

`backend/memory/confiance.py` pose la regle qu'Agent OS garde dans
`m8-prompt-injection` : **toute origine non humaine part en quarantaine,
quel que soit son contenu**. C'est le point le moins intuitif et le plus
important — un filtre qui cherche des formulations suspectes se contourne
en changeant de formulation. On juge la provenance.

`search()` et `search_experiences()` filtrent par defaut.
`inclure_quarantaine` est **nommé et faux** : un appelant qui veut du
contenu non verifie doit le dire, et ça se lit a la relecture. Un test
garde que le parametre reste keyword-only, parce qu'un drapeau
positionnel se passe par accident.

Une promotion **nomme qui l'a decidee**, sinon elle est refusee : sans
acteur, on ne peut plus revenir sur la decision — ce qui est precisement
ce qu'on veut pouvoir faire apres une injection reussie.

### HOS-217 — Un workspace ne reecrit pas ce qui gouverne l'agent

Deux scenarios, dont aucun n'exige un attaquant. Un depot clone arrive
avec son `.mcp.json` ou ses hooks, et l'agent herite d'outils que
personne ne lui a donnes. Ou l'agent ecrit lui-meme dans les fichiers qui
le gouvernent, et elargit ses propres permissions.

`backend/security/derive_workspace.py` releve l'empreinte de dix fichiers
et dossiers gouvernants — `CLAUDE.md`, `.mcp.json`,
`.claude/settings.json`, `.claude/hooks`, `.claude/skills`… — et compare.

Un dossier gouvernant est releve **fichier par fichier** : hacher
`.claude/hooks/` globalement dirait « quelque chose a change » sans dire
quoi, et un hook execute du code.

Il **releve et compare, il ne decide pas**. Bloquer, demander une
approbation ou seulement consigner releve de la politique, et cette
decision appartient a Aegis.

Et le tri-etat s'applique : une empreinte qu'on n'a pas pu prendre est
rapportee `INCONNU`, jamais « inchange ». On ne peut pas affirmer qu'un
fichier de gouvernance est intact quand on n'a pas su le lire.

### HOS-218 — Ce qui sort d'un agent est surveille pendant qu'il parle

Le canary est la meilleure idee du code d'Agent OS. On ne peut pas
enumerer tout ce qu'un agent ne doit pas dire, mais on peut savoir quand
il dit **une chose precise** qu'il n'aurait jamais du voir : une fausse
valeur, connue de nous seuls, plantee dans son environnement. Si elle
ressort, c'est que l'agent lit et recrache son environnement — donc que
les vrais secrets qui vivent a cote sont exposes de la meme façon. On n'a
pas besoin de savoir comment la fuite se produit.

`backend/security/surveillance_flux.py` porte aussi :

- un **report de 512 caracteres** entre deux blocs — un secret coupe par
  la fragmentation du flux passerait sinon entre les mailles ;
- une detection de **silence**, parce qu'un agent qui se tait n'echoue
  pas, il attend, et l'attente ressemble au travail. C'est la leçon du
  decodage qui a rampe quarante minutes le 2026-08-30 sans lever une
  seule erreur ;
- un plafond de **cout**.

Trois refus deliberes. Le module **ne tue pas** le processus : il
rapporte, et l'appelant decide. Un rapport de fuite **ne contient jamais
la valeur** — ce serait une seconde fuite ; il donne sa longueur. Et une
valeur de moins de huit caracteres n'est pas surveillee : « 1 », « true »
se retrouvent partout dans une sortie normale, et une alarme qui sonne
pour rien est debranchee dans la semaine.

### HOS-219 — Les deux decisions deleguees

**Le pare-feu de donnees refuse par defaut.** L'asymetrie des erreurs le
commande : classer trop haut coute une gene visible et reversible ;
classer trop bas envoie un secret chez un tiers, definitivement, sans que
personne le sache. Trois garde-fous pour que ce soit tenable — le refus
est nomme, il se contourne une fois et explicitement, et un contournement
repete propose une regle au lieu de s'installer en silence.

**La structuration se fait maintenant, l'authentification non.**
`user`, `project` et `workspace` entrent dans le modele de donnees au
moment ou le Run Ledger cree ses tables : trois colonnes coutent trois
colonnes maintenant, et une migration sur des donnees reelles plus tard.
L'authentification, non : Hermes ecoute sur `127.0.0.1` et une
authentification apporterait une surface sans proteger de rien de reel —
ce serait de la securite apparente.

La ligne a ne pas franchir est gardee par un test : tant qu'il n'y a pas
d'authentification, `user_id` ne doit jamais servir de controle d'acces.
C'est un champ de traçabilite, et un cloisonnement fonde dessus n'en
serait pas un.

### Mesures

62 gardes ajoutees sur les quatre jalons. Suite complete verte.


## HOS-214 - Le cahier des charges, confronte au code (2026-09-02)

Un cahier de 111 points a ete transmis, inspire d'Agent OS, d'OpenRouter
et d'OmniRoute. Ses 111 points ont ete sondes dans le depot, puis le code
source d'Agent OS a ete lu.

### Ce que la confrontation donne

| Etat | Compte | Part |
|---|---|---|
| existe et tient | **46** | 41 % |
| existe a moitie | **28** | 25 % |
| absent | **35** | 32 % |
| ecarte | 2 | 2 % |

Un cahier qui demande de batir ce qui existe coute autant qu'une roadmap
en retard. Six verdicts ont ete retournes dans les deux sens en relisant
les faux positifs des mots courants — `scope`, `score`, `canonical`,
`objectif`, `reserve`.

### Agent OS, ce qu'il est reellement

**Une application Next.js en TypeScript** : 369 fichiers `.ts`, 124
`.tsx`, ~67 000 lignes, contre 1 112 de Python. 86 modules dans
`src/lib`, 236 points d'API sur 47 domaines, 46 fichiers de test. Le
cahier ne le mentionnait nulle part, et **aucune ligne n'est reprenable**
— ce qui se transfere est son modele de donnees, ses invariants et son
modele de menaces.

Verifie : **zero occurrence d'OmniRoute** dans son code. Le cahier avait
raison, ce n'est pas une dependance d'Agent OS.

### La suite adverse a reordonne la roadmap

Leur lot de tests `m8` decrit des attaques que Hermes ne pare pas, et
trois manques que j'avais classes « confort » se revelent etre des
**controles** :

**La quarantaine memoire est la defense contre l'injection de prompt.**
Leurs tests gardent une seule propriete : le contenu en quarantaine
n'entre jamais dans le contexte resident ni dans une recherche sans
drapeau explicite, et l'origine non humaine est mise en quarantaine *quel
que soit son contenu*. Dans Hermes, une memoire produite par un agent
devient un fait immediatement.

**Un agent peut modifier la configuration qui le gouverne.**
`m8-hostile-config` detecte comme derive un workspace qui ajoute
`.claude/settings.json`, modifie `.claude/hooks`, ajoute un serveur MCP
dans `.mcp.json` ou modifie `CLAUDE.md`. Leur mecanisme est une table de
lignes de base comparee a chaque run. Hermes ne pare pas ça.

**L'etat utilisateur vit dans le depot.** 18 Mo de base, 8,2 de bus
d'evenements, 2,2 de snapshots. La premiere mise a jour qui remplace le
repertoire efface la base, la memoire et la capacite de reprise. Leur
reponse est un « preserve set » explicite et une base rangee hors de
l'application.

Ces quatre jalons — separation de l'etat, quarantaine, ligne de base de
configuration, canary — passent **devant** le Contract et le Run Ledger.
Les construire apres reviendrait a batir la tracabilite dans un dossier
effaçable, au-dessus d'une memoire empoisonnable.

### Trois gains caches sous un « ca existe deja »

**Hermes ne sait pas annuler une modification de fichier.**
`snapshot_manager` serialise l'etat de base ; leur checkpoint est une
reference git sur un commit detache, via un index temporaire, avec
verification d'integrite par re-hachage. Complementaires, pas redondants.

**La verification est booleenne.** Chaque controle de `verification.py`
rend `-> bool`. Ils distinguent `passed | failed | unavailable`, avec le
commentaire « never conflate unavailable with passed », et le gardent
dans leur suite de **securite**. Le cas s'est produit le 2026-08-30 :
`img07` etait `indetermine` et cet etat n'avait nulle part ou aller.

**L'approbation existe et n'est appelee nulle part.** `approval_engine`
sait `required_approvals` et `delegated_to`. Aucun chemin reel n'y passe.

### Deux points ou Hermes est devant

**Les sessions d'agent.** Ils ont mesure `hermes -z` par tour a ~28 s de
demarrage a froid et l'ont contourne par un serveur global chaud sur
`:8642`. HOS-138 tient une session ACP **par mission** — 220 Mio
mesures, tours serialises par un verrou.

**Le bus d'evenements.** Le leur est une seconde table `run_events` avec
`seq = MAX+1` sous transaction. Celui de Hermes est durable, rejouable
par plage et par motif, avec des identifiants idempotents. Le Ledger
portera les runs, pas les evenements — en porter un second creerait
l'architecture parallele que le cahier interdit a sa propre regle 4.

### Ce qui est ecarte, et pourquoi

**Le pool de comptes multiples chez un meme fournisseur.** Le cahier
demande de respecter les conditions des fournisseurs puis decrit un
mecanisme dont la finalite est d'agreger des quotas gratuits en faisant
tourner plusieurs comptes. C'est une violation des CGU de la plupart
d'entre eux.

**SEO, Leads, CRM, Music, Games.** Classes en extensions par le cahier
lui-meme, puis reintroduits dans sa liste finale. Ils n'entrent pas tant
que l'architecture de plugins n'existe pas.

### Surfaces

`docs/cahier-des-charges-hermes-2.md` — le cahier adapte, qui fait foi.
`docs/sondage-cahier-111-points.md` — les 111 points, un par un, avec la
preuve de chaque verdict. `ROADMAP.md` chapitre I — dix-neuf jalons
ordonnes.


## HOS-213 - La commande documentee etait plus etroite que la configuration (2026-09-02)

`tests/` — 2 594 tests, 53 % du depot — ne se collectait plus depuis
HOS-175. Vingt-deux jours, trente-sept jalons.

### La cause n'etait pas la configuration

`pytest.ini` declare `testpaths = backend/tests tests` depuis HOS-111,
avec un commentaire qui raconte precisement cet incident : 2 869 tests
que personne n'executait, 33 rouges dedans dont un vrai defaut
fonctionnel. La configuration etait juste.

C'est `CLAUDE.md` qui documentait `pytest backend/tests`. **Un chemin
passe en argument ecrase `testpaths`.** La commande documentee etait plus
etroite que la configuration, et l'angle mort s'est rouvert le jour ou on
l'a ecrite.

HOS-111 avait traite l'occurrence, pas la cause.

### Trois defauts dans l'arbre abandonne

**Un module qui ne s'importe plus.** `tests/conversation/test_conversation.py`
importait `WhisperProvider`, `CloudSTTProvider`, `PiperProvider` et
`CloudTTSProvider` — supprimes a HOS-175 parce que chacun se declarait
disponible sur un simple import et levait `NotImplementedError` au
premier appel. La suppression etait juste ; le test est reste sur elles.
Reecrit sur `PiperLocal` et `WhisperLocal`, les implementations reelles,
avec une garde qui refuse le retour des quatre souches.

**Une garde qui protegeait le chemin qu'on n'emprunte pas.**
`fake_inference.install()` ne patchait que `_default_chat`. Or
`execute()` choisit entre trois producteurs d'appel :

| Condition | Producteur |
|---|---|
| runtime `hermes-agent` | `_hermes_agent_chat_for` — **sous-processus** |
| mission liee a un workspace | `_chat_with_tools_for` — boucle d'outils |
| sinon | `_default_chat` — appel simple |

Le premier est le cas **par defaut** : Hermes Agent est le cerveau des
missions, et une `ExecutionMeta` sans workspace y aboutit.
`test_execute_single_task` et `test_get_goal` lançaient donc un vrai
sous-processus et bloquaient l'arbre entier. Apres correction : **0,5 s
au lieu de seize minutes**.

**Une course prise pour une regression.**
`test_sortie_de_l_agent.py::test_une_sortie_volontaire_est_nommee_comme_telle`
dormait 0,3 s puis diagnostiquait un sous-processus cense etre mort. Sur
une machine chargee, le demarrage de l'interpreteur depasse ce delai : le
diagnostic repondait — a juste titre — « le processus vit encore ». Le
test echouait sur la vitesse de la machine. Remplace par une attente
bornee de la vraie fin du processus ; stable sur trois executions.

### Ce qui garde la correction

Trois gardes, dont une qui surveille **la documentation** : elle lit les
blocs `bash` de `CLAUDE.md` et echoue si un chemin y est passe en
argument. Verifiee rouge sur le defaut, verte apres.

`tests/` passe de « ne se collecte pas » a 2 594 verts en 1 min 40.
Suite complete : **4 865 passed, 3 skipped**, 4 min 44.


## HOS-212 - Juger une voix et une image sur ce qu'elles sont, pas sur leur existence (2026-08-30)

Une premiere production reelle a servi de revelateur, comme HOS-211. Trois
instruments manquaient, et chacun a trouve un defaut des sa premiere
utilisation.

### La narration n'etait jugee que sur sa duree

Chatterbox rend un WAV valide, d'une duree plausible, **quoi qu'il ait
prononce**. Une replique ou il boucle sur un groupe de mots, ou bien ou il
ajoute un mot apres la fin du texte, ne se distingue en rien d'une bonne
replique : meme format, meme duree approximative, aucune erreur.

L'utilisateur a entendu deux defauts sur la premiere narration clonee :
« cette nuit » repete dans la premiere replique, et un « ok » ajoute a la
toute fin. `scripts/verifier_narration.py` transcrit et compare — il les
retrouve tous les deux, et en trouve un troisieme que personne n'avait
signale : **« les marais » a la place de « les marees »**. Sur une video
scientifique, ca change le sens.

La voix precedente sert de temoin, et c'est elle qui rend la mesure
utilisable : une transcription se trompe sur les homophones, et « les
marees » transcrit correctement sur la voix temoin prouve que l'ecart
vient de la voix clonee, pas du transcripteur. Deux autres ecarts —
« et »/« elle », « remarqueras »/« remarquerais » — sont du bruit de
transcription, et le temoin le montre aussi.

`faster-whisper` tourne sur processeur : la verification reste donc
possible pendant un rendu.

### Les reglages de voix ne se transposent pas d'une reference a l'autre

`exaggeration 0.3 / cfg_weight 0.3` avaient ete mesures en HOS-195 sur la
reference « Michael ». Les reprendre pour une autre voix etait une
supposition, et elle etait fausse.

Le banc, sur les trois repliques fautives :

| reference | cfg 0,3 | cfg 0,5 | cfg 0,7 |
|---|---|---|---|
| brute — finit en pleine parole | « debut » ajoute | derive complete | mot deforme |
| close — coupee sur un silence | « marais » | **propre** | « marais » |

Aucun des deux leviers ne suffit seul. La reference fournie se terminait
**en pleine parole** — mesure a -24,1 dB sur la derniere demi-seconde :
rien n'y signalait qu'un enonce s'acheve, ce qui explique un modele qui
continue apres le texte. Coupee sur un silence reel avec un fondu et
350 ms de blanc, et a `cfg_weight 0.5`, les trois defauts disparaissent.

Corriger les defauts **allonge** la parole : 30,04 s contre 26,88 s. Le
modele ne bacle plus les fins de phrase.

### Un clone se verifie a la mesure

`scripts/hauteur_voix.py` reprend la methode de HOS-195 — hauteur mediane
par autocorrelation, sur les trames voisees seulement — au lieu de la
reecrire a chaque changement de voix. La reference fournie est a 85,4 Hz ;
le clone rend 81,1 / 85,6 / 86,3 Hz. Il s'est bien deplace vers elle, et
non vers les 157 Hz de la voix par defaut du modele.

Le nombre de trames voisees compte autant que la hauteur : un clone qui
n'en produit que quatre sur une phrase entiere n'a pas une hauteur
imprecise, il n'a presque pas de voix. Releve sans conclusion : la
dispersion de hauteur de ce clone est le double de celle de « Michael »
(84-109 contre 32-43).

### La synthese sur processeur : possible, et mauvaise

`synthetiser(appareil="cpu")` existe pour narrer pendant qu'une nuit de
rendu tient les 16 Gio — l'arbitrage refuse alors la carte, a juste
titre, et attendre deux heures serait absurde. Sur processeur la synthese
ne reserve rien, puisqu'elle ne prend rien.

Mesure : **une replique en 49 minutes sur processeur, sept en 119 secondes
sur la carte.** Le repli reste juste en principe ; a ce rapport, mieux
vaut attendre. C'est ecrit ici pour que personne ne le redecouvre.

### Le relecteur ne savait pas lire une image fixe

`extraire()` demandait la duree du fichier, qui vaut zero pour un PNG, et
rendait une liste vide : « aucune image n'a pu etre extraite du plan ».
Vrai au pied de la lettre, faux sur le fond. Les sept references SDXL
d'une production finissaient `indetermine`, donc jamais confrontees a leur
consigne — alors que ce sont elles qui decident du decor de tous les plans
qui en decoulent.

Une image est son propre cadre. Des la correction, le relecteur a rejete
une reference en nommant deux ecarts reels : un sol pave annonce comme
asphalte, et une **Lune en croissant** la ou la consigne demandait une
pleine Lune. Sur une video dont le sujet est la disparition de la Lune, le
second n'est pas un detail.

Releve sans conclusion : la meme image a recu deux verdicts opposes du
meme modele a temperature 0,1. Une seule relecture ne fait donc peut-etre
pas une garde. Non verifie proprement — la carte etait prise, et sonder
pendant un rendu mesure la contention.

### Le relecteur empoisonnait le rendu suivant

Trouve en cherchant pourquoi un plan sur deux rampait. Le motif etait
net et je ne le lisais pas : **le premier rendu apres un redemarrage
passe toujours, le second tient quarante minutes sans aboutir.**

La file relit chaque plan avec un modele de vision servi par Ollama.
Ollama garde un modele **resident cinq minutes** par defaut, et le plan
suivant demarre bien avant.

| mesure | valeur |
|---|---|
| ce que le relecteur retient | **2,41 Gio de VRAM** |
| expiration par defaut | 5 minutes |
| ecart relecture de p01 / depart de p02a | **90 secondes** |

Sur 15,98 Gio dont un decodage reclame pres de 13, ces 2,41 Gio suffisent
a faire basculer le rendu entier sur la memoire partagee. Le rendu ne
debordait pas tout seul : il debordait de ce que le relecteur tenait
encore.

Trois plans perdus avant de le voir — 39 min, 40 min, puis un abandon en
cascade. `keep_alive: 0` : le relecteur rend la carte des qu'il a
repondu, verifie a `/api/ps`. Il travaille **entre** deux rendus sur une
carte qui n'en supporte qu'un ; rester charge n'avait aucun interet et
coutait le plan suivant.

Les chiffres se referment exactement :

| | |
|---|---|
| pic de VRAM d'un rendu, mesure sur `p02a` | **13,98 Gio** |
| carte | 15,98 Gio |
| marge disponible | **2,00 Gio** |
| ce que le relecteur retenait | **2,41 Gio** |

Il manquait 0,41 Gio. Le rendu ne debordait pas d'un peu : il debordait
de tres exactement ce qu'un modele de 2,41 Gio prend a une marge de 2,00.

Corrobore par le resultat : `p02a`, qui avait tenu 2 404 s sans aboutir,
passe en **1 365 s** — le meme temps que `p01` a 1 358 s. Le second plan
n'etait pas plus lourd que le premier ; il etait le premier a subir le
relecteur.

### Un montage amputé rendait `success: true`

Le defaut le plus grave de la nuit. `montage.assembler` verifie que le
resultat dure ce que les plans **qu'on lui donne** annoncaient. Il n'a
aucun moyen de savoir combien on aurait du lui en donner.

Il a donc valide une video de **4,0 secondes faite d'un plan sur dix**,
en releguant au rang d'avertissement une narration de 35,7 s posee
dessus — un ecart de +31,7 s.

C'est le `success: true` au-dessus de rien que ce depot traque depuis le
debut, passe par une porte que personne ne gardait. Le refus est pose chez
l'appelant, qui est le seul a savoir ce qu'il attendait :
`finaliser_lune.py` refuse d'assembler si un seul plan manque, et traite
un ecart voix/image au-dela de six secondes comme une erreur.

### Attendre un fichier n'est pas attendre une fin

Meme incident, plus petit : le script de finalisation guettait
l'apparition du MP4 pour enchainer. Or le fichier est ecrit **avant** la
relecture. Il a enchaine trop tot, la file suivante a ete refusee — « une
file de nuit tourne deja » — et toute la production est tombee. On attend
desormais `en_cours` a faux.

### Les consignes, reecrites sur des defauts constates

L'utilisateur, sur le premier plan rendu : une voiture garee sur le
trottoir, des passants trop nombreux, trop rapides, qui apparaissent et
disparaissent. Trois regles en sont sorties, appliquees a tous les plans :

**Nommer ce qui ne bouge pas.** LTX anime tout ce qu'on ne fige pas
explicitement.

**Dire la vitesse reelle.** Le modele comprime volontiers une action
entiere dans les quatre secondes qu'on lui donne. « Real-time speed, this
is not a time-lapse » corrige l'impression d'accelere.

**Interdire les entrees et sorties de cadre.** Un passant qui entre
pendant le plan n'a aucune histoire avant : le modele le fabrique image
par image, et il scintille.

Effet de bord mesure : cinq formulations negatives sur la voiture mal
garee suppriment la **classe d'objet entiere**. La reference corrigee n'a
plus aucun vehicule, et le relecteur a rejete l'image parce que la
consigne en demandait encore. C'etait la consigne qui etait fautive.

Backend 2263 passed, 2 skipped.


## HOS-211 - Ce qui manquait pour produire une video, et non plus des plans (2026-08-29)

Un cahier de production reel — dix plans, deux chaines de continuite, une
narration, des sous-titres — a servi de revelateur. Le Studio savait
rendre des plans ; il ne savait pas en faire une video.

### Cinq manques, dont un structurel

**La file de nuit ne savait pas enchainer.** `POST /studio/night`
composait **tous** les graphes a la soumission. Un plan dont l'image de
depart est la derniere image du plan precedent etait donc inexprimable :
ce fichier n'existe pas quand on decrit la nuit. Toute continuite
visuelle — meme decor, meme lumiere, meme personnage d'un plan au suivant
— etait hors de portee d'une nuit.

Un plan peut desormais etre decrit par `gabarit` + `parametres`, compose
**au moment de son rendu**, et declarer `depend_de`.

Le point delicat n'est pas la resolution, c'est l'echec. Un plan dont le
predecesseur n'a rien produit repartirait du bruit, rendrait un MP4
parfaitement valide, et la rupture ne se verrait qu'au montage — apres la
nuit. C'est la forme de defaut que ce depot paie le plus cher :
`success: True` au-dessus de rien. Il est donc `abandonne`, en nommant le
plan manquant, et sans compter comme un echec de rendu : trois plans
dependant d'un meme absent arreteraient sinon la file entiere alors qu'un
seul defaut est en cause.

**Rien ne transportait une image vers l'entree de LTX.** SDXL ecrit dans
`E:\YouTube\Generations` ; `LoadImage` ne lit que le `input` de ComfyUI.
`/studio/last-frame` ne savait extraire que depuis une video.
`enchainement.preparer_depart()` fait les deux et refuse une extension
inconnue plutot que de la deviner.

**Une image de rapport different aurait ete etiree, en silence.**
`LTXVImgToVideo` recoit les dimensions du plan et redimensionne **sans
recadrer**. Une reference SDXL en 768 x 1344 (rapport 0,571) donnee a un
plan en 704 x 1280 (0,550) est deformee — visible sur un visage, et rien
ne le dit. Le recadrage est centre, coute 3,8 % de champ lateral, et les
dimensions visees voyagent avec la demande.

**Aucune image fixe ne devenait une video.** Quatre plans sur dix sont des
images avec un mouvement lent. `concat` enchaine des flux video : un PNG
n'en est pas un. `montage.animer()` produit un clip au format exact des
autres — meme taille, meme cadence, meme profil — parce qu'un plan qui
differerait ferait echouer l'assemblage a la toute fin, apres deux heures
de rendu. Le `zoompan` travaille sur une image agrandie huit fois : sur
l'image a sa taille finale, le cadre saute d'un pixel entier d'une image
a l'autre et la saccade se voit.

**La narration n'avait pas de respirations.** Chatterbox lit ce qu'on lui
donne. `montage.coller_voix()` intercale des silences reels — des entrees
`lavfi` et non un `apad`, qui allongerait la derniere replique et
accumulerait le decalage sans qu'aucune duree ne le dise.

### Le defaut trouve en eprouvant le reste

`assembler` portait `-shortest` avec le commentaire « l'image commande ».
Il fait la moitie du travail : il coupe bien une narration trop longue,
mais il coupe aussi **l'image** quand la voix est plus courte. Mesure :
trois plans de 6,0 s avec une voix de 5,4 s rendaient une video de 5,4 s
— six dixiemes de seconde d'image simplement absents, sans erreur.

`apad` complete l'audio de silence et `-shortest` coupe alors sur
l'image. C'est ainsi que la phrase devient vraie dans les deux sens.

Ce defaut existait depuis HOS-191. Il n'a jamais ete vu parce qu'aucune
narration n'avait ete plus courte que l'image.

### Ce qui s'ajoute au montage

Un lit sonore mixe **sous** la voix, boucle et coupe sur la duree de
l'image ; et une mise a l'echelle en sortie. 704 x 1280 vers 1080 x 1920
est un facteur 1,53 en lanczos, sans information nouvelle : c'est ce que
demandent les plateformes, qui reencodent de toute facon. L'appeler un
upscale serait mentir sur ce qu'on livre.

Les sous-titres sont incrustes **avant** l'agrandissement : les poser sur
l'image agrandie les garde nets.

### Surfaces

`POST /studio/assemble`, `POST /studio/animate`, `POST /studio/start-frame`.
`montage.assembler` existait depuis HOS-191 mais n'etait joignable que
depuis Python : une production lancee la nuit ne pouvait donc pas se
terminer toute seule.


## HOS-210 - Le reglage du decodeur se mesure au lieu de se supposer (2026-08-29)

Trois fois de suite — HOS-205, HOS-208, HOS-209 — le defaut visible venait
de la **meme** table ecrite a la main, `PALIERS_TUILE`. Trop prudente
d'abord (elle descendait a 64 la ou 128 tenait, d'ou le quadrillage), mal
calibree ensuite. HOS-209 a rectifie un seuil ; il n'a pas rectifie le
fait qu'un seuil ecrit a la main est faux des que quelque chose bouge.

Et l'echec tombe **au decodage, apres la diffusion** : vingt minutes de
calcul pour decouvrir que la tuile ne passait pas.

### L'essai a blanc

La memoire du decodeur ne depend que des **dimensions** du latent, jamais
de son contenu. Decoder un latent vide exerce donc le meme chemin memoire
qu'un vrai plan, sans charger un seul modele de diffusion. C'est la
technique qui avait permis toute la campagne de mesure ; elle est
maintenant dans le produit, derriere un bouton.

La recherche part de ce que la table propose, puis **monte** tant que ca
passe et **descend** au premier debordement. Une descente depuis 256
coutait jusqu'a sept essais de plusieurs minutes chacun — c'est-a-dire un
reglage qu'on renonce a mesurer.

### Quatre defauts de l'instrument, trouves en le faisant tourner

Aucun en relisant le code. Tous sur un chiffre invraisemblable.

**La memoire ne se libere pas entre deux essais.** Deux essais consecutifs
ont vu **19,29 puis 25,64 Gio deja alloues** sur une carte de 15,98 : le
second debordait pour une raison etrangere a ce qu'il mesurait. Sans
remise a zero, la recherche conclut sur du bruit. `/free` avant chaque
essai.

**Un decodage qui deborde ne s'arrete pas, et rien ne l'arrete.** Il
bascule sur la memoire partagee et rampe : un essai a tenu **quarante
minutes** sans aboutir ni echouer, le processus consommant une seconde de
CPU par seconde ecoulee. `/interrupt` ne mord pas dessus — verifie deux
fois, la carte restant a 14,18 Gio apres l'appel ; il a fallu relancer
ComfyUI. L'essai qui n'aboutit pas est desormais interrompu avant de
rendre la main, ce qui suffit pour un essai qui tourne normalement mais
**pas** pour celui-la. La seule protection reelle est de ne pas l'y
laisser arriver, d'ou le plafond ci-dessous — et la reponse le dit
maintenant : « la carte peut rester occupee ».

**« Ca passe » ne veut pas dire « c'est utilisable ».** La tuile 160
decode 768x416x97 en quatre minutes ; la 192 tenait encore apres vingt,
avec 14,18 Gio de VRAM sur 15,98. Une premiere version l'aurait retenue
comme « la plus grande qui passe », et cette lenteur se serait payee a
chaque rendu — a rebours de la consigne, « de la qualite, mais dans un
temps acceptable ». La montee est bornee a deux fois et demie le cout du
premier succes.

**Un verdict incertain n'est pas un debordement.** `delai` et `erreur`
arretent la recherche au lieu de la faire continuer, et la route ne dit
plus « aucune tuile ne passe » quand elle n'a rien mesure : c'est cette
confusion entre « la carte ne peut pas » et « je n'ai pas su lire » qui a
produit trois faux resultats pendant HOS-207.

### La table de depart

Cinq entrees y ont ete versees a la creation, tirees des rendus reels de
la campagne plutot que redemandees a la carte : 768x416 a 49, 121 et 257
images (tuiles 256, 160, 128), et 1280x704 a 121 et 217 images (128 et
64). Elle vit a cote des rendus, pas dans le depot : c'est une mesure
propre a cette machine, pas un fait du code. `PALIERS_TUILE` reste le
repli, et une table illisible ne bloque jamais un rendu.

### La mesure de bout en bout, faite

768x416 sur 97 images, par la route de l'interface, sur une carte vide :
**tuile 160**, deux essais, 1500,8 s au total. La 160 decode en 296,5 s ;
la 192 tenait encore apres 1203,9 s et a ete classee `delai`, ce qui a
arrete la montee sans rien conclure sur elle.

La table ecrite a la main proposait deja 160 pour ce plan : la mesure la
**confirme** ici plutot que de la corriger. C'est le resultat attendu dans
le cas courant — l'interet n'est pas que la table soit fausse partout,
c'est de ne plus avoir a le supposer. Avec le plafond de rampe, la meme
mesure aurait coute 741 s au lieu de 1204 pour le second essai, meme
reponse.

### Ce que l'ecran dit

Sous le formulaire, une ligne par plan : soit « Decodage eprouve sur cette
machine — tuile N, mesuree le … », soit un avertissement disant d'ou vient
le reglage affiche, et un bouton pour mesurer.


## HOS-209 - Le quadrillage : HOS-208 se trompait de cause (2026-08-29)

HOS-208 attribuait le quadrillage a un **recouvrement nul** : le calcul
`min(32, tuile // 4)` donnait 16 pour une tuile de 64, et le nœud divise
cette valeur par la compression spatiale du VAE (32), donc `16 // 32` = 0.
Le raisonnement etait juste et le calcul reellement fautif.

**Ce n'etait pas la cause.**

### Comment le defaut de diagnostic a ete trouve

Le meme plan, meme graine, rendu avec un recouvrement de 16 puis de 32 :
les pixels sont **rigoureusement identiques**, ecart maximal **zero**.
Seules les metadonnees PNG different — ComfyUI y grave le graphe, qui
portait bien les deux valeurs distinctes.

Le premier indice etait la taille des deux fichiers video, identique a
l'octet pres (11 032 Ko). C'est en la trouvant invraisemblable qu'il a
fallu verifier, exactement comme pour les autres defauts de cette
campagne : aucun n'a ete trouve en relisant le code.

HOS-208 avait donc ete commite et pousse **en presentant comme solution un
correctif inoperant**. Sans la demande d'un nouveau rendu, il restait au
depot comme un fait acquis.

### La vraie cause

La **taille** de la tuile, pas son recouvrement. 64 pixels font deux
unites latentes seulement, et le VAE n'a pas assez de contexte pour
decoder un carre aussi petit. Aucun fondu ne rattrape ca.

Et la table de HOS-207 etait **trop prudente** : elle descendait a 64 des
un volume de 90, alors que la mesure montre que 128 tient a 109 — soit
precisement le cas signale, 1280 x 704 sur cinq secondes.

| volume | format et longueur | tuile | verdict |
|---|---|---|---|
| 82,1 | 768x416, 257 img | 128 | passe |
| **109,0** | **1280x704, 121 img** | **128** | **passe (437 s)** |
| 109,0 | 1280x704, 121 img | 96 | passe (245 s) |
| 195,6 | 1280x704, 217 img | 64 | passe |

Le palier 128 monte donc de 90 a 110. La tuile 64 ne subsiste qu'au-dela
de sept secondes en format lourd, ou rien d'autre ne tient.

Contre-intuitif, releve au passage : la tuile 96 decode en 245 s contre
437 s pour la 128. Une tuile plus petite est donc **plus rapide** ici, la
memoire etant moins sollicitee — le compromis n'est pas « qualite contre
vitesse » dans le sens attendu.

### Ce qui est garde de HOS-208

Le calcul du recouvrement, corrige. Il est juste sur le fond — un
recouvrement qui vaut zero apres division ne sert a rien — et il est
desormais documente comme **sans effet mesurable**, pas comme un remede.
Le garder coute une ligne ; le presenter comme une solution serait
mentir.

### Ce que cet incident apprend

Trois defauts de suite ont ete vus par l'utilisateur avant de l'etre par
la mesure : le comptage des coutures, l'infirmation du gain de
`res_multistep`, et ce quadrillage. Le point commun est que l'indicateur
de dispersion mesure le **deplacement du contenu** — il est aveugle a un
motif fixe, et il l'etait des la construction.

Le correctif de HOS-208, lui, n'a pas ete verifie **avant** d'etre
pousse : le rendu de confirmation a ete lance apres le commit. L'ordre
inverse aurait evite de publier une fausse cause.

Backend 2210 passed, 2 skipped.

## HOS-208 - Le quadrillage : un recouvrement qui valait zero (2026-08-29)

> **Amende par HOS-209 le meme jour : cette cause est fausse.** Le meme
> plan rendu avec un recouvrement de 16 puis de 32 donne des pixels
> rigoureusement identiques, ecart maximal zero. Le correctif decrit
> ci-dessous est juste sur le fond mais **sans effet** sur le defaut
> signale. La vraie cause est la taille de la tuile — voir HOS-209.

L'utilisateur, sur le premier rendu en 1280 x 704 issu de HOS-207 : « je
n'ai pas de probleme de scintillement en revanche l'image forme comme un
quadrillage ».

Le scintillement etait bien corrige. Mais le correctif en avait introduit
un autre, dans le meme nœud.

### La cause

`VAEDecodeTiled` divise `overlap` par la compression spatiale du VAE, qui
vaut 32 — exactement comme il divise `tile_size`. Mon calcul etait
`min(32, tuile // 4)`, soit **16** pour une tuile de 64. Et `16 // 32`
vaut **zero** : les carres se juxtaposaient sans le moindre fondu.

| tuile | recouvrement avant | en latentes | apres |
|---|---|---|---|
| 256 | 32 | 1 | 2 |
| 160 | 32 | 1 | 1 |
| 128 | 32 | 1 | 1 |
| **64** | **16** | **0 — quadrillage** | **1** |

Le defaut ne touchait donc que la tuile de 64, c'est-a-dire uniquement
les plans lourds ou longs. Les autres paliers tombaient deja sur une
latente de fondu, ce qui explique que le paysage n'ait jamais quadrille
et que le defaut ait passe la validation precedente.

`recouvrement_spatial()` garantit desormais au moins une unite latente,
et plafonne a la moitie de la tuile — au-dela, les carres se recouvrent
plus qu'ils ne couvrent et le decodage paie deux fois le meme pixel.

### Ce que cet incident apprend

L'indicateur de dispersion utilise pendant toute cette campagne mesure le
**deplacement du contenu**. Il est structurellement aveugle a un motif
**fixe** : une grille immobile ne deplace rien, donc il ne la voit pas.
Aucune de ces mesures n'aurait pu attraper ce defaut.

C'est la troisieme fois de la campagne que l'œil de l'utilisateur voit ce
que les chiffres ne peuvent pas voir — apres le comptage des coutures
(quinze scintillements pour quinze tuiles, correspondance exacte) et
l'infirmation du gain de `res_multistep`. La lecon vaut d'etre ecrite :
un instrument ne mesure que ce qu'il a ete construit pour mesurer, et le
defaut suivant est rarement dans cette dimension-la.

### Temps de generation, mesure

22,7 minutes pour 5 secondes en 1280 x 704, decodage compris. Dans le
meme temps, le format paysage produit environ quatre plans de 5 secondes
— vingt secondes de matiere au lieu de cinq.

Quatre gardes-fous nomment l'incident, verifies rouges sur l'ancien
calcul. Backend 2210 passed, 2 skipped.

## HOS-207 - Une seule tuile temporelle, a toute longueur (2026-08-29)

HOS-205 avait mis `temporal_size` a 64. **Ce n'etait pas assez.**
L'utilisateur a compte les coutures a l'oeil : quinze scintillements sur
un plan que le code decoupait en quinze morceaux, trois sur celui qu'il
decoupait en trois. Un par couture, sans exception.

Il en faut donc **une**, pas « moins ». 64 ne donnait un bloc unique
qu'aux plans de deux secondes ; a cinq secondes il en laissait trois.

### Le prix, et pourquoi c'est le bon echange

`temporal_size` vaut desormais 4096 — 512 images latentes par tuile,
contre 33 pour le plan le plus long du gabarit. Le bloc est unique
quelle que soit la longueur.

Ce bloc coute de la memoire, et la seule variable qui reste pour la payer
est la taille des carres **spatiaux**. L'echange est favorable : une
couture spatiale tombe au meme endroit a chaque image, donc elle ne
scintille pas. C'est toute la difference entre les deux decoupages, que
mon vocabulaire avait confondus pendant une partie de la campagne.

### La table, mesuree

Volume = `pixels x images`, en millions. Decodage en un bloc.

| volume | format et longueur | tuile | verdict |
|---|---|---|---|
| 15,7 | 768x416, 49 img | 256 | passe |
| 38,7 | 768x416, 121 img | 160 | passe |
| 44,2 | 1280x704, 49 img | 256 | **deborde** (12,81 Gio) |
| 82,1 | 768x416, 257 img | 160 | **deborde** (13,13 Gio) |
| 82,1 | 768x416, 257 img | 128 | passe |
| 195,6 | 1280x704, 217 img | 64 | passe |

`tuile_spatiale()` choisit d'apres ce volume. Les paliers sont poses
**sous** la premiere mesure qui deborde, jamais entre deux mesures : une
extrapolation optimiste transformerait un rendu mediocre en rendu absent,
ce qui est bien pire.

### Longueur maximale par format

| format | longueur max, un seul bloc | tuile |
|---|---|---|
| 768 x 416 | **10 s** (257 img) | 128 |
| 1280 x 704 | **9 s** (217 img) | 64 |
| 704 x 1280 | 9 s (meme volume, grille transposee) | 64 |

Le 257 images en format lourd n'est pas un debordement mais un
**indetermine** : trente minutes de decodage sans aboutir. Rapporte comme
tel — confondre « la carte ne peut pas » et « je n'ai pas attendu assez »
est l'erreur qui a produit trois resultats faux pendant cette campagne.

### Le cout, qu'il faut connaitre avant de choisir un format

Decodage seul, format 1280 x 704, bloc unique :

| longueur | decodage |
|---|---|
| 7 s (169 img) | 253 s |
| 9 s (217 img) | **806 s** |
| 10 s (257 img) | ne finit pas en 30 min |

Le saut entre 7 et 9 secondes est brutal. Conclusion pratique, et c'est
celle de l'utilisateur : mieux vaut cinq plans de cinq secondes en
paysage qu'un plan de neuf secondes en format lourd — meme temps total,
cinq fois plus de matiere.

### Trois instruments de mesure jetes en route

La campagne a demande trois versions de la sonde, les deux premieres
ayant rendu des verdicts faux :

1. **Delai confondu avec debordement.** Un delai de 420 s plus court que
   certaines sondes (374 s mesurees) faisait compter tout depassement
   comme un manque de memoire. Elle a annonce qu'aucune tuile ne passait
   a 97 images, la ou un vrai rendu a 121 avait abouti.
2. **Deconnexion prise pour un delai.** ComfyUI ferme parfois la
   connexion en gerant un `out of memory` ; la boucle mourait dessus et
   rendait « delai » alors que l'historique portait un debordement
   lisible.
3. La troisieme reessaie, lit l'erreur reelle, et cherche en montant
   depuis les petites tuiles — descendre depuis 256 coutait vingt-cinq
   minutes avant le moindre verdict.

Aucun de ces defauts n'a ete trouve en relisant le code. Tous l'ont ete
sur un chiffre invraisemblable.

Backend 2206 passed, 2 skipped.

## HOS-206 - La file de nuit se lance enfin depuis l'ecran (2026-08-28)

L'utilisateur : « peux-tu m'expliquer a quoi sert l'interface nuit de
l'onglet studio ? il n'y a pas de bouton accessible ou autre je ne
comprends pas son interet ou utilisation ».

Il n'y avait effectivement aucun bouton. L'onglet ne savait que **lire**
le rapport du matin ; le lancement n'existait que comme outil MCP
`studio_night`, donc uniquement accessible en le demandant a l'agent dans
le chat.

C'est le troisieme cas identique en trois jours — la voix Michael
(HOS-196), les trois parametres de rendu (HOS-199), et maintenant la file
de nuit. Le motif est toujours le meme : une capacite backend reelle,
testee, et sans aucune commande a l'ecran.

### Pourquoi l'ecran ne pouvait pas la lancer

`POST /studio/night` exigeait un `graphe` ComfyUI complet par plan. Le
frontend n'en compose aucun, et c'est deliberé : la regle qui prime sur
tout dans ce depot reserve cette decision au gabarit ou a l'agent.

La route accepte desormais `gabarit` + `parametres` par plan, exactement
comme `/render` depuis HOS-194, et compose cote serveur. La voie du
`graphe` reste intacte pour l'agent — un test l'atteste, pour qu'elle ne
regresse pas au profit de la nouvelle.

### Ce que l'ecran annonce avant le clic

Une nuit tient la carte pendant des heures. Le formulaire calcule donc le
cout total de la file — nombre de plans x cout par plan, avec le modele
de HOS-199 — et l'affiche en heures. Un delai maximal par plan est
reglable : au-dela, le plan est abandonne et la file passe au suivant,
plutot que de tenir la carte jusqu'au matin sur un rendu qui ne sort pas.

Les reglages sont communs a toute la file, seule la consigne change d'un
plan a l'autre : une nuit sert a decliner un meme plan, pas a melanger
des formats. Et la consigne n'est pas decorative — c'est elle que le
relecteur oppose au fichier produit. Sans elle le plan finit
`indetermine`, ce qui est correct mais coute un rendu pour rien.

### Tests

Cinq, dont deux qui nomment le defaut : un plan sans gabarit ni graphe
est refuse **en nommant son rang** (sur une file de dix, savoir lequel est
mal decrit evite de relire les dix), et un gabarit invalide de meme.

Backend 2200 passed, 2 skipped. Frontend tsc propre, vitest 113/113.

## HOS-205 - Le scintillement : trouve, corrige, confirme a l'oeil (2026-08-28)

Apres trois tours de mesures infructueux, la cause du scintillement est
le **decoupage temporel du decodeur VAE**. C'est l'hypothese formulee des
le premier tour, ecartee sur un indicateur que le tour suivant a invalide,
et jamais reprise depuis.

### Le calcul que je n'avais pas fait

`VAEDecodeTiled` divise `temporal_size` par la compression temporelle du
VAE, qui vaut 8 pour LTX. Le reglage de 16 ne signifiait donc pas « seize
images par tuile » mais **deux images latentes par tuile**, avec une seule
de recouvrement.

| temporal_size | 49 images | 121 images | 257 images |
|---|---|---|---|
| **16 (ancien)** | **6 tuiles** | **15 tuiles** | **32 tuiles** |
| 64 (retenu) | 1 | 3 | 5 |

Un plan de dix secondes etait reconstruit a partir de trente-deux
morceaux. La description de l'utilisateur — « comme si la video etait
creee en ajoutant des petits morceaux de 0,5 seconde les uns apres les
autres » — decrivait litteralement ce que le code faisait.

### La seule mesure propre de la campagne

A graine fixee le debruitage est deterministe : les latents sont
**identiques** et seul le decodeur change. Aucun bruit de graine possible
— celui-la meme qui avait fabrique tous les faux positifs precedents.
Plan a camera fixe, ou toute vitesse mesuree est un artefact.

| graine | derive fantome a 16 | a 64 | reduction |
|---|---|---|---|
| 777 | 0,108 | 0,035 | **-68 %** |
| 1234 | 0,110 | 0,065 | **-41 %** |

Trois signaux independants concordent, ce qu'aucun autre reglage de cette
campagne n'avait obtenu :

1. la correlation de phase ;
2. le poids des fichiers a CRF constant — **-30 %**, donc autant de
   changement inter-image en moins, mesure par un encodeur qui ne partage
   aucune hypothese avec l'instrument ;
3. **l'utilisateur, a l'oeil** : « la video est beaucoup plus stable, je
   n'ai plus la sensation de scintillement et de saccade ».

### Ce que le correctif ne fait pas

La dispersion locale ne baisse que de 2,5 %. Le decoupage ajoutait une
derive **parasite** ; l'incoherence de fond mesuree en HOS-202 — 2,4 fois
celle d'une video geometriquement parfaite — reste celle du modele. Deux
defauts coexistaient, et les trois premiers tours les ont confondus.

### Pourquoi 64 et non 4096

Le decodage non tuile echoue vraiment ici : `CUDA out of memory`, 10,51
Gio demandes d'un bloc, re-mesure ce tour-ci. Le choix d'origine de tuiler
etait donc fonde — c'est sa taille qui etait mauvaise, pas son principe.

4096 donnerait une tuile unique a toute longueur, mais sa consommation sur
les plans longs n'est pas mesuree et un debordement y transformerait un
rendu mediocre en rendu absent. 64 est meilleur a toutes les longueurs
deja testees, sans ce risque. La mesure sur 121 images est en cours et
pourra faire monter cette valeur.

### Ce que cet incident apprend

L'hypothese correcte a ete formulee au premier tour, puis ecartee sur une
mesure inadaptee — et **jamais reprise** apres que cette mesure eut ete
reconnue fausse. Invalider un instrument ne suffit pas : il faut rejouer
ce qu'il avait servi a ecarter. Deux gardes-fous nomment desormais
l'incident dans `test_studio_gabarits.py`, verifies rouges sur le reglage
d'origine avant d'etre gardes.

### Ce qui a ete essaye sans effet, ce tour-ci

Le post-traitement : `deflicker` et `atadenoise` d'ffmpeg donnent -2 % au
mieux, sur les images deja rendues. La raison est instructive — ces
filtres corrigent des variations de **luminance**, alors que le defaut est
structurel. Aucun etalonnage ne l'aurait rattrape.

## HOS-203 - La quantification n'y est pour rien, la graine pese plus que tout (2026-08-28)

Fin de la campagne sur le scintillement. Deux hypotheses restaient : la
quantification, et la formulation de la consigne. Les deux sont closes, et
un troisieme facteur, jamais regarde, s'avere dominer tous les autres.

### La quantification n'est pas la cause

Trois quantifications telechargees et rendues sur le meme plan statique,
meme graine, meme tout. Mesure sur images brutes, la seule base comparable.

| modele | vitesse | dispersion | ecart |
|---|---|---|---|
| Q5_K_M — 16,82 Go | 0,108 | 0,746 | reference |
| Q6_K — 18,66 Go | 0,138 | 0,952 | non comparable (vitesse x1,28) |
| **Q8_0 — 23,63 Go** | 0,112 | **0,763** | **+2 %** |

Le Q8_0 porte 40 % de bits de plus que le Q5 et donne le meme resultat.

Deux mesures au passage, contre le principe que j'avais suppose : le pic
VRAM reel est **12,71 Gio** et non les 7,6 du tableau de ce document — ces
chiffres ne decrivent pas la configuration actuelle. Et la contrainte est
la **RAM systeme**, pas la carte : le processus monte a 20,6 Gio, il ne
reste que 3,4 Gio libres, et le Q6_K met plus de vingt minutes la ou le Q5
en prend cinq. C'est de la pagination, pas du calcul.

### Les formules de coherence dans la consigne ne font rien

Consigne de l'utilisateur rendue telle quelle, puis privee de ses seuls
termes de coherence (« continuous coherent motion, stable architecture,
consistent lighting throughout the shot »), meme graine.

| | vitesse | dispersion |
|---|---|---|
| avec les formules | 9,70 | 30,385 |
| sans les formules | 8,94 | 30,196 |

**0,6 % d'ecart.** Le modele ne traite pas ces instructions comme des
contraintes.

### Un resultat annonce puis retire

`res_multistep` avait donne -17 % sur la graine 777, a vitesse identique.
Annonce comme « le seul gain solide de la campagne ». **Il ne se reproduit
pas** : sur la graine 1234, les deux echantillonneurs donnent 0,396,
strictement. Le -17 % etait du bruit de graine. Aucun changement de code
n'en decoule — la confirmation avait ete exigee avant de toucher au
gabarit, et elle a servi.

### La graine domine tout

Meme consigne, memes reglages, seule la graine change.

| graine | vitesse | dispersion |
|---|---|---|
| 1234 | 0,107 | **0,396** |
| 42 | 0,099 | 0,474 |
| 777 | 0,108 | **0,746** |

A vitesse quasi identique, un facteur **1,88**. Mis en regard de tout ce
qui a ete mesure :

| levier | effet sur la dispersion |
|---|---|
| quantification Q5 -> Q8 | x1,02 |
| echantillonneur | x1,00 |
| formules de coherence | x1,01 |
| etapes 8 -> 24 | x1,26, en pire |
| **graine** | **x1,88** |

La graine pese plus que tous les reglages reunis. C'est la seule action
utile trouvee, et la moins chere : un plan qui scintille se relance avec
une autre graine. Le bouton de tirage ajoute en HOS-199 prend ici sa vraie
justification.

C'est aussi l'explication retrospective des faux positifs de cette
campagne : plusieurs reglages ont semble marcher puis n'ont pas tenu a la
reproduction. Ils mesuraient du bruit de graine. **Toute mesure future sur
la coherence temporelle doit porter sur plusieurs graines**, sans quoi
elle ne mesure rien.

### Etat des six hypotheses du rapport initial

| hypothese | verdict |
|---|---|
| instabilite intrinseque de LTX-2.5 | **confirmee** — 2,4 fois la dispersion d'une video parfaite |
| quantification Q5_K_M | **ecartee** — Q8_0 identique |
| nombre d'etapes | **ecartee** — au-dela de huit, c'est pire |
| VAE au decodage | mesure faite sur images brutes : le defaut y est deja |
| type de mouvement | **non tranchee** — l'instrument ne compare pas des vitesses si differentes |
| encodage final | **ecartee** — present dans les PNG bruts |

Aucun code n'a change. Le resultat de ce tour est une mesure, et il dit
que le defaut est dans le modele.

## HOS-202 - Le defaut mesure sans encodage, deux formats qui mentaient, et 390 Mo de trop (2026-08-28)

Suite du diagnostic, avec le compte rendu de l'utilisateur comme point de
depart : textures qui changent d'une image a l'autre, feuillage qui se
redispose, zones lumineuses qui scintillent, decor qui « respire » —
surtout sur les plans presque statiques.

### Deux limites de l'instrument, trouvees avant de publier des chiffres

**L'indicateur est sensible a l'encodeur.** Le meme rendu mesure 0,621 sur
ses images brutes et 0,902 sur son mp4, alors que ce mp4 et un `libx264`
CRF 23 partant des memes images ont une erreur d'encodage **identique**
(2,98 contre 2,97 niveaux, memes tailles de fichier). L'ecart ne vient
donc pas de la qualite d'encodage. Il reste **non explique**, et il
invalidait le plancher de reference de HOS-201, mesure sur un fichier
libx264 quand les rendus venaient de ComfyUI.

**Le rapport dispersion/vitesse depend de la geometrie du mouvement.** Sur
des temoins parfaits a vitesse croissante, le rapport *monte* (3,4 → 10,1
→ 12,4) au lieu de rester constant : les bords d'un zoom se deplacent plus
que le centre. Ce rapport ne mesure donc rien des que les vitesses
different.

### La mesure refaite, sans aucun encodage

`SaveImage` ajoute au meme graphe donne les images du decodeur avant tout
h264.

| source | vitesse | dispersion |
|---|---|---|
| temoin : image figee x49 | 0,000 | **0,000** |
| temoin : travelling parfait | 0,076 | 0,257 |
| LTX-2.5 : plan statique | 0,109 | **0,621** |

Le temoin fige rend exactement zero : l'instrument n'a pas de biais. A
mouvement comparable, le modele produit **2,4 fois** la dispersion d'une
video geometriquement parfaite, et son incoherence vaut pres de six fois
son propre mouvement. C'est ce rapport qui explique que le defaut saute
aux yeux sur un plan statique.

### Sept reglages, aucun ne corrige

Meme consigne, meme graine, meme encodeur — donc comparables entre eux.

- Etapes 8 / 16 / 24 : 0,552 / 0,567 / **0,695**. Au-dela de huit, c'est
  pire. La note « un modele distille ne gagne rien au-dela de huit » vaut
  donc aussi pour la coherence, et dans le mauvais sens.
- `res_multistep` : -12 % en absolu, mais avec moins de mouvement — non
  concluant. A noter : le depot documentait `res_multistep` alors que le
  code envoyait `euler`, ecart trouve en verifiant.
- `uni_pc`, CFG 2,0, STG a l'echelle 2,0 sur les blocs 14/19, 720p :
  aucun gain.

Le plan de parallaxe a trente-quatre fois plus de mouvement que le plan
statique : les deux ne sont pas comparables avec cet instrument.
L'hypothese « un mouvement franc masque le defaut » reste **plausible et
non tranchee**.

### Deux formats qui n'ont jamais existe

`ffprobe` sur les fichiers reels :

| declare | reellement produit |
|---|---|
| `paysage` 768 x 432 | **768 x 416** |
| `paysage_large` 1280 x 720 | **1280 x 704** |

LTX ramene la hauteur au multiple de 32 inferieur, en silence. Ces tailles
faussaient le calcul de cout et le garde-fou du depart sur image, lequel
refusait `paysage` pour une hauteur de 432 qui n'existait pas. Les formats
declarent desormais leur taille reelle, et les variantes « suite » de
HOS-200 disparaissent : `paysage_large_suite` valait 1280 x 704,
c'est-a-dire ce que `paysage_large` rendait deja.

### 390 Mo commites par erreur

Un `git add -A` pendant la campagne de HOS-201 a commite **881 images**
d'analyse — les frames extraites par les scripts de mesure — soit environ
390 Mo. Elles sont retirees du suivi et `.gitignore` couvre desormais ces
motifs.

Retirer ne suffit pas a alleger le depot : les objets restent dans
l'historique. Les en sortir demanderait une reecriture d'historique et un
`push --force`, operation destructive qui n'est pas engagee sans decision
explicite.

### Le mur materiel

Lightricks documente que le scintillement se concentre sur les zones a
haute frequence — cheveux, tissus, **feuillage** — ce qui fait du plan de
test de ce projet, une foret dans la brume, a peu pres le pire sujet
possible. La recommandation officielle est le modele **Dev** avec
echantillonnage multi-etages ; il fait 22 milliards de parametres, 21,5 Go
en int8, sur une carte de 16. L'agrandisseur de latent du pipeline
multi-etages (1 Go) est dans un depot **ferme**, qui exige une
authentification et l'acceptation d'une licence.

Backend 2192 passed, 2 skipped. Frontend tsc propre.

## HOS-201 - La « micro-coupure » : bon phenomene, mauvaise mesure (2026-08-28)

L'utilisateur a corrige sa description apres avoir regarde les fichiers,
et cette correction invalide le diagnostic de HOS-200. Il ne decrit pas un
defaut de RYTHME mais de CONTENU : « comme si la video etait creee en
ajoutant des petits morceaux de 0,5 s », avec « de legeres variations sur
la disposition des plantes » et l'impression que le plan recule.

### Pourquoi la mesure precedente ne pouvait pas le voir

L'ecart de luminance entre images successives mesure **l'ampleur** d'un
changement, jamais son **sens**. Il ne peut ni voir un retour en arriere
ni un objet qui se redispose. La periode 8 qu'il revelait est reelle, mais
elle decrit autre chose que ce qui gene a l'oeil.

Mesure appropriee : correlation de phase au sous-pixel, par region.

### Le temoin, sans lequel les chiffres ne veulent rien dire

Un travelling avant mathematiquement parfait, fabrique par `zoompan` a
partir d'une seule image reelle du meme plan — meme resolution, meme
cadence, meme codec. Il donne le plancher de bruit de l'instrument.

| variante | dispersion locale | exces reel |
|---|---|---|
| temoin, zoom parfait | 0,302 px | plancher |
| 8 etapes | 0,552 px | **+0,25** |
| 16 etapes | 0,567 px | +0,27 |
| 24 etapes | 0,695 px | +0,39 |
| 8 etapes + STG 1.0 | 0,561 px | +0,26 |

Le mouvement global est **monotone** : un seul contre-sens sur 48. La
camera ne recule jamais. Mais l'incoherence locale vaut 0,25 px par image
contre 0,172 px de deplacement reel de la camera — le desordre domine le
mouvement d'un facteur 1,5. C'est ce rapport qui explique l'impression de
recul et la redisposition des plantes.

Deux conclusions de HOS-200 tombent : ce n'est **ni** le decoupage
temporel du decodeur, **ni** les huit images par latent. Aucune
periodicite ne ressort au-dessus du seuil de bruit.

### Trois leviers essayes, aucun ne corrige

Les etapes ne sont pas le levier, et au-dela de huit elles **nuisent** :
0,552 -> 0,567 -> 0,695. La note « un modele distille ne gagne rien
au-dela de huit etapes » valait pour la qualite d'image ; elle vaut aussi
pour la coherence, et dans le mauvais sens.

`LTXVSpatioTemporalGuidance` a l'echelle 1.0 ne change rien. Des echelles
plus fortes restent a mesurer.

L'interpolation ne s'y attaque pas : elle lisse la restitution, pas la
generation.

Restent non mesures et non ecartes : resolution plus haute, echelle de STG
plus forte, quantification superieure.

Aucun code n'a change : ce tour est une mesure, et son resultat est qu'il
n'y a rien a corriger dans ce depot — le defaut est dans le modele.

## HOS-200 - Les saccades mesurees, et l'enchainement de plans (2026-08-28)

Trois questions posees sur le Studio, dont une - « les saccades viennent
du modele ou d'un reglage ? » - qui ne se tranche que par la mesure.

### La saccade vient du modele, et l'hypothese de depart etait fausse

Ce que ce n'est pas : le conteneur est sain (24/1 constant, h264, nombre
d'images conforme), verifie par ffprobe sur un fichier reellement produit.

Mesure de l'ecart de luminance entre images successives, sur trois plans -
deux formats, trois contenus. L'autocorrelation culmine a **8** dans les
trois cas (+0,52 / +0,30 / +0,30), toujours le decalage le plus eleve,
alors que r(12) change de signe et ne decrit rien. Seuil de bruit ≈0,14
pour n≈50 : les valeurs sont 2 a 4 fois au-dessus. Dans chaque groupe de
huit images le mouvement est fort au debut et faible a la fin - trois
a-coups par seconde a 24 im/s.

Ce 8 est le taux de compression temporelle du VAE de LTX. Deux faits
independants le corroborent : la contrainte `8k + 1` sur le nombre
d'images, et le « Must be 8*n + 1 frames » de la documentation du noeud
`LTXVAddGuide`. Trois indices, une cause.

**L'hypothese de depart etait le decoupage temporel du decodeur**
(`temporal_size` 16, recouvrement 4, donc un pas de 12). La mesure l'a
infirmee : c'est precisement a 12 que le signal est le plus anti-correle.
Elle a ete ecartee au lieu d'etre corrigee apres coup.

### Le lissage : integre au rendu, et honnete sur ce qu'il ne fait pas

Trois modeles installes depuis `Comfy-Org/frame_interpolation`, le depot
que le gabarit officiel livre avec ComfyUI designe. Banc de comparaison
sans diffusion (la video deja rendue est rechargee), donc 6 a 26 s par
essai au lieu de minutes.

| modele | variation du pas | secousse image-a-image |
|---|---|---|
| rife_v4.26 | +26 % / +18 % | +55 % / +29 % |
| rife_v4.26_heavy | +32 % / +15 % | +58 % / +18 % |
| film_net_fp16 | +14 % / +8 % | **-18 % / -14 %** |

**Aucun ne supprime l'irregularite de fond** - attendu, puisque
l'interpolation ne peut pas inventer ce qui s'est passe entre deux groupes
de huit. FILM est le seul a reduire la secousse image-a-image ; RIFE
l'aggrave. FILM est donc le choix propose, et l'ecran ecrit ce que le
lissage ne fait pas plutot que de le laisser croire.

L'interpolation est faite **pendant** le rendu, pas en seconde passe, et
la cadence de sortie est multipliee d'autant pour que la duree ne bouge
pas - sans ce doublement, le plan deviendrait un ralenti.

### Enchainer deux plans en gardant decor et personnages

`LTXVImgToVideo` fait partir un plan d'une image au lieu du bruit ; donner
au suivant la derniere image du precedent conserve la scene.
`POST /studio/last-frame` extrait cette image dans le dossier d'entree de
ComfyUI, seule adresse que `LoadImage` sait lire.

Une contrainte que rien n'annoncait : ce noeud decoupe le latent en blocs
de 2x2 et exige des cotes **multiples de 32**. Ni 432 ni 720 ne le sont.
Constate en le lancant : le plan est accepte, occupe la carte, et echoue
**sept minutes plus tard** sur un `einops.EinopsError` illisible. Un
garde-fou refuse desormais en une milliseconde, en nommant les formats
compatibles. Deux formats compatibles ont ete ajoutes - `paysage_suite`
(768 x 448) et `paysage_large_suite` (1280 x 704, exactement le compte de
pixels du portrait deja chronometre).

Un test empeche un defaut trouve en ecrivant le code : avec le son,
`LTXVConcatAVLatent` etait cable en dur sur le latent vide. Le plan
repartait donc du bruit des qu'on demandait le son, en perdant sa
continuite, sans aucune erreur.

### La graine, et un piege corrige

La valeur par defaut etait `0` - une graine fixe, pas un tirage. Deux
lancements sans y toucher rendaient exactement le meme fichier. Un bouton
de tirage a ete ajoute, et l'aide corrigee : elle disait « 0 pour laisser
courir », ce qui etait faux.

### Verifications

Les deux nouveautes sont validees par des **rendus reels**, pas par
construction de graphe : un plan I2V + lissage en 512 x 320 rend 49 images
a 48 im/s pour 1,02 s - exactement le calcul. Le premier essai, lui, a
echoue, et c'est ce qui a fait trouver la contrainte des multiples de 32 :
`success: true` de la soumission ne valait que « accepte ».

## HOS-199 - La duree d'un plan, et trois reglages deja ecrits mais jamais offerts (2026-08-28)

« Je ne peux pas choisir la duree de la video. » C'etait vrai en pratique
et faux en theorie : le formulaire offrait un champ **Images**, qui *est*
la duree du plan, sans que rien ne le dise. Personne ne cherche « 97 »
quand il veut quatre secondes.

Le champ est desormais une duree en secondes. La conversion vit dans
`gabarits.py` avec les autres mesures, parce que LTX n'accepte que des
longueurs `8k + 1` — 49 images pour 2 s, 97 pour 4 s, les deux longueurs
effectivement rendues et chronometrees. A 24 im/s la coincidence est
exacte : 24 etant multiple de 8, toute duree entiere tombe pile sur une
longueur valide. L'ecran affiche la duree **reellement rendue** (2,04 s
pour 2 s demandees, l'image supplementaire de `8k+1`) plutot que d'arrondir
en silence.

### Trois parametres implementes depuis HOS-194, jamais offerts

Un releve de la signature des gabarits contre ce que le catalogue annonce
en a trouve trois : `negatif` (le prompt negatif), `prefixe` (le nom du
fichier de sortie) et `cadence`. Tous trois codes, testes, et invisibles
dans l'ecran — donc inaccessibles autrement qu'en passant par l'agent. Ils
sont maintenant dans le formulaire, pour les trois gabarits concernes.

Un test garde le catalogue et les fabriques d'accord : tout parametre
annonce a l'ecran doit etre accepte par `composer`. Verifie rouge sur un
parametre fantome avant d'etre garde.

### Une estimation fausse de +260 %, trouvee en la rendant visible

L'ecran annoncait « ≈ 5 min de calcul par seconde de video finie ». Cette
regle vient du **seul rendu vertical** dont elle est tiree et ne retient
que la duree, en ignorant la surface. Confrontee aux deux autres rendus du
tableau de `docs/studio-center.md`, elle surestime de **+144 %** en
768 × 432 (612 s annoncees pour 251 mesurees) et de **+260 %** en 512 × 288
(612 s pour 170).

L'erreur allait dans le sens le plus couteux a l'usage : elle decourageait
un essai bon marche en l'annoncant a vingt minutes. Le temps suit
`pixels x images`, pas la duree seule. Ajustement par moindres carres sur
les trois rendus reels, ecart maximal 11 % :

```
t ≈ 56 s + 13,27 s par million de pixels-images
```

Constantes dans `gabarits.py`, servies par `/studio/templates` plutot que
recopiees dans le frontend. L'ecran dit desormais « extrapole de trois
rendus mesures, a ±11 % » : trois points ne font pas une loi.

Verifie a l'ecran : 4 s en 704 × 1280 annonce 20 min, mesure 20,3 ; 2 s en
768 × 432 annonce 5 min, mesure 4,2 — contre 10 min annoncees avant.

`docs/studio-center.md` est **amende explicitement** a l'endroit ou la
regle etait etablie, sans reecrire la mesure d'origine : « cinq minutes par
seconde » reste juste pour le vertical, et c'est a ce titre que
`file_de_nuit.py` continue de s'en servir pour justifier l'atelier de nuit.

## HOS-198 - La bascule d'onglet, corrigee pour de bon (2026-08-27)

Le bug du Studio Center persistait apres HOS-196 : depuis un sous-onglet
(Voix, Nuit ou Graphe), changer d'onglet principal ne changeait rien a
l'ecran. Reproduit sur l'application en marche plutot que raisonne.

### Ce que HOS-196 avait rate, et pourquoi

Le correctif precedent retirait `exit` du conteneur de vue, en pariant que
sans variante de sortie a jouer, `AnimatePresence` demonterait l'ancienne
vue immediatement. **Il ne le fait pas** — framer-motion 11.18.2 sous
React 19 ne relache alors jamais l'enfant sortant. Mesure dans le DOM :
chaque navigation ajoutait un `.center-enter` de plus, tous a opacite 1,
aucun retire. Studio, puis Assistant, puis Mission Center, empiles dans le
flux. Le premier gardait le haut de la page et les suivants etaient
pousses 1 140 px plus bas, hors ecran — d'ou « ca ne fonctionne pas »,
alors que `activeView` et `aria-current` changeaient correctement. Le
correctif de HOS-196 avait donc remplace un blocage par une fuite.

### La correction

`AnimatePresence` n'avait plus de travail : la sortie est retiree pour de
bonnes raisons (une iframe ignore le fondu de ses ancetres et resterait
visible par-dessus la vue suivante), et l'entree est une animation CSS que
le remontage declenche seul. Ne restait que sa comptabilite de presence,
laquelle fuyait. Un `key` sur un element ordinaire suffit : React demonte
de facon deterministe, sans dependre d'une frame de composition, et
l'iframe s'en va avec la vue.

Verifie dans un vrai navigateur, cette fois avec un pane qui affiche :
32 combinaisons (quatre sous-onglets du Studio x huit onglets principaux),
zero echec, toujours exactement un Center en DOM. Le cas dur — quitter
Studio -> Graphe avec l'iframe ComfyUI vivante — passe de 1 iframe a 0.
Rafale de 19 onglets sans pause : maximum 1 Center a tout instant.

### Un test qui ne gardait rien, retire avant d'etre commite

Le premier garde-fou ecrit pour cet incident montait le shell et comptait
les Centers apres bascule. Verifie comme doit l'etre tout garde-fou — la
faute reintroduite exprès — il est reste **vert**. Sous JSDOM il n'y a pas
de vraies frames de composition, framer-motion y relache l'enfant sortant
immediatement, et le defaut ne peut pas s'y produire. Le garder aurait ete
pire que rien : il aurait affirme garder une regression qu'il laisse
passer.

Ce qui reste est ce qui *peut* se garder automatiquement — que la
construction fautive n'a pas ete remise — et il a ete verifie rouge sur la
faute reintroduite avant d'etre garde. Meme nature que
`test_hermes_agent_is_the_brain.py` : il ne prouve pas que la navigation
marche, il empeche le retour de la cause connue.

## HOS-197 - Ce que la maquette avait retenu, et que le code n'avait pas pris (2026-08-27)

L'utilisateur signale que le design cree en amont n'a pas ete mis en place,
« seul l'operateur ». Verifie avant d'agir, et le constat est l'inverse :
l'harmonisation sodium est complete (globals.css porte la palette, les 22
Centers en heritent par les alias), la piece ambiante existe (halo sodium,
contre-lumiere glacier, grille technique, grain, vignette), et l'operateur
va bien au-dela de la maquette — quinze postures pilotees par de vrais
evenements backend contre treize illustratives. L'ecart reel etait ailleurs,
et il tenait en quatre points.

### Le halo suit le curseur

La piece etait la, mais figee. La direction retenue
(`.design/cockpit/Main.dc.html`) en fait une source de lumiere mobile : le
halo sodium suit la souris, la contre-lumiere glacier se reflete en miroir a
travers le centre, et la grille ne se revele que la ou la lumiere tombe.
`components/room-halo.tsx` ecrit `--room-mx`/`--room-my` sur la racine — la
meme technique que `rail.tsx` pour `--rail-w`, et pour la meme raison :
plusieurs regles CSS doivent suivre une valeur sans qu'aucune ne devienne la
source de verite d'une autre. Ecriture directe de la variable, une fois par
frame au plus, plutot qu'un `setState` par mouvement de souris. Les deux
variables ont des valeurs de repli reelles dans le CSS, donc la piece se lit
correctement avant que le moindre JS ait tourne.

### Le badge d'etat dans la barre d'instruments

« Une couleur, un etat, partout ou il est lisible ». La figure de l'operateur
ne parait que sur douze Centers sur vingt-sept — elle demande de la place et
serait du bruit sur un ecran de reference. Le badge, lui, tient dans la barre
et parait partout : c'est justement sur ces ecrans-la qu'on veut encore
savoir, d'un coup d'oeil, qu'une mission travaille pendant qu'on regarde
ailleurs.

### La sante se retire au bord — Direction C, mesuree avant d'etre adoptee

Direction C affirmait que l'echelle vert/ambre/rouge remplissait les valeurs
et que, tout allant bien presque toujours, l'ecran etait vert. Verifie sur
l'application en marche plutot que sur le compte de jetons du depot :
**quarante et un elements verts contre treize sodium** sur le Dashboard,
alors que le sodium est l'accent cense porter « le systeme qui parle ».

La cause n'etait pas diffuse : `ProgressBar`, primitive partagee, remplissait
ses vingt-quatre segments de la couleur de sante. Desormais le corps de la
barre est sodium et seul le segment de tete porte la teinte de sante, halo
compris. Mesure apres : 41 -> 29 elements verts, et une barre a 49 % se lit
« onze segments sodium, un vert en tete ».

Une exception, et elle compte : le recensement des 35 sous-systemes du
Dashboard garde ses cellules colorees par la sante, parce que la sante **est**
la valeur qu'il montre — une cellule rouge dans une rangee verte est tout son
propos. Direction C vise les mesures dont le chiffre est la valeur, pas les
recensements de sante. La distinction est ecrite dans le contrat du systeme
de design plutot que laissee a la relecture suivante.

### Le bouton se remplit par la gauche, et s'enfonce sans retrecir

La planche de pieces (`.design/cockpit/Composants.dc.html`) est explicite :
« un bouton d'instrument s'enfonce, il ne retrecit pas ». Le bouton faisait
`active:scale-[0.985]` — exactement ce qu'elle recuse. Retire. Et le
remplissage entre par la gauche, dans le sens de lecture, au lieu de monter
en opacite partout a la fois (`.btn-fill` dans globals.css, une seule
mecanique pour les quatre variantes).

Verifie : tsc --noEmit propre, vitest 110/110, et le CSS mesure sur
l'application en marche (le halo suit bien, la contre-lumiere se reflete a
30%/80% quand le curseur est a 70%/20%, le masque de grille suit, le badge
porte la teinte de l'etat a 34 % de bordure et 8 % de fond, `--btn-fill` vaut
sodium avec un `::before` a `scaleX(0)`). Comme au tour precedent, aucune
capture d'ecran : le pane de test ne composite pas les frames.

## HOS-196 - Trois pannes d'interface qui n'en faisaient qu'une, et la voix Michael sur ecran (2026-08-27)

Trois bugs remontes par l'utilisateur sur l'interface : impossible de
scroller dans la plupart des Centers, la navigation qui se bloque un clic
en retard, ComfyUI (onglet Studio -> Graphe) qui reste affiche par-dessus
l'onglet suivant quand on change d'onglet. Racine commune dans
`cockpit-shell.tsx` : le conteneur de vue bornait sa hauteur
(`h-full overflow-hidden`) et `AnimatePresence` attendait la fin d'une
animation de sortie (`mode="wait"`) qui ne garantit jamais sa propre fin.

- **Scroll.** Dix-sept Centers sur vingt-sept n'ont pas de defilement
  interne et dependent entierement du debordement vers le conteneur
  parent. Mesure sur Governance a 500px de fenetre : une boite de 370px
  pour 415px de contenu reel, les 45px manquants recuperables nulle part.
  `h-full overflow-hidden` remplace par `min-h-full` pour tout Center hors
  Assistant, qui garde son comportement borne (seul Center a gerer son
  propre defilement interne).

- **Navigation bloquee.** `mode="wait"` bloque le montage de la vue
  suivante tant que la sortie de la precedente n'est pas confirmee
  terminee — une confirmation qui depend d'une frame de composition
  pouvant manquer (onglet en arriere-plan, GPU charge par un rendu
  parallele). Constate : `aria-current` changeait, `<main>` restait fige
  sur l'ancienne vue, chaque clic suivant s'empilait sans jamais aboutir.
  Retire.

- **Iframe persistante.** Les iframes ignorent le fondu CSS de leur
  conteneur et restent composees a pleine visibilite pendant la sortie —
  constate sur Studio -> Graphe, deux `.center-enter` en DOM
  simultanement (l'ancien Studio avec ComfyUI vivant, et la vue cible).
  `exit` retire du `motion.div` : sans variante de sortie a jouer,
  `AnimatePresence` demonte l'ancienne vue immediatement au lieu
  d'attendre une animation qui peut ne jamais se resoudre. Meme correctif
  applique a `web-preview.tsx`, seul autre site avec iframe (panneau
  plein ecran, ou le risque etait pire — bloquer l'application entiere).

Verifie : `tsc --noEmit` propre, vitest 110/110, balayage des 19 Centers
sans desynchronisation ni nouvelle erreur console. Aucune confirmation
visuelle par capture d'ecran n'a ete possible pendant cette revue : le
pane de navigateur de la session ne compositait pas les frames, confirme
par un timeout de 30s sur un `requestAnimationFrame` direct — verification
faite entierement par inspection DOM/etat.

### La voix Michael (HOS-195), sur ecran plutot que par le chat seul

`studio_narrate` n'existait que comme outil MCP — narrer une replique
exigeait de le decrire a l'agent en conversation. Nouvel onglet « Voix »
dans le Studio Center (`narration.tsx`), une route REST miroir de l'outil
(`POST /studio/narrate`, `backend/studio/routes.py`) qui appelle la meme
`narration.synthetiser` avec le meme arbitrage de carte — pas une seconde
implementation. Un test de route a trouve un vrai defaut avant qu'il ne
morde : une replique composee uniquement d'espaces passait le controle de
vacuite (`t` au lieu de `t.strip()`) et aurait lance une synthese sur du
texte blanc.

## HOS-195 - La voix Michael, branchee dans le pipeline (2026-08-27)

Chatterbox, clone depuis un echantillon fourni par l'utilisateur — sa
propre voix, en performance de personnage nomme « Michael », confirme
explicitement avant tout clonage. Trois references soumises et mesurees
avant de retenir la troisieme : la premiere (44,6 s, -30,7 dB) donnait un
clone a quatre trames voisees sur toute la phrase, la voix survivait a
peine. Reduite a seize secondes de parole continue et debruitee
**doucement** — le reglage fort gagnait 21 dB de silence mais faisait
chuter la confiance de transcription de -0.188 a -0.351, la voix decrochait
avec le bruit — le clone est monte a 126 trames. La troisieme etait deja
propre et n'a demande qu'une normalisation.

Verifie, pas suppose : la hauteur mediane du clone se deplace
systematiquement vers celle de la reference, de 157 Hz (voix par defaut du
modele) a 82-102 Hz selon les reglages, contre 91,2 Hz mesures sur
« Michael ».

### Un environnement separe, pour la meme raison que Hermes Agent

`chatterbox-tts` epingle `torch==2.6.0`. L'installer dans `.venv` ou dans
l'interprete embarque de ComfyUI aurait remplace le torch ROCm 2.13 par
une build CPU et casse tous les rendus. Une venv enfant herite du torch
de ComfyUI par un `.pth`, Chatterbox y est installe `--no-deps`. Verifie
apres coup : ComfyUI repond, en ROCm, GPU actif — l'isolation a tenu, deux
fois (a l'installation, puis a chaque appel reel depuis).

### Le pipeline

`backend/studio/narration.py` : un seul chargement pour plusieurs
repliques (9 a 27 s mesures par chargement, une narration en compte
plusieurs), et la carte s'arbitre comme pour un rendu — 4,38 Gio de pic
mesures, pas gratuit comme Piper. `_chatterbox_worker.py` est le seul
fichier qui tourne dans l'environnement Chatterbox ; il ne decide de
rien, tout arrive en parametre.

`studio_narrate` (MCP) rejoint la liste blanche de l'agent et son cache de
schemas a ete vide — les deux verrous silencieux qu'HOS-192 avait deja
trouves pour la delegation, retrouves une deuxieme fois sur un nouvel
outil.

### Un defaut latent corrige avant qu'il morde

Le sous-processus decodait stderr en UTF-8 strict. Un avertissement
HuggingFace accentue, imprime dans l'encodage systeme Windows, a fait
planter un thread interne pendant la verification reelle — sans faire
echouer l'appel cette fois, mais rien ne garantissait la prochaine.
Corrige avec `errors="replace"`, la meme convention deja posee pour
Hermes Agent dans ce depot pour la meme cause.

### Un redemarrage systeme, pas un bug

Pendant la verification reelle, ComfyUI, le backend et le Cockpit sont
tombes d'un coup. Diagnostic avant conclusion : `LastBootUpTime` et
l'evenement Windows 1074 confirment un **redemarrage systeme** a 21:05:30
— une mise a jour planifiee, sans rapport avec la synthese. Les trois
services relances, ComfyUI verifie sur ses bons drapeaux
(`--use-quad-cross-attention`, pas de CORS desarme).

### Verified

Synthese reelle de bout en bout : deux repliques, fichiers WAV sur disque,
16,2 s de chargement, 5,08-5,44 s de synthese chacune. Backend **2 161
passes, 2 ignores** (11 tests nouveaux pour la narration). Aucun binaire
audio n'entre dans le depot — la reference vit sous
`C:\AI\Models\Voices\michael\`, hors de git.

---

## HOS-194 - L'Atelier produit, et ComfyUI s'encastre sans rien desarmer (2026-08-27)

Trois manques constates en regardant l'ecran plutot qu'en le decrivant :
l'onglet Atelier ne lancait rien, SDXL n'y apparaissait pas, et l'iframe
de ComfyUI etait blanche.

### Un formulaire, et la frontiere qu'il ne franchit pas

`backend/studio/gabarits.py` compose trois graphes figes — plan video,
image SDXL, image LTX — a partir de parametres **explicites**. Rien n'est
infere de la consigne.

La regle qui prime sur tout interdit qu'une seconde boucle decide a la
place de l'agent, et j'avais ecrit qu'« un service qui construit le bon
workflow » serait exactement cela. La distinction tient en un mot :
**choisir**. Decider quel pipeline convient a un objectif, c'est
raisonner ; remplir un gabarit avec des parametres qu'on vous donne, c'est
un formulaire. C'est d'ailleurs ce que le cahier des charges prevoyait :
« le graphe vient de l'appelant [...] ou du Studio Center par un gabarit ».

`test_studio_gabarits.py` garde cette frontiere : le jour ou quelqu'un
ajoutera « si la consigne parle de mouvement, mettre plus d'images »,
c'est la que ca cassera.

### Le defaut qu'il a fallu regarder pour trouver

Le premier rendu lance depuis le formulaire est sorti **tuile et
deforme**. Le graphe etait correct, ComfyUI a rendu 200, le fichier
existait. Rien ne signalait quoi que ce soit — il fallait ouvrir l'image.

La cause : une liste de formats **commune aux deux moteurs**. Le rendu
SDXL est parti en 768x432, valide pour LTX et ruineux pour SDXL, qui est
entraine autour du megapixel. Les formats sont desormais separes, le
formulaire retombe sur un format valide quand on change de moteur, et deux
tests gardent la separation.

### L'iframe : un 403 selectif

`origin_only_middleware` (server.py:159) compare `Host` et `Origin` et
renvoie 403 quand ils different — protection contre un site tiers qui
ferait executer un workflow depuis le navigateur de l'utilisateur.

Le 403 etait **selectif**, ce qui l'a rendu long a voir : les feuilles de
style passaient, le navigateur n'envoyant pas d'`Origin` pour elles ; les
scripts `type="module"`, requetes CORS, echouaient. La page se chargeait,
affichait son ecran de demarrage, et n'en sortait jamais.

Ma premiere explication — « ComfyUI ne pose ni X-Frame-Options ni
frame-ancestors, donc l'encastrement fonctionne » — etait une verification
d'en-tetes prise pour un chargement de page. Exacte, et sans rapport.

**Ecarte : `--enable-cors-header`.** Une ligne, mais il **remplace** le
garde au lieu de le restreindre : verifie, une origine quelconque obtenait
alors 200. Desarmer la protection pour tout le monde afin d'en autoriser
une seule.

**Retenu : un proxy same-origin.** `next.config.ts` reecrit `/comfy/*`
cote serveur, `src/middleware.ts` retire `Origin` et `Sec-Fetch-Site`
avant de transmettre. La requete arrive comme un `curl`, sans rien a
comparer — cas que le garde laisse passer par construction. Rien n'est
desactive.

Trois details decidaient : `skipTrailingSlashRedirect`, sans quoi Next
redirige `/comfy/` et les chemins relatifs se resolvent contre `/` ; les
WebSockets, verifiees a **101 Switching Protocols** a travers la
reecriture, sans quoi l'interface se chargerait sans jamais afficher de
progression ; et un middleware limite a `/comfy/*`, l'`Origin` du Cockpit
lui-meme etant legitime.

### Rangement

`ckpt_name` manquait dans `/studio/models` : SDXL, installe et mesure la
veille, n'apparaissait nulle part. Et le mapping `checkpoints: vae/` de
HOS-192 faisait passer les deux VAE de LTX pour des checkpoints — le VAE
audio a desormais son propre dossier.

`hermes-ltx-cockpit.bat`, ecrit pour tester la piste CORS, est supprime :
le proxy le rend inutile et il desarmait un garde.

### Verified

Rendu lance **depuis le bouton** de l'ecran : soumis, carte reservee,
`image_00002_.png` sur disque, image nette et conforme a la consigne.
ComfyUI dans le cadre : 360 noeuds, 2 canvas, plus d'ecran de demarrage —
avec son garde intact.

Backend 2 150 passes, frontend 110 passes, tsc propre.

---

## HOS-193 - split mesure, et une mesure qui ne colle pas (2026-08-27)

`split` avait ete ecarte par un calcul qui additionnait le poids du
fichier a la memoire d'attention, comme si les poids residaient sur la
carte. Ils n'y resident pas. Le calcul refait donnait « ca tiendrait » —
une estimation, remplacee ici par une mesure.

Meme graphe, meme graine, 768x432 sur 49 images, les deux serveurs
demarres a froid :

    sub_quad   248 s   pic 14,42 Gio
    split      239 s   pic 14,42 Gio

**Neuf secondes, 3,6 %.** Pas les 40 % annonces.

L'ecart entre 40 % et 3,6 % est le resultat le plus instructif : les 40 %
venaient d'un banc qui chronometrait **l'attention seule**. Dans un rendu
reel elle est une petite part du travail — le reste, ce sont trente-six
gigaoctets de modele relus depuis le disque, le decodage du VAE, le
planificateur. Un micro-banc ne predit pas un pipeline.

### Aucune degradation, et c'est verifie

Les deux implementations calculent la meme attention et ne different que
par le decoupage. `sub_quad` implemente Rabe & Staats, un softmax decoupe
**exact** ; les deux chemins montent en float32 sous la meme condition —
lu dans le code, pas suppose. Restait l'associativite des flottants, qui
aurait pu deriver sur huit pas de debruitage.

    instant    ecart max   ecart moyen   PSNR        pixels touches
    15 %       0           0,000         identique   0,00 %
    50 %       0           0,000         identique   0,00 %
    85 %       0           0,000         identique   0,00 %

Les fichiers different de **deux octets** — un horodatage de conteneur —
et pas d'un pixel. Verifie sur deux paires independantes.

### Garde sub_quad quand meme

Le gain est de 3,6 %, et `split` prend bien plus de memoire d'attention
quand les jetons se multiplient. Le format 704x1280 sur 97 images — celui
des shorts — n'a pas ete teste avec lui, et c'est precisement la qu'il
pourrait deborder. `hermes-ltx-split.bat` garde la variante a cote.

### Une mesure incoherente, laissee ouverte

Ces rendus pesent 14,42 Gio au pic. Les trois plans de la nuit du **meme
jour**, meme resolution, meme modele, meme nombre d'images, avaient donne
7,61 Gio — trois fois exactement le meme chiffre.

Un rapport de deux entre deux mesures reproductibles de la meme chose.

J'ai verifie que ce n'est pas un pic manque : releve a la seconde, la
valeur haute est un plateau qui dure des minutes. Les conditions different
— la nuit passait par `carte_reservee`, qui venait de decharger Ollama —
mais je ne connais pas le mecanisme. L'hypothese la plus plausible est que
`Dedicated Usage` compte ce que l'allocateur PyTorch *reserve* et pas
seulement ce qu'il *utilise*, et qu'il en reserve d'autant plus que la
carte est libre. Non verifie, donc ecrit comme tel.

Consequence : `BESOIN_RENDU_OCTETS` vaut 9 Gio, cale sur la plus **basse**
des deux. Si c'est la haute qui decrit le besoin, la reservation est trop
courte — a trancher avant de faire tourner une nuit pendant qu'une mission
travaille.

### Verified

Quatre rendus sur disque sous `E:\YouTube\Generations\attention`,
comparaison pixel par numpy sur trois instants. Lanceur de production
restaure sur `--use-quad-cross-attention` et verifie par `/system_stats`.

---

## HOS-192 - Ce qui etait deja la, et que personne ne voyait (2026-08-27)

Trois taches, et le meme motif dans les trois : ce qu'il fallait etait
deja sur le disque, rendu invisible par une ligne de configuration.

### La delegation ne marchait pas pour une raison qui n'etait pas dans ce depot

Le but declare du projet YouTube etait que Hermes Agent conduise la
generation. Neuf outils MCP etaient enregistres et testes. L'agent n'en
voyait aucun.

`mcp_servers.hermes-ollama.tools.include` est une liste **blanche** de
seize noms. Enregistrer un outil cote serveur ne le donne pas a l'agent :
il faut l'y nommer. Et `cache/mcp_schema_cache.json` gardait les seize
anciens, ce qui aurait annule la correction sans un vidage.

Deux listes blanches silencieuses. C'est la troisieme fois dans ce projet
— l'EventHub avait avale trente-cinq topics de la meme facon.

Une fois levees : douze appels d'outils en 54 s, et la phrase qui compte,

    « none are in a successful "kept" state — they are all in the
      "indetermine" state »

La distinction entre « le fichier existe » et « le fichier est bon » a
survecu jusqu'a une reponse en langage naturel. C'etait le seul test.

### Les images fixes ne demandaient aucun telechargement

Avant de prendre douze gigaoctets de SDXL : LTX-2.5 avec `length: 1` rend
une image. Il le fait — 169 s et 6,86 Gio en 768x432.

Mais 1024x1024 est tombe en CUDA OOM a 14,57 Gio de pic, sur `VAEDecode`.

Le message le disait, et mon propre code le cachait : `Rendu.erreur`
serialisait le tableau `messages` entier et coupait a 600 caracteres — or
il commence par `execution_start` et `execution_cached`, si bien que la
coupe tombait avant `exception_message`. On lisait un horodatage la ou
ComfyUI ecrivait « CUDA out of memory ... VAEDecode ».

**Amendement, meme jour.** J'ai d'abord conclu qu'il fallait tuiler le
decodage, comme pour la video, et je l'ai ecrit avant de le verifier. La
mesure ne le confirme pas : avec `VAEDecodeTiled`, le 1024x1024 tournait
encore apres 455 s sans aboutir, epingle a 14,65 Gio. Le pic est le meme
quel que soit le mode de decodage — la pression est donc ailleurs, et
`VAEDecode` tombait parce qu'il demandait 2,67 Gio **de plus** sur une
carte deja pleine.

Je n'ai pas isole la cause, et j'ai interrompu le 1280x720 tuile a 150 s,
soit avant les 220 s du non tuile : il n'est donc pas etabli que le
tuilage soit plus lent ici. Conclusion etroite et honnete : au-dela de
~0,9 megapixel, LTX est a la limite de cette carte pour une image fixe.

### Un modele d'image, finalement

SDXL 1.0 base installe (6,94 Go + 335 Mo de VAE corrige, 86 Mo/s en six
tranches paralleles). Meme consigne, meme graine :

    LTX   1280x720    220 s   14,58 Gio   objet mou, lumiere respectee
    SDXL  1024x1024    45 s   13,46 Gio   objet net, lumiere ignoree
    SDXL  1344x768     35 s   13,23 Gio

Cinq fois plus rapide, a une resolution que LTX n'atteignait pas. Mais le
resultat le plus utile n'est pas « SDXL gagne » : les deux sont
complementaires. SDXL rend l'objet net et les graduations lisibles, et
aplatit la lumiere ; LTX est mou sur l'objet — un sextant demande, des
compas rendus — et respecte la lumiere laterale demandee.

SDXL pour une vignette dont le sujet doit se reconnaitre, LTX pour un plan
d'ambiance ou une image qui doit se raccorder a de la video.

Licence CreativeML Open RAIL++-M, usage commercial permis. Flux.1-dev
ecarte (non commercial) ; Flux.1-schnell est Apache 2.0 mais demande en
plus un encodeur T5 de cinq a dix gigaoctets sur une carte deja partagee.

### L'audio natif etait sur le disque depuis le debut

`ltx-2.5-audio-vae-bf16.safetensors` n'etait reference nulle part parce
que `LTXVAudioVAELoader` lit dans `checkpoints` et non dans `vae`. Une
ligne de `extra_model_paths.yaml`.

Deux verifications avant d'allumer le GPU : le VAE porte les prefixes
`audio_vae.` et `vocoder.` attendus, et le GGUF distille declare
`AVTransformer3DModel` avec `use_audio_video_cross_attention: true`.

    rendu        339 s pour 2,04 s  (+21 % sur la video seule)
    pic VRAM     11,07 Gio          (7,75 en video seule)
    piste        AAC 48 kHz stereo, 2,01 s
    niveau       moyenne -7,9 dB, crete 0,0 dB

Le niveau a ete **releve**, pas deduit de la presence d'une piste : un MP4
porte volontiers un canal silencieux et se termine avec le code 0. La
crete a 0,0 dB dit au passage que le signal sature.

Ce que ni Piper ni Kokoro ne peuvent poser apres coup : des pas qui
tombent sur l'image, une porte au bon quart de seconde.

### Une raison fausse propagee en quatre endroits

`BESOIN_DEFAUT` valait 11,5 Gio — le **poids du fichier** Q3_K_M — en
supposant que les poids resident sur la carte. Ils n'y resident pas :
`--cache-none` les fait diffuser depuis la RAM, et trois quantifications
de 10,7 a 17,4 Go avaient donne le meme pic a deux centiemes pres.

Reserver 11,5 quand il en faut 7,8 n'est pas prudent : c'est faux dans
l'autre sens, et la file aurait refuse des rendus qui tenaient. Le faux
echec, que ce depot traque autant que le faux succes.

La constante existait en **quatre exemplaires** — routes, file de nuit,
atelier, outil MCP. Une seule definition desormais, dans `arbitrage`.

La meme erreur justifiait le choix de l'attention dans `hermes-ltx.bat` :
« 10,73 + 8,25 depasse 15,98 ». Avec le pic reel, `split` — 40 % plus
rapide que `sub_quad` — tiendrait. Note dans le lanceur, non applique :
une hypothese n'est pas une mesure, et c'est exactement ce que cette
correction dit.

### Nettoyage

    LTX-2.5-gemma4-12b-text-encoder-Q4_K_M.gguf   8,60 Go  incompatible (AviUtl2)
    LTX-2.5-Distilled-Q3_K_M.gguf                10,73 Go  sous le plancher Q4
    LTX-2.5-Distilled-Q6_K.gguf                  17,38 Go  +34 % de temps, ecarte

70 Go -> 33 Go. Les trois etaient mesures et documentes ; a 60-85 Mo/s,
en reprendre un coute quelques minutes.

### Verified

Delegation : 12 appels d'outils en 54 s, l'agent nomme les trois plans et
rapporte `indetermine` pour chacun sans jamais parler de succes.

Audio natif : `pluie_toit_00001_.mp4`, AAC 48 kHz stereo, moyenne -7,9 dB
et crete 0,0 dB — niveau **releve**, pas deduit de la presence d'une
piste. 339 s, pic 11,07 Gio.

Images : quatre rendus sur disque, deux LTX et deux SDXL, tailles et
resolutions verifiees par ffprobe.

Disque : 70 Go -> 33 Go sur `C:/AI/Models/LTX`, plus 6,8 Go pour
`C:/AI/Models/Images`. Aucun residu `.part`.

Suites : backend **2 131 passes, 2 ignores** ; frontend **110 passes** ;
`npx tsc --noEmit` propre. Onglet Nuit verifie dans le navigateur.

---

## HOS-191 - Le relecteur, la file de nuit, et trois mesures fausses (2026-08-27)

Un plan video se termine toujours. ComfyUI rend un MP4 valide quel que soit
le contenu, et a cinq minutes de calcul par seconde de video finie, s'en
apercevoir au montage coute une nuit. Deux modules repondent a cela : un
relecteur qui regarde ce qui est sorti, et une file qui enchaine les plans
sans jamais compter un rendu acheve pour un rendu reussi.

Ce qui a coute du temps n'est pas leur ecriture. Ce sont **trois defauts de
mesure**, dont deux invisibles.

### Le relecteur a failli fabriquer de la confiance

Interroge une premiere fois, le modele a repondu « matches: true,
confidence: 98 » en enumerant comme presents les trois elements de la
consigne, dont de la vapeur que l'oeil ne trouvait pas. Un relecteur qui
approuve tout ne mesure rien.

La qualification passe donc par le cas negatif : la meme image, quatre
consignes fausses, graduees de l'absurde (un chiot en studio) au proche
(une rue de nuit en neons bleus sous la pluie — meme ambiance, autre
sujet). **4 refus sur 4**, consigne vraie acceptee, le cas proche refuse a
95 %.

### La fenetre bornee, encore

`num_predict` a 300 rendait `done_reason=length` et une reponse **vide** :
ce modele depense son budget en raisonnement avant de conclure. Le prendre
pour un refus aurait disqualifie un modele qui fonctionne. C'est le defaut
que ce depot documente deja sous « ni un echec sur parole », rencontre une
fois de plus, et il ne se reconnait pas plus facilement la deuxieme fois.

### Un cache KV de 256k pour juger une image

Le tag portait `num_ctx 262144` pour une image de 768 x 416 et cent vingt
jetons de consigne. L'allocation faisait depasser **300 s au chargement a
froid** : la premiere execution reelle est revenue en `TimeoutError`, ce
qui se lisait comme un relecteur en panne.

    residente    6,29 Gio  ->  2,41 Gio
    a froid     > 300 s    ->    9,9 s
    a chaud      21,7 s    ->    5,0 s

Le module, lui, avait raison : il a rendu `correspond: None` — « je n'ai
pas pu regarder » — et non `False`. La distinction a evite de conclure a
un plan non conforme sur une panne d'instrument.

### Trois images qui n'en etaient qu'une

`extraire()` documentait qu'elle rendait trois images reparties dans le
plan : « prendre seulement la premiere, c'est relire la couverture d'un
livre ». Elle en rendait **une**. Le filtre `thumbnail` choisit une image
representative par lot de cent, et un plan LTX en compte quarante-neuf.

Le lot reduit a la longueur du plan n'a pas corrige le defaut : les trois
fichiers sortaient alors **octet pour octet identiques**. Leurs tailles se
ressemblaient assez pour ne pas alerter — 386 Kio chacun — et seule une
empreinte SHA l'a montre. On demande desormais chaque image a un instant
precis, 15 / 50 / 85 % de la duree, une par appel.

### Un verdict qui portait sur un seuil jamais fixe

Sur le meme plan reel, deux reglages du **meme** modele ont vu exactement
la meme chose — rue etroite, nuit, sodium, asphalte mouille, pas de vapeur
— et rendu des verdicts opposes. Pas une divergence de perception : un
blanc dans la question. La consigne disait « sois strict » sans dire ce que
« correspond » signifie quand un element secondaire manque.

La regle est desormais ecrite — sujet, decor, moment et lumiere decident ;
un detail absent va dans `missing` et ne rejette pas — et l'assouplissement
a ete re-qualifie : toujours 4 refus sur 4.

### Un chemin qui ne menait nulle part

L'historique de ComfyUI decrit ses sorties par `{filename, subfolder,
type}`, dont aucun ne designe un fichier : la racine est dans les arguments
de lancement, `--output-directory E:\YouTube\Generations`. Le client ne
gardait que `filename`. Le relecteur recevait donc `rue_sodium_00001_.mp4`
et n'en tirait aucune image.

Trouve dans le rapport d'une nuit reelle, pas en relisant le code — et
seulement parce que la file avait ecrit `indetermine` au lieu de `retenu`.
Le comportement etait juste ; c'est la mesure qui manquait.

### Le montage, ou trois autres facons de rendre 0

`backend/studio/montage.py` assemble les plans retenus, pose la narration,
incruste les sous-titres — et **relit la duree du fichier obtenu**. Parce
que `ffmpeg` sort avec le code 0 dans trois cas ou le resultat n'est pas
celui qu'on croit : une entree manquante rend une video plus courte, un
SRT dont la fin precede le debut affiche un sous-titre qui ne disparait
jamais, et libass absent rend une video sans texte.

Mesure le 2026-08-27 : trois plans de 2,04 s -> 6,12 s verifiees, 1 s
d'encodage. Narration Piper de 9,96 s sur 6,12 s d'image, ecart `+3,84 s`
**rapporte et non corrige** — etirer changerait la voix, couper perdrait
la fin, et l'appelant est le seul a savoir lequel il prefere.
L'incrustation a ete constatee en comparant l'empreinte d'une image du
montage a la meme image du montage sans sous-titres.

### La file de nuit

`backend/studio/file_de_nuit.py`. Sept etats et non deux : un plan rendu
mais non relu est `indetermine`, jamais `retenu`. Elle reserve la carte
pour chaque rendu — un rendu lance pendant qu'une mission tient les 16 Gio
aboutit, dix-sept fois plus lentement, sans qu'aucune erreur ne le dise —
et la rend entre deux plans. Elle s'arrete apres trois echecs consecutifs :
au-dela, la nuit ne sert plus qu'a confirmer le meme defaut.

Le journal est reecrit apres **chaque** plan : une nuit coupee a la
sixieme heure doit laisser lisibles les cinq premieres.

Toutes ses dependances sont injectees. Une file qui ne se testerait que par
des nuits entieres ne serait jamais testee.

### Verified

Nuit reelle du 2026-08-27, file branchee sur ComfyUI + arbitrage +
relecteur : **2/2 plans retenus en 10 min**, 203 s et 212 s, pic 7,75 Gio
sur une carte de 15,98 — sur la carte, pas en memoire systeme. Chemins
absolus, relecture 3 images sur 3, confiance 100.

Discrimination verifiee sur un **second plan** que la qualification n'avait
pas servi : l'atelier est accepte pour sa consigne (3/3) et refuse pour
celle de la rue de nuit (0/3).

Une nuit precedente, avant le correctif des chemins, avait rendu 3 plans
en 309 / 294 / 309 s, tous a 7,61 Gio, tous consignes `indetermine` — la
file avait raison de ne pas les compter.

Montage final : 2 plans -> 4,08 s verifiees, h264 + aac, sous-titres
incrustes et constates a l'image.

Suites : backend **2 129 passes, 2 ignores** ; frontend **110 passes** ;
`npx tsc --noEmit` propre.

---

## HOS-190 (fin) — La quantification est presque gratuite (2026-08-27)

Meme format, meme graphe, seule la quantification change. 768 x 432,
49 images, 8 etapes.

    Q3_K_M   10,73 Go    251 s    pic 7,59 Gio
    Q5_K_M   15,66 Go    281 s    pic 7,61 Gio    +12 % de temps
    Q6_K     17,38 Go    336 s    pic 7,59 Gio    +34 % de temps

**Le pic de VRAM ne bouge pas.** 7,59 / 7,61 / 7,59 — a deux centiemes
pres, sur trois fichiers dont le plus gros depasse la carte de 1,4 Gio.

C'est la preuve definitive d'une hypothese formee en regardant les mesures
precedentes : ComfyUI **diffuse** les couches depuis la RAM au lieu de les
resider. `--cache-none` et `--disable-smart-memory` — les reglages que la
distribution patientx avait choisis pour ce materiel, et que j'avais failli
perdre en relancant le serveur avec mes propres drapeaux — font exactement
cela.

Le compromis n'est donc pas memoire contre qualite mais **temps contre
qualite**, et il est bon marche jusqu'a Q5 : quarante-six pour cent de bits
en plus pour douze pour cent de temps. Q6 demande vingt pour cent de plus
pour un ecart de quantification bien moindre.

Q5_K_M retenu, et consigne dans `hermes-ltx.bat` avec le tableau.

A noter : Q3_K_M etait **sous** le plancher que ce depot s'etait fixe
ailleurs — « jamais sous Q4 », note apres la campagne de modeles de secours.
La mesure confirme la regle, et cette fois elle ne coute presque rien.

### Verified

Cinq MP4 valides sous `E:\YouTube\Generations`, en-tete `ftyp` verifiee.
Suites inchangees : backend 2 083 passes, frontend 110 passes.

---

