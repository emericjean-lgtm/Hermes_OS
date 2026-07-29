"""Runtime Adapter (HOS-055C).

Exposes Oh My Pi as a runtime candidate to Runtime Orchestrator (HOS-038).
Provides: LSP capability, DAP capability, AST processing, code execution,
model info, cost estimation, suitability scoring.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class OhMyPiRuntimeInfo:
    runtime_id: str = "ohmypi"
    name: str = "Oh My Pi"
    version: str = ""
    capabilities: list[str] = None  # type: ignore
    model_used: str = ""
    estimated_cost_per_token: float = 0.0
    max_context_tokens: int = 128000
    available: bool = True


class OhMyPiRuntimeAdapter:
    def __init__(self, runtime_orchestrator: Any = None,
                 on_event: Optional[Callable] = None) -> None:
        self._lock = threading.RLock()
        self._orchestrator = runtime_orchestrator; self._on_event = on_event
        self._info = OhMyPiRuntimeInfo(
            capabilities=["lsp", "dap", "ast", "code_execution", "python", "javascript"],
        )
        self._suitability_scores: dict[str, float] = {}
        self._registered = False

    def register(self) -> bool:
        self._registered = True
        if self._orchestrator and hasattr(self._orchestrator, 'register_runtime'):
            try:
                self._orchestrator.register_runtime(self._info.runtime_id)
            except Exception: pass
        if self._on_event:
            self._on_event("ohmypi.runtime.registered", {"runtime_id": self._info.runtime_id})
        return True

    def get_suitability(self, task_type: str, context: Optional[dict] = None) -> float:
        """Calculate Oh My Pi's suitability score for a task type (0-1)."""
        base_scores = {
            "code_editing": 0.95, "debugging": 0.92, "code_execution": 0.90,
            "ast_manipulation": 0.95, "lsp_navigation": 0.98, "runtime_testing": 0.85,
            "analysis": 0.60, "code_generation": 0.75, "code_review": 0.70,
            "testing": 0.80, "documentation": 0.40, "deployment": 0.30,
        }
        score = base_scores.get(task_type, 0.50)
        if context:
            lang = context.get("language", "")
            if lang in ("python", "typescript", "javascript", "go", "rust"):
                score += 0.05
            if context.get("needs_debugger"): score += 0.10
            if context.get("needs_lsp"): score += 0.08
        score = min(1.0, score)
        self._suitability_scores[task_type] = score
        return score

    def recommend(self, task_type: str, context: Optional[dict] = None) -> dict:
        suitability = self.get_suitability(task_type, context)
        return {"runtime_id": self._info.runtime_id, "name": self._info.name,
                "suitability": round(suitability, 2),
                "capabilities": self._info.capabilities,
                "recommended": suitability >= 0.70}

    def get_info(self) -> OhMyPiRuntimeInfo:
        return self._info

    def update_capabilities(self, capabilities: list[str]) -> None:
        with self._lock: self._info.capabilities = capabilities

    def set_version(self, version: str) -> None:
        self._info.version = version

    def stats(self) -> dict:
        return {"registered": self._registered, "runtime_id": self._info.runtime_id,
                "capabilities": self._info.capabilities,
                "avg_suitability": round(sum(self._suitability_scores.values()) / max(len(self._suitability_scores), 1), 2),
                "tasks_evaluated": len(self._suitability_scores)}
