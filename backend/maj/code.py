"""Remplacer le code, et pouvoir le remettre (HOS-233).

## Ce qui manquait

HOS-232 sauvegardait l'**état** et le restaurait. Il ne touchait pas au
code : `mise_a_jour.py` n'écrivait rien hors de la racine d'état. Le
moteur n'était donc pas un moteur de mise à jour — c'était un filet.

Agent OS le dit sans détour dans son `UPDATE.md` : *« what an update DOES
replace: the app code itself (everything in the app folder) »*, avec une
sauvegarde datée de l'ancienne version à côté. C'est le patron, et il
est juste.

## Trois choses qu'Agent OS n'a pas à protéger, et Hermes si

**Le dépôt git.** Leur dossier d'application n'en est pas un. Ici, `.git`
porte l'historique, la branche, l'index et le travail non commité de
l'utilisateur. Il n'est **jamais** touché : ni sauvé, ni remplacé, ni
lu. Une mise à jour laisse donc `HEAD`, la branche et l'index
exactement où ils étaient — et l'utilisateur voit le changement comme un
diff, ce qui vaut mieux qu'un avertissement dans un fichier Markdown.

**Le `.env` de l'utilisateur.** Mesuré : `SettingsConfigDict(env_file=
".env")` le résout depuis le répertoire courant, donc **à la racine du
dépôt** — c'est-à-dire *dans* l'arbre que la mise à jour remplace. Un
remplacement naïf détruirait la clé API.

Il est donc **préservé en place** : ni copié, ni remplacé. Pas copié
parce qu'une sauvegarde de secret est un secret de plus, en clair, dans
un dossier que personne ne surveille. Pas remplacé parce qu'il est à
l'utilisateur.

**Les environnements installés.** `.venv` et `node_modules` pèsent des
gigaoctets et se reconstruisent. Les sauver ferait de chaque mise à jour
une copie de plusieurs minutes, donc une mise à jour qu'on ne lance pas.

## La règle

Ce qui est **remplacé** est sauvegardé. Ce qui est **préservé en place**
n'est ni sauvegardé ni remplacé. Il n'y a pas de troisième catégorie, et
c'est ce qui rend le retour arrière exact.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("hermes_os.maj.code")

#: Ce qu'une mise à jour ne touche **jamais**, même à l'intérieur d'une
#: racine qu'elle remplace. Ni sauvegardé, ni remplacé, ni lu.
#:
#: `.env` y figure pour une raison mesurée : c'est là que vit la clé
#: OpenRouter de l'utilisateur, et l'arbre de code est l'endroit où
#: `pydantic-settings` la cherche.
PRESERVE_EN_PLACE: frozenset[str] = frozenset({
    ".git", ".venv", "venv", "node_modules", ".env", ".env.local",
    "__pycache__", ".next", ".pytest_cache",
})

#: Où la version précédente est gardée. Sous la racine d'état, comme
#: Agent OS la garde « next to the app » : hors de ce qui est remplacé,
#: sinon la sauvegarde partirait avec l'ancienne version.
DOSSIER_CODE = "code_precedent"


class RemplacementImpossible(RuntimeError):
    """Dit, jamais avalé."""


@dataclass(frozen=True)
class SauvegardeCode:
    """L'ancienne version, et ce qu'elle contenait."""

    chemin: str
    prise_le: str
    racines: tuple[str, ...] = ()
    #: Ce qui a été laissé sur place, par nom. Rangé pour l'audit :
    #: un lecteur doit pouvoir vérifier qu'aucun secret n'a été copié.
    preserves: tuple[str, ...] = field(default_factory=tuple)


def _ignorer(dossier: str, noms: list[str]) -> set[str]:
    """Ce que `copytree` saute. La même liste des deux côtés.

    Une copie et un remplacement qui n'ignoreraient pas la même chose
    laisseraient un `.venv` de l'ancienne version dans la nouvelle — ou
    supprimeraient celui de l'utilisateur.
    """
    return {n for n in noms if n in PRESERVE_EN_PLACE}


def sauvegarder(installation: Path, racines: tuple[str, ...],
                destination: Path) -> SauvegardeCode:
    """Copier l'arbre de code, moins ce qui est préservé en place."""
    destination.mkdir(parents=True, exist_ok=True)
    copiees: list[str] = []
    preserves: set[str] = set()

    for nom in racines:
        source = installation / nom
        if not source.exists():
            continue
        for entree in source.rglob("*"):
            if entree.name in PRESERVE_EN_PLACE:
                preserves.add(entree.name)
        shutil.copytree(source, destination / nom, ignore=_ignorer,
                        dirs_exist_ok=True)
        copiees.append(nom)

    for nom in sorted(PRESERVE_EN_PLACE):
        if (installation / nom).exists():
            preserves.add(nom)

    return SauvegardeCode(
        chemin=str(destination),
        prise_le=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        racines=tuple(copiees), preserves=tuple(sorted(preserves)))


