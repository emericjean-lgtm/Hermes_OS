"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useCockpitStore } from "@/hooks/use-store";
import { NAV_GROUPS } from "@/components/nav-model";
import { Command, Pin, PinOff } from "lucide-react";

/** The navigation rail.
 *
 *  Default state: a permanent narrow rail of icons — the machine's physical
 *  control strip — with names revealed on hover in a flyout, and ⌘K as the
 *  fast way to move around once you know the system. The pin toggle below
 *  reintroduces an expanded, labels-always-visible mode on top of that
 *  default, for anyone who wants the rail to read like a list rather than
 *  rely on hover/⌘K — the narrow rail remains the default either way.
 *
 *  Group boundaries are drawn as measured gaps and reference marks (S1…S5)
 *  rather than as text headers in the narrow mode, because the rail has no
 *  room for headers there and the ticks double as a position scale. */
export function Rail({ onOpenPalette }: { onOpenPalette: () => void }) {
  const { activeView, setActiveView, railPinned, toggleRailPin } = useCockpitStore();
  const [hovered, setHovered] = useState<string | null>(null);

  // Every consumer of --rail-w (instrument-bar, statusbar, cockpit-shell's
  // marginLeft) reads the same CSS custom property, so setting it once here
  // keeps the whole shell in lockstep without each of them needing their
  // own pinned-state check.
  useEffect(() => {
    document.documentElement.style.setProperty(
      "--rail-w",
      railPinned ? "var(--rail-w-expanded)" : "56px",
    );
    return () => {
      document.documentElement.style.setProperty("--rail-w", "56px");
    };
  }, [railPinned]);

  return (
    <aside
      className="fixed left-0 top-0 z-40 h-screen flex flex-col items-center
        border-r border-hermes-border bg-hermes-bg-deep/80 backdrop-blur-xl
        transition-[width] duration-200 ease-out"
      style={{ width: "var(--rail-w)" }}
      onMouseLeave={() => setHovered(null)}
    >
      {/* Lit inner edge — the rail is the closest surface to the sodium
          source, so it catches the most light. */}
      <div className="pointer-events-none absolute right-0 top-0 h-full w-px
        bg-gradient-to-b from-hermes-sodium/50 via-hermes-border-bright/40 to-transparent" />

      {/* ── Mark ── */}
      <div className={`flex w-full items-center shrink-0 mt-3 mb-1 ${railPinned ? "justify-between px-3" : "justify-center"}`}>
        <button
          onClick={() => setActiveView("dashboard")}
          aria-label="Hermes OS — Dashboard"
          className="group relative h-9 w-9 shrink-0 clip-corner-sm
            border border-hermes-border-bright/70 bg-hermes-elevated
            flex items-center justify-center overflow-hidden
            transition-colors hover:border-hermes-sodium/70"
        >
          {/* eslint-disable-next-line @next/next/no-img-element -- fixed 36px
              chip in a client component; next/image buys nothing here. */}
          <img src="/hermes-agent-logo.png" alt="" className="h-6 w-6 object-contain" />
          <span className="pointer-events-none absolute inset-0 bg-hermes-sodium/0
            group-hover:bg-hermes-sodium/10 transition-colors" />
        </button>
        {railPinned && (
          <button
            onClick={toggleRailPin}
            aria-label="Réduire le rail"
            aria-pressed={true}
            title="Réduire le rail"
            className="h-7 w-7 shrink-0 flex items-center justify-center rounded-md
              text-hermes-muted transition-all hover:text-hermes-sodium hover:bg-hermes-sodium/[0.08]"
          >
            <PinOff size={13} strokeWidth={1.8} />
          </button>
        )}
      </div>

      {!railPinned && (
        <>
          <div className="h-px w-6 bg-hermes-border shrink-0" />
          <button
            onClick={toggleRailPin}
            aria-label="Épingler le rail déployé"
            aria-pressed={false}
            title="Épingler le rail déployé"
            className="mt-1.5 h-6 w-6 shrink-0 flex items-center justify-center rounded-md
              text-hermes-dim transition-all hover:text-hermes-sodium hover:bg-hermes-sodium/[0.08]"
          >
            <Pin size={12} strokeWidth={1.8} />
          </button>
        </>
      )}

      {/* ── Groups ──
          Real gap found while verifying: 22 items + section marks overflow
          a ~1000px-tall viewport with zero visible hint that Deploy/System
          are reachable only by scrolling this 56px strip. The fade mask is
          a static top+bottom hint rather than a scroll-position-tracked one
          — cheap, CSS-only, and enough to say "there's more" without a
          scroll listener for a rail this narrow. */}
      <nav className="flex-1 w-full overflow-y-auto overflow-x-visible py-2
        [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        style={{
          maskImage: "linear-gradient(180deg, transparent 0, #000 14px, #000 calc(100% - 14px), transparent 100%)",
          WebkitMaskImage: "linear-gradient(180deg, transparent 0, #000 14px, #000 calc(100% - 14px), transparent 100%)",
        }}>
        {NAV_GROUPS.map((group, gi) => (
          <div key={group.label} className="relative mb-3 last:mb-0">
            {/* Section reference — a drawing callout, and a scale marker. */}
            <div className={`flex items-center h-4 ${railPinned ? "justify-start px-3" : "justify-center"}`}>
              <span className="num text-[8px] tracking-[0.14em] text-hermes-dim/70 select-none">
                {group.ref}{railPinned ? ` — ${group.label}` : ""}
              </span>
            </div>

            {group.items.map((item) => {
              const active = activeView === item.id;
              const Icon = item.icon;
              return (
                <div key={item.id} className="relative">
                  <button
                    onClick={() => setActiveView(item.id)}
                    onMouseEnter={() => setHovered(item.id)}
                    aria-label={item.label}
                    aria-current={active ? "page" : undefined}
                    className={`group relative w-full h-10 flex items-center
                      transition-colors duration-200
                      ${railPinned ? "justify-start gap-2.5 px-3" : "justify-center"}
                      ${active ? "text-hermes-sodium" : "text-hermes-muted hover:text-hermes-text"}`}
                  >
                    {/* Active carriage — one element sliding between entries,
                        so the eye tracks a moving part rather than a new
                        highlight appearing somewhere else. */}
                    {active && (
                      <motion.span
                        layoutId="rail-carriage"
                        transition={{ type: "spring", stiffness: 520, damping: 40 }}
                        className="absolute inset-x-1 inset-y-0.5 clip-corner-sm
                          bg-gradient-to-r from-hermes-sodium/18 to-hermes-sodium/[0.03]
                          border-l-2 border-hermes-sodium"
                        style={{ boxShadow: "inset 0 0 18px rgba(255,148,54,0.10)" }}
                      />
                    )}
                    {!active && (
                      <span className="absolute inset-x-1 inset-y-0.5 clip-corner-sm
                        bg-hermes-elevated/0 group-hover:bg-hermes-elevated/70 transition-colors" />
                    )}
                    <Icon
                      size={16}
                      strokeWidth={active ? 2.1 : 1.7}
                      className={`relative shrink-0 transition-transform duration-200
                        ${active ? "scale-105" : "group-hover:scale-110"}`}
                    />
                    {railPinned && (
                      <span className="relative truncate text-[12px] font-medium">
                        {item.label}
                      </span>
                    )}
                  </button>

                  {/* Flyout: the name, on demand. Anchored to the item so it
                      reads as an extension of the control rather than a
                      tooltip floating near the cursor. */}
                  <AnimatePresence>
                    {!railPinned && hovered === item.id && (
                      <motion.div
                        initial={{ opacity: 0, x: -6 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: -6 }}
                        transition={{ duration: 0.14, ease: [0.16, 1, 0.3, 1] }}
                        className="pointer-events-none absolute left-full top-1/2 -translate-y-1/2 ml-2 z-50"
                      >
                        <div className="clip-corner-sm border border-hermes-border-bright
                          bg-hermes-elevated/95 backdrop-blur-md px-2.5 py-1.5 whitespace-nowrap
                          shadow-panel flex items-baseline gap-2">
                          <span className="text-[11.5px] font-medium text-hermes-text">
                            {item.label}
                          </span>
                          <span className="num text-[8.5px] text-hermes-dim tracking-[0.12em]">
                            {group.ref}.{String(gi + 1).padStart(2, "0")}
                          </span>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              );
            })}
          </div>
        ))}
      </nav>

      {/* ── Command entry ── */}
      <div className="w-full px-2 pb-3 pt-2 shrink-0 border-t border-hermes-border/70">
        <button
          onClick={onOpenPalette}
          aria-label="Ouvrir la palette de commandes"
          onMouseEnter={() => setHovered("__cmd")}
          className={`group relative w-full h-9 flex items-center
            clip-corner-sm border border-hermes-border text-hermes-muted
            hover:text-hermes-sodium hover:border-hermes-sodium/50
            hover:bg-hermes-sodium/[0.07] transition-all
            ${railPinned ? "justify-start gap-2.5 px-3" : "justify-center"}`}
        >
          <Command size={14} strokeWidth={1.8} className="shrink-0" />
          {railPinned && (
            <span className="text-[11.5px] font-medium">
              Commandes <span className="num text-[9px] text-hermes-dim ml-1">⌘K</span>
            </span>
          )}
          <AnimatePresence>
            {!railPinned && hovered === "__cmd" && (
              <motion.span
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -6 }}
                transition={{ duration: 0.14 }}
                className="pointer-events-none absolute left-full ml-2 z-50
                  clip-corner-sm border border-hermes-border-bright bg-hermes-elevated/95
                  backdrop-blur-md px-2.5 py-1.5 whitespace-nowrap shadow-panel
                  text-[11.5px] text-hermes-text"
              >
                Commandes <span className="num text-[9px] text-hermes-dim ml-1">⌘K</span>
              </motion.span>
            )}
          </AnimatePresence>
        </button>
      </div>
    </aside>
  );
}
