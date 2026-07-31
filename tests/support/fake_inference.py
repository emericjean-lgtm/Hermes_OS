"""A fake inference call for unit tests (R-001).

Why this exists. R-001 replaced the simulated execution step in
``MissionExecutor`` with a real runtime call, which is correct for production and
ruinous for a unit suite: every ``execute_task`` test started making a live LLM
request and ``tests/architecture/test_execution.py`` went from about a second to
sixteen minutes.

The fix follows the convention the codebase already uses for its agents — see
``backend/agents/minerva.py``: "fully testable with a fake Ollama client". Only
the network call is replaced. The executor, its telemetry, the artifact write,
the validator, the retry logic and the scheduler are all still the production
code paths, so these remain real tests of the pipeline rather than tests of a
stub.

Real-execution coverage lives in ``tests/integration/test_real_execution.py``,
which talks to an actual runtime and skips when none is reachable.
"""

from __future__ import annotations

from typing import Any

#: What the fake completion returns. Deliberately looks like a real answer so
#: assertions about result content stay meaningful.
FAKE_COMPLETION = "def reverse_string(s):\n    return s[::-1]"


class FakeChatResponse:
    """Mirrors ``backend.connectors.ollama_client.ChatResponse``."""

    def __init__(self, content: str, model: str) -> None:
        self.content = content
        self.metadata: dict[str, Any] = {
            "model": model,
            "provider": "ollama",
            "fake": True,
        }


async def fake_chat(*, messages: list[dict[str, Any]], model: str) -> FakeChatResponse:
    """Stand-in for ``RealTaskExecutor._default_chat``: no socket, same shape."""
    return FakeChatResponse(FAKE_COMPLETION, model)


def install(monkeypatch: Any) -> None:
    """Point ``RealTaskExecutor``'s default inference at :func:`fake_chat`."""
    from backend.execution.task_executor import RealTaskExecutor

    async def _patched(self: Any, *, messages: list[dict[str, Any]], model: str) -> Any:
        return await fake_chat(messages=messages, model=model)

    monkeypatch.setattr(RealTaskExecutor, "_default_chat", _patched, raising=True)
