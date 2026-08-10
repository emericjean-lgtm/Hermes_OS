"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Brain, ChevronDown, Copy, Check, Cpu, Globe, HardDrive, Info,
  MessageSquarePlus, RefreshCw, Search, Send, Sparkles, Square, User, Zap,
} from "lucide-react";
import { conversationClient } from "@/services/client";
import { streamConversation, type ContextUsage, type StreamRouting } from "@/services/conversation-stream";
import { useMonitoringResources, useSystemModelRoles } from "@/hooks/use-api";
import type { ResourceStatus } from "@/types/hermes";
import { formatGioPair } from "@/lib/format";
import { MarkdownMessage } from "./markdown-message";
import { ContextMeter, ModelPicker, type ModelSelection } from "./model-picker";
import {
  ContextPanel, HelpPanel, matchSlashCommands, SessionPicker, SlashCommandMenu, type SlashCommand,
} from "./slash-commands";
import { AttachButton, AttachmentChips, buildAttachmentPreamble, type Attachment } from "./attachments";
import { WebPreviewPanel } from "./web-preview";
import { VoiceButton } from "./voice-input";
import { RailPanel, Placeholder } from "./rail-primitives";
import { ProjectPanel } from "./project-panel";

/**
 * Assistant Hermes (HOS-074) — conversation-first console.
 *
 * Rebuilt from a blocking chat that could not stream, had no memory of its
 * own conversation (the backend only ever sent `[system, user]` to the
 * model), rendered replies through `dangerouslySetInnerHTML` + a two-line
 * regex, and offered no way to stop a running generation.
 *
 * Layout is deliberately conversation-first: the transcript owns the width,
 * and the context rail is collapsible rather than a permanent wall of
 * widgets — the panels only carry data that is genuinely real (runtime and
 * VRAM from HOS-072, routing decision from the ModelRouter headers). No
 * tool-use panel: this path performs no real tool calls yet (HOS-069
 * finding), and a control that implies otherwise would be a lie.
 */

interface SearchEntry {
  query: string;
  result?: string;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  thinking?: string;
  /** Real internet searches the model asked for this turn (HOS-078), in
   *  order — `result` is undefined until the search actually completes. */
  searches?: SearchEntry[];
  routing?: StreamRouting;
  context?: ContextUsage;
  attachments?: Attachment[];
  timestamp: string;
  /** Set when the user stopped generation — the partial answer is real and
   *  kept, but must not read as a complete reply. */
  interrupted?: boolean;
  error?: string;
}

const AUTO_SELECTION: ModelSelection = { role: "" };

const SESSION_STORAGE_KEY = "hermes.assistant.session";

const QUICK_ACTIONS = [
  { icon: "🔍", label: "Analyser le projet", prompt: "Analyse l'architecture de ce projet et identifie les points d'amélioration prioritaires." },
  { icon: "🐞", label: "Déboguer", prompt: "Aide-moi à déboguer un problème. Voici le contexte : " },
  { icon: "⚡", label: "Optimiser", prompt: "Quelles optimisations de performance recommandes-tu pour ce projet ?" },
  { icon: "📚", label: "Documenter", prompt: "Génère la documentation technique pour ce module." },
  { icon: "🧪", label: "Tests", prompt: "Propose une stratégie de tests pour ce composant." },
] as const;

const uid = () => `m_${Math.random().toString(36).slice(2, 10)}`;

