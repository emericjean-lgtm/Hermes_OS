---
name: architecture-review
description: Verify that a code change respects Hermes OS's overall architecture and doesn't silently break a shared contract other components depend on. Use before merging any change that touches a central system (mission planning/execution, agent supervision, model routing, runtime orchestration, memory, the event bus, governance/security, MCP/tools, skills, or model benchmarking) — never review such a change in isolation from its callers.
---

# Architecture Review

A change can be locally correct and still break the system if it silently changes a contract something else depends on. This skill's whole point is refusing to review a central-component change in isolation — the question is never just "is this code right on its own," it's "what else assumes this worked the old way."

## Central components — never touch these without checking impact

Hermes OS's real architecture (see [hermes/architecture](../hermes/architecture/SKILL.md) for the actual current map, package-by-package) is anchored by a set of components other systems depend on:

- **Mission Execution Engine / Mission Planner** — the DAG-based goal-to-tasks pipeline shared by Missions and Autonomous.
- **Agent Supervisor** — agent lifecycle, coordination between agents.
- **Runtime Orchestrator / Runtime Resource Manager** — process/model lifecycle, resource budgeting across concurrent work.
- **Model Router** — which model handles which task type, and the adaptive/learned routing layer on top of it.
- **Memory / Knowledge Graph** — persistent state other components read and write.
- **Event Bus** — the pub/sub backbone other components use to react to state changes without direct coupling.
- **Governance** — policy/permission evaluation that gates mutating actions.
- **MCP / Tools** — the tool-calling surface agents and external clients use.
- **Skills** (Hermes's own internal skill system — distinct from this `.claude/skills/` Claude-Code-facing system) — dynamically loaded agent capabilities.
- **Model Benchmark / Discovery** — how real performance data feeds back into routing decisions.
- **Autonomous Mission Execution** — the orchestrator that runs goals without a human driving each step.

If a change touches any of these — a function signature, a data shape, a routing decision, an event payload, a permission category — treat it as a shared-contract change, not a local edit.

## The review

1. **Read the component's real current contract before touching it.** What does it export, what shape does it expect/return, who's documented (in `docs/architecture/*.md`) or coded to call it? Don't assume from the name — verify with [hermes/architecture](../hermes/architecture/SKILL.md) or by reading the source directly.

2. **Find every real caller.** Grep for the function/class/event-type/config-key being changed across the whole repo, not just the file you're editing — both `backend/` and `frontend/` (a backend contract change often has a frontend consumer via `services/client.ts`'s DTOs). A caller three packages away that you didn't think to check is exactly how a "local" fix becomes a production break.

3. **Check both directions of dependency.** What does this component depend on (could your change break an assumption it's making about something upstream)? What depends on it (could your change break an assumption something downstream is making)? A change that looks additive (a new optional field, a new event type) can still break a caller that iterates over "all fields" or matches on "all known event types" exhaustively.

4. **Check the event/data contract, not just the function signature.** If the change alters what an event carries, what a DAG node's output shape is, or what a config file's schema looks like, every consumer of that shape needs checking — this class of break is easy to miss because nothing fails to *compile*, it just silently misbehaves at runtime.

5. **Verify test coverage actually exercises the shared path**, not just the new code in isolation. A shared-contract change deserves an integration-level test proving the two sides still agree, not just a unit test of the changed function alone.

6. **Consider the migration path**, if the contract change affects data already persisted (DB rows, cached files, in-flight missions) — does old data/state still work, or does it need a migration/backfill, and has that been made explicit rather than silently assumed away?

## Red flags that mean "stop and widen the review"

- A change to a shared dataclass/model/schema with no corresponding search for its other usages.
- A "small" tweak to routing logic, permission evaluation, or event payload shape justified as "shouldn't affect anything else."
- A new field added to a central config file without checking whether existing consumers iterate over that structure exhaustively.
- Any change where you can't currently name every caller — that's a sign you haven't actually looked yet.

## Output

State plainly: what shared contract (if any) this change touches, who else was found to depend on it, whether those dependents were checked/updated/still compatible, and whether anything needs a follow-up migration or a broader test pass before this is safe to merge. If nothing central is touched, say so explicitly and move on — this skill isn't meant to slow down changes that are genuinely local.
