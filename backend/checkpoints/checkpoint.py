"""Le point de reprise complet : les fichiers **et** l'état (HOS-223).

## Le manque

Hermes ne savait pas annuler une modification. Trois constats, mesurés
dans le code :

- `propose_write` déposait bien une sauvegarde horodatée à chaque
  écrasement — et **rien, nulle part, n'en restaurait jamais**. Elle
  était rendue à l'appelant et publiée dans un événement ; aucune
  fonction du dépôt ne la relisait.
- `delete()` faisait `shutil.rmtree()` sur un répertoire sans rien
  garder du tout. `move()` non plus.
- `snapshot_manager` sauve l'état de mission et **dit explicitement**
  qu'il ne copie pas les fichiers, en déléguant aux sauvegardes
  ci-dessus. La délégation pointait vers un mécanisme sans retour.

## Ce que ce module ajoute à Agent OS

Leur checkpoint est un état de fichiers. `snapshot_manager` sauve l'état
de mission — tâches, exécutions de workflow, contexte — ce qu'ils ne font
pas. Un point de reprise Hermes est le **couple**, pris et repris
ensemble.

La raison est concrète : restaurer les fichiers sans l'état laisse une
mission qui croit avoir fini un travail que le disque ne porte plus, et
qui repartira de là. Restaurer l'état sans les fichiers fait l'inverse.
L'un ou l'autre seul fabrique une incohérence — exactement le genre
d'incohérence que ce dépôt met des semaines à retrouver.

## Restaurer efface, et c'est traité comme tel

Même contrat que `snapshot_manager.restore_snapshot` : jamais
automatique, jamais au démarrage, jamais sur reprise après incident. Un
aperçu d'abord, une décision d'Aegis ensuite. Le geste qui remet un
workspace dans un état antérieur détruit tout ce qui a été fait depuis,
et l'appelant doit avoir vu quoi.
"""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.checkpoints import git_ref, repli_fichiers
from backend.core.etat import racine as racine_d_etat

logger = logging.getLogger("hermes_os.checkpoints")

#: Sous la racine d'état, jamais dans le dépôt (HOS-215) et jamais dans
#: le workspace : un point de reprise rangé dans le dossier qu'il
#: protège disparaîtrait avec lui.
DOSSIER = "checkpoints"

#: Le plafond de la copie intégrale, quand il n'y a pas de dépôt git.
#:
#: 500 Mo : au-delà, le point de reprise coûte plus que la mission qu'il
#: protège, et le prendre à chaque fois remplirait le disque sans que
#: personne l'ait décidé. Git n'y est pas soumis — son stockage par
#: contenu déduplique, et un second point de reprise d'un dépôt inchangé
#: ne coûte qu'un commit.
PLAFOND_COPIE = 500 * 1024 * 1024


class CheckpointImpossible(RuntimeError):
    """La prise a échoué. Dit plutôt qu'avalé.

    Un point de reprise qu'on croit avoir et qui n'existe pas est pire
    que pas de point de reprise : il autorise le geste risqué.
    """


class CheckpointIntrouvable(KeyError):
    pass


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Checkpoint:
    """Un point de reprise : des fichiers, un état, un motif."""

    identifiant: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    workspace: str = ""
    motif: str = ""
    mission: str = ""
    run: str = ""
    #: `"git"` ou `"fichiers"`. Rangé plutôt que redéduit : le workspace
    #: peut avoir été initialisé en dépôt git *après* la prise, et
    #: redemander « est-ce un dépôt ? » à la restauration choisirait
    #: alors le mauvais mécanisme sur un point de reprise qui n'en a pas.
    mecanisme: str = "fichiers"
    #: Le commit, quand le mécanisme est git.
    commit: str = ""
    #: L'instantané de `snapshot_manager`, quand il a pu être pris.
    #: Vide n'est pas une erreur : un workspace peut être protégé sans
    #: qu'une mission tourne.
    instantane: str = ""
    fichiers: int = 0
    cree_le: str = field(default_factory=_maintenant)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _racine() -> Path:
    chemin = racine_d_etat() / DOSSIER
    chemin.mkdir(parents=True, exist_ok=True)
    return chemin


def _dossier(identifiant: str) -> Path:
    return _racine() / identifiant


def _fiche(identifiant: str) -> Path:
    return _dossier(identifiant) / "checkpoint.json"


# ── Prendre ──────────────────────────────────────────────────────────

