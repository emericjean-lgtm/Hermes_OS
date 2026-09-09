"""Demander à Hermes Agent d'écrire dans son propre état (G-18, HOS-267).

## Le contrat d'autorité, tel que la mesure l'a établi

Hermes Agent est **seul autorité** sur `state.db` — 114 Mio sous son home,
son schéma, son WAL, ses transactions. Hermes OS ne l'ouvre pas, ne le lit
pas et ne l'écrit pas. Il *demande*, par l'API que l'agent expose pour ça.

Ce n'est pas une position de principe, c'est ce que la mesure a montré :

- `session.resume` **ne mute rien**. Empreinte de `state.db` identique
  avant/après ; seuls `-wal` et `-shm` bougent, ce qui est la comptabilité
  de lecture de SQLite. C'est une *activation runtime*, et son handle meurt
  avec le processus — `4001 session not found` après redémarrage, mesuré.
  Le présenter comme durable serait un mensonge d'interface.
- `session.branch` **mute vraiment** : contenu de `state.db` changé,
  nouvelle clé retrouvée par un processus neuf. Et elle est **additive** —
  la session parente reste intacte.

## Pourquoi ceci n'est pas une seconde autorité

Trois choses distinctes, trois propriétaires :

    la conversation stockee      -> Hermes Agent   (state.db)
    la session vivante           -> le processus gateway (ephemere)
    le recit de ce qu'on a demande -> Hermes OS    (son bus d'evenements)

Hermes OS ne revendique que la troisième. Tracer sa propre demande dans son
propre journal n'est pas posséder l'état de l'agent : c'est répondre de ses
actes, ce qu'aucune autre couche ne peut faire à sa place. L'inverse — ne
rien tracer — laisserait une écriture réelle sans trace côté OS, ce que le
Run Ledger interdit partout ailleurs.

## Ce que ce module refuse de faire

Il ne fabrique aucune API. `MUTATIONS_CONNUES` est courte parce qu'elle ne
contient que ce que le runtime sert réellement, mesuré ; une méthode
absente est refusée avant tout envoi.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("hermes_os.services.mutations_agent")


def _pont():
    from backend.api.routes.bridge import pont

    return pont()


def _tracer(topic: str, charge: dict) -> None:
    """Le journal de Hermes OS, jamais celui de l'agent.

    Best-effort : une trace qui échoue ne doit pas annuler une mutation
    déjà appliquée — l'inverse laisserait l'état de l'agent en avance sur
    ce que Hermes OS croit avoir fait, ce qui est la pire des deux
    incohérences.
    """
    try:
        from backend.core.event_hub import get_event_hub

        get_event_hub().publish(topic, charge)
    except Exception:  # noqa: BLE001
        logger.debug("trace %s impossible", topic, exc_info=True)


def brancher_session(cle_stockee: str, titre: str = "") -> dict[str, Any]:
    """Demande à l'agent de brancher une session stockée.

    `cle_stockee` est la clé de `state.db` (celle que `session.list` rend),
    pas un handle runtime. La branche exige pourtant une session **vivante**
    (`session.branch` est `live=True`), d'où l'activation préalable : on
    demande d'abord au propriétaire d'ouvrir la session, puis de la
    brancher. Les deux gestes sont à lui ; aucun n'est le nôtre.

    Rend `{applique, erreur, ...}` — jamais une exception pour un refus du
    runtime. Un refus est un résultat, et il doit se lire comme tel dans
    l'interface plutôt que comme une panne.
    """
    demande = {"methode": "session.branch", "cle_stockee": cle_stockee,
               "titre": titre}
    _tracer("bridge.mutation.demandee", demande)

    pont = _pont()
    try:
        activation = pont.appeler("session.resume",
                                  {"session_id": cle_stockee}, timeout=120)
    except Exception as exc:  # noqa: BLE001
        return _refus(demande, f"activation impossible : {exc}")
    if "error" in activation:
        erreur = activation["error"]
        return _refus(demande,
                      f"activation refusee ({erreur.get('code')}): "
                      f"{erreur.get('message')}")

    handle = (activation.get("result") or {}).get("session_id") or ""
    if not handle:
        return _refus(demande, "activation sans handle runtime")

    params: dict[str, Any] = {"session_id": handle}
    if titre.strip():
        params["name"] = titre.strip()
    try:
        reponse = pont.demander_mutation("session.branch", params, timeout=120)
    except Exception as exc:  # noqa: BLE001
        return _refus(demande, f"{type(exc).__name__}: {exc}")
    if "error" in reponse:
        erreur = reponse["error"]
        return _refus(demande,
                      f"refus du runtime ({erreur.get('code')}): "
                      f"{erreur.get('message')}")

    r = reponse.get("result") or {}
    applique = {
        "applique": True, "erreur": None,
        "cle_stockee": r.get("stored_session_id"),
        "parent": r.get("parent"),
        "titre": r.get("title"),
        "messages": r.get("message_count"),
    }
    _tracer("bridge.mutation.appliquee",
            {**demande, "resultat": {k: applique[k]
                                     for k in ("cle_stockee", "parent")}})
    return applique


def renommer_session(cle_stockee: str, titre: str) -> dict[str, Any]:
    """Demande a l'agent de renommer une session stockee.

    Deuxieme mutation du contrat G-18, et elle en verifie l'extensibilite :
    meme enchainement — activation par le proprietaire, puis mutation — et
    meme regle, un refus du runtime est un resultat.
    """
    titre = titre.strip()
    demande = {"methode": "session.title", "cle_stockee": cle_stockee,
               "titre": titre}
    _tracer("bridge.mutation.demandee", demande)
    if not titre:
        return _refus(demande, "un titre vide effacerait le nom sans le "
                               "remplacer")

    pont = _pont()
    try:
        activation = pont.appeler("session.resume",
                                  {"session_id": cle_stockee}, timeout=120)
    except Exception as exc:  # noqa: BLE001
        return _refus(demande, f"activation impossible : {exc}")
    if "error" in activation:
        erreur = activation["error"]
        return _refus(demande, f"activation refusee ({erreur.get('code')}): "
                               f"{erreur.get('message')}")
    handle = (activation.get("result") or {}).get("session_id") or ""
    if not handle:
        return _refus(demande, "activation sans handle runtime")

    try:
        reponse = pont.demander_mutation(
            "session.title", {"session_id": handle, "title": titre},
            timeout=60)
    except Exception as exc:  # noqa: BLE001
        return _refus(demande, f"{type(exc).__name__}: {exc}")
    if "error" in reponse:
        erreur = reponse["error"]
        return _refus(demande, f"refus du runtime ({erreur.get('code')}): "
                               f"{erreur.get('message')}")

    applique = {"applique": True, "erreur": None,
                "cle_stockee": cle_stockee, "parent": None,
                "titre": (reponse.get("result") or {}).get("title") or titre,
                "messages": None}
    _tracer("bridge.mutation.appliquee",
            {**demande, "resultat": {"cle_stockee": cle_stockee}})
    return applique


#: Ce que le runtime accepte comme action ; toute autre est refusee avant
#: envoi. Mesure : `tools.configure` rend `4017 unknown tools action` pour
#: le reste, mais un refus apres coup laisse croire qu'on a essaye.
ACTIONS_TOOLSET = {"enable", "disable"}


def basculer_toolset(nom: str, actif: bool) -> dict[str, Any]:
    """Demande a l'agent d'activer ou de desactiver un toolset.

    Troisieme mutation du contrat, et la premiere qui ne touche pas
    `state.db` : elle ecrit `config.yaml`, que **tous** les processus agent
    relisent — donc les missions aussi. C'est ce qui la distingue de
    `delegation.pause`, mesuree comme locale au gateway et pour cette
    raison jamais offerte au produit.

    Consequence a connaitre : le premier appel **fige les defauts du jour**
    dans le fichier. Le round-trip YAML materialise les toolsets implicites
    en listes explicites — il n'enleve rien (verifie par diff) mais un
    defaut amont qui changerait plus tard ne s'appliquerait plus.
    """
    action = "enable" if actif else "disable"
    nom = nom.strip()
    demande = {"methode": "tools.configure", "toolset": nom, "action": action}
    _tracer("bridge.mutation.demandee", demande)
    if not nom:
        return _refus(demande, "aucun toolset nomme")

    try:
        reponse = _pont().demander_mutation(
            "tools.configure", {"action": action, "names": [nom]}, timeout=90)
    except Exception as exc:  # noqa: BLE001
        return _refus(demande, f"{type(exc).__name__}: {exc}")
    if "error" in reponse:
        erreur = reponse["error"]
        return _refus(demande, f"refus du runtime ({erreur.get('code')}): "
                               f"{erreur.get('message')}")

    r = reponse.get("result") or {}
    # `changed` vide avec un `unknown` non vide : le runtime a repondu 200
    # sans rien faire. Le lire comme un succes afficherait un basculement
    # qui n'a pas eu lieu.
    if nom in (r.get("unknown") or []):
        return _refus(demande, f"toolset inconnu du runtime : {nom}")
    if nom not in (r.get("changed") or []):
        return _refus(demande, "le runtime n'a rien change")

    applique = {"applique": True, "erreur": None, "toolset": nom,
                "actif": actif,
                "toolsets_actifs": r.get("enabled_toolsets") or []}
    _tracer("bridge.mutation.appliquee",
            {**demande, "resultat": {"toolset": nom, "actif": actif}})
    return applique


def _refus(demande: dict, raison: str) -> dict[str, Any]:
    """Un refus est un résultat, pas une panne — et il se trace aussi."""
    logger.info("mutation refusee : %s", raison)
    _tracer("bridge.mutation.refusee", {**demande, "raison": raison})
    return {"applique": False, "erreur": raison, "cle_stockee": None,
            "parent": None, "titre": None, "messages": None}
