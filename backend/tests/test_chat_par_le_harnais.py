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

    def test_un_appel_d_outil_reel_traverse_le_pont(self, monkeypatch):
        """G-43/G-44 : le harnais ne traduisait que `reponse`/`pensee` —
        un appel d'outil réel (l'agent lit/écrit un fichier via ACP) n'avait
        aucune traduction et disparaissait donc entièrement dès qu'un
        projet était lié, précisément quand l'agent touche vraiment des
        fichiers. Même contrat NDJSON que le chemin direct :
        `tool_calls`/`tool_result` (voir `conversation-stream.ts`)."""
        from backend.ral.adapters.hermes_agent_acp import Tour

        outils_debut = [{"id": "tc-1", "function": {"name": "workspace_read",
                                                     "arguments": {"path": "a.txt"}}}]
        outils_fin = [{"name": "workspace_read", "arguments": {"path": "a.txt"},
                      "result": "contenu"}]

        class _Registre:
            async def tour(self, cle, workspace, texte, *, amorce="",
                           modele="", delai=0, au_fil_de_l_eau=None):
                au_fil_de_l_eau("outil_debut", "", outils_debut)
                au_fil_de_l_eau("outil_fin", "", outils_fin)
                au_fil_de_l_eau("reponse", "voila")
                return Tour(texte="voila", stop="end_turn")

        import backend.ral.adapters.sessions_de_mission as sess

        monkeypatch.setattr(sess, "registre", lambda: _Registre())

        async def scenario():
            flux, _ = await harnais.repondre(
                "lis a.txt", project_id="p-1", project_root="/ws")
            return [(m.kind, m.text, m.tool_calls) async for m in flux]

        morceaux = asyncio.run(scenario())

        assert morceaux[0] == ("tool_calls", "", outils_debut)
        assert morceaux[1] == ("tool_result", "", outils_fin)
        assert morceaux[2] == ("content", "voila", None)

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


class TestLeContratNDJSONDeLaRoute:
    """`backend/conversation/routes.py:_repondre_par_le_harnais` doit
    serialiser exactement le meme contrat que le chemin direct
    (`_body`, lignes ~617-631) : sans quoi le front (deja cable pour
    `tool_calls`/`tool_result`, `conversation-stream.ts`) ne recevrait
    jamais rien a afficher des qu'un projet est lie (G-43/G-44)."""

    def test_un_appel_d_outil_atteint_le_json_ndjson(self, monkeypatch, tmp_path):
        import json

        from backend.conversation import routes
        from backend.conversation.conversation_manager import ConversationManager
        from backend.conversation.conversation_store import SqliteConversationStore
        from backend.memory.db import init_db, make_engine, make_session_factory
        from backend.ral.adapters.hermes_agent_acp import Tour

        outils_debut = [{"id": "tc-1", "function": {"name": "workspace_read",
                                                     "arguments": {"path": "a.txt"}}}]
        outils_fin = [{"name": "workspace_read", "arguments": {"path": "a.txt"},
                      "result": "contenu"}]

        class _Registre:
            async def tour(self, cle, workspace, texte, *, amorce="",
                           modele="", delai=0, au_fil_de_l_eau=None):
                au_fil_de_l_eau("outil_debut", "", outils_debut)
                au_fil_de_l_eau("outil_fin", "", outils_fin)
                au_fil_de_l_eau("reponse", "voila")
                return Tour(texte="voila", stop="end_turn")

        import backend.ral.adapters.sessions_de_mission as sess

        monkeypatch.setattr(sess, "registre", lambda: _Registre())

        engine = make_engine(str(tmp_path / "conv.db"))
        init_db(engine)
        mgr = ConversationManager(store=SqliteConversationStore(make_session_factory(engine)))
        session_id, model_messages, intent = mgr.begin_stream("", "lis a.txt")

        async def scenario():
            reponse = await routes._repondre_par_le_harnais(
                mgr, session_id, "lis a.txt", intent, model_messages,
                project_id="p-1", project_root=str(tmp_path))
            return [json.loads(ligne)
                   async for ligne in reponse.body_iterator]

        lignes = asyncio.run(scenario())

        outil_debut_recu = next(l for l in lignes if l["kind"] == "tool_calls")
        outil_fin_recu = next(l for l in lignes if l["kind"] == "tool_result")
        assert outil_debut_recu["tool_calls"] == outils_debut
        assert outil_fin_recu["tool_calls"] == outils_fin
        contenu = next(l for l in lignes if l["kind"] == "content")
        assert "tool_calls" not in contenu


