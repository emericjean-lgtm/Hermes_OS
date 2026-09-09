# -*- coding: utf-8 -*-
"""Lire et renommer une session : deux tranches verticales (G-20, HOS-269).

## Comment ces deux-la ont ete choisies

Le registre expose 206 methodes ; la question n'etait pas « lesquelles
sont faciles » mais « lesquelles valent quelque chose une fois branchees ».
Deux candidates evidentes ont ete **ecartees par la mesure** :

- **`delegation.pause`** — `_spawn_paused` est un global de module dans le
  processus gateway. Mesure : pause posee dans une connexion, `False` lu
  dans une autre. Un bouton du cockpit aurait donc bride le gateway du
  pont, ou aucune mission ne tourne — les missions passent par
  `hermes_agent_cli`, un autre processus. C'est exactement « une UI qui
  simule une mutation » ;
- **le lancement d'un subagent** — il n'existe pas comme RPC : c'est
  `delegate_tool.py`, un outil que l'agent appelle lui-meme.

Restent les sessions, ou la valeur est immediate : le cockpit affichait un
inventaire de conversations qu'on ne pouvait pas ouvrir.

## Ce que la persistance prouve, et ce qu'elle ne prouve pas

G-18 avait pris le md5 de `state.db` comme preuve de mutation. Mesure du
2026-09-09 sur le renommage : **le fichier principal ne bouge pas** et un
processus neuf lit pourtant le nouveau titre — l'ecriture vit dans le WAL,
qui fait partie de la base. Le md5 est donc un signal *suffisant* et non
*necessaire* ; la preuve fiable est la relecture par un processus neuf.
"""
from __future__ import annotations

import pytest

from backend.bridge.hermes_agent_bridge import MUTATIONS_CONNUES
from backend.services import mutations_agent, vue_agent


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
    monkeypatch.setattr(vue_agent, "_pont", lambda: faux)
    monkeypatch.setattr(mutations_agent, "_pont", lambda: faux)
    monkeypatch.setattr(mutations_agent, "_tracer", lambda *a, **k: None)
    return faux


# ── Lire une session ──────────────────────────────────────────────────

def test_lire_active_la_session_avant_de_la_lire(pont):
    """`session.history` est `live=True` : lire exige d'activer d'abord.

    Les deux gestes appartiennent a l'agent ; Hermes OS ne fait que les
    demander dans l'ordre, avec le **handle runtime** pour le second.
    """
    pont.reponses["session.resume"] = {"result": {"session_id": "h7"}}
    pont.reponses["session.history"] = {
        "result": {"messages": [{"role": "user", "text": "bonjour"}]}}
    vue = vue_agent.historique("cle-stockee")
    assert [m for m, _ in pont.appels] == ["session.resume", "session.history"]
    assert pont.appels[1][1]["session_id"] == "h7"
    assert vue["disponible"] is True and vue["total"] == 1


def test_une_activation_refusee_ne_se_lit_pas_comme_une_session_vide(pont):
    """Sans cette distinction, une session illisible s'afficherait comme
    une conversation sans message — et l'operateur en conclurait qu'elle
    est vide."""
    vue = vue_agent.historique("inconnue")
    assert vue["disponible"] is False
    assert "4001" in (vue["erreur"] or "") and vue["elements"] == []


def test_un_message_d_outil_n_a_ni_texte_ni_horodatage(pont):
    """Mesure sur une session reelle : un message `tool` porte `name`,
    `args`, `context` — et **pas** `row_id`, `text` ni `timestamp`.

    Le rendu s'y appuyait : deux messages d'outil collisionnaient sur une
    cle `undefined`, ce que React a signale en console et que l'oeil
    n'attrapait pas. La vue doit donc les servir tels quels, sans
    supposer un texte.
    """
    pont.reponses["session.resume"] = {"result": {"session_id": "h"}}
    pont.reponses["session.history"] = {"result": {"messages": [
        {"role": "user", "text": "t", "timestamp": 1.0, "row_id": 1},
        {"role": "tool", "name": "write_file", "args": {"path": "x"}},
    ]}}
    elements = vue_agent.historique("cle")["elements"]
    assert elements[1]["role"] == "tool"
    assert "row_id" not in elements[1] and "text" not in elements[1]
    assert elements[1]["name"] == "write_file"


# ── Renommer une session ──────────────────────────────────────────────

def test_renommer_passe_par_le_contrat_de_mutation(pont):
    pont.reponses["session.resume"] = {"result": {"session_id": "h9"}}
    pont.reponses["session.title"] = {"result": {"title": "Nouveau nom"}}
    resultat = mutations_agent.renommer_session("cle", "Nouveau nom")
    assert [m for m, _ in pont.appels] == ["session.resume", "session.title"]
    assert pont.appels[1][1] == {"session_id": "h9", "title": "Nouveau nom"}
    assert resultat["applique"] is True
    assert resultat["titre"] == "Nouveau nom"


def test_un_titre_vide_est_refuse_avant_tout_envoi(pont):
    """`session.title` sans titre **lit** le titre au lieu de l'ecrire.
    Envoyer une chaine vide effacerait donc le nom, ou ne ferait rien —
    dans les deux cas l'interface aurait menti sur ce qu'elle a fait."""
    resultat = mutations_agent.renommer_session("cle", "   ")
    assert resultat["applique"] is False
    assert "vide" in resultat["erreur"]
    assert pont.appels == [], "rien ne doit partir"


def test_un_refus_du_renommage_reste_un_resultat(pont):
    pont.reponses["session.resume"] = {"result": {"session_id": "h"}}
    pont.reponses["session.title"] = {
        "error": {"code": 4009, "message": "session busy"}}
    resultat = mutations_agent.renommer_session("cle", "T")
    assert resultat["applique"] is False
    assert "4009" in resultat["erreur"] and "busy" in resultat["erreur"]


def test_les_deux_mutations_sont_au_contrat():
    """Une mutation demandee hors contrat est refusee avant tout envoi ;
    ces deux-la doivent donc y figurer, et elles restent additives."""
    assert {"session.branch", "session.title"} <= set(MUTATIONS_CONNUES)
    for methode in MUTATIONS_CONNUES:
        assert not any(mot in methode for mot in
                       ("delete", "remove", "reset", "purge")), methode


# ── Ce qui a ete ecarte, et pourquoi ──────────────────────────────────

def test_la_pause_de_delegation_n_est_pas_offerte_au_produit():
    """Mesure : `_spawn_paused` est un global du processus gateway — pause
    posee dans une connexion, `False` lu dans une autre.

    Un bouton du cockpit aurait bride le gateway du pont, ou aucune
    mission ne tourne. La declarer mutation l'aurait rendue appelable
    depuis l'interface, donc simulee.
    """
    assert "delegation.pause" not in MUTATIONS_CONNUES, (
        "`delegation.pause` est locale au processus gateway : l'exposer "
        "comme mutation produit ferait un bouton sans effet la ou les "
        "missions tournent.")
