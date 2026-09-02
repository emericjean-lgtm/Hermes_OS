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


# ── Les Control Rooms ────────────────────────────────────────────────

def _agents_du_superviseur() -> list[dict[str, Any]]:
    """Les agents, depuis la source que `GET /api/v1/agents` sert déjà.

    `AgentSupervisor` et non `core.agent_registry` : le second ne porte
    que les agents Ollama configurés, et s'y brancher aurait donné une
    seconde vérité sur ce qu'est un agent — exactement ce que ce jalon
    interdit.
    """
    from backend.agents import routes as routes_agents

    superviseur = getattr(routes_agents, "_supervisor", None)
    if superviseur is None:
        raise RuntimeError(
            "aucun superviseur d'agents — l'application n'est pas assemblée")
    fiches: list[dict[str, Any]] = []
    for a in superviseur.list_agents():
        fiches.append({
            "agent_id": a.agent_id,
            "name": a.name,
            "status": a.status.value,
            "capabilities": [c.value for c in a.capabilities],
            "preferred_runtime": a.preferred_runtime,
            "preferred_model": a.preferred_model,
            "total_tasks": a.total_tasks,
            "successful_tasks": getattr(a, "successful_tasks", 0),
            "current_task_id": getattr(a, "current_task_id", "") or "",
            "current_mission_id": getattr(a, "current_mission_id", "") or "",
        })
    return fiches


def _taux_mesure(reussies: int, total: int) -> dict[str, Any]:
    """Un taux de réussite, ou l'aveu qu'il n'y en a pas.

    `GET /api/v1/agents` rend `success_rate: 100.0` avec `total_tasks: 0`
    — un agent qui n'a **jamais rien fait** rapporté parfait. Et le
    Cockpit aggravait : `(agent.success_rate ?? 100)`, avec une barre de
    progression pleine.

    C'est le même mensonge que douze jalons ont chassé côté serveur, à sa
    dernière étape. Zéro tâche n'est pas cent pour cent : c'est *aucune
    mesure*, et un taux affiché sur rien fait choisir un agent sur une
    réputation qu'il n'a pas gagnée.
    """
    if total <= 0:
        return {"mesure": False, "taux": None, "total": 0,
                "detail": "aucune tâche exécutée — rien à mesurer"}
    return {"mesure": True, "taux": round(100.0 * reussies / total, 1),
            "total": total, "detail": f"{reussies}/{total}"}


def control_room(agent: str) -> dict[str, Any]:
    """Tout ce qu'on sait **réellement** d'un agent.

    Assemblée depuis les sources canoniques : le registre des agents pour
    l'identité et l'état, le registre des runs (HOS-221) pour ce qu'il a
    réellement exécuté. Aucun magasin neuf, aucun compteur calculé ici
    qui ne vienne de l'un des deux.
    """
    def lire() -> dict[str, Any]:
        from backend.runs.registre import Registre

        # `AgentSupervisor` est la source **canonique** : c'est elle que
        # `GET /api/v1/agents` sert déjà. `core.agent_registry` en est un
        # autre, qui ne porte que les agents Ollama configurés — s'y
        # brancher aurait donné une seconde vérité sur ce qu'est un
        # agent.
        fiche: dict[str, Any] | None = None
        for brut in _agents_du_superviseur():
            if agent in (str(brut.get("agent_id") or ""),
                         str(brut.get("name") or "")):
                fiche = brut
                break

        # Les runs que cet agent a portés. Le registre est la source :
        # `total_tasks` du registre d'agents est un compteur de processus,
        # celui-ci est une trace durable.
        tous = []
        try:
            base = Registre()
            for r in base.en_cours():
                if r.agent == agent or r.agent == (fiche or {}).get("name"):
                    tous.append(r)
        except Exception:
            logger.debug("registre des runs indisponible pour %s", agent,
                         exc_info=True)

        reussis = sum(1 for r in tous if r.statut.value == "reussi")
        return {
            "agent": agent,
            # `None` quand l'agent n'est pas au registre : c'est une
            # absence, pas un agent vide.
            "identite": fiche,
            "connu": fiche is not None,
            "runs_en_cours": [_run_en_dict(r) for r in tous],
            # Le taux du registre d'agents est **remplacé** par une mesure
            # tri-état : voir `_taux_mesure`.
            "reussite": _taux_mesure(
                reussis if tous else int((fiche or {}).get("successful_tasks") or 0),
                len(tous) if tous else int((fiche or {}).get("total_tasks") or 0)),
            # La confiance vient de son propre système et dit déjà
            # « unknown » quand elle ne sait pas — on la relaie telle
            # quelle plutôt que de la réinterpréter.
            "confiance": {
                "score": (fiche or {}).get("trust_score"),
                "niveau": (fiche or {}).get("trust_level"),
            },
        }

    return _bloc("control_room", "backend.core.agent_registry + backend.runs.registre",
                 lire)


def control_rooms() -> dict[str, Any]:
    """Une Control Room par agent connu."""
    def lire() -> list[dict[str, Any]]:
        salles: list[dict[str, Any]] = []
        for brut in _agents_du_superviseur():
            nom = str(brut.get("name") or brut.get("agent_id") or "")
            if not nom:
                continue
            bloc = control_room(nom)
            if bloc["disponible"]:
                salles.append(bloc["donnees"])
        return salles

    return _bloc("control_rooms",
                 "backend.core.agent_registry + backend.runs.registre", lire)


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


__all__ = ["approbations", "contrat_du_run", "control_room", "control_rooms",
           "fournisseurs", "installation",
           "lignee", "points_de_reprise", "runs_de_la_mission",
           "vue_d_ensemble"]
