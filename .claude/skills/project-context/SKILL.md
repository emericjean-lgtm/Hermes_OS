---
name: project-context
description: Load Hermes OS's real project context (architecture, conventions, current state, open work) before starting any non-trivial task in this repository. Use this at the start of a session, when picking up unfamiliar territory, or whenever you're about to make a decision that depends on how the rest of the system actually works rather than how a generic project would work.
---

# Project Context

This skill is the front door. Its only job is to point you at the right real sources before you start reasoning about Hermes OS from assumptions — a generic-looking FastAPI + Next.js repo is not evidence that Hermes OS behaves like a generic FastAPI + Next.js repo, and this codebase has enough project-specific architecture (mission execution, autonomous agents, local-model routing, a real permission engine) that guessing is more expensive than reading.

## Why this exists

Hermes OS has ~40 backend packages, 27+ architecture documents, a 65KB+ spec (`CAHIER_DES_CHARGES_HERMES_OLLAMA.md`), and hundreds of CHANGELOG entries recording real decisions and their reasons. None of that is optional color — code comments across the backend cite specific spec sections (`§9.1`, `§17`, `§22`) and specific past CHANGELOG entries (`HOS-065C`, `HOS-077`) as the reason a given constant or check exists. Skipping context means re-deriving decisions that were already made, tested, and recorded — usually worse the second time.

## What to read, and when

Don't read everything up front — that defeats progressive disclosure and burns context on things you won't need. Match the read to the task:

| You're about to... | Read first |
|---|---|
| Touch a specific backend subsystem (mission, autonomous, security, memory, model routing, runtime) | [hermes/architecture](../hermes/architecture/SKILL.md) — the real, audited map of what each package does and how they connect |
| Add or change a backend/frontend convention (naming, structure, error handling, tests) | [hermes/development-rules](../hermes/development-rules/SKILL.md) |
| Create or modify an HOS module end to end | [hermes/module-development](../hermes/module-development/SKILL.md) |
| Decide whether something is actually done | [hermes/verification](../hermes/verification/SKILL.md) |
| Touch anything involving Ollama, GPU/VRAM, model selection, or agent execution | [hermes/runtime](../hermes/runtime/SKILL.md) |
| Something bigger — a new feature area, or you're unsure which of the above applies | Read the real docs directly (see below) — don't guess from a skill summary when the source is one file away |

## Real sources, ranked by how current they are

1. **`CHANGELOG.md`** (repo root) — the most reliable record of *why* things are the way they are, in chronological order, newest first. Every HOS-numbered entry is a real shipped change with its own reasoning, not a summary — when a code comment references `HOS-XXX`, this is where to find the full story. For a fast timeline scan: `grep "^## HOS-" CHANGELOG.md`.
2. **`docs/architecture/*.md`** — 27 focused architecture documents (one per major subsystem: mission graph, autonomous execution, model intelligence, security/trust, unified memory, knowledge graph, event catalog, MCP, tool platform, cockpit, workspace, policy engine, self-evolution, and more). These describe *designed* contracts — cross-check against real code before assuming something documented is fully implemented; `hermes/architecture` already does this cross-check for the core subsystems.
3. **`CAHIER_DES_CHARGES_HERMES_OLLAMA.md`** — the master specification. Numbered sections (§) are cited directly in code comments and tests. If you see a `§` reference in code and want the full requirement it's satisfying, this is where it lives.
4. **`ARCHITECTURE.md`, `VISION.md`, `ROADMAP.md`, `DESIGN_DECISIONS.md`** (repo root) — project-level framing: what Hermes OS is for, its stated principles, where it's headed, and past architectural trade-offs with their reasoning.
5. **`frontend/CLAUDE.md`, `frontend/AGENTS.md`** — existing, authoritative frontend conventions. These are not something this skills system replaces or duplicates — they take precedence over any frontend guidance elsewhere in `.claude/skills/`.
6. **`docs/release/*.md`** — point-in-time audit/validation snapshots (RC audits, gap reports). Useful for understanding what was found broken and fixed over time, less useful as a description of current state (check the date and cross-reference with CHANGELOG).

## The standing engagement discipline

Independent of which skill you load next, this project has an established working rhythm worth carrying into any task here:

- **Audit before proposing.** Read the real code/config before describing what it does or proposing a change — this codebase has surprised its own maintainers more than once (a routing bug, a silently-swapped fallback, a config value that drifted from its own comment).
- **Propose, then implement.** For anything non-trivial, lay out the plan and the reasoning before writing code, especially when a change touches a shared contract.
- **No fabrication.** Never report something as "done", "fixed", or "verified" without having actually run it. If a fallback or default kicks in silently, that's treated as a bug worth surfacing, not a detail to omit — see [hermes/verification](../hermes/verification/SKILL.md).
- **Real tests, real numbers.** VRAM, latency, and throughput figures in this codebase are measured on real hardware (an RX 6800, ~17.16GB usable VRAM at Q4), not estimated — see [hermes/runtime](../hermes/runtime/SKILL.md) before changing anything model- or resource-related.

## Don't over-load

This skill's job is routing, not reading everything itself. If you're already deep into a specific subsystem and know which file answers your question, go read that file directly — you don't need to re-enter this skill first.
