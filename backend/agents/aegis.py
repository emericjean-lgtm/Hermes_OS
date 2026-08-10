"""Aegis — the always-on security gate (cahier des charges §9.1, §17).

Aegis does not produce chat completions, so it deliberately does not
subclass BaseAgent: its contract is evaluate(ActionRequest) -> AegisDecision,
not respond(messages) -> streamed text. It still takes the same
(ollama_client, router, models_config) constructor as every other agent so
AgentRegistry can instantiate it uniformly from config/agents.yaml — the
LLM client/router are unused for now (see aegis_engine.py for why the
decision engine is deterministic, not model-based) but kept for the
future advisory pass on ambiguous cases.

evaluate() also publishes to the message bus (core/message_bus.py,
§9.2/§24.4): a VALIDATION_REQUEST from the requesting agent, then a
VALIDATION_GRANTED/VALIDATION_DENIED/ESCALATION from Aegis, in every case
regardless of caller (this HTTP route, an MCP tool, or file_tools.py
called directly from Atlas) — the point of routing this through the bus
here rather than in each caller is that every evaluate() call gets traced
uniformly. ESCALATION covers require_human_validation: §9.2 defines it as
"agent -> user", and a human-validation verdict is exactly that request,
just raised by Aegis on the requesting agent's behalf rather than the
agent asking directly. Reached via the module-level get_message_bus()
singleton rather than constructor injection, the same pattern
MinervaAgent uses to reach Echo (see agents/minerva.py) — it keeps
AgentRegistry's uniform (ollama_client, router, models_config)
construction contract unchanged.

evaluate() also resolves action.project_id into a project root path
(via get_project_store(), the same singleton pattern) and passes it to
AegisEngine.evaluate() as project_root — this narrows the whitelist
further for that one call, never widens it (see aegis_engine.py). Only
existence matters for narrowing, not validation status: an unvalidated
or even archived project's root is still a real, known boundary to
scope an action *down* to. A project_id that doesn't resolve to any
project at all is different — that's treated as REQUIRE_HUMAN_VALIDATION
rather than silently skipping the restriction (don't fail open on the
unexpected, same as an unknown action_type).

Workspace/Filesystem tool layer: evaluate() also calls
_dynamic_allowed_paths() on every invocation and passes the result as
AegisEngine.evaluate()'s extra_allowed_paths — the root_path of every
currently ACTIVE, validation_status="valid" Project, resolved fresh
from ProjectStore each time (nothing cached). This is what lets a
user-registered, validated workspace (e.g. via POST /projects then
POST /projects/{id}/validate) actually grant filesystem access without
editing config/security.yaml's static ALLOWED_PATHS — the two lists
are unioned at the point of check (aegis_engine.py's
_is_within_whitelist), and a Project that stops being active+valid
stops appearing in that union on the very next call.

advise() is the advisory pass mentioned in aegis_engine.py's module
docstring: an LLM opinion attached to a REQUIRE_HUMAN_VALIDATION
decision, for a human reviewer's benefit — never a second vote on the
verdict itself (a no-op on ALLOW/DENY, returns the decision unchanged).
Deliberately a separate method from evaluate() rather than folded into
it: evaluate() is synchronous and every existing caller (file_tools.py,
/security/evaluate, security_evaluate, workflow nodes) depends on that;
advise() needs an LLM call so it has to be async. Callers opt in
explicitly (see /security/evaluate's include_advisory param) — same
"explicit call, no hidden side effect" principle as the self-evolution pipeline.

advise()'s output is cleaned with the same fixed-format-prompt +
text-parsing pattern as VeritasAgent.parse_verdict() (agents/veritas.py),
not Ollama's `think` API parameter. `think=True` was tried first and
confirmed on real hardware (RX 6800, Ollama 0.32.0) NOT to separate
reasoning from content for phi4-reasoning:14b-q4_K_M — a direct
/api/chat call with think:true still returns the whole chain-of-thought
in message.content, no message.thinking field ever appears, despite
`ollama show` declaring the "thinking" capability. So instead the system
prompt demands an "ADVISORY:" marker with nothing after it but the
answer, and _extract_advisory() takes everything after the last such
marker — a human reviewer never sees the model's raw reasoning even
when the model ignores `think` entirely. think=True is still passed as
harmless defense-in-depth for models/Ollama versions where it does work.
"""
from __future__ import annotations

import dataclasses
from typing import ClassVar

