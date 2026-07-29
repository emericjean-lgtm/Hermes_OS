"use client";

import { useAgentPerformance } from "@/hooks/use-agents";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, CartesianGrid, LineChart, Line } from "recharts";
import { BarChart3 } from "lucide-react";

const COLORS = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#64748b"];

export default function AgentPerformance() {
  const { data: perf, isLoading } = useAgentPerformance();

  if (isLoading) return <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4 animate-pulse"><div className="h-4 w-24 rounded bg-white/10 mb-3" /><div className="h-32 rounded bg-white/5" /></div>;
  if (!perf) return <div className="rounded-xl border border-dashed border-white/10 bg-[var(--color-bg-surface)] p-8 text-center"><BarChart3 size={32} className="mx-auto text-[var(--color-text-muted)]" /><p className="mt-2 text-sm text-[var(--color-text-muted)]">No performance data</p></div>;

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
      <div className="flex items-center gap-2 mb-3"><BarChart3 size={16} className="text-[var(--color-accent)]" /><h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Agent Performance</h3><span className="ml-auto text-xs text-[var(--color-success)]">{(perf.success_rate).toFixed(0)}% success</span></div>

      {perf.agent_durations.length > 0 && (
        <div className="mb-4">
          <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase mb-1">Duration by Agent</h4>
          <div style={{ height: 160 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={perf.agent_durations.filter(d => d.duration_ms > 0)}>
                <XAxis dataKey="agent" tick={{ fill: "#64748b", fontSize: 9 }} />
                <YAxis tick={{ fill: "#64748b", fontSize: 9 }} />
                <Tooltip contentStyle={{ background: "#1a1a24", border: "1px solid rgba(255,255,255,0.1)", fontSize: 11 }} formatter={(v) => `${(Number(v) / 1000).toFixed(1)}s`} />
                <Bar dataKey="duration_ms" fill="#6366f1" radius={[4,4,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        {perf.runtime_distribution.length > 0 && (
          <div>
            <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase mb-1">Runtimes</h4>
            <div style={{ height: 120 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={perf.runtime_distribution} dataKey="count" nameKey="runtime" cx="50%" cy="50%" outerRadius={40} innerRadius={20}>
                    {perf.runtime_distribution.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip contentStyle={{ background: "#1a1a24", border: "1px solid rgba(255,255,255,0.1)", fontSize: 11 }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="flex justify-center gap-2 text-[9px] text-[var(--color-text-muted)]">{perf.runtime_distribution.map((r, i) => <div key={r.runtime} className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{ backgroundColor: COLORS[i] }} />{r.runtime}</div>)}</div>
          </div>
        )}

        {perf.duration_histogram.length > 0 && (
          <div>
            <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase mb-1">Histogram</h4>
            <div style={{ height: 120 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={perf.duration_histogram}>
                  <XAxis dataKey="bucket" tick={{ fill: "#64748b", fontSize: 8 }} />
                  <YAxis tick={{ fill: "#64748b", fontSize: 8 }} />
                  <Bar dataKey="count" fill="#6366f1" radius={[4,4,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
