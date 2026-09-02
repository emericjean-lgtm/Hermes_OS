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


async def fake_chat(*, messages: list[dict[str, Any]], model: str,
                     num_ctx: "int | None" = None) -> FakeChatResponse:
    """Stand-in for ``RealTaskExecutor._default_chat``: no socket, same shape."""
    return FakeChatResponse(FAKE_COMPLETION, model)


def install(monkeypatch: Any) -> None:
    """Neutraliser **les trois** sorties d'inference de l'executeur.

    HOS-213. Cette fonction ne patchait que ``_default_chat``. Or
    ``execute()`` choisit entre trois producteurs d'appel :

    ==============================  =======================================
    Condition                       Producteur
    ==============================  =======================================
    runtime ``hermes-agent``        ``_hermes_agent_chat_for`` — sous-processus
    mission liee a un workspace     ``_chat_with_tools_for`` — boucle d'outils
    sinon                           ``_default_chat`` — appel simple
    ==============================  =======================================

    Le premier est le cas **par defaut** : Hermes Agent est le cerveau des
    missions, et une ``ExecutionMeta`` sans workspace y aboutit. La garde
    ne le couvrait pas, si bien que
    ``tests/architecture/test_execution.py::test_execute_single_task`` et
    ``tests/autonomous/test_autonomous_core.py::test_get_goal`` lançaient un
    vrai sous-processus et **bloquaient l'arbre `tests/` entier** — jamais
    vu, parce que la boucle documentee dans ``CLAUDE.md`` n'execute que
    ``backend/tests``.

    Patcher un seul chemin sur trois, c'est une garde qui protege le cas
    qu'on n'emprunte pas.
    """
    from backend.execution.task_executor import RealTaskExecutor

    async def _patched(self: Any, *, messages: list[dict[str, Any]], model: str,
                       num_ctx: "int | None" = None) -> Any:
        return await fake_chat(messages=messages, model=model, num_ctx=num_ctx)

    def _producteur(self: Any, *args: Any, **kwargs: Any) -> Any:
        """Rendre un appelable de la meme forme, sans socket ni processus."""
        async def _appel(*, messages: list[dict[str, Any]], model: str,
                         num_ctx: "int | None" = None) -> Any:
            return await fake_chat(messages=messages, model=model,
                                   num_ctx=num_ctx)
        return _appel

    monkeypatch.setattr(RealTaskExecutor, "_default_chat", _patched, raising=True)
    for producteur in ("_hermes_agent_chat_for", "_chat_with_tools_for"):
        if hasattr(RealTaskExecutor, producteur):
            monkeypatch.setattr(RealTaskExecutor, producteur, _producteur,
                                raising=True)
