"use client";
import { useRuntimeMetrics } from "@/hooks/use-runtimes";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, CartesianGrid, LineChart, Line } from "recharts";
import { BarChart3 } from "lucide-react";

const COLORS = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#64748b", "#8b5cf6"];

export default function RuntimePerformance() {
  const { data: metrics } = useRuntimeMetrics();
  const d = Array.isArray(metrics) ? metrics : metrics ? [metrics] : [];

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
      <div className="flex items-center gap-2 mb-3"><BarChart3 size={16} className="text-[var(--color-accent)]" /><h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Runtime Performance</h3></div>
      {d.length === 0 ? (
        <p className="py-8 text-center text-xs text-[var(--color-text-muted)]">No performance data</p>
      ) : (
        <>
          <div className="mb-3">
            <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase mb-1">Success Rate by Runtime</h4>
            <div style={{ height: 140 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={d.map(m => ({ name: m.name, success: m.success_rate }))}>
                  <XAxis dataKey="name" tick={{ fill: "#64748b", fontSize: 9 }} />
                  <YAxis domain={[0, 100]} tick={{ fill: "#64748b", fontSize: 9 }} />
                  <Tooltip contentStyle={{ background: "#1a1a24", border: "1px solid rgba(255,255,255,0.1)", fontSize: 11 }} formatter={(v) => `${Number(v).toFixed(1)}%`} />
                  <Bar dataKey="success" fill="#10b981" radius={[4,4,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase mb-1">Executions</h4>
              <div style={{ height: 100 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={d.map(m => ({ name: m.name, value: m.executions }))} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={35} innerRadius={15}>
                      {d.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                    </Pie>
                    <Tooltip contentStyle={{ background: "#1a1a24", border: "1px solid rgba(255,255,255,0.1)", fontSize: 11 }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div>
              <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase mb-1">Scores</h4>
              <div style={{ height: 100 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={d.map(m => ({ name: m.name, reliability: (m.reliability_score ?? 0) * 100, performance: (m.performance_score ?? 0) * 100 }))} layout="vertical">
                    <XAxis type="number" domain={[0, 100]} tick={{ fill: "#64748b", fontSize: 8 }} />
                    <YAxis dataKey="name" type="category" tick={{ fill: "#64748b", fontSize: 8 }} width={50} />
                    <Tooltip contentStyle={{ background: "#1a1a24", border: "1px solid rgba(255,255,255,0.1)", fontSize: 11 }} />
                    <Bar dataKey="reliability" fill="#6366f1" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
