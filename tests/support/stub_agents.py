"""Test-only doubles for the specialised agents' MCP adapters.

``KlaatCodeAgent``, ``OhMyPiAgent`` and ``CodeIntelligenceAgent`` used to fall
back to ``success = True`` with ``{"status": "simulated"}`` whenever no MCP
adapter was bound, so a Hermes running without those agents installed reported
every task as completed. R-002 P5 made that path report failure, which is what
actually happened — the work did not occur.

A number of tests construct the agents bare and assert that execution
*succeeds*, which was asserting the fabricated-success behaviour rather than any
real one. :func:`install` gives them an adapter that genuinely answers, so the
assertion becomes "given something that executes, execution succeeds". The
production fallback keeps reporting failure.

Mirrors the ``tests.support.fake_inference.install`` convention.
"""

from __future__ import annotations

from typing import Any


class _StubStatus:
    value = "success"


class _StubResponse:
    def __init__(self, action: Any) -> None:
        self.status = _StubStatus()
        self.error = ""
        self.data = {"stub": True, "action": str(action)}
        self.duration_ms = 1.0


class StubMCPAdapter:
    """Minimal stand-in for an MCP adapter that actually answers."""

    def execute(self, action: Any, parameters: Any = None,
                agent_id: str = "", mission_id: str = "") -> _StubResponse:
        return _StubResponse(action)


def install(monkeypatch: Any) -> None:
    """Bind a stub adapter to any specialised agent built without one."""
    from backend.agents.specialized.code_intelligence import (
        code_intelligence_agent as ci_mod,
    )
    from backend.agents.specialized.klaatcode import klaatcode_agent as kc_mod
    from backend.agents.specialized.ohmypi import ohmypi_agent as omp_mod

    for module, cls_name in ((kc_mod, "KlaatCodeAgent"), (omp_mod, "OhMyPiAgent")):
        cls = getattr(module, cls_name)
        original = cls.__init__

        def make_init(original_init):
            def __init__(self, *args, **kwargs):
                original_init(self, *args, **kwargs)
                if getattr(self, "_mcp_adapter", None) is None:
                    self._mcp_adapter = StubMCPAdapter()
            return __init__

        monkeypatch.setattr(cls, "__init__", make_init(original))

    # CodeIntelligenceAgent routes to the two leaf agents rather than to an
    # adapter of its own, and falls back the same way when they are absent.
    ci_cls = ci_mod.CodeIntelligenceAgent
    ci_original = ci_cls.__init__

    def _ci_init(self, *args, **kwargs):
        ci_original(self, *args, **kwargs)
        if getattr(self, "_klaatcode_agent", None) is None:
            self._klaatcode_agent = kc_mod.KlaatCodeAgent()
        if getattr(self, "_ohmypi_agent", None) is None:
            self._ohmypi_agent = omp_mod.OhMyPiAgent()

    monkeypatch.setattr(ci_cls, "__init__", _ci_init)
