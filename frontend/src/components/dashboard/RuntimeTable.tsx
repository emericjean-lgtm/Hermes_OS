"use client";

import { useRuntimes } from "@/hooks/use-dashboard";
import { Cpu, CheckCircle, AlertTriangle, XCircle } from "lucide-react";

const STATUS_ICON: Record<string, React.ReactNode> = {
  healthy: <CheckCircle size={14} className="text-[var(--color-success)]" />,
  degraded: <AlertTriangle size={14} className="text-[var(--color-warning)]" />,
  unhealthy: <XCircle size={14} className="text-[var(--color-danger)]" />,
};

function ScoreBar({ value, label }: { value: number; label: string }) {
  const color =
    value >= 80
      ? "var(--color-success)"
      : value >= 50
        ? "var(--color-warning)"
        : "var(--color-danger)";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-white/10">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${Math.min(value, 100)}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-[10px] text-[var(--color-text-muted)]">{label}</span>
    </div>
  );
}

export default function RuntimeTable() {
  const { data: runtimes, isLoading, isError } = useRuntimes();

  if (isLoading) {
    return (
      <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
        <div className="animate-pulse space-y-3">
          <div className="h-4 w-24 rounded bg-white/10" />
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-10 rounded bg-white/5" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
        <p className="text-sm text-[var(--color-danger)]">Failed to load runtimes</p>
      </div>
    );
  }

  if (!runtimes || runtimes.length === 0) {
    return (
      <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
        <div className="flex items-center gap-2">
          <Cpu size={16} className="text-[var(--color-text-muted)]" />
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Runtimes</h3>
        </div>
        <p className="mt-3 text-xs text-[var(--color-text-muted)]">No runtimes registered.</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4 transition-colors hover:border-white/20">
      <div className="mb-3 flex items-center gap-2">
        <Cpu size={16} className="text-[var(--color-accent)]" />
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
          Runtimes ({runtimes.length})
        </h3>
      </div>

      {/* Table - responsive */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-white/5 text-left text-[10px] text-[var(--color-text-muted)]">
              <th className="pb-2 pr-4 font-medium">Name</th>
              <th className="pb-2 pr-4 font-medium">Status</th>
              <th className="hidden pb-2 pr-4 font-medium sm:table-cell">Reliability</th>
              <th className="hidden pb-2 pr-4 font-medium md:table-cell">Performance</th>
              <th className="pb-2 pr-4 font-medium">Success</th>
              <th className="pb-2 text-right font-medium">Executions</th>
            </tr>
          </thead>
          <tbody>
            {runtimes.map((rt) => (
              <tr key={rt.name} className="border-b border-white/5 last:border-0 hover:bg-white/[0.02]">
                <td className="py-2.5 pr-4 font-medium text-[var(--color-text-primary)]">
                  {rt.name}
                </td>
                <td className="py-2.5 pr-4">
                  {STATUS_ICON[rt.status] ?? STATUS_ICON.unhealthy}
                </td>
                <td className="hidden py-2.5 pr-4 sm:table-cell">
                  <ScoreBar value={rt.reliability_score * 100} label={`${(rt.reliability_score * 100).toFixed(0)}%`} />
                </td>
                <td className="hidden py-2.5 pr-4 md:table-cell">
                  <ScoreBar value={rt.performance_score * 100} label={`${(rt.performance_score * 100).toFixed(0)}%`} />
                </td>
                <td className="py-2.5 pr-4">
                  <span
                    className={
                      rt.success_rate >= 90
                        ? "text-[var(--color-success)]"
                        : rt.success_rate >= 70
                          ? "text-[var(--color-warning)]"
                          : "text-[var(--color-danger)]"
                    }
                  >
                    {rt.success_rate.toFixed(1)}%
                  </span>
                </td>
                <td className="py-2.5 text-right text-[var(--color-text-muted)]">
                  {rt.executions}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
