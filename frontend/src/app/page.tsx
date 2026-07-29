"use client";

import { useState } from "react";
import { streamChat, type ChatMessage } from "@/lib/api";
import ActivityPanel from "@/components/ActivityPanel";

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [routing, setRouting] = useState<{ model: string | null; tier: string | null } | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  // Reasoning for the turn in flight. On a reasoning model the answer can
  // be preceded by a long silent phase — measured at 42 s on a
  // code_analysis task — which is indistinguishable from a hung request.
  const [thinking, setThinking] = useState("");
  // Hermes Prime defaults to `conversation`, where reasoning is off — so
  // without a way to pick a task type the reasoning panel is unreachable
  // from this page, and the routing matrix (§10.1) is invisible.
  const [taskType, setTaskType] = useState("");

  async function handleSend() {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;

    const nextMessages: ChatMessage[] = [...messages, { role: "user", content: trimmed }];
    setMessages([...nextMessages, { role: "assistant", content: "" }]);
    setInput("");
    setIsStreaming(true);
    setError(null);
    setThinking("");

    try {
      const result = await streamChat(
        nextMessages,
        (token) => {
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            updated[updated.length - 1] = { ...last, content: last.content + token };
            return updated;
          });
        },
        {
          onThinking: (text) => setThinking((prev) => prev + text),
          ...(taskType ? { task_type: taskType } : {}),
        },
      );
      setRouting({ model: result.model, tier: result.tier });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsStreaming(false);
    }
  }

  return (
    <div className="flex h-screen w-full">
      <main className="mx-auto flex h-full w-full max-w-3xl flex-col px-4">
      <header className="flex items-center justify-between border-b border-white/10 py-4">
        <h1 className="text-lg font-semibold tracking-tight">Hermes Ollama</h1>
        <div className="flex items-center gap-3">
          {routing?.model && (
            <span className="text-xs text-[var(--color-text-muted)]">
              {routing.model}
              {routing.tier ? ` · ${routing.tier}` : ""}
            </span>
          )}
          <a
            href="/dashboard"
            className="rounded-md bg-[var(--color-accent)]/10 px-3 py-1.5 text-xs font-medium text-[var(--color-accent)] transition-colors hover:bg-[var(--color-accent)]/20"
          >
            Dashboard
          </a>
        </div>
      </header>

      <section className="flex-1 space-y-4 overflow-y-auto py-6">
        {messages.length === 0 && (
          <p className="text-sm text-[var(--color-text-muted)]">
            Ask Hermes anything to try the walking skeleton (Prime agent, streamed via /chat).
          </p>
        )}
        {messages.map((message, index) => {
          const isLast = index === messages.length - 1;
          const showThinking = isLast && message.role === "assistant" && thinking !== "";

          return (
            <div key={index} className="space-y-2">
              {showThinking && (
                // Open while the answer is still empty — that is the whole
                // point, filling a silence that otherwise reads as a hang.
                // Collapses on its own once the first word lands, and stays
                // reachable. <details> rather than a state toggle: keyboard
                // and screen-reader behaviour come for free.
                <details
                  open={message.content === ""}
                  className="mr-auto max-w-[80%] rounded-lg border border-white/10 px-4 py-2"
                >
                  <summary className="cursor-pointer text-xs text-[var(--color-text-muted)]">
                    Raisonnement{message.content === "" ? " en cours…" : ""}
                  </summary>
                  <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-[var(--color-text-muted)]">
                    {thinking}
                  </p>
                </details>
              )}
              {/* Not rendered while empty *and* the reasoning panel is up:
                  an empty bubble is just a grey box next to the thing the
                  user is actually reading. */}
              {(message.content !== "" || !showThinking) && (
                <div
                  className={`max-w-[80%] whitespace-pre-wrap rounded-lg px-4 py-3 text-sm leading-relaxed ${
                    message.role === "user"
                      ? "ml-auto bg-[var(--color-accent)]/15"
                      : "mr-auto bg-[var(--color-bg-surface)]"
                  }`}
                >
                  {message.content || (isStreaming && isLast ? "…" : "")}
                </div>
              )}
            </div>
          );
        })}
        {error && (
          <div className="rounded-lg bg-[var(--color-danger)]/10 px-4 py-3 text-sm text-[var(--color-danger)]">
            {error}
          </div>
        )}
      </section>

      <footer className="border-t border-white/10 py-4">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex gap-2"
        >
          <select
            value={taskType}
            onChange={(e) => setTaskType(e.target.value)}
            disabled={isStreaming}
            aria-label="Type de tâche"
            className="rounded-md bg-[var(--color-bg-surface)] px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[var(--color-accent)] disabled:opacity-50"
          >
            <option value="">conversation</option>
            <option value="planning">planning</option>
            <option value="code_analysis">code_analysis</option>
            <option value="reasoning">reasoning</option>
            <option value="extraction">extraction</option>
          </select>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type your request..."
            disabled={isStreaming}
            className="flex-1 rounded-md bg-[var(--color-bg-surface)] px-4 py-2 text-sm outline-none focus:ring-1 focus:ring-[var(--color-accent)] disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={isStreaming || !input.trim()}
            className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            {isStreaming ? "Streaming…" : "Send"}
          </button>
        </form>
      </footer>
      </main>
      <ActivityPanel />
    </div>
  );
}
