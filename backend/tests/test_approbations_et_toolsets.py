# -*- coding: utf-8 -*-
"""Approbations : bloquees, et pourquoi. Toolsets : integres (HOS-270).

## Les approbations ne sont pas integrables aujourd'hui

Le brief les demandait en priorite. Le runtime les expose bel et bien —
`approval.pending`, `approval.received`, `approval.respond` repondent — et
pourtant la capacite n'a **aucun producteur** sur nos chemins. Trois
mesures l'etablissent :

1. **Le mecanisme est en memoire, dans le processus.** `_gateway_queues`
   est un dict de module de `tools/approval.py`, et chaque entree porte un
   `threading.Event` qui **bloque un fil de l'agent**. Une approbation
   n'existe que pendant qu'un tour tourne dans ce processus-la.
2. **Le chemin mission ne peut pas en produire.** `cli.py` pose
   `HERMES_SINGLE_QUERY_SESSION=1` pour tout `--query`, ce qui est
   exactement ce que Hermes OS lance : la porte prend alors le chemin
   deterministe d'`approvals.single_query_mode`. L'agent se protege
   lui-meme d'une porte que personne n'ecouterait — « without this marker
   the gate would wait the full timeout, fail closed ».
3. **Le gateway du pont pourrait en produire, mais n'en produit pas.**
   `tui_gateway/server.py` pose `HERMES_GATEWAY_SESSION=1` et enregistre
   `register_gateway_notify` : un tour lance **la** produirait des
   approbations repondables. Le pont ne lance aucun tour.

Mesure sur session vivante : `approval.pending` rend `{"approvals": []}` et
`approval.respond` rend `{"resolved": 0}`.

La condition prealable est donc le **chat** — faire passer des tours par le
gateway du pont. Les approbations viendront avec, et pas avant. Un panneau
« Approbations » branche aujourd'hui serait vide par construction, et son
bouton ne resoudrait jamais rien : precisement « une demande affichee sans
possibilite reelle de decision ».

## Les toolsets, eux, portent

`tools.configure` appelle `save_config` : il ecrit `config.yaml`, que
**tous** les processus agent relisent — missions comprises. C'est ce qui le
distingue de `delegation.pause`, mesuree comme locale au gateway.
"""
from __future__ import annotations

import pytest

from backend.bridge.hermes_agent_bridge import MUTATIONS_CONNUES
from backend.services import mutations_agent


class _PontFaux:
    def __init__(self, reponses=None, leve=None):
        self.reponses = reponses or {}
        self.leve = leve
        self.appels: list = []

    def appeler(self, methode, params=None, timeout=None):
        self.appels.append((methode, params))
        if self.leve is not None:
            raise self.leve
        return self.reponses.get(
            methode, {"error": {"code": 4001, "message": "session not found"}})

    def demander_mutation(self, methode, params=None, timeout=None):
        assert methode in MUTATIONS_CONNUES, methode
        return self.appeler(methode, params, timeout)


@pytest.fixture
def pont(monkeypatch):
    faux = _PontFaux()
    monkeypatch.setattr(mutations_agent, "_pont", lambda: faux)
    monkeypatch.setattr(mutations_agent, "_tracer", lambda *a, **k: None)
    return faux


# ── Les approbations restent hors contrat, et c'est mesure ────────────

def test_aucune_approbation_n_est_offerte_comme_mutation():
    """Repondre a une approbation ne resoudrait rien : la file est vide par
    construction sur nos chemins.

    L'exposer ferait un bouton qui n'agit sur aucune execution — ce que le
    chantier interdit explicitement. La condition prealable est le chat.
    """
    for methode in MUTATIONS_CONNUES:
        assert not methode.startswith("approval."), (
            f"`{methode}` est offerte comme mutation alors qu'aucun tour ne "
            "tourne dans le gateway du pont : la file d'approbations y est "
            "vide par construction. Integrez le chat d'abord.")


def test_la_pause_de_delegation_reste_ecartee():
    """Meme motif, mesure en HOS-269 : `_spawn_paused` est un global du
    processus gateway."""
    assert "delegation.pause" not in MUTATIONS_CONNUES


# ── Les toolsets : une mutation qui porte sur les missions ────────────

def test_basculer_ecrit_par_le_proprietaire(pont):
    pont.reponses["tools.configure"] = {
        "result": {"changed": ["browser"], "unknown": [],
                   "enabled_toolsets": ["coding", "browser"]}}
    resultat = mutations_agent.basculer_toolset("browser", True)
    assert pont.appels == [("tools.configure",
                            {"action": "enable", "names": ["browser"]})]
    assert resultat["applique"] is True and resultat["actif"] is True


def test_desactiver_passe_l_action_inverse(pont):
    pont.reponses["tools.configure"] = {
        "result": {"changed": ["browser"], "unknown": [],
                   "enabled_toolsets": []}}
    mutations_agent.basculer_toolset("browser", False)
    assert pont.appels[0][1]["action"] == "disable"


def test_un_toolset_inconnu_est_un_refus_pas_un_succes(pont):
    """Mesure : `tools.configure` rend `200` avec le nom dans `unknown` et
    `changed` vide. Le lire comme un succes afficherait un basculement qui
    n'a pas eu lieu.

    Ce cas **arrive en vrai** : `a2a` est un toolset de plugin, et sa
    validite depend de la decouverte des plugins dans le processus gateway.
    Mesure du 2026-09-09 : premier essai refuse, second accepte. La course
    existe ; l'interface doit la montrer, pas la maquiller.
    """
    pont.reponses["tools.configure"] = {
        "result": {"changed": [], "unknown": ["a2a"], "enabled_toolsets": []}}
    resultat = mutations_agent.basculer_toolset("a2a", True)
    assert resultat["applique"] is False
    assert "inconnu" in resultat["erreur"] and "a2a" in resultat["erreur"]


def test_un_runtime_qui_ne_change_rien_n_est_pas_un_succes(pont):
    """`changed` vide sans `unknown` : le runtime a repondu sans agir."""
    pont.reponses["tools.configure"] = {
        "result": {"changed": [], "unknown": [], "enabled_toolsets": []}}
    resultat = mutations_agent.basculer_toolset("browser", True)
    assert resultat["applique"] is False
    assert "rien change" in resultat["erreur"]


def test_un_nom_vide_ne_part_pas(pont):
    resultat = mutations_agent.basculer_toolset("   ", True)
    assert resultat["applique"] is False
    assert pont.appels == []


def test_un_refus_du_runtime_reste_un_resultat(pont):
    pont.reponses["tools.configure"] = {
        "error": {"code": 4017, "message": "unknown tools action"}}
    resultat = mutations_agent.basculer_toolset("browser", True)
    assert resultat["applique"] is False and "4017" in resultat["erreur"]


def test_une_panne_de_transport_ne_leve_pas(monkeypatch):
    monkeypatch.setattr(mutations_agent, "_tracer", lambda *a, **k: None)
    monkeypatch.setattr(mutations_agent, "_pont",
                        lambda: _PontFaux(leve=OSError("gateway mort")))
    resultat = mutations_agent.basculer_toolset("browser", True)
    assert resultat["applique"] is False
    assert "gateway mort" in resultat["erreur"]


def test_le_contrat_porte_la_configuration_de_l_agent():
    """`tools.configure` ecrit `config.yaml`, pas `state.db` : le contrat
    G-18 vaut pour tout etat natif de l'agent, pas seulement sa base."""
    assert MUTATIONS_CONNUES.get("tools.configure") == "hermes-agent:config.yaml"
