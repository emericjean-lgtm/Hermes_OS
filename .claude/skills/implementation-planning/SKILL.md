---
name: implementation-planning
description: Turn a reviewed, understood requirement into a concrete, phased implementation plan before writing code. Use after technical-spec-review (or for any non-trivial task even without a formal spec) when the work spans multiple files, components, or phases, and especially before touching a shared architectural contract.
---

# Implementation Planning

A plan's job is to catch sequencing mistakes and hidden dependencies before they cost a rewrite — not to produce a document for its own sake. For a small, obviously-scoped change, a one-line mental plan is enough; don't over-formalize trivial work. This skill is for the cases where the ordering of steps, or the existence of a hidden dependency between them, actually matters.

## Before planning

Make sure the requirement is actually understood — if it hasn't been through [technical-spec-review](../technical-spec-review/SKILL.md) and it's non-trivial, do that first, or fold its checks in here. A confidently-sequenced plan for a misunderstood requirement is still wrong, just more elaborately so.

## Building the plan

1. **Identify the real touch points.** Which files, modules, or components does this actually require changing? Search the codebase rather than guessing from the requirement's description — the place the change "should" live and the place existing similar code actually lives are not always the same, and consistency with the existing pattern usually wins.

2. **Map dependencies between steps.** What has to exist before something else can be built or tested? A backend endpoint the frontend will call, a schema migration a query depends on, a config flag a feature checks. Sequence around real dependencies, not around what feels natural to build first.

3. **Identify what's genuinely parallelizable.** Steps with no dependency between them (independent backend logic + frontend scaffolding, or a feature's tests + its docs) can happen concurrently — including via [multi-agent](../multi-agent/SKILL.md) if the task and environment support it. Don't parallelize things that share a file or a data contract that's still in flux; that's a recipe for merge conflicts and rework.

4. **Call out the risky step.** Every plan has one step most likely to reveal a wrong assumption — a shared contract change, a migration, an integration with something you haven't verified behaves as documented. Name it, and consider doing it (or a spike to de-risk it) earlier rather than discovering the problem after everything else is built on top of the wrong assumption.

5. **Decide the testing shape up front**, not as an afterthought: which parts get unit tests, which need integration coverage, whether a regression test is needed for a related bug, whether anything needs manual/browser verification. See [tdd-workflow](../tdd-workflow/SKILL.md).

6. **Note what's explicitly out of scope.** A plan that doesn't say what it's *not* doing tends to quietly grow scope during implementation. If the requirement implies something adjacent that you're deliberately deferring, say so.

## Phasing large work

For work too large for one sitting or one review: break it into phases where each phase is independently shippable and testable — not just independently *codeable*. A phase boundary should be a point where you could stop, verify, and hand off, not an arbitrary line through a half-working feature. Get explicit approval on the phase breakdown before implementing phase one, especially if the phases involve trade-offs (what's deferred to phase 2, what a phase 1 shortcut costs later).

## Format

A plan doesn't need a fixed template, but should make these legible to someone else reading it before implementation starts:
- The ordered steps, with dependencies between them shown (not just a flat list).
- What's parallelizable vs. sequential.
- The riskiest assumption, and how/when it gets tested.
- Testing approach per phase/step.
- Explicit non-goals for this pass.

## After planning

Get alignment before implementing anything non-trivial — this project's standing practice is propose-then-implement, not implement-then-explain. A plan that turns out wrong after a five-minute review is far cheaper than one discovered wrong after the code is written.
