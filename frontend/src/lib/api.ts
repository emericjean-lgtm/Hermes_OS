export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface StreamChatResult {
  model: string | null;
  tier: string | null;
  role: string | null;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * POSTs to the backend /chat endpoint and reads the streamed response body
 * chunk by chunk, invoking onToken for each piece of text as it arrives.
 * Routing metadata (model/tier/role) comes back as response headers, set
 * by the backend before the stream body starts.
 */
export async function streamChat(
  messages: ChatMessage[],
  onToken: (token: string) => void,
  options?: { agent?: string; task_type?: string },
): Promise<StreamChatResult> {
  const response = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      messages,
      ...(options?.agent ? { agent: options.agent } : {}),
      ...(options?.task_type ? { task_type: options.task_type } : {}),
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
  };

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    onToken(decoder.decode(value, { stream: true }));
  }

  return result;
}
