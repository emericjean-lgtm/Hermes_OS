"""La version du produit, à un seul endroit (HOS-232).

## Pourquoi ce fichier existe

Mesuré avant de l'écrire : **Hermes OS n'avait pas de version.** Le dépôt
en porte trois, et aucune ne désigne le produit — `SNAPSHOT_VERSION = 1`
pour le format des instantanés, `SCHEMA_VERSION = "1.0.0"` pour le graphe
de mission, `_KT_VERSION` pour une bibliothèque tierce.

On ne revient pas à une version qu'on n'a jamais nommée. Un retour
arrière suppose de savoir d'où l'on vient, et l'état installé doit le
dire lui-même — pas le code, qui aura déjà été remplacé quand la
question se posera.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

#: La version de Hermes OS. Sémantique, et incrémentée à la main : une
#: version dérivée d'un `git describe` vaudrait « inconnue » dans une
#: installation qui n'a pas de dépôt — c'est-à-dire dans toutes.
VERSION = "1.0.0"

#: Le fichier qui dit ce qui est **installé**, sous la racine d'état.
#: Sous la racine et non dans le dépôt : la question « d'où viens-je ? »
#: se pose au moment où le dépôt vient d'être remplacé.
NOM_FICHIER = "version.json"


@dataclass(frozen=True)
class Version:
    majeure: int = 0
    mineure: int = 0
    correctif: int = 0

    @classmethod
    def depuis(cls, texte: str) -> "Version":
        """Analyser une version, ou rendre 0.0.0.

        Rend `0.0.0` plutôt que de lever : une version illisible dans un
        état installé signifie « très ancienne ou abîmée », et une mise à
        jour doit pouvoir partir de là. Lever bloquerait exactement
        l'installation qui vient réparer.
        """
        morceaux = (texte or "").strip().split(".")
        nombres = []
        for morceau in morceaux[:3]:
            try:
                nombres.append(int("".join(c for c in morceau if c.isdigit())))
            except ValueError:
                nombres.append(0)
        while len(nombres) < 3:
            nombres.append(0)
        return cls(*nombres)

    def __str__(self) -> str:
        return f"{self.majeure}.{self.mineure}.{self.correctif}"

    @property
    def rang(self) -> tuple[int, int, int]:
        return (self.majeure, self.mineure, self.correctif)


def comparer(a: str, b: str) -> int:
    """-1, 0 ou +1. `a` est-il antérieur, égal ou postérieur à `b` ?"""
    ra, rb = Version.depuis(a).rang, Version.depuis(b).rang
    return (ra > rb) - (ra < rb)


def _fichier(racine: Path | None = None) -> Path:
    from backend.core.etat import racine as racine_d_etat

    return (racine or racine_d_etat()) / NOM_FICHIER


def lire_version_installee(racine: Path | None = None) -> str:
    """Ce que l'état dit de lui-même, ou une chaîne vide.

    Vide signifie « jamais installé par ce mécanisme » — une première
    mise à jour, ou une installation antérieure à HOS-232. Ce n'est pas
    une erreur, et le traiter comme telle refuserait la migration à
    toutes les installations existantes.
    """
    fichier = _fichier(racine)
    try:
        return str(json.loads(fichier.read_text(encoding="utf-8")).get("version")
                   or "")
    except Exception:
        return ""


def ecrire_version_installee(version: str, racine: Path | None = None) -> None:
    """Marquer l'état comme étant à cette version.

    Écrit **en dernier**, une fois la validation passée : un marqueur posé
    avant ferait croire à une mise à jour réussie qui ne l'est pas, et le
    retour arrière suivant repartirait du mauvais point.
    """
    fichier = _fichier(racine)
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(json.dumps({"version": version}, ensure_ascii=False,
                                  indent=2), encoding="utf-8")


__all__ = ["NOM_FICHIER", "VERSION", "Version", "comparer",
           "ecrire_version_installee", "lire_version_installee"]
