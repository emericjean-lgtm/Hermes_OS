"use client";

import React from "react";
import { Card, Badge } from "@/components/ui/card";

/** Éléments partagés par les Centers, pour qu'ils se ressemblent tous.
 *
 *  Chaque Center doit présenter des statistiques, un tableau principal, des
 *  filtres, une recherche, et des états de chargement / vide / erreur. Les
 *  réécrire huit fois produirait huit variantes divergentes : ces briques les
 *  rendent identiques par construction (P-001).
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
    <div className="flex items-start justify-between mb-6">
      <div>
        <h1 className="text-xl font-bold text-hermes-text font-mono tracking-tight">
          {title}
        </h1>
        <p className="text-xs text-hermes-muted mt-1">{subtitle}</p>
      </div>
      {right && <div className="flex items-center gap-2">{right}</div>}
    </div>
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
    ok: "text-hermes-green",
    warn: "text-hermes-amber",
    bad: "text-hermes-red",
  } as const;
  return (
    <div
      className="grid gap-3 mb-6"
      style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
    >
      {stats.map((s) => (
        <div
          key={s.label}
          className="bg-hermes-card border border-hermes-border rounded-lg p-3 text-center"
        >
          <div className="text-[10px] text-hermes-muted font-mono uppercase">
            {s.label}
          </div>
          <div
            className={`text-lg font-bold font-mono mt-0.5 ${
              s.tone ? tone[s.tone] : "text-hermes-text"
            }`}
          >
            {s.value}
          </div>
        </div>
      ))}
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
      <input
        type="text"
        value={search}
        onChange={(e) => onSearch(e.target.value)}
        placeholder={placeholder}
        className="flex-1 min-w-[200px] bg-hermes-bg border border-hermes-border rounded-lg px-3 py-2 text-sm text-hermes-text font-mono focus:outline-none focus:border-hermes-amber/50 placeholder:text-hermes-muted/50"
      />
      {filters?.map((f) => (
        <button
          key={f}
          onClick={() => onFilter?.(f)}
          className={`px-3 py-2 rounded-lg text-xs font-mono border transition-colors ${
            activeFilter === f
              ? "border-hermes-amber/50 bg-hermes-amber/10 text-hermes-amber-bright"
              : "border-hermes-border text-hermes-muted hover:text-hermes-text"
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
}) {
  return (
    <Card title={title} subtitle={subtitle} action={action}>
      {isLoading && (
        <div className="text-xs text-hermes-muted font-mono py-4">Chargement…</div>
      )}
      {!isLoading && isError && (
        <div className="text-xs text-hermes-red font-mono py-4">
          {error instanceof Error ? error.message : "Endpoint injoignable"}
        </div>
      )}
      {!isLoading && !isError && isEmpty && (
        <div className="text-xs text-hermes-muted font-mono py-4">{emptyLabel}</div>
      )}
      {!isLoading && !isError && !isEmpty && children}
    </Card>
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
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-hermes-border">
            {columns.map((c) => (
              <th
                key={c.header}
                className={`py-2 px-3 text-hermes-muted font-mono uppercase text-[10px] ${
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
            <tr
              key={rowKey(row, i)}
              className="border-b border-hermes-border/40 hover:bg-hermes-card/60"
            >
              {columns.map((c) => (
                <td
                  key={c.header}
                  className={`py-2 px-3 text-hermes-text font-mono ${
                    c.align === "right" ? "text-right" : ""
                  }`}
                >
                  {c.cell(row)}
                </td>
              ))}
            </tr>
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
      {connected ? "LIVE" : "HORS LIGNE"}
    </Badge>
  );
}
