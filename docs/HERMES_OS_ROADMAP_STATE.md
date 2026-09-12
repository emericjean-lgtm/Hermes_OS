# HERMES OS — ROADMAP STATE

> **Lire ce fichier en premier.** Il tient en une page et dit où en est le
> projet. Le détail vit dans `docs/HERMES_OS_MASTER_ROADMAP.md`.
>
> Ce fichier est un **pointeur**, pas une preuve. Il ne doit jamais
> affirmer qu'une section est terminée : il renvoie au statut établi dans
> la roadmap maître, lequel exige des preuves mesurées.

```
CURRENT_SECTION:      §15 — Frontend ↔ Backend Product Parity / Hermes Assistant
CURRENT_SUBSECTION:   §15.5 — Explainability / Resource visibility / Proofs
                      premier lot livré (HOS-298) ; §6.1 🟢 — la décision
                      du routeur atteint l'exécution
CURRENT_STATUS:       🟡 §15.5 premier lot (HOS-298) — routage d'un run
                      (`Run.decision`, HOS-242) et comptabilité physique
                      (R-6) branchés dans l'Operations Center ; restent
                      A-8/`DecisionExplainer`, G-3 hors ce Center, et la
                      famille Execution proofs. §6.1 fermée · §6.2 livré (HOS-257)
                      A-15 (HOS-258) · R-3/R-4 (HOS-259) · R-6 (HOS-260)
                      A-18 (HOS-261) · A-19 (HOS-262) · G-12 (HOS-263)
                      G-14 fermé (HOS-264) — le catalogue est sondé
                      §16 🟡 (HOS-265→274) — le pont, la matrice,
                      le chat joignable et enfin interruptible
                      §10 🟡 (HOS-274→286) — les Skills se lisent, le
                      chiffre de HOS-153 était faux, la provenance est
                      mesurée (60 système / 4 générées / 1 conflit), la
                      corrélation Run ↔ Skill est ADOPT, l'observateur est
                      INSTALLÉ, la relation est MONTRÉE, le cycle de vie
                      est VÉRIFIÉ à l'octet, et la pose est GOUVERNÉE :
                      demande → approbation Aegis → décision → pose
                      vérifiée. Restent versioning et rollback
                      §9/§15 🟡 (HOS-288→289) — les 22
                      Centers ont enfin été ouverts : 304 requêtes,
                      aucun 404 ; 2 écrans inventaient des mesures,
                      et le chiffre MCP avait dérivé (71 → 81)

LAST_VALIDATED_SECTION:        §1, §2, §5  (🟢)
                               §3, §4 rétrogradées 🟡 par l'audit J25
LAST_CONSOLIDATED_MILESTONE:   J24 — HOS-254
BASELINE:                      c9ad553 (T-28/HOS-297) — dernier commit
                               avant l'ouverture de §15.5 (HOS-298)
LAST_AUDIT:                    J25 — audit global final indépendant
                               verdict 🟠 PARTIELLEMENT CONFORME
LAST_FIX:                      A-1 fermé (HOS-255) — pare-feu cloud
                               inévitable par construction
                               A-2 fermé (HOS-256) — HOS-217/218 câblés
                               §6.2 livré (HOS-257) — admission + réservation
                               A-15 fermé (HOS-258) — source GPU canonique
                               R-3/R-4 fermés (HOS-259) — concurrence
                               dérivée de la capacité, bornée globalement
                               R-6 fermé (HOS-260) — consommation physique
                               par run, avec sa limite d'attribution
                               A-18 fermé (HOS-261) — l'empreinte déclarée
                               couvre le contexte réellement servi
                               §6.1 🟡 (HOS-262) — le type de tâche décide
                               enfin ; A-19 fermé en chemin
                               G-12 fermé (HOS-263) — un repli ne défait
                               une décision que s'il est mieux prouvé ;
                               §6.1 🟢, G-14 ouvert en chemin
                               G-14 fermé (HOS-264) — 18 essais réels,
                               6 modèles, 6/6 prouvés capables ;
                               G-15 ouvert en chemin
                               §16 🟡 (HOS-265) — Hermes Agent 0.21.0,
                               pont unique, capacités négociées ;
                               G-16 et G-17 ouverts en chemin
                               §16 avance (HOS-266) — le pont demande ;
                               sessions, outils, profils, délégation et
                               routines servis au Center « Cerveau » ;
                               G-18 ouvert, G-17 réduit de 17 à 12
                               G-18 fermé (HOS-267) — l'agent est seul
                               autorité sur `state.db`, Hermes OS demande
                               et trace ; une mutation intégrée de bout
                               en bout ; G-19 ouvert
                               G-19 fermé (HOS-268) — 206 méthodes
                               relevées, matrice reconstruite 19/19 ;
                               G-20 ouvert
                               G-20 avancé (HOS-269) — lire et renommer
                               une session intégrés ; deux candidates
                               écartées par la mesure ; G-21 ouvert
                               HOS-270 — approbations écartées faute de
                               producteur ; bascule de toolset intégrée ;
                               G-22 ouvert
                               G-22 partiellement fermé (HOS-271) — le
                               chat ACP existait et était injoignable ;
                               permissions d'édition tracées ; G-23 ouvert
                               G-23 tranché (HOS-272) — REJECT : la
                               convergence ACP↔Gateway fabrique de faux
                               succès ; garde posée, rien livré d'autre
                               G-24 fermé (HOS-273) — interruption ACP
                               réelle (217 s → 17 s) ; deux faux contrôles
                               déjà livrés corrigés ; G-25 ouvert
                               A-10 fermé (HOS-290) — le pare-feu voit
                               enfin la clé de son propre fournisseur
                               A-3 fermé (HOS-291) — on savait prendre un
                               filet, on sait le rendre : aperçu, accord
                               Aegis nommant le point de reprise,
                               restauration prouvée au navigateur puis
                               après redémarrage ; A-22/A-23/A-24 ouverts
                               en chemin
                               A-4 fermé (HOS-292) — l'habilitation de
                               workspace devient **nominative** : valider
                               un projet n'accorde sa racine qu'aux actions
                               qui le nomment. Avant : deux projets valides,
                               `project_id=None` lisait le secret de l'autre ;
                               60 racines dans l'union sur la base servie.
                               Prédicat unique `authorized_root` (il était
                               écrit 3 fois) ; 14 mutations rouges puis
                               vertes ; G-43/G-44/A-26 ouverts en chemin
                               G-15 fermé (HOS-293) — un verdict agentique
                               porte désormais l'empreinte (digest +
                               num_ctx) mesurée avec lui ; revérifiée à
                               chaque lecture, elle rend `None` — non
                               prouvé, pas prouvé faux — quand `ollama
                               pull` ou un Modelfile édité change ce qui
                               répond sous le même tag ; 15 mutations
                               rouges puis vertes, chaîne bout en bout
                               jusqu'à `_agentic_model` et redémarrage
                               inter-processus démontrés
                               G-11 fermé (HOS-294) — le rapport de
                               mission ne fait plus passer la
                               recommandation jamais invoquée
                               d'`AgentCoordinator` pour une mesure ;
                               `TaskExecution.tools_used` vient de ce que
                               `_run_tool_loop` a réellement appelé, vide
                               et honnête sur le chemin hermes-agent ;
                               l'asymétrie qui décide d'où bâtir Cowork
                               (§15.4) reste ouverte — G-11 fermait le
                               mensonge du rapport, pas l'asymétrie
                               G-16 avancé (HOS-295) — la dette de routes
                               orphelines datait du 2026-09-07 (120/306) et
                               n'avait jamais été revérifiée ; `_motif`
                               n'acceptait pas `$` en fin de chemin et
                               classait 4 appelants réels comme orphelins
                               (`` `/route${qs}` ``, le patron dominant du
                               client) — corrigé, mutation rouge→vert à
                               l'appui, 5 entrées retirées (118→113 sur
                               314 routes). Le reste n'est pas homogène :
                               sondes d'infra, pont de compatibilité
                               documenté, surfaces fonctionnelles non
                               câblées par choix déjà écrit ailleurs
                               (HOS-070), appelants opérateur hors
                               frontend — aucune n'avait de preuve
                               suffisante pour suppression ; classées à
                               conserver, pas fermées, pas fantômes
                               G-10 fermé (HOS-296) — l'énoncé du gap
                               datait d'avant une lecture directe du code :
                               `POST /memory/{id}/promote` existait déjà
                               (HOS-250), montée deux fois, gouvernée,
                               testée par 19 tests — mais sans appelant
                               frontend, exactement le défaut que G-16
                               nomme. Panneau Quarantaine ajouté au Memory
                               Center ; vérifié bout en bout sur le
                               processus réel, promotion persistée après
                               redémarrage backend ; `/memory` et
                               `/memory/{memory_id}/promote` retirés de
                               `ORPHELINS_CONNUS` (113→111)
                               T-28 tranché (HOS-297) — OPTION B : Chat et
                               Cowork sont deux contrats produit distincts
                               sur une infrastructure partagée, pas deux
                               modes d'une même exécution. La prémisse de
                               §15.1 (Ledger et bus déjà communs) ne
                               résistait pas à la lecture du code : le
                               chat n'ouvre jamais de Run
                               (`runs/correlation.py` :
                               `etiquette_du_tour()` rend `""` sans Run de
                               mission déjà ouvert) et son bus
                               d'événements est déclaré, jamais câblé
                               (`conversation_manager` sans
                               `event_dispatcher`, G-45 ouvert). Ce qui
                               est réellement partagé et mesuré : le même
                               registre de session ACP
                               (`sessions_de_mission.py: registre()`),
                               sous la même clé `projet:{id}`, entre
                               `conversation/harnais.py` et
                               `execution/task_executor.py`, et la même
                               base SQLite (`get_settings().sqlite_path`)
                               pour `runs`, `missions` et les
                               conversations. §15.4 hérite de l'asymétrie
                               d'outils de G-11, qui reste ouverte
                               §15.5 premier lot (HOS-298) — `Run.decision`
                               (HOS-242) et la comptabilité physique R-6
                               transitaient déjà par les routes
                               `/operations/.../{runs,lignee}` ; R-6
                               s'arrêtait avant `_run_en_dict`, qui ne
                               recopiait pas ses quatre colonnes. Les deux
                               sont désormais affichés dans la lignée d'un
                               run à l'Operations Center — routage
                               silencieux sauf déviation réelle, écart
                               machine affiché seulement si `exclusif`.
                               Aucune route neuve. A-8/`DecisionExplainer`,
                               G-3 (autres Centers) et Execution proofs
                               (`mission/verification.py`) restent ouverts,
                               ce dernier diagnostiqué mais non branché —
                               son système de mission reste à confirmer
                               avant d'y toucher
```

