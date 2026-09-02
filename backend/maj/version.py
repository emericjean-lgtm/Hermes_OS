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




# ── La compatibilité (HOS-233) ───────────────────────────────────────

#: La version installée la plus ancienne depuis laquelle ce code sait
#: reprendre. En dessous, la migration n'a pas été écrite et l'installer
#: quand même produirait un état que rien ne sait lire.
#:
#: `0.0.0` aujourd'hui : Hermes n'a jamais été distribué, donc toutes les
#: installations existantes sont antérieures au versionnement et doivent
#: pouvoir se mettre à jour. La faire monter est une décision, pas un
#: réglage — elle rend des installations non migrables.
MINIMUM_MIGRABLE = "0.0.0"


class IncompatibiliteVersion(RuntimeError):
    """La mise à jour est refusée, en le disant.

    Refusée et non « tentée quand même » : une mise à jour aveugle est
    exactement ce que le cahier interdit, et l'échec se verrait au
    redémarrage suivant plutôt qu'ici.
    """


def verifier_la_compatibilite(installee: str, cible: str, *,
                              depuis_au_moins: str = "",
                              minimum: str = MINIMUM_MIGRABLE) -> str:
    """Peut-on aller de `installee` à `cible` ? Rend une note, ou lève.

    Quatre cas, et chacun a été décidé :

    **Version installée inconnue** (chaîne vide) : on accepte. C'est une
    installation antérieure au versionnement — toutes celles qui existent
    aujourd'hui — et la refuser interdirait la première mise à jour à
    tout le monde.

    **Trop ancienne** : refusé. Sous `minimum`, ou sous le
    `depuis_au_moins` que le paquet déclare, la migration n'a pas été
    écrite.

    **Retour en arrière** : refusé par cette porte. Revenir à une version
    antérieure est un `restaurer()`, pas un `appliquer()` — le second
    n'a pas les migrations descendantes, et faire passer l'un pour
    l'autre laisserait un schéma neuf sous un code ancien.

    **Identique** : accepté, et dit. Réinstaller la même version est une
    réparation légitime.
    """
    if not (cible or "").strip():
        raise IncompatibiliteVersion("aucune version cible")

    v_cible = Version.depuis(cible)
    if v_cible.rang == (0, 0, 0):
        raise IncompatibiliteVersion(f"version cible illisible : {cible!r}")

    if not (installee or "").strip():
        return ("installation antérieure au versionnement — acceptée, "
                "c'est le cas de toutes celles qui existent aujourd'hui")

    v_installee = Version.depuis(installee)

    plancher = Version.depuis(depuis_au_moins or minimum)
    if v_installee.rang < plancher.rang and plancher.rang > (0, 0, 0):
        raise IncompatibiliteVersion(
            f"version installée {installee} antérieure au minimum "
            f"{plancher} — la migration depuis là n'a pas été écrite")

    if v_cible.rang < v_installee.rang:
        raise IncompatibiliteVersion(
            f"{cible} est antérieure à {installee} : revenir en arrière "
            "est une restauration, pas une mise à jour — cette porte n'a "
            "pas les migrations descendantes")

    if v_cible.rang == v_installee.rang:
        return f"réinstallation de {cible}"
    return f"{installee} → {cible}"



__all__ = ["IncompatibiliteVersion", "MINIMUM_MIGRABLE", "NOM_FICHIER",
           "VERSION", "Version", "comparer", "ecrire_version_installee",
           "lire_version_installee", "verifier_la_compatibilite"]
