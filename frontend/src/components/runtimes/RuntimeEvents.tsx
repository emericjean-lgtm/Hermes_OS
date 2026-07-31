"use client";
import { useMemo, useState } from "react";
import { useRuntimeEvents } from "@/hooks/use-runtimes";
import {
  useRuntimeEvents as useRuntimeEventStream,
  type RuntimeEvent as StreamRuntimeEvent,
} from "@/hooks/use-runtime-events";
import { Activity, CheckCircle, XCircle, AlertTriangle, RotateCcw, Zap, Wifi, WifiOff } from "lucide-react";
import type { RuntimeEvent } from "@/types/mission-control";

/** The WebSocket stream and the REST endpoint describe the same event with
 *  different field names (`runtime_id`/`event_type`/lowercase severity vs
 *  `runtime`/`type`/uppercase). Normalise the stream shape onto the REST one
 *  so both sources can be merged and rendered by the same code below. */
function normaliseStreamEvent(ev: StreamRuntimeEvent): RuntimeEvent {
  const severity = ev.severity?.toUpperCase();
  return {
    id: ev.id,
    type: ev.event_type,
    runtime: ev.runtime_id,
    timestamp: ev.timestamp,
    severity: (severity === "WARNING" || severity === "ERROR" || severity === "CRITICAL"
      ? severity
      : "INFO") as RuntimeEvent["severity"],
    message: typeof ev.payload?.message === "string" ? ev.payload.message : ev.event_type,
  };
}

const TYPE_ICONS: Record<string, React.ReactNode> = {
  "runtime.selected": <Zap size={12} className="text-[var(--color-accent)]" />,
  "runtime.started": <Activity size={12} className="text-[var(--color-accent)]" />,
  "runtime.completed": <CheckCircle size={12} className="text-[var(--color-success)]" />,
  "runtime.failed": <XCircle size={12} className="text-[var(--color-danger)]" />,
  "runtime.degraded": <AlertTriangle size={12} className="text-[var(--color-warning)]" />,
  "runtime.overloaded": <AlertTriangle size={12} className="text-[var(--color-warning)]" />,
  "runtime.recovered": <RotateCcw size={12} className="text-[var(--color-success)]" />,
  "runtime.circuit_opened": <XCircle size={12} className="text-[var(--color-danger)]" />,
  "runtime.circuit_closed": <CheckCircle size={12} className="text-[var(--color-success)]" />,
  "runtime.fallback": <RotateCcw size={12} className="text-[var(--color-warning)]" />,
  "runtime.registered": <Activity size={12} className="text-[var(--color-accent)]" />,
};

export default function RuntimeEvents() {
  const { data: restEvents } = useRuntimeEvents();
  const { events: rawWsEvents, isConnected } = useRuntimeEventStream();
  const [filter, setFilter] = useState("");
  const [source, setSource] = useState<"all" | "rest" | "realtime">("all");

  const connectionState = isConnected ? "connected" : "disconnected";
  const wsEvents = useMemo(
    () => rawWsEvents.map(normaliseStreamEvent),
    [rawWsEvents],
  );

  // Merge REST polling + WebSocket events, deduplicate by id
  const mergedEvents = useMemo(() => {
    const rest: RuntimeEvent[] = restEvents ?? [];
    const combined = source === "realtime" ? wsEvents : source === "rest" ? rest : [...wsEvents, ...rest];
    const seen = new Set<string>();
    return combined.filter((ev) => {
      if (seen.has(ev.id)) return false;
      seen.add(ev.id);
      return true;
    }).slice(0, 100);
  }, [restEvents, wsEvents, source]);

  const filtered = useMemo(() => {
    if (!filter) return mergedEvents;
    const lower = filter.toLowerCase();
    return mergedEvents.filter(
      (e) =>
        e.runtime?.toLowerCase().includes(lower) ||
        e.type?.toLowerCase().includes(lower) ||
        e.severity?.toLowerCase().includes(lower),
    );
  }, [mergedEvents, filter]);

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Activity size={16} className="text-[var(--color-accent)]" />
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Runtime Events</h3>
          <span className="text-[10px] text-[var(--color-text-muted)]">({mergedEvents.length})</span>
          {connectionState === "connected" ? (
            <span title="Live" className="inline-flex">
              <Wifi size={12} className="text-[var(--color-success)]" />
            </span>
          ) : (
            <span title={connectionState} className="inline-flex">
              <WifiOff size={12} className="text-[var(--color-text-muted)]" />
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <select
            value={source}
            onChange={(e) => setSource(e.target.value as typeof source)}
            className="rounded bg-[var(--color-bg-base)] py-1 px-1.5 text-[9px] text-[var(--color-text-primary)] outline-none ring-1 ring-white/10"
          >
            <option value="all">All</option>
            <option value="realtime">Live</option>
            <option value="rest">History</option>
          </select>
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter..."
            className="w-24 rounded bg-[var(--color-bg-base)] py-1 px-2 text-[10px] text-[var(--color-text-primary)] outline-none ring-1 ring-white/10 focus:ring-[var(--color-accent)]"
          />
        </div>
      </div>
      <div className="max-h-64 space-y-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <p className="py-6 text-center text-xs text-[var(--color-text-muted)]">
            {connectionState !== "connected" ? "Connecting..." : "No events"}
          </p>
        ) : (
          filtered.map((ev) => (
            <div
              key={ev.id}
              className="flex items-start gap-2 border-l-2 pl-3 py-1.5"
              style={{
                borderColor:
                  ev.severity === "ERROR" || ev.severity === "CRITICAL"
                    ? "var(--color-danger)"
                    : ev.severity === "WARNING"
                      ? "var(--color-warning)"
                      : "var(--color-accent)",
              }}
            >
              {TYPE_ICONS[ev.type] ?? <Activity size={12} className="text-[var(--color-text-muted)]" />}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] font-medium text-[var(--color-accent)]">{ev.runtime}</span>
                  <span className="text-[9px] text-[var(--color-text-muted)]">
                    {ev.timestamp?.slice(11, 19)}
                  </span>
                  <span
                    className={`text-[9px] ${
                      ev.severity === "ERROR" || ev.severity === "CRITICAL"
                        ? "text-[var(--color-danger)]"
                        : ev.severity === "WARNING"
                          ? "text-[var(--color-warning)]"
                          : "text-[var(--color-text-muted)]"
                    }`}
                  >
                    {ev.severity}
                  </span>
                </div>
                <p className="text-[11px] text-[var(--color-text-primary)]">{ev.message || ev.type}</p>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
