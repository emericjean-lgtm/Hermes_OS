# P-002 — Unified API Exposure & Legacy Route Migration

**Date** : 30 juillet 2026
**Nature** : exposition et migration. Aucune fonctionnalité nouvelle, aucun handler nouveau.

---

## Résultat

| Mesure | Avant | Après |
|---|---|---|
| Racines d'API utilisées par le Cockpit | **2** | **1** (`API_BASE`) |
| Chemins sous `/api/v1` | 188 | **248** |
| Endpoints hérités inaccessibles au Cockpit | **74** | **0** |
| Méthodes client visant une route morte | 2 | **0** |
| Actions destructives sans confirmation | 4 | **0** |
| Tests P-002 | — | **11/11** |

---

## STEP 1 — Inventaire des routes hors `/api/v1`

Produit par `scripts/validation/inventory_legacy.py` sur l'application réelle :
**64 chemins, 74 endpoints**, répartis en 23 modules.

| Module | Endpoints | Migrable | Note |
|---|---|---|---|
| `api.routes.git` | 9 | oui | `/git/branch`, `/git/commit`, `/git/status`… |
| `api.routes.memory` | 8 | **partiel** | 2 chemins disputés |
| `api.routes.workflows` | 7 | oui | |
| `api.routes.skills` | 6 | **partiel** | 2 chemins disputés |
| `api.routes.projects` | 5 | oui | |
| `api.routes.tasks` | 5 | oui | |
| `api.routes.files` | 4 | oui | protégé par `ALLOWED_PATHS` |
| `api.routes.snapshots` | 4 | oui | |
| `api.routes.logs` | 3 | oui | |
| `api.routes.security` | 3 | oui | `/security/approvals` |
| `api.routes.documents` | 2 | oui | |
| `api.routes.evolution` | 2 | oui | |
| `api.routes.system` | 2 | oui | |
| `api.routes.verification` | 2 | oui | `/verification/runners`, `/verification/run` |
| `chat`, `classify`, `messages`, `research`, `verify`, `vision`, `write` | 1 chacun | oui | |
| `main.health` | 1 | **disputé** | |

Table complète : `docs/release/legacy_routes.json`.

### Les cinq chemins disputés

Découverte centrale de cet inventaire : **ce ne sont pas des doublons**. Chaque
chemin porte deux implémentations *différentes*.

| Chemin | Historique | HOS |
|---|---|---|
| `/skills` | `api.routes.skills.list_skills` | `skills.routes.get_skills` |
| `/skills/{id}` | `api.routes.skills.get_skill` | `skills.routes.get_skill` |
| `/memory/search` | `api.routes.memory.search_memory` | `memory.routes.search_get` |
| `/memory/index` | `api.routes.memory.index_document` | `memory.routes.index_text` |
| `/health` | `main.health` | `sds.routes.sds_health` |

Les republier naïvement sous `/api/v1` aurait fait taire l'une des deux
implémentations **en silence** — FastAPI résout par ordre d'enregistrement.

---

## STEP 2 — Unification du namespace

`mount_legacy_under_api()` (dans `router_registry.py`, à côté de `mount_all`)
republie chaque routeur historique sous `/api/v1` en **réutilisant les mêmes
callables** : une seule implémentation par handler, servie sous plusieurs
chemins.

**70 routes republiées** sous `/api/v1`. **4 déviées** vers `/api/v1/legacy/…`
pour éviter le masquage :

```
/api/v1/legacy/skills
/api/v1/legacy/skills/{skill_id}
/api/v1/legacy/memory/search
/api/v1/legacy/memory/index
```

`/api/v1/legacy` n'est **pas une seconde base** : le préfixe reste `/api/v1`, le
client garde une racine unique.

### Ce qui reste hors `/api/v1`, et pourquoi

**62 chemins** restent servis à la racine — tous en doublon d'un équivalent
`/api/v1`. Ils sont conservés pour la compatibilité ascendante : les supprimer
casserait les clients existants et les outils MCP, sans rien gagner puisque le
handler est partagé. **Aucune capacité n'est joignable uniquement là.**

### Vérification d'absence d'écrasement

```
OK  /api/v1/skills         -> backend.skills.routes
OK  /api/v1/memory/search  -> backend.memory.routes
OK  /api/v1/health         -> backend.sds.routes
OK  /api/v1/agents         -> backend.agents.routes
OK  /api/v1/missions       -> backend.mission.routes
```

Et les routes héritées répondent sous le namespace canonique :

```
200  /api/v1/verification/runners
200  /api/v1/security/approvals
200  /api/v1/tasks
200  /api/v1/projects
200  /api/v1/legacy/skills
403  /api/v1/files?path=.      (sandbox ALLOWED_PATHS — comportement correct)
```

---

## STEP 3 — Alignement des contrats