`CURRENT_SECTION: §6` dit où porte le travail, pas qu'il soit fini. §6.1
est fermée (HOS-262 + HOS-263), §6.2 livré (HOS-257), A-15 fermé
(HOS-258), §6.5 fermé par R-3/R-4 (HOS-259), la comptabilité physique par
R-6 (HOS-260) et les empreintes déclarées par A-18 (HOS-261). Reste §6.6,
qu'aucune passe n'a ouverte.

**§6.1 est passée 🟢 le 2026-09-06 (HOS-263).** HOS-262 avait rendu le
routage juste — le routeur classait bien et n'était jamais écouté, un
filtre placé après lui multipliant l'empreinte mesurée par le **nombre de
mots du titre** de la tâche. Restait G-12 : `_agentic_model` défaisait
ensuite **toutes** ses décisions, 0 sur 5 mesurées. La règle disait de
substituer un repli « connu-bon » ; mesuré, le repli n'est pas mieux prouvé
que ce qu'il remplace — aucun des six modèles du catalogue n'a jamais été
sondé. Un repli ne défait désormais une décision que s'il porte une preuve
qu'elle n'a pas : **5 sur 5** conservées.

**G-14 est fermé le 2026-09-06 (HOS-264).** §6.1 était 🟢 sur une décision
juste appliquée à des modèles dont *aucun* n'avait de capacité agentique
mesurée. Le protocole existait pourtant en entier (`scripts/sonder_modeles.py`,
HOS-142) : c'est le magasin qui était vide. En le remplissant, la sonde
s'est révélée mesurer **la convention de chemin plutôt que le modèle** —
elle ne nommait pas le répertoire de travail, là où la production le nomme.
Corrigée, puis 18 essais réels sur les 6 modèles du catalogue : **6 sur 6
prouvés capables**, et les 5 décisions du routeur survivent toujours. §6.1
reste 🟢 — mais désormais sur une base mesurée, pas supposée.

