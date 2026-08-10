---
name: tdd-workflow
description: Test-driven development workflow (RED, GREEN, REFACTOR) for implementing a new feature, function, or bug fix where behavior can be objectively verified. Use when writing new backend (pytest) or frontend (vitest) logic, or when a bug fix needs a regression test. Do not force this on subjective/exploratory work (UI polish, prompt wording, prose) where a test would just encode an opinion.
---

# TDD Workflow

RED -> GREEN -> REFACTOR, applied where it actually pays off. The point of writing the test first is that it forces you to state the expected behavior precisely *before* you have a working implementation to rationalize against — it's much easier to convince yourself a test is "basically right" once the code already passes it.

## When to use this, and when not to

Use it for: new backend logic with a clear input/output contract, bug fixes (the regression test IS the fix's proof), anything touching a shared contract (routing decisions, permission verdicts, data transformations), edge cases you can already name.

Skip it, or use it lightly, for: UI layout/visual polish, prompt/copy wording, exploratory spikes where you don't yet know the right interface, one-off scripts. Forcing a test onto something inherently subjective just produces a brittle assertion that encodes today's opinion — don't do that. If you're unsure, ask: "is there an objectively correct answer here?" If yes, TDD fits.

## RED — write a failing test that states the requirement

1. Write the smallest test that would fail against a naive/absent implementation and pass against a correct one. Name it for the behavior, not the mechanism (`test_denies_write_outside_allowed_paths`, not `test_evaluate_returns_deny`).
2. Run it. Confirm it actually fails, and fails for the reason you expect (not a typo, import error, or fixture problem). A test you haven't watched fail is a test you don't actually know works.
3. Cover the real edge cases you can already name up front — empty input, boundary values, the failure path — not just the happy path. Don't invent edge cases nobody asked about; do cover the ones the task obviously implies.

## GREEN — make it pass, minimally

1. Write the smallest real implementation that makes the test pass. Resist the urge to build the general version before you have a second test demanding it — that's premature abstraction wearing a TDD costume.
2. Run the full relevant test file (not just the new test) — a naive implementation can pass its own test while breaking an existing one.
3. If the test still fails for a reason you didn't expect, stop and understand why before changing the test. A test that keeps failing "for the wrong reason" and gets patched to pass anyway stops meaning anything.

## REFACTOR — clean up with the safety net in place

1. With tests green, improve the implementation: remove duplication, clarify names, simplify control flow. The tests are what make this safe — you're allowed to change the "how" as long as the "what" (the passing tests) doesn't move.
2. Re-run tests after each meaningful change, not just at the end — if something breaks, you want to know which specific edit caused it.
3. Don't refactor scope you didn't touch. A bug fix doesn't need the surrounding function reorganized; that's a separate change with its own review burden.

## Test levels — pick what the change actually needs

- **Unit**: the default. Fast, isolated, one behavior per test.
- **Integration**: when the change's whole point is how two real components interact (e.g. a router decision feeding a real executor) — mocking the interaction away would test nothing.
- **Regression**: mandatory for bug fixes. The test should fail against the old code and pass against the fix — verify this, don't assume it.
- **Edge cases**: boundary values, empty/null input, concurrent access where relevant, failure/timeout paths. Add these because the task calls for them, not to pad coverage.
- **E2E**: rare, and expensive to maintain — reach for it only when nothing lower in the stack can catch the class of bug (e.g. real cross-service wiring, not logic).

## Running tests in this repo

Check [hermes/verification](../hermes/verification/SKILL.md) for the exact, current commands (test paths, coverage tools) — this project's test layout has a real quirk (`pytest.ini`'s `testpaths` doesn't cover the whole suite by default) that's easy to get wrong if you assume a bare `pytest` run is comprehensive.

## Anti-patterns to avoid

- **Testing the mock, not the behavior.** If a test only proves your mock returns what you told it to return, it proves nothing about the real code path.
- **One assertion per test taken too literally.** Group genuinely related assertions about the *same* behavior; splitting them into separate tests that each set up the same scenario is noise, not rigor.
- **Writing the test after the code, then calling it TDD.** That's just testing — fine, but it doesn't get you the "did I actually understand the requirement" check that writing-first gives you.
- **Chasing coverage numbers.** A test that exercises a line without asserting anything meaningful about its output is worse than no test — it creates false confidence.
