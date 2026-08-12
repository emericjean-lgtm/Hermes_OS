"""Detects a runtime that serves less context than agentic work needs.

HOS-090 cost a long debugging session to a failure with no error in it:
Ollama was serving 8192 tokens while devstral advertises 131072 and Hermes
Agent's own cache knew it. Nothing failed. The model answered, the mission
completed, the report said 5/5 — and the tool schema had been silently
truncated out of the prompt, so the agent correctly reported that it had no
file access and invented file contents instead.

The cause is structural rather than accidental: Hermes Agent reaches Ollama
over the OpenAI-compatible ``/v1`` endpoint, which carries no ``num_ctx``,
so Ollama applies its own ``OLLAMA_CONTEXT_LENGTH`` default. Nothing in the
request can override it, which means Hermes OS cannot fix this per call —
it can only detect it and say so loudly.

This module is that detector. It answers "what is actually being served",
never "what does the model support" — conflating those two is the bug.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

from backend.model_intelligence.model_intelligence_models import ModelProfile

logger = logging.getLogger("hermes_os.runtime.context_guard")

#: Ollama's own environment variable, and the only lever that changes what
#: it serves. Named here so the remediation message can be exact rather
#: than telling an operator to "increase the context somewhere".
OLLAMA_CONTEXT_ENV = "OLLAMA_CONTEXT_LENGTH"


@dataclass(frozen=True)
class ContextCheck:
    """What a runtime is really handing out, versus what agents need."""

    model: str
    served: Optional[int]
    required: int
    supported: Optional[int] = None

    @property
    def degraded(self) -> bool:
        """True only when we measured a real, insufficient value.

        An unknown served context is not reported as degraded: no model was
        resident, so nothing has been served yet and there is nothing to
        judge. Guessing here would train operators to ignore the warning.
        """
        return self.served is not None and self.served < self.required

    @property
    def remediation(self) -> str:
        env_value = os.environ.get(OLLAMA_CONTEXT_ENV)
        current = f" (currently {env_value})" if env_value else " (currently unset)"
        return (
            f"Set {OLLAMA_CONTEXT_ENV}={self.required} in Ollama's own "
            f"environment{current} and restart it. A command-line or API "
            f"argument cannot fix this: the OpenAI-compatible /v1 endpoint "
            f"carries no num_ctx, so Ollama's default is the only lever."
        )

    def as_event(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "served_context": self.served,
            "required_context": self.required,
            "supported_context": self.supported,
            "remediation": self.remediation,
        }


def check_served_context(
    model: str,
    served: Optional[int],
    *,
    supported: Optional[int] = None,
    required: int = ModelProfile.AGENTIC_MIN_CONTEXT,
) -> ContextCheck:
    """Pure comparison, so the policy can be tested without a live Ollama."""
    return ContextCheck(model=model, served=served, required=required,
                        supported=supported)


def report(check: ContextCheck, publish: Optional[Any] = None) -> bool:
    """Log and publish a degraded context. Returns True when degraded.

    Deliberately noisy at WARNING: the whole point is that this condition is
    invisible in normal operation — every request succeeds — and only shows
    up much later as an agent that "cannot" use its tools.
    """
    if not check.degraded:
        return False
    logger.warning(
        "runtime serving %s tokens of context for %r, below the %s needed for "
        "agentic work — tool schemas will be truncated and the agent will "
        "behave as though it has no tools. %s",
        check.served, check.model, check.required, check.remediation,
    )
    if publish is not None:
        try:
            from backend.runtime.events.event_types import RuntimeEventType

            publish(RuntimeEventType.RUNTIME_CONTEXT_DEGRADED.value, check.as_event())
        except Exception:  # pragma: no cover - never break startup over telemetry
            logger.debug("publishing context_degraded failed", exc_info=True)
    return True
