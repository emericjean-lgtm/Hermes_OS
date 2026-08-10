---
name: debugging
description: Structured root-cause debugging workflow for a real bug, error, crash, or unexpected behavior. Use whenever something is broken and the cause isn't already obvious — a failing test, an exception in logs, a live 404/500, a silent wrong-output bug, or a "this used to work" regression. Explicitly avoids speculative fixes.
---

# Debugging

Reproduce -> collect evidence -> form a hypothesis -> instrument -> find the real cause -> fix minimally -> add a regression test -> verify. The discipline this enforces is refusing to change code you don't yet understand is wrong — a fix applied before the cause is known has maybe a coin-flip's chance of being right, and even when it "works" you often can't say why, which means you can't say it won't recur elsewhere.

## 1. Reproduce

Get the bug to happen in front of you, reliably, before touching any code. If you can't reproduce it: narrow the conditions (exact input, exact environment, exact sequence of actions) until you can, or gather more evidence from logs/reports until a reproduction path becomes clear. A fix for a bug you can't reproduce is a guess wearing a diff.

If it's genuinely intermittent (race condition, external service flakiness, resource exhaustion under load), say so explicitly rather than pretending you reproduced it — the debugging approach for "always happens" and "happens sometimes" is different, and conflating them wastes time.

## 2. Collect evidence

Before forming a theory, gather what's actually there: the full error message and stack trace (not a paraphrase), the real input that triggered it, relevant log lines, the actual state of the system (what was in the DB/cache/queue, what model was loaded, what config was active). Read the failing code path yourself rather than trusting a memory of what it does — code drifts from what you last read it as.

## 3. Form a hypothesis

State a specific, falsifiable claim: "X is null because Y never sets it when Z happens" — not "something's probably wrong with the auth flow." A vague hypothesis can't be tested and tends to survive contact with evidence that should have killed it. If you have more than one plausible hypothesis, note them, but investigate the most likely one first rather than guessing across all of them with code changes.

## 4. Instrument, don't guess

Add logging, a debugger breakpoint, a print statement, a smaller reproduction script — whatever gets you a real, direct observation of the state at the point that matters. Prefer instrumenting over reasoning-in-your-head-from-the-code once you have a concrete hypothesis to check; code that *should* behave a certain way and code that *does* diverge more often than intuition expects, especially around edge cases, async timing, or third-party library behavior.

This project has a track record of exactly this kind of surprise — e.g. a client library silently dropping data on a specific chunk pattern, or a check ordered one line differently than assumed. Don't skip straight from "here's my theory" to "here's my fix" without the observation step in between.

## 5. Identify the real cause

Confirm your hypothesis against the instrumentation output before writing a fix. If the evidence doesn't match the hypothesis, that's not a reason to fix it anyway and hope — go back to step 3 with what you just learned. "The fix made the symptom go away" is not the same as "I found the cause" — a fix that happens to work can mask a deeper problem that resurfaces somewhere else.

Distinguish the root cause from a downstream symptom. If a value is null three functions later, ask why it was never set in the first place, not just how to null-check around the crash site.

## 6. Fix minimally

Change what's actually wrong, nothing else. Resist the temptation to "clean up while you're in there" — that's a separate change with its own review burden, and it makes the actual fix harder to verify in isolation. If the root cause reveals a class of similar bugs elsewhere (the same wrong pattern copy-pasted in three places), say so and ask whether to fix all instances now or file it separately — don't silently expand scope.

## 7. Add a regression test

Write a test that fails against the old (buggy) code and passes against the fix. If you can, verify this by temporarily reverting the fix and confirming the test fails for the right reason. This is what turns "I fixed a bug" into "this bug cannot silently come back." See [tdd-workflow](../tdd-workflow/SKILL.md).

## 8. Validate

Re-run the original reproduction (not just the new test) to confirm the actual reported symptom is gone. Run the broader test suite for anything the fix touched — a root-cause fix in shared code can affect callers you didn't have in mind. See [hermes/verification](../hermes/verification/SKILL.md) for what "actually verified" means in this repo before calling anything fixed.

## Anti-patterns

- **Shotgun debugging**: changing several things at once and seeing if the symptom disappears. Even when it works, you don't know which change mattered, and you may have introduced new bugs the others are masking.
- **Fixing the stack trace, not the bug**: adding a null check or try/except at the crash site without understanding why the null/exception happened. This usually just moves the failure somewhere quieter.
- **Trusting your memory of the code over the code**: re-read the actual current source at the point of failure — it may have changed since you last looked, or may not do what its name/comment implies.
- **Declaring victory without reproducing the original symptom gone.** "The code looks right now" is not verification.
