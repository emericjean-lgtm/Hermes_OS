"""Veritas — QA agent that reviews other agents' work (cahier des charges
§9.1, §9.3, §16: "Sortie -> verdict + corrections").

review() is pure prompt-construction + chat completion (inherited from
BaseAgent.respond()), so it's fully testable with a fake Ollama client.
parse_verdict() is a plain string parser with no LLM/network dependency —
it turns Veritas's constrained-format reply back into a structured verdict
so callers don't have to scrape free-form prose. The format is enforced
by instruction only (LLMs can still drift from it), so parse_verdict()
degrades gracefully: anything it can't confidently parse lands in `raw`
instead of raising.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from backend.agents.base_agent import BaseAgent
from backend.core.router import RoutingDecision

_VALID_VERDICTS = {"approved", "needs_revision", "rejected"}


class VeritasAgent(BaseAgent):
    name = "veritas"

    @property
    def default_task_type(self) -> str:
        return "verification"

    async def review(
        self,
        output: str,
        *,
        context: str = "",
        criteria: list[str] | None = None,
    ) -> tuple[RoutingDecision, AsyncIterator[str]]:
        """Ask the LLM to review `output` (another agent's work) and reply
        in Veritas's fixed VERDICT/ISSUES/CORRECTIONS format. `context`
        describes the task the output was meant to accomplish; `criteria`
        are extra things to specifically check (e.g. "no hardcoded model
        names", "matches cahier des charges §17")."""
        messages = [
            {"role": "system", "content": self._build_system_prompt(context, criteria)},
            {"role": "user", "content": output},
        ]
        return await self.respond(messages, task_type=self.default_task_type, sensitivity="critical")

    @staticmethod
    def _build_system_prompt(context: str, criteria: list[str] | None) -> str:
        criteria_block = (
            "\n".join(f"- {c}" for c in criteria) if criteria else "- general correctness and completeness"
        )
        context_block = context or "No additional context was provided."
        return (
            "You are Veritas, a rigorous QA reviewer for another agent's work. "
            "You do not redo the work — you check it and report problems. "
            "Reply in EXACTLY this format, nothing before or after it:\n\n"
            "VERDICT: <approved|needs_revision|rejected>\n"
            "ISSUES:\n"
            "- <one issue per line, or a single line \"- none\" if there are none>\n"
            "CORRECTIONS:\n"
            "<concrete suggested fixes, or \"none\" if verdict is approved>\n\n"
            f"Task context:\n{context_block}\n\n"
            f"Review criteria:\n{criteria_block}"
        )

    @staticmethod
    def parse_verdict(text: str) -> dict:
        """Parse a VERDICT/ISSUES/CORRECTIONS reply into a structured dict:
        {verdict, issues: list[str], corrections: str, raw: str}. `verdict`
        falls back to "unknown" and `issues` to [] if the reply doesn't
        follow the format — callers should treat that as "review failed to
        parse", not as an approval."""
        raw = text
        verdict = "unknown"
        issues: list[str] = []
        corrections = ""

        lines = text.splitlines()
        section = None
        corrections_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.upper().startswith("VERDICT:"):
                candidate = stripped.split(":", 1)[1].strip().lower()
                if candidate in _VALID_VERDICTS:
                    verdict = candidate
                section = None
            elif stripped.upper() == "ISSUES:":
                section = "issues"
            elif stripped.upper() == "CORRECTIONS:":
                section = "corrections"
            elif section == "issues" and stripped.startswith("-"):
                item = stripped[1:].strip()
                if item and item.lower() != "none":
                    issues.append(item)
            elif section == "corrections" and stripped:
                corrections_lines.append(stripped)

        corrections = "\n".join(corrections_lines)
        if corrections.strip().lower() == "none":
            corrections = ""

        return {"verdict": verdict, "issues": issues, "corrections": corrections, "raw": raw}
