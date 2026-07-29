"use client";

import { useAgentStatistics } from "@/hooks/use-agents";
import { Bot, Activity, CheckCircle, XCircle, GitBranch, Cpu, BarChart3, Clock } from "lucide-react";

function StatBox({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: string | number; color?: string }) {
  return (
    <div className="rounded-lg bg-[var(--color-bg-base)]/50 p-3">
      <div className="flex items-center gap-1.5 text-[10px] text-[var(--color-text-muted)] mb-1">
        {icon}{label}
      </div>
      <div className="text-lg font-semibold" style={color ? { color } : {}}>{value}</div>
    </div>
  );
}

export default function AgentOverview() {
  const { data: stats, isLoading } = useAgentStatistics();

  if (isLoading) {
    return (
      <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
        <div className="animate-pulse grid grid-cols-4 gap-2">
          {[1,2,3,4,5,6,7,8].map(i => <div key={i} className="h-14 rounded bg-white/5" />)}
        </div>
      </div>
    );
  }

  if (!stats) return null;

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
      <div className="flex items-center gap-2 mb-3">
        <Bot size={16} className="text-[var(--color-accent)]" />
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Agent Overview</h3>
      </div>
      <div className="grid grid-cols-4 gap-2">
        <StatBox icon={<Bot size={12} />} label="Total" value={stats.total_agents} />
        <StatBox icon={<Activity size={12} />} label="Active" value={stats.active_agents} color="var(--color-accent)" />
        <StatBox icon={<CheckCircle size={12} />} label="Completed" value={stats.completed_agents} color="var(--color-success)" />
        <StatBox icon={<XCircle size={12} />} label="Failed" value={stats.failed_agents} color={stats.failed_agents > 0 ? "var(--color-danger)" : undefined} />
        <StatBox icon={<GitBranch size={12} />} label="Sub-Agents" value={stats.sub_agents} />
        <StatBox icon={<BarChart3 size={12} />} label="Success" value={`${stats.success_rate.toFixed(0)}%`} color={stats.success_rate >= 80 ? "var(--color-success)" : stats.success_rate >= 50 ? "var(--color-warning)" : "var(--color-danger)"} />
        <StatBox icon={<Clock size={12} />} label="Avg Duration" value={`${(stats.avg_duration_ms / 1000).toFixed(1)}s`} />
        <StatBox icon={<Cpu size={12} />} label="Runtimes" value={Object.keys(stats.runtime_distribution).length} />
      </div>
    </div>
  );
}
