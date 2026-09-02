"""Ce que douze jalons ont produit, enfin lisible (HOS-234).

## Mesuré avant d'écrire

Aucune route n'expose le registre des runs (J5), le contrat, les points
de reprise (J7), la portée des approbations (J8), les causes d'échec
(J9), le pare-feu de données (J11), le courtier de quotas (J12), le
relais (J13), la boucle (J14) ni la mise à jour (J16). Douze jalons de
travail, invisibles à toute interface.

Ce qui existe et qu'il ne faut **pas** refaire : `MissionControlService`
(1 242 lignes) et son API, avec un WebSocket d'événements. Ce module s'y
branche.

## Une vue, jamais un second runtime

Lecture seule, entièrement. Aucune écriture, aucun magasin nouveau,
aucun compteur calculé ici qui ne vienne d'un système réel. Un test sur
l'arbre syntaxique le tient : ce module n'appelle rien qui commence par
`ouvrir`, `terminer`, `enregistrer`, `prendre`, `restaurer` ou
`appliquer`.

La raison n'est pas esthétique. Une vue qui écrit devient un second
chemin vers l'état, et deux chemins vers l'état, c'est la question
« lequel fait foi ? » à chaque incident.

## Chaque section dit d'où elle vient

`source` accompagne chaque bloc. Ce n'est pas de la décoration : le
frontend a déjà eu des compteurs fabriqués — `deployment-center` dormait
1 500 ms et rendait `Math.random() * 20 + 30`, `model-intelligence-center`
attendait 600–1 000 ms avant de répondre — et le commentaire de
`telemetry-trace.tsx` dit ce qu'on en a retenu : « `Math.random()` would
have made a prettier picture and a dishonest one ».

Une vue qui nomme ses sources rend la fabrication visible au relecteur
suivant.

## Ce qui est absent est dit absent

Un système indisponible rend `disponible: false` avec sa raison, jamais
un zéro. Un zéro se lit « rien ne s'est passé » ; une indisponibilité se
lit « on ne sait pas ». C'est la règle tri-état de HOS-222, appliquée à
l'affichage — et c'est là qu'elle compte le plus, parce que c'est là
qu'un humain décide.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger("hermes_os.services.vue")


def _bloc(nom: str, source: str, lecture: Callable[[], Any]) -> dict[str, Any]:
    """Lire une section, ou dire pourquoi on ne sait pas.

    Une section qui lève ne fait pas tomber la vue : les autres sont
    justement ce qu'on regarde quand une chose va mal.
    """
    try:
        return {"disponible": True, "source": source, "donnees": lecture()}
    except Exception as exc:
        logger.debug("section %s indisponible", nom, exc_info=True)
        return {"disponible": False, "source": source,
                "raison": f"{type(exc).__name__}: {exc}", "donnees": None}


# ── Les runs, leur lignée, leurs causes ──────────────────────────────

def _run_en_dict(run: Any) -> dict[str, Any]:
    return {
        "identifiant": run.identifiant,
        "mission": run.mission,
        "objectif": run.objectif,
        "statut": run.statut.value,
        # `None` et non « inconnue » : une colonne vide se lit « on ne
        # sait pas », une étiquette se lit comme un diagnostic posé
        # (HOS-225).
        "cause": run.cause.value if run.cause else None,
        "raison": run.raison,
        "modele": run.modele,
        "runtime": run.runtime,
        "fournisseur": run.fournisseur,
        "agent": run.agent,
        "workspace": run.workspace,
        "projet": run.projet,
        "tentative": run.tentative,
        "parent": run.parent,
        "motif_de_reprise": run.motif_de_reprise,
        "jetons_entree": run.jetons_entree,
        "jetons_sortie": run.jetons_sortie,
        "cout": run.cout,
        "cree_le": run.cree_le,
        "demarre_le": run.demarre_le,
        "fini_le": run.fini_le,
        "contrat": bool(run.contrat),
    }


def runs_de_la_mission(mission: str) -> dict[str, Any]:
    """Les tentatives d'une mission, dans l'ordre."""
    def lire() -> list[dict[str, Any]]:
        from backend.runs.registre import Registre

        return [_run_en_dict(r) for r in Registre().de_la_mission(mission)]

    return _bloc("runs", "backend.runs.registre", lire)


def lignee(run: str) -> dict[str, Any]:
    """La chaîne des tentatives, de la première à celle-ci.

    C'est la question à laquelle la nuit du 29 au 30 août n'a pas su
    répondre : « avec quel modèle, et pourquoi le premier essai a
    raté ? ».
    """
    def lire() -> list[dict[str, Any]]:
        from backend.runs.registre import Registre

        return [_run_en_dict(r) for r in Registre().lignee(run)]

    return _bloc("lignee", "backend.runs.registre.lignee", lire)


def contrat_du_run(run: str) -> dict[str, Any]:
    """Ce qui devait être vrai à la fin, et où en est chaque critère."""
    def lire() -> dict[str, Any] | None:
        from backend.runs.contrat import Contrat
        from backend.runs.registre import Registre

        entree = Registre().lire(run)
        if entree is None or not entree.contrat:
            return None
        contrat = Contrat.from_json(entree.contrat)
        return {
            "objectif": contrat.objectif,
            "tenu": contrat.tenu,
            "resume": contrat.resume(),
            "criteres": [c.to_dict() for c in contrat.criteres],
            # Séparés du compteur : un critère invérifiable n'est pas un
            # critère échoué, et les fondre ferait lire une ignorance
            # comme un constat (HOS-222).
            "inverifiables": [c.texte for c in contrat.inverifiables],
            "violes": [c.texte for c in contrat.violes],
        }

    return _bloc("contrat", "backend.runs.contrat", lire)


# ── Les points de reprise ────────────────────────────────────────────

def points_de_reprise(workspace: str | None = None) -> dict[str, Any]:
    def lire() -> list[dict[str, Any]]:
        from backend.checkpoints import lister

        return [
            {"identifiant": p.identifiant, "workspace": p.workspace,
             "motif": p.motif, "mission": p.mission, "run": p.run,
             "mecanisme": p.mecanisme, "fichiers": p.fichiers,
             "cree_le": p.cree_le,
             # Le couple : un point de reprise sans état de mission ne
             # ramène que la moitié (HOS-223).
             "avec_etat": bool(p.instantane)}
            for p in lister(workspace)
        ]

    return _bloc("checkpoints", "backend.checkpoints", lire)


# ── Les fournisseurs et leurs écarts ─────────────────────────────────

def fournisseurs() -> dict[str, Any]:
    """Qui est disponible, qui est écarté, et pour combien de temps."""
    def lire() -> dict[str, Any]:
        from backend.ral import fournisseurs as registre_cloud
        from backend.ral.courtier import courtier

        broker = courtier()
        configures = sorted(registre_cloud.fournisseurs())
        etats = broker.etats()
        return {
            "configures": configures,
            # Aucun fournisseur configuré est l'état **normal** : aucune
            # clé n'est posée par défaut. Le dire évite de le lire comme
            # une panne.
            "aucun_configure": not configures,
            "etats": [
                {"fournisseur": nom, "etat": v.etat.value,
                 "dans_s": round(v.dans_s, 1), "raison": v.raison}
                for nom, v in sorted(etats.items())
            ],
        }

    return _bloc("fournisseurs", "backend.ral.courtier", lire)


# ── Les approbations, avec leur portée ───────────────────────────────

def approbations() -> dict[str, Any]:
    """Ce qui attend un humain, et ce qu'une portée accordée couvre."""
    def lire() -> dict[str, Any]:
        from sqlalchemy.orm import sessionmaker

        from backend.core.config import get_settings
        from backend.memory.db import make_engine
        from backend.security import approvals

        fabrique = sessionmaker(bind=make_engine(get_settings().sqlite_path))
        with fabrique() as session:
            attente = approvals.list_approvals(session, status="pending")
            accordees = approvals.list_approvals(session, status="approved")
            return {
                "en_attente": [approvals.to_dict(e) for e in attente],
                # Les portées vivantes séparément : une ligne qui
                # autorise un dossier entier ne se lit pas comme une qui
                # autorise une action (HOS-224).
                "portees_vivantes": [
                    approvals.to_dict(e) for e in accordees
                    if (e.portee or "") == approvals.PORTEE_ARBORESCENCE
                ],
            }

    return _bloc("approbations", "backend.security.approvals", lire)