**§16 — le pont Hermes Agent — est 🟡 depuis le 2026-09-07 (HOS-265).**
Infrastructure transverse, consommée par §7, §8, §10, §11, §13 et §15, et
sans autorité nouvelle. L'agent est passé en v0.21.0 sans perdre un octet
d'état, et le pont **négocie** ce que le runtime sert au lieu de le
supposer : 54 méthodes présentes, 8 absentes, 15 surfaces complètes sur 18.
Une seule — les capacités elles-mêmes — a la chaîne entière jusqu'au
cockpit ; les autres sont visibles et **non intégrées**, et le disent.

La règle posée dans la même passe est ce qui empêchera l'écart de se
reformer : `test_pas_de_backend_orphelin.py` fait rougir toute route neuve
sans appelant frontend. Elle a commencé par mesurer que **120 routes sur
306 — 39 %** n'en ont aucun.

**HOS-266 a fait passer cinq surfaces de « négociée » à « démontrée ».** Le
pont ne savait que négocier — dire ce que le runtime peut faire — et les
capacités étaient donc visibles et inertes. Il tient désormais une
connexion vivante et sait demander : sessions (200), toolsets (62, dont 8
actifs), profils, délégation et routines sont servis par une route unique
et affichés dans un Center « Cerveau ». **HOS-267 a tranché l'autorité (G-18).** La question était mal posée :
mesuré, `session.resume` **n'écrit rien** — empreinte de `state.db`
identique, et son handle meurt avec le gateway. C'est une *activation*, pas
une mutation. Trois choses distinctes, trois propriétaires : la conversation
stockée est à l'agent, la session vivante au processus, et le **récit de ce
qu'on a demandé** à Hermes OS. Hermes OS demande donc au propriétaire et
trace sa demande dans son propre bus — il n'ouvre jamais `state.db`, et deux
gardes structurelles l'en empêchent. Une mutation additive
(`session.branch`, le fork) est intégrée de bout en bout, clic réel vérifié.

