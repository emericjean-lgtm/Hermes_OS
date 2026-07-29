"use client";

import { useMemo, useState } from "react";
import { useReactTable, getCoreRowModel, getSortedRowModel, getFilteredRowModel, flexRender, type SortingState, type ColumnDef } from "@tanstack/react-table";
import { useAgents } from "@/hooks/use-agents";
import type { AgentInfo } from "@/types/mission-control";
import { Search, ArrowUpDown, Bot } from "lucide-react";

const STATE_COLORS: Record<string, string> = {
  CREATED: "var(--color-text-muted)", READY: "var(--color-accent)", SCHEDULED: "var(--color-accent)",
  RUNNING: "var(--color-accent)", PAUSED: "var(--color-warning)", WAITING: "var(--color-warning)",
  COMPLETED: "var(--color-success)", FAILED: "var(--color-danger)", CANCELLED: "var(--color-text-muted)", TIMEOUT: "var(--color-danger)",
};

interface AgentTableProps {
  onSelect: (id: string) => void;
  selectedId: string | null;
}

export default function AgentTable({ onSelect, selectedId }: AgentTableProps) {
  const { data: agents, isLoading } = useAgents();
  const [sorting, setSorting] = useState<SortingState>([{ id: "state", desc: false }]);
  const [filter, setFilter] = useState("");

  const data = useMemo(() => agents ?? [], [agents]);

  const columns = useMemo<ColumnDef<AgentInfo>[]>(() => [
    { accessorKey: "name", header: "Agent", cell: ({ row }) => (
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: STATE_COLORS[row.original.state] ?? "var(--color-text-muted)" }} />
        <span className="text-sm font-medium">{row.original.name}</span>
      </div>
    )},
    { accessorKey: "state", header: "State", cell: ({ getValue }) => <span className="text-xs uppercase" style={{ color: STATE_COLORS[getValue() as string] ?? "" }}>{getValue() as string}</span> },
    { accessorKey: "runtime", header: "Runtime", cell: ({ getValue }) => <span className="text-xs text-[var(--color-text-muted)]">{getValue() as string}</span> },
    { accessorKey: "mission_id", header: "Mission", cell: ({ getValue }) => <span className="text-xs text-[var(--color-text-muted)]">{(getValue() as string)?.slice(0, 8) ?? "—"}</span> },
    { accessorKey: "duration_ms", header: "Duration", cell: ({ getValue }) => { const v = getValue() as number | null; return <span className="text-xs text-[var(--color-text-muted)]">{v ? `${(v / 1000).toFixed(1)}s` : "—"}</span>; }},
    { accessorKey: "retries", header: "Retries", cell: ({ getValue }) => { const v = getValue() as number; return <span className={`text-xs ${v > 0 ? "text-[var(--color-warning)]" : "text-[var(--color-text-muted)]"}`}>{v}</span>; }},
    { accessorKey: "progress", header: "Progress", cell: ({ getValue }) => { const v = getValue() as number; return <div className="flex items-center gap-1"><div className="h-1.5 w-10 rounded-full bg-white/10"><div className="h-full rounded-full bg-[var(--color-accent)]" style={{ width: `${v}%` }} /></div><span className="text-[10px] text-[var(--color-text-muted)]">{v}%</span></div>; }},
  ], []);

  const filtered = useMemo(() => data.filter(a => !filter || a.name.toLowerCase().includes(filter.toLowerCase()) || a.state.toLowerCase().includes(filter.toLowerCase())), [data, filter]);

  const table = useReactTable({ data: filtered, columns, state: { sorting }, onSortingChange: setSorting, getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel() });

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Bot size={16} className="text-[var(--color-accent)]" />
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Agents ({data.length})</h3>
        </div>
        <div className="relative"><Search size={10} className="absolute left-2 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" /><input value={filter} onChange={e => setFilter(e.target.value)} placeholder="Search..." className="w-28 rounded bg-[var(--color-bg-base)] py-1 pl-6 pr-2 text-[10px] text-[var(--color-text-primary)] outline-none ring-1 ring-white/10 focus:ring-[var(--color-accent)]" /></div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>{table.getHeaderGroups().map(hg => <tr key={hg.id} className="border-b border-white/5">{hg.headers.map(h => <th key={h.id} className="cursor-pointer pb-2 pr-2 text-left text-[10px] font-medium text-[var(--color-text-muted)]" onClick={h.column.getToggleSortingHandler()}><div className="flex items-center gap-1">{flexRender(h.column.columnDef.header, h.getContext())}<ArrowUpDown size={10} /></div></th>)}</tr>)}</thead>
          <tbody>{table.getRowModel().rows.length === 0 ? <tr><td colSpan={7} className="py-8 text-center text-xs text-[var(--color-text-muted)]">No agents</td></tr> : table.getRowModel().rows.map(row => <tr key={row.id} onClick={() => onSelect(row.original.id)} className={`cursor-pointer border-b border-white/5 last:border-0 hover:bg-white/[0.02] ${selectedId === row.original.id ? "bg-[var(--color-accent)]/5" : ""}`}>{row.getVisibleCells().map(cell => <td key={cell.id} className="py-2 pr-2">{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}</tr>)}</tbody>
        </table>
      </div>
    </div>
  );
}
