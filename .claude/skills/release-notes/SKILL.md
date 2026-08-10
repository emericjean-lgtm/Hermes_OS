---
name: release-notes
description: Generate a CHANGELOG entry from real, completed changes — never from a plan or an intention. Use when a piece of work (an HOS-numbered ticket or otherwise) is actually done, tested, and ready to record, following this project's existing CHANGELOG.md conventions.
---

# Release Notes

Hermes OS's `CHANGELOG.md` is not a marketing artifact — it's the project's primary record of *why* things are the way they are, dense enough that code comments cite specific entries (`HOS-065C`, `HOS-077`) as the explanation for a constant or a check. A release note written from a plan rather than from what actually shipped breaks that record for everyone who trusts it later, including future sessions of this same skill set reading it as source material.

## Write it after, not before

Only write the entry once the work is actually done and verified — see [hermes/verification](../hermes/verification/SKILL.md). A CHANGELOG entry is a statement of fact about what happened, not a plan for what will happen. If something was scoped down, deferred, or partially completed, say that plainly in the entry rather than describing the original, larger intention as if it fully landed.

## Match the existing format

This project's CHANGELOG has an established structure per entry — a heading with the ticket ID, a short title, and a date; a short framing paragraph on what prompted the change and why; then sections (varying by entry, but commonly things like what was found/audited, what was fixed/added, and a "Verified" section with real test numbers). Read a few recent entries before writing a new one, and match their voice and structure rather than introducing a new format. Recent entries also model the honesty pattern this project cares about most: naming a real bug found *while testing* (not just while auditing), stating the exact before/after numbers, and being explicit about what's still unverified or out of scope.

## What to include

- **What prompted this work** — a user request, a bug report, an audit finding. Real trigger, not a generic "improved X."
- **What was actually found**, if this involved investigation — the real root cause, not a guess. If a fix turned out to be different from the original plan because investigation revealed something unexpected, say so; that's exactly the kind of detail that makes this record useful later.
- **What changed**, grouped sensibly (e.g. by area, or Added/Fixed/Changed) — specific enough that a reader knows which files/behaviors moved, not just a category label.
- **Real verification numbers** — actual test counts and pass/fail state from an actual run, not an estimate. If a known pre-existing issue was hit and not caused by this change, name it and say so explicitly rather than letting it look like this change's own regression.
- **What's explicitly out of scope or deferred**, if relevant — future readers (including future work sessions) benefit from knowing a gap was seen and deliberately not addressed yet, versus never noticed.

## What not to do

- Don't invent a plausible-sounding number (test count, latency, percentage) — every figure in this CHANGELOG's existing entries is either a real measurement or explicitly marked as an estimate/extrapolation. Matching that discipline is not optional.
- Don't describe a deferred or partially-done feature as complete. If three of four planned pieces landed, say three of four landed and name the fourth.
- Don't write the entry as advertising copy. The audience is a future developer (or agent) trying to understand why the code is the way it is — plain, specific, and honest beats polished and vague.
- Don't retroactively edit a past entry to match a later, different understanding — if something recorded earlier turns out to have been wrong, add a new entry noting the correction rather than silently rewriting history.

## After writing

Re-read the entry against the actual diff and the actual test output one more time — the same discipline [documentation](../documentation/SKILL.md) applies to any doc applies doubly here, since this file is the one other work most directly relies on as ground truth.
