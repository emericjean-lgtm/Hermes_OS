# HERMES OS — ROADMAP STATE

> **Lire ce fichier en premier.** Il tient en une page et dit où en est le
> projet. Le détail vit dans `docs/HERMES_OS_MASTER_ROADMAP.md`.
>
> Ce fichier est un **pointeur**, pas une preuve. Il ne doit jamais
> affirmer qu'une section est terminée : il renvoie au statut établi dans
> la roadmap maître, lequel exige des preuves mesurées.

```
CURRENT_SECTION:      §6 — Cognitive Scheduler / Resource Intelligence
CURRENT_SUBSECTION:   §6.6 — Ordonnancement cognitif (non ouvert)
                      §6.1 🟢 — la décision du routeur atteint l'exécution
CURRENT_STATUS:       🟡 §6.1 fermée · §6.2 livré (HOS-257)
                      A-15 (HOS-258) · R-3/R-4 (HOS-259) · R-6 (HOS-260)
                      A-18 (HOS-261) · A-19 (HOS-262) · G-12 (HOS-263)
                      G-14 fermé (HOS-264) — le catalogue est sondé
                      §16 🟡 (HOS-265→274) — le pont, la matrice,
                      le chat joignable et enfin interruptible
                      §10 🟡 (HOS-274→276) — les Skills se lisent, le
                      chiffre de HOS-153 était faux, la provenance est
                      mesurée (60 système / 4 générées / 1 conflit), et le
                      plugin qui porterait la corrélation est prouvé
                      faisable mais DEFER faute de consommateur

LAST_VALIDATED_SECTION:        §1, §2, §5  (🟢)
                               §3, §4 rétrogradées 🟡 par l'audit J25
LAST_CONSOLIDATED_MILESTONE:   J24 — HOS-254
BASELINE:                      4791d00 (G-27, HOS-275) — dernier commit
                               de code avant G-28 (plugin observateur)
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
créer ne la rend pas prioritaire, et deux de ses sous-chantiers sont
bloqués par des dettes qui vivent ailleurs (A-3 pour la reprise, A-4 pour
les artefacts, G-10 pour le contrôle mémoire). Le contrat §15.1 (T-28)
doit être tranché avant toute ligne de produit.

---

## NEXT_ACTION

**Les deux défauts P1 de l'audit J25 sont fermés** (A-1, HOS-255 ;
A-2, HOS-256), et A-15 avec eux (HOS-258). Ce qui reste est de niveau P2
ou moins :

1. ~~**R-3 / R-4**~~ — **fermés le 2026-09-05 (HOS-259)**. La borne vient
   de `ResourceManager`, relue à chaque étape ; le portillon qui
   l'applique est partagé par toutes les missions.
2. **A-10** — trouvé en fermant A-1 : le pare-feu ignore `sk-or-v1-…`,
   le format de clé d'OpenRouter. Défaut de détection, pas de routage.
   Bloque §4.
3. ~~**A-18**~~ — **fermé le 2026-09-05 (HOS-261)**. L'empreinte dépend
   du contexte servi ; le catalogue porte désormais deux chiffres, et
   l'admission retient le pire cas du tag.
4. **A-16** — trouvé en fermant A-15 : sur Linux sans `rocm-smi`, aucune
   sonde d'occupation ne répond et l'admission ne contraint rien.
   `/sys/class/drm/card*/device/mem_info_vram_used` a la bonne
   sémantique ; rien ici ne permet de l'exercer, et une sonde non
   mesurée reproduirait la faute que A-15 vient de corriger.

### Et §15 dans tout ça

**§15 n'est pas le prochain chantier.** Elle a été formalisée le
2026-09-05 parce que la trajectoire produit n'était écrite nulle part —
pas parce qu'elle est prête. Ce qui la précède :

1. **A-10** ferme §4 ;
2. ~~**T-22 / §6.1**~~ — **tranché le 2026-09-05 (ADAPT)** : l'architecture
   existante suffisait, aucun ordonnanceur n'était requis ;
3. ~~**T-29**~~ — **tranché le 2026-09-06 (ADAPT)**, et ~~**G-14**~~
   **fermé le même jour (HOS-264)** : le catalogue est sondé, 6 modèles
   sur 6 prouvés capables. Reste **G-15**, sa suite naturelle — un verdict
   est une mesure datée que rien ne réévalue quand les poids ou le
   `num_ctx` changent sous le même tag ;
4. **T-28** tranche le contrat Chat/Cowork — sans lui, §15 ne peut pas
   commencer.

Quand §15 s'ouvrira, **§15.5 est l'entrée à privilégier**, et c'est la
mesure qui le dit plutôt qu'une préférence : `DecisionExplainer` produit
des explications que personne ne demande (A-8), la provenance est exposée
et affichée nulle part (G-3), et §6 vient de rendre la ressource honnête.
Tout y est monté, testé, et sans consommateur — meilleur rapport
valeur/coût du dépôt, et aucune dépendance ouverte.

§15.4 (Cowork) est à l'inverse **bloqué** : `checkpoint.restaurer` n'a
aucun appelant (A-3), et un bouton « reprendre » sans restauration
mentirait sur ce qu'il fait.

---

## OPEN_CRITICAL_ARCHITECTURAL_GAPS

| Gap | Classe | Section |
|---|---|---|
| ~~Contournement du pare-feu cloud (A-1)~~ — **fermé HOS-255** | security | §4 |
| Le pare-feu ignore `sk-or-v1-…` (A-10) | security | §4 |
| ~~Source d'admission = `/api/ps` (A-15)~~ — **fermé HOS-258** | architectural | §6 |
| Aucune sonde d'occupation sur Linux sans `rocm-smi` (A-16) | architectural | §6 |
| ~~Comptabilité VRAM/CPU par Run (R-6)~~ — **fermé HOS-260** | observability | §6 |
| ~~Empreinte déclarée sous le contexte servi (A-18)~~ — **fermé HOS-261** | architectural | §6 |
| Rien ne détecte un Modelfile élargi sous une empreinte (A-20) | architectural | §6 |
| La promotion d'un souvenir n'a aucune route HTTP (G-10) | architectural | §8 |
| `assigned_tools` planifié et jamais invoqué (G-11) | technical debt | §7 |
| ~~`_RegistreMissions` hydrate sur un ordre non garanti (A-19)~~ — **fermé HOS-262** | test | §3 |
| ~~Le repli agentique défait toutes les décisions du routeur (G-12)~~ — **fermé HOS-263** | architectural | §6/§7 |
| ~~La capacité agentique n'est mesurée pour aucun modèle du catalogue (G-14)~~ — **fermé HOS-264** | architectural | §7 |
| Un verdict agentique est une mesure datée que rien ne réévalue (G-15) | observability | §6/§7 |
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
| Deux dimensions sur cinq du score modèle sont inertes (G-13) | technical debt | §6 |
| `test_no_real_subsystem_event_is_dropped` ne tient pas dans le délai de garde de 60 s (A-17) | test | §3 |
| ~~Contrôles de sécurité non câblés (A-2)~~ — **fermé HOS-256** | security | §3 |
| Points de reprise pris et jamais restaurables (A-3) | functional | §3 |
| Portée projet MCP validée mais non autorisée (A-4) | security | §8 / §10 |
| Workflows utilisateur écrits dans le dépôt (A-5) | technical debt | §3 |
| `unified_memory` sans isolation de projet | architectural | §8 |
| Quarantaine/provenance non affichées au frontend | UX | §9 |
| `DecisionExplainer` sans consommateur | observability | §9 |
| `CollaborationEngine` non intégré au noyau | architectural | §11 |
| Machinerie des skills non adoptée en pratique | future capability | §10 |
| Complétude outils/capacités génériques (HOS-049) | technical debt | §12 |
| Maturation du modèle de propriété des processus | architectural | §7 |

---

## DETTES ACCEPTÉES

- **8 runs orphelins** de mes missions de diagnostic, conservés
  volontairement : `Registre` n'expose aucune suppression, et retirer des
  lignes SQL contournerait la seule autorité du Ledger.
- **`data/db/hermes.db`** (17,7 Mio) dans le dépôt, non suivi, vestige
  d'avant HOS-215 : données potentiellement utilisateur, décision séparée.
- **`backend/api/hos_routes.py`** non monté (0 route sur 423) — documenté
  depuis HOS-072, conservé comme façade morte plutôt que supprimé sans
  décision.
- **43 modules sans appelant** (8,4 %), dont 13 sans test. Inventoriés,
  non élagués.
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
