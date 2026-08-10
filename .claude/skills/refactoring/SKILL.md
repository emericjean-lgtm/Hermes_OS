---
name: refactoring
description: Restructure existing code (extract, rename, simplify, remove duplication, change internal structure) without changing external behavior. Use when code works but is hard to change safely, when preparing an area for a feature that needs cleaner seams first, or when explicitly asked to refactor/clean up/simplify something.
---

# Refactoring

Refactoring changes structure, not behavior. If a "refactor" changes what the code outputs for any real input, it's not a refactor — it's a rewrite wearing a refactor's name, and it needs the review/testing scrutiny of a behavior change, not the lighter scrutiny a pure restructuring earns.

## Before starting

1. **Have a safety net.** Passing tests that cover the current behavior are what make a refactor verifiable — without them, you're trusting your own read of the diff, which is exactly the failure mode refactoring risk comes from. If coverage is thin, consider writing characterization tests first (tests that pin down current behavior, even behavior you're not sure is "correct") rather than refactoring blind. See [tdd-workflow](../tdd-workflow/SKILL.md).
2. **Scope it.** Decide what's in and out before starting. "While I'm in here" scope creep is the most common way a clean refactor turns into a large, hard-to-review, easy-to-break diff.
3. **Know why.** A refactor without a concrete reason (this function is about to grow a new branch, this duplication caused a real bug when only one copy got fixed, this name actively misleads) is speculative work — see the "don't add abstractions beyond what the task requires" principle. Refactoring for its own sake, on code nobody is about to touch, is a cost with no payoff.

## Common moves, and when each earns its keep

- **Extract function/method** — when a block does one identifiable thing and either repeats elsewhere or is long enough to obscure the function it's in. Don't extract a three-line block just to hit a line-count preference; the extraction should make the caller more readable, not just shorter.
- **Rename** — when a name actively misleads about what a thing holds or does. Free and safe with a real find-all, but check for string-based references (dynamic imports, config keys, serialized field names) that a mechanical rename won't catch.
- **Remove duplication** — only when the duplicated logic is actually the same *concept*, not just currently-identical code that happens to coincide. Two functions that look alike today but represent different business rules will diverge later, and a shared abstraction between them becomes the wrong kind of coupling. Three genuinely-the-same instances is a much safer signal than two.
- **Simplify conditionals** — flatten nested ifs, replace a boolean flag parameter with two clear call sites, replace a magic value with a named constant. Do this when it measurably reduces the reader's work, not as a reflex.
- **Change internal data structure** — riskier; verify every call site that touches the structure, not just the ones in the file you're editing. Grep before assuming you found them all.

## While refactoring

- Make one kind of change at a time — don't rename AND restructure control flow in the same diff if you can help it; it makes the diff much harder to review and much harder to bisect if something breaks.
- Re-run tests after each meaningful step, not just once at the end. If something breaks, you want to know which specific move caused it.
- If you discover the refactor is bigger than expected (the "simple rename" touches a dynamic string key in twelve places), stop and reassess scope rather than plowing through — a large surprise refactor deserves the same proposal-before-implementation treatment as a new feature.

## After

- Confirm the test suite for the touched area passes, and confirm you didn't just get lucky with "no failures because nothing exercises the changed path" — check that the tests genuinely cover what moved.
- Diff-review the change yourself with fresh eyes before considering it done: does every line actually preserve behavior, or did something quietly change along the way (an off-by-one introduced while restructuring a loop, a default value that shifted)?
- If the refactor was in service of an upcoming feature, don't bundle the feature into the same change — land the refactor on its own so it's reviewable as "structure only."

## Anti-patterns

- **Refactoring and adding a feature in the same diff.** Makes both harder to review, and if something breaks you can't easily tell which part caused it.
- **"Improving" code you were only supposed to touch in passing** for an unrelated task. Flag it (or use spawn_task-style follow-up) instead of scope-creeping the current change.
- **Introducing an abstraction for a single current use case** "because we'll probably need it later." Three real instances justify an abstraction; a hypothetical future one doesn't.
- **Trusting that a refactor is safe because it "obviously" preserves behavior**, without actually running anything.
