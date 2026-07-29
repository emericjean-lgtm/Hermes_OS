"use client";

import { useStatus } from "@/hooks/use-dashboard";
import { useEvents } from "@/hooks/use-events";

export default function StatusBar() {
  const { data: status } = useStatus();
  const { connectionState } = useEvents();

  const statusColor =
    status?.status === "HEALTHY"
      ? "var(--color-success)"
      : status?.status === "DEGRADED"
        ? "var(--color-warning)"
        : "var(--color-danger)";

  const wsColor =
    connectionState === "open"
      ? "var(--color-success)"
      : connectionState === "connecting"
        ? "var(--color-warning)"
        : "var(--color-danger)";

  const wsLabel =
    connectionState === "open"
      ? "Live"
      : connectionState === "connecting"
        ? "Connecting…"
        : "Disconnected";

  return (
    <footer className="flex h-7 items-center justify-between border-t border-white/10 bg-[var(--color-bg-surface)] px-4 text-[11px] text-[var(--color-text-muted)]">
      {/* Left */}
      <div className="flex items-center gap-4">
        <span className="hidden sm:inline">Hermes OS</span>
        <span className="hidden md:inline">v{status?.version ?? "—"}</span>
      </div>

      {/* Center */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ backgroundColor: statusColor }}
          />
          <span>{status?.status ?? "—"}</span>
        </div>
        <span className="hidden sm:inline">
          Uptime: {status?.uptime ? `${Math.floor(status.uptime / 60)}m` : "—"}
        </span>
      </div>

      {/* Right */}
      <div className="flex items-center gap-1.5">
        <span
          className="h-1.5 w-1.5 rounded-full"
          style={{ backgroundColor: wsColor }}
        />
        <span>{wsLabel}</span>
      </div>
    </footer>
  );
}
