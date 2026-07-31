# P-001 — Missing Centers

**Date** : 30 juillet 2026
**Nature** : exposition de capacités backend existantes. Aucune logique métier ajoutée.
**Règle** : aucune donnée simulée, aucun mock, aucun TODO. Une API absente est documentée, jamais inventée.

---

## Résultat

| Mesure | Avant | Après |
|---|---|---|
| Centers dans le Cockpit | 17 | **25** |
| Centers utilisant uniquement des données réelles | 17 | **25** |
| Centers en panne ou vides | 0 | **0** |
| Actions backend inaccessibles depuis le Cockpit | 36 | **34** |
| Divergences de contrat TS ↔ API | 0 | **0** (41 méthodes vérifiées) |

`tsc --noEmit` : 0 erreur · `npm run build` : succès, 14 pages · `vitest` : 65/65.

---

## 1. Les huit Centers créés

Chacun comporte statistiques, tableau principal, filtres, recherche, états de
chargement / vide / erreur, et les actions réellement exposées par le backend.

| Center | API utilisées | Données observées en direct | Actions câblées |
|---|---|---|---|
| **Health** | `/system/health`, `/health`, `/system/assembly` | **34 sous-systèmes, 23 sains, 11 sans télémétrie** | — (lecture seule côté backend) |
| **Monitoring** | `/runtime/resources`, `/runtime/events`, `/runtime/intelligence/scores`, `/runtime/resources/allocations`, `/system/statistics`, WebSocket `/ws` | **GPU AMD Radeon RX 6800**, VRAM, RAM, allocations | — |
| **Workspace** | `/workspace` (+ `{id}`, `/status`, `/artifacts`) | 0 espace (aucune mission n'en a réclamé) | **verrouiller · libérer · supprimer** |
| **Knowledge Graph** | `/memory/graph`, `/alexandrie/graph` | nœuds et arêtes réels (0 au repos) | — |
| **Execution** | `/execution`, `/execution/statistics` | compteurs du planificateur et du validateur | **pause · reprise · annulation** |
| **Policy** | `/policy/rules`, `/approval`, `/audit` | **10 règles, 4 catégories** | **approuver · rejeter** |
| **Validation** | `/verification/runners`, `execution_engine.validator` | **7 runners, 4 familles** | — (voir §3) |
| **Alexandrie** | 19 routes `/alexandrie/*` | **service HORS LIGNE**, message explicite | **synchroniser**, recherche hybride |

Les huit sont accessibles depuis la barre latérale, au même style que les
existants (socle commun `center-scaffold.tsx`).

### Un état d'erreur qui dit la vérité

`/alexandrie/health` répond `healthy:false` (port 8200 injoignable). Le Center
l'affiche tel quel :

> Alexandrie est injoignable — HTTPConnectionPool(host='localhost', port=8200)…
> Les compteurs ci-dessous sont donc vides **parce que le service ne répond pas,
> pas parce que le corpus est vide**.

Un « 0 document » silencieux aurait laissé croire à un corpus vide.

---

## 2. Corrections de contrat trouvées en chemin

Construire ces Centers a révélé trois dérives supplémentaires entre TypeScript,
l'OpenAPI et le backend :

| Défaut | Réalité | Correctif |
|---|---|---|
| `PolicyRule.action: "ALLOW"\|"DENY"\|"REVIEW_REQUIRED"` | l'API envoie `decision: "review_required"` et `priority: number` ; **ni `action` ni `description` n'existent** | type aligné sur la charge utile réelle |
| **Governance Center** affichait `rule.action` | champ inexistant → badge systématiquement vide | lit `rule.decision`, palette en minuscules |
| `ApprovalRequest` : j'avais supposé `action` / `risk` | le type réel expose `operation` / `priority` | Policy Center aligné sur le type réel |

Le premier est un vrai bug utilisateur : la colonne « décision » du Governance
Center était vide depuis toujours.

---

## 3. Ce qui n'a pas été exposé, et pourquoi

**Déclencher une vérification.** `POST /verification/run` existe mais sa charge
utile n'est décrite ni dans l'OpenAPI ni dans le code de la route. Le Validation
Center ne propose donc **aucun bouton « lancer »** : câbler un bouton sur un
contrat deviné produirait un 422 à chaque clic. Le Center le dit explicitement à
l'écran.

**34 actions restent inaccessibles** :

| Groupe | Actions | Raison |
|---|---|---|
| **legacy (non préfixé)** | **21** | Routes servies hors `/api/v1` (`/security/approvals`, `/verify`, `/files`, `/git/*`…). Le client frontend est construit autour de `API_BASE = …/api/v1` ; les atteindre demande une seconde base, décision d'architecture qui dépasse « exposer l'existant ». |
| collaboration | 5 | `broadcast`, `delegate`, `review`… supposent un modèle d'interaction multi-agent qui n'a pas d'écran d'origine. |
| evolution | 3 | `simulate/{id}`, `apply/{id}`, `rollback/{id}` — actions à effet de bord sur le code ; à exposer avec une confirmation dédiée. |
| planner, skills, workspace, security, alexandrie | 1 chacune | Charges utiles non documentées (`/planner/plan/template/{id}`, `/skills/distribute`, `/security/permissions/grant`, `/alexandrie/sync/mark-outdated`) ou variantes d'actions déjà exposées. |

---

## 4. Les derniers écarts avant « 100 % complet »

1. **Les 21 routes héritées non préfixées** sont le plus gros bloc. Tant qu'elles
   coexistent avec `/api/v1`, une partie du produit reste hors de portée du
   Cockpit. À trancher : les migrer sous `/api/v1` ou donner au client une base
   secondaire assumée.
2. **`POST /verification/run` sans contrat documenté** — un schéma OpenAPI
   suffirait à débloquer le bouton manquant du Validation Center.
3. **Alexandrie hors ligne** sur cette machine : le Center est complet mais ne
   pourra être validé sur données réelles qu'avec le service démarré (port 8200).
4. **Trois actions Evolution** (`simulate`, `apply`, `rollback`) méritent un
   parcours de confirmation avant exposition : elles modifient le système.

---

## 5. Vérification

Parcours réel des 25 Centers dans le navigateur, backend sur `:8010`, Cockpit sur `:3010`.

```
Execution    ok (447c, 4 boutons, 1 champ)
Workspace    ok (276c, 3 boutons, 1 champ)
Knowledge    ok (478c, 1 bouton,  1 champ)
Alexandrie   ok (658c, 2 boutons, 2 champs)  → HORS LIGNE signalé
Policy       ok (863c, 5 boutons, 1 champ)   → 10 règles, 4 catégories
Validation   ok (996c, 5 boutons, 1 champ)   → 7 runners, 4 familles
Monitoring   ok (572c, 5 boutons, 1 champ)   → GPU AMD Radeon RX 6800
Health       ok (1733c, 4 boutons, 1 champ)  → 34 sous-systèmes, 23 sains
```

Aucune panne, aucun appel réseau en échec, aucun `TODO`, aucune constante
`MOCK_*` : le balayage du dépôt en confirme zéro dans `frontend/src`.

```bash
python scripts/validation/check_contracts.py --base http://127.0.0.1:8010/api/v1
```

```bash
cd frontend && npx tsc --noEmit && npm run build && npx vitest run
```
