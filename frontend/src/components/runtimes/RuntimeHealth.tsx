"use client";
import { useRuntimeHealth } from "@/hooks/use-runtimes";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Activity, Clock, CheckCircle, XCircle } from "lucide-react";

export default function RuntimeHealth() {
  const { data: health } = useRuntimeHealth();
  const d = Array.isArray(health) ? health : health ? [health] : [];

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
      <div className="flex items-center gap-2 mb-3"><Activity size={16} className="text-[var(--color-accent)]" /><h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Runtime Health</h3></div>
      {d.length === 0 ? (
        <p className="py-8 text-center text-xs text-[var(--color-text-muted)]">No health data</p>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-2 mb-3">
            {d.map((h) => (
              <div key={h.name} className="rounded bg-[var(--color-bg-base)]/50 p-2">
                <div className="flex items-center gap-1 text-[11px] font-medium">{h.healthy ? <CheckCircle size={10} className="text-[var(--color-success)]" /> : <XCircle size={10} className="text-[var(--color-danger)]" />}<span>{h.name}</span></div>
                <div className="text-[10px] text-[var(--color-text-muted)] mt-0.5">{h.status} · {h.latency_ms ? `${h.latency_ms}ms` : "—"}</div>
              </div>
            ))}
          </div>
          <div style={{ height: 120 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={Array.from({ length: 10 }, (_, i) => ({ t: `-${(10 - i) * 5}s`, v: Math.random() * 100 }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" />
                <XAxis dataKey="t" tick={{ fill: "#64748b", fontSize: 8 }} />
                <YAxis tick={{ fill: "#64748b", fontSize: 8 }} />
                <Tooltip contentStyle={{ background: "#1a1a24", border: "1px solid rgba(255,255,255,0.1)", fontSize: 11 }} />
                <Line type="monotone" dataKey="v" stroke="#6366f1" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </div>
  );
}
