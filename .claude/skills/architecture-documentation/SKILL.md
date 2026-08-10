---
name: architecture-documentation
description: Update Hermes OS's architecture documentation (docs/architecture/*.md, ARCHITECTURE.md) after a structurally significant change — a new subsystem, a changed component boundary, a new/changed data flow or event contract, or a component that moved from designed-but-unwired to actually wired into the running app. Use after architecture-review confirms a change touches a central system, not for routine feature work.
---

# Architecture Documentation

Hermes OS has 27+ real architecture documents under `docs/architecture/`, and its own recent history is the clearest possible argument for keeping them honest: several were written describing a fully-designed subsystem, and a later independent audit found the subsystem was real code that nothing in the running application ever actually called. The doc wasn't lying exactly — it was describing the *design*, correctly — but nothing marked the gap between "designed" and "load-bearing in production," and that gap cost real audit cycles to find.

## The one rule that matters most here

**State explicitly whether what you're documenting is live in the running app or not.** Three honest categories, and every architecture doc (or update to one) should make clear which applies to the piece being described:
- **Wired and live** — the composition root actually constructs this, real requests reach it, you've confirmed this by tracing the call path or by a real test/run, not by reading the class definition and assuming.
- **Built but not wired** — the code exists, may even be well-tested in isolation, but nothing in the real running app's dependency graph constructs or calls it yet.
- **Designed, not built** — this section describes an intended future shape, explicitly marked as such (a "Future Migration Path" or similar heading, not blended into the current-state description).

Blending these three into one undifferentiated description is exactly the pattern that produced Hermes OS's own real audit findings — don't repeat it.

## When to update

- **New subsystem or component** — add or extend the relevant `docs/architecture/*.md`, following the existing doc's structure (most follow: purpose, key classes/interfaces, data flow, REST surface if any, limitations/future work).
- **Changed component boundary or contract** — a shared interface's shape changed, an event's payload changed, a data flow was rerouted. Update the doc *and* grep for other docs that reference the old contract, since Hermes OS's architecture docs cross-reference each other (e.g. adapter docs describing how one subsystem bridges to another).
- **Something moved from unwired to wired** (or vice versa) — this is a status change worth documenting explicitly, ideally with a note of when/how it was verified, following the pattern already used in this project's own CHANGELOG (which records exactly this kind of "found X was never actually called, wired it in" finding, with the real evidence that proved it).
- **A documented limitation was resolved**, or a new one was discovered — keep the "known gaps" honest in both directions.

## What to verify before writing

Don't describe a component's behavior from its class/function names — read enough of the real implementation to be confident, and if you're claiming something is "wired" or "live," trace the actual call path from the composition root (or equivalent real entry point) rather than assuming a well-built class is automatically in use. This project's own audit history shows that assumption fails often enough to be worth the extra five minutes of tracing every time.

## Format

Match the existing per-subsystem doc structure rather than inventing a new one — consistency across 27+ documents matters more than any individual doc's format being locally optimal. If updating `ARCHITECTURE.md` (the top-level summary) alongside a `docs/architecture/*.md` detail doc, make sure the two don't contradict each other about live/unwired status — the top-level doc should never claim something is complete when its own detail doc says otherwise.

## Don't

- Don't write a new architecture doc for something that's still a rough idea — that belongs in [implementation-planning](../implementation-planning/SKILL.md), not the permanent architecture record.
- Don't silently upgrade a doc's own "not yet built" note to sound complete just because related work happened nearby — verify the *specific* thing the note was about actually got built before removing the caveat.
