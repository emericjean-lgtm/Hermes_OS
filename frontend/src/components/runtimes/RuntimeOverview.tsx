"use client";
import { useRuntimeList, useRuntimeHealth } from "@/hooks/use-runtimes";
import { Cpu, CheckCircle, AlertTriangle, XCircle, Clock, BarChart3, Star, Zap } from "lucide-react";

function StatBox({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: string | number; color?: string }) {
  return <div className="rounded-lg bg-[var(--color-bg-base)]/50 p-3"><div className="flex items-center gap-1.5 text-[10px] text-[var(--color-text-muted)] mb-1">{icon}{label}</div><div className="text-lg font-semibold" style={color ? { color } : {}}>{value}</div></div>;
}

export default function RuntimeOverview() {
  const { data: runtimes } = useRuntimeList();
  const d = runtimes ?? [];
  const healthy = d.filter(r => r.status === "healthy").length;
  const degraded = d.filter(r => r.status === "degraded" || r.status === "unavailable").length;
  const avgLat = d.length ? d.reduce((a, r) => a + r.avg_latency_ms, 0) / d.length : 0;
  const best = [...d].sort((a, b) => b.reliability_score - a.reliability_score)[0];
  const mostUsed = [...d].sort((a, b) => b.executions - a.executions)[0];

  return <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4"><div className="flex items-center gap-2 mb-3"><Cpu size={16} className="text-[var(--color-accent)]" /><h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Runtime Overview</h3></div>
    <div className="grid grid-cols-4 gap-2">
      <StatBox icon={<Cpu size={12} />} label="Total" value={d.length} />
      <StatBox icon={<CheckCircle size={12} />} label="Healthy" value={healthy} color="var(--color-success)" />
      <StatBox icon={<AlertTriangle size={12} />} label="Degraded" value={degraded} color={degraded > 0 ? "var(--color-warning)" : undefined} />
      <StatBox icon={<Clock size={12} />} label="Avg Latency" value={`${(avgLat / 1000).toFixed(2)}s`} />
      <StatBox icon={<Star size={12} />} label="Most Reliable" value={best?.name ?? "—"} color="var(--color-success)" />
      <StatBox icon={<Zap size={12} />} label="Most Used" value={mostUsed?.name ?? "—"} color="var(--color-accent)" />
      <StatBox icon={<BarChart3 size={12} />} label="Best Score" value={best ? `${(best.reliability_score * 100).toFixed(0)}%` : "—"} color="var(--color-success)" />
      <StatBox icon={<XCircle size={12} />} label="Failures" value={d.reduce((a, r) => a + r.failures, 0)} color={d.reduce((a, r) => a + r.failures, 0) > 0 ? "var(--color-danger)" : undefined} />
    </div>
  </div>;
}
