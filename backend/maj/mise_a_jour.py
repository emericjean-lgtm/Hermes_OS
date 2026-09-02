"""Sauvegarder, migrer, valider, valider ou revenir (HOS-232).

## Ce qui existait, mesuré

`installer/` fait 378 lignes et **ne contient que de la détection** —
`system_detector`, `hardware_profile`. Aucune installation, aucune mise à
jour, aucun retour arrière.

Et deux choses manquaient qui rendaient l'exercice impossible :

- **Hermes OS n'avait pas de version.** Le dépôt en porte trois, aucune
  ne désignant le produit. On ne revient pas à une version qu'on n'a
  jamais nommée.
- **`preserve_set()` ne couvrait pas tout.** HOS-215 l'a écrite ;
  HOS-223 a créé `checkpoints` sous la même racine deux jalons plus
  tard, hors de la liste. Rien ne l'a signalé parce que **rien ne
  consommait `preserve_set()`** — une mise à jour aurait effacé les
  points de reprise, c'est-à-dire le seul moyen d'annuler ce qu'elle
  aurait cassé.

Une liste que rien ne vérifie contre la réalité est une liste qui dérive.

## Ce que ce module fait, et ce qu'il ne fait pas

**Il fait** la moitié qui protège : sauvegarder l'état, migrer, valider,
et revenir en arrière si la validation échoue. C'est cette moitié qui
tient les quinze jalons — Ledger, points de reprise, mémoire,
approbations, quarantaine.

**Il ne fait pas** le remplacement du code : télécharger une version,
échanger l'arborescence. Cela demande un canal de distribution qui
n'existe pas, et l'écrire sans lui produirait un mécanisme non
éprouvable. `appliquer()` prend donc une fonction d'installation
**injectée** — ce qui rend la séquence testable pour de bon, avec une
installation qui échoue exprès.

## L'ordre, et pourquoi il est celui-là

    sauvegarde → migration → installation → validation → validation finale
                                                    ↘ échec → retour arrière

La sauvegarde d'abord : après elle, tout est réversible. La marque de
version **en dernier**, après la validation — posée avant, elle ferait
croire à une mise à jour réussie qui ne l'est pas, et le retour arrière
suivant repartirait du mauvais point.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from backend.core.etat import preserve_set, racine
from backend.maj.version import (
    VERSION,
    ecrire_version_installee,
    lire_version_installee,
)

logger = logging.getLogger("hermes_os.maj")

#: Le catalogue d'événements, à côté de son producteur (patron HOS-181,
#: confirmé par HOS-227).
MAJ_EVENTS: dict[str, str] = {
    "etape": "maj.etape",
    "terminee": "maj.terminee",
    "retour": "maj.retour_arriere",
}

#: Où les sauvegardes vivent : sous la racine d'état, mais **hors** du
#: `preserve_set` qu'elles copient — sinon la sauvegarde d'une
#: sauvegarde doublerait l'occupation à chaque mise à jour.
DOSSIER_SAUVEGARDES = "sauvegardes"

#: Combien on en garde. Trois : assez pour revenir de deux mises à jour
#: successives ratées, assez peu pour que l'état ne quadruple pas.
SAUVEGARDES_GARDEES = 3


class MiseAJourImpossible(RuntimeError):
    """Dit plutôt qu'avalé.

    Une mise à jour qui échouerait en silence laisserait un état à
    mi-chemin que personne ne sait diagnostiquer.
    """


class Etape(str, Enum):
    SAUVEGARDE = "sauvegarde"
    MIGRATION = "migration"
    INSTALLATION = "installation"
    VALIDATION = "validation"
    MARQUAGE = "marquage"
    RETOUR_ARRIERE = "retour_arriere"


@dataclass(frozen=True)
class Sauvegarde:
    """Une copie de l'état, et de quoi la retrouver."""

    chemin: str
    version: str
    prise_le: str
    #: Ce qui a été copié, par nom de dossier. Rangé plutôt que redéduit :
    #: un retour arrière doit restaurer ce qui a été sauvé, pas ce que la
    #: version d'aujourd'hui croit qu'il fallait sauver.
    dossiers: tuple[str, ...] = ()