def remplacer(installation: Path, paquet: Path,
              racines: tuple[str, ...]) -> list[str]:
    """Installer les racines du paquet à la place des existantes.

    Chaque racine est retirée puis recopiée, et non écrasée par-dessus :
    une copie par-dessus laisserait les fichiers que l'ancienne version
    avait et que la nouvelle n'a plus — un arbre mi-ancien mi-nouveau,
    qui importe et qui ment.

    C'est la même règle que `MiseAJour.restaurer` applique à l'état
    depuis HOS-232, et pour la même raison.
    """
    remplacees: list[str] = []
    for nom in racines:
        source = paquet / nom
        if not source.is_dir():
            raise RemplacementImpossible(
                f"le paquet ne contient pas {nom!r} — un remplacement "
                "partiel laisserait un arbre incohérent")
        cible = installation / nom
        _vider(cible)
        shutil.copytree(source, cible, ignore=_ignorer, dirs_exist_ok=True)
        remplacees.append(nom)
    return remplacees


def restaurer(installation: Path, sauvegarde: SauvegardeCode) -> list[str]:
    """Remettre l'ancienne version.

    Restaure **ce qui a été sauvé** — la liste voyage avec la sauvegarde,
    comme celle de l'état (HOS-232). Une version qui aurait ajouté une
    racine ne doit pas prétendre la restaurer depuis une copie qui ne la
    contient pas.
    """
    source_racine = Path(sauvegarde.chemin)
    if not source_racine.is_dir():
        raise RemplacementImpossible(
            f"sauvegarde de code introuvable : {sauvegarde.chemin}")

    rendues: list[str] = []
    for nom in sauvegarde.racines:
        source = source_racine / nom
        if not source.is_dir():
            continue
        cible = installation / nom
        _vider(cible)
        shutil.copytree(source, cible, ignore=_ignorer, dirs_exist_ok=True)
        rendues.append(nom)
    return rendues


def _vider(cible: Path) -> None:
    """Retirer une racine sans toucher à ce qui est préservé en place.

    `shutil.rmtree` emporterait le `.venv` et le `.env` qui vivent
    dessous. Ici on descend d'un niveau et on saute ce qui est protégé.
    """
    if not cible.exists():
        return
    if cible.name in PRESERVE_EN_PLACE:
        return
    for entree in cible.iterdir():
        if entree.name in PRESERVE_EN_PLACE:
            continue
        if entree.is_dir():
            _vider(entree)
            try:
                entree.rmdir()
            except OSError:
                # Reste quelque chose de préservé dessous : c'est le
                # comportement voulu, on laisse le dossier.
                logger.debug("dossier conservé (contenu préservé) : %s", entree)
        else:
            entree.unlink(missing_ok=True)


__all__ = ["DOSSIER_CODE", "PRESERVE_EN_PLACE", "RemplacementImpossible",
           "SauvegardeCode", "remplacer", "restaurer", "sauvegarder"]
