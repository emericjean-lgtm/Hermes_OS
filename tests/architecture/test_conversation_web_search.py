"""Tests for the Assistant chat's real internet search wiring (HOS-078):
backend/conversation/routes.py's _execute_web_search / _web_search_authorized.

_web_search_authorized() itself is monkeypatched here (its real Aegis
behaviour is covered by backend/tests/test_aegis.py's
test_web_search_*_autonomy tests) — this file is about the tool-executor
function's own logic: unknown tool names, missing queries, the Aegis
refusal message, and a connector failure being reported rather than
raised into the chat stream.
"""
from __future__ import annotations

import pytest

from backend.conversation import routes as conv_routes
from backend.tools.connectors.web_search import WebSearchResult


class _FakeConnector:
    def __init__(self, results=None, *, raise_error: Exception | None = None):
        self._results = results or []
        self._raise_error = raise_error
        self.calls: list[tuple[str, int | None]] = []

    async def search(self, query: str, *, max_results=None):
        self.calls.append((query, max_results))
        if self._raise_error:
            raise self._raise_error
        return self._results


class TestUnknownTool:
    @pytest.mark.asyncio
    async def test_a_tool_name_other_than_web_search_is_rejected_without_side_effects(self, monkeypatch):
        monkeypatch.setattr(conv_routes, "_web_search_authorized", lambda: True)
        result = await conv_routes._execute_web_search("some_other_tool", {"query": "x"})
        assert "Unknown tool" in result


class TestAegisGate:
    @pytest.mark.asyncio
    async def test_refused_when_not_authorized_no_search_attempted(self, monkeypatch):
        monkeypatch.setattr(conv_routes, "_web_search_authorized", lambda: False)
        fake = _FakeConnector(results=[WebSearchResult("t", "u", "s")])
        monkeypatch.setattr(conv_routes, "_get_web_search_connector", lambda: fake)

        result = await conv_routes._execute_web_search("web_search", {"query": "test"})

        assert "validation humaine" in result.lower() or "refus" in result.lower()
        assert fake.calls == []  # the real search must never run when refused


class TestRealSearchPath:
    @pytest.mark.asyncio
    async def test_authorized_search_calls_the_real_connector_with_the_query(self, monkeypatch):
        monkeypatch.setattr(conv_routes, "_web_search_authorized", lambda: True)
        fake = _FakeConnector(results=[
            WebSearchResult("Firestore | Firebase", "https://firebase.google.com/docs/firestore/",
                             "Cloud Firestore is a flexible database."),
        ])
        monkeypatch.setattr(conv_routes, "_get_web_search_connector", lambda: fake)

        result = await conv_routes._execute_web_search(
            "web_search", {"query": "firestore docs", "max_results": 3},
        )

        assert fake.calls == [("firestore docs", 3)]
        assert "Firestore | Firebase" in result
        assert "https://firebase.google.com/docs/firestore/" in result

    @pytest.mark.asyncio
    async def test_empty_query_is_rejected_without_calling_the_connector(self, monkeypatch):
        monkeypatch.setattr(conv_routes, "_web_search_authorized", lambda: True)
        fake = _FakeConnector()
        monkeypatch.setattr(conv_routes, "_get_web_search_connector", lambda: fake)

        result = await conv_routes._execute_web_search("web_search", {"query": "   "})

        assert fake.calls == []
        assert "no search query" in result.lower()

    @pytest.mark.asyncio
    async def test_no_results_is_reported_honestly_not_as_an_error(self, monkeypatch):
        monkeypatch.setattr(conv_routes, "_web_search_authorized", lambda: True)
        fake = _FakeConnector(results=[])
        monkeypatch.setattr(conv_routes, "_get_web_search_connector", lambda: fake)

        result = await conv_routes._execute_web_search("web_search", {"query": "asdkjfhaslkdjfh"})
        assert "no results" in result.lower()

    @pytest.mark.asyncio
    async def test_a_real_connector_failure_is_reported_not_raised_into_the_chat_stream(self, monkeypatch):
        monkeypatch.setattr(conv_routes, "_web_search_authorized", lambda: True)
        fake = _FakeConnector(raise_error=RuntimeError("DNS resolution failed"))
        monkeypatch.setattr(conv_routes, "_get_web_search_connector", lambda: fake)

        result = await conv_routes._execute_web_search("web_search", {"query": "anything"})
        assert "DNS resolution failed" in result


class TestToolsSchema:
    def test_conversation_tools_offers_exactly_web_search(self):
        """Sans projet lié, la recherche web est le seul outil offert.

        `_conversation_tools` a gagné un paramètre `project_root` avec les
        outils de fichiers : sans projet, aucun outil de fichier n'est
        proposé au modèle — c'est la garantie de sécurité de ce chemin, et
        elle n'était plus testée puisque l'appel échouait sur un TypeError.
        """
        tools = conv_routes._conversation_tools(None)

        assert [t["function"]["name"] for t in tools] == ["web_search"]

    def test_un_projet_lie_ajoute_les_outils_de_fichiers(self):
        """Le pendant : c'est l'existence d'un projet autorisé qui ouvre
        l'accès au disque, rien d'autre."""
        tools = conv_routes._conversation_tools("C:/quelque/part")
        noms = [t["function"]["name"] for t in tools]

        assert "web_search" in noms
        assert len(noms) > 1, "aucun outil de fichier offert malgré un projet lié"
