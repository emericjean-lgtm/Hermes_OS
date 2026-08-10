---
name: documentation
description: Update documentation impacted by a code change — keeping docs in sync with real, current behavior. Use whenever a change alters something a doc describes (an API contract, a config option, a setup step, a behavior). Never generates documentation for something that doesn't exist or hasn't been verified.
---

# Documentation

Documentation's only job is to be true. Docs that describe aspirational or outdated behavior are worse than no docs — they actively mislead the next reader (human or agent) into trusting something that isn't real anymore. This project has direct, repeated experience of that cost: several of its own architecture documents describe a designed system that later audits found was never actually wired up, and stale test-count badges in its README have contradicted the real, current numbers.

## Before writing anything

**Verify against the real code, not against your memory of the code or the existing doc's own claims.** If you're documenting an API, read the actual handler. If you're documenting a config option, read the actual code that consults it — not just the option's own comment, which can drift from what the code does. If you're documenting a workflow, run it (or trace it in code) rather than describing the intended flow.

## What counts as "impacted"

A change to any of these usually means a doc needs updating:
- A public function/endpoint signature, request/response shape, or error behavior.
- A config option's meaning, default, or valid values.
- A setup/installation step (a new dependency, a changed command, a new required env var).
- A described architecture or data flow that the change actually alters (see [architecture-documentation](../architecture-documentation/SKILL.md) for structural changes specifically).
- A documented example that would now produce different output.

Not everything needs a doc update — an internal refactor with no external-facing change, or a bug fix that restores documented (rather than changes) behavior, usually doesn't. If you're unsure, check whether the current doc's description is still accurate after your change; if yes, leave it.

## Writing style

- State what's true now, plainly. Avoid hedging language that tries to cover for uncertainty you could resolve by just checking ("should work", "typically") — either verify it and state it, or say plainly that it's unverified.
- Match the existing document's structure and tone rather than imposing a new format on one section of it.
- Prefer a real, runnable example over an abstract description where one is feasible — but only include an example you've actually verified produces the output shown.
- Keep it as short as accuracy allows. A long doc nobody reads fully protects nothing; a short, accurate one does.

## Common failure modes to avoid

- **Describing intent as if it were shipped behavior.** "This will validate X" when the validation isn't actually implemented yet — write about what exists, and if something's planned, say so explicitly as a plan, not as current fact.
- **Copying an old doc's structure into a new one without checking whether the old one was ever accurate.** Some of Hermes OS's own architecture docs describe designed systems that were later found to be unwired — inheriting that pattern (writing the intended design as if it's confirmed working) repeats the exact mistake this project has already paid down once.
- **Letting counts/badges/version numbers go stale.** A "N tests passing" or "vX.Y" badge that isn't updated alongside the change it's describing becomes actively wrong the moment reality moves past it — either update it in the same change, or don't include a number that will need separate upkeep.
- **Documenting a config value's default without checking the live config file** — a comment claiming "default: X" can drift from what the shipped config actually sets, especially after a deliberate later change.

## After writing

Re-read the doc against the actual current code/config one more time before considering it done — the point of this skill is that the doc matches reality at the moment you finish, not at the moment you started writing.
