"""Baseline catalogue of Hermes OS event topics (HOS-066B).

Deliberately a leaf module: it imports nothing from the project, so
``backend.core.event_hub`` can consume it without creating a cycle
(``core`` → ``security`` → ``core`` would be one).

Why this exists. ``EventHub`` validates the topic of every publish against an
allow-list, which is a good design — it catches a producer inventing a name and
a client filtering on a typo, both of which otherwise present as a socket that
is silently forever empty. What went wrong is narrower: the allow-list held six
entries while the RAL, security and runtime layers had grown to emit 44
distinct topics, so 26 of 28 RAL topics were dropped on the floor with only a
log line. The mechanism was right; the list was stale.

Two safeguards against that happening again:

* the baseline below is grouped by owning layer, so an addition has an obvious
  home;
* :func:`backend.core.bootstrap.event_wiring.collect_known_topics` re-derives
  the set from the live enums at startup and feeds anything missing to
  :func:`backend.core.event_hub.register_event_types`, so the authoritative
  source stays the enum, not this file.
"""

from __future__ import annotations

# The five topics named in the cahier des charges §24.2, plus the one the hub
# reports about itself when a slow subscriber loses frames.
LEGACY_TOPICS: frozenset[str] = frozenset({
    "system.metrics",
    "chat.token",
    "agent.message",
    "task.update",
    "validation.request",
    "stream.dropped",
})

# backend.ral.event_bus.Topic
RAL_TOPICS: frozenset[str] = frozenset({
    "runtime.started",
    "runtime.stopped",
    "runtime.health",
    "capability.registered",
    "capability.unregistered",
    "task.created",
    "task.started",
    "task.completed",
    "task.failed",
    "task.cancelled",
    "memory.updated",
    "memory.deleted",
    "knowledge.indexed",
    "skill.generated",
    "skill.compilation.completed",
    "workflow.started",
    "workflow.completed",
    "workflow.failed",
    "evolution.triggered",
    "evolution.completed",
    "delegation.requested",
    "delegation.completed",
    "security.validation.requested",
    "security.validation.granted",
    "security.validation.denied",
    "sdsl.message",
})

# backend.runtime.events.event_types.RuntimeEventType
RUNTIME_TOPICS: frozenset[str] = frozenset({
    "runtime.failed",
    "runtime.recovered",
    "runtime.health_changed",
    "runtime.overloaded",
    "runtime.unavailable",
    "model.loaded",
    "model.unloaded",
    "model.switch_started",
    "model.switch_completed",
    "routing.decision",
    "routing.fallback",
    "routing.failed",
    "memory.warning",
    "vram.limit_reached",
})

# backend.security.security_models.SECURITY_EVENTS
SECURITY_TOPICS: frozenset[str] = frozenset({
    "security.permission.checked",
    "security.permission.denied",
    "security.threat.detected",
    "security.agent.trust.updated",
    "security.isolation.created",
    "security.isolation.violation",
    "security.policy.updated",
})

