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
project at all is different — the engine is still consulted first, and
only a path it would otherwise have allowed is escalated to
REQUIRE_HUMAN_VALIDATION rather than silently skipping the restriction
(don't fail open on the unexpected, same as an unknown action_type). A
DENY from the boundary stays a DENY: before HOS-292 this branch returned
without calling the engine at all, so one human approval on a
non-existent project opened any path on disk.

Workspace/Filesystem tool layer: evaluate() also calls
_workspace_grant() on every invocation and passes the result as
AegisEngine.evaluate()'s extra_allowed_paths — the root_path of the
one Project **the action itself names**, and only while that Project is
ACTIVE and validation_status="valid", resolved fresh from ProjectStore
each time (nothing cached). This is what lets a user-registered,
validated workspace (e.g. via POST /projects then POST
/projects/{id}/validate) actually grant filesystem access without
editing config/security.yaml's static ALLOWED_PATHS — the two lists
are unioned at the point of check (aegis_engine.py's
_is_within_whitelist), and a Project that stops being active+valid
stops granting on the very next call.

That grant is **nominative** (A-4, HOS-292), and that is the whole
point: it was previously the union of *every* active validated
Project, handed to every action regardless of which project the action
named — or whether it named one at all. Two validated projects A and
B, reading ws-b/secret.txt, measured 2026-09-11: project_id=A denied
(narrowing worked), project_id=None allowed, with B's contents
returned. An MCP files_read(path) with no project_id therefore read
the workspace of a project it never named. Validation proves a folder
exists; it never said who may touch it.

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

    def decide_approval(self, approval_id: str, *, approved: bool,
                        portee: str = approvals.PORTEE_ACTION,
                        portee_racine: str | None = None,
                        usages: int | None = None) -> dict | None:
        """Record a human yes/no.

        Par défaut, exactement ce que c'était : un accord pour une seule
        reprise de la même action, qui expire ensuite et ne devient
        jamais une permission permanente.

        Une **portée** (HOS-224) doit être demandée explicitement, avec
        sa racine ; elle reste bornée par un budget d'usages et une
        expiration plus courte. Elle existe parce que trente écritures
        dans un dossier demandaient trente approbations — et qu'une
        fonctionnalité qui exige trente clics est une fonctionnalité
        désactivée.
        """
        with self._session_factory() as session:
            entry = approvals.decide(session, approval_id, approved=approved,
                                     portee=portee, portee_racine=portee_racine,
                                     usages=usages)
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
            discriminants = dict(action.discriminants)
            consumed = approvals.consume_approval(
                session,
                action_type=action.action_type,
                target_path=action.target_path,
                description=action.description,
                discriminants=discriminants,
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
                discriminants=discriminants,
            )

        return decision

    def _workspace_grant(self, project_id: str | None) -> list[str]:
        """Ce que le projet **nomme par l'action** autorise, et rien d'autre.

        L'habilitation est nominative (A-4, HOS-292). Cette methode rendait
        auparavant `active_validated_project_roots()` — l'union de *tous*
        les projets actifs et valides — quel que soit le projet que
        l'action nommait, y compris quand elle n'en nommait aucun. Deux
        projets valides A et B, lecture de `ws-b/secret.txt`, mesure du
        2026-09-11 :

            project_id=A    -> deny   (le retrecissement fonctionnait)
            project_id=None -> allow  (le contenu de B etait rendu)

        Un `files_read(chemin)` MCP sans `project_id` lisait donc le
        workspace d'un projet qu'il ne nommait pas. La liste blanche
        statique, elle, ne bouge pas : elle est configuree par un humain
        dans `config`, pas accordee par une validation.

        Resolu a chaque appel via `projects.store.authorized_root`, le
        predicat unique du depot ; rien n'est cache ici.
        """
        from backend.projects.store import authorized_root
        racine = authorized_root(project_id)
        return [racine] if racine else []

    def _resolve_decision(self, action: ActionRequest) -> AegisDecision:
        # Elargissement (extra_paths) et retrecissement (project_root) sont
        # gates independamment, mais tous deux partent desormais du *seul*
        # projet que l'action nomme.
        #
        # Elargir : la racine n'est accordee que si ce projet-la est ACTIVE
        # et validation_status="valid" (`_workspace_grant`). Une action qui
        # ne nomme aucun projet ne porte aucune habilitation de workspace —
        # il lui reste la liste blanche statique, qu'un humain a ecrite.
        #
        # Retrecir : la regle d'origine, inchangee. Si l'appelant nomme un
        # project_id, sa racine borne l'action a ce dossier quel que soit
        # son statut de validation — la racine d'un projet non valide reste
        # une frontiere reelle et connue pour reduire une portee, meme
        # avant que quiconque ait confirme qu'elle accorde quoi que ce soit.
        #
        # `not` et non `is None` : l'absence de projet s'ecrit de deux
        # facons selon la surface. MCP rend `""` pour un argument omis —
        # mesure du 2026-09-11 sur une vraie session streamable-HTTP —
        # la ou HTTP rend `None`. Les traiter differemment faisait tomber
        # tout appel MCP non nomme sur la branche « projet inconnu »
        # ci-dessous, donc sur une *demande de validation humaine* au lieu
        # d'un refus. Ne nommer aucun projet n'est pas nommer un projet
        # inconnu : c'est n'avoir aucune habilitation de workspace.
        if not action.project_id:
            return self._engine.evaluate(action, extra_allowed_paths=[])

        project = get_project_store().get(action.project_id)
        if project is None:
            # Un identifiant qui ne resout pas reste suspect (§17.3) — mais
            # on interroge le moteur **d'abord**.
            #
            # Cette branche rendait REQUIRE_HUMAN_VALIDATION sans jamais
            # appeler `evaluate`, donc sans que la liste blanche soit
            # regardee. Or `_apply_human_consent` transforme un
            # REQUIRE_HUMAN_VALIDATION approuve en ALLOW. Mesure du
            # 2026-09-11, `ALLOWED_PATHS` reduit a un dossier :
            #
            #     project_id='inexistant-xyz' sur un chemin hors de toute
            #     liste blanche -> require_human_validation
            #     puis un seul accord humain            -> allow
            #
            # Un projet qui n'existe pas ouvrait donc n'importe quel
            # chemin du disque au premier « oui ». Le commentaire de
            # `_apply_human_consent` promettait exactement le contraire :
            # « A DENY is never upgraded: those come from the hard
            # boundaries ». La promesse tenait, la frontiere n'etait
            # simplement jamais consultee.
            base = self._engine.evaluate(action, extra_allowed_paths=[])
            if base.verdict is Verdict.DENY:
                return base
            return AegisDecision(
                verdict=Verdict.REQUIRE_HUMAN_VALIDATION,
                reason=(
                    f"project_id {action.project_id!r} does not resolve to a known "
                    "project — treated as suspicious rather than silently skipping "
                    "project-level restriction (§17.3)."
                ),
                action_type=action.action_type,
            )
        extra_paths = self._workspace_grant(action.project_id)
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
