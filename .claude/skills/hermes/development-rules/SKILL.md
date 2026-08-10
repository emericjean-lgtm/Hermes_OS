---
name: development-rules
description: Hermes OS's real, derived development conventions — naming, structure, config-vs-code discipline, error handling, testing commands, Git/CHANGELOG practice, and the project's stated design principles. Use whenever writing or reviewing code in this repository, especially before introducing a new pattern that might already have an established convention.
---

# Hermes OS — Development Rules

These are derived from the real repository (code, config, `CONTRIBUTING.md`, the cahier des charges' §7/§14.2/§22, and the actual established CHANGELOG practice) — not invented. Where the codebase's own documentation is stale or contradicts the real, current behavior, that's noted explicitly and the real behavior wins.

## The project's own stated principles (cahier des charges §7)

Ten numbered principles; the two most load-bearing in practice: **"Fiable avant d'être ambitieux"** — *reliable before ambitious*: "better an agent that finishes 10 simple tasks correctly than one that promises the moon and breaks a Git repo." And **"Économe en VRAM"** — never load a heavy model when a light one suffices. The rest: local-first, controlled-first (risky actions validated/bounded), traceable, reversible, modular, extensible without rearchitecture, versatile, readable (the user understands what's happening without guessing).

**The real, dominant, unwritten principle** — not formally named in any founding doc but the organizing theme of this project's entire recent history (see [hermes/architecture](../architecture/references/timeline.md)): **never fabricate a result.** A component with no real telemetry reports itself as unmeasured, not healthy. A benchmark number comes from a real measurement or is marked as an estimate. A failure raises an error, never invents a plausible-looking success. See [hermes/verification](../verification/SKILL.md).

## Config is configuration, not code

Stated explicitly in the cahier des charges (§22.4): **model names are configuration**, never hardcoded in application logic — `config/models.yaml` is the single source of truth, resolved through `backend/core/router.py`'s `ModelRouter` (or `model_intelligence`'s `AdaptiveRouter` for the execution path — see [hermes/architecture](../architecture/SKILL.md)). This project has real, recent, first-hand evidence of what happens when this slips: a routine model upgrade (HOS-079) surfaced four separate places where a model tag had been hardcoded outside `config/models.yaml` (a default parameter value, a docstring, a fallback constant) — each one silently wrong the moment the config changed. Before adding a model-name literal anywhere outside `config/models.yaml`, ask whether it should instead be resolved through the router.

The same discipline applies to `config/security.yaml` (autonomy level, permission categories — see [security-review](../../security-review/SKILL.md)) and `config/agents.yaml` (the agent roster) — `backend/core/config.py`'s `Settings`/`load_*_config()` functions are the only place meant to read these files or `os.environ` directly; everything else should go through them.

## Backend conventions

- **Python 3.11, FastAPI, Pydantic v2.** Dependencies are deliberately minimal (`backend/requirements.txt` is explicitly commented "walking-skeleton dependencies only") — check [dependency-audit](../../dependency-audit/SKILL.md) before adding one.
- **Two coexisting architectural patterns, know which one you're in** (full detail: [hermes/architecture](../architecture/SKILL.md)): "World A" (the original agent roster) uses simple module-level singletons with `@lru_cache` (`get_settings()`, `get_agent_registry()`, etc.); "World B" (the HOS-numbered mission/DI architecture) uses the real composition root (`backend/core/bootstrap/`, explicit key-based dependency injection, no autowiring by type). Match whichever pattern the code you're extending already uses — don't introduce a third.
- **New agents** go in `backend/agents/`, subclass `BaseAgent` if they have a chat-completion contract (`respond()`/`respond_events()`), are declared in `config/agents.yaml`, and are instantiated by `core.agent_registry.AgentRegistry`. See [hermes/module-development](../module-development/SKILL.md).
- **New mutating action types** get a category in `config/security.yaml`'s `action_categories`, gated through `AegisEngine` — not a bespoke permission check. Follow the existing pattern (see e.g. the `web_search` category's own reasoning comment for how to justify a threshold).
- **Real event publishing**: use the `EventDispatcher`/`EventHub` pattern already wired through the composition root rather than inventing a new notification path — see [hermes/architecture](../architecture/references/backend-map.md)'s Events section for which bus to use for what.
- **Docstrings that explain a real, non-obvious constraint** are a genuine, established convention here — many modules document *why* a specific number or ordering was chosen (often citing a `HOS-XXX` CHANGELOG entry or a cahier des charges `§N`), not just what the code does. Follow this pattern for anything similarly non-obvious; don't restate what the code already makes clear.

## Frontend conventions

