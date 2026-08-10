---
name: ui-ux
description: UX analysis before implementing or changing a Hermes OS Cockpit Center (Mission, Agent, Runtime, Memory, Skills, Tools, Governance, or any of the other 22 real Centers). Use before building new UI, before restructuring information density or navigation in a Center, and when a change could affect how the operator understands system state at a glance.
---

# UI/UX Analysis

Hermes OS's Cockpit is an operations dashboard for a single, technically-capable user managing autonomous agents and missions — not a marketing site, not a consumer app. UX here means the operator can tell, at a glance, what's happening and what needs their attention; anything that makes that slower or more ambiguous is a real regression, even if it looks polished.

## The real structure to work within

"Cockpit" (`CockpitShell`) is the permanent shell — sidebar, topbar, statusbar — hosting whichever of the **22 real Centers** is active, switched client-side via a single Zustand store (there's effectively one real route, `/dashboard`; Centers aren't separately addressable URLs today). See [hermes/architecture](../hermes/architecture/references/frontend-map.md) for the full inventory. Before building a new screen, check whether it's actually a new Center or a tab/section within an existing one — this project has already deliberately merged overlapping Centers twice (Memory absorbed a separate Knowledge Graph and Alexandrie screen; Governance absorbed a separate Policy screen) specifically because they called near-identical endpoints and didn't earn separate top-level nav slots. Don't reintroduce that fragmentation.

## What to check before implementing

- **Information density** — an operations dashboard should surface state, not require drilling in to see if something needs attention. Encode state in form as well as text: a pill/badge/severity color reads faster than a sentence. This project's own design tokens are already semantic (cyan=system, magenta=human-decision-point, green/amber/red=health, violet=autonomous activity) — use the existing meaning, don't invent a new color convention for the same kind of signal.
- **Loading / error / empty / success states** — every real data-driven panel needs all four handled explicitly, not just the happy path. The existing `AsyncPanel` component (see [design-system](../design-system/SKILL.md)) exists specifically to make skipping one of these a visible gap rather than an easy oversight — use it for new Centers/panels rather than hand-rolling state branches, unless there's a specific reason the scaffold doesn't fit.
- **Failure isolation** — a single Center's error should never take down the whole Cockpit. This project has a real, working `CenterBoundary` error boundary for exactly this, added after this failure mode was reproduced multiple times in practice — make sure any new Center is actually wrapped by it (check how existing Centers are mounted in `CockpitShell`'s views map).
- **Responsive** — the Cockpit is a dense, information-heavy interface; verify a new panel doesn't break down at smaller viewport widths, especially anything using the `DataTable`/`StatGrid` scaffold components.
- **Accessibility** — real keyboard focus visibility, `prefers-reduced-motion` respected (the existing animated grid/nebula background and neon-edge effects already honor this — anything new with animation should too).
- **Live/streaming state** — several Centers show real-time data (events, chat, mission progress). Distinguish "this data is live and updating" from "this data is a static snapshot" visually — this project has a real, currently-broken example worth knowing about: the Topbar's LIVE/OFFLINE badge is permanently stuck on OFFLINE because nothing sets the state it reads, while the actual working connection indicators live independently inside `DashboardView`/`EventsCenter`. Don't copy that broken pattern into new work, and if touching connection-status UI, be aware the "obvious" existing indicator (the Topbar badge) doesn't reflect reality.

## Before adding a component, check design-system

See [design-system](../design-system/SKILL.md) — this project has two generations of shared Center-building components (a plain primitive tier and a richer composition tier), and the newer tier is a deliberate reuse target, not just one option among equals.

## Copy and labeling

Name things by what the operator recognizes (a mission, an agent, a task) not by internal implementation names (don't surface "MissionNode" or "DAG" in UI copy where "task" or "step" is what a human would say). Match the existing Cockpit's terse, technical-but-legible voice — this is an operator's tool, not a consumer product; don't soften or over-explain in a way that adds noise without adding clarity.

## Verification

For any UI change, actually run the dev server and exercise it in a browser — see [hermes/verification](../hermes/verification/SKILL.md). A type-checked, unit-tested component that was never actually looked at in a browser has not been verified for the thing UX review is actually about.
