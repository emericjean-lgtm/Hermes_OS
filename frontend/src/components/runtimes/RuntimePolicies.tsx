"use client";
import { useRuntimePolicies } from "@/hooks/use-runtimes";
import { Shield, CheckCircle, XCircle } from "lucide-react";

export default function RuntimePolicies() {
  const { data: policies } = useRuntimePolicies();
  const d = policies ?? [];

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
      <div className="flex items-center gap-2 mb-3"><Shield size={16} className="text-[var(--color-accent)]" /><h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Runtime Policies</h3></div>
      {d.length === 0 ? (
        <p className="py-8 text-center text-xs text-[var(--color-text-muted)]">No policies defined</p>
      ) : (
        <div className="space-y-2">
          {d.map(p => (
            <div key={p.id} className="rounded-lg border border-white/5 bg-[var(--color-bg-base)]/50 p-3">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-[var(--color-text-primary)]">{p.name}</span>
                  {p.enabled ? <CheckCircle size={10} className="text-[var(--color-success)]" /> : <XCircle size={10} className="text-[var(--color-text-muted)]" />}
                </div>
                <span className="text-[10px] text-[var(--color-text-muted)]">P{p.priority}</span>
              </div>
              <p className="text-[10px] text-[var(--color-text-muted)] mb-1">{p.description}</p>
              <div className="flex items-center gap-2 text-[10px]">
                <span className="text-[var(--color-text-muted)]">Preference:</span>
                <span className="font-medium text-[var(--color-text-primary)]">{p.preference}</span>
              </div>
              {p.rules.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {p.rules.map((r, i) => (
                    <span key={i} className="rounded bg-[var(--color-accent)]/10 px-1.5 py-0.5 text-[9px] text-[var(--color-accent)]">
                      {r.field} {r.operator} {String(r.value)}
                    </span>
                  ))}
                </div>
              )}
              {p.runtimes_allowed.length > 0 && <div className="mt-1 flex flex-wrap gap-1"><span className="text-[9px] text-[var(--color-success)]">Allowed:</span>{p.runtimes_allowed.map(r => <span key={r} className="text-[9px] text-[var(--color-text-muted)]">{r}</span>)}</div>}
              {p.runtimes_denied.length > 0 && <div className="mt-1 flex flex-wrap gap-1"><span className="text-[9px] text-[var(--color-danger)]">Denied:</span>{p.runtimes_denied.map(r => <span key={r} className="text-[9px] text-[var(--color-danger)]">{r}</span>)}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
