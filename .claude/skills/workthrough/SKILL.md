---
name: workthrough
description: Produce a structured end-of-task summary — what was done, files changed, decisions made, tests run, problems hit, risks, and what's left. Use at the end of any non-trivial task, especially one that spanned multiple files, took several steps, or involved a decision the next person (human or agent) would benefit from knowing the reasoning behind.
---

# Workthrough

The purpose isn't to restate the diff — it's to preserve the *reasoning* that isn't visible in the diff. Code shows what changed; a workthrough should carry why it changed that way, what alternatives were rejected, and what's genuinely still open. Anyone can read a diff; not everyone was in the room for the decisions.

## Structure

**What was done.** A few sentences, not a changelog restated line by line. Focus on the outcome and its intent, not a narration of every step taken to get there.

**Files changed.** A real list, not a vague summary — grouped sensibly if there are many (backend / frontend / tests / config / docs). For each meaningfully-changed file, a phrase on what changed there if it's not obvious from the filename alone.

**Decisions made.** The choices that weren't forced by the task — an approach picked over an alternative, a scope boundary drawn, a trade-off accepted. State the reasoning, not just the choice: "used X instead of Y because Z" is useful to a future reader; "used X" alone isn't. This is the part most likely to be lost if not written down now.

**Tests.** What was actually run, and what the real result was — not "tests should pass," but the actual command and actual outcome. If something wasn't tested (a manual-only verification, a path that couldn't be exercised in this environment), say so plainly rather than implying full coverage. See [hermes/verification](../hermes/verification/SKILL.md) — a workthrough is not a substitute for actually verifying, it's a record of what verification happened.

**Problems encountered.** Real obstacles hit along the way and how they were resolved — a wrong initial assumption, an unexpected dependency, a flaky test that turned out to be a pre-existing issue rather than something the current change caused. This is often the most valuable section for someone debugging a similar issue later.

**Risks.** What could still go wrong that isn't fully covered by the tests — a behavior change that only manifests under load, a migration that assumes a data shape that might not hold for all existing records, a dependency on an external service's current (undocumented) behavior. Naming a risk explicitly is more useful than silently hoping it doesn't materialize.

**What's left.** Anything explicitly deferred, out of scope, or blocked — and why. A task that's "done" except for three named follow-ups is more honest and more useful than one that implies total completion while quietly not mentioning them.

## What makes a workthrough bad

- **Restating the diff in prose.** If it just says what each file's change was without adding reasoning, it's not adding anything the diff didn't already show.
- **Implying more certainty than exists.** "This is fully tested and production-ready" when only the happy path was exercised is the kind of overstatement this project's own standing practice explicitly rejects — see [hermes/verification](../hermes/verification/SKILL.md).
- **Padding.** A workthrough for a five-line fix doesn't need every section filled with a full paragraph — match the length to what's actually worth recording. "No open risks, fully covered by the new regression test" is a complete and honest risks section when that's actually true.

## When to skip this

Trivial, single-file, obviously-scoped changes don't need a formal workthrough — a one-line summary in the response is enough. This skill earns its keep on work substantial enough that the reasoning behind it would otherwise be lost.
