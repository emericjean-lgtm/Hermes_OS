"""Atlas — the developer agent (cahier des charges §9.1, §14.2).

Chat completions go through the router like any other agent, defaulting
to the code_analysis task type (which resolves to qwen3-coder:30b, see
config/models.yaml). File-modifying work does NOT happen through chat
text — it goes through backend/tools/file_tools.py, which always
consults Aegis before writing anything to disk (§17), proposes a diff,
and takes a backup before overwriting an existing file (§14.1).
"""
from __future__ import annotations

from backend.agents.base_agent import BaseAgent


class AtlasAgent(BaseAgent):
    name = "atlas"

    @property
    def default_task_type(self) -> str:
        return "code_analysis"
