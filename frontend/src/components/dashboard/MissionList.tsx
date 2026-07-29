"use client";

import { useMissions } from "@/hooks/use-dashboard";
import { Target, Play, Pause, XCircle } from "lucide-react";
import type { Mission } from "@/types/mission-control";

const STATUS_COLOR: Record<string, string> = {
  COMPLETED: "var(--color-success)",
  RUNNING: "var(--color-accent)",
  FAILED: "var(--color-danger)",
  PAUSED: "var(--color-warning)",
  CANCELLED: "var(--color-text-muted)",
  CREATED: "var(--color-text-muted)",
  PLANNING: "var(--color-warning)",
  READY: "var(--color-accent)",
};

function ProgressBar({ value }: { value: number }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
      <div
        className="h-full rounded-full bg-[var(--color-accent)] transition-all duration-500"
        style={{ width: `${Math.min(value, 100)}%` }}
      />
    </div>
  );
}

export default function MissionList() {
  const { data: missions, isLoading, isError } = useMissions();

  if (isLoading) {
    return (
      <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
        <div className="animate-pulse space-y-3">
          <div className="h-4 w-24 rounded bg-white/10" />
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-12 rounded bg-white/5" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
        <p className="text-sm text-[var(--color-danger)]">Failed to load missions</p>
      </div>
    );
  }

  if (!missions || missions.length === 0) {
    return (
      <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
        <div className="flex items-center gap-2">
          <Target size={16} className="text-[var(--color-text-muted)]" />
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Missions</h3>
        </div>
        <p className="mt-3 text-xs text-[var(--color-text-muted)]">
          No missions yet. Create one to get started.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4 transition-colors hover:border-white/20">
      <div className="mb-3 flex items-center gap-2">
        <Target size={16} className="text-[var(--color-accent)]" />
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
          Missions ({missions.length})
        </h3>
      </div>

      <div className="space-y-2">
        {missions.slice(0, 10).map((mission) => (
          <div
            key={mission.id}
            className="rounded-lg border border-white/5 bg-[var(--color-bg-base)]/50 p-3 transition-colors hover:border-white/10"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ backgroundColor: STATUS_COLOR[mission.status] ?? "var(--color-text-muted)" }}
                  />
                  <span className="truncate text-sm font-medium text-[var(--color-text-primary)]">
                    {mission.title}
                  </span>
                </div>
                <div className="mt-1 flex items-center gap-3 text-[10px] text-[var(--color-text-muted)]">
                  <span>{mission.status}</span>
                  {mission.priority && <span className="uppercase">{mission.priority}</span>}
                  {mission.runtime && <span>{mission.runtime}</span>}
                  {mission.duration_ms != null && (
                    <span>{(mission.duration_ms / 1000).toFixed(1)}s</span>
                  )}
                </div>
              </div>

              {/* Actions */}
              <div className="flex shrink-0 gap-1">
                {mission.status === "RUNNING" && (
                  <span className="rounded bg-[var(--color-accent)]/10 px-1.5 py-0.5 text-[10px] text-[var(--color-accent)]">
                    <Play size={12} className="inline" /> Active
                  </span>
                )}
              </div>
            </div>

            {/* Progress bar */}
            {mission.progress > 0 && (
              <div className="mt-2">
                <ProgressBar value={mission.progress} />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
