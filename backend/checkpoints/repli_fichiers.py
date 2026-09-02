"""Le point de reprise quand il n'y a pas de dépôt git (HOS-223).

## Pourquoi un repli, et pas seulement git

Un workspace n'est pas toujours un dépôt. Un dossier de travail créé
pour l'occasion, un projet que l'utilisateur n'a pas versionné, un
montage vidéo — la production du 30 août tournait dans un dossier sans
`.git`. Refuser le point de reprise dans ces cas reviendrait à ne
protéger que ceux qui étaient déjà protégés.

## Ce qui est repris d'Agent OS, et ce qui manquait

Leur repli copie les fichiers avec un **manifeste de contenu**, et
vérifie l'intégrité en **re-hachant** à la restauration. Les deux comptent
et sont repris : une copie sans manifeste ne sait pas ce qu'elle devait
contenir, et un manifeste jamais revérifié n'est qu'une déclaration.

Deux ajouts, tirés de ce dépôt :

**Les répertoires ignorés sont ceux de `verification.py`.** Un point de
reprise qui copierait `node_modules/` ou `.venv/` coûterait des
gigaoctets et des minutes, et personne ne le prendrait donc plus. La
liste vit déjà à un endroit ; en écrire une seconde la ferait diverger.

**Un fichier illisible fait échouer la prise, il n'est pas ignoré.** La
leçon de HOS-222 : un instantané silencieusement partiel est pire
qu'absent, parce qu'on croit pouvoir revenir en arrière. Mieux vaut
apprendre maintenant qu'on n'a pas de filet que le découvrir en tombant.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from backend.mission.verification import _IGNORED_DIRS

#: Le manifeste : chemin relatif -> sha256. Rangé à côté des fichiers,
#: en JSON lisible avec `cat` — comme les instantanés de
#: `snapshot_manager`, et pour la même raison : ce qui sert à sortir d'un
#: mauvais état doit rester lisible quand le code qui l'a écrit est
#: cassé.
NOM_MANIFESTE = "manifeste.json"
NOM_CONTENU = "contenu"


class RepliCorrompu(RuntimeError):
    """Le contenu ne correspond plus à ce que le manifeste annonce.

    Levé plutôt qu'avalé : restaurer à moitié depuis un point de reprise
    abîmé laisserait un workspace dans un troisième état, ni l'ancien ni
    le nouveau — et sans que rien le dise.
    """


def _hacher(chemin: Path) -> str:
    h = hashlib.sha256()
    with chemin.open("rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def _fichiers(racine: Path) -> list[Path]:
    return [p for p in sorted(racine.rglob("*"))
            if p.is_file()
            and not any(part in _IGNORED_DIRS for part in p.relative_to(racine).parts)]


@dataclass(frozen=True)
class Ecart:
    """Ce qu'une restauration ferait. Même forme que celui de git.

    Deux types identiques plutôt qu'un partagé : ils décrivent la même
    chose mais ne se calculent pas pareil, et `checkpoint.py` les traite
    de façon interchangeable par leurs attributs. Les fondre demanderait
    un module commun pour trois listes de chaînes.
    """

    a_restaurer: tuple[str, ...] = ()
    a_recreer: tuple[str, ...] = ()
    a_supprimer: tuple[str, ...] = ()

    @property
    def vide(self) -> bool:
        return not (self.a_restaurer or self.a_recreer or self.a_supprimer)

    def resume(self) -> str:
        if self.vide:
            return "le workspace est déjà dans l'état du point de reprise"
        return (f"{len(self.a_restaurer)} à réécrire, "
                f"{len(self.a_recreer)} à recréer, "
                f"{len(self.a_supprimer)} à supprimer")


class TropGros(RuntimeError):
    """Le workspace dépasse le plafond de copie.

    Levé plutôt que tronqué. Un point de reprise partiel est le pire des
    trois états : on croit avoir un filet, il ne retient qu'une partie du
    workspace, et on ne s'en aperçoit qu'en tombant.

    Levé plutôt qu'ignoré aussi : dépenser silencieusement plusieurs
    gigaoctets à chaque mission ferait découvrir le coût par un disque
    plein, pas par une décision.
    """


def taille(workspace: str) -> int:
    """Ce que la copie coûterait, avant de la faire."""
    racine = Path(workspace)
    total = 0
    for f in _fichiers(racine):
        try:
            total += f.stat().st_size
        except OSError:
            continue
    return total


def prendre(workspace: str, destination: Path,
            plafond: int | None = None) -> dict[str, str]:
    """Copier le workspace et rendre son manifeste.

    Lève si un fichier ne se lit pas, ou si le plafond est dépassé : voir
    l'en-tête du module et `TropGros`.
    """
    racine = Path(workspace)
    if plafond is not None:
        mesure = taille(workspace)
        if mesure > plafond:
            raise TropGros(
                f"{mesure / 1e6:.0f} Mo à copier pour {workspace!r}, plafond "
                f"à {plafond / 1e6:.0f} Mo — versionner ce dossier avec git "
                "rendrait le point de reprise quasi gratuit")
    contenu = destination / NOM_CONTENU
    contenu.mkdir(parents=True, exist_ok=True)

    manifeste: dict[str, str] = {}
    for source in _fichiers(racine):
        relatif = source.relative_to(racine)
        cible = contenu / relatif
        cible.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, cible)
        manifeste[relatif.as_posix()] = _hacher(source)

    (destination / NOM_MANIFESTE).write_text(
        json.dumps(manifeste, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifeste


def lire_manifeste(destination: Path) -> dict[str, str]:
    fichier = destination / NOM_MANIFESTE
    if not fichier.exists():
        raise RepliCorrompu(f"manifeste absent : {fichier}")
    return json.loads(fichier.read_text(encoding="utf-8"))


def verifier(destination: Path) -> list[str]:
    """Re-hacher la copie et rendre ce qui ne correspond plus.

    Sans cet appel, le manifeste ne serait qu'une déclaration : il dirait
    ce que la copie *devait* contenir, jamais ce qu'elle contient.
    """
    manifeste = lire_manifeste(destination)
    contenu = destination / NOM_CONTENU
    abimes: list[str] = []
    for relatif, empreinte in manifeste.items():
        copie = contenu / relatif
        if not copie.is_file() or _hacher(copie) != empreinte:
            abimes.append(relatif)
    return sorted(abimes)


def ecart(workspace: str, destination: Path) -> Ecart:
    racine = Path(workspace)
    manifeste = lire_manifeste(destination)
    presents = {p.relative_to(racine).as_posix(): p for p in _fichiers(racine)}

    reecrire = [r for r, e in manifeste.items()
                if r in presents and _hacher(presents[r]) != e]
    recreer = [r for r in manifeste if r not in presents]
    supprimer_ = [r for r in presents if r not in manifeste]
    return Ecart(tuple(sorted(reecrire)), tuple(sorted(recreer)),
                 tuple(sorted(supprimer_)))


def restaurer(workspace: str, destination: Path) -> Ecart:
    """Remettre le workspace dans l'état copié.

    L'intégrité est vérifiée **avant** d'écrire quoi que ce soit : une
    restauration à moitié faite depuis une copie abîmée laisserait un
    troisième état, ni l'ancien ni le nouveau.
    """
    abimes = verifier(destination)
    if abimes:
        raise RepliCorrompu(
            f"{len(abimes)} fichier(s) du point de reprise ne correspondent "
            f"plus à leur empreinte : {', '.join(abimes[:5])} — restaurer "
            "depuis là laisserait un état intermédiaire")

    fait = ecart(workspace, destination)
    racine = Path(workspace)
    contenu = destination / NOM_CONTENU

    for relatif in fait.a_restaurer + fait.a_recreer:
        cible = racine / relatif
        cible.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(contenu / relatif, cible)

    for relatif in fait.a_supprimer:
        (racine / relatif).unlink(missing_ok=True)
    return fait


__all__ = ["Ecart", "NOM_CONTENU", "NOM_MANIFESTE", "RepliCorrompu", "TropGros",
           "ecart", "lire_manifeste", "prendre", "restaurer", "taille",
           "verifier"]
