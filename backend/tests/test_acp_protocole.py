"""Les deux sens numérotent dans le même espace (HOS-138).

ACP est bidirectionnel : Hermes OS envoie des requêtes à l'agent, et l'agent
en envoie au client — `session/request_permission` avant toute écriture. Les
deux numérotent leurs requêtes indépendamment, l'agent à partir de 0, le
client à partir de 1. **Les identifiants finissent donc par se croiser.**

L'incident, mesuré le 2026-08-21 sur une mission réelle. `_echanger` testait
l'identifiant avant de regarder s'il s'agissait d'une requête entrante :

* la demande de permission portant l'identifiant du tour en cours était
  prise pour la réponse au tour ;
* le tour rendait la main immédiatement, sans `stopReason` — donc
  `abouti = False`, sans erreur, sans rien à lire ;
* côté agent le tour restait actif, en attente d'une permission qui ne
  viendrait plus ; la tâche suivante recevait pour toute réponse
  « Redirected the active turn with your correction. »

Le fichier demandé était pourtant **bien écrit sur le disque**. Un rapport
qui se serait fié au tour aurait conclu à un échec sur un travail réussi —
l'exacte symétrie de la règle « ne jamais croire un succès sur parole ».

Le discriminant est `method` : une réponse JSON-RPC n'en porte jamais, une
requête toujours. L'ordre des deux tests est donc le correctif entier.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from backend.ral.adapters.hermes_agent_acp import HermesAgentACP, SessionAgent


class _Entree:
    """Le flux que l'agent écrirait, servi ligne à ligne."""

    def __init__(self, lignes):
        self._lignes = [json.dumps(o).encode() + b"\n" for o in lignes]

    async def readline(self):
        return self._lignes.pop(0) if self._lignes else b""


class _Sortie:
    def __init__(self):
        self.envoyes = []

    def write(self, donnees):
        self.envoyes.append(json.loads(donnees.decode()))

    async def drain(self):
        return None


class _Proc:
    def __init__(self, lignes):
        self.stdout = _Entree(lignes)
        self.stdin = _Sortie()
        self.stderr = None


def _session(lignes, tmp_path):
    session = SessionAgent(cwd=str(tmp_path), session_id="s-1", compteur=2)
    session.proc = _Proc(lignes)
    session.verrou = asyncio.Lock()
    return session


#: Une demande de permission portant **le même identifiant** que la requête
#: que le client vient d'émettre. C'est la trame exacte de l'incident.
def _permission(identifiant, chemin="note.txt"):
    return {"jsonrpc": "2.0", "id": identifiant,
            "method": "session/request_permission",
            "params": {"toolCall": {"content": [{"type": "diff",
                                                 "path": chemin,
                                                 "newText": "x"}]},
                       "options": [{"optionId": "allow_once"}]}}


class TestLaCollisionDIdentifiants:
    def test_une_demande_de_permission_n_est_pas_notre_reponse(self, tmp_path):
        """Le cœur de l'incident : même identifiant, sens opposés."""
        vraie_reponse = {"jsonrpc": "2.0", "id": 3,
                         "result": {"stopReason": "end_turn"}}
        session = _session([_permission(3), vraie_reponse], tmp_path)
        client = HermesAgentACP()

        recu = asyncio.run(client._echanger(
            session, "session/prompt", {"sessionId": "s-1"}, 5.0, []))

        assert recu is vraie_reponse or recu == vraie_reponse
        assert recu["result"]["stopReason"] == "end_turn"

    def test_la_permission_recoit_bien_une_reponse(self, tmp_path):
        """Y répondre est ce qui débloque le tour : sans réponse, l'agent
        attend indéfiniment et rien dans le protocole ne le signale."""
        session = _session([_permission(3),
                            {"jsonrpc": "2.0", "id": 3, "result": {}}],
                           tmp_path)

        asyncio.run(HermesAgentACP()._echanger(
            session, "session/prompt", {"sessionId": "s-1"}, 5.0, []))

        reponses = [m for m in session.proc.stdin.envoyes if "result" in m]
        assert len(reponses) == 1
        assert reponses[0]["id"] == 3

    def test_une_ecriture_hors_workspace_est_refusee_meme_en_collision(
            self, tmp_path):
        """La frontière ne doit pas dépendre de l'ordre d'arrivée des
        trames : le chemin qui s'est réellement échappé, sur l'identifiant
        qui a réellement collisionné."""
        session = _session([_permission(3, "/Users/emeri/note.txt"),
                            {"jsonrpc": "2.0", "id": 3, "result": {}}],
                           tmp_path)

        asyncio.run(HermesAgentACP()._echanger(
            session, "session/prompt", {"sessionId": "s-1"}, 5.0, []))

        reponse = [m for m in session.proc.stdin.envoyes if "result" in m][0]
        assert reponse["result"]["outcome"]["outcome"] != "selected"


class TestCeQuiEstCollecte:
    def test_les_notifications_sont_collectees_pas_confondues(self, tmp_path):
        """Une notification n'a pas d'identifiant. Le texte de la réponse ne
        voyage que par là — le résultat JSON-RPC ne porte que `stopReason`
        et `usage`."""
        notification = {"jsonrpc": "2.0", "method": "session/update",
                        "params": {"update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": {"type": "text", "text": "BON"}}}}
        session = _session([notification,
                            {"jsonrpc": "2.0", "id": 3,
                             "result": {"stopReason": "end_turn"}}], tmp_path)
        collecte: list = []

        asyncio.run(HermesAgentACP()._echanger(
            session, "session/prompt", {"sessionId": "s-1"}, 5.0, collecte))

        assert collecte == [notification]

    def test_un_flux_ferme_est_dit(self, tmp_path):
        session = _session([], tmp_path)

        with pytest.raises(RuntimeError, match="flux fermé"):
            asyncio.run(HermesAgentACP()._echanger(
                session, "session/prompt", {"sessionId": "s-1"}, 5.0, []))
