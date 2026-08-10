---
name: code-review
description: Systematic code review of a diff, PR, or set of recent changes — checking correctness, architecture fit, security, performance, concurrency, types, error handling, test coverage, and regressions. Use before considering a change complete, before opening a PR, or when explicitly asked to review code (yours or someone else's).
---

# Code Review

A review's job is to find what's actually wrong or risky, not to perform thoroughness. A list of 20 nitpicks with no real finding is worse than a short list of things that would genuinely break in production — it trains the author (and you, next time) to skim past the noise. Be specific: point at the line, state the concrete failure mode, don't just gesture at a category.

## What to check, in rough order of how much it matters

**Correctness & logic** — does the code do what it's supposed to, including the cases nobody wrote a happy-path test for? Read conditionals for off-by-one and inverted-boolean mistakes; read loops for the actual termination condition, not the intended one. Trace at least one non-trivial input through the code by hand rather than trusting that it "looks right."

**Architecture fit** — does this change respect the boundaries and contracts of the system it's in, or does it reach across a layer it shouldn't, duplicate logic that already exists elsewhere, or quietly change a shared contract's behavior? For anything touching a component other code depends on, pair this review with [architecture-review](../architecture-review/SKILL.md) rather than assuming local correctness is enough.

**Security** — does user-controlled input reach a shell command, file path, SQL query, or template without validation? Are secrets/credentials handled correctly (never logged, never hardcoded)? Is a new permission check actually enforced, not just present in a comment? For anything security-sensitive, use [security-review](../security-review/SKILL.md) instead of a quick pass here.

**Error handling** — does a failure path produce an honest, actionable outcome, or does it silently swallow the problem (bare `except:`, a fallback that never tells anyone it fired, a default returned in place of a real error)? A silent fallback is often worse than a loud crash — see [hermes/verification](../hermes/verification/SKILL.md)'s stance on this.

**Concurrency** — for anything async or multi-threaded: is shared state actually protected, or does it just look protected? Can two callers race on the same resource? Does an `await` sit where the code assumes synchronous execution?

**Types** — do type hints/annotations reflect what the code actually does, not what it did before the last edit? Is `Any`/`any` covering up a real type that should be spelled out? Does a nullable value get used somewhere without a null check?

**Performance** — only flag this where there's a real, plausible cost (an N+1 query, an unbounded loop over user input, a blocking call on a hot path) — not as a reflex on every line. If you're not sure it matters, say so and suggest measuring rather than asserting a change is needed; see [performance-analysis](../performance-analysis/SKILL.md) for anything that needs real measurement before a verdict.

**Test coverage** — does the change include a test that would fail without it? Are the edge cases the change itself introduces (a new branch, a new failure mode) actually covered, not just the happy path?

**Regressions** — does this change what a caller already relied on? Grep for other call sites before assuming a signature or behavior change is safe; a function used in three places needs three places checked, not one.

**Maintainability** — is the code readable by someone who didn't write it, without needing the author standing next to them? Are names honest about what they hold? Is there a comment explaining a genuinely non-obvious constraint, or is there comment noise restating what the code already says?

## How to structure findings

Group by severity so the author can triage:
- **Blocking** — this will break, is a real security hole, or silently does the wrong thing. Must be addressed before merge.
- **Important** — a real risk or a meaningful maintainability cost, but not an emergency.
- **Nit** — style/naming/minor clarity. Say so explicitly as optional so it doesn't read as blocking.
- **Question** — you're not sure this is wrong, but you don't understand why it's right either. Ask rather than assert.

For each finding: cite the file and line, state the concrete failure scenario (not just "this could be a problem"), and if you know the fix, say what it is — but don't rewrite the whole file unasked.

## What not to do

- Don't flag something as wrong without reading enough surrounding context to be sure — a pattern that looks wrong in isolation is often intentional given a constraint two functions away.
- Don't pad a review with restated-praise or restated-summary; say what's actually notable and stop.
- Don't block on pure style preference that the codebase's existing convention already contradicts — match what's there, don't relitigate it mid-review.
- Don't approve something you didn't actually read carefully because it's long — say so, and review it in passes if needed, rather than rubber-stamping.
