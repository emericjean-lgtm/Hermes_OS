"""Garde la suite conversation hermétique.

``ResponseGenerator`` interroge un vrai modèle depuis que le chat a été réparé —
sans cela il servait un gabarit figé à toute question. C'est le bon comportement
en production et le mauvais dans une suite unitaire : chaque test du manager
émettait une requête d'inférence réelle et ce paquet passait de quelques
secondes à plus de quatre minutes.

Seul l'appel sortant est remplacé. L'analyse d'intention, le choix du gabarit,
la porte d'approbation, les suggestions et la gestion de session restent du code
de production. La couverture avec inférence réelle vit dans
``tests/integration/``.

Même convention que ``tests.support.fake_inference``.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_live_chat(monkeypatch):
    """Réponse déterministe au lieu d'un appel réseau."""
    async def canned(*, messages, model):  # noqa: ARG001
        user = next((m["content"] for m in reversed(messages)
                     if m.get("role") == "user"), "")
        return f"Réponse de test à : {user[:60]}"

    monkeypatch.setattr(
        "backend.conversation.response_generator._default_chat", canned)
