"use client";

import { motion } from "framer-motion";
import { useSystemStatistics } from "@/hooks/use-api";
import { useCockpitStore } from "@/hooks/use-store";

/** Bandeau de pied : compteurs agrégés + dernier événement reçu.
 *
 *  `if (!stats) return null` faisait disparaître toute la barre tant que la
 *  requête n'avait pas abouti, ce qui décalait la mise en page au chargement.
 *  Elle reste désormais en place et affiche des tirets. */
export function StatusBar() {
  const { data: stats } = useSystemStatistics();
  const { liveEvents, navCollapsed } = useCockpitStore();

  const n = (v: unknown) => (typeof v === "number" ? v : null);
  const pair = (a: unknown, b: unknown) => {
    const x = n(a);
    const y = n(b);
    return x === null && y === null ? "—" : `${x ?? 0}/${y ?? 0}`;
  };

  const items = [
    { label: "Missions", value: pair(stats?.missions_active, stats?.missions_total) },
    { label: "Agents", value: pair(stats?.agents_active, stats?.agents_total) },
    { label: "Runtimes", value: pair(stats?.runtimes_healthy, stats?.runtimes_total) },
    { label: "Mémoire", value: n(stats?.memory_entries)?.toString() ?? "—" },
    { label: "Événements", value: liveEvents.length.toString() },
  ];

  const last = liveEvents[0];

  return (
    <motion.footer
      animate={{ left: navCollapsed ? 68 : 232 }}
      transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
      className="fixed right-0 bottom-0 z-30 h-8 flex items-center gap-5 px-6
        border-t border-hermes-border glass"
    >
      <div className="absolute top-0 left-0 h-px w-full bg-gradient-to-r
        from-transparent via-hermes-cyan/25 to-transparent" />

      {items.map((item) => (
        <div key={item.label} className="flex items-center gap-1.5 shrink-0">
          <span className="text-[9px] text-hermes-dim font-mono uppercase tracking-[0.12em]">
            {item.label}
          </span>
          <span className="text-[10px] text-hermes-cyan font-mono font-semibold tabular-nums">
            {item.value}
          </span>
        </div>
      ))}

      {/* Dernier événement — la seule zone qui bouge en continu. */}
      {last && (
        <div className="flex items-center gap-2 min-w-0 flex-1 ml-2">
          <span className="h-3 w-px bg-hermes-border shrink-0" />
          <span className="text-[9px] text-hermes-violet font-mono uppercase shrink-0">
            {last.type}
          </span>
          <span className="text-[9px] text-hermes-dim font-mono truncate">
            {last.source}
          </span>
        </div>
      )}

      <div className="ml-auto text-[9px] text-hermes-dim font-mono tracking-wider shrink-0">
        HERMES OS
      </div>
    </motion.footer>
  );
}
