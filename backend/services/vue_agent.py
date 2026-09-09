"""Ce que le cerveau agentique porte, vu depuis Hermes OS (HOS-266).

Une **vue**, jamais une seconde autorité. Toutes les fonctions lisent ; il
n'y a pas d'écriture ici, et `test_la_vue_agent_n_ecrit_rien` le vérifie
sur l'arbre syntaxique — la même garde que `vue_operations` porte depuis
HOS-235, pour la même raison : une vue qui se met à écrire devient une
autorité concurrente sans que personne ne l'ait décidé.

## Pourquoi ce module existe

Le pont (HOS-265) savait négocier — dire *ce que le runtime peut faire* —
et rien d'autre. Il ne savait pas **demander**. Les capacités étaient donc
visibles et inertes : le cockpit affichait « sessions : complète » sans
pouvoir montrer une seule session, ce qui est précisément la moitié de
promesse que la règle anti-orphelin sanctionne.

Ce module transforme des méthodes négociées en surfaces produit, une par
une, et chacune n'existe ici que si elle a un consommateur frontend réel.

## Ce qu'il ne fait pas

Il ne reprend pas de session, n'en supprime aucune, n'active aucun toolset.
Ces gestes-là écrivent dans l'état de l'agent, et les poser demanderait de
répondre d'abord à une question que cette passe ne tranche pas : qui, de
Hermes OS ou de l'agent, est autorité sur cet état. Tant que la réponse
n'est pas écrite, la vue reste en lecture.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("hermes_os.services.vue_agent")

#: Au-delà, une liste devient un vidage de base plutôt qu'une surface : la
#: mesure du 2026-09-09 relève 200 sessions et 62 toolsets, et le cockpit
#: n'en montre utilement qu'une page.
LIMITE_PAR_DEFAUT = 100


def _pont():
    from backend.api.routes.bridge import pont

    return pont()


def _appeler(methode: str, params: Optional[dict] = None) -> dict:
    """Un appel, et ce qu'on en sait quand il échoue.

    Rend toujours une enveloppe `{disponible, erreur, ...}` plutôt que de
    lever : une panne du gateway ne doit pas rendre un écran de cockpit
    illisible, et surtout elle ne doit pas se lire comme « il n'y a rien ».
    C'est la même distinction que `NegociationRuntime.negociee`.
    """
    try:
        message = _pont().appeler(methode, params or {})
    except Exception as exc:  # noqa: BLE001 - une panne est un résultat
        logger.info("appel %s indisponible : %s", methode, exc)
        return {"disponible": False, "erreur": f"{type(exc).__name__}: {exc}"}
    erreur = message.get("error")
    if erreur is not None:
        return {"disponible": False,
                "erreur": f"{erreur.get('code')}: {erreur.get('message')}"}
    return {"disponible": True, "erreur": None,
            "resultat": message.get("result") or {}}


def _liste(methode: str, cle: str, limite: int,
           params: Optional[dict] = None) -> dict:
    """Une page, et la vérité sur ce qu'elle ne montre pas.

    `total` disait `len(elements)` — or `session.list` **plafonne à 200
    côté serveur**. HOS-266 affichait donc « 100 servis sur 200 » alors que
    200 était le plafond du gateway, pas le nombre de sessions. Un chiffre
    exact qui trompe, exactement ce que cette vue prétend éviter.

    On demande donc une page de plus que nécessaire : si le runtime la
    rend, c'est qu'il y en a davantage, et `tronque` le dit.
    """
    enveloppe = _appeler(methode, params)
    if not enveloppe["disponible"]:
        return {"disponible": False, "erreur": enveloppe["erreur"],
                "total": 0, "tronque": False, "elements": []}
    elements = enveloppe["resultat"].get(cle) or []
    if not isinstance(elements, list):
        elements = []
    tronque = len(elements) > limite
    return {"disponible": True, "erreur": None,
            "total": len(elements[:limite]), "tronque": tronque,
            "elements": elements[:limite]}


def sessions(limite: int = LIMITE_PAR_DEFAUT) -> dict:
    """Les sessions que l'agent a réellement tenues.

    `tronque` dit qu'il en reste au-delà de la page. Il remplace un `total`
    qui valait en réalité le **plafond du gateway** (200) et se lisait comme
    un décompte — un chiffre exact et faux, ce que cette vue existe pour
    éviter.
    """
    # `limite + 1` : ce que le runtime rend en trop prouve qu'il en reste.
    return _liste("session.list", "sessions", limite,
                  {"limit": limite + 1})


def toolsets(limite: int = LIMITE_PAR_DEFAUT) -> dict:
    """Les outils dont le cerveau dispose, et lesquels sont actifs.

    `enabled` est la donnée qui compte : un toolset présent et désactivé
    n'est pas un outil disponible, et c'est exactement la confusion qui a
    produit des missions « réussies » au-dessus d'un workspace vide.
    """
    return _liste("tools.list", "toolsets", limite)


def profils(limite: int = LIMITE_PAR_DEFAUT) -> dict:
    """Les profils — la primitive amont des Bots."""
    return _liste("profiles.list", "profiles", limite)


def delegation() -> dict:
    """L'état de la délégation : subagents actifs et bornes en vigueur."""
    enveloppe = _appeler("delegation.status")
    if not enveloppe["disponible"]:
        return {"disponible": False, "erreur": enveloppe["erreur"],
                "actifs": [], "en_pause": None,
                "profondeur_max": None, "enfants_max": None}
    r = enveloppe["resultat"]
    return {
        "disponible": True, "erreur": None,
        "actifs": r.get("active") or [],
        "en_pause": r.get("paused"),
        "profondeur_max": r.get("max_spawn_depth"),
        "enfants_max": r.get("max_concurrent_children"),
    }


