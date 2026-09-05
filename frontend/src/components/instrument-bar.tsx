"use client";

import { useSystemHealth, useResourceStatus } from "@/hooks/use-api";
import { useCockpitStore } from "@/hooks/use-store";
import { navLabel, navGroupOf } from "@/components/nav-model";
import { TelemetryTrace } from "@/components/telemetry-trace";
import { useOperateur } from "@/hooks/use-operateur";
import { Search, Thermometer } from "lucide-react";
import { vramPourcent } from "@/lib/format";

/** The instrument bar.
 *
 *  Replaces the old topbar. Three zones, left to right: where you are, what
 *  the machine is doing right now, and how to move. The middle zone is the
 *  point — VRAM and RAM are the constraints this product actually lives
 *  under (a 16GB card running local models), so they are permanently on
 *  screen as live traces rather than buried three clicks deep in a Center.
 *
 *  Everything here is measured. Where a reading is genuinely unavailable it
 *  renders as "––" and the trace holds a flat baseline; nothing is
 *  interpolated or invented to keep the picture moving. */
export function InstrumentBar({ onOpenPalette }: { onOpenPalette: () => void }) {
  const { data: health } = useSystemHealth();
  const { data: res } = useResourceStatus();
  const { activeView } = useCockpitStore();
  const operateur = useOperateur();

  const status = health?.status ?? "UNKNOWN";
  const tone =
    status === "HEALTHY"
      ? { text: "text-hermes-arc", dot: "bg-hermes-arc", label: "NOMINAL" }
      : status === "DEGRADED"
      ? { text: "text-hermes-gold", dot: "bg-hermes-gold", label: "DÉGRADÉ" }
      : status === "UNKNOWN"
      ? { text: "text-hermes-dim", dot: "bg-hermes-dim", label: "INCONNU" }
      : { text: "text-hermes-alarm", dot: "bg-hermes-alarm", label: "CRITIQUE" };

  // A-15 : `null` couvre desormais deux cas — pas de carte, et
  // carte dont aucune sonde n'a lu l'occupation. Les deux doivent
  // s'afficher comme absents, jamais comme 0 %.
  const vramPct = vramPourcent(res?.gpu);
  const ramPct = typeof res?.ram?.usage_pct === "number" ? res.ram.usage_pct : null;
  const temp = res?.gpu?.temperature_celsius ?? null;

  const subsystems = health?.subsystems ? Object.values(health.subsystems) : [];
  const healthy = subsystems.filter((s) => s?.status === "HEALTHY").length;

  return (
    <header
      className="fixed right-0 top-0 z-30 flex items-stretch
        border-b border-hermes-border bg-hermes-bg-deep/75 backdrop-blur-xl
        transition-[left] duration-200 ease-out"
      style={{ left: "var(--rail-w)", height: "var(--bar-h)" }}
    >
      {/* Lit underside — the bar catches the sodium source the same way the
          rail does, so the two read as one lit assembly. */}
      <div className="pointer-events-none absolute bottom-0 left-0 h-px w-full
        bg-gradient-to-r from-hermes-sodium/45 via-hermes-border-bright/35 to-transparent" />

      {/* ── Zone 1 — position ── */}
      <div className="flex items-center gap-3 pl-5 pr-4 shrink-0 min-w-0">
        <div className="min-w-0">
          <div className="tech-label leading-none">{navGroupOf(activeView) || "HERMES OS"}</div>
          <div className="display text-[15px] leading-tight text-hermes-text truncate mt-1">
            {navLabel(activeView)}
          </div>
        </div>
      </div>

      <Seam />

      {/* ── Zone 2 — the machine, live ──
          The two constraints that actually bind this deployment. */}
      <div className="hidden lg:flex items-center gap-5 px-5 shrink-0">
        <TelemetryTrace label="VRAM" value={vramPct} color="#ff9436" />
        <TelemetryTrace label="RAM" value={ramPct} color="#5eb8e8" width={104} />
        {temp !== null && (
          <div className="flex items-center gap-1.5">
            <Thermometer size={11} className="text-hermes-dim" />
            <span
              className={`num text-[10.5px] tabular-nums ${
                temp >= 90 ? "text-hermes-alarm" : temp >= 85 ? "text-hermes-gold" : "text-hermes-muted"
              }`}
            >
              {Math.round(temp)}°C
            </span>
          </div>
        )}
      </div>

      <div className="flex-1 min-w-0" />

      {/* ── Zone 3 — state and command ── */}
      <div className="flex items-center gap-4 px-5 shrink-0">
        {subsystems.length > 0 && (
          <div className="hidden md:flex items-baseline gap-1.5">
            <span className="tech-label">SOUS-SYST</span>
            <span className="num text-[11px] text-hermes-text">{healthy}</span>
            <span className="num text-[11px] text-hermes-dim">/{subsystems.length}</span>
          </div>
        )}

        {/* Le badge de l'opérateur (HOS-197) — « une couleur, un état,
            partout où il est lisible » (`.design/cockpit/Main.dc.html`).
            Volontairement pas gardé par `ONGLETS_AVEC_OPERATEUR` comme la
            figure elle-même : la figure a besoin de place et serait du
            bruit sur un écran de référence (agents, mémoire, gouvernance…),
            mais ce badge tient dans une barre d'instruments et c'est
            justement sur ces écrans-là qu'on veut encore savoir, d'un
            coup d'œil, si une mission travaille pendant qu'on regarde
            autre chose. */}
        <div
          className="hidden sm:flex items-center gap-2 clip-corner-sm border px-2.5 py-1"
          style={{
            borderColor: `color-mix(in srgb, ${operateur.teinte} 34%, transparent)`,
            background: `color-mix(in srgb, ${operateur.teinte} 8%, transparent)`,
          }}
          title={operateur.signal}
        >
          <span
            className="h-[5px] w-[5px] shrink-0"
            style={{ background: operateur.teinte, boxShadow: `0 0 8px ${operateur.teinte}` }}
          />
          <span className="num text-[10px] tracking-[0.1em]" style={{ color: operateur.teinte }}>
            {operateur.libelle.toUpperCase()}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span className={`relative flex h-1.5 w-1.5 ${tone.dot}`}>
            <span className={`absolute inline-flex h-full w-full ${tone.dot} opacity-60 animate-ping`} />
          </span>
          <span className={`num text-[10px] tracking-[0.16em] ${tone.text}`}>{tone.label}</span>
        </div>

        {/* The command affordance is a real control, labelled with its own
            shortcut, not a decorative search box that does nothing. */}
        <button
          onClick={onOpenPalette}
          className="group flex items-center gap-2 pl-2.5 pr-2 py-1.5 clip-corner-sm
            border border-hermes-border text-hermes-dim
            hover:text-hermes-text hover:border-hermes-border-bright
            hover:bg-hermes-elevated/60 transition-all"
        >
          <Search size={11} strokeWidth={1.9} />
          <span className="hidden xl:inline text-[11px]">Aller à…</span>
          <kbd className="num text-[9px] px-1 py-0.5 border border-hermes-border
            text-hermes-dim group-hover:border-hermes-border-bright transition-colors">
            ⌘K
          </kbd>
        </button>
      </div>
    </header>
  );
}

/** A machined seam rather than a 1px divider — two hairlines with a gap,
 *  the way panels actually meet on an instrument. */
function Seam() {
  return (
    <div className="hidden lg:flex items-center shrink-0" aria-hidden="true">
      <span className="h-full w-px bg-hermes-border" />
      <span className="h-full w-px bg-hermes-bg-deep" />
      <span className="h-full w-px bg-hermes-border/60" />
    </div>
  );
}
