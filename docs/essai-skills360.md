# Skills360 Industry lancé sur l'orchestrateur autonome — mesure du 15 août 2026

Le cahier de HOS-119 était écrit par moi, court, et nommait les fichiers à
produire. Celui-ci est le vrai : 23 Ko, 40 sections, écrit par
l'utilisateur, et il **refuse de nommer une stack** (§5 : « l'architecture
technique n'est PAS définie par ce document »).

Une seule étape lancée : le modèle d'identité des §6 et §7 — la contrainte
que le document répète le plus. Workspace = une **copie** du dossier réel,
spécification comprise. Le projet de l'utilisateur n'a pas été touché.

Workspace conservé : `C:\Users\emeri\AppData\Local\Temp\skills360_pejvrpuh`

## Le verdict brut

| | |
|---|---|
| Statut rapporté | `completed`, `success: True`, 7/7 tâches |
| Durée | **2 186 s** (36 min) |
| Fichiers produits | **12** (hors `__pycache__` et les 3 fichiers d'amorce) |
| Tests du livrable | **ne compilent pas** — `pytest` sort en code 2 |
| Fidélité §4/§37 | **28 marqueurs `À DÉCIDER`**, correctement placés |

## Ce qui marche, et qui ne marchait pas il y a deux jours

La spécification a été **lue sur le disque**, pas devinée. Les 12 fichiers
existent. Le départ de HOS-119 était *zéro fichier* avec un rapport
affirmatif ; ce n'est plus le régime.

Et surtout, la partie qu'on pouvait croire hors de portée d'un modèle local
est la mieux tenue : **le §4 est respecté**. 28 `À DÉCIDER` écrits, et les
notions que le §37 déclare ouvertes — cardinalités, suppression,
désactivation, utilisateurs sans Employee — se trouvent dans les documents,
là où elles doivent être, pas codées en dur. Un fichier va jusqu'à écrire
« la spec ne précise pas la contrainte sur `auth_uid` ».

Une réserve honnête : `tests/test_auth_models.py:105` étiquette
`assert employee.auth_uid is None` par « cardinalité optionnelle ».
L'assertion porte sur une valeur par défaut de dataclass, pas sur une règle
métier — mais le libellé transforme un `À DÉCIDER` en règle nommée. C'est
la frontière exacte que le §32 interdit de franchir.

## Le défaut dominant : les tâches ne se voient pas

7 tâches ont produit **quatre fois le même livrable** :

| Concept | Fichiers produits |
|---|---|
| Modules d'identité | `auth.py`, `auth_models.py`, `auth_user_employee.py`, `identity_models.py` |
| Documents de décision | `DECISION.md`, `DESIGN_DECISIONS.md`, `IDENTITY_MODEL_DECISIONS.md`, `docs/model_identity_documentation.md` |
| Tests | `test_auth_user_employee.py`, `test_identity.py`, `test_identity_extended.py`, `tests/test_auth_models.py` |

Les quatre modules définissent chacun `Auth`, `User`, `Employee`.

Ce n'est **pas** le défaut corrigé par HOS-119. Celui-là écrivait deux fois
le même fichier parce que le modèle préfixait le chemin ; il est corrigé.
Celui-ci est autre : chaque tâche ré-implémente le livrable entier depuis
zéro, sans voir ce que la précédente a écrit. Un cahier des charges réel
n'est pas une addition de tâches indépendantes — la tâche 4 doit *importer*
ce que la tâche 2 a défini.

C'est le blocage principal pour exécuter un vrai cahier des charges, et il
n'est pas dans la liste de dette actuelle.

## Le livrable ne compile pas

`test_identity_extended.py:81` ouvre une docstring par `"""` et la ferme
par `"` :

```
SyntaxError: unterminated triple-quoted string literal (detected at line 98)
```

`pytest` s'arrête à la collecte, code 2. **Vérifié sur les octets bruts** :
le fichier est de l'UTF-8 valide, le défaut vient du modèle et non de
l'encodage — la règle « ni un échec sur parole » a été appliquée avant de
conclure.

## Le filet de HOS-119 n'a jamais tourné

C'est le résultat qui compte le plus, et c'est exactement la forme de la
leçon centrale du projet.

`_verdict_des_tests`, construit en HOS-119 pour attraper précisément ce cas
— « les fichiers existent, les tests ne passent pas, la mission dit 6/6 » —
a rendu :

```json
{"ran": false, "runner": "pytest", "passed": false, "exit_code": null,
 "reason": "verification_run needs autonomy level 'high' to auto-allow; current level is 'medium'."}
```

`config/security.yaml` livre `autonomy_level: medium` (ligne 8) et exige
`min_autonomy_for_auto_allow: high` pour `verification_run`. Le filet est
donc **inerte au niveau par défaut**.

L'instrument est honnête : il dit « je n'ai pas mesuré » plutôt que
« ça passe ». Le problème est ailleurs — **le rapport que l'utilisateur
voit ne le répète pas**. `MissionReport` porte bien un champ
`verification` (`mission_models.py:192`), mais le rapport d'objectif
autonome, celui que lit l'onglet Autonomous, n'y fait aucune référence :
il affiche `success: True`, seul.

Un `success: True` posé sur un verdict « non mesuré » est exactement ce que
ce dépôt s'interdit. La correction n'est pas de baisser le seuil de sécurité
— faire tourner le code d'un projet tiers sans surveillance au niveau par
défaut est une vraie décision — mais de faire **remonter les trois états**
déjà distingués en interne : *non mesuré* / *passé* / *échoué*.

## La cause mesurée de la duplication

HOS-105 avait construit exactement le mécanisme qui manquait :
`_upstream_results_for` doit donner à une tâche ce que ses dépendances ont
produit. Il n'a **jamais fonctionné sur le DAG**.

```python
# service_registry.py:541 — lit task_id EN PREMIER
node_id = getattr(task, "task_id", "") or getattr(task, "node_id", "") or ""

# node_execution.py:57 — la production préfixe
task_id=f"{node.node_id}-task",
```

`"n2-task"` ne correspond à aucun `node_id` du graphe, la recherche rend
`None`, et la section « Already done by the tasks yours depends on » n'est
jamais ajoutée au prompt. Mesuré, pas déduit :

| tâche | `task_id` | `_upstream_results_for` |
|---|---|---|
| construite comme en production | `n2-task` | **`None`** |
| double du test `_Task` | `n2` | `- Definir Auth : ecrit identity_models.py…` |

Le test passait parce que son double fabrique un identifiant que la
production ne produit jamais. `_mission_brief_for`, lui, fonctionne : il
n'a besoin que du `mission_id`.

Chaque tâche repartait donc de zéro — d'où quatre modules d'identité
parallèles.

## Les deux relancements

### Run 2 — une régression qui a révélé un défaut plus vieux

Après les trois correctifs : **1/7 tâches, zéro fichier, `failed`, 878 s**.
Un seul nœud a signalé une erreur — `runtime 'default' timed out after 180s`
— et les cinq suivants ont été bloqués en cascade.

La cause est arithmétique. `_chat_with_tools_for` enchaîne jusqu'à 12
inférences (`mission_max_tool_rounds`), chacune suivie d'une lecture ou
d'une écriture, et la boucle **entière** était enveloppée par les 180 s de
`_timeout_s` : 15 s par tour, sur un matériel mesuré entre 13 et 89 tok/s.

Cette leçon avait déjà été apprise. Six lignes au-dessus de
`_HERMES_AGENT_TIMEOUT_S = 900` on lit qu'« une tâche triviale à un seul
fichier prend déjà 37-57 s » et que le plafond de 180 s produisait « une
mission qui tournait 12 minutes et terminait 0/5 tâches ». Le correctif
n'avait jamais été appliqué au chemin frère, qui fait la même chose :
plusieurs tours sur du matériel local.

**Pourquoi le run 1 passait**, lui : sans contexte amont le modèle n'allait
rien lire et écrivait son module directement, en peu de tours. La
correction du contexte l'a poussé à faire le travail correctement, et le
travail correct ne tenait pas dans le budget. La réussite du run 1 et sa
duplication étaient la même chose — sept tâches paresseuses.

### Run 3 — après correction du budget

| | run 1 | run 3 |
|---|---|---|
| Tâches | 7/7 | 7/7 |
| Durée | 2 186 s | **1 084 s** |
| Fichiers produits | 12 | **5** |
| Modules d'identité | **4** | **1** |
| Documents de décision | 4 | 2 |
| Fichiers de tests | 4 | 2 |
| Erreur de syntaxe | oui | **non** |

**La duplication du code est résolue** : un seul `identity_model.py`
définissant `Auth`, `User`, `Employee`. Le contexte amont, une fois qu'il
arrive vraiment, suffit à faire converger les tâches sur un module unique.

### Ce qui reste, et ce que ça désigne

Les deux fichiers de tests portent le **même nom de base**, ce qui suffit à
faire échouer `pytest` à la collecte (`import file mismatch`). Lancés
séparément :

| fichier | résultat |
|---|---|
| `test_identity_model.py` | 6 passent, 1 échoue (une assertion sur `__repr__`) |
| `tests/test_identity_model.py` | 1 passe, 4 échouent |

Et l'erreur est parlante :

```
TypeError: User.__init__() missing 1 required positional argument: 'email'
```

Ce second fichier appelle `User("user_001", "auth_uid_123")`. Il a été écrit
**sans jamais lire le module** qu'il teste. La duplication n'a pas disparu :
elle s'est déplacée du code vers les tests.

C'est exactement ce que l'axe `expected_outputs` doit traiter — le
planificateur remplit déjà ce champ sur chaque nœud, le sérialiseur
l'expose, et rien ne le lit à l'exécution. Une mission qui déclare « le
livrable est `identity_model.py` et `test_identity_model.py` » rend
impossible qu'une tâche invente un second fichier de tests contre une API
imaginée. On sait désormais que c'est le prochain levier, au lieu de le
supposer.

Réserve de méthode : **un run n'est pas une mesure**. L'écart est assez
large (12 → 5 fichiers, 4 → 1 module, moitié moins de temps) pour être
rapporté, pas pour être tenu pour une constante.

Une note sur l'instrument : le compte de `À DÉCIDER` passe de 28 à 5, mais
il faut se méfier de ce chiffre — le run 2, qui n'a produit **aucun**
fichier, en affichait 24, tous venant de `PROJECT_SPEC.md` lui-même. Le
comptage inline de `essai_skills360.py` inclut les fichiers d'amorce ;
seul celui de `mesurer_s360.py` les exclut. Les 28 et les 5 sont
comparables entre eux, le 24 ne l'est avec rien.

### Run 4 — avec le manifeste des livrables

| | run 1 | run 3 | run 4 |
|---|---|---|---|
| Tâches | 7/7 | 7/7 | **5/5** |
| Durée | 2 186 s | 1 084 s | **566 s** |
| Fichiers produits | 12 | 5 | **3** |
| Modules d'identité | 4 | 1 | 1 |
| Documents | 4 | 2 | **1** |
| Fichiers de tests | 4 | 2 | **1** |
| Tests du livrable | ne compilent pas | code 2 (collision) | **code 0, 6 passent** |

Trois fichiers, exactement les trois demandés : `identity_model.py`,
`tests/test_identity_model.py`, `docs/identity_design.md`. Et `pytest` sort
en 0.

**L'amélioration est attribuable au manifeste, pas au hasard** — le rapport
le prouve :

```json
"manifeste": {"declares": 3, "manquants": [], "nombre_manquants": 0, "tenu": true}
```

Trois livrables déclarés par les tâches elles-mêmes, trois présents. Le
champ `expected_outputs`, câblé de bout en bout sur du vide depuis toujours,
porte enfin quelque chose.

Effet de bord non anticipé : la décomposition est passée de 7 à 5 tâches.
Demander « quels fichiers vas-tu écrire ? » semble rendre le planificateur
plus économe — une tâche qui ne peut nommer aucun livrable propre a moins de
raisons d'exister. Une observation sur un run, pas une loi.

### Le défaut que ce run a révélé dans mon propre correctif

Le rapport annonçait `qualite: "verifiee"` au-dessus de :

```json
"tests": {"ran": false, "reason": "verification_run needs autonomy level
                                   'high' to auto-allow; current level is 'medium'."}
```

Le disque avait changé, le manifeste tenait — les tests du livrable
n'avaient **pas** tourné. On avait remplacé un `success: True` trompeur par
un `verifiee` qui l'était tout autant.

Un quatrième état a été ajouté : **`partielle`**. `verifiee` exige désormais
que les tests aient réellement tourné et réellement passé ; tout ce qui a
été constaté sans eux est `partielle` — c'est vrai, c'est utile, et ça ne se
fait pas passer pour davantage.

Le rabattre sur `non_mesuree` aurait jeté une information vraie : le
manifeste tenu et le disque changé sont de vraies mesures. Elles ne valent
simplement pas les tests.

## Ce que cet essai établit

- L'orchestrateur **exécute** un vrai cahier des charges, lit sa
  spécification, et en respecte les règles de non-invention.
- Il ne **compose** pas encore : sept tâches produisent sept solutions
  parallèles au lieu d'une.
- Le contrôle qualité existe mais ne s'arme pas tout seul, et son silence
  se lit comme un succès.

Trois défauts, aucun trouvé en relisant du code.
