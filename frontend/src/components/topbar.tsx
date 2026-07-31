"use client";

import { motion } from "framer-motion";
import { useSystemHealth } from "@/hooks/use-api";
import { useCockpitStore } from "@/hooks/use-store";
import { Beacon } from "@/components/ui/card";
import { Activity, Clock, Wifi, WifiOff } from "lucide-react";

/** Bandeau d'état permanent. Il ne montre que ce qui est réellement mesuré
 *  côté backend (santé agrégée, uptime, version, lien WebSocket) — pas de
 *  jauge décorative alimentée par une valeur inventée. */
export function Topbar() {
  const { data: health } = useSystemHealth();
  const { wsConnected, navCollapsed } = useCockpitStore();

  const status = health?.status ?? "UNKNOWN";
  const tone =
    status === "HEALTHY"
      ? { text: "text-hermes-green", glow: "text-glow-green", beacon: "green" as const }
      : status === "DEGRADED"
      ? { text: "text-hermes-amber", glow: "text-glow-amber", beacon: "amber" as const }
      : status === "UNKNOWN"
      ? { text: "text-hermes-muted", glow: "", beacon: "cyan" as const }
      : { text: "text-hermes-red", glow: "text-glow-red", beacon: "red" as const };

  const subsystems = health?.subsystems ? Object.values(health.subsystems) : [];
  const healthy = subsystems.filter((s) => s?.status === "HEALTHY").length;

  return (
    <motion.header
      animate={{ left: navCollapsed ? 68 : 232 }}
      transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
      className="fixed right-0 top-0 z-30 h-14 flex items-center justify-between gap-4 px-6
        border-b border-hermes-border glass"
    >
      {/* Filet lumineux en pied de bandeau. */}
      <div className="absolute bottom-0 left-0 h-px w-full bg-gradient-to-r
        from-hermes-cyan/40 via-hermes-violet/20 to-transparent" />

      <div className="flex items-center gap-5 min-w-0">
        {/* État global */}
        <div className={`flex items-center gap-2 ${tone.text}`}>
          <Beacon tone={tone.beacon} />
          <span className={`text-[11px] font-mono font-bold uppercase tracking-[0.14em] ${tone.glow}`}>
            {status}
          </span>
        </div>

        <Divider />

        {/* Sous-systèmes sains / total */}
        {subsystems.length > 0 && (
          <>
            <div className="flex items-center gap-1.5">
              <Activity size={12} className="text-hermes-cyan/60" />
              <span className="text-[11px] font-mono text-hermes-muted tabular-nums">
                <span className="text-hermes-text font-semibold">{healthy}</span>
                <span className="text-hermes-dim">/{subsystems.length}</span>
                <span className="text-hermes-dim ml-1">sous-systèmes</span>
              </span>
            </div>
            <Divider />
          </>
        )}

        {/* Uptime */}
        <div className="flex items-center gap-1.5">
          <Clock size={12} className="text-hermes-cyan/60" />
          <span className="text-[11px] font-mono text-hermes-muted tabular-nums">
            {formatUptime(health?.uptime_seconds ?? 0)}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-4 shrink-0">
        {/* Lien temps réel */}
        <div
          className={`flex items-center gap-1.5 px-2 py-1 rounded border clip-corner-sm
            transition-all duration-300 ${
              wsConnected
                ? "border-hermes-green/40 bg-hermes-green/10 text-hermes-green shadow-glow-green"
                : "border-hermes-red/40 bg-hermes-red/10 text-hermes-red"
            }`}
        >
          {wsConnected ? <Wifi size={11} /> : <WifiOff size={11} />}
          <span className="text-[10px] font-mono font-bold tracking-wider">
            {wsConnected ? "LIVE" : "OFFLINE"}
          </span>
        </div>

        <span className="text-[10px] text-hermes-dim font-mono tracking-wider">
          {health?.version ? `v${health.version}` : "—"}
        </span>
      </div>
    </motion.header>
  );
}

function Divider() {
  return <span className="h-3.5 w-px bg-hermes-border" />;
}

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (d > 0) return `${d}j ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}
