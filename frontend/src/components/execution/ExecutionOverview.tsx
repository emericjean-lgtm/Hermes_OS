"use client";

import { useExecutionOverview } from "@/hooks/use-execution";
import { Activity, Clock, Cpu, Bot, ListChecks, AlertCircle } from "lucide-react";

const STATE_COLORS: Record<string, string> = {
  IDLE: "var(--color-text-muted)",
  INITIALIZING: "var(--color-warning)",
  RUNNING: "var(--color-accent)",
  WAITING: "var(--color-warning)",
  PAUSED: "var(--color-warning)",
  RECOVERING: "var(--color-danger)",
  COMPLETED: "var(--color-success)",
  FAILED: "var(--color-danger)",
  CANCELLED: "var(--color-text-muted)",
};

function StatBox({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: string | number; color?: string }) {
  return (
    <div className="rounded-lg bg-[var(--color-bg-base)]/50 p-3">
      <div className="flex items-center gap-1.5 text-[10px] text-[var(--color-text-muted)] mb-1">
        {icon}
        <span>{label}</span>
      </div>
      <div className="text-lg font-semibold" style={color ? { color } : {}}>{value}</div>
    </div>
  );
}

export default function ExecutionOverview() {
  const { data: overview, isLoading } = useExecutionOverview();

  if (isLoading) {
    return (
      <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
        <div className="animate-pulse space-y-3">
          <div className="h-4 w-32 rounded bg-white/10" />
          <div className="grid grid-cols-3 gap-3">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="h-14 rounded bg-white/5" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!overview) {
    return (
      <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-8 text-center">
        <Activity size={32} className="mx-auto text-[var(--color-text-muted)]" />
        <p className="mt-2 text-sm text-[var(--color-text-muted)]">No active execution</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4 transition-colors hover:border-white/20">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity size={16} className="text-[var(--color-accent)]" />
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Execution Overview</h3>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="h-2 w-2 rounded-full"
            style={{ backgroundColor: STATE_COLORS[overview.state] ?? "var(--color-text-muted)" }}
          />
          <span className="text-xs font-medium" style={{ color: STATE_COLORS[overview.state] }}>
            {overview.state}
          </span>
        </div>
      </div>

      {/* Mission title */}
      {overview.mission_title && (
        <p className="mb-3 text-xs text-[var(--color-text-muted)]">{overview.mission_title}</p>
      )}

      {/* Progress bar */}
      <div className="mb-4">
        <div className="flex items-center justify-between text-xs text-[var(--color-text-muted)] mb-1">
          <span>Progress</span>
          <span>{overview.progress}%</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-white/10">
          <div
            className="h-full rounded-full bg-[var(--color-accent)] transition-all duration-500"
            style={{ width: `${Math.min(overview.progress, 100)}%` }}
          />
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-3 gap-2">
        <StatBox icon={<Clock size={12} />} label="Duration" value={`${(overview.duration_ms / 1000).toFixed(0)}s`} />
        <StatBox icon={<Cpu size={12} />} label="Runtime" value={overview.runtime ?? "Auto"} />
        <StatBox icon={<Bot size={12} />} label="Agents" value={overview.active_agents} />
        <StatBox icon={<ListChecks size={12} />} label="Done" value={`${overview.completed_tasks}/${overview.total_tasks}`} />
        <StatBox
          icon={<AlertCircle size={12} />}
          label="Failed"
          value={overview.failed_tasks}
          color={overview.failed_tasks > 0 ? "var(--color-danger)" : undefined}
        />
        <StatBox icon={<ListChecks size={12} />} label="Remaining" value={overview.remaining_tasks} />
      </div>
    </div>
  );
}
