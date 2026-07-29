"use client";

import { useStatistics } from "@/hooks/use-dashboard";
import { BarChart3 } from "lucide-react";

interface StatItemProps {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
}

function StatItem({ label, value, sub, color }: StatItemProps) {
  return (
    <div className="rounded-lg bg-[var(--color-bg-base)]/50 p-3 transition-colors hover:bg-[var(--color-bg-base)]">
      <div className="text-xs text-[var(--color-text-muted)]">{label}</div>
      <div className="mt-1 text-lg font-semibold" style={color ? { color } : {}}>
        {value}
      </div>
      {sub && <div className="mt-0.5 text-[10px] text-[var(--color-text-muted)]">{sub}</div>}
    </div>
  );
}

export default function StatisticsCard() {
  const { data: stats, isLoading } = useStatistics();

  if (isLoading) {
    return (
      <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
        <div className="animate-pulse space-y-3">
          <div className="h-4 w-24 rounded bg-white/10" />
          <div className="grid grid-cols-2 gap-3">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-16 rounded bg-white/5" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!stats) return null;

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4 transition-colors hover:border-white/20">
      <div className="mb-3 flex items-center gap-2">
        <BarChart3 size={16} className="text-[var(--color-accent)]" />
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
          Statistics
        </h3>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <StatItem
          label="Missions"
          value={stats.missions?.total ?? 0}
          sub={`${stats.missions?.active ?? 0} active · ${stats.missions?.completed ?? 0} done`}
          color="var(--color-accent)"
        />
        <StatItem
          label="Agents"
          value={stats.agents?.total ?? 0}
          sub={`${stats.agents?.running ?? 0} running`}
          color="var(--color-success)"
        />
        <StatItem
          label="Runtimes"
          value={stats.runtimes?.total ?? 0}
          sub={`${stats.runtimes?.healthy ?? 0} healthy · ${stats.runtimes?.degraded ?? 0} degraded`}
          color="var(--color-warning)"
        />
        <StatItem
          label="Memory"
          value={stats.memory?.entries ?? 0}
          sub={`${Object.keys(stats.memory?.scopes ?? {}).length} scopes`}
        />
        <StatItem
          label="Skills"
          value={stats.skills?.registered ?? 0}
          sub={`${stats.skills?.loaded ?? 0} loaded`}
        />
        <StatItem
          label="Events"
          value={stats.events?.total ?? 0}
          color="var(--color-danger)"
        />
      </div>
    </div>
  );
}
