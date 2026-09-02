"""Ce qu'un paquet de version doit être pour qu'on y touche (HOS-233).

## Mesuré avant d'écrire

`MiseAJour.appliquer(vers="1.1.0")` acceptait **n'importe quelle chaîne**
et n'ouvrait aucun paquet. Il n'y avait donc rien à valider, et rien qui
puisse être invalide : la mise à jour était aveugle par construction.

## Ce qu'est un paquet ici

Un **répertoire local** contenant l'arbre de code d'une version, plus un
`hermes.json` qui la nomme. Pas une archive : ouvrir une archive demande
de décider quoi faire d'un chemin absolu ou d'un `..` à l'intérieur, ce
qui est un problème de sécurité à part entière. Un répertoire déjà
extrait laisse cette décision à qui l'extrait.

Le téléchargement n'est pas ici non plus, et c'est la même règle : ce
module reçoit un chemin. D'où vient ce chemin est la question du canal de
distribution, qui n'existe pas.

## Ce qui est vérifié, et pourquoi

- **La version est lisible et sémantique.** Une version illisible dans un
  paquet n'est pas « ancienne » comme dans un état installé : c'est un
  paquet qu'on ne sait pas placer, et on ne l'installe pas.
- **Les racines annoncées existent.** Un paquet qui déclare remplacer
  `backend` sans le contenir viderait `backend`.
- **Aucune racine ne s'échappe.** Un `..` ou un chemin absolu dans la
  liste des racines écrirait hors de l'installation.
- **La compatibilité est explicite.** Voir `version.compatible`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from backend.maj.version import Version

#: Le fichier qui identifie un paquet. Nommé, pas deviné : un répertoire
#: quelconque ne doit pas pouvoir passer pour une version de Hermes.
NOM_MANIFESTE = "hermes.json"

#: Ce qu'un paquet remplace par défaut, faute de le dire. Les répertoires
#: de code livrés, et rien d'autre.
#:
#: `.git`, `.venv`, `node_modules` et `.env` n'y sont **jamais** : voir
#: `code.PRESERVE_EN_PLACE`, qui les protège explicitement.
RACINES_PAR_DEFAUT = ("backend", "frontend", "config", "data", "scripts")


class PaquetInvalide(ValueError):
    """Dit, jamais deviné.

    Un paquet qu'on ne comprend pas ne s'installe pas : l'installer « au
    mieux » remplacerait une partie du code par une autre partie d'une
    version inconnue, ce qui est le pire état possible.
    """


@dataclass(frozen=True)
class Paquet:
    """Une version prête à être installée, déjà sur le disque."""

    chemin: Path
    version: str
    #: Les répertoires que ce paquet remplace, relatifs à sa racine.
    racines: tuple[str, ...] = RACINES_PAR_DEFAUT
    #: La version installée la plus ancienne depuis laquelle ce paquet
    #: sait migrer. Vide = pas d'exigence déclarée.
    depuis_au_moins: str = ""
    notes: str = ""
    #: Ce que le manifeste disait, tel quel — pour l'audit.
    brut: dict = field(default_factory=dict)

    @property
    def semantique(self) -> Version:
        return Version.depuis(self.version)


def _sous(racine: Path, nom: str) -> Path:
    """Résoudre `nom` sous `racine`, ou refuser.

    Un `..` ou un chemin absolu dans la liste des racines écrirait hors
    de l'installation. C'est la même vérification de confinement que
    `empreinte.couvre` (HOS-224) et `aegis._is_within_path`, appliquée
    ici parce qu'un paquet est du contenu qu'on n'a pas écrit.
    """
    if not nom or nom.strip() in (".", "..", "/", "\\"):
        raise PaquetInvalide(f"racine de paquet invalide : {nom!r}")
    cible = (racine / nom).resolve()
    if cible != racine.resolve() and racine.resolve() not in cible.parents:
        raise PaquetInvalide(
            f"la racine {nom!r} sort du paquet — un paquet n'écrit que "
            "chez lui")
    return cible


def lire(chemin: str | Path) -> Paquet:
    """Ouvrir un paquet et le vérifier, ou lever.

    Toutes les vérifications sont faites ici, **avant** que quoi que ce
    soit soit sauvegardé : un paquet refusé ne doit rien coûter, et
    surtout ne pas laisser une sauvegarde orpheline derrière lui.
    """
    racine = Path(chemin)
    if not racine.is_dir():
        raise PaquetInvalide(f"{chemin!r} n'est pas un répertoire")

    manifeste = racine / NOM_MANIFESTE
    if not manifeste.is_file():
        raise PaquetInvalide(
            f"pas de {NOM_MANIFESTE} : un répertoire quelconque ne doit pas "
            "pouvoir passer pour une version de Hermes")

    try:
        donnees = json.loads(manifeste.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PaquetInvalide(f"{NOM_MANIFESTE} illisible : {exc}") from exc
    if not isinstance(donnees, dict):
        raise PaquetInvalide(f"{NOM_MANIFESTE} n'est pas un objet")

    version = str(donnees.get("version") or "").strip()
    if not version:
        raise PaquetInvalide("le paquet ne dit pas sa version")
    if Version.depuis(version).rang == (0, 0, 0):
        # Différent d'un **état installé** sans version, qui signifie
        # « très ancien » et doit pouvoir être mis à jour. Ici c'est un
        # paquet qu'on ne sait pas placer.
        raise PaquetInvalide(
            f"version de paquet illisible : {version!r} — on ne sait pas "
            "où la placer, donc on ne l'installe pas")

    brutes = donnees.get("racines") or list(RACINES_PAR_DEFAUT)
    if not isinstance(brutes, list) or not brutes:
        raise PaquetInvalide("« racines » doit être une liste non vide")

    racines: list[str] = []
    for nom in brutes:
        cible = _sous(racine, str(nom))
        if not cible.exists():
            raise PaquetInvalide(
                f"le paquet annonce remplacer {nom!r} et ne le contient pas "
                "— l'installer viderait ce répertoire")
        racines.append(str(nom))

    return Paquet(chemin=racine, version=version, racines=tuple(racines),
                  depuis_au_moins=str(donnees.get("depuis_au_moins") or ""),
                  notes=str(donnees.get("notes") or ""), brut=donnees)


__all__ = ["NOM_MANIFESTE", "Paquet", "PaquetInvalide", "RACINES_PAR_DEFAUT",
           "lire"]
