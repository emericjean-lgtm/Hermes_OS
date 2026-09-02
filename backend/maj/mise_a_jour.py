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

**Il fait aussi**, depuis HOS-233, le **remplacement réel du code** :
`code.remplacer` retire et recopie les racines déclarées par le paquet,
en laissant en place `.git`, `.venv`, `node_modules` et le `.env` de
l'utilisateur. Le paquet est un répertoire local validé
(`paquet.lire`), et d'où il vient reste la question du canal de
distribution — qui n'existe toujours pas, et qui n'est pas ici.

**Il ne fait pas** le téléchargement. `appliquer()` reçoit un chemin, ou
une fonction d'installation injectée pour les cas où l'appelant sait
faire autrement.

## L'ordre, et pourquoi il est celui-là

    paquet → compatibilité → sauvegarde état → sauvegarde code
          → remplacement → migration → self-check → marquage
                                    ↘ échec → retour arrière (code puis état)

Le paquet est validé **avant** toute sauvegarde : un paquet refusé ne
doit rien coûter, et surtout pas laisser une sauvegarde orpheline.

Le retour arrière remet le **code d'abord**, l'état ensuite : restaurer
un état ancien sous un code neuf donnerait le seul état que rien ne sait
lire.

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
from backend.maj import code as _code
from backend.maj import paquet as _paquet
from backend.maj import sante as _sante
from backend.maj.version import (
    VERSION,
    ecrire_version_installee,
    lire_version_installee,
    verifier_la_compatibilite,
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
    PAQUET = "paquet"
    COMPATIBILITE = "compatibilite"
    SAUVEGARDE = "sauvegarde"
    SAUVEGARDE_CODE = "sauvegarde_code"
    REMPLACEMENT = "remplacement"
    MIGRATION = "migration"
    INSTALLATION = "installation"
    VALIDATION = "validation"
    MARQUAGE = "marquage"
    RETOUR_ARRIERE = "retour_arriere"
    #: Le pire état : l'installation a échoué **et** le retour aussi.
    FATAL = "fatal"


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
    #: Ce qui a été trouvé sous la racine sans figurer dans
    #: `preserve_set()`. Sauvé quand même — perdre la donnée serait pire
    #: — mais **dit**, parce que le silence est ce qui a laissé passer
    #: `checkpoints` puis `workflows`.
    non_declares: tuple[str, ...] = ()


@dataclass
class Issue:
    """Ce que la mise à jour a fait, et où elle s'est arrêtée."""

    reussie: bool
    depuis: str = ""
    vers: str = ""
    etapes: list[str] = field(default_factory=list)
    sauvegarde: Sauvegarde | None = None
    #: L'ancienne version du code, quand il y a eu remplacement.
    sauvegarde_code: Any = None
    revenue: bool = False
    #: Le pire cas : ni installé, ni revenu. Distinct de `revenue=False`
    #: sur un échec avant modification, où il n'y avait rien à revenir.
    fatal: bool = False
    #: Le rapport structuré du self-check, exploitable après coup.
    sante: Any = None
    raison: str = ""

    def resume(self) -> str:
        if self.reussie:
            return f"{self.depuis or '(neuve)'} → {self.vers}"
        if self.revenue:
            return f"échec puis retour arrière : {self.raison}"
        if self.fatal:
            return f"ÉTAT FATAL — ni installé ni revenu : {self.raison}"
        return f"échec avant modification : {self.raison}"


class MiseAJour:
    """La séquence, avec son filet.

    Les trois travaux — migrer, installer, valider — sont **injectés**.
    Ce module orchestre et protège ; il ne sait pas ce qu'installer veut
    dire, et le décider ici ferait dépendre le filet du contenu.
    """

    def __init__(self, *, migrer: Callable[[], Any] | None = None,
                 installer: Callable[[], Any] | None = None,
                 valider: Callable[[], bool] | None = None,
                 racine_etat: Path | None = None,
                 installation: Path | None = None) -> None:
        self._migrer = migrer
        self._installer = installer
        self._valider = valider
        self._racine = racine_etat or racine()
        # L'arbre de code à remplacer. Déduit du module plutôt que du
        # répertoire courant : une mise à jour lancée depuis ailleurs ne
        # doit pas remplacer un autre dossier que celui d'où elle tourne.
        self._installation = installation or Path(__file__).resolve().parents[2]

    # ── La séquence ──────────────────────────────────────────────────

    def appliquer(self, paquet: Any = None, *, vers: str = "") -> Issue:
        """Mettre à jour, ou revenir exactement d'où l'on vient.

        `paquet` est un chemin vers un répertoire de version, ou `None`
        pour n'exécuter que la moitié « état » — ce que faisait HOS-232,
        conservé pour un appelant qui installe autrement via `installer=`.
        """
        depuis = lire_version_installee(self._racine)
        paquet_lu = None

        # 1. Le paquet, **avant** toute sauvegarde : un paquet refusé ne
        #    doit rien coûter, et surtout pas laisser une sauvegarde
        #    orpheline derrière lui.
        if paquet is not None:
            try:
                paquet_lu = _paquet.lire(paquet)
                vers = vers or paquet_lu.version
            except Exception as exc:
                return self._clore(Issue(reussie=False, depuis=depuis,
                                         vers=vers, raison=f"paquet : {exc}"))

        vers = vers or VERSION
        issue = Issue(reussie=False, depuis=depuis, vers=vers)

        # 2. La compatibilité. Aucune mise à jour aveugle.
        try:
            note = verifier_la_compatibilite(
                depuis, vers,
                depuis_au_moins=paquet_lu.depuis_au_moins if paquet_lu else "")
            issue.etapes.append(Etape.COMPATIBILITE.value)
            self._publier("etape", {"etape": Etape.COMPATIBILITE.value,
                                    "note": note})
        except Exception as exc:
            issue.raison = f"compatibilité : {exc}"
            return self._clore(issue)

        # 3. L'état, puis le code. Après, tout est réversible.
        try:
            issue.sauvegarde = self.sauvegarder(depuis)
            issue.etapes.append(Etape.SAUVEGARDE.value)
            self._publier("etape", {"etape": Etape.SAUVEGARDE.value,
                                    "chemin": issue.sauvegarde.chemin})
        except Exception as exc:
            # Sans sauvegarde, rien n'est réversible : on n'installe pas.
            issue.raison = f"sauvegarde impossible : {exc}"
            return self._clore(issue)

        if paquet_lu is not None:
            try:
                issue.sauvegarde_code = _code.sauvegarder(
                    self._installation, paquet_lu.racines,
                    self._dossier_sauvegardes() / issue.sauvegarde.prise_le
                    / _code.DOSSIER_CODE)
                issue.etapes.append(Etape.SAUVEGARDE_CODE.value)
            except Exception as exc:
                issue.raison = f"sauvegarde du code impossible : {exc}"
                return self._clore(issue)

            try:
                _code.remplacer(self._installation, paquet_lu.chemin,
                                paquet_lu.racines)
                issue.etapes.append(Etape.REMPLACEMENT.value)
                self._publier("etape", {"etape": Etape.REMPLACEMENT.value,
                                        "racines": list(paquet_lu.racines)})
            except Exception as exc:
                issue.raison = f"remplacement : {exc}"
                return self._revenir(issue)

        # 4. Migration puis installation complémentaire, si injectées.
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

        # 5. Le self-check. Structuré, pour qu'on sache quoi réparer.
        try:
            valide, issue.sante = self._verifier()
        except Exception as exc:
            issue.raison = f"auto-vérification : {exc}"
            return self._revenir(issue)

        issue.etapes.append(Etape.VALIDATION.value)
        if not valide:
            detail = (issue.sante.resume() if hasattr(issue.sante, "resume")
                      else "")
            issue.raison = f"auto-vérification en échec : {detail}"
            return self._revenir(issue)

        # 6. En dernier : une marque posée avant ferait croire à une mise
        #    à jour réussie qui ne l'est pas.
        ecrire_version_installee(vers, self._racine)
        issue.etapes.append(Etape.MARQUAGE.value)
        issue.reussie = True
        return self._clore(issue)

    def _verifier(self) -> tuple[bool, Any]:
        """Le self-check, injecté ou réel.

        Un `valider` injecté qui rend un booléen est accepté tel quel —
        les tests s'en servent — mais le défaut est le rapport structuré
        de `sante.verifier()`, qui touche à la base, aux approbations, aux
        points de reprise et au RAL.
        """
        if self._valider is not None:
            resultat = self._valider()
            if hasattr(resultat, "sain"):
                return bool(resultat.sain), resultat
            return bool(resultat), None
        rapport = _sante.verifier()
        return rapport.sain, rapport

    # ── Sauvegarder et revenir ───────────────────────────────────────

    def sauvegarder(self, version: str = "") -> Sauvegarde:
        """Copier ce que `preserve_set()` désigne — **et ce qu'il oublie**.

        Trois sources, et il en faut trois (HOS-233) :

        1. la **liste déclarative**, `preserve_set()` ;
        2. l'**observation du disque** : tout répertoire présent sous la
           racine et absent de la liste est copié quand même, et signalé ;
        3. le **manifeste** de la sauvegarde, qui porte les deux et sert
           de vérité au retour arrière.

        La deuxième existe à cause d'un défaut mesuré deux fois. HOS-223 a
        créé `checkpoints` hors de la liste, et rien ne l'a dit. Puis
        l'audit de HOS-233 a trouvé `workflows` sous la racine réelle,
        également hors de la liste — un résidu de la migration HOS-215,
        que la garde de HOS-232 n'a pas vu **parce qu'elle lisait le code
        et non le disque**.

        Une liste ne peut pas décrire ce qu'elle ignore. On la garde parce
        qu'elle est la déclaration d'intention ; on observe parce que
        c'est le disque qui a le dernier mot.
        """
        horodatage = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = self._dossier_sauvegardes() / horodatage
        destination.mkdir(parents=True, exist_ok=True)

        declares = {p.name: p for p in preserve_set()}
        # Ce que le disque porte réellement, moins ce qui n'est pas de
        # l'état : les sauvegardes elles-mêmes, et les fichiers isolés
        # comme `version.json`, qui sont réécrits par la mise à jour.
        observes: dict[str, Path] = {}
        if self._racine.is_dir():
            for entree in self._racine.iterdir():
                if entree.is_dir() and entree.name != DOSSIER_SAUVEGARDES:
                    observes[entree.name] = entree

        copies: list[str] = []
        non_declares: list[str] = []
        for nom, source in sorted({**declares, **observes}.items()):
            if not source.exists():
                # Un dossier absent n'est pas une erreur : un état neuf
                # n'a pas encore de points de reprise.
                continue
            shutil.copytree(source, destination / nom, dirs_exist_ok=True)
            copies.append(nom)
            if nom not in declares:
                non_declares.append(nom)

        if non_declares:
            # Signalé, pas fatal : perdre la donnée serait pire que la
            # sauver sans l'avoir déclarée. Mais le silence serait pire
            # encore — c'est ainsi que `checkpoints` est passé.
            logger.warning(
                "sauvegardés bien qu'absents de preserve_set() : %s — "
                "à déclarer dans SOUS_DOSSIERS ou à retirer de la racine",
                non_declares)

        self._elaguer()
        return Sauvegarde(chemin=str(destination), version=version,
                          prise_le=horodatage, dossiers=tuple(copies),
                          non_declares=tuple(non_declares))

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

        # HOS-233 : vérifier **avant** d'écrire que tout ce que le
        # manifeste annonce est là.
        #
        # Une première version se contentait de sauter les dossiers
        # absents. Un test l'a prise en défaut : une sauvegarde vidée
        # restaurait alors **zéro dossier** et se déclarait réussie —
        # une perte de données silencieuse déguisée en retour arrière.
        # « Un backup non restauré n'est pas une preuve de rollback. »
        manquants = [nom for nom in sauvegarde.dossiers
                     if not (source_racine / nom).is_dir()]
        if manquants:
            raise MiseAJourImpossible(
                f"sauvegarde incomplète : {manquants} annoncé(s) et absent(s) "
                f"de {sauvegarde.chemin} — restaurer à moitié laisserait un "
                "état que personne ne sait lire")

        for nom in sauvegarde.dossiers:
            source = source_racine / nom
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
        """Remettre le **code d'abord**, l'état ensuite.

        L'ordre compte : restaurer un état ancien sous un code neuf
        donnerait le seul état que rien ne sait lire — un schéma d'hier
        servi par le code de demain.
        """
        if issue.sauvegarde is None and issue.sauvegarde_code is None:
            return self._clore(issue)

        echecs: list[str] = []
        if issue.sauvegarde_code is not None:
            try:
                _code.restaurer(self._installation, issue.sauvegarde_code)
            except Exception as exc:
                echecs.append(f"code : {exc}")
                logger.error("retour arrière du code impossible", exc_info=True)

        if issue.sauvegarde is not None:
            try:
                self.restaurer(issue.sauvegarde)
            except Exception as exc:
                echecs.append(f"état : {exc}")
                logger.error("retour arrière de l'état impossible",
                             exc_info=True)

        if echecs:
            # Le pire cas, et il doit être dit fort : l'installation a
            # échoué **et** le retour arrière aussi. Taire ça laisserait
            # un état à mi-chemin que personne ne sait diagnostiquer.
            issue.fatal = True
            issue.etapes.append(Etape.FATAL.value)
            issue.raison += (" — et le retour arrière a échoué : "
                             + " ; ".join(echecs))
            return self._clore(issue)

        issue.revenue = True
        issue.etapes.append(Etape.RETOUR_ARRIERE.value)
        self._publier("retour", {
            "chemin": issue.sauvegarde.chemin if issue.sauvegarde else "",
            "code": getattr(issue.sauvegarde_code, "chemin", ""),
            "raison": issue.raison})
        # L'état **opérationnel** — cooldowns, santé, caches — n'est pas
        # restauré : il est recalculé. Voir `_reinitialiser_l_operationnel`.
        self._reinitialiser_l_operationnel()
        return self._clore(issue)

    @staticmethod
    def _reinitialiser_l_operationnel() -> None:
        """Repartir des faits, pas d'un souvenir (HOS-233).

        Un cooldown de fournisseur, une santé de runtime, un catalogue en
        cache : tout cela décrit **maintenant**, et un retour arrière
        change ce maintenant. Le restaurer réappliquerait un écart décidé
        pour un incident qui appartenait à l'installation d'avant.

        Mesuré : le courtier (HOS-228) est déjà sans état persistant, et
        son propre commentaire le dit — « un écart est une réaction à un
        incident en cours ». On le remet donc à zéro explicitement plutôt
        que de compter sur un redémarrage qui n'aura peut-être pas lieu.
        """
        try:
            from backend.ral import courtier

            courtier.reinitialiser()
        except Exception:  # pragma: no cover - jamais bloquant
            logger.debug("courtier non réinitialisé", exc_info=True)
        try:
            from backend.core.config import get_settings

            get_settings.cache_clear()
        except Exception:  # pragma: no cover
            logger.debug("configuration non rechargée", exc_info=True)

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
            "fatal": issue.fatal, "raison": issue.raison,
            "etapes": issue.etapes,
            "sante": issue.sante.to_dict() if hasattr(issue.sante, "to_dict")
                     else None,
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
