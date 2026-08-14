"""Detects a role configured onto a model the runtime does not have.

HOS-108 cost a broken chat path that nothing announced. The model cleanup
renamed 21 Ollama tags down to 11, baking each model's measured context
into its name, and ``config/models.yaml`` was not updated with it. Eleven
of twelve roles then pointed at a tag that no longer existed.

The failure had no error in it from where anyone was looking. Ollama
answered ``/api/chat`` with 404; the chat route recorded ``result="failed"``
in the audit log and re-raised, exactly as it should — but a streaming
response commits its HTTP status before the first chunk, so the client
still saw 200 with an empty body. The Assistant tab showed silence. Eight
tests had been reporting it for hours and were dismissed as machine
contention.

This module is the check that would have caught it at startup, in one line,
before a single request. It compares what is configured against what is
installed, and says which is missing — never "a model is missing
somewhere".

The comparison is pure so the policy is testable without a live Ollama:
a test that needs a particular set of models installed measures the
machine it runs on, not the code.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable, Optional

logger = logging.getLogger("hermes_os.runtime.model_guard")


def normalise(tag: str) -> str:
    """``qwen3.6-35b-128k`` and ``qwen3.6-35b-128k:latest`` are one model.

    Ollama reports installed tags with an explicit ``:latest`` that
    configuration files almost never write. Comparing the raw strings makes
    every correctly configured role look missing.
    """
    return tag[: -len(":latest")] if tag.endswith(":latest") else tag


@dataclass(frozen=True)
class MissingRole:
    """A role whose model is not installed, named so it can be fixed."""

    role: str
    model: str

    def as_event(self) -> dict[str, Any]:
        return {"role": self.role, "model": self.model,
                "remediation": f"Install it (`ollama pull {self.model}`) or point "
                               f"the `{self.role}` role at an installed tag in "
                               f"config/models.yaml."}


def check_roles(roles: dict[str, dict], installed: Iterable[str]) -> list[MissingRole]:
    """Pure comparison of configured roles against installed tags.

    Returns them in configuration order rather than sorted: reading the
    report next to the file it is about is the point.
    """
    present = {normalise(tag) for tag in installed}
    return [MissingRole(role=name, model=str(spec.get("model") or ""))
            for name, spec in (roles or {}).items()
            if normalise(str(spec.get("model") or "")) not in present]


#: Ollama's own limit on resident models. Named so the message can be
#: exact rather than telling an operator to "increase something".
OLLAMA_MAX_LOADED_ENV = "OLLAMA_MAX_LOADED_MODELS"


def check_residency(roles: dict[str, dict], max_loaded: Optional[int]) -> list[str]:
    """Roles asking to stay resident on a runtime that will evict them.

    ``always_loaded: true`` sends ``keep_alive: -1``, which stops a model
    expiring for idleness. It does **not** survive another model being
    requested: ``OLLAMA_MAX_LOADED_MODELS`` wins, and at 1 there is exactly
    one resident model at any time.

    So the flag can describe an intent the runtime refuses, and nothing
    said so — the configuration read as though swift and the embedding
    model were permanently in VRAM while in practice each request evicted
    the previous one. The requirement (§22, keep the fast models warm) is
    sound; what was wrong was believing it satisfied.

    Returns [] when ``max_loaded`` is unknown. Guessing would train an
    operator to ignore the warning — the same rule ContextCheck follows
    when no model is resident to measure.
    """
    if max_loaded is None or max_loaded <= 0:
        return []
    demandes = [nom for nom, spec in (roles or {}).items()
                if (spec or {}).get("always_loaded")]
    return demandes if len(demandes) > max_loaded else []


def report_residency(roles_epingles: list[str], max_loaded: int,
                     publish: Optional[Any] = None) -> bool:
    """Log the contradiction between configuration and runtime."""
    if not roles_epingles:
        return False
    logger.warning(
        "%s role(s) ask to stay resident (%s) but %s=%s — Ollama keeps only "
        "%s model(s) loaded and evicts the rest on the next request, so the "
        "flag stops idle expiry and nothing more. Either raise %s (check the "
        "combined VRAM first) or stop reading this configuration as though "
        "those models were warm.",
        len(roles_epingles), ", ".join(roles_epingles), OLLAMA_MAX_LOADED_ENV,
        max_loaded, max_loaded, OLLAMA_MAX_LOADED_ENV,
    )
    if publish is not None:
        try:
            from backend.runtime.events.event_types import RuntimeEventType

            publish(RuntimeEventType.RUNTIME_RESIDENCY_UNSATISFIABLE.value,
                    {"roles": roles_epingles, "max_loaded": max_loaded})
        except Exception:  # pragma: no cover - never break startup over telemetry
            logger.debug("publishing residency_unsatisfiable failed", exc_info=True)
    return True


def report(missing: list[MissingRole], publish: Optional[Any] = None) -> bool:
    """Log and publish missing role models. Returns True when any is missing.

    ERROR rather than WARNING, and one line per role rather than a count:
    this condition breaks every request routed to that role, and an
    operator needs the role name and the tag to act — not a number.
    """
    if not missing:
        return False
    for entry in missing:
        logger.error(
            "role %r is configured onto %r, which is not installed — every "
            "request routed here will fail with a 404 from Ollama, and a "
            "streaming response will surface it as an empty answer rather "
            "than an error. %s",
            entry.role, entry.model, entry.as_event()["remediation"],
        )
    if publish is not None:
        try:
            from backend.runtime.events.event_types import RuntimeEventType

            for entry in missing:
                publish(RuntimeEventType.RUNTIME_MODEL_MISSING.value, entry.as_event())
        except Exception:  # pragma: no cover - never break startup over telemetry
            logger.debug("publishing model_missing failed", exc_info=True)
    return True
