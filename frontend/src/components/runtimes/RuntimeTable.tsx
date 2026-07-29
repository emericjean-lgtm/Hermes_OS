"use client";
import { useMemo, useState } from "react";
import { useReactTable, getCoreRowModel, getSortedRowModel, flexRender, type SortingState, type ColumnDef } from "@tanstack/react-table";
import { useRuntimeList } from "@/hooks/use-runtimes";
import type { RuntimeInfo } from "@/types/mission-control";
import { Search, ArrowUpDown, Cpu } from "lucide-react";

const STATUS_COLORS: Record<string, string> = { healthy: "var(--color-success)", degraded: "var(--color-warning)", unhealthy: "var(--color-danger)", available: "var(--color-accent)" };

interface Props { onSelect: (name: string) => void; selectedName: string | null; }

export default function RuntimeTable({ onSelect, selectedName }: Props) {
  const { data: runtimes, isLoading } = useRuntimeList();
  const [sorting, setSorting] = useState<SortingState>([{ id: "status", desc: false }]);
  const [filter, setFilter] = useState("");
  const data = useMemo(() => runtimes ?? [], [runtimes]);

  const columns = useMemo<ColumnDef<RuntimeInfo>[]>(() => [
    { accessorKey: "name", header: "Runtime", cell: ({ row }) => <div className="flex items-center gap-2"><span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: STATUS_COLORS[row.original.status] ?? "#64748b" }} /><span className="text-sm font-medium">{row.original.name}</span></div> },
    { accessorKey: "status", header: "Status", cell: ({ getValue }) => <span className="text-xs" style={{ color: STATUS_COLORS[getValue() as string] ?? "" }}>{(getValue() as string).toUpperCase()}</span> },
    { accessorKey: "healthy", header: "Healthy", cell: ({ getValue }) => { const v = getValue() as boolean; return <span className={`text-xs ${v ? "text-[var(--color-success)]" : "text-[var(--color-danger)]"}`}>{v ? "Yes" : "No"}</span>; }},
    { accessorKey: "avg_latency_ms", header: "Latency", cell: ({ getValue }) => <span className="text-xs text-[var(--color-text-muted)]">{(getValue() as number / 1000).toFixed(2)}s</span> },
    { accessorKey: "reliability_score", header: "Reliability", cell: ({ getValue }) => { const v = getValue() as number; return <span className={`text-xs ${v >= 0.9 ? "text-[var(--color-success)]" : v >= 0.7 ? "text-[var(--color-warning)]" : "text-[var(--color-danger)]"}`}>{(v * 100).toFixed(0)}%</span>; }},
    { accessorKey: "performance_score", header: "Perf.", cell: ({ getValue }) => <span className="text-xs text-[var(--color-text-muted)]">{(getValue() as number * 100).toFixed(0)}%</span> },
    { accessorKey: "success_rate", header: "Success", cell: ({ getValue }) => <span className="text-xs text-[var(--color-text-muted)]">{(getValue() as number).toFixed(1)}%</span> },
    { accessorKey: "executions", header: "Execs", cell: ({ getValue }) => <span className="text-xs text-[var(--color-text-muted)]">{getValue() as number}</span> },
    { accessorKey: "failures", header: "Fail", cell: ({ getValue }) => { const v = getValue() as number; return <span className={`text-xs ${v > 0 ? "text-[var(--color-danger)]" : "text-[var(--color-text-muted)]"}`}>{v}</span>; }},
  ], []);

  const filtered = useMemo(() => data.filter(r => !filter || r.name.toLowerCase().includes(filter.toLowerCase()) || r.status.includes(filter)), [data, filter]);
  const table = useReactTable({ data: filtered, columns, state: { sorting }, onSortingChange: setSorting, getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel() });

  return <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
    <div className="flex items-center justify-between mb-3">
      <div className="flex items-center gap-2"><Cpu size={16} className="text-[var(--color-accent)]" /><h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Runtimes ({data.length})</h3></div>
      <div className="relative"><Search size={10} className="absolute left-2 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" /><input value={filter} onChange={e => setFilter(e.target.value)} placeholder="Search..." className="w-28 rounded bg-[var(--color-bg-base)] py-1 pl-6 pr-2 text-[10px] text-[var(--color-text-primary)] outline-none ring-1 ring-white/10 focus:ring-[var(--color-accent)]" /></div>
    </div>
    <div className="overflow-x-auto"><table className="w-full text-xs">
      <thead>{table.getHeaderGroups().map(hg => <tr key={hg.id} className="border-b border-white/5">{hg.headers.map(h => <th key={h.id} className="cursor-pointer pb-2 pr-2 text-left text-[10px] font-medium text-[var(--color-text-muted)]" onClick={h.column.getToggleSortingHandler()}><div className="flex items-center gap-1">{flexRender(h.column.columnDef.header, h.getContext())}<ArrowUpDown size={10} /></div></th>)}</tr>)}</thead>
      <tbody>{table.getRowModel().rows.length === 0 ? <tr><td colSpan={9} className="py-8 text-center text-xs text-[var(--color-text-muted)]">No runtimes</td></tr> : table.getRowModel().rows.map(row => <tr key={row.id} onClick={() => onSelect(row.original.name)} className={`cursor-pointer border-b border-white/5 last:border-0 hover:bg-white/[0.02] ${selectedName === row.original.name ? "bg-[var(--color-accent)]/5" : ""}`}>{row.getVisibleCells().map(cell => <td key={cell.id} className="py-2 pr-2">{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}</tr>)}</tbody>
    </table></div>
  </div>;
}
