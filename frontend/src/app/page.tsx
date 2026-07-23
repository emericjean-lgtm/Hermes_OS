"use client";

import { useState } from "react";
import { streamChat, type ChatMessage } from "@/lib/api";

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [routing, setRouting] = useState<{ model: string | null; tier: string | null } | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  async function handleSend() {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;

    const nextMessages: ChatMessage[] = [...messages, { role: "user", content: trimmed }];
    setMessages([...nextMessages, { role: "assistant", content: "" }]);
    setInput("");
    setIsStreaming(true);
    setError(null);

    try {
      const result = await streamChat(nextMessages, (token) => {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          updated[updated.length - 1] = { ...last, content: last.content + token };
          return updated;
        });
      });
      setRouting({ model: result.model, tier: result.tier });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsStreaming(false);
    }
  }

  return (
    <main className="mx-auto flex h-screen w-full max-w-3xl flex-col px-4">
      <header className="flex items-center justify-between border-b border-white/10 py-4">
        <h1 className="text-lg font-semibold tracking-tight">Hermes Ollama</h1>
        {routing?.model && (
          <span className="text-xs text-[var(--color-text-muted)]">
            {routing.model}
            {routing.tier ? ` · ${routing.tier}` : ""}
          </span>
        )}
      </header>

      <section className="flex-1 space-y-4 overflow-y-auto py-6">
        {messages.length === 0 && (
          <p className="text-sm text-[var(--color-text-muted)]">
            Ask Hermes anything to try the walking skeleton (Prime agent, streamed via /chat).
          </p>
        )}
        {messages.map((message, index) => (
          <div
            key={index}
            className={`max-w-[80%] whitespace-pre-wrap rounded-lg px-4 py-3 text-sm leading-relaxed ${
              message.role === "user"
                ? "ml-auto bg-[var(--color-accent)]/15"
                : "mr-auto bg-[var(--color-bg-surface)]"
            }`}
          >
            {message.content || (isStreaming && index === messages.length - 1 ? "…" : "")}
          </div>
        ))}
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
  );
}
