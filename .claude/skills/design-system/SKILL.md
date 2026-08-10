---
name: design-system
description: Check for an existing component, token, or pattern before building a new one in Hermes OS's frontend. Use before creating any new UI component, adding a color/spacing value, or building a new Center's layout.
---

# Design System — Check Before You Build

The question this skill exists to force, every time: **does this already exist?** Hermes OS's frontend has a real, if inconsistently-adopted, shared system — building a one-off instead of reusing or extending it is how a 22-Center app ends up with 22 different layouts, which is exactly the fragmentation this system was built to prevent (see its own in-code doc-comment stating that intent directly).

## Before creating a new component, check in order

1. **Does a primitive already cover this?** `components/ui/card.tsx` — `Card`, `Badge` (7 variants), `Beacon` (pulsing status dot), `StatCard`, `ProgressBar` (color-ramped, invertible for "high is bad" meters), `Button` (4 variants). Most low-level visual needs are already here.
2. **Does the Center-composition tier already cover this?** `components/center-scaffold.tsx` — `CenterHeader`, `StatGrid`, `Toolbar`, `AsyncPanel` (the loading/error/empty/content pattern — use this rather than hand-rolling those four states again), `PanelLoading`, `DataTable<T>`, `CenterTabs<T>`, `LiveBadge`. This tier exists specifically so a new Center doesn't need its own bespoke layout logic.
3. **Does an existing token already express this value?** Colors, in `app/globals.css`'s CSS custom properties (`--hermes-cyan`/`--hermes-magenta`/`--hermes-violet`/`--hermes-green`/`--hermes-amber`/`--hermes-red`/`--hermes-blue`, plus bg/text/muted/dim), mirrored into `tailwind.config.ts`'s `theme.extend.colors.hermes`. **Both files must stay in sync** — the Tailwind mirror is what makes `text-hermes-*` classes compile to anything at all; a token added to one without the other silently does nothing.
4. **Does a similar Center already solve this exact layout problem?** Memory and Governance Centers are the current best examples — both fully built on the Tier-2 scaffold. If extending or building a Center, look at one of these first, not an older hand-rolled one, even though several older Centers exist as precedent — they predate the scaffold's full adoption and are legacy, not the pattern to copy forward.

Only build new if none of the above genuinely fits — and if you do, consider whether the new thing belongs in the shared component tier (if it's likely to be reused) rather than living locally in one Center's file.

## The real token system

Color is semantic, not decorative — cyan means the system is speaking, magenta means a human decision point, green/amber/red are health states, violet means autonomous activity. Reuse this meaning for anything new rather than picking a color for its aesthetics alone; introducing a new color for a concept that already has a semantic home creates a second, competing visual language.

## Real gaps to know about, not to silently "fix" as a side effect

- **Dark theme only, on purpose (so far)** — no theme toggle, no `next-themes`, no `dark:` Tailwind variant in use, and `<html>`'s `dark` class is hardcoded. If a task explicitly asks for a light theme, that's real, scoped work — [frontend-design](../frontend-design/SKILL.md) and [hermes/architecture](../hermes/architecture/references/frontend-map.md) have the token/CSS-variable structure that would need a light-mode counterpart. Don't add light-mode styling opportunistically while working on something unrelated.
- **The declared monospace stack (`JetBrains Mono, Fira Code, ...`) is never actually loaded** (no `next/font`, no `@font-face`) — it silently falls back to whatever monospace the OS provides. If you're touching typography and this matters for what you're building, that's worth flagging explicitly rather than assuming the intended font is what's rendering.
- **Scaffold adoption is inconsistent across the 22 Centers** — don't assume every existing Center is a good model to copy; check which generation it's actually using (see `references/frontend-map.md` under [hermes/architecture](../hermes/architecture/SKILL.md) for the current per-Center breakdown) before treating it as precedent.

## When extending a token or primitive

Changing an existing token or primitive affects every Center that uses it — this is shared-contract territory. Check real usage across `features/` before changing a `Badge` variant's meaning or a color token's hex value, the same discipline as [architecture-review](../architecture-review/SKILL.md) applied to the frontend.
