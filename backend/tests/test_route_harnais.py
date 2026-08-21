"""L'opérateur doit voir dans quel mode tourne son agent (HOS-138).

Le harnais et le mode jetable produisent des résultats de mission **de la
même forme**. Rien, dans un rapport, ne dit si l'agent qui a travaillé
gardait le contexte de la tâche précédente ou le découvrait à chaque fois.
La dégradation est donc réelle et invisible — la classe de défaut qui a
laissé, des mois durant, des missions contourner Hermes Agent.

`GET /system/harnais` répond à la question sans lire les journaux, et dit
**lequel** des prérequis manque : le cas le plus fréquent, mesuré, est un
backend éteint, dont l'agent tire ses outils par MCP.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routes.system import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestLaRoute:
    def test_elle_repond_les_trois_prerequis(self, client):
        reponse = client.get("/system/harnais")

        assert reponse.status_code == 200
        corps = reponse.json()
        assert set(corps["prerequis"]) == {
            "agent_installe", "backend_joignable", "mcp_declare"}
        assert isinstance(corps["pret"], bool)
        assert isinstance(corps["sessions_ouvertes"], int)

    def test_elle_dit_pourquoi_quand_ce_n_est_pas_pret(self, client,
                                                       monkeypatch):
        """« Harnais indisponible » sans cause envoie chercher au mauvais
        endroit."""
        import backend.ral.adapters.prerequis_harnais as pre

        etat = pre.Prerequis(agent_installe=True, mcp_declare=True,
                             backend_joignable=False)
        monkeypatch.setattr(pre, "verifier", lambda **_: etat)

        corps = client.get("/system/harnais").json()

        assert corps["pret"] is False
        assert "MCP" in corps["explication"]

    def test_pret_n_explique_rien(self, client, monkeypatch):
        import backend.ral.adapters.prerequis_harnais as pre

        monkeypatch.setattr(pre, "verifier", lambda **_: pre.Prerequis(
            agent_installe=True, mcp_declare=True, backend_joignable=True))

        corps = client.get("/system/harnais").json()

        assert corps["pret"] is True
        assert corps["explication"] == ""

    def test_actif_suit_l_environnement(self, client, monkeypatch):
        """La suite pose `HERMES_HARNAIS=0` ; la route doit le refléter,
        sans quoi elle affirmerait un mode que personne n'exécute."""
        monkeypatch.setenv("HERMES_HARNAIS", "0")

        assert client.get("/system/harnais").json()["actif"] is False

        monkeypatch.setenv("HERMES_HARNAIS", "1")

        assert client.get("/system/harnais").json()["actif"] is True


class TestLeHandlerNEstPasAsynchrone:
    """Le backend se declarait eteint dans sa propre reponse.

    La verification sonde le backend en HTTP, de facon bloquante. Dans un
    handler `async def`, cet appel gele la boucle meme qui devrait repondre
    a la sous-requete. Mesure sur le backend reel :

        {"pret": false, "backend_joignable": false, ... "(ReadTimeout)"}

    — obtenu, precisement, en interrogeant ce backend. Un operateur y aurait
    lu « backend eteint » sur une reponse que le backend venait de produire.

    En `def`, FastAPI execute le handler dans un threadpool et la boucle
    reste libre. Le test porte sur l'invariant, pas sur le symptome : rendre
    la fonction asynchrone le reintroduirait a l'identique.
    """

    def test_le_handler_est_synchrone(self):
        import inspect

        from backend.api.routes.system import system_harnais

        assert not inspect.iscoroutinefunction(system_harnais)


class TestCeQueLeCompteurNeVoitPas:
    """`sessions_ouvertes` est **local au processus** (HOS-141).

    Le registre est un singleton par interpreteur. Un script lance a cote —
    `derouler_cahier.py` deroulant un cahier toute une nuit — tient ses
    propres sessions, que cette route ne verra jamais.

    Mesure du 2026-08-21 : la route repondait `0` pendant qu'une campagne de
    22 sections tournait avec le harnais. Le chiffre n'est pas faux, il est
    local — et un operateur qui l'ignore conclut d'un `0` que le harnais ne
    sert pas.

    Le test verrouille ce que la route promet vraiment : son propre
    registre, et rien d'autre. Il empeche surtout qu'on rebaptise un jour ce
    champ en quelque chose de global sans en faire le travail.
    """

    def test_le_compteur_est_celui_du_registre_de_ce_processus(self, client,
                                                               monkeypatch):
        import backend.ral.adapters.sessions_de_mission as sess

        class _Registre:
            def sessions_ouvertes(self):
                return 3

        monkeypatch.setattr(sess, "registre", lambda: _Registre())

        assert client.get("/system/harnais").json()["sessions_ouvertes"] == 3

    def test_pret_ne_depend_pas_des_sessions(self, client, monkeypatch):
        """`pret` decrit la machine — agent installe, backend joignable, MCP
        declare — et vaut donc pour tous les processus, contrairement au
        compteur. Les lier ferait mentir le seul champ qui soit global."""
        import backend.ral.adapters.prerequis_harnais as pre
        import backend.ral.adapters.sessions_de_mission as sess

        monkeypatch.setattr(pre, "verifier", lambda **_: pre.Prerequis(
            agent_installe=True, mcp_declare=True, backend_joignable=True))
        monkeypatch.setattr(sess, "registre",
                            lambda: type("R", (), {"sessions_ouvertes": lambda s: 0})())

        corps = client.get("/system/harnais").json()

        assert corps["pret"] is True and corps["sessions_ouvertes"] == 0
