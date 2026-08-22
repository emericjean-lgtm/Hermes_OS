"""Un modèle qui fabrique la dépendance qui lui manque (HOS-148).

Mesuré sur deux campagnes consécutives, la même pathologie :

* §9 d'un déroulé — `django/__init__.py`, `django/db/__init__.py`,
  `django/test.py` créés dans le workspace ;
* §6 du suivant — `flask/__init__.py`, en toutes lettres
  « Minimal Flask stub for tests », avec un `DummyClient` dépourvu de la
  moitié des méthodes que les tests appellent :

      AttributeError: 'DummyClient' object has no attribute 'post'

Le modèle ne dit pas « il me manque Flask ». Il **l'écrit**. Le projet
paraît alors complet, les imports se résolvent, et l'échec surgit à
l'exécution sous une forme qui n'a plus rien à voir avec sa cause.

## Pourquoi c'est pire qu'une dépendance manquante

Une dépendance absente échoue franchement, au premier import, avec son nom
dans le message. Un faux paquet la masque : il satisfait l'import, laisse
le projet se construire par-dessus, et ne cède qu'au moment où une méthode
non implémentée est appelée. La correction demande alors de défaire tout ce
qui s'est appuyé dessus.

C'est aussi un mensonge silencieux au sens de ce dépôt : le workspace
contient un `flask` qui n'est pas Flask.

## La règle

Un répertoire qui porte le nom d'un paquet tiers connu et contient un
`__init__.py` n'est jamais légitime dans un projet applicatif. Personne
n'appelle son propre module `django`, `flask` ou `numpy` — ces noms sont
pris, et les prendre casse l'import du vrai paquet.

La liste est **fermée et courte** à dessein. Une heuristique du genre « ce
nom ressemble à un paquet PyPI » refuserait des modules légitimes, et un
faux refus coûte autant qu'une fuite dans ce projet — il a déjà bloqué une
campagne entière sur un dossier parfaitement valide.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("hermes_os.mission.faux_paquets")

#: Les paquets qu'un modèle fabrique quand ils lui manquent. Tenue courte :
#: chaque entrée doit être un nom qu'aucun projet applicatif n'emploierait
#: pour un module à lui. Les deux premiers sont mesurés, les autres sont de
#: la même famille — des dépendances lourdes qu'un modèle est tenté de
#: simuler plutôt que de déclarer.
PAQUETS_TIERS = frozenset({
    "django", "flask", "fastapi", "starlette", "pydantic", "sqlalchemy",
    "alembic", "celery", "redis", "requests", "httpx", "aiohttp",
    "numpy", "pandas", "scipy", "torch", "tensorflow", "sklearn",
    "pytest", "unittest2", "boto3", "psycopg2", "pymongo", "jinja2",
})

#: Ce qu'on ne traverse pas : ni l'environnement où le vrai paquet est
#: légitimement installé, ni les caches.
IGNORES = frozenset({".venv", "venv", "env", "node_modules", "__pycache__",
                     ".git", "site-packages", ".tox", "build", "dist"})


def _fabrique(chemin: Path) -> bool:
    """Ce répertoire est-il un paquet Python portant un nom pris ?"""
    return (chemin.is_dir()
            and chemin.name.lower() in PAQUETS_TIERS
            and (chemin / "__init__.py").is_file())


def verdict(racine: str) -> Optional[dict]:
    """Le premier faux paquet du projet, ou None."""
    base = Path(racine)
    if not base.is_dir():
        return None
    for chemin in sorted(base.rglob("*")):
        if any(p in IGNORES for p in chemin.parts):
            continue
        if _fabrique(chemin):
            try:
                relatif = str(chemin.relative_to(base))
            except ValueError:  # pragma: no cover - hors racine
                relatif = chemin.name
            return {"paquet": chemin.name, "chemin": relatif}
    return None


def message(racine: str) -> str:
    """Ce qu'on dit à l'agent, ou "" s'il n'y a rien à dire."""
    faux = verdict(racine)
    if faux is None:
        return ""
    return _texte(faux["paquet"], faux["chemin"])


def message_du_fichier(chemin: str, racine: str) -> str:
    """Le même avertissement, **au moment où le fichier est écrit**.

    Une dépendance fabriquée coûte d'autant plus cher qu'elle est
    découverte tard : le projet se construit par-dessus, et la défaire
    demande de défaire tout ce qui s'y appuie. Dit à l'écriture du
    `__init__.py`, il ne coûte qu'un tour.
    """
    cible = Path(chemin)
    if cible.name != "__init__.py":
        return ""
    dossier = cible.parent
    if dossier.name.lower() not in PAQUETS_TIERS:
        return ""
    try:
        relatif = str(dossier.relative_to(Path(racine)))
    except (ValueError, OSError):
        relatif = dossier.name
    return _texte(dossier.name, relatif)


def _texte(paquet: str, chemin: str) -> str:
    saut = chr(10) * 2
    return (
        f"{saut}DÉPENDANCE FABRIQUÉE — {chemin}{chr(92)}__init__.py\n"
        f"`{paquet}` est un paquet tiers : ce répertoire masque le vrai et "
        f"casse son import. Un doublure écrite à la main ne porte jamais "
        f"toute l'API, et l'échec surgira plus tard sous une forme qui n'a "
        f"plus rien à voir avec sa cause.\n"
        f"Supprime ce répertoire. Si `{paquet}` est réellement nécessaire, "
        f"déclare-le comme dépendance du projet ; sinon, écris le code sans "
        f"lui."
    )