**HOS-268 a corrigé la matrice elle-même (G-19).** Relevé du registre réel
du runtime : **206 méthodes**, là où le pont en sondait 62 — et les trois
surfaces déclarées absentes l'étaient sur des noms **inventés**. La matrice
mesurait notre vocabulaire, pas le runtime ; reconstruite depuis le
registre, elle compte **19 surfaces, 19 complètes**. Les deux absences qui
subsistent — la mémoire, et le lancement d'un subagent — sont vérifiées
contre les 206 et portent leur preuve, au lieu de disparaître de l'écran.
Le relevé est versé au dépôt, daté et empreint ; trois gardes interdisent
qu'un nom inventé y rentre.

**HOS-269 a transformé le relevé en produit (G-20).** Deux tranches
verticales intégrées — **lire** une session et la **renommer** — et surtout
**deux écartées par la mesure avant d'écrire une ligne** : `delegation.pause`
est un global du processus gateway (pause posée dans une connexion, `False`
lue dans une autre, donc un bouton qui briderait un processus où aucune
mission ne tourne), et rien ne lance un subagent par RPC — c'est un outil
que l'agent s'appelle. La mémoire reste sans couture : aucune méthode dans
les 206, la capacité vivant côté agent, d'où **G-21** — Hermes OS ne peut
lui appliquer ni provenance, ni quarantaine, ni promotion.

**HOS-270 a écarté les approbations et intégré les toolsets.** Les trois
méthodes d'approbation répondent, mais la file est **en mémoire** et bloque
un fil de l'agent : les missions prennent le mode déterministe — le CLI pose
lui-même `HERMES_SINGLE_QUERY_SESSION` — et le pont ne lance aucun tour. Un
panneau serait vide par construction. C'est **G-22** : approbations,
steering et interruption attendent toutes le **chat**, leur seul producteur.

`tools.configure` en revanche écrit `config.yaml`, que tous les processus
agent relisent, missions comprises : la bascule d'un toolset est intégrée
de bout en bout.

**HOS-271 a trouvé que le chat interactif existait déjà (G-22).** Une
conversation liée à un projet ouvre une session Hermes Agent **vivante par
ACP**, et l'agent y demande une permission avant chaque édition de fichier —
mesuré, **quatre décisions dont trois refus** sur un seul tour, un contrôle
qui agit vraiment et que personne ne voyait. Ce chemin était **injoignable
depuis l'Assistant** : sa sonde de disponibilité interrogeait le backend en
synchrone depuis le handler, bloquant la boucle qui devait répondre. Corrigé,
les décisions sont tracées et affichées. **G-23** : le chat passe par ACP et
le pont par le gateway — deux transports, deux files, sans passerelle.

**HOS-272 a tranché G-23 : REJECT.** Les deux transports partagent pourtant
`state.db`, et le Gateway *reprend* un identifiant ACP sans erreur — d'où la
tentation. Mais la reprise matérialise une **seconde session vivante** dans
son propre processus : mesuré pendant un tour ACP réel, `session.steer` rend
`queued` et `session.interrupt` rend `interrupted` **sans toucher le tour**,
qui se termine normalement et écrit son fichier. Une ligne stockée, deux
sessions vivantes, deux processus. Rejeté plutôt que différé : la
convergence produirait exactement le faux succès que ce dépôt poursuit
depuis l'origine. Le chemin réel est le contrôle **natif d'ACP**
(`acp_adapter/server.py: cancel`).

**HOS-273 l'a emprunté et fermé G-24 — interruption ADOPT.** `session/cancel`
atteint le tour vivant : 50 s et 9898 caractères sans annulation, **12 s et
0 caractère** avec, et **195 s avec un mauvais identifiant** — le contrôle
est donc réel *et* corrélé. De bout en bout par HTTP : 217 s → 17 s.

Deux faux contrôles **déjà livrés** ont été corrigés au passage :
`POST /conversation/{id}/cancel` marquait la conversation `CANCELLED` sans
toucher le tour, et le bouton « stop » de l'Assistant n'abandonnait que le
`fetch` — le navigateur cessait de lire pendant que l'agent continuait
d'écrire. Tous deux affirmaient avoir arrêté quelque chose.

Le **steering reste DEFER** (G-25) : rien n'injecte dans un tour actif ; ACP
n'offre qu'« annuler puis redemander », un geste produit distinct. Deux réserves mesurées et affichées — le premier
basculement fige les défauts du jour dans le fichier, et un toolset de
plugin peut être refusé tant que la découverte n'a pas abouti.

