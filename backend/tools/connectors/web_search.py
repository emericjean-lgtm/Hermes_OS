"""Real internet search (Assistant chat feedback round).

DuckDuckGo's HTML endpoint (``html.duckduckgo.com/html/``), not the JSON
API — DuckDuckGo has never shipped a free, keyless JSON search API; the
HTML endpoint is the only route that doesn't require an account or a paid
key, which is the whole reason it was chosen. It returns server-rendered
markup (no JS), scraped here with a handful of narrow regexes rather than
a full HTML parser — ``beautifulsoup4``/``lxml`` aren't installed in this
environment (checked before writing this), and the three fields this needs
(title, URL, snippet) don't warrant adding a dependency for. If DuckDuckGo
changes its markup, ``search()`` returns zero results rather than raising
or fabricating — a real, empty-but-honest outcome the caller/model can act
on, not a silent lie about what was found.
"""
from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

logger = logging.getLogger("hermes_os.web_search")

_SEARCH_URL = "https://html.duckduckgo.com/html/"
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HermesOS-WebSearch/1.0"

# Matches DuckDuckGo's HTML result markup as observed live (2026-08):
# <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=<url>&rut=...">title</a>
_RESULT_LINK_RE = re.compile(
    r'class="result__a"\s+href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL,
)
_SNIPPET_RE = re.compile(
    r'class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_text(raw: str) -> str:
    return html.unescape(_TAG_RE.sub("", raw)).strip()


def _resolve_target_url(ddg_href: str) -> str:
    """DuckDuckGo's HTML results link through its own redirector
    (``//duckduckgo.com/l/?uddg=<url-encoded-real-url>&rut=...``) rather
    than the real target directly — unwrap it so callers get an actual,
    followable URL."""
    if ddg_href.startswith("//"):
        ddg_href = "https:" + ddg_href
    parsed = urlparse(ddg_href)
    qs = parse_qs(parsed.query)
    target = qs.get("uddg", [None])[0]
    return unquote(target) if target else ddg_href


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str

    def to_dict(self) -> dict[str, str]:
        return {"title": self.title, "url": self.url, "snippet": self.snippet}


class WebSearchConnector:
    """One real, read-only capability: search the public web via DuckDuckGo.

    No API key, no account — the tradeoff for that is markup-scraping
    fragility (see module docstring) and DuckDuckGo's own rate limiting,
    which surfaces as a real timeout/non-200, not a fabricated result set.
    """

    NAME = "web_search"

    def __init__(self, *, timeout: float = 10.0, max_results: int = 5) -> None:
        self._timeout = timeout
        self._max_results = max_results

    async def search(self, query: str, *, max_results: int | None = None) -> list[WebSearchResult]:
        query = query.strip()
        if not query:
            return []
        limit = max_results or self._max_results

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                _SEARCH_URL,
                params={"q": query},
                headers={"User-Agent": _USER_AGENT},
                follow_redirects=True,
            )
            response.raise_for_status()
            body = response.text

        links = _RESULT_LINK_RE.findall(body)
        snippets = _SNIPPET_RE.findall(body)
        if not links:
            logger.warning(
                "web search for %r returned a 200 but no parseable result markup "
                "— DuckDuckGo's HTML may have changed", query,
            )

        results: list[WebSearchResult] = []
        for i, (href, title_html) in enumerate(links[:limit]):
            snippet = _clean_text(snippets[i]) if i < len(snippets) else ""
            results.append(WebSearchResult(
                title=_clean_text(title_html),
                url=_resolve_target_url(href),
                snippet=snippet,
            ))
        return results


def web_search_tool_schema(max_results: int = 5) -> dict[str, Any]:
    """Ollama/OpenAI-shaped tool declaration for ``chat_events(tools=...)``."""
    return {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the public internet for current information. Use this "
                "when the answer requires up-to-date facts, real URLs, or "
                "anything outside your training data — not for general "
                "knowledge you already have."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": f"Number of results to return (default {max_results}).",
                    },
                },
                "required": ["query"],
            },
        },
    }
