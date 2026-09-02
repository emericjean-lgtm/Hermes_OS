"""Ce qui doit répondre après une installation (HOS-233).

## Ce que c'était

HOS-232 vérifiait deux choses : la racine d'état est un répertoire, et
`Registre().en_cours()` répond. C'est mieux qu'un `import hermes`, et
c'est encore trop peu — la mémoire, les missions, les points de reprise
et la configuration peuvent être corrompus sans que le registre bronche.

## Le tri-état, encore

Chaque contrôle rend `OK`, `ECHEC` ou `INDISPONIBLE`. Le troisième n'est
pas un échec : une installation neuve n'a **pas** de points de reprise, et
en exiger un ferait échouer la première mise à jour de tout le monde.

Mais il n'est pas un succès non plus, et c'est là que la règle se gagne :
`critique` distingue ce dont l'absence est normale de ce dont l'absence
est un défaut. Seul un `ECHEC` sur un contrôle critique déclenche le
retour arrière.

## Ce qui n'est pas vérifié, et pourquoi

Pas de démarrage de serveur, pas d'appel de modèle. Les deux prendraient
des minutes et dépendent de choses — port libre, Ollama en marche — qui
n'ont rien à voir avec la mise à jour. Un contrôle qui échoue pour une
raison étrangère fait revenir en arrière une installation saine.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

logger = logging.getLogger("hermes_os.maj.sante")


class Etat(str, Enum):
    OK = "ok"
    ECHEC = "echec"
    #: Rien à vérifier — une installation neuve, un composant absent.
    #: Ni succès ni échec.
    INDISPONIBLE = "indisponible"


@dataclass(frozen=True)
class Controle:
    nom: str
    etat: Etat
    detail: str = ""
    #: Un échec ici fait revenir en arrière. Faux pour ce dont
    #: l'indisponibilité comme l'échec sont supportables.
    critique: bool = True


@dataclass
class Rapport:
    """Un résultat structuré, exploitable par l'updater.

    Structuré et non booléen : « ça ne va pas » ne dit pas quoi restaurer
    ni quoi réparer, et c'est le rapport qu'on relira après un retour
    arrière pour comprendre.
    """

    controles: list[Controle] = field(default_factory=list)

    @property
    def sain(self) -> bool:
        """Aucun contrôle **critique** en échec.

        Les `INDISPONIBLE` ne comptent pas : une installation neuve n'a
        pas de points de reprise, et en exiger un ferait échouer la
        première mise à jour de tout le monde.
        """
        return not self.echecs

    @property
    def echecs(self) -> list[Controle]:
        return [c for c in self.controles
                if c.critique and c.etat is Etat.ECHEC]

    @property
    def indetermines(self) -> list[Controle]:
        return [c for c in self.controles if c.etat is Etat.INDISPONIBLE]

    def resume(self) -> str:
        parts = [f"{len([c for c in self.controles if c.etat is Etat.OK])} ok"]
        if self.echecs:
            parts.append(f"{len(self.echecs)} en échec : "
                         + ", ".join(c.nom for c in self.echecs))
        if self.indetermines:
            parts.append(f"{len(self.indetermines)} sans objet")
        return " — ".join(parts)

    def to_dict(self) -> dict:
        return {"sain": self.sain,
                "controles": [{"nom": c.nom, "etat": c.etat.value,
                               "detail": c.detail, "critique": c.critique}
                              for c in self.controles]}


def _essayer(nom: str, travail: Callable[[], Etat | tuple[Etat, str]], *,
             critique: bool = True) -> Controle:
    """Faire tourner un contrôle sans que son échec tue les suivants.

    Un rapport partiel ne dit pas ce qui va mal : il dit ce qui a été
    testé avant que ça casse. On veut les onze.
    """
    try:
        resultat = travail()
    except Exception as exc:
        return Controle(nom, Etat.ECHEC, f"{type(exc).__name__}: {exc}",
                        critique)
    if isinstance(resultat, tuple):
        return Controle(nom, resultat[0], resultat[1], critique)
    return Controle(nom, resultat, "", critique)


def verifier() -> Rapport:
    """Les invariants critiques de Hermes, après installation.

    Chacun **touche** à ce qu'il vérifie : ouvrir la base, lire une
    table, lister un dossier. Un contrôle qui se contenterait d'importer
    un module passerait sur une base corrompue — c'est exactement ce que
    HOS-232 faisait à moitié.
    """
    from pathlib import Path

    rapport = Rapport()

    def racine_d_etat() -> tuple[Etat, str]:
        from backend.core.etat import preserve_set, racine

        r = racine()
        if not r.is_dir():
            return Etat.ECHEC, f"{r} n'est pas un répertoire"
        manquants = [p.name for p in preserve_set() if not p.exists()]
        return Etat.OK, (f"racine {r}"
                         + (f", à créer : {manquants}" if manquants else ""))

    def ledger() -> tuple[Etat, str]:
        from backend.runs.registre import Registre

        registre = Registre()
        en_cours = registre.en_cours()
        return Etat.OK, f"{len(en_cours)} run(s) en cours"

    def base_applicative() -> tuple[Etat, str]:
        # La base SQLAlchemy : mémoire, approbations, projets, tâches.
        # `_add_missing_columns` y tourne, et c'est le mécanisme
        # d'évolution de schéma **vivant** de ce dépôt.
        from backend.core.config import get_settings
        from backend.memory.db import init_db, make_engine

        chemin = get_settings().sqlite_path
        if not Path(chemin).exists():
            return Etat.INDISPONIBLE, "base applicative pas encore créée"
        init_db(make_engine(chemin))
        return Etat.OK, chemin

    def approbations() -> tuple[Etat, str]:
        from sqlalchemy.orm import sessionmaker

        from backend.core.config import get_settings
        from backend.memory.db import make_engine
        from backend.security import approvals

        chemin = get_settings().sqlite_path
        if not Path(chemin).exists():
            return Etat.INDISPONIBLE, "pas de base"
        with sessionmaker(bind=make_engine(chemin))() as session:
            attente = approvals.list_approvals(session, status="pending")
        return Etat.OK, f"{len(attente)} en attente"

    def missions() -> tuple[Etat, str]:
        from backend.core.snapshot_manager import list_snapshots

        instantanes = list_snapshots()
        if not instantanes:
            return Etat.INDISPONIBLE, "aucun instantané de mission"
        return Etat.OK, f"{len(instantanes)} instantané(s)"

    def points_de_reprise() -> tuple[Etat, str]:
        from backend.checkpoints import lister

        points = lister()
        if not points:
            return Etat.INDISPONIBLE, "aucun point de reprise"
        # Lire vraiment le plus récent : un dossier présent ne prouve pas
        # qu'une fiche est lisible.
        return Etat.OK, f"{len(points)} point(s), dernier : {points[0].identifiant}"

    def configuration() -> tuple[Etat, str]:
        from backend.core.config import get_settings, load_models_config

        get_settings()
        roles = (load_models_config().get("roles") or {})
        if not roles:
            return Etat.ECHEC, "config/models.yaml ne déclare aucun rôle"
        return Etat.OK, f"{len(roles)} rôle(s)"

    def ral() -> tuple[Etat, str]:
        from backend.ral.capabilities import ChatCapability, CloudCapability
        from backend.ral.courtier import courtier

        courtier().etats()
        assert ChatCapability and CloudCapability
        return Etat.OK, "capacités et courtier chargés"

    def bus() -> tuple[Etat, str]:
        from backend.core.event_topics import BASELINE_TOPICS

        if len(BASELINE_TOPICS) < 50:
            return Etat.ECHEC, f"{len(BASELINE_TOPICS)} topics seulement"
        return Etat.OK, f"{len(BASELINE_TOPICS)} topics déclarés"

    def cerveau() -> tuple[Etat, str]:
        # La règle qui prime sur tout : l'interpréteur de Hermes Agent
        # est référencé **en absolu**, et une mise à jour ne doit pas
        # l'avoir déplacé.
        from backend.ral.adapters.hermes_agent_cli import HermesAgentCliConfig

        # `python_exe` est **absolu** et le reste : HOS-103. Le résoudre
        # depuis `sys.executable` lancerait `cli.py` sous l'interpréteur
        # de Hermes OS, qui n'a aucune de ses dépendances. Une mise à
        # jour ne doit pas l'avoir déplacé.
        chemin = Path(HermesAgentCliConfig().python_exe)
        if not chemin.exists():
            return Etat.INDISPONIBLE, f"agent non installé : {chemin}"
        return Etat.OK, str(chemin)

    for nom, travail, critique in (
        ("racine d'état", racine_d_etat, True),
        ("registre des runs", ledger, True),
        ("base applicative", base_applicative, True),
        ("approbations", approbations, True),
        ("configuration", configuration, True),
        ("bus d'événements", bus, True),
        ("RAL", ral, True),
        ("instantanés de mission", missions, False),
        ("points de reprise", points_de_reprise, False),
        # Non critique : Hermes OS démarre sans l'agent, et une mise à
        # jour de Hermes OS n'a pas à échouer parce que l'agent n'est pas
        # installé sur cette machine.
        ("cerveau (Hermes Agent)", cerveau, False),
    ):
        rapport.controles.append(_essayer(nom, travail, critique=critique))

    return rapport


__all__ = ["Controle", "Etat", "Rapport", "verifier"]
