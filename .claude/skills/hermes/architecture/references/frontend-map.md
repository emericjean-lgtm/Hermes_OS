# Frontend map (full detail)

Grounded 2026-08-10, updated same day after HOS-080 (complete visual redesign — "SODIUM" direction). Next.js 15.1.0, React 19, TypeScript strict mode, Tailwind v3.4.16 (not v4 — see gotcha below).

## Convention docs — read, but thin

`frontend/CLAUDE.md` is one line, `@AGENTS.md` (a pure include). `frontend/AGENTS.md` is 6 lines, only a warning to check `node_modules/next/dist/docs/` before writing code — that directory does not actually exist in this install (confirmed HOS-080), so the instruction can't be followed literally; treat it as "verify current Next.js behavior before assuming training-data conventions still hold," not as a literal file to open. `frontend/README.md` is **stale, unmodified `create-next-app` boilerplate** — still true after the redesign, still worth ignoring as a source of truth. None of the three describe the Centers, the design system, or state conventions — this file and [design-system](../../../design-system/SKILL.md) exist to fill that real gap.

## The redesign — SODIUM

HOS-080 replaced the entire visual system in one pass, on explicit user instruction to avoid the generic-AI-dashboard look (cyan+magenta neon, glow on every hover, uniform rounding, an undifferentiated accent palette). The organizing idea: **temperature contrast** — a cold, blue-tinted carbon chassis carrying **one** warm signal colour. Old token *names* were kept as the public API (`text-hermes-cyan`, `.glass`, `.neon-edge`, `.bracket`, etc. all still work) so the 22 Centers inherited the new look without 22 separate edits — but the values underneath changed completely. Prefer the new semantic names (`sodium`/`glacier`/`steel`/`arc`/`gold`/`alarm`) in new work; the legacy names (`cyan`/`magenta`/`violet`/`green`/`amber`/`red`) are aliases kept only for backward compatibility with markup that hasn't been revisited yet.

