# Cohérence du namespace d'API

## La règle

**Toute capacité de Hermes est joignable sous `/api/v1`.** Le client du Cockpit
ne connaît qu'une seule constante de base :

```ts
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
```

Il n'existe aucune racine secondaire. Un test le vérifie
(`test_frontend_uses_a_single_api_root`).

## Pourquoi il y en avait deux

Hermes a grandi en deux couches :

* l'**API Hermes-Ollama** d'origine (`backend/api/routes/*`) — `/chat`, `/files`,
  `/git`, `/tasks`, `/projects`, `/memory`, `/skills`… servie à la racine ;
* les **sous-systèmes Hermes OS** (`backend/{mission,agents,memory,skills,…}/routes.py`)
  montés sous `/api/v1` par le composition root.

Le Cockpit ne parlait qu'à la seconde. La première — 74 endpoints — lui était
donc structurellement inaccessible, quelle que soit la qualité de son
implémentation.

## Ce que fait la migration

`mount_legacy_under_api()` republie chaque routeur historique sous `/api/v1` en
**réutilisant les mêmes callables**. Il n'existe toujours qu'une implémentation
de chaque handler, servie sous plusieurs chemins.

Les montages à la racine sont **conservés** : les supprimer casserait les clients
existants et les outils MCP, sans rien apporter puisque le handler est partagé.

## Le cas des chemins disputés

Cinq chemins portent **deux implémentations différentes** :

| Chemin | Implémentation historique | Implémentation HOS |
|---|---|---|
| `/skills` | `api.routes.skills.list_skills` | `skills.routes.get_skills` |
| `/skills/{id}` | `api.routes.skills.get_skill` | `skills.routes.get_skill` |
| `/memory/search` | `api.routes.memory.search_memory` | `memory.routes.search_get` |
| `/memory/index` | `api.routes.memory.index_document` | `memory.routes.index_text` |
| `/health` | `main.health` | `sds.routes.sds_health` |

Ce ne sont pas des doublons : ce sont deux fonctionnalités homonymes. Les monter
au même endroit ferait taire l'une des deux en silence — FastAPI résout par
ordre d'enregistrement, premier arrivé premier servi.

Elles sont donc servies sous **`/api/v1/legacy/…`**. Ce n'est pas une seconde
base : le préfixe reste `/api/v1`, le client n'a toujours qu'une racine, et rien
n'est masqué. `test_migration_did_not_shadow_any_existing_handler` verrouille la
propriété : `/api/v1/skills` doit rester servi par `backend.skills.routes`.

## Ajouter une route

1. Écrire le routeur dans son sous-système.
2. Le déclarer dans `SERVICE_SPECS` avec son `route_binder`.

Le composition root le monte sous `/api/v1`. Ne jamais ajouter de routeur à
`_LEGACY_ROUTERS` : cette liste est historique et n'a pas vocation à grandir.

## Ce qui reste hors du namespace

Rien, fonctionnellement. Les chemins encore servis à la racine ont tous leur
équivalent sous `/api/v1` ; ils subsistent uniquement pour la compatibilité
ascendante. `test_every_legacy_route_is_reachable_under_api_v1` échoue si une
capacité redevient joignable *uniquement* hors du namespace.

Depuis le nettoyage de dette technique du 2026-07-31, ces montages racine
portent `deprecated=True` (`backend/main.py`, `app.include_router(module.router,
deprecated=True)`) : Swagger UI les affiche barrés, et tout outil qui lit
`openapi.json` peut filtrer sur `deprecated`. Comportement identique,
signal explicite en plus — premier pas d'un cycle de dépréciation sans
casser personne. Les mêmes routeurs republiés sous `/api/v1` par
`mount_legacy_under_api()` restent volontairement non dépréciés : c'est la
façon actuelle et canonique de les atteindre.
