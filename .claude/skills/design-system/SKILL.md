---
name: design-system
description: Check for an existing component, token, or pattern before building a new one in Hermes OS's frontend — the "SODIUM" design system. Use before creating any new UI component, adding a color/spacing value, or building a new Center's layout.
---

# Design System — Check Before You Build

The question this skill exists to force, every time: **does this already exist?** Hermes OS's frontend has a real, shared system — building a one-off instead of reusing or extending it is how a 22-Center app ends up with 22 different layouts, which is exactly the fragmentation this system was built to prevent (see its own in-code doc-comment stating that intent directly).

As of HOS-080 the system carries a specific visual identity — codenamed **SODIUM** — chosen deliberately to avoid the generic AI-dashboard look (cyan/magenta neon, glow on every hover, uniform rounding). See the contract at the bottom of this file before introducing anything that looks like that default.

## Before creating a new component, check in order

1. **Does a primitive already cover this?** `components/ui/card.tsx` — `Card`, `Badge` (7 variants), `Beacon` (pulsing status dot), `StatCard` (a gauge readout with pointer-tracked spotlight depth), `ProgressBar` (a segmented 24-cell meter; the fill is sodium and only the **leading lit segment** carries the health tint — see "Health at the edge" below — invertible for "high is bad" meters), `Button` (4 variants; the fill enters from the left on hover and the press depresses 1px without scaling). Most low-level visual needs are already here.
2. **Does the Center-composition tier already cover this?** `components/center-scaffold.tsx` — `CenterHeader`, `StatGrid`, `Toolbar`, `AsyncPanel` (the loading/error/empty/content pattern — use this rather than hand-rolling those four states again), `PanelLoading`, `DataTable<T>`, `CenterTabs<T>`, `LiveBadge`. This tier exists specifically so a new Center doesn't need its own bespoke layout logic.
3. **Does an existing token already express this value?** Colour, in `app/globals.css`'s CSS custom properties. **Use the semantic names for new work**: `--hermes-sodium` (the one warm accent — system speaking, every interactive affordance), `--hermes-glacier` (cold, a human decision point), `--hermes-steel` (autonomous activity), `--hermes-arc`/`--hermes-gold`/`--hermes-alarm` (the health scale: good/caution/bad). The old names (`cyan`/`magenta`/`violet`/`green`/`amber`/`red`) still resolve — they're aliases kept for markup that hasn't been revisited — but they now point at the SODIUM values, not their old literal hex codes; don't read the class name as a colour guarantee. **Both `globals.css` and `tailwind.config.ts` must stay in sync** — the Tailwind mirror is what makes `text-hermes-*` classes compile to anything at all.
4. **Does a similar Center already solve this exact layout problem?** Memory and Governance Centers are the current best examples — both fully built on the Tier-2 scaffold. If extending or building a Center, look at one of these first, not an older hand-rolled one.

