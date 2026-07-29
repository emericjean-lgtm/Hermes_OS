"use client";

import { useEvents } from "@/hooks/use-events";
import { useDashboardStore } from "@/store/dashboard-store";
import { Activity, AlertTriangle, Info, AlertCircle, XCircle } from "lucide-react";
import type { TimelineEvent } from "@/types/mission-control";

const SEVERITY_ICON: Record<string, React.ReactNode> = {
  DEBUG: <Info size={12} className="text-[var(--color-text-muted)]" />,
  INFO: <Info size={12} className="text-[var(--color-accent)]" />,
  WARNING: <AlertTriangle size={12} className="text-[var(--color-warning)]" />,
  ERROR: <AlertCircle size={12} className="text-[var(--color-danger)]" />,
  CRITICAL: <XCircle size={12} className="text-[var(--color-danger)]" />,
};

const SEVERITY_COLOR: Record<string, string> = {
  DEBUG: "border-l-[var(--color-text-muted)]",
  INFO: "border-l-[var(--color-accent)]",
  WARNING: "border-l-[var(--color-warning)]",
  ERROR: "border-l-[var(--color-danger)]",
  CRITICAL: "border-l-[var(--color-danger)]",
};

const FILTERS = [null, "INFO", "WARNING", "ERROR", "CRITICAL"] as const;

function EventRow({ event }: { event: TimelineEvent }) {
  return (
    <div
      className={`border-l-2 pl-3 py-1.5 transition-colors hover:bg-white/[0.02] ${SEVERITY_COLOR[event.severity] ?? "border-l-[var(--color-text-muted)]"}`}
    >
      <div className="flex items-center gap-1.5">
        {SEVERITY_ICON[event.severity] ?? <Info size={12} className="text-[var(--color-text-muted)]" />}
        <span className="text-[10px] text-[var(--color-text-muted)]">
          {event.timestamp?.slice(11, 19) ?? "--:--:--"}
        </span>
        <span className="text-[10px] uppercase text-[var(--color-text-muted)]">{event.source}</span>
      </div>
      <p className="mt-0.5 text-xs text-[var(--color-text-primary)] line-clamp-2">
        {event.message}
      </p>
    </div>
  );
}

export default function EventTimeline() {
  const { events, connectionState } = useEvents();
  const { eventSeverityFilter, setEventSeverityFilter } = useDashboardStore();

  const filtered = eventSeverityFilter
    ? events.filter((e) => e.severity === eventSeverityFilter)
    : events;

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4 transition-colors hover:border-white/20">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity size={16} className="text-[var(--color-accent)]" />
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
            Live Events
          </h3>
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              connectionState === "open"
                ? "bg-[var(--color-success)]"
                : connectionState === "connecting"
                  ? "bg-[var(--color-warning)]"
                  : "bg-[var(--color-danger)]"
            }`}
          />
        </div>

        {/* Filters */}
        <div className="flex gap-1">
          {FILTERS.map((f) => (
            <button
              key={f ?? "all"}
              onClick={() => setEventSeverityFilter(f)}
              className={`rounded px-1.5 py-0.5 text-[10px] transition-colors ${
                eventSeverityFilter === f
                  ? "bg-[var(--color-accent)]/15 text-[var(--color-accent)]"
                  : "text-[var(--color-text-muted)] hover:bg-white/5"
              }`}
            >
              {f ?? "All"}
            </button>
          ))}
        </div>
      </div>

      {/* Timeline */}
      <div className="max-h-80 space-y-0.5 overflow-y-auto">
        {filtered.length === 0 && (
          <div className="py-6 text-center text-xs text-[var(--color-text-muted)]">
            {connectionState === "open"
              ? "No events yet. Events will appear here in real time."
              : "Connecting to event stream..."}
          </div>
        )}
        {filtered.slice(0, 50).map((event) => (
          <EventRow key={event.id} event={event} />
        ))}
      </div>
    </div>
  );
}
