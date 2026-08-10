---
name: verification
description: Hermes OS's "verification first" discipline — never declare something done, fixed, or working without real proof. Use before saying anything is complete, functional, or fixed in this repository, and whenever you need the real (not documented-but-stale) commands for running tests, typecheck, lint, and build.
---

# Verification First

This is the single most consistently-applied principle in Hermes OS's real development history — more consistently followed than anything formally written in its founding documents. The project's own audit trail ([hermes/architecture](../architecture/references/timeline.md)) is a direct, repeated demonstration of what happens without it: a validation step that was `random.random() > 0.15`, a benchmark scheduler that used `random.uniform()` instead of real Ollama measurements, an MCP client that reported "connected" without ever opening a socket, six identical requests reporting six different invented durations. Every one of these was found by someone actually checking, and every fix since has been judged by the same standard.

## Never say, without proof

- **"Done" / "implemented"** — without having actually run the code and observed the real result.
- **"Fixed"** — without a test that fails on the old code and passes on the new one (see [debugging](../../debugging/SKILL.md)'s regression-test step), or equivalent direct observation that the original symptom is gone.
- **"Working" / "functional"** — without exercising the real path, not just a unit test of an isolated piece. A module can pass its own tests and still not be reachable from anywhere real — see [hermes/module-development](../module-development/SKILL.md)'s integration step, which exists specifically because this project has multiple real, confirmed cases of exactly that.
- **"Tested"** — without saying which tests, run how, with what real result. "Should pass" is not a result.

If something wasn't actually verified — a path couldn't be exercised in this environment, a manual UI check wasn't possible, a live-hardware measurement wasn't taken — **say so explicitly**. This project treats an honestly-flagged gap as normal and a silently-assumed success as the actual failure worth catching. A silent fallback that "just works" without anyone confirming what it fell back to is treated as a bug in this codebase, not a convenience — see the real HOS-077 example: a 90-second decomposition timeout silently substituted a generic English-language template for a French-language request, with zero visible indication anywhere in the UI or API that this had happened, until someone happened to compare the output against the actual request.

## The real, current verification commands

`pytest.ini`'s `testpaths = backend/tests` means a bare `pytest` only collects `backend/tests/` — it silently misses the entire top-level `tests/` tree (97 files, 13 subdirectories). Some of this project's own docs (`CONTRIBUTING.md`, `README.md`) give commands or badges that don't reflect this and are stale relative to the real current numbers.

**The actual comprehensive command: `pytest backend/tests tests -q`** (from the repo root) — or the two paths separately if you need to isolate one. Use this, not a bare `pytest`, whenever "run the full suite" is what's meant.

Frontend: `pnpm --dir frontend test` (vitest) for tests, `pnpm --dir frontend lint` (or root `pnpm lint`) for ESLint, `tsc --noEmit` (via the frontend's own tooling) for typecheck. No root `test:frontend` script exists — don't assume `pnpm test` covers the frontend; it only runs `test:backend`.

There is **no CI/CD** in this repository (no `.github/workflows`, nothing) — a check you ran locally is the only verification that exists; nothing runs it again automatically later. `config/verification.yaml` defines a fixed, safe whitelist of runners (`pytest`, `ruff`, `ruff_format_check`, `mypy`, `npm_test`, `npm_build`, `tsc`) that Aegis gates behind the `verification_run` category — useful if triggering a check through the agent-tool surface rather than a direct shell command.

## Distinguishing a real regression from a known pre-existing flake

This project has one documented, tracked, pre-existing flaky test (`test_task_executor_shares_the_container_model_intelligence` — an order-dependent shared-state issue between test files, not a product bug) that has appeared across multiple otherwise-clean full-suite runs. Before treating a failing test as something your change broke:
1. Run the failing test file alone — if it passes in isolation but fails in the full combined run, that's the signature of a shared-state/ordering issue, not your change.
2. Check whether the failure is already a known, named, tracked issue (search recent CHANGELOG entries) before spending time re-diagnosing it from scratch.
3. Never silently ignore a failure because you assume it's the known flake — confirm it's the *same* failure, not a new one that happens to also be intermittent.

## Real hardware measurement, not estimation

This project runs on real, specific, constrained hardware (see [hermes/runtime](../runtime/SKILL.md)) and has an established, repeatedly-applied practice of measuring rather than estimating: VRAM figures in `config/models.yaml` are annotated with whether they're a real measurement or an extrapolation, benchmark numbers come from Ollama's own real counters (`eval_count`/`eval_duration`), and a model swap is verified with a real `ollama ps` GPU/CPU-split check before being accepted into config — not assumed correct from a spec sheet or a "should be similar" guess. Apply the same standard to any resource-, latency-, or capacity-related claim: measure it on this real system, or mark it explicitly as unverified.

## For UI/frontend changes specifically

Start the real dev server and exercise the actual feature in a browser before calling it done — type-checking and a green test suite verify code correctness, not feature correctness. If the environment doesn't allow a live browser check, say that explicitly rather than implying the feature was seen working.

## The honest failure report

When something doesn't work, or can't be verified, or was only partially completed: state exactly what was checked, what the real result was, and what remains unknown or unverified. This project's own CHANGELOG is full of real examples of this done well — entries that name a specific bug found while testing (not while auditing), give exact before/after numbers, and explicitly list what's still out of scope. That's the bar.
