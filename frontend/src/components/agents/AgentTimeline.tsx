"use client";

import { useAgentTimeline } from "@/hooks/use-agents";
import { Activity, CheckCircle, XCircle, AlertTriangle, RotateCcw, Play, Pause } from "lucide-react";

const EVENT_ICONS: Record<string, React.ReactNode> = {
  created: <Play size={12} className="text-[var(--color-accent)]" />,
  ready: <Activity size={12} className="text-[var(--color-accent)]" />,
  running: <Play size={12} className="text-[var(--color-accent)]" />,
  completed: <CheckCircle size={12} className="text-[var(--color-success)]" />,
  failed: <XCircle size={12} className="text-[var(--color-danger)]" />,
  cancelled: <XCircle size={12} className="text-[var(--color-text-muted)]" />,
  paused: <Pause size={12} className="text-[var(--color-warning)]" />,
  recovered: <RotateCcw size={12} className="text-[var(--color-success)]" />,
};

export default function AgentTimeline() {
  const { data: events, isLoading } = useAgentTimeline();

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
      <div className="flex items-center gap-2 mb-3">
        <Activity size={16} className="text-[var(--color-accent)]" />
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Agent Timeline</h3>
        {events && <span className="text-[10px] text-[var(--color-text-muted)]">({events.length})</span>}
      </div>
      <div className="max-h-64 space-y-1 overflow-y-auto">
        {!events || events.length === 0 ? (
          <p className="py-6 text-center text-xs text-[var(--color-text-muted)]">No events yet</p>
        ) : events.slice(0, 60).map((ev) => (
          <div key={ev.id} className="flex items-start gap-2 border-l-2 border-[var(--color-accent)] pl-3 py-1.5">
            {EVENT_ICONS[ev.type] ?? <Activity size={12} className="text-[var(--color-text-muted)]" />}
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] font-medium text-[var(--color-accent)]">{ev.agent_name}</span>
                <span className="text-[9px] text-[var(--color-text-muted)]">{ev.timestamp?.slice(11, 19)}</span>
              </div>
              <p className="text-[11px] text-[var(--color-text-primary)] truncate">{ev.message}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