export default function ConversationCenter() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [railOpen, setRailOpen] = useState(true);
  const [selection, setSelection] = useState<ModelSelection>(AUTO_SELECTION);
  const [slashIndex, setSlashIndex] = useState(0);
  const [sessionPickerOpen, setSessionPickerOpen] = useState(false);
  const [contextPanelOpen, setContextPanelOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [webPreviewOpen, setWebPreviewOpen] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  /** Suppresses auto-scroll once the user scrolls up to read back — being
   *  yanked to the bottom mid-read is the classic streaming-chat annoyance. */
  const pinnedRef = useRef(true);

  const { data: resources } = useMonitoringResources() as { data?: ResourceStatus };
  const gpu = resources?.gpu;
  const ram = resources?.ram;

  const {
    data: modelRolesData, isError: rolesFailed, refetch: refetchRoles,
  } = useSystemModelRoles();
  const roles = useMemo(() => modelRolesData?.roles ?? [], [modelRolesData]);

  const lastRouting = useMemo(
    () => [...messages].reverse().find((m) => m.routing)?.routing,
    [messages],
  );
  const lastContext = useMemo(
    () => [...messages].reverse().find((m) => m.context)?.context,
    [messages],
  );
  const slashMatches = useMemo(() => matchSlashCommands(input), [input]);

  /* ── Session lifecycle ─────────────────────────────────────────── */

  const loadHistory = useCallback(async (id: string) => {
    try {
      const data = await conversationClient.session(id);
      const raw = (data as { messages?: { role: string; content: string; timestamp: string }[] })
        .messages ?? [];
      if (raw.length === 0) return false;
      setMessages(raw.map((m) => ({
        id: uid(),
        role: m.role === "user" ? "user" : "assistant",
        content: m.content,
        timestamp: m.timestamp,
      })));
      return true;
    } catch {
      return false;
    }
  }, []);

  // Restore the previous session across reloads: the history endpoint has
  // always existed and was simply never called, so every refresh silently
  // started a blank conversation over a session that still held its
  // transcript server-side.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const stored = typeof window !== "undefined"
        ? window.localStorage.getItem(SESSION_STORAGE_KEY) : null;
      if (stored) {
        const ok = await loadHistory(stored);
        if (!cancelled && ok) { setSessionId(stored); return; }
      }
      try {
        const started = await conversationClient.start();
        if (cancelled) return;
        setSessionId(started.session_id);
        window.localStorage.setItem(SESSION_STORAGE_KEY, started.session_id);
      } catch {
        if (!cancelled) setError("Impossible d'ouvrir une session — le backend est-il démarré ?");
      }
    })();
    return () => { cancelled = true; };
  }, [loadHistory]);

  const newConversation = useCallback(async () => {
    abortRef.current?.abort();
    setStreaming(false);
    setError(null);
    try {
      const started = await conversationClient.start();
      setSessionId(started.session_id);
      window.localStorage.setItem(SESSION_STORAGE_KEY, started.session_id);
      setMessages([]);
    } catch {
      setError("Impossible d'ouvrir une nouvelle session.");
    }
  }, []);

  const switchSession = useCallback(async (id: string) => {
    setSessionPickerOpen(false);
    setInput("");
    if (id === sessionId) return;
    abortRef.current?.abort();
    setStreaming(false);
    setError(null);
    const ok = await loadHistory(id);
    setSessionId(id);
    window.localStorage.setItem(SESSION_STORAGE_KEY, id);
    if (!ok) setMessages([]);
  }, [sessionId, loadHistory]);

  const runSlashCommand = useCallback((command: SlashCommand) => {
    setInput("");
    if (command.cmd === "/clean") {
      void newConversation();
    } else if (command.cmd === "/resume") {
      setSessionPickerOpen(true);
    } else if (command.cmd === "/context") {
      setContextPanelOpen(true);
    } else if (command.cmd === "/help") {
      setHelpOpen(true);
    } else if (command.cmd === "/compact") {
      setNotice(command.description);
    }
  }, [newConversation]);

  /* ── Scrolling ─────────────────────────────────────────────────── */

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    pinnedRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  }, []);

  useEffect(() => {
    if (pinnedRef.current) {
      endRef.current?.scrollIntoView({ behavior: streaming ? "auto" : "smooth" });
    }
  }, [messages, streaming]);

  /* ── Sending ───────────────────────────────────────────────────── */

  const send = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if ((!trimmed && attachments.length === 0) || streaming || !sessionId) return;

    const pendingAttachments = attachments;
    const wireMessage = buildAttachmentPreamble(pendingAttachments) + trimmed;

    const userMsg: ChatMessage = {
      id: uid(), role: "user", content: trimmed || "(pièce jointe sans message)",
      attachments: pendingAttachments.length ? pendingAttachments : undefined,
      timestamp: new Date().toISOString(),
    };
    const assistantId = uid();
    setMessages((prev) => [...prev, userMsg, {
      id: assistantId, role: "assistant", content: "",
      timestamp: new Date().toISOString(),
    }]);
    setInput("");
    setAttachments([]);
    setError(null);
    setStreaming(true);
    pinnedRef.current = true;

    const controller = new AbortController();
    abortRef.current = controller;

    const patch = (fn: (m: ChatMessage) => ChatMessage) =>
      setMessages((prev) => prev.map((m) => (m.id === assistantId ? fn(m) : m)));

    try {
      await streamConversation(
        {
          sessionId, message: wireMessage, signal: controller.signal,
          ...(selection.role ? { role: selection.role } : {}),
          ...(selection.thinking !== undefined ? { thinking: selection.thinking } : {}),
        },
        {
          onRouting: (routing) => patch((m) => ({ ...m, routing })),
          onThinking: (t) => patch((m) => ({ ...m, thinking: (m.thinking ?? "") + t })),
          onContent: (t) => patch((m) => ({ ...m, content: m.content + t })),
          onToolCall: (calls) => patch((m) => {
            const additions = calls
              .filter((c) => c.function?.name === "web_search")
              .map((c) => ({ query: String(c.function?.arguments?.query ?? "") }));
            return additions.length
              ? { ...m, searches: [...(m.searches ?? []), ...additions] }
              : m;
          }),
          onToolResult: (results) => patch((m) => {
            if (!m.searches?.length) return m;
            const searches = [...m.searches];
            for (const r of results) {
              const idx = searches.findIndex((s) => s.result === undefined);
              if (idx >= 0) searches[idx] = { ...searches[idx], result: r.result };
            }
            return { ...m, searches };
          }),
          onDone: (payload) => patch((m) => ({ ...m, context: payload.context })),
          onError: (message) => patch((m) => ({ ...m, error: message })),
        },
      );
    } catch (e) {
      const message = e instanceof Error ? e.message : "Hermes est injoignable";
      patch((m) => ({ ...m, error: message }));
      setError(message);
    } finally {
      if (controller.signal.aborted) patch((m) => ({ ...m, interrupted: true }));
      setStreaming(false);
      abortRef.current = null;
    }
  }, [sessionId, streaming, selection, attachments]);

  const stop = useCallback(() => abortRef.current?.abort(), []);

  const regenerate = useCallback(() => {
    // Re-ask the last question; the previous (kept) answer stays in the
    // server-side transcript, so this reads as a follow-up turn rather
    // than pretending the first attempt never happened.
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (lastUser) void send(lastUser.content);
  }, [messages, send]);

  const onKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (slashMatches.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSlashIndex((i) => (i + 1) % slashMatches.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setSlashIndex((i) => (i - 1 + slashMatches.length) % slashMatches.length);
        return;
      }
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        runSlashCommand(slashMatches[slashIndex] ?? slashMatches[0]);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setInput("");
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send(input);
    } else if (e.key === "Escape" && streaming) {
      e.preventDefault();
      stop();
    }
  }, [input, send, streaming, stop, slashMatches, slashIndex, runSlashCommand]);

  // Auto-grow the composer, capped so it never eats the transcript.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [input]);

  const isEmpty = messages.length === 0;

  return (
    <div className="flex h-full min-h-0 gap-4">
      {/* ── Conversation column ─────────────────────────────────── */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-hermes-border/70 px-1 pb-3">
          <div className="relative">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-hermes-cyan/25 to-hermes-violet/20 ring-1 ring-hermes-cyan/30">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/hermes-agent-logo.png" alt="Hermes" className="h-5 w-5 object-contain invert" />
            </div>
            {streaming && (
              <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-hermes-green shadow-glow-green" />
            )}
          </div>
          <div className="min-w-0">
            <h1 className="text-[15px] font-semibold leading-tight text-hermes-text-bright">
              Assistant Hermes
            </h1>
            <p className="truncate font-mono text-[10px] text-hermes-muted">
              {sessionId ? `${sessionId} · ${messages.length} message(s)` : "ouverture de session…"}
            </p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            {lastRouting?.model && (
              <RoutingBadge routing={lastRouting} />
            )}
            <button
              onClick={() => setWebPreviewOpen(true)}
              title="Aperçu web — rendu en direct d'une page locale"
              className="flex items-center gap-1.5 rounded-lg border border-hermes-border px-2.5 py-1.5
                font-mono text-[10px] uppercase tracking-wider text-hermes-muted transition-all
                hover:border-hermes-cyan/40 hover:text-hermes-cyan"
            >
              <Globe size={12} /> Aperçu
            </button>
            <button
              onClick={newConversation}
              title="Nouvelle conversation"
              className="flex items-center gap-1.5 rounded-lg border border-hermes-border px-2.5 py-1.5
                font-mono text-[10px] uppercase tracking-wider text-hermes-muted transition-all
                hover:border-hermes-cyan/40 hover:text-hermes-cyan"
            >
              <MessageSquarePlus size={12} /> Nouvelle
            </button>
            <button
              onClick={() => setRailOpen((v) => !v)}
              title={railOpen ? "Masquer le panneau" : "Afficher le panneau"}
              className="rounded-lg border border-hermes-border px-2 py-1.5 text-hermes-muted
                transition-all hover:border-hermes-cyan/40 hover:text-hermes-cyan"
            >
              <ChevronDown size={12} className={`transition-transform ${railOpen ? "-rotate-90" : "rotate-90"}`} />
            </button>
          </div>
        </header>

        {error && (
          <div className="mt-3 flex items-center gap-2 rounded-lg border border-hermes-red/30 bg-hermes-red/10 px-3 py-2 text-[11px] text-hermes-red">
            <span>⚠</span>{error}
          </div>
        )}

        {notice && (
          <div className="mt-3 flex items-center gap-2 rounded-lg border border-hermes-amber/30 bg-hermes-amber/10 px-3 py-2 text-[11px] text-hermes-amber">
            <span>ℹ</span>{notice}
            <button onClick={() => setNotice(null)} className="ml-auto text-hermes-amber/70 hover:text-hermes-amber">✕</button>
          </div>
        )}

        {/* mx-auto max-w-4xl: on an ultrawide monitor the flex-1 column
            can be well over 2000px, so the transcript and composer are
            capped to a comfortable reading width and centered, while the
            rail keeps its own fixed width alongside. */}
        <div
          ref={scrollRef}
          onScroll={onScroll}
          className="min-h-0 flex-1 overflow-y-auto px-1 py-5"
        >
          <div className="mx-auto w-full max-w-4xl space-y-5">
            {isEmpty ? (
              <EmptyState onPick={(p) => { setInput(p); textareaRef.current?.focus(); }} />
            ) : (
              messages.map((m) => (
                <MessageRow
                  key={m.id}
                  message={m}
                  streaming={streaming && m.role === "assistant" && m === messages[messages.length - 1]}
                />
              ))
            )}
            <div ref={endRef} />
          </div>
        </div>

        {/* ── Composer ──────────────────────────────────────────── */}
        <div className="border-t border-hermes-border/70 px-1 pt-3">
         <div className="mx-auto w-full max-w-4xl">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <ModelPicker roles={roles} value={selection} onChange={setSelection} />
              {rolesFailed && (
                <button
                  onClick={() => void refetchRoles()}
                  title="Le chargement des modèles a échoué — cliquer pour réessayer"
                  className="flex items-center gap-1 rounded-md px-1.5 py-1 font-mono text-[9.5px]
                    uppercase tracking-wider text-hermes-amber transition-colors hover:text-hermes-amber/80"
                >
                  <RefreshCw size={10} /> Modèles indisponibles
                </button>
              )}
              <AttachButton
                onFiles={(files) => setAttachments((prev) => [...prev, ...files])}
                onError={setError}
              />
              <VoiceButton
                onResult={(text) => setInput((prev) => (prev ? `${prev} ${text}` : text))}
                onError={setError}
              />
              {lastContext && <ContextMeter used={lastContext.used_tokens_estimate} window={lastContext.window} />}
            </div>
            {!isEmpty && !streaming && (
              <button
                onClick={regenerate}
                className="flex items-center gap-1.5 rounded-md px-2 py-1 font-mono text-[10px]
                  uppercase tracking-wider text-hermes-dim transition-colors hover:text-hermes-cyan"
              >
                <RefreshCw size={10} /> Régénérer
              </button>
            )}
          </div>
          <AttachmentChips
            attachments={attachments}
            onRemove={(id) => setAttachments((prev) => prev.filter((a) => a.id !== id))}
          />
          <div className="group relative rounded-xl border border-hermes-border bg-hermes-elevated/50
            transition-all focus-within:border-hermes-cyan/50 focus-within:shadow-glow-cyan">
            <AnimatePresence>
              {slashMatches.length > 0 && (
                <SlashCommandMenu matches={slashMatches} activeIndex={slashIndex} onPick={runSlashCommand} />
              )}
            </AnimatePresence>
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => { setInput(e.target.value); setSlashIndex(0); }}
              onKeyDown={onKeyDown}
              rows={1}
              placeholder={streaming ? "Hermes répond… (Échap pour interrompre)" : "Posez votre question ou donnez une instruction…"}
              className="w-full resize-none bg-transparent px-4 py-3.5 pr-28 text-[13.5px] leading-relaxed
                text-hermes-text-bright placeholder-hermes-dim focus:outline-none"
            />
            <div className="absolute bottom-2.5 right-2.5 flex items-center gap-2">
              <kbd className="hidden font-mono text-[9px] text-hermes-dim sm:block">
                {streaming ? "ÉCHAP" : "↵"}
              </kbd>
              {streaming ? (
                <button
                  onClick={stop}
                  className="flex items-center gap-1.5 rounded-lg border border-hermes-red/50 bg-hermes-red/10
                    px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider text-hermes-red
                    transition-all hover:bg-hermes-red/20"
                >
                  <Square size={10} fill="currentColor" /> Stop
                </button>
              ) : (
                <button
                  onClick={() => void send(input)}
                  disabled={(!input.trim() && attachments.length === 0) || !sessionId}
                  className="flex items-center gap-1.5 rounded-lg border border-hermes-cyan/50 bg-hermes-cyan/15
                    px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider text-hermes-cyan
                    transition-all hover:bg-hermes-cyan/25 disabled:pointer-events-none disabled:opacity-30"
                >
                  <Send size={10} /> Envoyer
                </button>
              )}
            </div>
          </div>
         </div>
        </div>
      </div>

      {/* ── Context rail ────────────────────────────────────────── */}
      <AnimatePresence initial={false}>
        {railOpen && (
          <motion.aside
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 268, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            className="hidden shrink-0 overflow-hidden lg:block"
          >
            <div className="flex h-full w-[268px] flex-col gap-3 overflow-y-auto pr-0.5">
              <RailPanel title="Runtime" icon={<Brain size={11} />}>
                {lastRouting?.model ? (
                  <div className="space-y-2">
                    <div className="font-mono text-[12px] text-hermes-text-bright">{lastRouting.model}</div>
                    <div className="flex flex-wrap gap-1">
                      <Chip>{lastRouting.tier}</Chip>
                      <Chip>{lastRouting.role}</Chip>
                      {lastRouting.thinking && <Chip tone="violet">raisonnement</Chip>}
                    </div>
                    {lastRouting.reason && (
                      <p className="text-[10.5px] leading-relaxed text-hermes-muted">{lastRouting.reason}</p>
                    )}
                  </div>
                ) : (
                  <Placeholder>Le modèle sera choisi au premier message.</Placeholder>
                )}
              </RailPanel>

              <RailPanel title="Ressources" icon={<Cpu size={11} />}>
                {gpu?.available ? (
                  <div className="space-y-2.5">
                    <Meter
                      label={gpu.name || "GPU"}
                      detail={formatGioPair(gpu.vram_used_bytes, gpu.vram_total_bytes)}
                      pct={gpu.vram_total_bytes ? (gpu.vram_used_bytes / gpu.vram_total_bytes) * 100 : 0}
                    />
                    {ram && (
                      <Meter
                        label="RAM"
                        detail={formatGioPair(ram.used_bytes, ram.total_bytes)}
                        pct={ram.usage_pct}
                      />
                    )}
                  </div>
                ) : (
                  <Placeholder>Télémétrie GPU indisponible.</Placeholder>
                )}
              </RailPanel>

              <RailPanel title="Actions rapides" icon={<Zap size={11} />}>
                <div className="flex flex-col gap-1">
                  {QUICK_ACTIONS.map((a) => (
                    <button
                      key={a.label}
                      onClick={() => { setInput(a.prompt); textareaRef.current?.focus(); }}
                      className="flex items-center gap-2 rounded-md px-2 py-1.5 text-left text-[11px]
                        text-hermes-muted transition-all hover:bg-hermes-cyan/[0.07] hover:text-hermes-cyan"
                    >
                      <span className="text-[12px]">{a.icon}</span>{a.label}
                    </button>
                  ))}
                </div>
              </RailPanel>

              <ProjectPanel />
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

      {sessionPickerOpen && (
        <SessionPicker
          currentSessionId={sessionId}
          onPick={(id) => void switchSession(id)}
          onClose={() => setSessionPickerOpen(false)}
        />
      )}

      {contextPanelOpen && (
        <ContextPanel sessionId={sessionId} onClose={() => setContextPanelOpen(false)} />
      )}

      {helpOpen && <HelpPanel onClose={() => setHelpOpen(false)} />}

      <AnimatePresence>
        {webPreviewOpen && <WebPreviewPanel onClose={() => setWebPreviewOpen(false)} />}
      </AnimatePresence>
    </div>
  );
}

/* ── Message ─────────────────────────────────────────────────────── */

function MessageRow({ message, streaming }: { message: ChatMessage; streaming: boolean }) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";

  const copy = useCallback(() => {
    void navigator.clipboard?.writeText(message.content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    });
  }, [message.content]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className={`group flex gap-3 ${isUser ? "justify-end" : ""}`}
    >
      {!isUser && (
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg
          bg-gradient-to-br from-hermes-cyan/20 to-hermes-violet/15 ring-1 ring-hermes-cyan/25">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/hermes-agent-logo.png" alt="Hermes" className="h-4 w-4 object-contain invert" />
        </div>
      )}

      <div className={`min-w-0 ${isUser ? "max-w-[78%]" : "max-w-[calc(100%-2.75rem)] flex-1"}`}>
        {isUser ? (
          <div>
            {message.attachments && message.attachments.length > 0 && (
              <div className="mb-1.5 flex flex-wrap justify-end gap-1.5">
                {message.attachments.map((a) => (
                  <span key={a.id} className="rounded-md border border-hermes-cyan/25 bg-hermes-cyan/[0.06]
                    px-2 py-1 font-mono text-[9.5px] text-hermes-muted">{a.name}</span>
                ))}
              </div>
            )}
            <div className="rounded-2xl rounded-tr-sm border border-hermes-cyan/25 bg-hermes-cyan/[0.09]
              px-4 py-2.5 text-[13.5px] leading-relaxed text-hermes-text-bright">
              {/* A reloaded session's history has no client-side attachment
                  chips — it only has the raw text that was actually sent,
                  fenced code and all, so it goes through the same markdown
                  renderer as the answer rather than showing literal backticks. */}
              <MarkdownMessage content={message.content} />
            </div>
          </div>
        ) : (
          <div className="min-w-0">
            {message.searches?.map((s, i) => (
              <SearchBlock key={`${s.query}-${i}`} entry={s} />
            ))}
            {message.thinking && <ThinkingBlock text={message.thinking} live={streaming && !message.content} />}

            {message.content ? (
              <div className={streaming ? "hermes-caret-host" : ""}>
                <MarkdownMessage content={message.content} />
                {streaming && <span className="hermes-caret" />}
              </div>
            ) : !message.thinking && !message.error ? (
              <ThinkingDots />
            ) : null}

            {message.error && (
              <div className="mt-1.5 rounded-lg border border-hermes-red/30 bg-hermes-red/10 px-3 py-2
                text-[11px] text-hermes-red">
                {message.error}
              </div>
            )}

            {message.interrupted && (
              <div className="mt-1.5 font-mono text-[10px] uppercase tracking-wider text-hermes-amber">
                ⏹ Interrompu — réponse partielle
              </div>
            )}

            {message.content && !streaming && (
              <div className="mt-1.5 flex items-center gap-2 opacity-0 transition-opacity group-hover:opacity-100">
                <button
                  onClick={copy}
                  className="flex items-center gap-1 rounded px-1.5 py-0.5 font-mono text-[9.5px]
                    uppercase tracking-wider text-hermes-dim transition-colors hover:text-hermes-cyan"
                >
                  {copied ? <Check size={9} /> : <Copy size={9} />}{copied ? "Copié" : "Copier"}
                </button>
                {message.routing?.model && (
                  <span className="font-mono text-[9.5px] text-hermes-dim">{message.routing.model}</span>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {isUser && (
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg
          bg-hermes-elevated ring-1 ring-hermes-border">
          <User size={13} className="text-hermes-muted" />
        </div>
      )}
    </motion.div>
  );
}

/** Reasoning models spend the first seconds emitting only `message.thinking`.
 *  Collapsed by default — visible enough to explain the wait, quiet enough
 *  not to compete with the answer. */
function ThinkingBlock({ text, live }: { text: string; live: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mb-2 overflow-hidden rounded-lg border border-hermes-violet/25 bg-hermes-violet/[0.05]">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left transition-colors hover:bg-hermes-violet/[0.08]"
      >
        <Brain size={11} className={`text-hermes-violet ${live ? "animate-pulse" : ""}`} />
        <span className="font-mono text-[10px] uppercase tracking-wider text-hermes-violet">
          {live ? "Raisonnement en cours…" : "Raisonnement"}
        </span>
        <ChevronDown size={11} className={`ml-auto text-hermes-violet/60 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0 }} animate={{ height: "auto" }} exit={{ height: 0 }}
            transition={{ duration: 0.2 }}
          >
            <pre className="max-h-56 overflow-y-auto whitespace-pre-wrap px-3 pb-2.5 pt-1
              font-mono text-[11px] leading-relaxed text-hermes-muted">{text}</pre>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/** One real internet search this turn (HOS-078) — collapsed by default,
 *  same pattern as ThinkingBlock. Shown as soon as the model asks for it
 *  ("Recherche…"), filled in once the real DuckDuckGo results come back —
 *  never a control that implies a search happened when it didn't. */
function SearchBlock({ entry }: { entry: SearchEntry }) {
  const [open, setOpen] = useState(false);
  const pending = entry.result === undefined;
  return (
    <div className="mb-2 overflow-hidden rounded-lg border border-hermes-cyan/25 bg-hermes-cyan/[0.05]">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left transition-colors hover:bg-hermes-cyan/[0.08]"
      >
        <Search size={11} className={`text-hermes-cyan ${pending ? "animate-pulse" : ""}`} />
        <span className="min-w-0 truncate font-mono text-[10px] uppercase tracking-wider text-hermes-cyan">
          {pending ? "Recherche…" : "Recherche"} {entry.query && `« ${entry.query} »`}
        </span>
        <ChevronDown size={11} className={`ml-auto shrink-0 text-hermes-cyan/60 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      <AnimatePresence initial={false}>
        {open && entry.result && (
          <motion.div
            initial={{ height: 0 }} animate={{ height: "auto" }} exit={{ height: 0 }}
            transition={{ duration: 0.2 }}
          >
            <pre className="max-h-56 overflow-y-auto whitespace-pre-wrap px-3 pb-2.5 pt-1
              font-mono text-[11px] leading-relaxed text-hermes-muted">{entry.result}</pre>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function ThinkingDots() {
  return (
    <div className="flex items-center gap-1.5 py-1.5">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="h-1.5 w-1.5 rounded-full bg-hermes-cyan"
          animate={{ opacity: [0.25, 1, 0.25] }}
          transition={{ duration: 1.1, repeat: Infinity, delay: i * 0.18 }}
        />
      ))}
    </div>
  );
}

function RoutingBadge({ routing }: { routing: StreamRouting }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 rounded-lg border border-hermes-border bg-hermes-elevated/60
          px-2.5 py-1.5 font-mono text-[10px] text-hermes-muted transition-all
          hover:border-hermes-cyan/40 hover:text-hermes-cyan"
      >
        <Brain size={11} />{routing.model}
        <Info size={9} className="opacity-60" />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.97 }}
            transition={{ duration: 0.16 }}
            className="absolute right-0 top-full z-20 mt-2 w-72 rounded-xl border border-hermes-border
              bg-hermes-card p-3.5 shadow-2xl"
          >
            <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-hermes-muted">
              Pourquoi ce modèle ?
            </div>
            <dl className="space-y-1.5 font-mono text-[11px]">
              <Row label="Modèle" value={routing.model} bright />
              <Row label="Tier" value={routing.tier} />
              <Row label="Rôle" value={routing.role} />
              <Row label="Raisonnement" value={routing.thinking ? "activé" : "désactivé"} />
              {routing.intent && <Row label="Intention" value={routing.intent} />}
            </dl>
            {routing.reason && (
              <p className="mt-2.5 border-t border-hermes-border/60 pt-2 text-[11px] leading-relaxed text-hermes-muted">
                {routing.reason}
              </p>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Row({ label, value, bright }: { label: string; value: string; bright?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-hermes-dim">{label}</dt>
      <dd className={`truncate ${bright ? "text-hermes-cyan" : "text-hermes-text"}`}>{value}</dd>
    </div>
  );
}

function EmptyState({ onPick }: { onPick: (prompt: string) => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className="flex h-full flex-col items-center justify-center px-6 text-center"
    >
      <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl
        bg-gradient-to-br from-hermes-cyan/20 to-hermes-violet/15 ring-1 ring-hermes-cyan/25">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/hermes-agent-logo.png" alt="Hermes" className="h-9 w-9 object-contain invert" />
      </div>
      <h2 className="text-[17px] font-semibold text-hermes-text-bright">Assistant Hermes</h2>
      <p className="mt-1.5 max-w-md text-[12.5px] leading-relaxed text-hermes-muted">
        Posez une question, ou partez d&apos;une action. Hermes choisit le modèle
        adapté à la tâche et vous montre lequel — et pourquoi.
      </p>
      <div className="mt-6 flex max-w-lg flex-wrap justify-center gap-2">
        {QUICK_ACTIONS.map((a) => (
          <button
            key={a.label}
            onClick={() => onPick(a.prompt)}
            className="flex items-center gap-2 rounded-lg border border-hermes-border bg-hermes-elevated/40
              px-3 py-2 text-[11.5px] text-hermes-muted transition-all
              hover:-translate-y-0.5 hover:border-hermes-cyan/40 hover:text-hermes-cyan"
          >
            <span>{a.icon}</span>{a.label}
          </button>
        ))}
      </div>
    </motion.div>
  );
}

/* ── Rail primitives ─────────────────────────────────────────────── */

function Chip({ children, tone }: { children: React.ReactNode; tone?: "violet" }) {
  const cls = tone === "violet"
    ? "border-hermes-violet/40 bg-hermes-violet/10 text-hermes-violet"
    : "border-hermes-border bg-hermes-elevated/60 text-hermes-muted";
  return (
    <span className={`rounded border px-1.5 py-0.5 font-mono text-[9.5px] uppercase tracking-wider ${cls}`}>
      {children}
    </span>
  );
}

function Meter({ label, detail, pct }: { label: string; detail: string; pct: number }) {
  const safe = Math.min(100, Math.max(0, pct));
  const tone = safe > 90 ? "from-hermes-red to-hermes-magenta"
    : safe > 70 ? "from-hermes-amber to-hermes-red"
    : "from-hermes-green to-hermes-cyan";
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <span className="truncate font-mono text-[10px] text-hermes-muted">{label}</span>
        <span className="shrink-0 font-mono text-[10px] tabular-nums text-hermes-text">{detail}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full border border-hermes-border/60 bg-hermes-bg-deep">
        <motion.div
          className={`h-full rounded-full bg-gradient-to-r ${tone}`}
          initial={{ width: 0 }} animate={{ width: `${safe}%` }}
          transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
        />
      </div>
    </div>
  );
}

