"""§12 — résumer le passé au lieu de le couper (HOS-120).

Le cahier des charges exige de « résumer automatiquement le contexte trop
long » et de « tronquer intelligemment sans perte d'information critique
(résumer les parties les moins récentes plutôt que couper brutalement) ».

`build_model_messages` faisait exactement l'inverse :

    history = session.messages[-MAX_HISTORY_MESSAGES:]

Au vingt-et-unième message, le premier — souvent celui qui pose le sujet,
la contrainte ou le fichier concerné — cessait d'exister pour le modèle,
sans que rien ne le signale. C'était le seul critère d'acceptation du §28
jamais construit.
"""
from __future__ import annotations

import pytest

from backend.conversation.context_summary import (
    MINIMUM_A_RESUMER, bloc_systeme, bloc_troncature, decouper, resumer,
)


class _Message:
    def __init__(self, contenu: str, role: str = "user"):
        self.content = contenu
        self.role = type("R", (), {"value": role})()


def _messages(n: int) -> list[_Message]:
    return [_Message(f"message {i}") for i in range(n)]


class TestLeDecoupage:
    def test_une_conversation_courte_n_est_pas_resumee(self):
        """La résumer coûterait un appel modèle sans rien économiser."""
        anciens, gardes = decouper(_messages(8), tours_gardes=12)

        assert anciens == []
        assert len(gardes) == 8

    def test_juste_au_dessus_du_seuil_rien_n_est_encore_resume(self):
        """Résumer deux messages produit un texte plus long qu'eux."""
        anciens, _ = decouper(_messages(12 + MINIMUM_A_RESUMER), tours_gardes=12)

        assert anciens == []

    def test_au_dela_les_plus_anciens_partent_au_resume(self):
        anciens, gardes = decouper(_messages(30), tours_gardes=12)

        assert len(gardes) == 12
        assert len(anciens) == 18

    def test_les_tours_recents_restent_mot_pour_mot(self):
        """C'est la moitié de l'exigence : compresser l'ancien *et* garder
        le récent intact."""
        anciens, gardes = decouper(_messages(30), tours_gardes=12)

        assert gardes[-1].content == "message 29"
        assert anciens[0].content == "message 0"


class TestLeResumeEstUnVraiAppel:
    @pytest.mark.asyncio
    async def test_le_texte_du_modele_est_rendu(self):
        async def chat(*, messages, model, num_ctx=None):
            return {"content": "L'utilisateur veut un module de calcul."}

        resume = await resumer(_messages(6), chat=chat, model="m")

        assert resume == "L'utilisateur veut un module de calcul."

    @pytest.mark.asyncio
    async def test_la_transcription_contient_les_messages_et_les_roles(self):
        vus = {}

        async def chat(*, messages, model, num_ctx=None):
            vus["contenu"] = messages[-1]["content"]
            return {"content": "ok"}

        await resumer([_Message("écris un module", "user"),
                       _Message("d'accord", "hermes")],
                      chat=chat, model="m")

        assert "user: écris un module" in vus["contenu"]
        assert "hermes: d'accord" in vus["contenu"]


class TestUnResumeNEstJamaisFabrique:
    """La règle centrale : un contexte inventé est pire qu'un contexte
    tronqué. Le second se voit, le premier se lit comme un souvenir."""

    @pytest.mark.asyncio
    async def test_une_panne_du_modele_rend_None_et_ne_leve_pas(self):
        async def chat(*, messages, model, num_ctx=None):
            raise ConnectionError("ollama injoignable")

        assert await resumer(_messages(6), chat=chat, model="m") is None

    @pytest.mark.asyncio
    async def test_un_resume_vide_est_traite_comme_une_absence(self):
        """Et non comme « rien d'important n'a été dit »."""
        async def chat(*, messages, model, num_ctx=None):
            return {"content": "   "}

        assert await resumer(_messages(6), chat=chat, model="m") is None

    @pytest.mark.asyncio
    async def test_des_messages_vides_ne_declenchent_pas_d_appel(self):
        appels = []

        async def chat(*, messages, model, num_ctx=None):
            appels.append(1)
            return {"content": "ok"}

        assert await resumer([_Message("  ")], chat=chat, model="m") is None
        assert appels == []


class TestCeQueLeModeleLit:
    def test_le_resume_est_annonce_comme_un_resume(self):
        """Un modèle qui le prendrait pour une transcription pourrait citer
        l'utilisateur sur des mots qu'il n'a pas dits."""
        bloc = bloc_systeme("il veut un module", 18)

        assert "pas une transcription" in bloc["content"]
        assert "18" in bloc["content"]
        assert bloc["role"] == "system"

    def test_un_trou_non_resume_est_annonce_au_lieu_d_etre_taire(self):
        """Le comportement précédent était le silence : les messages
        disparaissaient et le modèle répondait comme s'ils n'avaient jamais
        existé."""
        bloc = bloc_troncature(18)

        assert "18" in bloc["content"]
        assert "demande" in bloc["content"].lower()
