# Frontend map (full detail)

Grounded 2026-08-10 by direct code audit of `frontend/src/`. Next.js 15.1.0, React 19, TypeScript strict mode, Tailwind v3.4.16 (not v4 — see gotcha below).

## Convention docs — read, but thin

`frontend/CLAUDE.md` is one line, `@AGENTS.md` (a pure include). `frontend/AGENTS.md` is 6 lines, only a warning to check `node_modules/next/dist/docs/` before writing code — no real project conventions documented there. `frontend/README.md` is **stale, unmodified `create-next-app` boilerplate** (mentions editing `app/page.tsx`, which is really just a redirect; mentions the Geist font, which isn't what's actually loaded — that's Inter). None of the three describe the Centers, the design system, or state conventions — everything below comes from the real code, because no doc currently states it. This is itself the gap `hermes/development-rules` exists to fill.

## Structure

- **`app/`** — effectively one real page: `app/dashboard/page.tsx` renders `<CockpitShell />`. `app/page.tsx` just redirects there. `app/layout.tsx` hardcodes `<html className="dark">` and loads Inter via `next/font/google`. `app/providers.tsx` is **dead code** (a near-duplicate of the real one, different cache settings, imported nowhere).
- **`components/`** — `ui/card.tsx` (Tier 1 primitives: `Card`, `Badge`, `Beacon`, `StatCard`, `ProgressBar`, `Button`), `center-scaffold.tsx` (Tier 2 composition: `CenterHeader`, `StatGrid`, `Toolbar`, `AsyncPanel`, `PanelLoading`, `DataTable`, `CenterTabs`, `LiveBadge`), `cockpit-shell.tsx` (the shell), `sidebar.tsx`/`topbar.tsx`/`statusbar.tsx` (chrome), `center-boundary.tsx` (`CenterBoundary`, a real error-boundary isolating one Center's crash from the rest — added after this exact failure mode was reproduced multiple times), `confirm-action.tsx`, `providers.tsx` (the real, used React Query provider).
- **`features/`** — one directory per Center (see full list below), plus `dashboard` and `conversation`.
- **`hooks/`** — `use-api.ts` (848 lines, **99 exported React Query hooks**, one per backend capability), `use-store.ts` (the single Zustand store), `use-websocket.ts` (the real, used WS hook), `use-runtime-events.ts` (**dead code**, defined, never imported).
- **`lib/`** — both files **dead**: `lib/api.ts` (`streamChat`, superseded by `services/conversation-stream.ts`), `lib/events.ts` (`openEventStream`, superseded by `hooks/use-websocket.ts`).
- **`services/`** — `client.ts` (1205 lines, the real API client — see below), `conversation-stream.ts` (177 lines, the real NDJSON chat streamer).
- **`types/hermes.ts`** (840 lines) — every shared DTO, unusually well-commented with *why* each field is shaped the way it is (documents real backend mismatches found and fixed).

## The Centers — all real, 22 total

"Cockpit" is the shell (`CockpitShell`), not itself a Center — the sidebar's own footer literally reads "22 CENTERS". Confirmed real (calling actual backend hooks, not mock data) for all of: **Mission** (`features/missions/mission-center.tsx`), **Agent** (`features/agents/agent-center.tsx`), **Runtime** (`features/runtime/runtime-center.tsx`), **Memory** (`features/memory/memory-center.tsx` — a merge of three former screens: Memory/Knowledge Graph/Alexandrie, now three tabs), **Skills** (`features/skills/skills-center.tsx`), **Tools** (`features/tools/tools-center.tsx`), **Governance** (`features/governance/governance-center.tsx` — a merge of former Governance+Policy, now three tabs), **Dashboard**, **Assistant/Conversation**, **Models**, **Execution**, **Autonomous**, **Code Intelligence**, **Workspace**, **Security**, **Validation**, **Evolution**, **Health**, **Monitoring**, **Events**, **System**, **Deployment**.

Many carry in-code comments about a prior remediation pass (`deployment-center.tsx` explicitly notes it "was fabricated end to end" — invented specs/services/actions — before being rewired to real endpoints; similar notes on `autonomous-center.tsx`, `model-intelligence-center.tsx`, `conversation-center.tsx`). All checked and confirmed to currently call real hooks against real routes.

## Component scaffold adoption — inconsistent, know the good pattern

Two generations coexist. **Memory, Governance, Workspace, Health, Validation, Execution, Monitoring** fully use the Tier-2 scaffold (`AsyncPanel`/`StatGrid`/`Toolbar`/`DataTable`/`CenterTabs`) — **these are the pattern to copy when extending a Center**. Mission, Agent, Skills, Tools, Events, Autonomous, Security, System, Deployment, Evolution, Model Intelligence import only `CenterHeader` and hand-roll the rest against `Card`/`Badge` directly. Runtime and Code Intelligence use `CenterHeader`+`PanelLoading` only. Conversation is fully bespoke (neither tier).

## Design tokens & aesthetic

Real CSS custom properties in `app/globals.css` (`--hermes-cyan`, `--hermes-magenta`, `--hermes-violet`, `--hermes-green`, `--hermes-amber`, `--hermes-red`, `--hermes-blue`, plus bg/text/muted/dim), mirrored into `tailwind.config.ts`'s `theme.extend.colors.hermes` (a comment there notes this duplication is load-bearing — without it, `text-hermes-*` classes compile to nothing, so keep both in sync if you touch either). Color is explicitly semantic: cyan = system speaking, magenta = human decision point, green/amber/red = health, violet = autonomous activity. Look: "cyberpunk" — glassmorphism (`.glass`/`.glass-bright`), animated neon borders (`.neon-edge`, `.neon-edge-live`), corner brackets (`.bracket`), clipped corners (`.clip-corner*`), animated grid + drifting nebula background. `prefers-reduced-motion: reduce` is respected. **Dark-only** — no theme toggle, no `next-themes`, no `dark:` Tailwind variant used anywhere; the `dark` class on `<html>` is hardcoded and vestigial. Mono font (`JetBrains Mono, Fira Code, ...`) is declared in Tailwind config but **never actually loaded** (no `next/font`, no `@font-face`) — silently falls back to whatever monospace the OS provides. Animation via `framer-motion` (package name `framer-motion`, not `motion`).

## State management

**Server state**: TanStack React Query v5, all 99 hooks in `use-api.ts`. Two `QueryClient` configs exist; only `components/providers.tsx`'s is actually wired (`app/providers.tsx`'s is dead). **Global UI state**: one Zustand store, `useCockpitStore` (`hooks/use-store.ts`) — active view, nav-collapsed, live events (capped 200), selected mission/agent id. No persistence middleware. Zero React Context beyond `QueryClientProvider`.

**Known real bug, worth knowing before touching status indicators**: `wsConnected`/`setWsConnected` in the store are dead wiring — `setWsConnected` is called nowhere in the real app (only in a test), so the Topbar's "LIVE"/"OFFLINE" badge is permanently stuck on OFFLINE regardless of real connectivity. The actual working live-status indicators are separate: `DashboardView` and `EventsCenter` each open their **own independent** WebSocket via `useWebSocket()` and use that hook's own local state — not pooled, not connected to the Topbar badge.

## API client layer

`services/client.ts` (1205 lines) — 26 exported domain-client objects, hand-written, no OpenAPI codegen (despite the backend exposing `/openapi.json`), all funneled through one `fetchJSON<T>()`. DTOs in `types/hermes.ts` are manually kept in sync with real backend response shapes, with normalizers (`toMission()`, `toAgent()`, `unwrap()`) handling documented real mismatches — lowercase-on-the-wire enums needing `.toUpperCase()`, envelope-wrapped list responses, field renames. If you're adding a new endpoint's frontend client, follow this exact pattern (manual typed client + normalizer), not a new approach.

## Build tooling gotchas

Package manager ambiguity: `pnpm-lock.yaml` (the one actually used, per `packageManager: pnpm@10.0.0`) coexists with an unused `bun.lock`. **PostCSS config conflict**: both `postcss.config.js` (CommonJS, Tailwind v3 style — matches what's actually installed) and `postcss.config.mjs` (ESM, Tailwind v4 style — `@tailwindcss/postcss` is **not installed**) exist simultaneously; the `.js` one matches reality, the `.mjs` one looks like a stale template leftover. Not independently confirmed which one a real build picks when both are present — flag, don't assume, if this becomes relevant.

## Testing — real but thin

Vitest, `jsdom`, co-located `*.test.tsx` (except one file, `__tests__/cockpit.test.ts`). Only 5 test files total exist; 18 of 22 Centers have zero dedicated tests. No E2E tooling at all. The existing tests split into two kinds: `cockpit.test.ts` is mostly shallow "is this exported" smoke checks; the four feature-level tests (`model-picker`, `slash-commands`, `voice-input`, `code-intelligence-center`) are genuine, narrow regression tests each tied to a specific real bug that was fixed — that's the pattern worth following for new tests here, not the shallow smoke-check pattern.
