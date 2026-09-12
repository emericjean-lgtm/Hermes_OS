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


def _debut_outil(identifiant="tc-1", titre="Reading note.txt",
                 raw_input=None, chemin=None):
    maj = {"sessionUpdate": "tool_call", "toolCallId": identifiant,
           "title": titre, "kind": "read"}
    if raw_input is not None:
        maj["rawInput"] = raw_input
    if chemin is not None:
        maj["locations"] = [{"path": chemin}]
    return {"jsonrpc": "2.0", "method": "session/update", "params": {"update": maj}}


def _fin_outil(identifiant="tc-1", statut="completed", texte=None):
    maj = {"sessionUpdate": "tool_call_update", "toolCallId": identifiant,
          "status": statut}
    if texte is not None:
        maj["content"] = [{"type": "content",
                           "content": {"type": "text", "text": texte}}]
    return {"jsonrpc": "2.0", "method": "session/update", "params": {"update": maj}}


class TestLesAppelsDOutilTraduits:
    """G-43/G-44 : le harnais ne traduisait jamais `tool_call`/
    `tool_call_update`, donc l'Assistant ne montrait aucun chip d'outil dès
    qu'un projet était lié — c'est-à-dire dès que l'agent touchait
    vraiment des fichiers via ACP."""

    def test_un_debut_d_outil_est_traduit_et_mis_en_cache(self):
        cache: dict = {}

        genre, fragment, outils = HermesAgentACP.morceau(
            _debut_outil(raw_input={"path": "note.txt"}), cache)

        assert genre == "outil_debut"
        assert fragment == ""
        assert outils == [{"id": "tc-1",
                           "function": {"name": "Reading note.txt",
                                       "arguments": {"path": "note.txt"}}}]
        assert cache == {"tc-1": {"name": "Reading note.txt",
                                  "arguments": {"path": "note.txt"}}}

    def test_une_fin_d_outil_reprend_le_nom_du_debut(self):
        """`build_tool_complete` (hermes-agent) ne répète ni le titre ni les
        arguments : sans le cache posé au début, la fin ne saurait pas quoi
        montrer."""
        cache = {"tc-1": {"name": "Reading note.txt",
                          "arguments": {"path": "note.txt"}}}

        genre, fragment, outils = HermesAgentACP.morceau(
            _fin_outil(texte="contenu du fichier"), cache)

        assert genre == "outil_fin"
        assert fragment == ""
        assert outils == [{"name": "Reading note.txt",
                           "arguments": {"path": "note.txt"},
                           "result": "contenu du fichier"}]
        assert cache == {}  # consommé, pas laissé fuiter au tour suivant

    def test_un_statut_intermediaire_ne_produit_rien(self):
        cache = {"tc-1": {"name": "x", "arguments": {}}}

        genre, fragment, outils = HermesAgentACP.morceau(
            _fin_outil(statut="in_progress"), cache)

        assert (genre, fragment, outils) == ("", "", None)
        assert cache == {"tc-1": {"name": "x", "arguments": {}}}  # pas consommé

    def test_une_fin_sans_debut_connu_reste_honnete_pas_muette(self):
        """Notification perdue, ou cache d'un tour precedent : pas de nom a
        recuperer, donc pas de nom invente — mais un chip nomme plutot
        qu'aucun."""
        genre, fragment, outils = HermesAgentACP.morceau(
            _fin_outil(identifiant="tc-inconnu", texte="ok"), {})

        assert genre == "outil_fin"
        assert outils == [{"name": "tool", "arguments": {}, "result": "ok"}]

    def test_desactive_quand_aucun_cache_n_est_fourni(self):
        """`lire()` n'a besoin ni de l'un ni de l'autre : passer `appels=None`
        doit neutraliser la traduction plutot que de risquer un cache
        partage entre deux tours qui ne devraient pas se voir."""
        genre, fragment, outils = HermesAgentACP.morceau(_debut_outil())

        assert (genre, fragment, outils) == ("", "", None)

    def test_le_flux_les_porte_jusqu_a_l_observateur(self, tmp_path):
        """Bout en bout par `_echanger`, comme
        `test_les_notifications_sont_collectees_pas_confondues` : la
        correlation traverse la vraie boucle de lecture, pas seulement
        l'appel direct a `morceau`."""
        session = _session([
            _debut_outil(raw_input={"path": "note.txt"}),
            _fin_outil(texte="ok"),
            {"jsonrpc": "2.0", "id": 3, "result": {"stopReason": "end_turn"}},
        ], tmp_path)
        recus: list = []

        asyncio.run(HermesAgentACP()._echanger(
            session, "session/prompt", {"sessionId": "s-1"}, 5.0, [],
            au_fil_de_l_eau=lambda genre, fragment, outils=None:
                recus.append((genre, fragment, outils))))

        assert recus[0][0] == "outil_debut"
        assert recus[0][2][0]["function"]["name"] == "Reading note.txt"
        assert recus[1][0] == "outil_fin"
        assert recus[1][2][0]["result"] == "ok"
        assert session.appels_outils_en_cours == {}
