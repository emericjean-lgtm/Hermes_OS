"""Minerva — research & RAG agent (cahier des charges §9.1, §10.5).

Split into retrieve() and synthesize() on purpose:
- retrieve() delegates to Echo's documentary memory (EchoAgent.recall),
  which needs a live Ollama server for embeddings — same constraint as
  everywhere else Echo's ChromaDB side is touched.
- synthesize() is pure prompt-construction + chat completion (inherited
  from BaseAgent.respond()), so it's fully testable with a fake Ollama
  client and hand-built passages, independent of retrieval.
research() just chains the two for the full "ask a question, get a
cited answer" loop.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from backend.agents.base_agent import BaseAgent
from backend.core.agent_registry import get_agent_registry
from backend.core.router import RoutingDecision


class MinervaAgent(BaseAgent):
    name = "minerva"

    @property
    def default_task_type(self) -> str:
        return "research"

    def retrieve(self, query: str, *, n_results: int = 5) -> list[dict]:
        """Fetch passages relevant to `query` from Echo's documentary
        memory. Needs a live Ollama server for embeddings."""
        echo = get_agent_registry().get("echo")
        return echo.recall(query, n_results=n_results)

    async def synthesize(
        self, query: str, passages: list[dict]
    ) -> tuple[RoutingDecision, AsyncIterator[str]]:
        """Ask the LLM to answer `query` using only `passages` as
        context, citing them by [n]. No retrieval here — pass in
        whatever passages you already have."""
        messages = [
            {"role": "system", "content": self._build_system_prompt(passages)},
            {"role": "user", "content": query},
        ]
        return await self.respond(messages, task_type=self.default_task_type)

    async def research(
        self, query: str, *, n_results: int = 5
    ) -> tuple[RoutingDecision, AsyncIterator[str], list[dict]]:
        """Full RAG loop: retrieve() then synthesize(). Returns
        (decision, stream, passages) so callers can show sources
        alongside (or ahead of) the synthesized answer."""
        passages = self.retrieve(query, n_results=n_results)
        decision, stream = await self.synthesize(query, passages)
        return decision, stream, passages

    @staticmethod
    def _build_system_prompt(passages: list[dict]) -> str:
        if not passages:
            context = "No relevant passages were found."
        else:
            context = "\n\n".join(
                f"[{i}] (source: {p.get('metadata', {}).get('source', 'unknown')})\n"
                f"{p['content']}"
                for i, p in enumerate(passages, start=1)
            )
        return (
            "Answer the user's question using ONLY the context passages below. "
            "Cite passages by their [n] number. If the context doesn't contain "
            "the answer, say so plainly instead of guessing.\n\n" + context
        )