Real conventions (there's no populated `CLAUDE.md`/`AGENTS.md` describing these today — this section is filling that gap from the actual code). The frontend also carries an explicit visual identity contract (SODIUM, since HOS-080) — see [design-system](../../design-system/SKILL.md)'s contract table before introducing a new colour, font, or a generic-looking pattern; it's the same "never fabricate a result" principle above, applied to what a panel is allowed to display as a live measurement:

- **API access**: a new backend capability gets a typed method on the relevant domain client object in `services/client.ts`, plus a React Query hook in `hooks/use-api.ts` (one hook per capability, matching the existing 99). Don't call `fetch` directly from a component.
- **DTOs**: add/extend a type in `types/hermes.ts`, and if the backend's wire shape differs from what the UI wants (a case mismatch, an envelope wrapper, a field rename — this project has several real, documented examples), write the normalization in `client.ts`, not scattered across components.
- **New Center**: put it in `features/<name>/`, register it in `components/sidebar.tsx`'s groups and in `CockpitShell`'s `views` map (the `satisfies` guard makes an orphaned id a compile error — keep it that way). Build it on the Tier-2 scaffold (`AsyncPanel`/`StatGrid`/`Toolbar`/`DataTable`/`CenterTabs` from `components/center-scaffold.tsx`) — Memory and Governance Centers are the cleanest current examples to copy; several older Centers hand-roll loading/error state instead, which is legacy, not the pattern to extend.
- **State**: server data through React Query hooks; only genuinely global UI state (active view, nav state, live-event buffer) goes in the single `useCockpitStore` Zustand store. Don't add a second store or reach for Context.
- **Styling**: use the existing design tokens (`--hermes-*` CSS custom properties, mirrored in `tailwind.config.ts` — keep both in sync if you touch either) and the established semantic color convention (cyan=system, magenta=human-decision, green/amber/red=health, violet=autonomous). See [design-system](../../design-system/SKILL.md).
- **Before creating a new component or hook**, check whether one already exists — this project has several real, confirmed instances of dead duplicate code (an old streaming client superseded by a newer one at the real call site, a duplicate provider config, a WebSocket hook nobody imports) left in place after being replaced rather than removed. Don't add to that pattern, and if you're touching an area with an obvious duplicate, flag it for [codebase-cleanup](../../codebase-cleanup/SKILL.md) rather than silently working around it.

## Testing — the real, current commands

`pytest.ini` sets `testpaths = backend/tests`, so **a bare `pytest` only ever collects `backend/tests/`** — it silently skips the entire top-level `tests/` tree (97 files across 13 subdirectories: architecture, autonomous, conversation, integration, model_intelligence, tools, api, security, production, evolution, integrations, sds, support). `CONTRIBUTING.md` and `README.md` both give commands/badges that don't reflect this (one references only `pytest tests/`, which misses `backend/tests`; the README's test-count badge is stale versus the real, current number). **The comprehensive command is `pytest backend/tests tests -q`** (or run the two paths separately) — use this, not a bare `pytest`, when "run everything" is what's meant. See [hermes/verification](../verification/SKILL.md) for full detail including the one known pre-existing flaky test.

Frontend: `pnpm --dir frontend test` (vitest). Note there's no root-level `test:frontend` script — only `test`/`test:backend` exist at the repo root.

## Git & CHANGELOG practice

- This repo's standing workflow: audit real code → propose a plan → get explicit approval for non-trivial work → implement with real tests → verify (browser/live checks where applicable) → write a CHANGELOG entry → commit → push. See [release-notes](../../release-notes/SKILL.md) for the CHANGELOG format specifically, and [hermes/verification](../verification/SKILL.md) for what counts as actually verified.
- New commits, not amends, unless explicitly asked otherwise. Never force-push or skip hooks without explicit instruction.
- CHANGELOG entries are the project's primary "why" record — code comments across the backend cite specific entries (`HOS-065C`, `HOS-077`) as the reason a constant or check exists. Write real, verified entries, matching the existing entries' format and honesty about what's deferred/out of scope.

## Known, real gaps not worth "fixing" reflexively

No CI/CD exists (no `.github/workflows` at all) — verification here is manual/agent-driven, not pipeline-enforced; don't assume a check "will run in CI." `deployment/`/`installer/` (Postgres/Redis/Docker) are aspirational and disconnected from the real SQLite/ChromaDB dev stack — don't treat them as how the app actually runs today, and don't "fix" the dev workflow to match them without that being the actual task. No ruff/mypy config exists (`.ruff_cache` exists but no `pyproject.toml`/`ruff.toml`) — lint is ad hoc, not enforced; don't assume a lint failure blocks anything today.
