"use client";
import { useRuntime } from "@/hooks/use-runtimes";
import { Cpu, CheckCircle, XCircle, BarChart3, Clock, Hash, Activity, AlertTriangle } from "lucide-react";

function Row({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: string | number; color?: string }) {
  return <div className="flex items-center justify-between rounded bg-[var(--color-bg-base)]/50 px-3 py-1.5"><div className="flex items-center gap-2"><span className="text-[var(--color-text-muted)]">{icon}</span><span className="text-xs text-[var(--color-text-muted)]">{label}</span></div><span className="text-xs font-medium" style={color ? { color } : {}}>{value}</span></div>;
}

interface Props { runtimeName: string | null; }

export default function RuntimeInspector({ runtimeName }: Props) {
  const { data: rt, isLoading } = useRuntime(runtimeName);
  if (!runtimeName) return <div className="rounded-xl border border-dashed border-white/10 bg-[var(--color-bg-surface)] p-8 text-center"><Cpu size={32} className="mx-auto text-[var(--color-text-muted)]" /><p className="mt-2 text-sm text-[var(--color-text-muted)]">Select a runtime to inspect</p></div>;
  if (isLoading) return <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4 animate-pulse"><div className="h-4 w-32 rounded bg-white/10 mb-3" />{[1,2,3,4,5,6,7,8].map(i => <div key={i} className="h-7 rounded bg-white/5 mb-1" />)}</div>;
  if (!rt) return null;

  return <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
    <div className="flex items-center gap-2 mb-3"><Cpu size={16} className="text-[var(--color-accent)]" /><h3 className="text-sm font-semibold text-[var(--color-text-primary)]">{rt.name}</h3><span className={`ml-auto text-xs ${rt.healthy ? "text-[var(--color-success)]" : "text-[var(--color-danger)]"}`}>{rt.healthy ? "HEALTHY" : "DEGRADED"}</span></div>
    <div className="space-y-1 mb-3">
      <Row icon={<Clock size={12} />} label="Status" value={rt.status.toUpperCase()} color={rt.status === "healthy" ? "var(--color-success)" : "var(--color-warning)"} />
      <Row icon={<Hash size={12} />} label="Version" value={rt.version ?? "—"} />
      <Row icon={<Activity size={12} />} label="Latency" value={`${(rt.avg_latency_ms / 1000).toFixed(2)}s`} />
      <Row icon={<BarChart3 size={12} />} label="Reliability" value={`${(rt.reliability_score * 100).toFixed(0)}%`} color={rt.reliability_score >= 0.9 ? "var(--color-success)" : rt.reliability_score >= 0.7 ? "var(--color-warning)" : "var(--color-danger)"} />
      <Row icon={<BarChart3 size={12} />} label="Performance" value={`${(rt.performance_score * 100).toFixed(0)}%`} />
      <Row icon={<CheckCircle size={12} />} label="Success Rate" value={`${rt.success_rate.toFixed(1)}%`} color={rt.success_rate >= 90 ? "var(--color-success)" : "var(--color-warning)"} />
      <Row icon={<XCircle size={12} />} label="Failures" value={rt.failures} color={rt.failures > 0 ? "var(--color-danger)" : undefined} />
      <Row icon={<AlertTriangle size={12} />} label="Executions" value={rt.executions} />
    </div>
    {rt.capabilities && <div className="mb-3"><h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase mb-1">Capabilities</h4><div className="flex flex-wrap gap-1">{rt.capabilities.map(c => <span key={c} className="rounded-full bg-[var(--color-accent)]/10 px-1.5 py-0.5 text-[9px] text-[var(--color-accent)]">{c}</span>)}</div></div>}
    {rt.type && <Row icon={<Cpu size={12} />} label="Type" value={rt.type} />}
    {rt.last_decision && <div className="mt-3"><h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase mb-1">Last Decision</h4><Row icon={<Activity size={12} />} label="Score" value={rt.last_decision.final_score} color="var(--color-accent)" /><p className="mt-1 text-[10px] text-[var(--color-text-muted)]">{rt.last_decision.reason}</p></div>}
  </div>;
}
