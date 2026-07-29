"use client";

import { useRef, useMemo, useState, useEffect } from "react";
import { useExecutionTimeline } from "@/hooks/use-execution";
import {
  Activity,
  PlayCircle,
  CheckCircle,
  XCircle,
  AlertTriangle,
  RotateCcw,
  SkipForward,
} from "lucide-react";

const EVENT_ICONS: Record<string, React.ReactNode> = {
  "execution.started": <PlayCircle size={12} className="text-[var(--color-accent)]" />,
  "task.ready": <Activity size={12} className="text-[var(--color-accent)]" />,
  "task.started": <PlayCircle size={12} className="text-[var(--color-accent)]" />,
  "task.completed": <CheckCircle size={12} className="text-[var(--color-success)]" />,
  "task.failed": <XCircle size={12} className="text-[var(--color-danger)]" />,
  "task.skipped": <SkipForward size={12} className="text-[var(--color-text-muted)]" />,
  "execution.fallback": <AlertTriangle size={12} className="text-[var(--color-warning)]" />,
  "execution.recovered": <RotateCcw size={12} className="text-[var(--color-success)]" />,
  "circuit.opened": <XCircle size={12} className="text-[var(--color-danger)]" />,
  "circuit.closed": <CheckCircle size={12} className="text-[var(--color-success)]" />,
};

const SEVERITY_COLORS: Record<string, string> = {
  ERROR: "border-l-[var(--color-danger)] bg-[var(--color-danger)]/5",
  WARNING: "border-l-[var(--color-warning)] bg-[var(--color-warning)]/5",
  INFO: "border-l-[var(--color-accent)]",
  DEBUG: "border-l-[var(--color-text-muted)]",
};

const FILTER_TYPES = ["all", "execution", "task", "circuit"] as const;

export default function ExecutionTimeline() {
  const { events, clearTimeline } = useExecutionTimeline(100);
  const [filter, setFilter] = useState<string>("all");
  const listRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  const filtered = useMemo(() => {
    if (filter === "all") return events;
    return events.filter((e) => e.type.startsWith(filter));
  }, [events, filter]);

  // Auto-scroll
  useEffect(() => {
    if (autoScroll && listRef.current) {
      listRef.current.scrollTop = 0;
    }
  }, [filtered.length, autoScroll]);

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity size={16} className="text-[var(--color-accent)]" />
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Timeline</h3>
          <span className="text-[10px] text-[var(--color-text-muted)]">({filtered.length})</span>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1 text-[10px] text-[var(--color-text-muted)]">
            <input type="checkbox" checked={autoScroll} onChange={() => setAutoScroll(!autoScroll)} className="accent-[var(--color-accent)]" />
            Auto-scroll
          </label>
          <div className="flex gap-1">
            {FILTER_TYPES.map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`rounded px-1.5 py-0.5 text-[9px] uppercase transition-colors ${
                  filter === f ? "bg-[var(--color-accent)]/15 text-[var(--color-accent)]" : "text-[var(--color-text-muted)] hover:bg-white/5"
                }`}
              >
                {f}
              </button>
            ))}
          </div>
          <button onClick={clearTimeline} className="text-[10px] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]">
            Clear
          </button>
        </div>
      </div>

      {/* Timeline */}
      <div ref={listRef} className="max-h-80 space-y-1 overflow-y-auto">
        {filtered.length === 0 && (
          <p className="py-6 text-center text-xs text-[var(--color-text-muted)]">No events yet</p>
        )}
        {filtered.slice(0, 80).map((event) => (
          <div
            key={event.id}
            className={`border-l-2 pl-3 py-1.5 transition-colors hover:bg-white/[0.02] ${SEVERITY_COLORS[event.severity ?? "INFO"] ?? "border-l-[var(--color-text-muted)]"}`}
          >
            <div className="flex items-center gap-1.5">
              {EVENT_ICONS[event.type] ?? <Activity size={12} className="text-[var(--color-text-muted)]" />}
              <span className="text-[10px] text-[var(--color-text-muted)]">
                {event.timestamp?.slice(11, 19) ?? "--:--:--"}
              </span>
              <span className="text-[9px] text-[var(--color-text-muted)] truncate max-w-[100px]">
                {event.source ?? event.type}
              </span>
            </div>
            <p className="mt-0.5 text-xs text-[var(--color-text-primary)]">{event.message}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
