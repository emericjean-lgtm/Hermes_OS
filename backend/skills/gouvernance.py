r"""Ce que le cycle de vie des Skills a réellement fait, vérifié (G-35, HOS-283).

L'agent **possède** ses Skills et tient déjà le dossier de leur cycle de
vie, sur son disque, sous `<HERMES_HOME>/skills/.hub/` :

    audit.log   une ligne par opération : INSTALL, BLOCKED, UNINSTALL
    lock.json   ce que le hub a posé — source, identifiant, niveau de
                confiance, verdict du scanner, empreinte, findings

Rien dans Hermes OS ne lisait ce dossier. C'est la quatrième lecture du
disque de l'agent, après les compétences (HOS-274), leur provenance
(HOS-275) et les mutations observées (HOS-281), et la posture ne change
pas : **lire, jamais écrire, jamais recopier.**

## Pourquoi vérifier, et pas seulement lire

`skills.manage install` répond `{"installed": true}` dans tous les cas.
Ce n'est pas une négligence du gateway : `do_install` est annoté `-> None`
et rend `None` sur **tous** ses chemins, succès compris. Il n'y a donc
aucune valeur de retour à corriger en amont — la vérité n'est pas dans le
compte rendu, elle est sur le disque.

Mesure du 2026-09-10, sur un `HERMES_HOME` de substitution :

    official/devops/actual-setup      posée   INSTALL … dangerous
    skills-sh/mindrally/…/docker      posée   INSTALL … safe
    skills-sh/bobmatnyc/…/docker      RIEN    BLOCKED … dangerous 25_findings
    docker, skill-docker, …           RIEN    aucune ligne
    la même, déjà posée, sans --force RIEN    aucune ligne

Deux verdicts `dangerous`, deux issues opposées — la première est passée
parce que sa source est `builtin`, la seconde a été bloquée parce qu'elle
est `community`. Un écran qui dirait seulement « installée » tairait
exactement ce qu'un opérateur a besoin de savoir.

## Ce que la vérification peut affirmer, et ce qu'elle ne peut pas

`content_hash` est une SHA-256 canonique sur (chemin POSIX, octets), et
elle se **recalcule ici** — vérifié le 2026-09-10, à l'octet près, sur
deux compétences posées. Hermes OS peut donc dire si ce qui est sur le
disque est bien ce que l'agent a scanné, sans importer un module de
l'agent : le retrait de compatibilité du 2026-09-14 ne l'atteint pas.

Ce qu'elle ne peut pas : voir un refus **silencieux**. Trois des cas
mesurés n'écrivent rien, nulle part — ni fichier, ni ligne d'audit. Aucun
lecteur *a posteriori* ne peut les distinguer d'une opération jamais
demandée, et l'agent lui-même ne les garde pas. Les voir demanderait
d'observer avant/après autour de l'appel, donc de le déclencher — ce que
G-35 laisse en DEFER, faute d'approbateur joignable.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("hermes_os.skills.gouvernance")

#: L'état d'une compétence posée par le hub, confronté au disque. Borné,
#: comme les catégories de provenance de G-27 : une chaîne libre laisserait
#: l'écran broder sur ce qu'il n'a pas mesuré.
CONFORME = "conforme"
ALTEREE = "alteree"
ANNONCEE_ABSENTE = "annoncee_absente"

#: Les actions que l'agent écrit dans son journal. Toute autre valeur est
#: rendue telle quelle plutôt que rangée dans l'une de celles-ci.
INSTALL = "INSTALL"
BLOCKED = "BLOCKED"
UNINSTALL = "UNINSTALL"


@dataclass(frozen=True)
class Operation:
    """Une ligne du journal de l'agent, telle qu'elle est écrite."""

    horodatage: str
    action: str
    skill: str
    source: str
    confiance: str
    verdict: str
    detail: str

    def as_dict(self) -> dict:
        return {"horodatage": self.horodatage, "action": self.action,
                "skill": self.skill, "source": self.source,
                "confiance": self.confiance, "verdict": self.verdict,
                "detail": self.detail}


@dataclass(frozen=True)
class Posee:
    """Une compétence que le hub a posée, et ce que le disque en dit."""

    nom: str
    source: str
    identifiant: str
    confiance: str
    verdict: str
    chemin: str
    empreinte_attendue: str
    #: `""` quand le dossier n'est pas là — jamais un zéro ni un « ok ».
    empreinte_reelle: str
    etat: str
    findings: dict[str, int]

    def as_dict(self) -> dict:
        return {"nom": self.nom, "source": self.source,
                "identifiant": self.identifiant, "confiance": self.confiance,
                "verdict": self.verdict, "chemin": self.chemin,
                "empreinte_attendue": self.empreinte_attendue,
                "empreinte_reelle": self.empreinte_reelle,
                "etat": self.etat, "findings": self.findings}


def _competences() -> Path:
    """Le dossier des compétences de l'**agent**, pas la racine d'état.

    Le nom compte, et il a coûté un rouge. Appelée `_racine`, cette
    fonction était prise pour l'accesseur de la racine d'état de Hermes OS
    par `test_tout_ce_qui_vit_sous_la_racine_est_preserve`, qui cherche
    dans tout `backend/` un appel a l'accesseur de racine suivi d'un
    litteral de dossier. (Ce commentaire ne reecrit pas le motif : la garde
    lit le texte source, et l'ecrire ici la declencherait — elle l'a fait.)
    La garde exigeait alors
    que `.hub` entre dans `preserve_set()` — or `.hub` vit sous
    `%LOCALAPPDATA%\\hermes`, chez l'agent, et la mise à jour de Hermes OS
    n'y touche jamais. L'y inscrire aurait été une fausse promesse, sur un
    dossier que cette mise à jour ne voit même pas.
    """
    from backend.skills.registre import racine_des_competences

    return racine_des_competences()


def _hub() -> Path:
    return _competences() / ".hub"


def empreinte(dossier: Path) -> str:
    """`content_hash` de l'agent, recalculée ici.

    SHA-256 sur les couples (chemin relatif POSIX, octets), **ordonnés par
    la chaîne** du chemin. L'ordre est le détail qui compte : trier des
    `Path` est insensible à la casse sous Windows, et l'agent porte le
    commentaire de l'incident que cela lui a coûté — chaque compétence
    installée se déclarait périmée pour toujours. Trier les chaînes garde
    les deux côtés symétriques.

    Réimplémentée plutôt qu'importée : `plugin_compat` désactive au
    2026-09-14 tout code externe qui importe les internes de l'agent, et
    une empreinte de gouvernance ne doit pas mourir avec une date.
    """
    h = hashlib.sha256()
    for rel, chemin in sorted((p.relative_to(dossier).as_posix(), p)
                              for p in dossier.rglob("*") if p.is_file()):
        h.update(rel.encode("utf-8") + b"\x00")
        h.update(chemin.read_bytes())
    return "sha256:" + h.hexdigest()[:16]


#: L'horodatage que l'agent ecrit : `%Y-%m-%dT%H:%M:%SZ`.
_HORODATAGE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _est_une_ligne(morceaux: list[str]) -> bool:
    """Une ligne d'audit se reconnait a sa FORME, pas a son nombre de mots.

    Compter les mots ne gardait rien : « ceci n'est pas une ligne d'audit »
    en fait six, et devenait une operation `INSTALL n'est` d'une source
    `pas`. Trouve par la garde qui devait justement empecher qu'on devine.

    Deux marqueurs suffisent et ne se produisent pas par accident : un
    horodatage ISO en Z, et un couple `source:confiance`.
    """
    return bool(_HORODATAGE.match(morceaux[0])) and ":" in morceaux[3]


def journal(limite: int = 200) -> list[Operation]:
    """Les opérations écrites par l'agent, de la plus récente à la plus
    ancienne.

    Format : `horodatage ACTION nom source:confiance verdict [détail]`.
    Une ligne qui ne s'y conforme pas est rendue avec `action` à `""` et
    la ligne entière en `detail` : la deviner reviendrait à inventer une
    opération, et c'est exactement ce que cette passe refuse.
    """
    chemin = _hub() / "audit.log"
    try:
        lignes = chemin.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        logger.debug("journal du hub illisible : %s", chemin, exc_info=True)
        return []

    operations: list[Operation] = []
    for ligne in lignes:
        ligne = ligne.strip()
        if not ligne:
            continue
        morceaux = ligne.split(" ", 5)
        if len(morceaux) < 5 or not _est_une_ligne(morceaux):
            operations.append(Operation("", "", "", "", "", "", ligne))
            continue
        horodatage, action, skill, origine, verdict = morceaux[:5]
        source, _, confiance = origine.partition(":")
        operations.append(Operation(
            horodatage=horodatage, action=action, skill=skill,
            source=source, confiance=confiance, verdict=verdict,
            detail=morceaux[5] if len(morceaux) > 5 else ""))
    return list(reversed(operations))[:limite]


def _verrou() -> dict[str, Any]:
    try:
        contenu = json.loads((_hub() / "lock.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.debug("verrou du hub illisible", exc_info=True)
        return {}
    return contenu.get("installed", {}) if isinstance(contenu, dict) else {}


def _findings(entree: dict) -> dict[str, int]:
    """Les findings du scanner, comptés par sévérité.

    Comptés et non recopiés : le détail d'un finding porte le chemin et
    l'extrait du fichier incriminé, et l'écran n'en a pas besoin pour dire
    « bloquée sur 25 findings dont 3 critiques ». Le dossier complet reste
    chez son propriétaire.
    """
    provenance = entree.get("scan_provenance") or {}
    comptes: dict[str, int] = {}
    for f in provenance.get("findings") or []:
        if isinstance(f, dict):
            severite = str(f.get("severity") or "inconnue")
            comptes[severite] = comptes.get(severite, 0) + 1
    return comptes


def posees() -> list[Posee]:
    """Ce que le hub a posé, confronté à ce que le disque porte.

    Le cœur de la passe : `install_path` et `content_hash` sont ce que
    l'agent a **enregistré** ; le dossier et son empreinte recalculée sont
    ce qui **est**. Les trois états couvrent les trois écarts possibles, et
    aucun ne se déduit d'un autre.
    """
    racine = _competences()
    resultat: list[Posee] = []
    for nom, entree in sorted(_verrou().items()):
        if not isinstance(entree, dict):
            continue
        chemin_relatif = str(entree.get("install_path") or "")
        dossier = racine / chemin_relatif if chemin_relatif else racine / nom
        attendue = str(entree.get("content_hash") or "")
        if not dossier.is_dir():
            reelle, etat = "", ANNONCEE_ABSENTE
        else:
            try:
                reelle = empreinte(dossier)
            except OSError:
                logger.debug("empreinte illisible : %s", dossier, exc_info=True)
                reelle = ""
            etat = CONFORME if reelle and reelle == attendue else ALTEREE
        resultat.append(Posee(
            nom=nom,
            source=str(entree.get("source") or ""),
            identifiant=str(entree.get("identifier") or ""),
            confiance=str(entree.get("trust_level") or ""),
            verdict=str(entree.get("scan_verdict") or ""),
            chemin=chemin_relatif,
            empreinte_attendue=attendue,
            empreinte_reelle=reelle,
            etat=etat,
            findings=_findings(entree)))
    return resultat


def vue(limite: int = 200) -> dict:
    """La vue produit : le dossier du cycle de vie, vérifié.

    `dossier_lisible` distingue « l'agent n'a jamais rien posé par le hub »
    de « Hermes OS n'a pas su lire son dossier ». Sans lui, un écran vide
    dirait la même chose dans les deux cas, et le second est une panne.
    """
    hub = _hub()
    ops = journal(limite)
    installees = posees()
    return {
        "dossier_lisible": hub.is_dir(),
        "racine": str(hub),
        "operations": [o.as_dict() for o in ops],
        "posees": [p.as_dict() for p in installees],
        "alertes": {
            "alterees": sum(1 for p in installees if p.etat == ALTEREE),
            "absentes": sum(1 for p in installees if p.etat == ANNONCEE_ABSENTE),
            "bloquees": sum(1 for o in ops if o.action == BLOCKED),
        },
        # Ce que ce lecteur ne peut pas voir, dit plutôt que tu. Trois des
        # cinq issues mesurees d'`install` n'ecrivent rien nulle part.
        "angle_mort": (
            "un refus silencieux — nom introuvable, deja installee sans "
            "--force — n'ecrit ni fichier ni ligne d'audit : aucun lecteur "
            "a posteriori ne peut le distinguer d'une operation jamais "
            "demandee"),
    }