def prendre(workspace: str, *, motif: str = "", mission: str = "",
            run: str = "", avec_etat: bool = True,
            plafond: int | None = PLAFOND_COPIE) -> Checkpoint:
    """Prendre un point de reprise du workspace, et de l'état s'il y en a.

    Le mécanisme est choisi ici et **une seule fois** : git quand le
    workspace en est un, copie vérifiée sinon.
    """
    racine = Path(workspace)
    if not racine.is_dir():
        raise CheckpointImpossible(
            f"{workspace!r} n'est pas un répertoire — rien à protéger, et "
            "annoncer un point de reprise ici autoriserait le geste risqué")

    point = Checkpoint(workspace=str(racine.resolve()), motif=motif,
                       mission=mission, run=run)
    dossier = _dossier(point.identifiant)
    dossier.mkdir(parents=True, exist_ok=True)

    try:
        if git_ref.est_un_depot(str(racine)):
            point.mecanisme = "git"
            point.commit = git_ref.prendre(
                str(racine), motif or f"point de reprise Hermes {point.identifiant}")
        else:
            point.mecanisme = "fichiers"
            manifeste = repli_fichiers.prendre(str(racine), dossier,
                                               plafond=plafond)
            point.fichiers = len(manifeste)
    except Exception as exc:
        # Le dossier à moitié écrit est retiré : le laisser ferait
        # apparaître un point de reprise dans `lister()` sans fiche, donc
        # un filet qu'on croit avoir.
        shutil.rmtree(dossier, ignore_errors=True)
        raise CheckpointImpossible(
            f"point de reprise impossible sur {workspace!r} : {exc}") from exc

    if avec_etat:
        point.instantane = _prendre_l_etat(point)

    _fiche(point.identifiant).write_text(
        json.dumps(point.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8")
    return point


def _prendre_l_etat(point: Checkpoint) -> str:
    """L'instantané de mission, en meilleur effort.

    Son absence n'annule pas le point de reprise : les fichiers sont déjà
    protégés, et refuser tout parce que la base d'état n'a pas répondu
    laisserait l'utilisateur sans rien plutôt qu'avec l'essentiel.
    `restaurer()` dit ensuite ce qui a pu être repris et ce qui n'a pas
    pu l'être — c'est la règle du tri-état (HOS-222) appliquée ici.
    """
    try:
        from backend.core import snapshot_manager

        info = snapshot_manager.create_snapshot(
            reason=point.motif or f"checkpoint {point.identifiant}",
            context={"checkpoint": point.identifiant,
                     "workspace": point.workspace,
                     "mission": point.mission, "run": point.run})
        return info.id
    except Exception:
        logger.warning("état de mission non capturé pour le checkpoint %s",
                       point.identifiant, exc_info=True)
        return ""


# ── Lire ─────────────────────────────────────────────────────────────

def lire(identifiant: str) -> Checkpoint:
    fiche = _fiche(identifiant)
    if not fiche.exists():
        raise CheckpointIntrouvable(identifiant)
    return Checkpoint(**json.loads(fiche.read_text(encoding="utf-8")))


def lister(workspace: str | None = None) -> list[Checkpoint]:
    """Les points de reprise, du plus récent au plus ancien."""
    points: list[Checkpoint] = []
    for fiche in _racine().glob("*/checkpoint.json"):
        try:
            points.append(Checkpoint(**json.loads(
                fiche.read_text(encoding="utf-8"))))
        except Exception:
            # Une fiche illisible est signalée, pas propagée : elle ne
            # doit pas rendre les autres points de reprise inaccessibles
            # au moment où on en cherche un.
            logger.warning("fiche de checkpoint illisible : %s", fiche,
                           exc_info=True)
    if workspace:
        cible = str(Path(workspace).resolve())
        points = [p for p in points if p.workspace == cible]
    return sorted(points, key=lambda p: p.cree_le, reverse=True)


# ── Apercevoir avant d'agir ──────────────────────────────────────────

@dataclass(frozen=True)
class Restauration:
    """Ce qu'une restauration ferait, ou vient de faire."""

    checkpoint: str
    workspace: str
    a_restaurer: tuple[str, ...] = ()
    a_recreer: tuple[str, ...] = ()
    #: **Ce qui sera effacé.** Liste séparée, jamais fondue dans un
    #: compteur : c'est la seule des trois qui détruise du travail.
    a_supprimer: tuple[str, ...] = ()
    etat_repris: bool = False
    #: Renseigné quand l'état de mission n'a pas pu être repris. On le
    #: dit plutôt que de rendre un succès partiel silencieux.
    etat_non_repris: str = ""
    applique: bool = False

    @property
    def vide(self) -> bool:
        return not (self.a_restaurer or self.a_recreer or self.a_supprimer)

    def resume(self) -> str:
        if self.vide:
            return "le workspace est déjà dans l'état du point de reprise"
        return (f"{len(self.a_restaurer)} à réécrire, "
                f"{len(self.a_recreer)} à recréer, "
                f"**{len(self.a_supprimer)} à supprimer**")


def apercu(identifiant: str) -> Restauration:
    """Ce que la restauration ferait, sans rien faire.

    Le même contrat que `snapshot_manager.preview_restore` et que
    `propose_write` : montrer la différence avant de l'appliquer.
    """
    point = lire(identifiant)
    ecart = _ecart(point)
    return Restauration(
        checkpoint=point.identifiant, workspace=point.workspace,
        a_restaurer=ecart.a_restaurer, a_recreer=ecart.a_recreer,
        a_supprimer=ecart.a_supprimer, applique=False)


def _ecart(point: Checkpoint):
    if point.mecanisme == "git":
        if not git_ref.existe(point.workspace, point.commit):
            raise CheckpointImpossible(
                f"le commit {point.commit[:12]} du point de reprise "
                f"{point.identifiant} n'est plus dans le dépôt — sa "
                "référence a-t-elle été supprimée ?")
        return git_ref.ecart(point.workspace, point.commit)
    return repli_fichiers.ecart(point.workspace, _dossier(point.identifiant))


# ── Restaurer ────────────────────────────────────────────────────────

def restaurer(aegis: Any, identifiant: str, *,
              project_id: str | None = None) -> Restauration:
    """Remettre le workspace, et l'état, dans l'état du point de reprise.

    Passe par Aegis en `data_migration` — la même catégorie que
    `snapshot_manager.restore_snapshot`, et pour la même raison : le §17.3
    du cahier la classe en validation obligatoire à tous les niveaux
    d'autonomie. Ce geste détruit tout ce qui a été fait depuis.
    """
    from backend.security.aegis_engine import ActionRequest, Verdict

    point = lire(identifiant)
    decision = aegis.evaluate(ActionRequest(
        action_type="data_migration",
        description=(f"Restaurer le workspace {point.workspace} au point de "
                     f"reprise {identifiant} ({point.motif or 'sans motif'})"),
        target_path=point.workspace, requesting_agent="hermes",
        project_id=project_id,
    ))
    if decision.verdict is not Verdict.ALLOW:
        raise CheckpointImpossible(
            f"restauration refusée : {decision.reason}")

    if point.mecanisme == "git":
        if not git_ref.existe(point.workspace, point.commit):
            raise CheckpointImpossible(
                f"le commit {point.commit[:12]} n'est plus dans le dépôt")
        ecart = git_ref.restaurer(point.workspace, point.commit)
    else:
        ecart = repli_fichiers.restaurer(point.workspace,
                                         _dossier(point.identifiant))

    etat_repris, motif = _restaurer_l_etat(aegis, point, project_id)
    return Restauration(
        checkpoint=point.identifiant, workspace=point.workspace,
        a_restaurer=ecart.a_restaurer, a_recreer=ecart.a_recreer,
        a_supprimer=ecart.a_supprimer, etat_repris=etat_repris,
        etat_non_repris=motif, applique=True)


def _restaurer_l_etat(aegis: Any, point: Checkpoint,
                      project_id: str | None) -> tuple[bool, str]:
    """Reprendre l'état de mission, et dire honnêtement si ça n'a pas pu.

    Les fichiers sont déjà revenus quand on arrive ici. Lever
    maintenant laisserait le workspace restauré et l'appelant persuadé
    que rien n'a eu lieu — le pire des trois états possibles. On rend
    donc un couple, et `Restauration` le porte jusqu'à l'appelant.
    """
    if not point.instantane:
        return False, "aucun état de mission n'avait été capturé"
    try:
        from backend.core import snapshot_manager

        snapshot_manager.restore_snapshot(aegis, point.instantane,
                                          project_id=project_id)
        return True, ""
    except Exception as exc:
        logger.warning("état de mission non repris pour %s", point.identifiant,
                       exc_info=True)
        return False, str(exc)


# ── Supprimer ────────────────────────────────────────────────────────

def supprimer(identifiant: str) -> bool:
    """Retirer un point de reprise et ce qu'il retenait.

    Pour le mécanisme git, retire aussi la référence : sans ça les objets
    resteraient protégés du ramasse-miettes indéfiniment, et le dépôt
    grossirait d'un point de reprise que plus personne ne peut lire.
    """
    try:
        point = lire(identifiant)
    except CheckpointIntrouvable:
        return False
    if point.mecanisme == "git" and point.commit:
        try:
            git_ref.supprimer(point.workspace, point.commit)
        except Exception:
            logger.warning("référence git non retirée pour %s", identifiant,
                           exc_info=True)
    shutil.rmtree(_dossier(identifiant), ignore_errors=True)
    return True


__all__ = ["Checkpoint", "CheckpointImpossible", "CheckpointIntrouvable",
           "DOSSIER", "PLAFOND_COPIE", "Restauration", "apercu", "lire",
           "lister", "prendre", "restaurer", "supprimer"]
