/**
 * Client for the §24.2 real-time channel.
 *
 * Two things this deliberately refuses to do quietly.
 *
 * It never shows a stale view as if it were live: the connection state is
 * exposed so the UI can say "déconnecté" instead of leaving the last
 * events on screen looking current. A monitoring view that lies about
 * being connected is worse than no monitoring view.
 *
 * And it surfaces `stream.dropped`. The backend discards the oldest
 * events when a client cannot keep up and reports how many; swallowing
 * that here would undo the whole point of it being reported.
 */

export type EventType =
  | "system.metrics"
  | "chat.token"
  | "agent.message"
  | "task.update"
  | "validation.request"
  | "stream.dropped";

export interface HermesEvent {
  type: EventType;
  payload: Record<string, unknown>;
  timestamp: string;
}

export type ConnectionState = "connecting" | "open" | "closed";

const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL ??
  (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/^http/, "ws");

const RECONNECT_BASE_MS = 500;
const RECONNECT_MAX_MS = 10_000;

export interface EventStreamHandlers {
  onEvent: (event: HermesEvent) => void;
  onState?: (state: ConnectionState) => void;
}

/**
 * Opens the channel and keeps it open. Returns a function that closes it
 * for good — call it on unmount, or React's dev-mode double-effect will
 * leave an orphan socket delivering events into a dead component.
 */
export function openEventStream(
  types: EventType[] | undefined,
  handlers: EventStreamHandlers,
): () => void {
  let socket: WebSocket | null = null;
  let attempt = 0;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let closedByCaller = false;

  const query = types?.length ? `?types=${types.join(",")}` : "";
  const url = `${WS_URL.replace(/\/$/, "")}/ws${query}`;

  function connect() {
    handlers.onState?.("connecting");
    socket = new WebSocket(url);

    socket.onopen = () => {
      attempt = 0;
      handlers.onState?.("open");
    };

    socket.onmessage = (message) => {
      try {
        handlers.onEvent(JSON.parse(message.data) as HermesEvent);
      } catch {
        // A frame we cannot parse is a bug on the wire, not a reason to
        // tear down a working connection.
      }
    };

    socket.onclose = () => {
      handlers.onState?.("closed");
      if (closedByCaller) return;
      // Backoff, capped: the backend restarting is the common case and
      // resolves in seconds, but an unbounded retry storm against a
      // server that is genuinely down helps nobody.
      attempt += 1;
      const delay = Math.min(RECONNECT_BASE_MS * 2 ** (attempt - 1), RECONNECT_MAX_MS);
      retryTimer = setTimeout(connect, delay);
    };

    socket.onerror = () => {
      // onclose always follows; reconnection is handled there so the
      // backoff is not applied twice for one failure.
    };
  }

  connect();

  return () => {
    closedByCaller = true;
    if (retryTimer) clearTimeout(retryTimer);
    socket?.close();
  };
}

/** One-line human summary of an event, for the activity list. */
export function describeEvent(event: HermesEvent): string {
  const p = event.payload;
  switch (event.type) {
    case "task.update":
      return `${p.change} · ${p.title ?? p.id} → ${p.status ?? "?"}`;
    case "agent.message":
      return `${p.from} → ${p.to} · ${p.type}`;
    case "validation.request":
      return `${p.action_type} · ${p.description}`;
    case "stream.dropped":
      return `${p.count} événement(s) perdu(s) — affichage incomplet`;
    default:
      return JSON.stringify(p).slice(0, 120);
  }
}
