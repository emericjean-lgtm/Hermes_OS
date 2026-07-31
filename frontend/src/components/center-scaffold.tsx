"use client";

import React from "react";
import { motion } from "framer-motion";
import { Card, Badge, Beacon } from "@/components/ui/card";

/** Éléments partagés par les Centers, pour qu'ils se ressemblent tous.
 *
 *  Chaque Center doit présenter des statistiques, un tableau principal, des
 *  filtres, une recherche, et des états de chargement / vide / erreur. Les
 *  réécrire vingt-cinq fois produirait vingt-cinq variantes divergentes : ces
 *  briques les rendent identiques par construction (P-001), et c'est aussi ce
 *  qui permet à la refonte cyberpunk de traverser tout le cockpit en ne
 *  touchant que ce fichier et ui/card.tsx.
 */

export function CenterHeader({
  title,
  subtitle,
  right,
}: {
  title: string;
  subtitle: string;
  right?: React.ReactNode;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className="relative flex items-start justify-between gap-4 mb-6 pb-4 border-b border-hermes-border/60"
    >
      {/* Rail lumineux sous le titre : large, puis fondu. */}
      <div className="absolute bottom-0 left-0 h-px w-48 bg-gradient-to-r from-hermes-cyan via-hermes-violet/50 to-transparent" />
      <div className="min-w-0">
        <div className="flex items-center gap-2.5">
          <span className="h-4 w-[3px] rounded-full bg-gradient-to-b from-hermes-cyan to-hermes-magenta shadow-glow-cyan" />
          <h1 className="text-xl font-bold font-mono tracking-tight text-gradient-cyan">
            {title}
          </h1>
        </div>
        <p className="text-[11px] text-hermes-muted mt-1.5 font-mono pl-[14px]">{subtitle}</p>
      </div>
      {right && <div className="flex items-center gap-2 shrink-0">{right}</div>}
    </motion.div>
  );
}

