"""Tests for WebSearchConnector (HOS-078 — Assistant chat real internet
search via DuckDuckGo's HTML endpoint).

The HTML fixture below is a trimmed, hand-verified reproduction of the
real markup DuckDuckGo returned for a live query (checked by hand,
2026-08-09) — enough to exercise the real regex parsing/URL-unwrapping
logic without embedding a full ~30KB scraped page. The real end-to-end
path (an actual HTTP call to html.duckduckgo.com) was verified separately
by hand and via base_agent's tool-calling tests; this file locks in the
parsing itself, hermetically (httpx is monkeypatched, no real network
call here).
"""
from __future__ import annotations

import httpx
import pytest

from backend.tools.connectors.web_search import (
    WebSearchConnector,
    _resolve_target_url,
    web_search_tool_schema,
)

_TWO_RESULTS_HTML = """
<div class="results">
  <div class="result results_links results_links_deep web-result">
    <div class="links_main links_deep result__body">
      <h2 class="result__title">
        <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Ffirebase.google.com%2Fdocs%2Ffirestore%2F&amp;rut=abc">Firestore | Firebase</a>
      </h2>
      <a class="result__snippet" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Ffirebase.google.com%2Fdocs%2Ffirestore%2F&amp;rut=abc">Cloud <b>Firestore</b> is a flexible, scalable database for mobile, web, and server development.</a>
    </div>
  </div>
  <div class="result results_links results_links_deep web-result">
    <div class="links_main links_deep result__body">
      <h2 class="result__title">
        <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.cloud.google.com%2Ffirestore%2F&amp;rut=def">Firestore documentation | Google Cloud</a>
      </h2>
      <a class="result__snippet" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.cloud.google.com%2Ffirestore%2F&amp;rut=def">Getting started with security rules &amp; more.</a>
    </div>
  </div>
</div>
"""

_NO_RESULTS_HTML = "<div class=\"no-results\">No results found for your search.</div>"


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)  # type: ignore[arg-type]


class _FakeAsyncClient:
    def __init__(self, response_text: str, *, raise_error: Exception | None = None) -> None:
        self._response_text = response_text
        self._raise_error = raise_error
        self.requested_params: dict | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, *, params=None, headers=None, follow_redirects=None):
        self.requested_params = params
        if self._raise_error:
            raise self._raise_error
        return _FakeResponse(self._response_text)


def _patch_client(monkeypatch, response_text: str, **kwargs):
    fake = _FakeAsyncClient(response_text, **kwargs)
    monkeypatch.setattr(
        "backend.tools.connectors.web_search.httpx.AsyncClient",
        lambda **_kw: fake,
    )
    return fake


class TestUrlUnwrapping:
    def test_resolves_the_real_target_url_from_ddgs_redirector(self):
        ddg_href = "//duckduckgo.com/l/?uddg=https%3A%2F%2Ffirebase.google.com%2Fdocs%2Ffirestore%2F&rut=abc"
        assert _resolve_target_url(ddg_href) == "https://firebase.google.com/docs/firestore/"

    def test_passes_through_a_plain_url_unchanged(self):
        assert _resolve_target_url("https://example.com") == "https://example.com"


class TestSearchParsing:
    @pytest.mark.asyncio
    async def test_parses_real_shaped_result_markup_into_structured_results(self, monkeypatch):
        _patch_client(monkeypatch, _TWO_RESULTS_HTML)
        connector = WebSearchConnector()
        results = await connector.search("firestore")

        assert len(results) == 2
        assert results[0].title == "Firestore | Firebase"
        assert results[0].url == "https://firebase.google.com/docs/firestore/"
        assert "Firestore" in results[0].snippet
        assert "<b>" not in results[0].snippet  # HTML tags stripped
        assert results[1].url == "https://docs.cloud.google.com/firestore/"

    @pytest.mark.asyncio
    async def test_respects_max_results(self, monkeypatch):
        _patch_client(monkeypatch, _TWO_RESULTS_HTML)
        connector = WebSearchConnector()
        results = await connector.search("firestore", max_results=1)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_a_200_with_no_matching_markup_returns_empty_not_an_error(self, monkeypatch):
        _patch_client(monkeypatch, _NO_RESULTS_HTML)
        connector = WebSearchConnector()
        results = await connector.search("something with truly no results")
        assert results == []

    @pytest.mark.asyncio
    async def test_empty_query_returns_empty_without_a_network_call(self, monkeypatch):
        fake = _patch_client(monkeypatch, _TWO_RESULTS_HTML)
        connector = WebSearchConnector()
        results = await connector.search("   ")
        assert results == []
        assert fake.requested_params is None

    @pytest.mark.asyncio
    async def test_a_real_network_failure_propagates_rather_than_a_fabricated_result(self, monkeypatch):
        _patch_client(monkeypatch, "", raise_error=httpx.ConnectError("refused"))
        connector = WebSearchConnector()
        with pytest.raises(httpx.ConnectError):
            await connector.search("anything")

    @pytest.mark.asyncio
    async def test_sends_the_real_query_as_a_request_param(self, monkeypatch):
        fake = _patch_client(monkeypatch, _TWO_RESULTS_HTML)
        connector = WebSearchConnector()
        await connector.search("Firestore security rules")
        assert fake.requested_params == {"q": "Firestore security rules"}


class TestToolSchema:
    def test_schema_is_a_well_formed_ollama_function_tool(self):
        schema = web_search_tool_schema()
        assert schema["type"] == "function"
        fn = schema["function"]
        assert fn["name"] == "web_search"
        assert "query" in fn["parameters"]["properties"]
        assert fn["parameters"]["required"] == ["query"]
