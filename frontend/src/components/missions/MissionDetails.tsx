"use client";

import { useMission, useMissionPlan } from "@/hooks/use-missions";
import { MISSION_STATUS_COLORS } from "@/types/mission-control";
import {
  Target,
  Clock,
  Cpu,
  Brain,
  Puzzle,
  Activity,
  BookOpen,
  BarChart3,
} from "lucide-react";

interface MissionDetailsProps {
  missionId: string | null;
}

function DetailRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between rounded-md bg-[var(--color-bg-base)]/50 px-3 py-2">
      <div className="flex items-center gap-2">
        <span className="text-[var(--color-text-muted)]">{icon}</span>
        <span className="text-xs text-[var(--color-text-muted)]">{label}</span>
      </div>
      <span className="text-xs font-medium text-[var(--color-text-primary)]">{value}</span>
    </div>
  );
}

export default function MissionDetails({ missionId }: MissionDetailsProps) {
  const { data: mission, isLoading } = useMission(missionId);
  const { data: plan } = useMissionPlan(missionId);

  if (!missionId) {
    return (
      <div className="flex h-full items-center justify-center rounded-xl border border-dashed border-white/10 bg-[var(--color-bg-surface)] p-8">
        <div className="text-center">
          <Target size={32} className="mx-auto text-[var(--color-text-muted)]" />
          <p className="mt-3 text-sm text-[var(--color-text-muted)]">
            Select a mission to view details
          </p>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
        <div className="animate-pulse space-y-3">
          <div className="h-5 w-32 rounded bg-white/10" />
          <div className="h-3 w-48 rounded bg-white/10" />
          <div className="space-y-2">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-8 rounded bg-white/5" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!mission) return null;

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
      {/* Header */}
      <div className="mb-4 flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: MISSION_STATUS_COLORS[mission.status] }}
            />
            <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">{mission.title}</h3>
          </div>
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            {mission.description ?? "No description"}
          </p>
        </div>
        <span className="rounded-full bg-[var(--color-accent)]/10 px-2 py-0.5 text-[10px] text-[var(--color-accent)]">
          {mission.status}
        </span>
      </div>

      {/* Progress */}
      <div className="mb-4">
        <div className="flex items-center justify-between text-xs text-[var(--color-text-muted)] mb-1">
          <span>Progress</span>
          <span>{mission.progress}%</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-white/10">
          <div
            className="h-full rounded-full bg-[var(--color-accent)] transition-all duration-500"
            style={{ width: `${Math.min(mission.progress, 100)}%` }}
          />
        </div>
      </div>

      {/* Stats grid */}
      <div className="space-y-1">
        <DetailRow icon={<BarChart3 size={13} />} label="Priority" value={mission.priority} />
        <DetailRow icon={<Cpu size={13} />} label="Runtime" value={mission.runtime ?? "Auto"} />
        <DetailRow icon={<Clock size={13} />} label="Duration" value={mission.duration_ms ? `${(mission.duration_ms / 1000).toFixed(1)}s` : "—"} />
        <DetailRow icon={<Activity size={13} />} label="Created" value={new Date(mission.created_at).toLocaleDateString()} />
      </div>

      {/* Plan info */}
      {plan && (
        <div className="mt-4 space-y-1">
          <h4 className="text-xs font-medium text-[var(--color-text-muted)] mb-2">Execution Plan</h4>
          <DetailRow icon={<Brain size={13} />} label="Tasks" value={plan.nodes.length} />
          <DetailRow icon={<Puzzle size={13} />} label="Edges" value={plan.edges.length} />
          <DetailRow icon={<BookOpen size={13} />} label="Est. Duration" value={`${(plan.nodes.reduce((acc, n) => acc + (n.estimated_ms ?? 0), 0) / 1000).toFixed(0)}s`} />
        </div>
      )}

      {/* Error */}
      {mission.error && (
        <div className="mt-4 rounded-md bg-[var(--color-danger)]/10 px-3 py-2 text-xs text-[var(--color-danger)]">
          {mission.error}
        </div>
      )}
    </div>
  );
}