**§15 — Hermes Assistant — a été créée le 2026-09-05 et n'est pas la
section active.** Elle est une couche produit qui consomme §1→§13 ; la
créer ne la rend pas prioritaire. Le contrat §15.1 (T-28) doit être
tranché avant toute ligne de produit. (A-3, A-4 et G-10 — les dettes qui
bloquaient §15.4/§15.6 — sont fermées depuis, respectivement HOS-291,
HOS-292 et HOS-296.)

**G-15 est fermé le 2026-09-12 (HOS-293).** `agentic_probe.py` indexait un
verdict sur le seul tag du modèle : un `ollama pull` remplaçant les poids
sous ce tag, ou un Modelfile édité pour servir un autre `num_ctx`,
laissaient le verdict stocké en place, sans que rien ne le signale,
jusqu'au prédicat de production et à la décision du routeur. Chaque
entrée du magasin porte désormais l'**empreinte** — `digest` (`/api/tags`,
un hash de contenu) et `num_ctx` (parsé du Modelfile que `/api/show`
renvoie) — mesurée avec elle. `measured_success_for` la revérifie à
chaque lecture contre ce qu'Ollama sert maintenant ; un écart rend `None`,
non prouvé plutôt que la valeur périmée (même distinction à trois états
que T-29). `save_result` applique la même règle en écriture : une
empreinte différente de celle stockée repart d'une série à zéro plutôt que
de mélanger des essais mesurés sur deux modèles distincts. Une empreinte
introuvable échoue **ouvert** — elle ne fabrique pas un faux échec à
partir d'une panne réseau. Même remède que celui que
`hermes_agent_bridge.NegociationRuntime` applique déjà à son propre
cache, appliqué au second magasin qui en avait besoin. 15 mutations
rouges puis vertes, chaîne bout en bout démontrée jusqu'à
`RealTaskExecutor._agentic_model`, et redémarrage inter-processus vérifié.

**G-11 est fermé le 2026-09-12 (HOS-294).** `AgentCoordinator._select_tools`
recommande des outils par mot-clé contre le catalogue de plugins MCP ;
`task_executor.py:31` documentait depuis HOS-069 que rien ne l'invoque
jamais — un espace de noms disjoint des deux seuls chemins d'exécution
réels (Hermes Agent choisit ses propres outils par son propre MCP,
HOS-085 l'interdit à Hermes OS ; la boucle locale n'offre qu'un jeu fixe
`workspace_*`/`verification_*`). Ce que HOS-069 ne disait pas : ce champ
jamais invoqué atteignait quand même l'opérateur — `execute_task`
rapportait `"tools": task.assigned_tools` aux côtés de trois champs qui
rapportent, eux, ce qui a réellement servi, et `finalize()` agrégeait la
même recommandation dans un `ExecutionReport.tools_used` jamais rempli par
une mesure. Invoquer réellement `assigned_tools` a été écarté — ça violerait
HOS-085 sur le chemin agent, ou exigerait un second pont d'outils
disproportionné sur le chemin local, pour une dette classée *technical
debt* et non *architectural*. `_run_tool_loop` capture désormais les noms
réels appelés (`tools_invoked`), et `TaskExecution.tools_used` — sur
l'idiome de `model_used`/`provider_used` — les rapporte à la place de la
recommandation ; vide et honnête sur le chemin hermes-agent, jamais
repêché depuis `assigned_tools`. 6 tests neufs, mutation vérifiée à la
main : reconnecter le rapport à `assigned_tools` fait rougir 3 des 6
exactement sur l'assertion attendue. `assigned_tools` lui-même n'a pas
bougé — le mensonge était dans le rapport, pas dans le champ — et
l'asymétrie qui décide d'où bâtir Cowork (§15.4) reste donc ouverte.

---

## NEXT_ACTION

**Les deux défauts P1 de l'audit J25 sont fermés** (A-1, HOS-255 ;
A-2, HOS-256), et A-15 avec eux (HOS-258). Ce qui reste est de niveau P2
ou moins :

1. ~~**R-3 / R-4**~~ — **fermés le 2026-09-05 (HOS-259)**. La borne vient
   de `ResourceManager`, relue à chaque étape ; le portillon qui
   l'applique est partagé par toutes les missions.
2. ~~**A-10**~~ — **fermé le 2026-09-11 (HOS-290)**. Le pare-feu
   ignorait `sk-or-v1-…`, le format de clé d'OpenRouter lui-même : la
   classe du motif excluait le tiret. Corrigé dans l'unique scanner
   (`audit_log._SECRET_PATTERNS`), prouvé à la socket — 0 requête
   émise sur `chat` et `chat_events`. **§4 passe 🟢.**
3. ~~**A-18**~~ — **fermé le 2026-09-05 (HOS-261)**. L'empreinte dépend
   du contexte servi ; le catalogue porte désormais deux chiffres, et
   l'admission retient le pire cas du tag.