from backend.connectors.ollama_client import OllamaClientProtocol
from backend.core.config import get_settings, load_security_config
from backend.core.message_bus import MessageType, get_message_bus
from backend.core.router import ModelRouter
from backend.projects.project_manager import ProjectStatus, ValidationStatus
from backend.projects.store import get_project_store
from backend.memory.db import init_db, make_engine, make_session_factory
from backend.security import approvals
from backend.security.aegis_engine import ActionRequest, AegisDecision, AegisEngine, Verdict
from backend.security.permission_matrix import PermissionMatrix

_ADVISORY_SYSTEM_PROMPT = (
    "You are Aegis's advisory reviewer. A deterministic rules engine has "
    "already decided this action requires human validation. In 2-3 "
    "sentences, explain what about it is worth double-checking before a "
    "human approves it. You are not deciding whether to allow it — only "
    "informing the human's review.\n\n"
    "You may think it through first, but your reply MUST end with a line "
    "reading exactly \"ADVISORY:\" followed by nothing but your 2-3 "
    "sentence note — no further reasoning, headers, or commentary after "
    "it."
)

_VERDICT_MESSAGE_TYPE = {
    Verdict.ALLOW: MessageType.VALIDATION_GRANTED,
    Verdict.DENY: MessageType.VALIDATION_DENIED,
    Verdict.REQUIRE_HUMAN_VALIDATION: MessageType.ESCALATION,
}

_ADVISORY_MARKER = "ADVISORY:"


def _extract_advisory(text: str) -> str:
    """Strip everything up to and including the last "ADVISORY:" marker,
    same degrade-gracefully philosophy as VeritasAgent.parse_verdict():
    a model that ignores the format (or a `think`-less model that never
    needed separating in the first place) still gets its raw text
    returned rather than an empty string, so a human reviewer always has
    something to read even when the format instruction is ignored."""
    idx = text.rfind(_ADVISORY_MARKER)
    if idx == -1:
        return text.strip()
    return text[idx + len(_ADVISORY_MARKER) :].strip()


