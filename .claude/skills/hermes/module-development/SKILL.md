---
name: module-development
description: Checklist and process for creating or modifying an HOS module (a backend subsystem/agent/feature) in Hermes OS. Use when building a new module end to end, or making a structural change to an existing one — not for a small, local bug fix.
---

# Hermes OS — Module Development

Hermes OS's own history is a direct lesson in what happens when a module is built without this checklist: this codebase currently contains multiple subsystems that are real, complete, well-tested code that nothing in the running application actually calls (see [hermes/architecture](../architecture/SKILL.md)'s dead/unfed inventory) — built in isolation, verified against their own tests, but never actually wired into the composition root or given a real caller. The checklist below exists specifically to prevent repeating that pattern.

## 1. Analyze the existing module (if modifying) or the closest analog (if new)

Read the real current code, not a design doc's description of it — [hermes/architecture](../architecture/SKILL.md) is a good starting map, but verify anything load-bearing against the actual source, since this project's own docs have a real history of describing designed-but-unwired systems as if they were live. If building something new, find the closest existing pattern (an existing agent if building an agent, an existing DI service if building a World-B subsystem) and follow its shape rather than inventing a new one.

## 2. Identify dependencies

What does this module need from the rest of the system (config, another subsystem's output, an event it should react to)? What will need it (a route, another subsystem, the frontend)? Map this explicitly — see [architecture-review](../../architecture-review/SKILL.md) if this touches a central/shared system.

## 3. Define interfaces

What's the module's real public surface — the class/functions other code will call, the event types it will publish/consume, the REST routes if any? Decide this before implementing so the shape isn't discovered accidentally halfway through. If it's a new agent, define it in `config/agents.yaml` and follow `BaseAgent`'s contract if it has a chat-completion role. If it's a World-B subsystem, plan its `ServiceSpec` entry (factory, dependencies, route_binder) up front.

## 4. Define tests

Decide the testing shape before or alongside implementation, not after — see [tdd-workflow](../../tdd-workflow/SKILL.md). At minimum: unit tests for the module's own logic; if it has a real external dependency (Ollama, another subsystem), a hermetic test using this project's established pattern of a fake client / monkeypatched boundary rather than hitting the real thing in every test run (see the real `FakeOllamaClient` pattern already used across `backend/tests/conftest.py` and `tests/architecture/conftest.py`'s `_no_live_inference` fixture).

## 5. Implement

Follow [hermes/development-rules](../development-rules/SKILL.md) — config-vs-code discipline, matching the existing World-A or World-B pattern, real event publishing through the established bus. Keep the implementation scoped to what the plan actually called for.

## 6. Integrate — the step this project's history shows is easiest to skip

**A module isn't done when its own code and tests pass — it's done when something in the real running application actually constructs and calls it.** For a World-B subsystem, this means a real `ServiceSpec` entry in `backend/core/bootstrap/service_registry.py`, actually reached by `HermesBootstrap.build()`. For an agent, this means a real, enabled entry in `config/agents.yaml`, actually reachable via `AgentRegistry`. For a route, this means actually mounted in `main.py` (directly or via the bootstrap's router registry) — not just defined.

Verify this concretely: trace the real call path from an actual entry point (an HTTP request, a CLI invocation, an event) to your new code, rather than trusting that a well-built module with correct DI declarations must be reachable. This project has multiple real, confirmed examples of exactly this assumption failing.

## 7. Test the integrated result

Run the module's own tests, then run (or at minimum trace) the real path that would invoke it in production — an isolated passing test suite doesn't prove the module is reachable; see step 6. See [hermes/verification](../verification/SKILL.md).

## 8. Code review

See [code-review](../../code-review/SKILL.md).

## 9. Architecture review

Required if this module touches a central/shared system (mission planning, agent supervision, model routing, memory, the event bus, governance, MCP/tools) — see [architecture-review](../../architecture-review/SKILL.md). Not required for a genuinely local addition.

## 10. Update documentation

- [architecture-documentation](../../architecture-documentation/SKILL.md) if this is structurally significant — and if you do, state explicitly whether the new/changed piece is wired-and-live, built-but-not-wired, or designed-not-built. This is the single most valuable thing a Hermes OS architecture doc can get right, given the project's own history.
- [release-notes](../../release-notes/SKILL.md) for the CHANGELOG entry, written after the work is actually done and verified, not before.

## The recurring failure mode to actively guard against

Building a complete, well-tested, isolated module and considering it finished without confirming step 6 actually happened. This project's own architecture ([hermes/architecture](../architecture/references/backend-map.md)) currently documents this exact pattern in multiple places — real code, real tests, zero real callers. Don't add to that list.