class TestLeChoixManuelDuModele:
    """Le ModelPicker de l'Assistant (HOS-075) laissait le chat retomber sur
    `standard` (`ornith-9b-256k`) des qu'un projet etait lie a la session,
    quel que soit le role choisi a l'ecran : `_repondre_par_le_harnais`
    n'avait jamais recu `forced_role`, seul `_modele_du_chat()` sans
    argument etait appele. Un operateur qui selectionnait `reasoning` dans
    l'Assistant voyait donc sa conversation servie par un autre modele que
    celui affiche, sans qu'aucune erreur ne le signale."""

    def test_le_role_choisi_dans_l_assistant_atteint_le_harnais(
        self, monkeypatch, tmp_path,
    ):
        import io

        import yaml

        from backend.conversation import routes
        from backend.conversation.conversation_manager import ConversationManager
        from backend.conversation.conversation_store import SqliteConversationStore
        from backend.memory.db import init_db, make_engine, make_session_factory
        from backend.ral.adapters.hermes_agent_acp import Tour

        catalogue = yaml.safe_load(io.open("config/models.yaml", encoding="utf-8").read())
        modele_attendu = catalogue["roles"]["reasoning"]["model"]
        assert modele_attendu != catalogue["roles"]["standard"]["model"]

        modeles_recus = []

        class _Registre:
            async def tour(self, cle, workspace, texte, *, amorce="",
                           modele="", delai=0, au_fil_de_l_eau=None):
                modeles_recus.append(modele)
                return Tour(texte="ok", stop="end_turn")

        import backend.ral.adapters.sessions_de_mission as sess

        monkeypatch.setattr(sess, "registre", lambda: _Registre())

        engine = make_engine(str(tmp_path / "conv.db"))
        init_db(engine)
        mgr = ConversationManager(store=SqliteConversationStore(make_session_factory(engine)))
        session_id, model_messages, intent = mgr.begin_stream("", "explique")

        async def scenario():
            reponse = await routes._repondre_par_le_harnais(
                mgr, session_id, "explique", intent, model_messages,
                project_id="p-1", project_root=str(tmp_path),
                forced_role="reasoning")
            return [_ async for _ in reponse.body_iterator]

        asyncio.run(scenario())

        assert modeles_recus == [modele_attendu]

    def test_sans_choix_manuel_le_comportement_precedent_est_conserve(
        self, monkeypatch, tmp_path,
    ):
        """`forced_role=None` (Auto dans le ModelPicker) ne doit rien
        changer au routage existant du chat par le harnais."""
        import io

        import yaml

        from backend.conversation import routes
        from backend.conversation.conversation_manager import ConversationManager
        from backend.conversation.conversation_store import SqliteConversationStore
        from backend.memory.db import init_db, make_engine, make_session_factory
        from backend.ral.adapters.hermes_agent_acp import Tour

        catalogue = yaml.safe_load(io.open("config/models.yaml", encoding="utf-8").read())
        modele_standard = catalogue["roles"]["standard"]["model"]

        modeles_recus = []

        class _Registre:
            async def tour(self, cle, workspace, texte, *, amorce="",
                           modele="", delai=0, au_fil_de_l_eau=None):
                modeles_recus.append(modele)
                return Tour(texte="ok", stop="end_turn")

        import backend.ral.adapters.sessions_de_mission as sess

        monkeypatch.setattr(sess, "registre", lambda: _Registre())

        engine = make_engine(str(tmp_path / "conv.db"))
        init_db(engine)
        mgr = ConversationManager(store=SqliteConversationStore(make_session_factory(engine)))
        session_id, model_messages, intent = mgr.begin_stream("", "explique")

        async def scenario():
            reponse = await routes._repondre_par_le_harnais(
                mgr, session_id, "explique", intent, model_messages,
                project_id="p-1", project_root=str(tmp_path))
            return [_ async for _ in reponse.body_iterator]

        asyncio.run(scenario())

        assert modeles_recus == [modele_standard]

    def test_un_nom_hors_catalogue_est_traite_comme_un_tag_litteral(self):
        """Le ModelPicker propose aussi les modeles Ollama installes mais
        non benchmarkes (pas de role dans config/models.yaml) : un nom
        absent du catalogue n'est plus une erreur, c'est un tag de modele
        pris tel quel — jamais un repli silencieux sur `standard` non plus,
        ce qui reste le vrai contrat a garder. Ollama, pas ce module, dira
        honnetement si le tag n'existe pas."""
        from backend.conversation.routes import _modele_du_chat

        assert _modele_du_chat("un-tag-ollama-hors-catalogue") == "un-tag-ollama-hors-catalogue"


