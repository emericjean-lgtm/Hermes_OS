"""Abstract base class every Hermes agent implements.

An agent does not own a fixed model — it asks the ModelRouter for the best
model given a task_type, so the economy-of-VRAM principle (§7, principle 10
of the cahier des charges) is enforced centrally rather than per agent.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, ClassVar, Optional

#: Real tool-calling rounds are bounded: a model that keeps asking for the
#: same tool without ever producing a final answer stops after this many
#: round trips rather than looping forever.
_MAX_TOOL_ROUNDS = 3

from backend.connectors.ollama_client import OllamaClientProtocol, StreamChunk
from backend.core.router import ModelRouter, RoutingDecision

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    name: ClassVar[str]

    def __init__(
        self,
        ollama_client: OllamaClientProtocol,
        router: ModelRouter,
        models_config: dict,
        cloud_client: Optional[Any] = None,
    ) -> None:
        """``cloud_client`` (HOS-066C) is an ``OpenRouterClient``-shaped
        object (``chat_events(model, messages, ...)``), optional and
        ``None`` by default — every agent runs local-only unless the
        bootstrap wires one in (only when ``OPENROUTER_API_KEY`` is
        configured). It is a *resilience* fallback, not a capability
        escalation: it is only ever tried when the local stream fails
        before yielding a single chunk — see ``respond_events``."""
        self._ollama = ollama_client
        self._router = router
        self._models_config = models_config
        self._cloud_client = cloud_client

    @property
    @abstractmethod
    def default_task_type(self) -> str:
        """Task type used to look up a model in the routing matrix when the
        caller doesn't specify one explicitly."""

    async def routing_decision(
        self, task_type: str | None = None, *,
        forced_role: str | None = None, forced_thinking: bool | None = None,
    ) -> RoutingDecision:
        """``forced_role`` (HOS-075 — manual model choice / reasoning effort
        from the Assistant) bypasses ranking entirely: the named role *is*
        the decision. Still resolved through the same ``RoutingDecision``
        shape as automatic routing, so a manual pick is exactly as visible
        in the audit log and the "why this model?" panel as an automatic
        one — never a second, undocumented code path."""
        resolved_task_type = task_type or self.default_task_type
        if forced_role is not None:
            return self._router.decision_for_role(
                forced_role, resolved_task_type, thinking=forced_thinking,
            )
        running = await self._ollama.list_running_models()
        loaded_tags = self._router.running_model_tags(running)
        return self._router.select_model(
            resolved_task_type,
            loaded_models=loaded_tags,
        )

    def generation_params(self, sensitivity: str = "standard") -> dict:
        return self._models_config["generation_defaults"][sensitivity]

    async def respond(
        self,
        messages: list[dict[str, Any]],
        *,
        task_type: str | None = None,
        sensitivity: str = "standard",
    ) -> tuple[RoutingDecision, AsyncIterator[str]]:
        """Resolve a model via the router, then return the routing decision
        alongside the streamed response so callers can log/display both."""
        decision, events = await self.respond_events(
            messages, task_type=task_type, sensitivity=sensitivity
        )

        async def content_only():
            async for chunk in events:
                if chunk.kind == "content":
                    yield chunk.text

        return decision, content_only()

    async def respond_events(
        self,
        messages: list[dict[str, Any]],
        *,
        task_type: str | None = None,
        sensitivity: str = "standard",
        forced_role: str | None = None,
        forced_thinking: bool | None = None,
        tools: Optional[list[dict[str, Any]]] = None,
        tool_executor: Optional[Callable[[str, dict[str, Any]], Awaitable[str]]] = None,
    ) -> tuple[RoutingDecision, AsyncIterator[StreamChunk]]:
        """Same as `respond`, but the reasoning phase is surfaced instead
        of discarded — for callers with a human on the other end, who
        would otherwise face a silent wait as long as the reasoning takes
        (measured: 42 s on a code_analysis task).

        ``tools``/``tool_executor`` (real internet search, Assistant chat
        feedback round) are both optional and ``None`` by default, so
        every existing caller is unaffected. Passing ``tools`` without a
        ``tool_executor`` would let a model ask for a tool call that never
        runs — the caller must supply both or neither.
        """
        decision = await self.routing_decision(
            task_type, forced_role=forced_role, forced_thinking=forced_thinking,
        )
        params = self.generation_params(sensitivity)
        resolved_task_type = task_type or self.default_task_type

        if tools and tool_executor is not None:
            stream = self._stream_with_tools(
                list(messages), decision, params, resolved_task_type,
                tools, tool_executor,
            )
            return decision, stream

        # Constructed here, in a plain async method, not inside the
        # generator below — chat_events() is itself an async generator
        # function for the real OllamaClient (and is expected to be for any
        # OllamaClientProtocol implementation), so calling it does not run
        # any of its body; only iterating does. Keeping the call at this
        # level preserves that same "call now, iterate later" timing
        # exactly as before this method existed, rather than deferring the
        # call itself into the wrapper's lazy body.
        local_stream = self._ollama.chat_events(
            decision.model,
            messages,
            temperature=params["temperature"],
            top_p=params["top_p"],
            # From the routing decision, not resolved here: the value is
            # per task_type (config/models.yaml → `thinking`) and must be
            # the same one the audit log records. See §22.1 — reasoning
            # costs ~3.5 s of silence before the first visible word.
            think=decision.thinking,
            # Per-role, chosen from real benchmark data (HOS-065C) — every
            # chat_events() call used to fall back to one global default
            # (8192) regardless of which model it was actually talking to.
            num_ctx=decision.num_ctx,
        )
        stream = self._stream_with_cloud_fallback(
            local_stream, params, resolved_task_type, messages,
        )
        return decision, stream

    async def _stream_with_tools(
        self,
        messages: list[dict[str, Any]],
        decision: RoutingDecision,
        params: dict,
        task_type: str,
        tools: list[dict[str, Any]],
        tool_executor: Callable[[str, dict[str, Any]], Awaitable[str]],
    ) -> AsyncIterator[StreamChunk]:
        """Real tool-calling round trip (Assistant chat feedback round).

        A model can ask for a tool in its first turn; this actually
        executes it via ``tool_executor`` and feeds the real result back
        for a second (bounded) turn — offering ``tools`` without this loop
        would let the model ask for a search that nothing ever performs,
        which is a more elaborate way of silently ignoring the request.
        Bounded to ``_MAX_TOOL_ROUNDS`` so a model that keeps asking for
        tools without ever answering cannot hang the response forever.
        """
        working_messages = list(messages)
        for _round in range(_MAX_TOOL_ROUNDS):
            local_stream = self._ollama.chat_events(
                decision.model, working_messages,
                temperature=params["temperature"], top_p=params["top_p"],
                think=decision.thinking, num_ctx=decision.num_ctx,
                tools=tools,
            )
            pending_calls: list[dict[str, Any]] = []
            async for chunk in self._stream_with_cloud_fallback(
                local_stream, params, task_type, working_messages,
            ):
                if chunk.kind == "tool_calls":
                    pending_calls.extend(chunk.tool_calls or [])
                yield chunk

            if not pending_calls:
                return

            working_messages.append({
                "role": "assistant", "content": "", "tool_calls": pending_calls,
            })
            for call in pending_calls:
                fn = call.get("function", {})
                name = fn.get("name", "")
                arguments = fn.get("arguments") or {}
                try:
                    result = await tool_executor(name, arguments)
                except Exception as exc:
                    result = f"Tool {name!r} failed: {type(exc).__name__}: {exc}"
                yield StreamChunk(
                    "tool_result", "",
                    tool_calls=[{"name": name, "arguments": arguments, "result": str(result)[:4000]}],
                )
                working_messages.append({"role": "tool", "content": str(result), "tool_name": name})

        # Ran out of rounds without a final answer — observed in practice
        # (gpt-oss:20b) as the model repeatedly refining its search query
        # instead of ever answering from what it already has. Rather than
        # a dead-end apology, force one last real call with no `tools`
        # offered: it physically cannot ask for another search, so it has
        # to synthesize from the real results already gathered above.
        final_stream = self._ollama.chat_events(
            decision.model,
            working_messages + [{
                "role": "user",
                "content": (
                    "Réponds maintenant avec les informations déjà trouvées "
                    "ci-dessus, du mieux que tu peux — aucune nouvelle "
                    "recherche n'est disponible."
                ),
            }],
            temperature=params["temperature"], top_p=params["top_p"],
            think=decision.thinking, num_ctx=decision.num_ctx,
        )
        async for chunk in self._stream_with_cloud_fallback(
            final_stream, params, task_type, working_messages,
        ):
            yield chunk

    async def _stream_with_cloud_fallback(
        self,
        local_stream: AsyncIterator[StreamChunk],
        params: dict,
        task_type: str,
        messages: list[dict[str, Any]],
    ) -> AsyncIterator[StreamChunk]:
        """Local is the unconditional first attempt. A cloud retry (HOS-066C)
        only happens if the local stream fails *before yielding a single
        chunk* — the same guard OllamaClient.chat_events() already applies
        to its own reconnect-on-drop logic (backend/connectors/
        ollama_client.py's ``started`` flag): once the caller has received
        part of an answer, switching runtimes would risk a duplicated or
        incoherent response, which is worse than a clean failure.
        """
        started = False
        local_error: Exception | None = None
        try:
            async for chunk in local_stream:
                started = True
                yield chunk
            return
        except Exception as exc:
            local_error = exc
            if started or self._cloud_client is None:
                raise

        logger.warning(
            "%s: local runtime unreachable (%s: %s) — trying a cloud fallback",
            self.name, type(local_error).__name__, local_error,
        )
        from backend.model_intelligence.routes import get_cloud_fallback_model

        cloud_model = get_cloud_fallback_model(task_type)
        if cloud_model is None:
            raise RuntimeError(
                f"{self.name}: local runtime unreachable and no cloud fallback "
                "is currently available"
            ) from local_error
        async for chunk in self._cloud_client.chat_events(
            cloud_model, messages,
            temperature=params["temperature"], top_p=params["top_p"],
        ):
            yield chunk
