"use client";

import { useWebSocket, severityColor, severityBg } from "@/hooks/use-websocket";
import { useCockpitStore } from "@/hooks/use-store";
import { Card, Badge } from "@/components/ui/card";
import type { EventSeverity, SystemEvent } from "@/types/hermes";

export function EventsCenter() {
  const { events, connected, clearEvents } = useWebSocket({});
  const {
    eventSeverityFilter,
    setEventSeverityFilter,
    eventSourceFilter,
    setEventSourceFilter,
  } = useCockpitStore();

  const severityOptions: EventSeverity[] = ["INFO", "WARNING", "ERROR", "CRITICAL"];

  const filtered = events.filter((e) => {
    if (eventSeverityFilter.length > 0 && !eventSeverityFilter.includes(e.severity)) return false;
    if (eventSourceFilter.length > 0 && !eventSourceFilter.includes(e.source)) return false;
    return true;
  });

  // Extract unique sources
  const sources = [...new Set(events.map((e) => e.source))];

  return (
    <div className="animate-fade-in">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-hermes-text font-mono tracking-tight">
            Event Center
          </h1>
          <p className="text-xs text-hermes-muted mt-1">
            Real-time event bus & system observability
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant={connected ? "success" : "danger"}>
            {connected ? "LIVE" : "DISCONNECTED"}
          </Badge>
          <button
            onClick={clearEvents}
            className="px-3 py-1.5 text-xs font-mono text-hermes-muted border border-hermes-border rounded-lg hover:border-hermes-amber hover:text-hermes-amber transition-colors"
          >
            Clear
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-4 mb-4">
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-hermes-muted font-mono uppercase">Severity:</span>
          {severityOptions.map((s) => (
            <button
              key={s}
              onClick={() => {
                setEventSeverityFilter(
                  eventSeverityFilter.includes(s)
                    ? eventSeverityFilter.filter((f) => f !== s)
                    : [...eventSeverityFilter, s]
                );
              }}
              className={`px-2 py-0.5 text-[10px] font-mono rounded border transition-colors ${
                eventSeverityFilter.includes(s) || eventSeverityFilter.length === 0
                  ? `${severityColor(s)} border-current bg-current/10`
                  : "text-hermes-muted border-hermes-border"
              }`}
            >
              {s}
            </button>
          ))}
        </div>

        {sources.length > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-hermes-muted font-mono uppercase">Source:</span>
            {sources.slice(0, 5).map((s) => (
              <button
                key={s}
                onClick={() => {
                  setEventSourceFilter(
                    eventSourceFilter.includes(s)
                      ? eventSourceFilter.filter((f) => f !== s)
                      : [...eventSourceFilter, s]
                  );
                }}
                className={`px-2 py-0.5 text-[10px] font-mono rounded border transition-colors ${
                  eventSourceFilter.includes(s) || eventSourceFilter.length === 0
                    ? "text-hermes-blue border-hermes-blue/30 bg-hermes-blue/10"
                    : "text-hermes-muted border-hermes-border"
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Event stream */}
      <Card title="Event Stream" subtitle={`${filtered.length} events`}>
        <div className="flex flex-col gap-1 max-h-[600px] overflow-y-auto font-mono">
          {filtered.map((event, i) => (
            <EventRow key={`${event.id || i}`} event={event} />
          ))}
          {filtered.length === 0 && connected && (
            <p className="text-xs text-hermes-muted py-8 text-center">Waiting for events...</p>
          )}
          {!connected && (
            <p className="text-xs text-hermes-red py-8 text-center">
              WebSocket disconnected. Attempting to reconnect...
            </p>
          )}
        </div>
      </Card>
    </div>
  );
}

function EventRow({ event }: { event: SystemEvent }) {
  return (
    <div
      className={`flex items-start gap-2 py-1.5 px-2 rounded border-l-2 ${severityBg(event.severity)} text-[11px]`}
    >
      <span className="text-hermes-muted w-14 flex-shrink-0 text-[10px]">
        {new Date(event.timestamp).toLocaleTimeString()}
      </span>
      <span className={`w-14 flex-shrink-0 font-bold ${severityColor(event.severity)}`}>
        {event.severity}
      </span>
      <span className="text-hermes-purple w-20 flex-shrink-0 truncate">
        {event.source}
      </span>
      <span className="text-hermes-amber flex-shrink-0">{event.type}</span>
      <span className="text-hermes-muted flex-1 truncate">
        {JSON.stringify(event.payload).slice(0, 100)}
      </span>
      {event.correlation_id && (
        <span className="text-[10px] text-hermes-muted font-mono" title={event.correlation_id}>
          #{event.correlation_id.slice(0, 8)}
        </span>
      )}
    </div>
  );
}
