# HERMES OS — ROADMAP STATE

> **Lire ce fichier en premier.** Il tient en une page et dit où en est le
> projet. Le détail vit dans `docs/HERMES_OS_MASTER_ROADMAP.md`.
>
> Ce fichier est un **pointeur**, pas une preuve. Il ne doit jamais
> affirmer qu'une section est terminée : il renvoie au statut établi dans
> la roadmap maître, lequel exige des preuves mesurées.

```
CURRENT_SECTION:      §6 — Cognitive Scheduler / Resource Intelligence
CURRENT_SUBSECTION:   §6.1 — Capability routing
CURRENT_STATUS:       🟠 PLANNED

LAST_VALIDATED_SECTION:        §1, §2, §5  (🟢)
                               §3, §4 rétrogradées 🟡 par l'audit J25
LAST_CONSOLIDATED_MILESTONE:   J24 — HOS-254
BASELINE:                      528a0d37ac2fb323f338a68e325e69cdb192478e
LAST_AUDIT:                    J25 — audit global final indépendant
                               verdict 🟠 PARTIELLEMENT CONFORME
```

`CURRENT_SECTION: §6` signifie **« §6 est le prochain chantier »**, pas
« §6 est implémenté ». Aucune ligne de §6 n'existe aujourd'hui.

---

## NEXT_ACTION

**Avant d'ouvrir §6**, refermer les deux défauts P1 trouvés par l'audit
J25. Ce sont des corrections, pas des fonctionnalités, et elles touchent
des sections déclarées terminées :

1. **A-1** — deux chemins envoient un prompt à OpenRouter sans passer par
   le pare-feu de données (`base_agent.py:279`,
   `task_decomposer.py:489`). Bloque §4.
2. **A-2** — `security/derive_workspace.py` et
   `security/surveillance_flux.py` sont implémentés, testés, déclarés
   ✅ *Fait* au ROADMAP, et n'ont **aucun appelant**. Bloque §3.

Puis : phase de décision §6.1 (capability routing), sans écrire de code
avant que le contrat soit tranché.

---

## OPEN_CRITICAL_ARCHITECTURAL_GAPS

| Gap | Classe | Section |
|---|---|---|
| Contournement du pare-feu cloud (A-1) | security | §4 |
| Contrôles de sécurité non câblés (A-2) | security | §3 |
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