class AegisAgent:
    name: ClassVar[str] = "aegis"

    def __init__(
        self,
        ollama_client: OllamaClientProtocol,
        router: ModelRouter,
        models_config: dict,
    ) -> None:
        self._ollama = ollama_client
        self._router = router
        self._models_config = models_config

        settings = get_settings()
        matrix = PermissionMatrix(load_security_config())
        self._engine = AegisEngine(matrix, settings.allowed_paths_list)

        # The approvals queue lives here, not in the engine: aegis_engine
        # is deliberately DB-free and pure so a verdict stays reproducible
        # from its inputs alone. Consent is state, so it belongs to the
        # agent that already owns state (project lookup, message bus).
        db_engine = make_engine(settings.sqlite_path)
        init_db(db_engine)
        self._session_factory = make_session_factory(db_engine)

    # ── human approvals (§23 "vue sécurité") ─────────────────────────
    def list_approvals(
        self, *, status: str | None = None, project_id: str | None = None
    ) -> list[dict]:
        with self._session_factory() as session:
            return [
                approvals.to_dict(a)
                for a in approvals.list_approvals(
                    session, status=status, project_id=project_id
                )
            ]

    def decide_approval(self, approval_id: str, *, approved: bool) -> dict | None:
        """Record a human yes/no. An approval authorises exactly one later
        retry of the same action and then expires — it never becomes a
        standing permission."""
        with self._session_factory() as session:
            entry = approvals.decide(session, approval_id, approved=approved)
            return approvals.to_dict(entry) if entry is not None else None

    def evaluate(self, action: ActionRequest) -> AegisDecision:
        bus = get_message_bus()
        bus.publish(
            from_agent=action.requesting_agent,
            to_agent=self.name,
            type_=MessageType.VALIDATION_REQUEST,
            payload={
                "action_type": action.action_type,
                "description": action.description,
                "target_path": action.target_path,
            },
            task_id=action.task_id,
            project_id=action.project_id,
        )

        decision = self._apply_human_consent(action, self._resolve_decision(action))

        bus.publish(
            from_agent=self.name,
            to_agent=action.requesting_agent,
            type_=_VERDICT_MESSAGE_TYPE[decision.verdict],
            payload={
                "verdict": decision.verdict.value,
                "reason": decision.reason,
                "action_type": decision.action_type,
            },
            task_id=action.task_id,
            project_id=action.project_id,
        )

        return decision

    def _apply_human_consent(
        self, action: ActionRequest, decision: AegisDecision
    ) -> AegisDecision:
        """Turn a require_human_validation verdict into ALLOW when a human
        has already approved this exact action, otherwise queue it.

        Only ever acts on REQUIRE_HUMAN_VALIDATION. A DENY is never
        upgraded: those come from the hard boundaries (outside
        ALLOWED_PATHS, outside a project root, missing target_path), which
        no amount of consent should be able to unlock from here.
        """
        if decision.verdict is not Verdict.REQUIRE_HUMAN_VALIDATION:
            return decision

        with self._session_factory() as session:
            consumed = approvals.consume_approval(
                session,
                action_type=action.action_type,
                target_path=action.target_path,
                description=action.description,
            )
            if consumed is not None:
                return AegisDecision(
                    verdict=Verdict.ALLOW,
                    reason=(
                        f"Human approval {consumed.id} accepted for this exact action "
                        f"(single use, granted {consumed.decided_at.isoformat()})."
                    ),
                    action_type=decision.action_type,
                )

            approvals.record_pending(
                session,
                action_type=action.action_type,
                description=action.description,
                reason=decision.reason,
                target_path=action.target_path,
                requesting_agent=action.requesting_agent,
                task_id=action.task_id,
                project_id=action.project_id,
            )

        return decision

    def _dynamic_allowed_paths(self) -> list[str]:
        """Every ACTIVE, validation_status="valid" Project's root_path —
        together with the static ALLOWED_PATHS config, this is the real,
        current whitelist (see AegisEngine.evaluate's extra_allowed_paths
        and this module's docstring). Fetched fresh on every call, never
        cached: an archived, invalidated, or deleted Project must stop
        granting access the moment that happens, not on some later
        refresh. Fails closed (empty list) rather than raising if the
        store is briefly unavailable — a missing grant is safe, a
        crashing security check is not."""
        try:
            projects = get_project_store().list(status=ProjectStatus.ACTIVE)
        except Exception:
            return []
        return [
            p.root_path for p in projects
            if p.root_path and p.validation_status == ValidationStatus.VALID.value
        ]

    def _resolve_decision(self, action: ActionRequest) -> AegisDecision:
        # Widening (extra_paths) and narrowing (project_root below) are
        # gated independently. Widening is the new capability — a
        # Project's root only ever grants access while it is ACTIVE and
        # validation_status="valid" (_dynamic_allowed_paths enforces
        # that). Narrowing is the pre-existing restriction: if a caller
        # names a project_id, its root scopes the action to that folder
        # regardless of validation status — an unvalidated project's root
        # is still a real, known boundary to scope *down* to, even before
        # anyone has confirmed it grants anything on its own.
        extra_paths = self._dynamic_allowed_paths()

        if action.project_id is None:
            return self._engine.evaluate(action, extra_allowed_paths=extra_paths)

        project = get_project_store().get(action.project_id)
        if project is None:
            return AegisDecision(
                verdict=Verdict.REQUIRE_HUMAN_VALIDATION,
                reason=(
                    f"project_id {action.project_id!r} does not resolve to a known "
                    "project — treated as suspicious rather than silently skipping "
                    "project-level restriction (§17.3)."
                ),
                action_type=action.action_type,
            )
        if not project.root_path:
            return self._engine.evaluate(action, extra_allowed_paths=extra_paths)
        return self._engine.evaluate(
            action, project_root=project.root_path, extra_allowed_paths=extra_paths
        )

    async def advise(self, action: ActionRequest, decision: AegisDecision) -> AegisDecision:
        if decision.verdict != Verdict.REQUIRE_HUMAN_VALIDATION:
            return decision

        model = self._router.model_for_role("security")
        messages = [
            {"role": "system", "content": _ADVISORY_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Action type: {action.action_type}\n"
                    f"Description: {action.description}\n"
                    f"Target path: {action.target_path or 'n/a'}\n"
                    f"Engine's reason: {decision.reason}"
                ),
            },
        ]
        params = self._models_config["generation_defaults"]["critical"]
        chunks = [
            chunk
            async for chunk in self._ollama.chat_stream(
                model,
                messages,
                temperature=params["temperature"],
                top_p=params["top_p"],
                # Harmless defense-in-depth for models/Ollama versions
                # where this genuinely works — but not relied upon: see
                # _extract_advisory() and the module docstring for why.
                think=True,
            )
        ]
        return dataclasses.replace(decision, advisory=_extract_advisory("".join(chunks)))