def routines() -> dict:
    """Les tâches planifiées de l'agent (cron)."""
    enveloppe = _appeler("cron.manage")
    if not enveloppe["disponible"]:
        return {"disponible": False, "erreur": enveloppe["erreur"],
                "total": 0, "tronque": False, "elements": []}
    jobs = enveloppe["resultat"].get("jobs") or []
    return {"disponible": True, "erreur": None,
            "total": len(jobs), "tronque": False, "elements": jobs}


def historique(cle_stockee: str, limite: int = 200) -> dict:
    """Les messages d'une session stockee.

    Lire exige d'**activer** la session : `session.history` est
    `live=True`, comme `session.branch`. On demande donc au proprietaire
    d'ouvrir la session, puis de la lire — les deux gestes sont a lui.

    L'activation n'ecrit rien (mesure de G-18 : empreinte de `state.db`
    identique), ce qui laisse cette fonction dans une **vue** malgre
    l'appel a `session.resume`.
    """
    activation = _appeler("session.resume", {"session_id": cle_stockee})
    if not activation["disponible"]:
        return {"disponible": False, "erreur": activation["erreur"],
                "total": 0, "tronque": False, "elements": []}
    handle = activation["resultat"].get("session_id") or ""
    if not handle:
        return {"disponible": False,
                "erreur": "activation sans handle runtime",
                "total": 0, "tronque": False, "elements": []}
    return _liste("session.history", "messages", limite,
                  {"session_id": handle})


def vue_d_ensemble(limite: int = LIMITE_PAR_DEFAUT) -> dict[str, Any]:
    """Tout ce que le Center affiche, en une seule ouverture de gateway.

    Cinq appels séparés rouvriraient cinq fois la même connexion depuis le
    frontend ; le gateway coûte six secondes à froid, et le pont n'en
    garde qu'un. Une seule route, donc, et un seul aller-retour.
    """
    return {
        "sessions": sessions(limite),
        "toolsets": toolsets(limite),
        "profils": profils(limite),
        "delegation": delegation(),
        "routines": routines(),
    }