4. ~~**A-3**~~ — **fermé le 2026-09-11 (HOS-291)**. `prendre` avait un
   appelant sur le chemin de toute mission, `restaurer` en avait zéro.
   **ADOPT** : l'appelant naturel existait déjà — le panneau « Points de
   reprise » de Supervision — donc rien n'a été inventé. Aegis reste
   l'autorité, l'accord nomme désormais son point de reprise (les
   empreintes étaient identiques, mesuré), et un état refusé n'est plus
   annoncé repris.
5. **A-16** — trouvé en fermant A-15 : sur Linux sans `rocm-smi`, aucune
   sonde d'occupation ne répond et l'admission ne contraint rien.
   `/sys/class/drm/card*/device/mem_info_vram_used` a la bonne
   sémantique ; rien ici ne permet de l'exercer, et une sonde non
   mesurée reproduirait la faute que A-15 vient de corriger.

### Et §15 dans tout ça

**§15 n'est pas le prochain chantier.** Elle a été formalisée le
2026-09-05 parce que la trajectoire produit n'était écrite nulle part —
pas parce qu'elle est prête. Ce qui la précède :

1. ~~**A-10**~~ — **fermé le 2026-09-11 (HOS-290)**, §4 est 🟢 ;
2. ~~**T-22 / §6.1**~~ — **tranché le 2026-09-05 (ADAPT)** : l'architecture
   existante suffisait, aucun ordonnanceur n'était requis ;
3. ~~**T-29**~~ — **tranché le 2026-09-06 (ADAPT)**, et ~~**G-14**~~
   **fermé le même jour (HOS-264)** : le catalogue est sondé, 6 modèles
   sur 6 prouvés capables. Reste **G-15**, sa suite naturelle — un verdict
   est une mesure datée que rien ne réévalue quand les poids ou le
   `num_ctx` changent sous le même tag ;
4. ~~**T-28**~~ — **tranché le 2026-09-12 (HOS-297, OPTION B)** : Chat et
   Cowork sont deux contrats produit distincts sur une infrastructure
   partagée (agent-cerveau, base SQLite), pas deux modes d'une même
   exécution. §15.1 satisfait son critère de passage.

**§15.5 est ouverte, premier lot livré le 2026-09-12 (HOS-298).** Deux
capacités déjà mesurées et persistées, jamais affichées, sont désormais
branchées dans l'Operations Center : le routage d'un run (`Run.decision`,
HOS-242) et sa comptabilité physique (R-6). `DecisionExplainer` (A-8) et
G-3 hors de ce Center restent ouverts — non traités par ce lot, qui a
délibérément préféré une provenance déjà alimentée par une décision réelle
à une autorité d'explication générique sans appelant démontré derrière
elle. Détail : `CHANGELOG.md` HOS-298, `HERMES_OS_MASTER_ROADMAP.md`
§15.5.

