export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface StreamChatResult {
  model: string | null;
  tier: string | null;
  role: string | null;
  /** Whether the router enabled reasoning for this task type (§22.1). */
  thinking: boolean;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * POSTs to the backend /chat endpoint and reads the streamed response body
 * chunk by chunk, invoking onToken for each piece of text as it arrives.
 * Routing metadata (model/tier/role) comes back as response headers, set
 * by the backend before the stream body starts.
 *
 * Passing onThinking opts into the reasoning channel. On a reasoning
 * model the answer can be preceded by a long silent phase — measured at
 * 42 s on a code_analysis task — which reads as a hung request. Asking
 * for it switches the response body to NDJSON; without it the body stays
 * raw text, exactly as before.
 */
export async function streamChat(
  messages: ChatMessage[],
  onToken: (token: string) => void,
  options?: {
    agent?: string;
    task_type?: string;
    onThinking?: (text: string) => void;
  },
): Promise<StreamChatResult> {
  const includeThinking = Boolean(options?.onThinking);

  const response = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      messages,
      ...(options?.agent ? { agent: options.agent } : {}),
      ...(options?.task_type ? { task_type: options.task_type } : {}),
      ...(includeThinking ? { include_thinking: true } : {}),
    }),
  });

  if (!response.ok || !response.body) {
    const detail = await response.text().catch(() => response.statusText);
    throw new Error(`Chat request failed (${response.status}): ${detail}`);
  }

  const result: StreamChatResult = {
    model: response.headers.get("X-Hermes-Model"),
    tier: response.headers.get("X-Hermes-Tier"),
    role: response.headers.get("X-Hermes-Role"),
    thinking: response.headers.get("X-Hermes-Thinking") === "true",
  };

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  if (!includeThinking) {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      onToken(decoder.decode(value, { stream: true }));
    }
    return result;
  }

  // NDJSON: one {"kind","text"} object per line. A network chunk can split
  // a line anywhere, so the tail is held back until its newline arrives —
  // parsing a half-line would drop tokens rather than fail loudly.
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.trim()) continue;
      let chunk: { kind: string; text: string };
      try {
        chunk = JSON.parse(line);
      } catch {
        continue;
      }
      if (chunk.kind === "thinking") options?.onThinking?.(chunk.text);
      else onToken(chunk.text);
    }
  }

  return result;
}
