"""Le SQL livré s'exécute-t-il ? (HOS-170)

Mesuré sur le projet livré par la campagne Skill360, en exécutant pour de
bon les six migrations contre une base en mémoire :

    0001_create_employee_assignment.py      OK
    0002_create_audit_log.py                ÉCHEC : AUTOINCREMENT is only
                                            allowed on an INTEGER PRIMARY KEY
    20230901_create_position_training.py    ÉCHEC : unrecognized token: "#"
    20230910_create_position_skill.py       aucun SQL
    20230915_create_employee_assignment.py  OK
    add_position_skill.py                   aucun SQL

Deux migrations sur six ne s'exécutent pas, et **aucun test ne les
touche** : les 74 tests verts du projet ne lancent jamais une migration.
La section a donc été déclarée vérifiée au-dessus d'un schéma qui ne se
crée pas.

C'est la même famille que `imports_relatifs` : une faute que le langage
refuse, invisible tant que personne ne la fait tourner.

## Le piège du faux positif, et comment il est écarté

Exécuter du SQL PostgreSQL contre SQLite produirait des erreurs qui ne sont
pas des fautes — `SERIAL`, `JSONB`, `NOW()` n'existent pas ici. Signaler ces
cas coûterait des sections bloquées à tort, et ce projet a mesuré que cinq
de ses huit défauts d'instrumentation produisaient de faux échecs.

Ne sont donc retenues que les erreurs **fautives dans tout dialecte** :

* `unrecognized token` — une faute lexicale, refusée par tout moteur ;
* `incomplete input` — une instruction tronquée, idem ;
* `AUTOINCREMENT is only allowed…` — le mot-clé n'existe qu'en SQLite, et
  il y est mal employé ; ailleurs il est inconnu. Faux dans les deux cas.

**`syntax error` en est délibérément absent**, et c'est un renoncement
mesuré : `CREATE TABLE t (a TEXT DEFAULT NOW())` est du PostgreSQL valide
que SQLite refuse par « near "(" : syntax error ». Le retenir signalerait
donc du SQL correct. Le prix est de laisser passer un `CREATE TABL` mal
orthographié — une faute plus rare qu'une différence de dialecte, et que le
premier déploiement révèle de toute façon.

Tout le reste — type inconnu, fonction inconnue, table absente — est ignoré
pour la même raison.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Iterable, Optional

IGNORES = {"__pycache__", ".venv", "venv", "node_modules", ".git", ".hermes",
           ".pytest_cache", "build", "dist"}

#: Les erreurs qui sont des fautes quel que soit le moteur visé.
FAUTES = (
    "unrecognized token",
    "autoincrement is only allowed",
    "incomplete input",
)

#: Le SQL d'une migration Python vit dans une chaîne de module. On accepte
#: les noms usuels plutôt qu'un seul : `sql`, `SQL`, `up`, `UP`.
_CHAINE_SQL = re.compile(
    r"^(?:sql|SQL|up|UP|DDL|ddl)\s*=\s*(?:r?)(\"\"\"|''')(.*?)\1",
    re.S | re.M)


def sql_du_fichier(chemin: Path) -> str:
    """Le SQL que ce fichier porte, ou "" s'il n'en porte pas."""
    try:
        source = chemin.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if chemin.suffix.lower() == ".sql":
        return source
    trouve = _CHAINE_SQL.search(source)
    return trouve.group(2) if trouve else ""


def faute_du_sql(sql: str) -> str:
    """Le motif de refus, ou "" si ce SQL est acceptable.

    Chaque fichier part d'une base **neuve** : une migration qui référence
    une table créée par la précédente échouerait sinon, et l'ordre des
    migrations n'est pas ce qu'on vérifie ici.
    """
    if not sql.strip():
        return ""
    try:
        sqlite3.connect(":memory:").executescript(sql)
    except sqlite3.Error as erreur:
        motif = str(erreur)
        if any(f in motif.lower() for f in FAUTES):
            return motif
    return ""


def verdict(racine: str,
            touches: Optional[Iterable[str]] = None) -> Optional[dict]:
    """La première migration livrée qui ne s'exécute pas, ou None.

    `touches` restreint l'examen aux fichiers de la mission, pour la même
    raison que le garde des livrables vides : reprocher à une section le
    SQL d'une autre serait un faux échec sans issue.
    """
    base = Path(racine)
    if not base.is_dir():
        return None

    if touches is not None:
        candidats = sorted(
            c for c in (base / str(r).replace("\\", "/") for r in touches)
            if c.suffix.lower() in (".sql", ".py") and c.is_file())
    else:
        candidats = sorted(
            list(base.rglob("*.sql")) + list(base.rglob("*.py")))

    for fichier in candidats:
        if any(p in IGNORES for p in fichier.parts):
            continue
        sql = sql_du_fichier(fichier)
        if not sql:
            continue
        motif = faute_du_sql(sql)
        if motif:
            return {"fichier": fichier.relative_to(base).as_posix(),
                    "motif": motif}
    return None


def message(racine: str) -> str:
    """Ce qu'on dit à l'agent, ou "" s'il n'y a rien à dire."""
    faute = verdict(racine)
    if faute is None:
        return ""
    return (
        f"\n\nSQL QUI NE S'EXÉCUTE PAS — {faute['fichier']}\n"
        f"Le moteur le refuse : « {faute['motif']} ».\n"
        f"Un schéma qui ne se crée pas n'est pas un livrable, et aucun test "
        f"de ce projet ne lance les migrations — l'erreur ne se verrait "
        f"qu'au premier déploiement. Corrige le SQL, puis exécute-le pour "
        f"de bon avant de conclure."
    )