export function StatGrid({
  stats,
  columns = 4,
}: {
  stats: { label: string; value: React.ReactNode; tone?: "ok" | "warn" | "bad" }[];
  columns?: number;
}) {
  const tone = {
    ok: { text: "text-hermes-green", glow: "text-glow-green", rail: "from-hermes-green/70" },
    warn: { text: "text-hermes-amber", glow: "text-glow-amber", rail: "from-hermes-amber/70" },
    bad: { text: "text-hermes-red", glow: "text-glow-red", rail: "from-hermes-red/70" },
  } as const;
  const neutral = {
    text: "text-hermes-cyan",
    glow: "text-glow-cyan",
    rail: "from-hermes-cyan/70",
  };

  return (
    <div
      className="grid gap-3 mb-6"
      style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
    >
      {stats.map((s, i) => {
        const t = s.tone ? tone[s.tone] : neutral;
        return (
          <motion.div
            key={s.label}
            initial={{ opacity: 0, y: 12, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.45, delay: i * 0.05, ease: [0.16, 1, 0.3, 1] }}
            className="group relative rounded-xl glass neon-edge bracket p-3 text-center overflow-hidden
              transition-all duration-300 hover:-translate-y-0.5 hover:shadow-glow-cyan"
          >
            <div
              className={`absolute bottom-0 left-0 h-[2px] w-6 bg-gradient-to-r ${t.rail} to-transparent
                transition-all duration-500 group-hover:w-full`}
            />
            <div className="text-[10px] text-hermes-muted font-mono uppercase tracking-[0.12em]">
              {s.label}
            </div>
            <div className={`text-2xl font-bold font-mono tabular-nums mt-1 ${t.text} ${t.glow}`}>
              {s.value}
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}

export function Toolbar({
  search,
  onSearch,
  placeholder = "Rechercher…",
  filters,
  activeFilter,
  onFilter,
  actions,
}: {
  search: string;
  onSearch: (v: string) => void;
  placeholder?: string;
  filters?: string[];
  activeFilter?: string;
  onFilter?: (v: string) => void;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 mb-4">
      <div className="relative flex-1 min-w-[220px] group">
        {/* Chevron d'invite : signale la zone de saisie sans placeholder bavard. */}
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-hermes-cyan/60 font-mono text-xs pointer-events-none
          group-focus-within:text-hermes-cyan transition-colors">
          ›
        </span>
        <input
          type="text"
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          placeholder={placeholder}
          className="w-full glass rounded-lg border border-hermes-border pl-7 pr-3 py-2 text-sm
            text-hermes-text font-mono placeholder:text-hermes-dim
            focus:outline-none focus:border-hermes-cyan/60 focus:shadow-glow-cyan
            transition-all duration-200"
        />
      </div>
      {filters?.map((f) => (
        <button
          key={f}
          onClick={() => onFilter?.(f)}
          className={`sweep clip-corner-sm px-3 py-2 rounded-md text-[11px] font-mono font-semibold
            uppercase tracking-wider border transition-all duration-200 active:scale-[0.97] ${
              activeFilter === f
                ? "border-hermes-cyan/60 bg-hermes-cyan/10 text-hermes-cyan shadow-glow-cyan"
                : "border-hermes-border text-hermes-muted hover:text-hermes-text hover:border-hermes-border-bright hover:bg-hermes-elevated/60"
            }`}
        >
          {f}
        </button>
      ))}
      {actions}
    </div>
  );
}

/** Rend l'un des quatre états d'une requête, jamais un tableau vide muet. */
export function AsyncPanel({
  title,
  subtitle,
  isLoading,
  isError,
  error,
  isEmpty,
  emptyLabel,
  children,
  action,
  live,
}: {
  title: string;
  subtitle?: string;
  isLoading: boolean;
  isError: boolean;
  error?: unknown;
  isEmpty: boolean;
  emptyLabel: string;
  children: React.ReactNode;
  action?: React.ReactNode;
  live?: boolean;
}) {
  return (
    <Card title={title} subtitle={subtitle} action={action} live={live && !isLoading && !isError}>
      {isLoading && <PanelLoading />}
      {!isLoading && isError && (
        <div className="flex items-start gap-2.5 py-4">
          <span className="text-hermes-red text-glow-red font-mono text-sm leading-none mt-0.5">⚠</span>
          <div>
            <div className="text-[11px] text-hermes-red font-mono font-semibold uppercase tracking-wider">
              Endpoint injoignable
            </div>
            <div className="text-[11px] text-hermes-muted font-mono mt-1 break-all">
              {error instanceof Error ? error.message : "Erreur inconnue"}
            </div>
          </div>
        </div>
      )}
      {!isLoading && !isError && isEmpty && (
        <div className="flex items-center gap-2.5 py-5 justify-center">
          <span className="text-hermes-dim font-mono text-xs">◇</span>
          <span className="text-[11px] text-hermes-muted font-mono">{emptyLabel}</span>
        </div>
      )}
      {!isLoading && !isError && !isEmpty && children}
    </Card>
  );
}

/** Barre de chargement indéterminée : un segment lumineux qui traverse. */
export function PanelLoading() {
  return (
    <div className="py-5">
      <div className="relative h-[3px] w-full overflow-hidden rounded-full bg-hermes-bg-deep border border-hermes-border/50">
        <div
          className="absolute inset-y-0 w-1/3 rounded-full bg-gradient-to-r from-transparent via-hermes-cyan to-transparent shadow-glow-cyan"
          style={{ animation: "shimmer 1.1s ease-in-out infinite" }}
        />
      </div>
      <div className="text-[10px] text-hermes-muted font-mono mt-2.5 text-center uppercase tracking-[0.2em]">
        Acquisition…
      </div>
    </div>
  );
}

export function DataTable<T>({
  rows,
  columns,
  rowKey,
}: {
  rows: T[];
  columns: { header: string; cell: (row: T) => React.ReactNode; align?: "right" }[];
  rowKey: (row: T, i: number) => string;
}) {
  return (
    <div className="overflow-x-auto -mx-1">
      <table className="w-full text-xs border-separate border-spacing-0">
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.header}
                className={`sticky top-0 z-10 bg-hermes-card/95 backdrop-blur py-2 px-3
                  text-hermes-cyan/70 font-mono uppercase text-[10px] tracking-[0.12em] font-semibold
                  border-b border-hermes-border ${
                    c.align === "right" ? "text-right" : "text-left"
                  }`}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <motion.tr
              key={rowKey(row, i)}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3, delay: Math.min(i * 0.02, 0.3) }}
              className="group transition-colors hover:bg-hermes-cyan/[0.04]"
            >
              {columns.map((c, ci) => (
                <td
                  key={c.header}
                  className={`relative py-2 px-3 text-hermes-text font-mono
                    border-b border-hermes-border/30 ${
                      c.align === "right" ? "text-right" : ""
                    }`}
                >
                  {/* Marqueur de survol sur la première colonne uniquement. */}
                  {ci === 0 && (
                    <span className="absolute left-0 top-1/2 -translate-y-1/2 h-0 w-[2px] rounded-full
                      bg-hermes-cyan shadow-glow-cyan transition-all duration-200 group-hover:h-[70%]" />
                  )}
                  {c.cell(row)}
                </td>
              ))}
            </motion.tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Pastille d'état live, alimentée par le flux WebSocket quand il est branché. */
export function LiveBadge({ connected }: { connected: boolean }) {
  return (
    <Badge variant={connected ? "success" : "default"}>
      {connected && <Beacon tone="green" />}
      {connected ? "LIVE" : "HORS LIGNE"}
    </Badge>
  );
}