# Emitted through the ``on_event`` seam by the governance, mission, agent,
# memory and integration layers. These are string literals in their emitters
# rather than enum members, so they cannot be derived from an enum at runtime.
#
# Collected by walking the AST of backend/ for every string constant passed as
# the first argument to an on_event/_publish/_emit call, then grouped by prefix.
# Grounded in the emitters rather than guessed: an earlier hand-written version
# of this block named topics that no emitter used ("mission.completed") while
# missing ones that 67 emitters did use ("mission.node_completed").
SUBSYSTEM_TOPICS: frozenset[str] = frozenset({
    # agent
    "agent.created",
    # alexandrie
    "alexandrie.circuit.opened",
    "alexandrie.document.created",
    "alexandrie.document.deleted",
    "alexandrie.document.updated",
    "alexandrie.sync.completed",
    "alexandrie.sync.failed",
    "alexandrie.sync.started",
    # approval
    "approval.expired",
    "approval.granted",
    "approval.rejected",
    "approval.requested",
    # audit
    "audit.created",
    # autonomous
    "autonomous.decision.made",
    # collaboration
    "collaboration.started",
    # conflict
    "conflict.detected",
    "conflict.resolved",
    # consensus
    "consensus.reached",
    "consensus.started",
    # context
    "context.shared",
    # discovery
    "discovery.benchmark_completed",
    "discovery.error",
    "discovery.new_models_found",
    # execution
    "execution.completed",
    "execution.failed",
    "execution.optimized",
    "execution.planning",
    "execution.started",
    "execution.task_completed",
    "execution.task_started",
    "execution.waiting_approval",
    # experience
    "experience.learned",
    # git
    "git.branch_created",
    "git.commit_created",
    # graph
    "graph.updated",
    # intelligence
    "intelligence.recommendation_created",
    "intelligence.score_updated",
    # klaatcode
    "klaatcode.cost.estimated",
    "klaatcode.diagnostics.analyzed",
    "klaatcode.graph.indexed",
    "klaatcode.patch.validated",
    "klaatcode.runtime.recommended",
    # memory
    "memory.created",
    "memory.indexed",
    # message
    "message.received",
    "message.sent",
    # model (ModelAutonomousAdapter, HOS-065B — added when it was wired
    # into AutonomousOrchestrator; see CHANGELOG)
    "model.decision.created",
    "model.performance.updated",
    "model.recommended",
    "model.routing.optimized",
    "model.profiled",
    "model.selection.completed",
    # mission
    "mission.cancelled",
    "mission.created",
    "mission.node_completed",
    "mission.node_failed",
    # HOS-112 : une étape dont un nœud n'a jamais rendu la main. Distinct de
    # `node_failed`, qui dit qu'un nœud a échoué — ici on ne sait même pas
    # ce qu'il est devenu, et c'est cette différence qui oriente le
    # diagnostic.
    "mission.step_timeout",
    "mission.node_ready",
    "mission.started",
    # HOS-092: emitted when a mission reports success over a workspace that
    # did not change. Separate from mission.completed on purpose — the green
    # event stays green, and this one makes the contradiction impossible to
    # read past.
    "mission.unverified",
    # HOS-099: carries the brief that would make a second attempt differ from
    # the first — the filesystem evidence, not just "try again".
    "mission.retry_suggested",
    # ohmypi
    "ohmypi.ast.analyzed",
    "ohmypi.lsp.diagnostics",
    "ohmypi.lsp.symbols_indexed",
    "ohmypi.memory.recorded",
    "ohmypi.runtime.registered",
    "ohmypi.workspace.committed",
    "ohmypi.workspace.prepared",
    "ohmypi.workspace.rolled_back",
    # planning
    "planning.completed",
    "planning.complexity_estimated",
    "planning.decomposing_completed",
    "planning.dependencies_built",
    "planning.failed",
    "planning.runtimes_recommended",
    "planning.validation_failed",
    # policy
    # Selected by a conditional assigned to a variable in
    # PolicyEngine.evaluate, so the AST harvest that produced the rest of this
    # block could not see them. Found by the RC2 audit driving the engine and
    # watching which topics the hub reported as unknown.
    "policy.allowed",
    "policy.denied",
    # recovery
    "recovery.action_started",
    "recovery.started",
    # resource
    "resource.allocation_failed",
    "resource.released",
    # retrieval
    "retrieval.completed",
    # review
    "review.completed",
    "review.requested",
    # routing
    "routing.analysis_started",
    "routing.decision_created",
    "routing.decision_failed",
    "routing.runtime_selected",
    # sandbox
    "sandbox.created",
    "sandbox.destroyed",
    # simulation
    "simulation.started",
    # task
    "task.assigned",
    "task.delegated",
    "task.dispatch_failed",
    "task.reassigned",
    # workspace (backend/workspace/* — mission-execution slots/locks, an
    # entirely different concept from the project.*/filesystem.* topics
    # below — see backend/projects/project_manager.py's module docstring)
    "workspace.archived",
    "workspace.created",
    "workspace.locked",
    "workspace.policy_denied",
    "workspace.released",

    # project — Project registration/validation (the Workspace/Filesystem
    # tool layer's "authorized workspace" concept; backend/projects/).
    # Deliberately project.* rather than reusing workspace.* above: same
    # word from a user's point of view ("register a workspace"), but two
    # different backend systems that must stay distinguishable in the
    # event stream (see project_manager.py's module docstring).
    "project.registered",
    "project.validated",
    "project.selected",

    # filesystem — every real, agent/chat-reachable file operation
    # (backend/tools/file_tools.py). One topic per operation kind plus
    # three outcome topics that apply across all of them.
    "filesystem.read",
    "filesystem.write",
    "filesystem.create",
    "filesystem.move",
    "filesystem.copy",
    "filesystem.delete",
    "filesystem.permission_denied",
    "filesystem.verification_failed",
    "filesystem.operation_failed",
})

#: Everything the system may legitimately publish.
BASELINE_TOPICS: frozenset[str] = (
    LEGACY_TOPICS
    | RAL_TOPICS
    | RUNTIME_TOPICS
    | SECURITY_TOPICS
    | SUBSYSTEM_TOPICS
)

__all__ = [
    "BASELINE_TOPICS",
    "LEGACY_TOPICS",
    "RAL_TOPICS",
    "RUNTIME_TOPICS",
    "SECURITY_TOPICS",
    "SUBSYSTEM_TOPICS",
]
