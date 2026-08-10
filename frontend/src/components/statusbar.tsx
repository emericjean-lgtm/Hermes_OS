"use client";

import { useSystemStatistics } from "@/hooks/use-api";
import { useCockpitStore } from "@/hooks/use-store";

/** The footer readout.
 *
 *  A row of counters and the last event off the bus. Deliberately quiet: it
 *  is the one strip on screen that never demands attention, so anything
 *  that *does* move here (the event ticker) is genuinely new information.
 *
 *  It renders unconditionally with em-dashes when data has not arrived —
 *  an earlier version returned null until the first response, which made
 *  the whole page reflow on load. */
export function StatusBar() {
  const { data: stats } = useSystemStatistics();
  const { liveEvents } = useCockpitStore();

  const n = (v: unknown) => (typeof v === "number" ? v : null);
  const pair = (a: unknown, b: unknown) => {
    const x = n(a);
    const y = n(b);
    return x === null && y === null ? null : ([x ?? 0, y ?? 0] as const);
  };

  const readouts: { label: string; pair?: readonly [number, number] | null; single?: string }[] = [
    { label: "MSN", pair: pair(stats?.missions_active, stats?.missions_total) },
    { label: "AGT", pair: pair(stats?.agents_active, stats?.agents_total) },
    { label: "RT", pair: pair(stats?.runtimes_healthy, stats?.runtimes_total) },
    { label: "MEM", single: n(stats?.memory_entries)?.toLocaleString("fr-FR") ?? "––" },
    { label: "EVT", single: liveEvents.length.toString() },
  ];

  const last = liveEvents[0];

  return (
    <footer
      className="fixed right-0 bottom-0 z-30 flex items-center gap-0
        border-t border-hermes-border bg-hermes-bg-deep/80 backdrop-blur-xl"
      style={{ left: "var(--rail-w)", height: "var(--foot-h)" }}
    >
      <div className="pointer-events-none absolute top-0 left-0 h-px w-full
        bg-gradient-to-r from-hermes-border-bright/50 to-transparent" />

      {readouts.map((r) => (
        <div
          key={r.label}
          className="flex items-baseline gap-1.5 px-3.5 h-full border-r border-hermes-border/60
            shrink-0 first:pl-5"
          style={{ alignItems: "center" }}
        >
          <span className="tech-label !text-[8.5px]">{r.label}</span>
          {r.pair ? (
            <span className="num text-[10.5px]">
              <span className="text-hermes-sodium">{r.pair[0]}</span>
              <span className="text-hermes-dim">/{r.pair[1]}</span>
            </span>
          ) : (
            <span className="num text-[10.5px] text-hermes-muted">{r.single ?? "––"}</span>
          )}
        </div>
      ))}

      {/* The only moving part down here. */}
      <div className="flex items-center gap-2.5 min-w-0 flex-1 px-4">
        {last ? (
          <>
            <span className="h-1 w-1 rounded-full bg-hermes-steel shrink-0" />
            <span className="num text-[9.5px] text-hermes-steel uppercase shrink-0 tracking-[0.1em]">
              {last.type}
            </span>
            <span className="text-[10px] text-hermes-dim truncate">{last.source}</span>
          </>
        ) : (
          <span className="text-[10px] text-hermes-dim/70">Aucun événement reçu</span>
        )}
      </div>

      <div className="flex items-center gap-2 px-5 shrink-0 border-l border-hermes-border/60 h-full">
        <span className="tech-label !text-[8.5px]">HERMES OS</span>
      </div>
    </footer>
  );
}
