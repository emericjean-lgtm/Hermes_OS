"use client";
import { useRuntimeDecisions } from "@/hooks/use-runtimes";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { BarChart3 } from "lucide-react";

const METRICS = [
  { key: "health_score", label: "Health", color: "#10b981" },
  { key: "reliability_score", label: "Reliability", color: "#6366f1" },
  { key: "performance_score", label: "Performance", color: "#f59e0b" },
  { key: "capability_score", label: "Capability", color: "#8b5cf6" },
  { key: "policy_score", label: "Policy", color: "#64748b" },
];

export default function RuntimeDecisionExplorer() {
  const { data: decisions } = useRuntimeDecisions();
  const d = decisions ?? [];

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
      <div className="flex items-center gap-2 mb-3"><BarChart3 size={16} className="text-[var(--color-accent)]" /><h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Decision Explorer</h3></div>
      {d.length === 0 ? (
        <p className="py-8 text-center text-xs text-[var(--color-text-muted)]">No decisions available</p>
      ) : (
        <>
          {d.map((dec) => (
            <div key={dec.runtime} className="mb-4 last:mb-0">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-[var(--color-text-primary)]">{dec.runtime}</span>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-[var(--color-accent)]">{dec.final_score}</span>
                  <span className="text-[10px] text-[var(--color-text-muted)]">confidence: {(dec.confidence * 100).toFixed(0)}%</span>
                </div>
              </div>
              <div style={{ height: 100 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={METRICS.map(m => ({ name: m.label, score: (dec as any)[m.key] ?? 0, fill: m.color }))} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" />
                    <XAxis type="number" domain={[0, 100]} tick={{ fill: "#64748b", fontSize: 9 }} />
                    <YAxis dataKey="name" type="category" tick={{ fill: "#64748b", fontSize: 9 }} width={70} />
                    <Tooltip contentStyle={{ background: "#1a1a24", border: "1px solid rgba(255,255,255,0.1)", fontSize: 11 }} />
                    <Bar dataKey="score" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-1 text-[10px] text-[var(--color-text-muted)]">{dec.reason}</p>
              {dec.circuit_penalty > 0 && <p className="text-[10px] text-[var(--color-danger)]">Circuit penalty: -{dec.circuit_penalty}</p>}
            </div>
          ))}
        </>
      )}
    </div>
  );
}
