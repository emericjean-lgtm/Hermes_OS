"use client";

import { useSystemStatistics } from "@/hooks/use-api";
import { useCockpitStore } from "@/hooks/use-store";

export function StatusBar() {
  const { data: stats } = useSystemStatistics();
  const { liveEvents } = useCockpitStore();

  if (!stats) return null;

  const items = [
    { label: "Missions", value: `${stats.missions_active || 0}/${stats.missions_total || 0}` },
    { label: "Agents", value: `${stats.agents_active || 0}/${stats.agents_total || 0}` },
    { label: "Runtimes", value: `${stats.runtimes_healthy || 0}/${stats.runtimes_total || 0}` },
    { label: "Memory", value: `${stats.memory_entries || 0}` },
    { label: "Events", value: `${liveEvents.length}` },
  ];

  return (
    <footer className="fixed left-56 right-0 bottom-0 z-30 h-7 border-t border-hermes-border bg-hermes-surface flex items-center px-6 gap-6">
      {items.map((item) => (
        <div key={item.label} className="flex items-center gap-1.5">
          <span className="text-[10px] text-hermes-muted font-mono uppercase">
            {item.label}
          </span>
          <span className="text-[10px] text-hermes-amber-bright font-mono">
            {item.value}
          </span>
        </div>
      ))}
      <div className="ml-auto text-[9px] text-hermes-muted font-mono">
        Hermes OS Cockpit
      </div>
    </footer>
  );
}