Only build new if none of the above genuinely fits — and if you do, consider whether the new thing belongs in the shared component tier (if it's likely to be reused) rather than living locally in one Center's file.

## Type

Three roles, all actually loaded via `next/font/google` in `app/layout.tsx` (a pre-HOS-080 bug had one of these declared in Tailwind config but never loaded, so it silently fell back to the OS default — verify a new font actually reaches a `<Fonts .../>` call, not just a config entry, before trusting it renders). **Chakra Petch** (`.display` utility, `--font-chakra`) — numerals, screen titles, the wordmark; type that should feel stamped, not typed. **Barlow** (default body face, `--font-barlow`). **IBM Plex Mono** (`.num` utility, `--font-plex`, also sets tabular figures) — every id, telemetry value, and code block.

## Geometry and texture

Chamfered corners (`.clip-corner` / `.clip-corner-sm` / `.clip-notch`) replace uniform rounding — vary the chamfer deliberately (tighter on dense cells, wider on hero panels), don't default to one radius everywhere. `.room-grain` and `.room-vignette` (mounted once in `app/layout.tsx`, above the whole app) are what keep large flat panels from reading as sterile vector fills — don't disable or duplicate them per-Center.

## Health at the edge (HOS-197)

The health scale fills **marks**, not surfaces. A meter's body is sodium; its
leading lit segment — and only that segment — takes the arc/gold/alarm tint,
with the glow reserved for it too. This is Direction C of the retained design
canvas (`.design/cockpit/Sodium.dc.html`), and it is a measurement, not a
preference: on the running Dashboard on 2026-08-27, forty-one green elements
faced thirteen sodium ones. Because almost everything is healthy almost all
the time, a health-filled meter made the screen green, and one more green
told you nothing. A red has to stay a rupture; it is not one if it is merely
the third value of a ramp you read every day.

The exception is a surface whose subject **is** health — the Dashboard's
35-cell subsystem census, where a single red cell among the green is the
entire point. Health colours the value there because health is the value.
Ask which of the two you have before reaching for the scale.

## The room follows the cursor (HOS-197)

`globals.css`'s `body::before`/`::after` read `--room-mx`/`--room-my`, written
on mousemove by `components/room-halo.tsx` (mounted once in the shell): the
sodium pool tracks the pointer, the glacier counter-wash mirrors it through
the viewport centre, and the engineering grid's mask follows, so the lattice
only resolves where the light falls. Both variables have real fixed fallbacks
in the CSS, so the room reads correctly before any JS runs. Don't re-implement
this per-Center and don't set those variables from anywhere else.

## Live data, honestly rendered

The signature pattern for anything showing a live/operational metric: `components/telemetry-trace.tsx`'s canvas oscilloscope holds a flat baseline when a reading is genuinely unavailable, rather than interpolating or inventing motion to keep the picture busy. See the contract's data-integrity rule below — this isn't a style choice, it's load-bearing for a cockpit whose whole premise is that a displayed value is a measured value.

## SODIUM design contract

A change that introduces any of the left column, without a specific and explicit reason tied to the task at hand, is very likely reintroducing the generic-AI look this system was deliberately built away from — treat it as a stop-and-check, not a shrug.

| ❌ Don't reach for | ✅ Use instead |
|---|---|
| Cyan/magenta/violet as literal new colour choices | The semantic tokens — `sodium`/`glacier`/`steel`/`arc`/`gold`/`alarm` |
| A second or third "accent" colour competing with sodium | One dominant accent; everything else is the health scale or a deliberately rare cold counterpoint |
| Glow/shadow on hover as a default for every element | Reserve glow for genuinely live/active state (`.neon-edge-live`, a running process) — see [ui-ux](../ui-ux/SKILL.md) on keeping "live" meaningful |
| Uniform `rounded-xl`/`rounded-lg` | `.clip-corner`/`.clip-corner-sm`, varied deliberately |
| A new font not loaded through `next/font` in `app/layout.tsx` | Chakra Petch (display) / Barlow (interface) / IBM Plex Mono (data) — extend this trio before adding a fourth |
| An interpolated, randomized, or count-up-from-zero value standing in for a real measurement, even briefly | Render the real value directly; if data is missing, show it as missing (an em-dash, a flat baseline) — see `hermes/verification`'s "never fabricate a result" |
| A purple-to-blue "AI gradient" hero, symmetric radial glow centred on the viewport, or a flat sterile panel with no texture | The room's actual light source (a sodium pool, off-centre and cursor-tracked, per `globals.css`'s `body::before` and `room-halo.tsx`) + `.room-grain`/`.room-vignette` |
| The health scale filling a meter's whole body, so a healthy screen is a green screen | Sodium carries the measure; the health tint sits on the leading segment only — unless health genuinely *is* the value (the subsystem census) |
| A press state that scales the control down | A 1px depress — an instrument button sinks, it doesn't shrink |
| A brand-new visual language for one Center | The existing Tier-1/Tier-2 primitives — extend them if they're missing something, don't route around them |

This contract describes the current, real state of `app/globals.css`/`tailwind.config.ts` — if a deliberate future redesign changes the direction, update this table in the same change, not after.