@dataclass
class Issue:
    """Ce que la mise à jour a fait, et où elle s'est arrêtée."""

    reussie: bool
    depuis: str = ""
    vers: str = ""
    etapes: list[str] = field(default_factory=list)
    sauvegarde: Sauvegarde | None = None
    revenue: bool = False
    raison: str = ""

    def resume(self) -> str:
        if self.reussie:
            return f"{self.depuis or '(neuve)'} → {self.vers}"
        if self.revenue:
            return f"échec puis retour arrière : {self.raison}"
        return f"échec sans retour arrière : {self.raison}"


class MiseAJour:
    """La séquence, avec son filet.

    Les trois travaux — migrer, installer, valider — sont **injectés**.
    Ce module orchestre et protège ; il ne sait pas ce qu'installer veut
    dire, et le décider ici ferait dépendre le filet du contenu.
    """

    def __init__(self, *, migrer: Callable[[], Any] | None = None,
                 installer: Callable[[], Any] | None = None,
                 valider: Callable[[], bool] | None = None,
                 racine_etat: Path | None = None) -> None:
        self._migrer = migrer
        self._installer = installer
        self._valider = valider or self._auto_verification
        self._racine = racine_etat or racine()

    # ── La séquence ──────────────────────────────────────────────────

    def appliquer(self, vers: str = VERSION) -> Issue:
        """Mettre à jour, ou revenir exactement d'où l'on vient."""
        depuis = lire_version_installee(self._racine)
        issue = Issue(reussie=False, depuis=depuis, vers=vers)

        try:
            issue.sauvegarde = self.sauvegarder(depuis)
            issue.etapes.append(Etape.SAUVEGARDE.value)
            self._publier("etape", {"etape": Etape.SAUVEGARDE.value,
                                    "chemin": issue.sauvegarde.chemin})
        except Exception as exc:
            # Sans sauvegarde, rien n'est réversible : on n'installe pas.
            # C'est le seul échec qui arrête avant d'avoir rien touché,
            # et c'est celui qu'il faut arrêter.
            issue.raison = f"sauvegarde impossible : {exc}"
            return self._clore(issue)

        for etape, travail in ((Etape.MIGRATION, self._migrer),
                               (Etape.INSTALLATION, self._installer)):
            if travail is None:
                continue
            try:
                travail()
                issue.etapes.append(etape.value)
                self._publier("etape", {"etape": etape.value})
            except Exception as exc:
                issue.raison = f"{etape.value} : {exc}"
                return self._revenir(issue)

        try:
            valide = bool(self._valider())
        except Exception as exc:
            issue.raison = f"auto-vérification : {exc}"
            return self._revenir(issue)

        issue.etapes.append(Etape.VALIDATION.value)
        if not valide:
            issue.raison = "l'auto-vérification a échoué après installation"
            return self._revenir(issue)

        # En dernier : une marque posée avant ferait croire à une mise à
        # jour réussie qui ne l'est pas.
        ecrire_version_installee(vers, self._racine)
        issue.etapes.append(Etape.MARQUAGE.value)
        issue.reussie = True
        return self._clore(issue)

    # ── Sauvegarder et revenir ───────────────────────────────────────

    def sauvegarder(self, version: str = "") -> Sauvegarde:
        """Copier ce que `preserve_set()` désigne.

        Lit la liste plutôt que d'énumérer des noms : c'est tout
        l'intérêt qu'elle soit une donnée. Un dossier ajouté sous la
        racine sans y être inscrit ne serait pas sauvé — le défaut trouvé
        sur `checkpoints`, que la garde de `test_mise_a_jour.py` empêche
        maintenant.
        """
        horodatage = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = self._dossier_sauvegardes() / horodatage
        destination.mkdir(parents=True, exist_ok=True)

        copies: list[str] = []
        for source in preserve_set():
            if not source.exists():
                # Un dossier absent n'est pas une erreur : un état neuf
                # n'a pas encore de points de reprise.
                continue
            shutil.copytree(source, destination / source.name,
                            dirs_exist_ok=True)
            copies.append(source.name)

        self._elaguer()
        return Sauvegarde(chemin=str(destination), version=version,
                          prise_le=horodatage, dossiers=tuple(copies))

    def restaurer(self, sauvegarde: Sauvegarde) -> None:
        """Remettre l'état tel qu'il était.

        Restaure **ce qui a été sauvé**, pas ce que la version
        d'aujourd'hui croit qu'il fallait sauver : la liste voyage avec
        la sauvegarde. Une version qui aurait ajouté un dossier ne doit
        pas prétendre le restaurer depuis une copie qui ne le contient
        pas.
        """
        source_racine = Path(sauvegarde.chemin)
        if not source_racine.is_dir():
            raise MiseAJourImpossible(
                f"sauvegarde introuvable : {sauvegarde.chemin}")

        for nom in sauvegarde.dossiers:
            source = source_racine / nom
            if not source.is_dir():
                continue
            cible = self._racine / nom
            # Retirer d'abord : une copie par-dessus laisserait les
            # fichiers que la version fautive a créés, et un état
            # mi-ancien mi-nouveau est pire que l'un ou l'autre.
            shutil.rmtree(cible, ignore_errors=True)
            shutil.copytree(source, cible)

        if sauvegarde.version:
            ecrire_version_installee(sauvegarde.version, self._racine)

    # ── L'auto-vérification par défaut ───────────────────────────────

    def _auto_verification(self) -> bool:
        """Ce qui doit répondre après une installation.

        Volontairement minimale et **réelle** : la racine d'état est
        lisible, la base s'ouvre, et le registre des runs répond. Une
        auto-vérification qui ne ferait qu'importer des modules
        passerait sur une base corrompue.
        """
        try:
            if not self._racine.is_dir():
                return False
            for dossier in preserve_set():
                dossier.mkdir(parents=True, exist_ok=True)

            from backend.runs.registre import Registre

            Registre().en_cours()
            return True
        except Exception:
            logger.warning("auto-vérification en échec", exc_info=True)
            return False

    # ── Interne ──────────────────────────────────────────────────────

    def _revenir(self, issue: Issue) -> Issue:
        if issue.sauvegarde is None:
            return self._clore(issue)
        try:
            self.restaurer(issue.sauvegarde)
            issue.revenue = True
            issue.etapes.append(Etape.RETOUR_ARRIERE.value)
            self._publier("retour", {"chemin": issue.sauvegarde.chemin,
                                     "raison": issue.raison})
        except Exception as exc:
            # Le pire cas, et il doit être dit fort : l'installation a
            # échoué **et** le retour arrière aussi. Taire ça laisserait
            # un état à mi-chemin que personne ne sait diagnostiquer.
            issue.raison += f" — et le retour arrière a échoué : {exc}"
            logger.error("retour arrière impossible", exc_info=True)
        return self._clore(issue)

    def _dossier_sauvegardes(self) -> Path:
        chemin = self._racine / DOSSIER_SAUVEGARDES
        chemin.mkdir(parents=True, exist_ok=True)
        return chemin

    def _elaguer(self) -> None:
        """Ne garder que les dernières. Jamais la plus récente."""
        dossiers = sorted((d for d in self._dossier_sauvegardes().iterdir()
                           if d.is_dir()), key=lambda d: d.name)
        for vieille in dossiers[:-SAUVEGARDES_GARDEES]:
            shutil.rmtree(vieille, ignore_errors=True)

    def _clore(self, issue: Issue) -> Issue:
        self._publier("terminee", {
            "reussie": issue.reussie, "depuis": issue.depuis,
            "vers": issue.vers, "revenue": issue.revenue,
            "raison": issue.raison, "etapes": issue.etapes,
        })
        return issue

    @staticmethod
    def _publier(cle: str, charge: dict) -> None:
        try:
            from backend.core.event_hub import get_event_hub

            get_event_hub().publish(MAJ_EVENTS[cle], charge)
        except Exception:  # pragma: no cover - la trace ne casse pas la MAJ
            logger.debug("événement de mise à jour non publié", exc_info=True)


__all__ = ["DOSSIER_SAUVEGARDES", "Etape", "Issue", "MAJ_EVENTS", "MiseAJour",
           "MiseAJourImpossible", "SAUVEGARDES_GARDEES", "Sauvegarde"]
