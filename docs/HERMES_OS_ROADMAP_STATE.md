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
                      §6.1 🟡 — routage juste, défait par le repli (G-12)
CURRENT_STATUS:       🟡 §6.1 audité · §6.2 livré (HOS-257)
                      A-15 (HOS-258) · R-3/R-4 (HOS-259) · R-6 (HOS-260)
                      A-18 fermé (HOS-261) · §6.1 🟡 + A-19 fermé (HOS-262)

LAST_VALIDATED_SECTION:        §1, §2, §5  (🟢)
                               §3, §4 rétrogradées 🟡 par l'audit J25
LAST_CONSOLIDATED_MILESTONE:   J24 — HOS-254
BASELINE:                      04624ae (§15 créée) — dernier commit avant §6.1
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
```

`CURRENT_SECTION: §6` dit où porte le travail, pas qu'il soit fini. §6.1
est audité, §6.2 livré (HOS-257), A-15 fermé (HOS-258), §6.5 fermé par
R-3/R-4 (HOS-259), la comptabilité physique par R-6 (HOS-260) et les
empreintes déclarées par A-18 (HOS-261). Reste §6.6, qu'aucune passe n'a
ouverte.

**§6.1 est passée 🟡 le 2026-09-05 (HOS-262).** Le routeur classait juste
et n'était jamais écouté : un filtre placé après lui multipliait
l'empreinte mesurée par le **nombre de mots du titre** de la tâche, et
éliminait les cinq modèles compétents. Corrigé et démontré. Elle n'est pas
🟢 parce que **G-12** la vide de son effet sur le chemin agentique : le
repli substitue 100 % des décisions.

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
3. **T-29** décide si un modèle non sondé peut piloter la boucle — sans
   quoi le routage reste juste et sans effet (G-12) ;
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
| Le repli agentique défait toutes les décisions du routeur (G-12) | architectural | §6/§7 |
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
  dans `_run_coro` sur une inférence, pas dans l'admission. Le rapport
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
