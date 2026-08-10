"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useCockpitStore } from "@/hooks/use-store";
import { ALL_NAV_ITEMS } from "@/components/nav-model";
import { CornerDownLeft, Search } from "lucide-react";

/** ⌘K navigation.
 *
 *  With 22 screens, the fastest path between two of them is typing, not
 *  hunting a menu. This is the primary navigation for anyone who knows the
 *  system; the rail is for everyone else and for orientation.
 *
 *  Matching is over label + group + keywords, so "vram" finds Runtime and
 *  "aegis" finds Security even though neither word appears in the menu. */
export function CommandPalette({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { setActiveView, activeView } = useCockpitStore();
  const [q, setQ] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  const results = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return ALL_NAV_ITEMS;
    return ALL_NAV_ITEMS.filter((i) =>
      `${i.label} ${i.group} ${i.keywords ?? ""}`.toLowerCase().includes(needle),
    );
  }, [q]);

  // Reset per opening rather than persisting the last query — reopening the
  // palette should feel like a fresh instrument, not a resumed session.
  useEffect(() => {
    if (open) {
      setQ("");
      setCursor(0);
      // Focus after the entrance transition starts, or the browser scrolls
      // the dialog into place mid-animation.
      const t = window.setTimeout(() => inputRef.current?.focus(), 40);
      return () => window.clearTimeout(t);
    }
  }, [open]);

  useEffect(() => setCursor(0), [q]);

  // Keep the highlighted row in view when arrowing past the fold.
  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(`[data-idx="${cursor}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  const commit = (id: string) => {
    setActiveView(id);
    onClose();
  };

  // A native window listener, not React's onKeyDown prop — matching the
  // ⌘K toggle's own pattern in cockpit-shell.tsx. React's synthetic event
  // delegation and a plain addEventListener normally see the same key
  // presses; this only exists as a separate effect because live testing
  // found a real asymmetry between the two paths worth not depending on —
  // a native listener is the one already proven reliable for every other
  // keyboard shortcut in this shell. Reading `results`/`cursor` via refs
  // rather than closing over the render's values, since this effect only
  // re-subscribes on `open`, not on every keystroke.
  const resultsRef = useRef(results);
  resultsRef.current = results;
  const cursorRef = useRef(cursor);
  cursorRef.current = cursor;

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setCursor((c) => (resultsRef.current.length ? (c + 1) % resultsRef.current.length : 0));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setCursor((c) =>
          resultsRef.current.length
            ? (c - 1 + resultsRef.current.length) % resultsRef.current.length
            : 0,
        );
      } else if (e.key === "Enter") {
        e.preventDefault();
        const item = resultsRef.current[cursorRef.current];
        if (item) commit(item.id);
      } else if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          // AnimatePresence tracks children by key; without one the exit
          // animation plays but the node is never removed — leaving this
          // full-screen overlay in the DOM, invisible and swallowing every
          // click in the cockpit.
          key="command-palette"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.16 }}
          className="fixed inset-0 z-[9990] flex items-start justify-center pt-[14vh] px-4"
          onMouseDown={onClose}
        >
          <div className="absolute inset-0 bg-hermes-bg-deep/75 backdrop-blur-sm" />

          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label="Palette de commandes"
            initial={{ opacity: 0, y: -14, scale: 0.985 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.99 }}
            transition={{ type: "spring", stiffness: 420, damping: 34 }}
            onMouseDown={(e) => e.stopPropagation()}
            className="relative w-full max-w-[560px] clip-corner border border-hermes-border-bright
              glass-bright shadow-panel overflow-hidden"
          >
            {/* Sodium seam along the top edge — the palette is the system
                answering, and sodium is the system's voice. */}
            <div className="h-px w-full bg-gradient-to-r from-hermes-sodium via-hermes-sodium/30 to-transparent" />

            <div className="flex items-center gap-3 px-4 py-3.5 border-b border-hermes-border">
              <Search size={14} className="text-hermes-sodium shrink-0" strokeWidth={2} />
              <input
                ref={inputRef}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Aller à un écran…"
                aria-label="Rechercher un écran"
                className="flex-1 bg-transparent border-0 outline-none text-[14px]
                  text-hermes-text placeholder:text-hermes-dim"
              />
              <kbd className="num text-[9px] px-1.5 py-0.5 border border-hermes-border text-hermes-dim">
                ESC
              </kbd>
            </div>

            <div ref={listRef} className="max-h-[46vh] overflow-y-auto py-1.5">
              {results.length === 0 && (
                <div className="px-4 py-8 text-center">
                  <div className="text-[12.5px] text-hermes-muted">Aucun écran ne correspond</div>
                  <div className="num text-[10px] text-hermes-dim mt-1">
                    {ALL_NAV_ITEMS.length} écrans disponibles
                  </div>
                </div>
              )}

              {results.map((item, i) => {
                const Icon = item.icon;
                const active = i === cursor;
                const current = item.id === activeView;
                return (
                  <button
                    key={item.id}
                    data-idx={i}
                    onMouseEnter={() => setCursor(i)}
                    onClick={() => commit(item.id)}
                    className={`group relative w-full flex items-center gap-3 px-4 py-2.5 text-left
                      transition-colors ${active ? "bg-hermes-sodium/[0.09]" : "hover:bg-hermes-elevated/50"}`}
                  >
                    {active && (
                      <motion.span
                        layoutId="cmd-cursor"
                        transition={{ type: "spring", stiffness: 600, damping: 42 }}
                        className="absolute left-0 inset-y-0 w-[2px] bg-hermes-sodium"
                      />
                    )}
                    <Icon
                      size={15}
                      strokeWidth={1.8}
                      className={active ? "text-hermes-sodium" : "text-hermes-muted"}
                    />
                    <span className={`text-[13px] flex-1 ${active ? "text-hermes-text" : "text-hermes-muted"}`}>
                      {item.label}
                    </span>
                    {current && (
                      <span className="num text-[9px] tracking-[0.14em] text-hermes-sodium/70">
                        ACTUEL
                      </span>
                    )}
                    <span className="tech-label !text-[8.5px] shrink-0">{item.group}</span>
                    {active && (
                      <CornerDownLeft size={12} className="text-hermes-sodium shrink-0" />
                    )}
                  </button>
                );
              })}
            </div>

            <div className="flex items-center gap-4 px-4 py-2 border-t border-hermes-border
              bg-hermes-bg-deep/40">
              <Hint keys="↑↓" label="naviguer" />
              <Hint keys="↵" label="ouvrir" />
              <span className="ml-auto num text-[9px] text-hermes-dim">
                {results.length}/{ALL_NAV_ITEMS.length}
              </span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function Hint({ keys, label }: { keys: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <kbd className="num text-[9px] px-1 py-0.5 border border-hermes-border text-hermes-dim">
        {keys}
      </kbd>
      <span className="text-[10px] text-hermes-dim">{label}</span>
    </span>
  );
}