Le contrôle automatisé (`check_contracts.py`) rapporte **0 divergence** sur les
41 méthodes vérifiables.

Corrections appliquées dans cette phase :

| Défaut | Réalité | Correctif |
|---|---|---|
| Base secondaire `LEGACY_BASE` dans le client | plus nécessaire après migration | supprimée, `verificationClient` passe par `API_BASE` |
| `PolicyRule.action` | l'API envoie `decision` + `priority` | type aligné ; **la colonne « décision » du Governance Center était vide depuis toujours** |
| `ApprovalRequest.action` / `.risk` | le type réel expose `operation` / `priority` | Policy Center aligné |

---

## STEP 4 — Actions désormais atteignables depuis le Cockpit

| Action | Center | Route |
|---|---|---|
| approuver / rejeter une demande | Policy, Governance | `POST /approval/{id}/approve`\|`reject` |
| pause / reprise / annulation | Execution | `POST /execution/{id}/…` |
| verrouiller / libérer / supprimer un espace | Workspace | `POST /workspace/{id}/lock`\|`release`, `DELETE` |
| **simuler / approuver / appliquer une évolution** | Evolution | `POST /evolution/{simulate,approve,apply}/{id}` |
| synchroniser le corpus | Alexandrie | `POST /alexandrie/sync` |
| recommander un modèle | Model Intelligence | `POST /models/recommend` |
| pause / reprise / annulation d'objectif | Autonomous | `POST /autonomous/{id}/…` |

---

## STEP 5 — Confirmation des actions irréversibles

`components/confirm-action.tsx` : un premier clic **arme** l'action et affiche ce
qu'elle va faire et sur quelle cible ; un second la déclenche.

Appliqué à :

* **Evolution** — `simulate`, `approve`, `apply` (`apply` marqué *destructive*) ;
* **Workspace** — suppression d'espace de travail.

Le composant documente explicitement qu'il **ne remplace pas** Policy / Security /
Approval : c'est une garde d'interface contre le déclenchement accidentel,
l'autorisation reste au backend. Un test le vérifie.

---

## STEP 6 — Contrat du Validation Center

`GET /verification/runners` est documenté et exploité : **7 runners, 4 familles**,
affichés avec filtres et recherche.

`POST /verification/run` **n'a pas de schéma** dans l'OpenAPI ni dans le code de
la route. Aucun bouton ne l'appelle. Le Center l'indique à l'écran :

> Le déclenchement d'une vérification n'est pas exposé ici : sa charge utile
> n'est pas décrite dans l'OpenAPI, et aucun bouton ne sera câblé sur un contrat
> deviné.

Deux tests verrouillent ce choix : l'un vérifie qu'aucun *appel* n'est émis,
l'autre que l'absence est signalée à l'utilisateur.

---

## STEP 7 — Exposition morte supprimée

| Élément | Constat | Action |
|---|---|---|
| `runtimeClient.select` | `POST /runtime/select` → **404** | méthode supprimée |
| `systemClient.version` | `GET /version` → **404** | méthode supprimée |
| `LEGACY_BASE` | racine secondaire | supprimée |
| `cockpit.test.ts` | garantissait la présence de `select` | assertion inversée : la méthode morte **ne doit plus exister** |

---

## STEP 8 — Tests

`tests/integration/test_p002_api_namespace.py` — **11/11**.

* toute route héritée est joignable sous `/api/v1` ;
* la migration n'a masqué aucun handler existant ;
* les chemins disputés vivent dans `/api/v1/legacy`, pas perdus ;
* le client n'a qu'une racine (`API_BASE`) ;
* aucune méthode client ne vise une route inexistante ;
* appliquer une évolution inexistante **échoue** au lieu de simuler un succès ;
* les actions destructives passent par `ConfirmAction` ;
* la confirmation ne se substitue pas à l'autorisation backend ;
* le Validation Center n'invente pas de charge utile.

Frontend : `tsc` 0 erreur · `vitest` 65/65.

---

## Écarts restants

1. **62 chemins encore servis à la racine.** Tous en doublon ; conservés pour la
   compatibilité. Les retirer est une décision de rupture, à planifier avec un
   cycle de dépréciation.
2. **`POST /verification/run` sans schéma.** Documenter sa charge utile
   débloquerait le bouton manquant du Validation Center — c'est du travail
   backend, hors périmètre P-002.
3. **`/api/v1/legacy` est une concession assumée.** L'alternative propre serait
   de renommer l'une des deux familles homonymes (`/skills` historique vs HOS),
   ce qui casse des clients ; à trancher séparément.

---

## Reproduire

```bash
python scripts/validation/inventory_legacy.py --out docs/release/legacy_routes.json
```

```bash
python -m pytest tests/integration/test_p002_api_namespace.py -q -p no:randomly
```

```bash
python scripts/validation/check_contracts.py --base http://127.0.0.1:8010/api/v1
```
