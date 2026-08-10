# Hermes OS — Claude Code skills

This is a development-environment skill set **for Claude Code while building Hermes OS**. It is not part of Hermes OS itself, and nothing here changes Hermes OS's own application code or architecture — every skill lives under `.claude/` and describes how to work on this repository well.

Start with [project-context](project-context/SKILL.md) if you're new to a task here — it's the front door and points at the right deeper skill for what you're about to do.

## Routing matrix

| Task type | Skill sequence |
|---|---|
| New feature | [technical-spec-review](technical-spec-review/SKILL.md) → [implementation-planning](implementation-planning/SKILL.md) → [tdd-workflow](tdd-workflow/SKILL.md) → [code-review](code-review/SKILL.md) |
| Bug | [debugging](debugging/SKILL.md) → [tdd-workflow](tdd-workflow/SKILL.md) (regression test) → [code-review](code-review/SKILL.md) |
| Architecture-affecting change | [architecture-review](architecture-review/SKILL.md) → [architecture-documentation](architecture-documentation/SKILL.md) |
| Frontend / Cockpit UI | [frontend-design](frontend-design/SKILL.md) → [ui-ux](ui-ux/SKILL.md) → [design-system](design-system/SKILL.md) → [tdd-workflow](tdd-workflow/SKILL.md) |
| Runtime / models / Ollama / GPU | [hermes/runtime](hermes/runtime/SKILL.md) → [performance-analysis](performance-analysis/SKILL.md) / [resource-analysis](resource-analysis/SKILL.md) |
| Security-sensitive change | [security-review](security-review/SKILL.md) |
| Documentation update | [documentation](documentation/SKILL.md) → [architecture-documentation](architecture-documentation/SKILL.md) (if structural) |
| Refactoring | [code-review](code-review/SKILL.md) → [tdd-workflow](tdd-workflow/SKILL.md) → [codebase-cleanup](codebase-cleanup/SKILL.md) |
| Multi-part independent work | [multi-agent](multi-agent/SKILL.md) |
| New Claude Code skill | [skill-creator](skill-creator/SKILL.md) |
| New backend module (agent, DI service) | [hermes/module-development](hermes/module-development/SKILL.md) |
| "Is this actually done?" | [hermes/verification](hermes/verification/SKILL.md) — always, before declaring anything fixed/working/complete |
| End of a substantial task | [workthrough](workthrough/SKILL.md), then [release-notes](release-notes/SKILL.md) once verified |
| Adding a dependency (package or external skill) | [dependency-audit](dependency-audit/SKILL.md) |

None of this is a rigid pipeline — pick the skills the actual task calls for, skip what doesn't apply, and load a skill only when its trigger condition is real. The point is knowing what's available, not running every skill on every task.

## Two skill families

**Generic engineering skills** (the ones above, not under `hermes/`) — process and methodology. Written for this project's real conventions but not exclusively about Hermes OS's own code; the discipline (TDD, debugging, code review, security review, documentation, multi-agent coordination) applies to work here the same way it would anywhere, just calibrated to this repo's actual practices.

**`hermes/` skills** — Hermes OS-specific facts, derived exclusively from this repository's real, current code (last grounded 2026-08-10, HOS-079). Load these when you need to know how *this* system actually works, not general practice:
- [hermes/architecture](hermes/architecture/SKILL.md) — the real backend/frontend map, what's live vs. dead vs. built-but-dormant vs. duplicated. Read this before touching any central subsystem.
- [hermes/development-rules](hermes/development-rules/SKILL.md) — derived conventions (naming, config-vs-code discipline, testing commands, Git/CHANGELOG practice).
- [hermes/module-development](hermes/module-development/SKILL.md) — checklist for building/changing an HOS module, with explicit emphasis on the integration step this project's own history shows is easiest to skip.
- [hermes/verification](hermes/verification/SKILL.md) — this project's "never fabricate a result" discipline, and the real (not stale-doc) test commands.
- [hermes/runtime](hermes/runtime/SKILL.md) — Ollama/GPU/VRAM/model-routing constraints specific to this deployment's real hardware.

## A note on where the content came from

Two skills — [skill-creator](skill-creator/SKILL.md) and [frontend-design](frontend-design/SKILL.md) — are adopted, close to verbatim (Apache 2.0, `LICENSE.txt` in each), from Anthropic's official `anthropics/skills` repository; `frontend-design` has one short added section pointing at Hermes OS's real, existing visual system. Every other skill here was purpose-written for this engagement rather than pulled from a third-party marketplace — see the final report delivered alongside this skill set for the reasoning (source trust, safety, and fit considerations that led to writing rather than importing for the remaining categories).

Don't treat this README as a substitute for the skills it indexes — it's a map to help you load the right one quickly, not a summary of their content.
