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
CURRENT_STATUS:       🟡 §6.1 audité · §6.2 livré (HOS-257)
                      A-15 (HOS-258) · R-3/R-4 (HOS-259) · R-6 (HOS-260)

LAST_VALIDATED_SECTION:        §1, §2, §5  (🟢)
                               §3, §4 rétrogradées 🟡 par l'audit J25
LAST_CONSOLIDATED_MILESTONE:   J24 — HOS-254
BASELINE:                      b59ae24 (R-6 fermé) — 28a7ad7 pour R-3/R-4
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
```

`CURRENT_SECTION: §6` dit où porte le travail, pas qu'il soit fini. §6.1
est audité, §6.2 livré (HOS-257), A-15 fermé (HOS-258), §6.5 fermé par
R-3/R-4 (HOS-259) et la comptabilité physique par R-6 (HOS-260). Restent
§6.1 (capability routing) et §6.6, qu'aucune passe n'a ouverts.

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
3. **A-18** — trouvé en fermant R-6, et le plus gênant des trois :
   l'empreinte déclarée du rôle `swift` est **deux fois trop basse**
   (2,05 Gio annoncés, 4,33 mesurés) tandis que `vision` est exacte.
   C'est la table dont R-3 dérive la capacité.
4. **A-16** — trouvé en fermant A-15 : sur Linux sans `rocm-smi`, aucune
   sonde d'occupation ne répond et l'admission ne contraint rien.
   `/sys/class/drm/card*/device/mem_info_vram_used` a la bonne
   sémantique ; rien ici ne permet de l'exercer, et une sonde non
   mesurée reproduirait la faute que A-15 vient de corriger.

---

## OPEN_CRITICAL_ARCHITECTURAL_GAPS

| Gap | Classe | Section |
|---|---|---|
| ~~Contournement du pare-feu cloud (A-1)~~ — **fermé HOS-255** | security | §4 |
| Le pare-feu ignore `sk-or-v1-…` (A-10) | security | §4 |
| ~~Source d'admission = `/api/ps` (A-15)~~ — **fermé HOS-258** | architectural | §6 |
| Aucune sonde d'occupation sur Linux sans `rocm-smi` (A-16) | architectural | §6 |
| ~~Comptabilité VRAM/CPU par Run (R-6)~~ — **fermé HOS-260** | observability | §6 |
| Une empreinte déclarée mesurée 2,1× trop basse (A-18) | architectural | §6 |
| `_RegistreMissions.__len__` hydrate au milieu d'un test (A-19) | test | §3 |
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
   l'écart avant de commencer ;
4. travailler **dans le périmètre de la section active** ;
5. mettre à jour ce fichier **et** le statut de la section en fin de
   passe ;
6. ne jamais passer une section à 🟢 sans les preuves qu'exige §0 de la
   roadmap maître.
