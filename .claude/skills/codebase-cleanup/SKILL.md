---
name: codebase-cleanup
description: Periodic audit for technical debt — duplication, dead code, unnecessary complexity, unused dependencies, unhelpful abstractions, and inconsistencies. Use when explicitly asked to clean up an area, or periodically on a specific scope. Do not run this automatically after every change — cleanup is its own deliberate task, not a reflex.
---

# Codebase Cleanup

This is a periodic, deliberate audit — not something to trigger reflexively after finishing an unrelated change. Cleanup work deserves its own scoped task with its own review, not a scope-creeping addition to whatever else was just being worked on.

## What to look for

**Dead code** — functions, files, or exports nothing imports or calls. Verify with a real search (not just a guess from the name) before removing — a thing that looks unused can still be a public API surface, a plugin entry point, or referenced dynamically (string-based lookup, config-driven dispatch) in a way a naive grep misses. This project has real, confirmed examples of exactly this pattern: a duplicate provider setup superseded by a near-identical file elsewhere, an older streaming client left in place after a newer one replaced it at the actual call site, a WebSocket hook defined but never imported anywhere. Each is safe to remove once genuinely confirmed unused — but confirm first.

**Duplication** — two implementations of the same concept that should be one, or (the more common and more dangerous case) two things that *look* like duplication but actually encode different rules that happen to coincide today. Verify which case you're looking at before merging — this project has a real documented instance of the first kind (three separate, mutually inconsistent scoring formulas for the same "which model is best" question) that caused real bugs before being unified; collapsing the wrong kind of "duplication" instead creates a bug when the two cases diverge later.

**Unnecessary complexity** — a config option nobody sets, a flag with only one real value, an abstraction built for a generality the codebase never actually uses. Distinguish this from complexity that's load-bearing but non-obvious (a specific ordering, a workaround for a real upstream bug) — removing the latter without understanding why it's there is how regressions get reintroduced. If you're not sure why something exists, find out before removing it, don't assume it's cruft.

**Unused dependencies** — a package in `requirements.txt`/`package.json` nothing imports anymore. Verify with a real search across the codebase (including config files and scripts, not just application source) before removing.

**Inconsistencies** — the same kind of thing done two different ways in two places for no reason other than history (two competing state-management patterns, two logging conventions, two ways of constructing the same kind of object). Fixing these is genuinely valuable, but pick a direction based on which pattern the codebase has more clearly standardized on, not personal preference — check [hermes/development-rules](../hermes/development-rules/SKILL.md) or the more common existing pattern before picking a "winner."

## What NOT to do

- **Don't fix everything you find in one pass.** A cleanup task with an unbounded scope becomes an unreviewable diff. Scope it — one category, one directory, one specific debt item — and finish that before considering the next.
- **Don't refactor behavior while cleaning up structure.** Cleanup should be behavior-preserving; if you find an actual bug while cleaning up, flag it and fix it as its own separate, clearly-labeled change (or via a follow-up task), not silently folded into the cleanup diff.
- **Don't remove something "unused" without verifying it thoroughly** — see [refactoring](../refactoring/SKILL.md)'s note on dynamic references. A regression from an overzealous cleanup pass is a worse outcome than leaving the debt for another day.
- **Don't treat every stylistic difference as debt worth fixing.** Not everything inconsistent is a problem; only flag what genuinely costs future maintainers real time or creates real risk of a bug from divergent behavior.

## Output

A cleanup pass should produce: what was found (with enough evidence that a reviewer can verify the claim — a real search result, not "I think this is unused"), what was actually changed in this pass (scoped, not everything found), and what was found but deliberately deferred with a reason (too large for this pass, needs a decision from someone, uncertain enough to need more investigation first).
