"use client";

import { useAgent } from "@/hooks/use-agents";
import { Bot, Clock, Cpu, GitBranch, BarChart3, Activity, AlertTriangle, RotateCcw, Hash } from "lucide-react";

function DetailRow({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: string | number; color?: string }) {
  return (
    <div className="flex items-center justify-between rounded bg-[var(--color-bg-base)]/50 px-3 py-1.5">
      <div className="flex items-center gap-2"><span className="text-[var(--color-text-muted)]">{icon}</span><span className="text-xs text-[var(--color-text-muted)]">{label}</span></div>
      <span className="text-xs font-medium" style={color ? { color } : {}}>{value}</span>
    </div>
  );
}

interface AgentInspectorProps { agentId: string | null }

export default function AgentInspector({ agentId }: AgentInspectorProps) {
  const { data: agent, isLoading } = useAgent(agentId);

  if (!agentId) return (
    <div className="rounded-xl border border-dashed border-white/10 bg-[var(--color-bg-surface)] p-8 text-center">
      <Bot size={32} className="mx-auto text-[var(--color-text-muted)]" />
      <p className="mt-2 text-sm text-[var(--color-text-muted)]">Select an agent to inspect</p>
    </div>
  );

  if (isLoading) return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4 animate-pulse"><div className="h-4 w-32 rounded bg-white/10 mb-3" />{[1,2,3,4,5,6,7,8].map(i => <div key={i} className="h-7 rounded bg-white/5 mb-1" />)}</div>
  );

  if (!agent) return null;

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
      <div className="flex items-center gap-2 mb-3">
        <Bot size={16} className="text-[var(--color-accent)]" />
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">{agent.name}</h3>
        <span className="ml-auto text-xs uppercase" style={{ color: "var(--color-accent)" }}>{agent.state}</span>
      </div>

      <div className="space-y-1 mb-3">
        <DetailRow icon={<Cpu size={12} />} label="Runtime" value={agent.runtime} />
        <DetailRow icon={<Clock size={12} />} label="Duration" value={agent.duration_ms ? `${(agent.duration_ms / 1000).toFixed(1)}s` : "—"} />
        <DetailRow icon={<Hash size={12} />} label="Retries" value={agent.retries} color={agent.retries > 0 ? "var(--color-warning)" : undefined} />
        <DetailRow icon={<RotateCcw size={12} />} label="Fallback" value={agent.fallback_used ? "Yes" : "No"} color={agent.fallback_used ? "var(--color-warning)" : undefined} />
        <DetailRow icon={<Activity size={12} />} label="Progress" value={`${agent.progress}%`} />
      </div>

      {agent.error && <div className="mb-3 rounded bg-[var(--color-danger)]/10 px-3 py-2 text-xs text-[var(--color-danger)]">{agent.error}</div>}

      <div className="mb-3">
        <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase mb-1">Scores</h4>
        <DetailRow icon={<BarChart3 size={12} />} label="Reliability" value={`${(agent.reliability_score * 100).toFixed(0)}%`} color={agent.reliability_score >= 0.8 ? "var(--color-success)" : agent.reliability_score >= 0.5 ? "var(--color-warning)" : "var(--color-danger)"} />
        <DetailRow icon={<BarChart3 size={12} />} label="Performance" value={`${(agent.performance_score * 100).toFixed(0)}%`} color={agent.performance_score >= 0.8 ? "var(--color-success)" : "var(--color-warning)"} />
      </div>

      <div className="mb-3">
        <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase mb-1">Circuit & Fallback</h4>
        <DetailRow icon={<AlertTriangle size={12} />} label="Circuit Breaker" value={agent.circuit_breaker_count} color={agent.circuit_breaker_count > 0 ? "var(--color-danger)" : undefined} />
        <DetailRow icon={<RotateCcw size={12} />} label="Fallback Count" value={agent.fallback_count} color={agent.fallback_count > 0 ? "var(--color-warning)" : undefined} />
      </div>

      {agent.sub_agent_ids && agent.sub_agent_ids.length > 0 && (
        <div>
          <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase mb-1">Sub-Agents ({agent.sub_agent_ids.length})</h4>
          <div className="flex flex-wrap gap-1">{agent.sub_agent_ids.map(id => <span key={id} className="rounded bg-[var(--color-accent)]/10 px-1.5 py-0.5 text-[9px] text-[var(--color-accent)]">{id.slice(0, 8)}</span>)}</div>
        </div>
      )}

      {agent.state_history && agent.state_history.length > 0 && (
        <div className="mt-3">
          <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase mb-1">State History</h4>
          <div className="space-y-1 max-h-32 overflow-y-auto">
            {agent.state_history.slice(-8).map((h, i) => (
              <div key={i} className="flex items-center gap-1.5 text-[10px]">
                <span className="text-[var(--color-text-muted)]">{h.timestamp.slice(11, 19)}</span>
                <span className="text-[var(--color-accent)]">{h.from}</span>
                <span className="text-[var(--color-text-muted)]">→</span>
                <span className="text-[var(--color-accent)]">{h.to}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
