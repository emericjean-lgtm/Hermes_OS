"use client";

import React, { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Clock, History, MessageSquarePlus } from "lucide-react";
import { conversationClient } from "@/services/client";

/**
 * Slash commands (HOS-075) — a small, honest set.
 *
 * `/clean` and `/resume` wrap real, pre-existing capabilities the Assistant
 * never surfaced (a fresh session, and `GET /conversation/sessions` which
 * had zero UI callers before this). `/compact` has no real backend
 * counterpart yet — Claude Code's version summarises history to reclaim
 * context, and Hermes has no such pass. It stays in the menu so the
 * command namespace is discoverable, but selecting it says so plainly
 * instead of quietly doing nothing or doing something else.
 */

export interface SlashCommand {
  cmd: string;
  label: string;
  description: string;
  icon: React.ElementType;
  implemented: boolean;
}

export const SLASH_COMMANDS: SlashCommand[] = [
  { cmd: "/clean", label: "/clean", description: "Démarrer une nouvelle conversation",
    icon: MessageSquarePlus, implemented: true },
  { cmd: "/resume", label: "/resume", description: "Reprendre une session précédente",
    icon: History, implemented: true },
  { cmd: "/compact", label: "/compact", description: "Pas encore implémenté — aucun résumé de l'historique n'existe côté serveur",
    icon: AlertTriangle, implemented: false },
];

export function matchSlashCommands(input: string): SlashCommand[] {
  if (!input.startsWith("/") || input.includes(" ")) return [];
  const q = input.slice(1).toLowerCase();
  return SLASH_COMMANDS.filter((c) => c.cmd.slice(1).startsWith(q));
}

export function SlashCommandMenu({
  matches, activeIndex, onPick,
}: {
  matches: SlashCommand[];
  activeIndex: number;
  onPick: (cmd: SlashCommand) => void;
}) {
  if (matches.length === 0) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 6 }}
      transition={{ duration: 0.13 }}
      className="absolute bottom-full left-0 z-20 mb-2 w-80 overflow-hidden rounded-xl
        border border-hermes-border bg-hermes-card p-1.5 shadow-2xl"
    >
      {matches.map((c, i) => (
        <button
          key={c.cmd}
          onClick={() => onPick(c)}
          className={`flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors
            ${i === activeIndex ? "bg-hermes-cyan/[0.09]" : "hover:bg-hermes-elevated/60"}`}
        >
          <c.icon size={13} className={`mt-0.5 shrink-0 ${c.implemented ? "text-hermes-cyan" : "text-hermes-amber"}`} />
          <span className="min-w-0 flex-1">
            <span className="font-mono text-[11.5px] text-hermes-text-bright">{c.label}</span>
            <span className="line-clamp-1 block text-[10px] text-hermes-muted">{c.description}</span>
          </span>
        </button>
      ))}
    </motion.div>
  );
}

interface SessionSummary {
  session_id: string;
  status: string;
  message_count: number;
  updated_at: string;
}

export function SessionPicker({
  currentSessionId, onPick, onClose,
}: {
  currentSessionId: string;
  onPick: (sessionId: string) => void;
  onClose: () => void;
}) {
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await conversationClient.sessions();
        if (!cancelled) setSessions(data.sessions as SessionSummary[]);
      } catch {
        if (!cancelled) setError("Impossible de charger les sessions.");
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const sorted = useMemo(
    () => [...(sessions ?? [])].sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
    [sessions],
  );

  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center bg-hermes-bg-deep/70 backdrop-blur-sm"
      onClick={onClose}>
      <motion.div
        initial={{ opacity: 0, scale: 0.97, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.97, y: 8 }}
        transition={{ duration: 0.16 }}
        onClick={(e) => e.stopPropagation()}
        className="max-h-[70vh] w-[420px] overflow-hidden rounded-2xl border border-hermes-border bg-hermes-card shadow-2xl"
      >
        <div className="flex items-center gap-2 border-b border-hermes-border/60 px-4 py-3">
          <History size={13} className="text-hermes-cyan" />
          <h3 className="font-mono text-[11px] uppercase tracking-[0.14em] text-hermes-muted">
            Reprendre une session
          </h3>
        </div>
        <div className="max-h-[55vh] overflow-y-auto p-1.5">
          {error && <p className="px-3 py-3 text-[11px] text-hermes-red">{error}</p>}
          {!error && sessions === null && (
            <p className="px-3 py-3 text-[11px] text-hermes-dim">Chargement…</p>
          )}
          {!error && sessions !== null && sorted.length === 0 && (
            <p className="px-3 py-3 text-[11px] text-hermes-dim">Aucune session enregistrée.</p>
          )}
          {sorted.map((s) => (
            <button
              key={s.session_id}
              onClick={() => onPick(s.session_id)}
              className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left transition-colors
                ${s.session_id === currentSessionId ? "bg-hermes-cyan/[0.09]" : "hover:bg-hermes-elevated/60"}`}
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate font-mono text-[11px] text-hermes-text-bright">
                  {s.session_id}
                </span>
                <span className="mt-0.5 flex items-center gap-2 text-[10px] text-hermes-muted">
                  <Clock size={9} />{new Date(s.updated_at).toLocaleString("fr-FR")}
                  <span>· {s.message_count} message(s)</span>
                </span>
              </span>
              {s.session_id === currentSessionId && (
                <span className="shrink-0 rounded border border-hermes-cyan/40 bg-hermes-cyan/10
                  px-1.5 py-0.5 font-mono text-[8.5px] uppercase text-hermes-cyan">active</span>
              )}
            </button>
          ))}
        </div>
      </motion.div>
    </div>
  );
}
