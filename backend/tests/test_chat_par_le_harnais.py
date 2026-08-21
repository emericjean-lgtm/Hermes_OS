"""Le chat de l'Assistant servi par la session d'agent (HOS-141).

Le harnais ne servait que les missions. Le chat appelait Ollama en direct,
avec les seuls outils `workspace_*` que Hermes OS réimplémente et aucune
mémoire au-delà de l'historique reconstruit à chaque tour.

Deux règles y sont vérifiées, et une seule est un gain :

* **le choix est dit dans les deux sens.** Un chat qui bascule en silence
  entre deux moteurs aux capacités différentes est indébogable — la même
  question donnerait deux réponses sans que rien n'explique l'écart ;
* **le flux part au fil de l'eau.** Une tâche de mission tolère qu'un tour
  rende tout d'un coup ; une conversation non. Une minute d'attente muette
  est indiscernable d'une panne, et c'est ce que le chat montrerait si le
  harnais ne savait qu'assembler.
"""
from __future__ import annotations

import asyncio

import pytest

from backend.conversation import harnais


class TestQuandLeHarnaisSert:
    def test_sans_projet_il_n_y_a_rien_a_faire_durer(self):
        """Le chemin direct reste strictement meilleur : pas de workspace,
        donc pas de continuité à gagner, et un processus de moins."""
        ok, raison = harnais.disponible("")

        assert ok is False
        assert "projet" in raison

    def test_coupe_par_l_environnement(self, monkeypatch):
        monkeypatch.setenv("HERMES_HARNAIS", "0")

        ok, raison = harnais.disponible("/un/dossier")

        assert ok is False
        assert "HERMES_HARNAIS" in raison

    def test_les_prerequis_manquants_sont_expliques(self, monkeypatch):
        import backend.ral.adapters.prerequis_harnais as pre

        monkeypatch.setenv("HERMES_HARNAIS", "1")
        monkeypatch.setattr(pre, "verifier", lambda **_: pre.Prerequis(
            agent_installe=True, mcp_declare=True, backend_joignable=False))

        ok, raison = harnais.disponible("/un/dossier")

        assert ok is False
        assert "MCP" in raison


class TestLeFlux:
    """Le pont entre le rappel synchrone du client ACP et l'itérateur
    asynchrone que la route attend."""

    def test_les_morceaux_sortent_dans_l_ordre_et_traduits(self, monkeypatch):
        """`reponse`/`pensee` côté ACP deviennent `content`/`thinking`, les
        deux genres que le client du Cockpit sait déjà distinguer."""
        from backend.ral.adapters.hermes_agent_acp import Tour

        class _Registre:
            async def tour(self, cle, workspace, texte, *, amorce="",
                           modele="", delai=0, au_fil_de_l_eau=None):
                au_fil_de_l_eau("pensee", "je reflechis")
                au_fil_de_l_eau("reponse", "BON")
                au_fil_de_l_eau("reponse", "JOUR")
                return Tour(texte="BONJOUR", stop="end_turn", jetons_entree=42)

        import backend.ral.adapters.sessions_de_mission as sess

        monkeypatch.setattr(sess, "registre", lambda: _Registre())

        async def scenario():
            flux, verdict = await harnais.repondre(
                "salut", project_id="p-1", project_root="/ws")
            return [(m.kind, m.text) async for m in flux], verdict

        morceaux, verdict = asyncio.run(scenario())

        assert morceaux == [("thinking", "je reflechis"),
                            ("content", "BON"), ("content", "JOUR")]
        assert verdict.abouti is True
        assert verdict.jetons_entree == 42

    def test_un_tour_vide_devient_une_erreur_pas_une_reponse(self, monkeypatch):
        """Rendre le silence ferait passer une session en panne pour un
        modèle laconique — « ni un échec sur parole », mais pas un succès
        sur parole non plus."""
        from backend.ral.adapters.hermes_agent_acp import Tour

        class _Registre:
            async def tour(self, *a, **kw):
                return Tour(texte="", stop="cancelled")

        import backend.ral.adapters.sessions_de_mission as sess

        monkeypatch.setattr(sess, "registre", lambda: _Registre())

        async def scenario():
            flux, _ = await harnais.repondre(
                "salut", project_id="p-1", project_root="/ws")
            return [(m.kind, m.text) async for m in flux]

        morceaux = asyncio.run(scenario())

        assert [k for k, _ in morceaux] == ["error"]
        assert "cancelled" in morceaux[0][1]

    def test_une_panne_de_session_est_dite_et_non_avalee(self, monkeypatch):
        class _Registre:
            async def tour(self, *a, **kw):
                raise RuntimeError("tube ferme")

        import backend.ral.adapters.sessions_de_mission as sess

        monkeypatch.setattr(sess, "registre", lambda: _Registre())

        async def scenario():
            flux, verdict = await harnais.repondre(
                "salut", project_id="p-1", project_root="/ws")
            return [(m.kind, m.text) async for m in flux], verdict

        morceaux, verdict = asyncio.run(scenario())

        assert morceaux[0][0] == "error"
        assert "tube ferme" in verdict.erreur


class TestLaFenetreAnnoncee:
    """L'indicateur de contexte du Cockpit lit cette valeur. La deviner
    afficherait une jauge fausse — et une jauge fausse est pire qu'absente."""

    def test_elle_vient_du_catalogue(self):
        import io

        import yaml

        catalogue = yaml.safe_load(io.open("config/models.yaml",
                                           encoding="utf-8").read())
        standard = catalogue["roles"]["standard"]

        assert harnais.fenetre_de(standard["model"]) == standard["num_ctx"]

    def test_un_modele_inconnu_rend_zero_plutot_qu_une_invention(self):
        assert harnais.fenetre_de("modele-qui-n-existe-pas") == 0
