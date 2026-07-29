"use client";

import { useExecutionPerformance } from "@/hooks/use-execution";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  LineChart,
  Line,
  CartesianGrid,
} from "recharts";
import { BarChart3 } from "lucide-react";

const COLORS = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#64748b", "#8b5cf6"];

function StatChip({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="rounded-md bg-[var(--color-bg-base)]/50 px-3 py-2">
      <div className="text-[10px] text-[var(--color-text-muted)]">{label}</div>
      <div className="text-sm font-semibold" style={color ? { color } : {}}>{value}</div>
    </div>
  );
}

export default function PerformanceCharts() {
  const { data: perf, isLoading } = useExecutionPerformance();
  const data = perf;

  if (isLoading) {
    return (
      <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
        <div className="animate-pulse space-y-3">
          <div className="h-4 w-24 rounded bg-white/10" />
          <div className="h-32 rounded bg-white/5" />
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="rounded-xl border border-dashed border-white/10 bg-[var(--color-bg-surface)] p-8 text-center">
        <BarChart3 size={32} className="mx-auto text-[var(--color-text-muted)]" />
        <p className="mt-2 text-sm text-[var(--color-text-muted)]">No performance data</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
      <div className="mb-3 flex items-center gap-2">
        <BarChart3 size={16} className="text-[var(--color-accent)]" />
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Performance</h3>
      </div>

      {/* Stats row */}
      <div className="mb-4 grid grid-cols-3 gap-2">
        <StatChip label="Avg Latency" value={`${(data.avg_latency_ms / 1000).toFixed(2)}s`} />
        <StatChip label="Wait Time" value={`${(data.wait_time_ms / 1000).toFixed(2)}s`} />
        <StatChip label="Retries" value={data.retries} color={data.retries > 0 ? "var(--color-warning)" : undefined} />
        <StatChip label="Fallbacks" value={data.fallbacks} color={data.fallbacks > 0 ? "var(--color-warning)" : undefined} />
        <StatChip label="Circuit Breaker" value={data.circuit_breaker_count} color={data.circuit_breaker_count > 0 ? "var(--color-danger)" : undefined} />
        <StatChip label="Runtimes" value={data.runtime_usage.length} />
      </div>

      {/* Task durations bar chart */}
      {data.task_durations.length > 0 && (
        <div className="mb-4">
          <h4 className="mb-2 text-[10px] font-medium text-[var(--color-text-muted)] uppercase">Task Durations</h4>
          <div style={{ height: 200 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.task_durations}>
                <XAxis dataKey="task" tick={{ fill: "#64748b", fontSize: 10 }} />
                <YAxis tick={{ fill: "#64748b", fontSize: 10 }} unit="s" />
                <Tooltip
                  contentStyle={{ background: "#1a1a24", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, fontSize: 12 }}
                  formatter={(value) => [`${(Number(value) / 1000).toFixed(1)}s`, "Duration"]}
                />
                <Bar dataKey="duration_ms" fill="#6366f1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Runtime usage pie + timeline row */}
      <div className="grid grid-cols-2 gap-4">
        {/* Runtime usage */}
        {data.runtime_usage.length > 0 && (
          <div>
            <h4 className="mb-2 text-[10px] font-medium text-[var(--color-text-muted)] uppercase">Runtime Usage</h4>
            <div style={{ height: 150 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={data.runtime_usage}
                    dataKey="count"
                    nameKey="runtime"
                    cx="50%"
                    cy="50%"
                    outerRadius={50}
                    innerRadius={25}
                  >
                    {data.runtime_usage.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: "#1a1a24", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, fontSize: 12 }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="flex justify-center gap-3 text-[10px] text-[var(--color-text-muted)]">
              {data.runtime_usage.map((r, i) => (
                <div key={r.runtime} className="flex items-center gap-1">
                  <span className="h-2 w-2 rounded-full" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                  <span>{r.runtime}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Timeline */}
        {data.timeline.length > 0 && (
          <div>
            <h4 className="mb-2 text-[10px] font-medium text-[var(--color-text-muted)] uppercase">Latency Trend</h4>
            <div style={{ height: 150 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data.timeline}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" />
                  <XAxis dataKey="time" tick={{ fill: "#64748b", fontSize: 9 }} />
                  <YAxis tick={{ fill: "#64748b", fontSize: 9 }} />
                  <Tooltip
                    contentStyle={{ background: "#1a1a24", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, fontSize: 12 }}
                  />
                  <Line type="monotone" dataKey="value" stroke="#6366f1" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
