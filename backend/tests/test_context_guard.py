"""The served-context guard (HOS-091).

Exists because HOS-090 was a failure with no error in it: Ollama served 8192
while devstral advertises 131072, every request succeeded, the mission
reported 5/5, and the tool schema had been silently truncated out of the
prompt — so the agent truthfully answered that it had no file access and
invented file contents instead.

Nothing in a request can correct this: Hermes Agent reaches Ollama over the
OpenAI-compatible /v1 endpoint, which carries no num_ctx, so Ollama's own
default wins. Hermes OS can therefore only detect it and say so — which
makes the detector itself worth testing carefully.
"""
from __future__ import annotations

from backend.model_intelligence.model_intelligence_models import ModelProfile
from backend.runtime.context_guard import (
    OLLAMA_CONTEXT_ENV,
    check_served_context,
    report,
)


def test_served_below_requirement_is_degraded():
    check = check_served_context("devstral", 8192, supported=131072)

    assert check.degraded
    assert check.required == ModelProfile.AGENTIC_MIN_CONTEXT


def test_sufficient_context_is_not_degraded():
    assert not check_served_context("devstral", 65536).degraded
    assert not check_served_context("devstral", 131072).degraded


def test_unmeasured_context_is_not_reported_as_degraded():
    """No model resident means nothing has been served yet. Warning on an
    unknown would fire on every cold start and train operators to ignore
    the one message that matters."""
    assert not check_served_context("devstral", None).degraded


def test_supported_context_does_not_excuse_a_starved_runtime():
    """The whole bug in one assertion: advertising 131072 changes nothing
    if 8192 is what gets served."""
    assert check_served_context("devstral", 8192, supported=131072).degraded


def test_remediation_names_the_real_lever():
    check = check_served_context("devstral", 8192)

    assert OLLAMA_CONTEXT_ENV in check.remediation
    assert str(ModelProfile.AGENTIC_MIN_CONTEXT) in check.remediation


def test_report_publishes_an_actionable_event():
    published: list[tuple[str, dict]] = []

    degraded = report(
        check_served_context("devstral", 8192, supported=131072),
        publish=lambda name, payload: published.append((name, payload)),
    )

    assert degraded
    assert len(published) == 1
    name, payload = published[0]
    assert name == "runtime.context_degraded"
    assert payload["served_context"] == 8192
    assert payload["required_context"] == ModelProfile.AGENTIC_MIN_CONTEXT
    assert payload["supported_context"] == 131072
    assert OLLAMA_CONTEXT_ENV in payload["remediation"]


def test_report_stays_silent_when_healthy():
    published: list = []

    assert not report(
        check_served_context("devstral", 131072),
        publish=lambda name, payload: published.append((name, payload)),
    )
    assert published == []


def test_report_survives_a_broken_publisher():
    """Telemetry must never be able to break startup — this runs inside the
    boot sequence."""
    def _explode(*_a, **_k):
        raise RuntimeError("event hub down")

    assert report(check_served_context("devstral", 8192), publish=_explode)
