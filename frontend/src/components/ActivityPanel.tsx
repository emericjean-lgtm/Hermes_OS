"use client";

import { useEffect, useRef, useState } from "react";
import {
  describeEvent,
  openEventStream,
  type ConnectionState,
  type EventType,
  type HermesEvent,
} from "@/lib/events";

/**
 * Live view of what the agents are doing — the thing the dashboard could
 * not show before §24.2, because nothing was pushed.
 *
 * `chat.token` is deliberately not subscribed to. It is one event per
 * token, hundreds per answer, and it would push every other line off the
 * panel within a second — the answer is already on screen next to it.
 * Subscribing to only what is displayed also means the backend never
 * queues a firehose this client would immediately discard.
 */
const SUBSCRIBED: EventType[] = [
  "task.update",
  "agent.message",
  "validation.request",
  "system.metrics",
  "stream.dropped",
];

const MAX_ROWS = 60;

const TONE: Record<string, string> = {
  "task.update": "text-[var(--color-accent)]",
  "validation.request": "text-[var(--color-danger)]",
  "stream.dropped": "text-[var(--color-danger)]",
  "agent.message": "text-[var(--color-text-muted)]",
};

interface Metrics {
  vramUsed?: number;
  vramTotal?: number;
  tempC?: number | null;
  models?: string[];
}

export default function ActivityPanel() {
  const [rows, setRows] = useState<HermesEvent[]>([]);
  const [state, setState] = useState<ConnectionState>("connecting");
  const [metrics, setMetrics] = useState<Metrics>({});
  const listRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    return openEventStream(SUBSCRIBED, {
      onState: setState,
      onEvent: (event) => {
        // Metrics update a gauge rather than the log: at one every two
        // seconds they would bury everything else within a minute.
        if (event.type === "system.metrics") {
          const gpu = event.payload.gpu as Record<string, number> | undefined;
          const models = event.payload.loaded_models as
            | Array<{ name?: string }>
            | undefined;
          setMetrics({
            vramUsed: gpu?.vram_used_gb,
            vramTotal: gpu?.vram_total_gb,
            tempC: gpu?.temp_c ?? null,
            models: models?.map((m) => m.name ?? "?") ?? [],
          });
          return;
        }
        setRows((prev) => [event, ...prev].slice(0, MAX_ROWS));
      },
    });
  }, []);

  return (
    <aside className="hidden w-80 shrink-0 flex-col border-l border-white/10 lg:flex">
      <header className="flex items-center justify-between border-b border-white/10 px-4 py-4">
        <h2 className="text-sm font-semibold tracking-tight">Activité</h2>
        <span
          className={`text-xs ${
            state === "open"
              ? "text-[var(--color-text-muted)]"
              : "text-[var(--color-danger)]"
          }`}
        >
          {/* Never let a stale list pass for a live one. */}
          {state === "open"
            ? "en direct"
            : state === "connecting"
              ? "connexion…"
              : "déconnecté"}
        </span>
      </header>

      {metrics.vramTotal !== undefined && (
        <div className="border-b border-white/10 px-4 py-3 text-xs text-[var(--color-text-muted)]">
          <div className="flex justify-between">
            <span>VRAM</span>
            <span>
              {metrics.vramUsed?.toFixed(2)} / {metrics.vramTotal?.toFixed(2)} Go
              {metrics.tempC != null ? ` · ${metrics.tempC} °C` : ""}
            </span>
          </div>
          {metrics.models && metrics.models.length > 0 && (
            <p className="mt-1 truncate">{metrics.models.join(", ")}</p>
          )}
        </div>
      )}

      <ul ref={listRef} className="flex-1 space-y-2 overflow-y-auto px-4 py-3">
        {rows.length === 0 && (
          <li className="text-xs text-[var(--color-text-muted)]">
            {/* Never a mute empty state: say what would appear here. */}
            {state === "open"
              ? "Rien pour l’instant. Les tâches, messages entre agents et demandes de validation apparaîtront ici."
              : "En attente du canal temps réel."}
          </li>
        )}
        {rows.map((event, index) => (
          <li key={`${event.timestamp}-${index}`} className="text-xs leading-relaxed">
            <div className="flex items-baseline justify-between gap-2">
              <span className={TONE[event.type] ?? ""}>{event.type}</span>
              <span className="shrink-0 text-[10px] text-[var(--color-text-muted)]">
                {event.timestamp.slice(11, 19)}
              </span>
            </div>
            <p className="text-[var(--color-text-muted)]">{describeEvent(event)}</p>
          </li>
        ))}
      </ul>
    </aside>
  );
}