# ── L'installation ───────────────────────────────────────────────────

def installation() -> dict[str, Any]:
    """La version installée, et ce que le self-check en dit."""
    def lire() -> dict[str, Any]:
        from backend.core.etat import racine
        from backend.maj.sante import verifier
        from backend.maj.version import VERSION, lire_version_installee

        rapport = verifier()
        installee = lire_version_installee()
        return {
            "version_du_code": VERSION,
            # Vide n'est pas une erreur : une installation antérieure au
            # versionnement (HOS-232).
            "version_installee": installee or None,
            "racine_d_etat": str(racine()),
            "sante": rapport.to_dict(),
        }

    return _bloc("installation", "backend.maj", lire)


# ── La vue d'ensemble ────────────────────────────────────────────────

def vue_d_ensemble() -> dict[str, Any]:
    """Tout ce qu'une console d'opérations regarde en premier.

    Assemblée ici plutôt que côté frontend pour une raison mesurée : un
    frontend qui compose lui-même finit par calculer, et calculer côté
    affichage est exactement ce qui a produit les compteurs fabriqués
    que ce dépôt a dû retirer.
    """
    from backend.runs.registre import Registre

    def runs_recents() -> dict[str, Any]:
        registre = Registre()
        actifs = [_run_en_dict(r) for r in registre.en_cours()]
        return {"en_cours": actifs, "nombre_en_cours": len(actifs)}

    return {
        "runs": _bloc("runs", "backend.runs.registre", runs_recents),
        "fournisseurs": fournisseurs(),
        "approbations": approbations(),
        "points_de_reprise": points_de_reprise(),
        "installation": installation(),
    }


__all__ = ["approbations", "contrat_du_run", "fournisseurs", "installation",
           "lignee", "points_de_reprise", "runs_de_la_mission",
           "vue_d_ensemble"]