class TestLesEntetesDeRoutage:
    """L'indicateur de modele de l'Assistant (RoutingBadge) lit les entetes
    `X-Hermes-*` de la reponse. Le chemin direct les posait ; le chemin par
    le harnais n'en posait aucun sauf `X-Hermes-Runtime` — l'indicateur
    restait donc vide des qu'un projet etait lie a la session, c'est a
    dire dans le cas normal."""

    def test_le_modele_et_le_role_atteignent_les_entetes(self, monkeypatch, tmp_path):
        import io

        import yaml

        from backend.conversation import routes
        from backend.conversation.conversation_manager import ConversationManager
        from backend.conversation.conversation_store import SqliteConversationStore
        from backend.memory.db import init_db, make_engine, make_session_factory
        from backend.ral.adapters.hermes_agent_acp import Tour

        catalogue = yaml.safe_load(io.open("config/models.yaml", encoding="utf-8").read())
        role_reasoning = catalogue["roles"]["reasoning"]

        class _Registre:
            async def tour(self, *a, **kw):
                return Tour(texte="ok", stop="end_turn")

        import backend.ral.adapters.sessions_de_mission as sess

        monkeypatch.setattr(sess, "registre", lambda: _Registre())

        engine = make_engine(str(tmp_path / "conv.db"))
        init_db(engine)
        mgr = ConversationManager(store=SqliteConversationStore(make_session_factory(engine)))
        session_id, model_messages, intent = mgr.begin_stream("", "explique")

        async def scenario():
            reponse = await routes._repondre_par_le_harnais(
                mgr, session_id, "explique", intent, model_messages,
                project_id="p-1", project_root=str(tmp_path),
                forced_role="reasoning")
            [_ async for _ in reponse.body_iterator]
            return reponse

        reponse = asyncio.run(scenario())

        assert reponse.headers["X-Hermes-Model"] == role_reasoning["model"]
        assert reponse.headers["X-Hermes-Role"] == "reasoning"
        assert reponse.headers["X-Hermes-Tier"] == role_reasoning["tier"]
        assert reponse.headers["X-Hermes-Session"] == session_id
        assert "manuellement" in reponse.headers["X-Hermes-Reason"]

    def test_un_modele_impose_hors_catalogue_ne_casse_pas_les_entetes(self):
        """`HERMES_MISSION_MODEL` peut pointer un tag qui n'est le modele
        d'aucun role — la relecture doit rendre des chaines vides, jamais
        lever, plutot qu'inventer un role."""
        from backend.conversation.routes import _role_et_tier_pour_modele

        assert _role_et_tier_pour_modele("un-tag-hors-catalogue") == ("", "")


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
