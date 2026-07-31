"use client";

import { useSystemHealth } from "@/hooks/use-api";
import { useCockpitStore } from "@/hooks/use-store";

export function Topbar() {
  const { data: health } = useSystemHealth();
  const { wsConnected } = useCockpitStore();

  const statusColor =
    health?.status === "HEALTHY"
      ? "bg-hermes-green"
      : health?.status === "DEGRADED"
      ? "bg-hermes-amber"
      : "bg-hermes-red";

  return (
    <header className="fixed left-56 right-0 top-0 z-30 h-12 border-b border-hermes-border bg-hermes-surface/95 backdrop-blur-sm flex items-center justify-between px-6">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span
            className={`w-2 h-2 rounded-full ${statusColor} animate-pulse`}
          />
          <span className="text-xs text-hermes-muted font-mono uppercase tracking-wider">
            {health?.status || "UNKNOWN"}
          </span>
        </div>
        <span className="text-hermes-border">|</span>
        <span className="text-xs text-hermes-muted font-mono">
          Uptime: {formatUptime(health?.uptime_seconds || 0)}
        </span>
      </div>

      <div className="flex items-center gap-4">
        {/* WebSocket indicator */}
        <div className="flex items-center gap-1.5">
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              wsConnected ? "bg-hermes-green" : "bg-hermes-red"
            }`}
          />
          <span className="text-[10px] text-hermes-muted font-mono">
            WS
          </span>
        </div>

        {/* Version */}
        <span className="text-[10px] text-hermes-muted font-mono">
          {health?.version || "—"}
        </span>
      </div>
    </header>
  );
}

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}