§15.4 (Cowork) était **bloqué** sur A-3 : `checkpoint.restaurer` n'avait
aucun appelant, et un bouton « reprendre » sans restauration mentirait
sur ce qu'il fait. **A-3 est fermé le 2026-09-11 (HOS-291)** — la
restauration est appelable, gouvernée par Aegis et démontrée. Le blocage
qui reste sur §15.4 est donc l'autre : fork/branche n'a toujours aucune
primitive, et l'asymétrie que G-11 décrivait décide toujours d'où bâtir
Cowork (voir HOS-294 ci-dessous : G-11 est fermé, l'asymétrie qu'il
décrivait ne l'est pas).

---

## OPEN_CRITICAL_ARCHITECTURAL_GAPS

| Gap | Classe | Section |
|---|---|---|
| ~~Contournement du pare-feu cloud (A-1)~~ — **fermé HOS-255** | security | §4 |
| ~~Le pare-feu ignore `sk-or-v1-…` (A-10)~~ — **fermé HOS-290** | security | §4 |
| La règle `clé=valeur` de `redact` ne couvre pas un nom en `…_KEY` seul (A-21) — mesuré HOS-290 : `_API_KEY` et `_SECRET` caviardés, `OPENROUTER_KEY:` non ; sans danger pour les clés dont la forme est reconnue, ouvert pour les autres | security | §4 |
| ~~Source d'admission = `/api/ps` (A-15)~~ — **fermé HOS-258** | architectural | §6 |
| Aucune sonde d'occupation sur Linux sans `rocm-smi` (A-16) | architectural | §6 |
| ~~Comptabilité VRAM/CPU par Run (R-6)~~ — **fermé HOS-260** | observability | §6 |
| ~~Empreinte déclarée sous le contexte servi (A-18)~~ — **fermé HOS-261** | architectural | §6 |
| Rien ne détecte un Modelfile élargi sous une empreinte (A-20) | architectural | §6 |
| ~~La promotion d'un souvenir n'a aucune route HTTP (G-10)~~ — **fermé HOS-296** | architectural | §8 |
| ~~Deux files d'approbation, et le cockpit regarde la morte (G-36)~~ — **fermé HOS-285** | security | §15/§23 |
| ~~La file de `backend/policy/` n'a aucun producteur ni consommateur (G-37)~~ — **audité HOS-286 (REJECT), supprimé HOS-287** | technical debt | §15 |
| ~~`assigned_tools` planifié et jamais invoqué (G-11)~~ — **fermé HOS-294** | technical debt | §7 |
| ~~`_RegistreMissions` hydrate sur un ordre non garanti (A-19)~~ — **fermé HOS-262** | test | §3 |
| ~~Le repli agentique défait toutes les décisions du routeur (G-12)~~ — **fermé HOS-263** | architectural | §6/§7 |
| ~~La capacité agentique n'est mesurée pour aucun modèle du catalogue (G-14)~~ — **fermé HOS-264** | architectural | §7 |
| ~~Un verdict agentique est une mesure datée que rien ne réévalue (G-15)~~ — **fermé HOS-293** | observability | §6/§7 |
| 120 routes `/api/v1` sur 306 sans appelant frontend (G-16) | technical debt | §15/§16 |
| Le pont négocie 12 surfaces qu'aucun service n'expose (G-17) | architectural | §16 |
| ~~L'autorité sur l'état de l'agent n'est pas tranchée (G-18)~~ — **fermé HOS-267** | architectural | §16 |
| ~~Le fork était déclaré absent sur la foi d'un nom (G-19)~~ — **fermé HOS-268** | technical debt | §16 |
| 12 surfaces exactes et sans consommateur frontend (G-20) | architectural | §16 |
| La mémoire de l'agent échappe à la provenance Hermes OS (G-21) | architectural | §8/§16 |
| ~~Approbations, steering et interruption attendent le chat (G-22)~~ — **partiellement fermé HOS-271** | architectural | §16 |
| Deux transports agentiques coexistent sans passerelle (G-23) — **convergence REJECT, HOS-272** | architectural | §16 |
| ~~Le contrôle natif d'ACP (`cancel`) n'est pas émis par notre client (G-24)~~ — **fermé HOS-273** | functional | §16 |
| Le steering n'a aucun mécanisme d'injection dans un tour actif (G-25) | functional | §16 |
| `conversation_manager` déclare des événements jamais publiés (G-45) — mesuré T-28/HOS-297 : aucun `event_dispatcher` injecté, le bus de `/conversation/stream` n'émet rien | observability | §15/§16 |
| Deux dimensions sur cinq du score modèle sont inertes (G-13) | technical debt | §6 |
| `test_no_real_subsystem_event_is_dropped` ne tient pas dans le délai de garde de 60 s (A-17) | test | §3 |
| ~~Contrôles de sécurité non câblés (A-2)~~ — **fermé HOS-256** | security | §3 |
| ~~Points de reprise pris et jamais restaurables (A-3)~~ — **fermé HOS-291** | functional | §3 |
| `ALLOWED_PATHS` n'est pas consulté pour une restauration (A-22) — `data_migration` est `path_based: false` ; le seul verrou est la validation humaine. Basculer la catégorie refuserait toute restauration d'instantané (`target_path=None` → `deny`, mesuré HOS-291) | security | §3 |
| Le couple fichiers + état demande deux accords distincts (A-23) — empreintes `{checkpoint}` et `{snapshot}` ; non atteignable aujourd'hui, le seul producteur prend `avec_etat=False` | architectural | §3 |
| La garde d'octets du plugin observateur rougit sur une copie de travail neuve (A-25) — mesuré HOS-291 : LF → CRLF à la sortie de git, 304 → 310 et 4795 → 4914 octets ; le contrat est juste, l'instrument est trop strict d'un cran | test | §3 |
| `prune_snapshots` et `StepCounter` sans appelant de production (A-24) — 26 instantanés pour un `keep` de 20, et le « tous les N pas » du §19.3 n'a jamais lieu | technical debt | §3 |
| ~~Portée projet MCP validée mais non autorisée (A-4)~~ — **fermé HOS-292** : l'habilitation est nominative, la racine ne s'accorde qu'à qui la nomme | security | §8 / §10 |
| Un chat lié à un projet est servi par le harnais, donc ses lectures passent par la frontière ACP et le hook `pre_tool_call`, pas par Aegis (G-43) — mesuré HOS-292 | architectural | §15 / §16 |
| Aucun chip d'outil dans l'Assistant quand un projet est lié (G-44) — le chemin harnais n'émet jamais `tool_calls` ; rien n'est inventé côté frontend | observability | §15 |
| `ensure_for_path` crée et valide un projet par objectif autonome et n'en retire jamais (A-26) — 66 projets, 60 actifs+validés, mesuré HOS-292 | technical debt | §8 |
| Workflows utilisateur écrits dans le dépôt (A-5) | technical debt | §3 |
| `unified_memory` sans isolation de projet | architectural | §8 |
| Quarantaine/provenance non affichées au frontend | UX | §9 |
| Trois fichiers de test portent une séquence d'échappement invalide (`\.`, `\e`, `\u`) | technical debt | §3 |
| `DecisionExplainer` sans consommateur | observability | §9 |
| Une affirmation de capacité sans producteur n'a aucune garde (G-40) — mesuré HOS-289 : aucune regex ne sépare l'affirmation de la négation | observability | §9/§15 |
| 66 numéros de jalon sur 78 entre HOS-112 et HOS-189 ne sont cités par aucun document (G-41) — mesuré HOS-289 ; git en porte 71, donc le travail a eu lieu et c'est le suivi qui l'a perdu | technical debt | — |
| `CollaborationEngine` non intégré au noyau | architectural | §11 |
| Machinerie des skills non adoptée en pratique | future capability | §10 |
| Complétude outils/capacités génériques (HOS-049) | technical debt | §12 |
| Maturation du modèle de propriété des processus | architectural | §7 |

---

## DETTES ACCEPTÉES

- **8 runs orphelins** de mes missions de diagnostic, conservés
  volontairement : `Registre` n'expose aucune suppression, et retirer des
  lignes SQL contournerait la seule autorité du Ledger. **Plus 4 de
  G-34** (`mission: g34-demonstration`), ouverts pour démontrer la
  relation Run ↔ Skill sur le Ledger réel, et marqués `perdu` par la
  réconciliation puisque le processus qui les portait est mort. Même
  raison de les garder : les effacer demanderait de contourner le Ledger.
- **`data/db/hermes.db`** (17,7 Mio) dans le dépôt, non suivi, vestige
  d'avant HOS-215 : données potentiellement utilisateur, décision séparée.
- **`backend/api/hos_routes.py`** non monté (0 route sur 423) — documenté
  depuis HOS-072, conservé comme façade morte plutôt que supprimé sans
  décision.
- **43 modules sans appelant** (8,4 %), dont 13 sans test. Inventoriés,
  non élagués. **Neuf de moins depuis HOS-287** : `backend/policy/` est
  retiré, après l'audit qui a mesuré que ses trois responsabilités
  étaient portées ailleurs. C'est le premier élagage de cette liste, et
  il a demandé deux passes — une pour prouver, une pour retirer.
- **La suite complète n'est pas verte de façon reproductible** (A-17).
  `tests/integration/test_assembly.py::TestEventWiring::
  test_no_real_subsystem_event_is_dropped` lance un objectif autonome
  réel et attend qu'un nœud engagé se termine ; le délai de garde global
  est de 60 s. Mesuré le 2026-09-05, GPU au repos, aucun modèle
  résident : il dépasse le délai **au commit `03f4f96` comme après
  A-15**, avec des piles identiques ligne pour ligne — le fil est bloqué
  dans `_run_coro` sur une inférence, pas dans l'admission. Re-mesuré le
  2026-09-06, T-29 faisant engager un modèle de 20,9 Md là où le repli en
  imposait un de 2,7 : **65 s à la baseline `0d2b9e1`, 66 s après**, même
  pile, même ligne. Le plafond global de 60 s ne laisse passer aucune
  inférence réelle, quel que soit le modèle — la taille du modèle n'entre
  pas dans ce défaut. Le rapport
  §6.2 annonçait « 5979 passed » : c'était vrai ce jour-là, ça ne se
  reproduit pas. Hors périmètre A-15.

---

## PROTOCOLE POUR LA PROCHAINE SESSION

1. lire ce fichier ;
2. lire la section active de `docs/HERMES_OS_MASTER_ROADMAP.md` ;
3. vérifier que `git rev-parse HEAD` correspond à `BASELINE`, ou relever
   l'écart avant de commencer. **Et vérifier que ce SHA existe encore** :
   le 2026-09-05, `BASELINE` nommait `9f98031`, un commit rendu orphelin
   par un `--amend` postérieur à son inscription. Un pointeur qui désigne
   un objet inatteignable ne dit rien.
   **La cause était la convention elle-même** : `BASELINE` nommait le
   commit de la passe en cours, écrit par `--amend` — donc un SHA que
   l'amendement suivant invalidait, à chaque fois. Depuis le 2026-09-05
   il nomme le **dernier commit de code**, jamais celui qui l'écrit ;
4. travailler **dans le périmètre de la section active** ;
5. mettre à jour ce fichier **et** le statut de la section en fin de
   passe ;
6. ne jamais passer une section à 🟢 sans les preuves qu'exige §0 de la
   roadmap maître.
