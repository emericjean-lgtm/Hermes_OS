---
name: technical-spec-review
description: Analyze a specification, feature request, or cahier des charges before implementation begins — checking requirements clarity, internal consistency, feasibility, architecture fit, security implications, edge cases, dependencies, impacts on existing systems, and acceptance criteria. Use before starting any new feature, new HOS module, or significant change, especially when the spec was written by someone other than the implementer (a user, a stakeholder, a separate planning document).
---

# Technical Spec Review

The cost of a bad assumption caught here is minutes. The same assumption caught after implementation is a rewrite. This skill's job is to surface the gaps, contradictions, and hidden costs in a spec *before* committing to a plan — not to rubber-stamp it, and not to nitpick wording that's already clear enough to act on.

## What to check

**Requirements clarity** — is it actually specified what "done" looks like, or does the spec describe a vibe? For anything ambiguous, either resolve it by reading the rest of the spec/codebase for the answer, or surface the ambiguity explicitly rather than silently picking an interpretation and hoping it's right.

**Internal consistency** — does the spec contradict itself across sections (a data model described one way in §3 and used differently in §7)? Does it contradict something already true of the system it's extending? A spec that conflicts with existing behavior needs that conflict named, not quietly resolved by picking one side.

**Feasibility** — is this actually buildable with what's available? For Hermes OS specifically, this means checking against real hardware/model constraints (see [hermes/runtime](../hermes/runtime/SKILL.md)) before assuming a proposed approach fits — a spec written without awareness of local VRAM/model limits can describe something that's correct in the abstract and impossible on this deployment.

**Architecture fit** — does the spec's approach respect existing boundaries and contracts, or does it imply a shared component needs to change? If it touches a central system (mission planner, agent supervisor, router, memory, security engine, event bus), pair this with [architecture-review](../architecture-review/SKILL.md) before committing to the plan.

**Security implications** — does anything in the spec touch auth, permissions, file/network access, secrets, or user-controlled input reaching a sensitive sink? Flag it for [security-review](../security-review/SKILL.md) rather than assuming a later pass will catch it — specs that don't mention security are exactly the ones where it gets forgotten.

**Edge cases** — what does the spec say happens on empty input, on failure of an external dependency (a model, a network call, another agent), on partial completion, on concurrent access? If it doesn't say, that's a gap worth naming before implementation has to invent an answer under time pressure.

**Dependencies** — what does this spec assume already exists (an API, a data shape, a permission category, another team's work)? Verify those assumptions against the real current state rather than trusting the spec's description of them — specs age, code doesn't wait.

**Impact on existing systems** — who else calls the thing this spec is changing? A spec that reads as self-contained can still break every existing caller of a shared function or contract; this needs a real search, not an assumption of isolation.

**Acceptance criteria** — is there a concrete, testable definition of success? If the spec only describes the feature and not how anyone will know it's correctly built, propose acceptance criteria rather than proceeding without any and hoping expectations align later.

## Scope realism

Large specs (a full application cahier des charges, a multi-module feature) deserve an explicit scope-vs-capacity check before planning starts: given the actual available time/models/team, what's realistic to build, and what should be phased or deferred? Saying this plainly up front — with reasoning, not just a gut feeling — is more useful than silently scoping down mid-implementation and leaving the original ask looking abandoned.

## Output

A spec review isn't a rewrite of the spec. Produce: a short list of what's clear and solid (so it's obvious what's already settled), a list of gaps/ambiguities/contradictions each with a proposed resolution or an explicit question, feasibility flags tied to real constraints (not vague doubt), and — if the spec is judged buildable — a pointer into [implementation-planning](../implementation-planning/SKILL.md) for the next step. If it's not yet buildable as written, say so plainly and what needs to change first.
