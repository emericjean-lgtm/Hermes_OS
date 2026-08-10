/**
 * Streaming client for the Assistant (HOS-074).
 *
 * The Cockpit used to POST `/conversation/message` and wait for the whole
 * answer: on a local model at ~13 tok/s a 400-token reply is 30 s of a
 * bouncing-dots animation with nothing to read. `POST /conversation/stream`
 * returns NDJSON — one `{kind, text}` object per line — carrying the
 * reasoning channel separately from the answer, plus the real routing
 * decision in `X-Hermes-*` headers.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

/** The real routing decision behind a reply — the same ModelRouter output
 *  `/chat` exposes, surfaced so the Assistant can answer "why this model?"
 *  with the actual reason rather than a plausible-looking guess. */
export interface StreamRouting {
  session_id: string;
  model: string;
  tier: string;
  role: string;
  reason: string;
  thinking: boolean;
  intent: string;
}

/** Real, honest estimate (~4 chars/token) of how much of the model's
 *  actual context window this turn used — see the backend's own
 *  ``used_tokens_estimate``/``window`` docstring for why this isn't an
 *  exact token count. */
export interface ContextUsage {
  used_tokens_estimate: number;
  window: number;
}

/** One real internet search the model asked for (Assistant chat, real
 *  DuckDuckGo results — see backend/tools/connectors/web_search.py). */
export interface ToolCall {
  id?: string;
  function?: { name: string; arguments?: Record<string, unknown> };
}
export interface ToolResult {
  name: string;
  arguments?: Record<string, unknown>;
  result: string;
}

export interface StreamHandlers {
  onRouting?: (routing: StreamRouting) => void;
  onThinking?: (text: string) => void;
  onContent?: (text: string) => void;
  /** The model asked to call a tool (currently only `web_search`) — fires
   *  before the tool actually runs. */
  onToolCall?: (calls: ToolCall[]) => void;
  /** The tool actually ran and this is its real result, fed back to the
   *  model for its next turn. */
  onToolResult?: (results: ToolResult[]) => void;
  /** Terminal signal from the server, carrying the analysed intent and
   *  real context-window usage for this turn. */
  onDone?: (payload: {
    session_id: string;
    intent?: { type: string; confidence: number; domain: string };
    context?: ContextUsage;
  }) => void;
  onError?: (message: string) => void;
}

export interface StreamRequest {
  sessionId: string;
  message: string;
  agent?: string;
  taskType?: string;
  /** A real config/models.yaml role (HOS-075) forcing the model choice —
   *  "auto" or omitted keeps automatic ModelRouter selection. */
  role?: string;
  /** Forces the reasoning channel on/off regardless of the task type's own
   *  policy — undefined keeps that policy. */
  thinking?: boolean;
  /** Aborting mid-stream is a first-class action, not an error: the backend
   *  persists whatever was generated, so the transcript stays truthful. */
  signal?: AbortSignal;
}

export async function streamConversation(
  { sessionId, message, agent, taskType, role, thinking, signal }: StreamRequest,
  handlers: StreamHandlers,
): Promise<void> {
  const response = await fetch(`${API_BASE}/conversation/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      message,
      ...(agent ? { agent } : {}),
      ...(taskType ? { task_type: taskType } : {}),
      ...(role ? { role } : {}),
      ...(thinking !== undefined ? { thinking } : {}),
    }),
    signal,
  });

  if (!response.ok || !response.body) {
    const detail = await response.text().catch(() => response.statusText);
    throw new Error(`Hermes n'a pas pu répondre (${response.status}) : ${detail}`);
  }

  handlers.onRouting?.({
    session_id: response.headers.get("X-Hermes-Session") ?? sessionId,
    model: response.headers.get("X-Hermes-Model") ?? "",
    tier: response.headers.get("X-Hermes-Tier") ?? "",
    role: response.headers.get("X-Hermes-Role") ?? "",
    reason: response.headers.get("X-Hermes-Reason") ?? "",
    thinking: response.headers.get("X-Hermes-Thinking") === "true",
    intent: response.headers.get("X-Hermes-Intent") ?? "",
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  // A network chunk can split a line anywhere, so the tail is held back
  // until its newline arrives — parsing a half-line would drop tokens.
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (!line.trim()) continue;
        let event: {
          kind: string; text?: string; error?: string; session_id?: string;
          intent?: any; context?: ContextUsage; tool_calls?: any[];
        };
        try {
          event = JSON.parse(line);
        } catch {
          continue;
        }
        switch (event.kind) {
          case "thinking":
            handlers.onThinking?.(event.text ?? "");
            break;
          case "content":
            handlers.onContent?.(event.text ?? "");
            break;
          case "tool_calls":
            handlers.onToolCall?.((event.tool_calls ?? []) as ToolCall[]);
            break;
          case "tool_result":
            handlers.onToolResult?.((event.tool_calls ?? []) as ToolResult[]);
            break;
          case "done":
            handlers.onDone?.({
              session_id: event.session_id ?? sessionId,
              intent: event.intent,
              context: event.context,
            });
            break;
          case "error":
            handlers.onError?.(event.error ?? "erreur inconnue");
            break;
        }
      }
    }
  } catch (err) {
    // An abort is the user pressing stop — the caller decides what that
    // means, and it must not surface as a failure.
    if ((err as Error)?.name === "AbortError") return;
    throw err;
  } finally {
    reader.releaseLock?.();
  }
}