**Token values** (`app/globals.css`'s `:root`, mirrored in `tailwind.config.ts` — keep both in sync if you touch either):

| Semantic name | Hex | Meaning | Legacy alias |
|---|---|---|---|
| `sodium` | `#ff9436` | the system speaking; the one dominant accent; every interactive affordance | `cyan` |
| `glacier` | `#5eb8e8` | a human decision point (cold, rare, deliberate) | `magenta` |
| `steel` | `#8ab4f0` | autonomous activity | `violet` |
| `arc` | `#9ede3a` | health: good | `green` |
| `gold` | `#ffc93d` | health: caution | `amber` |
| `alarm` | `#ff5347` | health: bad | `red` |

Chassis: `bg #080a0d` / `bg-deep #050609` / `surface #0d1116` / `card #11161d` / `elevated #182029` / `border #212a35` / `border-bright #33404f` — all cold, blue-tinted, never pure black (pure `#000` reads as an absence, not a material).

**Fonts — now actually loaded.** The pre-redesign config declared JetBrains Mono in Tailwind but never loaded it anywhere; every `font-mono` reading silently fell back to the OS default. HOS-080 fixed this: `app/layout.tsx` loads three roles via `next/font/google` — **Chakra Petch** (`--font-chakra`, display: numerals, screen titles, the wordmark — used through the `.display` utility class), **Barlow** (`--font-barlow`, default body/interface face), **IBM Plex Mono** (`--font-plex`, data: every id, telemetry value, code block — used through the `.num` utility class, which also sets `font-variant-numeric: tabular-nums`).

**Geometry**: chamfered corners (`.clip-corner` / `.clip-corner-sm` / `.clip-notch`, CSS `clip-path` polygons) replace the old uniform `rounded-xl`/`rounded-lg`. Deliberately varied — a tighter chamfer on dense cells, a wider one on hero panels — not a single uniform radius token.

**Texture — new.** `.room-grain` (a fixed, `pointer-events: none`, `mix-blend-mode: overlay` SVG-noise layer, opacity ~0.5, lower under `prefers-reduced-motion`) and `.room-vignette` (a radial darkening toward the edges) sit above the whole app, mounted once in `app/layout.tsx`. This is what stops large flat panels reading as sterile vector fills — the single biggest "AI-generated" tell the redesign specifically targeted.

**Signature element**: `components/telemetry-trace.tsx`, a real oscilloscope drawn on `<canvas>`, plotting real polled values (VRAM/RAM) on a fixed rolling window. It is deliberately honest about missing data — it holds a flat baseline rather than interpolating or randomizing a waveform when a reading is unavailable. This is the concrete referent for the "no fabricated metrics" rule below — it was designed to that constraint from the start, not retrofitted.

## Structure

- **`app/`** — still effectively one real page (`/dashboard`, redirected from `/`). `app/layout.tsx` now loads all three fonts and mounts `.room-grain`/`.room-vignette`. `app/providers.tsx` is still dead code (confirmed still unused after the redesign).
- **`components/`**:
  - `ui/card.tsx` — Tier 1 primitives, **rewritten for SODIUM**: `Card`, `Badge`, `Beacon`, `StatCard`, `ProgressBar` (now a segmented 24-cell meter, not a smooth capsule), `Button`. All gained a `spotlight` pointer-tracking glow (`useSpotlight` hook, sets `--mx`/`--my` custom properties read by the `.spotlight` CSS rule) so panel depth responds to the real cursor instead of glowing uniformly on hover.
  - `center-scaffold.tsx` — Tier 2 composition primitives, same components as before (`CenterHeader`, `StatGrid`, `Toolbar`, `AsyncPanel`, `PanelLoading`, `DataTable`, `CenterTabs`, `LiveBadge`), geometry aligned to `clip-corner`/`clip-corner-sm` and the title face switched to `.display`/`text-gradient-sodium` in the HOS-080 follow-up pass. Same adoption inconsistency as before the redesign (see below) — this file didn't change which Centers use it, only what it looks like.
  - `rail.tsx` (new, replaces the deleted `sidebar.tsx`) — a permanent 56px icon rail with a hover flyout for names, grouped with technical reference marks (S1…S5) instead of text headers. The expand/collapse sidebar is gone entirely; there is no "collapsed" state anymore.
  - `instrument-bar.tsx` (new, replaces the deleted `topbar.tsx`) — three zones: position (current Center name), live telemetry (`TelemetryTrace` for VRAM/RAM, GPU temperature), and state/command (health status, ⌘K affordance).
  - `command-palette.tsx` (new) — ⌘K navigation, the primary way to move between 22 screens once you know the system. Matches label + group + free-text keywords (`nav-model.ts`'s `keywords` field), so e.g. "vram" finds Runtime and "aegis" finds Security without either word appearing in the visible menu.
  - `nav-model.ts` (new) — the single navigation model (`NAV_GROUPS`/`ALL_NAV_ITEMS`), shared by the rail and the palette so they can't drift apart.
  - `telemetry-trace.tsx` (new) — the canvas oscilloscope, described above.
  - `sidebar.tsx` and `topbar.tsx` — **deleted** (were already effectively legacy; HOS-080 removed them outright rather than leaving dead code, and updated the one test file — `__tests__/cockpit.test.ts` — that referenced them by name).
  - `cockpit-shell.tsx` — same `views` map / `satisfies Record<string, React.FC>` guard as before (still the mechanism that turns an orphaned nav id into a compile error), now composing `Rail` + `InstrumentBar` + `StatusBar` + `CommandPalette` instead of `Sidebar` + `Topbar` + `StatusBar`. The rail defaults to a fixed narrow width (`--rail-w: 56px`), but HOS-08x reintroduced a pinnable expanded mode (`useCockpitStore`'s `railPinned`/`toggleRailPin`, `rail.tsx`'s pin button) that sets `--rail-w` to `--rail-w-expanded` (232px, `globals.css`) — every consumer of the CSS var (`instrument-bar.tsx`, `statusbar.tsx`, `cockpit-shell.tsx`'s own `marginLeft`) picks it up automatically. The Assistant view is also the one deliberate exception to `cockpit-shell.tsx`'s usual left-anchored, width-capped content wrapper — `isConversation` swaps it for `mx-auto w-full` so the chat centers using the full available width on an ultrawide monitor instead of centering inside an already-left-shifted box.
  - `statusbar.tsx` — same responsibility (footer counters + last event), rewritten to the new material/geometry.
- **`features/`** — same 22 Centers as before. `dashboard-view.tsx` was rebuilt from a 5-equal-StatCard grid into an asymmetric layout ordered by real operator priority (approvals that block → live event bus → missions in full → a permanent narrow vitals column) — see [ui-ux](../../../ui-ux/SKILL.md) for why that hierarchy, not a grid, is the point.
- **`hooks/`, `lib/`, `services/`, `types/`** — unchanged by the redesign; the dead files noted before HOS-080 (`lib/api.ts`, `lib/events.ts`, `hooks/use-runtime-events.ts`) are still dead, not yet removed.

## The Centers — still all real, 22 total

No change to the roster or the merge history (Memory absorbed Knowledge Graph + Alexandrie; Governance absorbed Policy) — see the previous audit findings, all still accurate. What changed is only the visual material every Center is built from.

**Verified individually after the redesign** (real backend, real data, live in browser): Dashboard, Governance, Execution. The other 19 inherit the same Tier-1/Tier-2 primitives but have not each been opened and checked individually — see [hermes/verification](../../verification/SKILL.md) on the difference between "shares the primitives" and "individually confirmed."

## Component scaffold adoption — still inconsistent, same Centers

The redesign did not change *which* Centers use the Tier-2 scaffold vs. hand-rolled `Card`/`Badge` layout — only what the scaffold itself looks like. Memory, Governance, Workspace, Health, Validation, Execution, Monitoring are still the fully-scaffolded examples to copy. This inconsistency is a real, still-open item, not something HOS-080 was scoped to fix.

## State management — unchanged, including the known bug

React Query (99 hooks in `use-api.ts`) + one Zustand store (`useCockpitStore`) — the redesign didn't touch state shape at all, only presentation. The `wsConnected`/`setWsConnected` dead-wiring bug (the Topbar's live/offline badge — now the InstrumentBar's status dot — is driven by real per-subsystem health data, not by this broken flag; the flag itself is still never set to `true` anywhere in the real app) is **still present**, unfixed by HOS-080. `DashboardView` and `EventsCenter` still each open their own independent WebSocket via `useWebSocket()`.

## Health status — real data available, not fully surfaced yet

`GET /api/v1/system/health` returns, honestly: `{"status", "services", "by_status": {"healthy": N, "unknown": M}, "unhealthy": [...], "silent": [...ids with no telemetry accessor at all...], "detail": {...per-subsystem status + message...}}`. Confirmed live (2026-08-10): 23 healthy, 12 "unknown" — and critically, **all 12 "unknown" are also listed in `silent`**, meaning zero subsystems are actually reporting a bad state; the 12 simply have no telemetry accessor wired yet (a real, documented architectural gap — see `backend-map.md`'s composition-root section). `services/client.ts`'s `normaliseStatus()` deliberately maps `"unknown"` to `"DEGRADED"` rather than `"HEALTHY"` (own comment: "ne pas mentir en annonçant HEALTHY" — don't lie by calling it healthy) — defensible, but it means the Dashboard's subsystem census currently cannot visually distinguish "genuinely degraded" from "not yet instrumented," which read as very different situations to an operator. Worth fixing with a distinct third visual state fed from the real `silent` array, rather than collapsing both into one amber signal.

## Build tooling gotchas — unchanged

Package manager ambiguity (pnpm + unused `bun.lock`) and the PostCSS config conflict (`postcss.config.js`, CommonJS/Tailwind-v3-style, matches what's actually installed; `postcss.config.mjs`, ESM/Tailwind-v4-style, `@tailwindcss/postcss` not installed) are both still present — HOS-080 did not touch build config beyond `tailwind.config.ts`'s token values. Confirmed during the redesign that a stale `.next` build cache can serve pre-redesign CSS after a token change — clear `frontend/.next` and restart the dev server if colours don't seem to update after editing `globals.css` or `tailwind.config.ts`.

## Testing — updated for the new components

Same vitest/jsdom setup. `__tests__/cockpit.test.ts` updated in HOS-080: the `Sidebar`/`Topbar` export checks were replaced with `Rail`/`InstrumentBar`/`CommandPalette` checks, plus a new test asserting every nav id in `nav-model.ts` is unique. 82/82 passing post-redesign. Coverage gap unchanged otherwise — still only 5 test files, still only 4 Centers with any dedicated test.

## API client layer — unchanged

No redesign-related changes to `services/client.ts` or `types/hermes.ts`. Still the pattern to follow for new endpoints: a typed method on the relevant domain client + a React Query hook in `use-api.ts`, with normalization for any real backend/frontend shape mismatch.
