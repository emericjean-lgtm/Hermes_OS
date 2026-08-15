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

## Ce que cet essai établit

- L'orchestrateur **exécute** un vrai cahier des charges, lit sa
  spécification, et en respecte les règles de non-invention.
- Il ne **compose** pas encore : sept tâches produisent sept solutions
  parallèles au lieu d'une.
- Le contrôle qualité existe mais ne s'arme pas tout seul, et son silence
  se lit comme un succès.

Trois défauts, aucun trouvé en relisant du code.
