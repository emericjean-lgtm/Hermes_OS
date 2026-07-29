"use client";

import { useMemo, useState } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  type SortingState,
  type ColumnDef,
} from "@tanstack/react-table";
import { useExecutionTasks } from "@/hooks/use-execution";
import type { ExecutionTask } from "@/types/mission-control";
import { ListChecks, ArrowUpDown, Search } from "lucide-react";

const STATUS_COLORS: Record<string, string> = {
  pending: "var(--color-text-muted)",
  ready: "var(--color-accent)",
  running: "var(--color-accent)",
  completed: "var(--color-success)",
  failed: "var(--color-danger)",
  skipped: "var(--color-text-muted)",
  cancelled: "var(--color-text-muted)",
  retry: "var(--color-warning)",
};

export default function TaskTable() {
  const { data: tasks, isLoading } = useExecutionTasks();
  const [sorting, setSorting] = useState<SortingState>([{ id: "status", desc: false }]);
  const [filter, setFilter] = useState("");

  const data = useMemo(() => tasks ?? [], [tasks]);

  const columns = useMemo<ColumnDef<ExecutionTask>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Task",
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: STATUS_COLORS[row.original.status] ?? "var(--color-text-muted)" }}
            />
            <span className="text-sm font-medium">{row.original.name}</span>
          </div>
        ),
      },
      {
        accessorKey: "runtime",
        header: "Runtime",
        cell: ({ getValue }) => (
          <span className="text-xs text-[var(--color-text-muted)]">{getValue() as string ?? "—"}</span>
        ),
      },
      {
        accessorKey: "agent_id",
        header: "Agent",
        cell: ({ getValue }) => (
          <span className="text-xs text-[var(--color-text-muted)]">{getValue() as string ?? "—"}</span>
        ),
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ getValue }) => {
          const s = getValue() as string;
          return (
            <span className="text-xs font-medium uppercase" style={{ color: STATUS_COLORS[s] }}>
              {s}
            </span>
          );
        },
      },
      {
        accessorKey: "duration_ms",
        header: "Duration",
        cell: ({ getValue }) => {
          const ms = getValue() as number | null;
          return <span className="text-xs text-[var(--color-text-muted)]">{ms ? `${(ms / 1000).toFixed(1)}s` : "—"}</span>;
        },
      },
      {
        accessorKey: "progress",
        header: "Progress",
        cell: ({ getValue }) => {
          const v = getValue() as number;
          return (
            <div className="flex items-center gap-2">
              <div className="h-1.5 w-12 overflow-hidden rounded-full bg-white/10">
                <div className="h-full rounded-full bg-[var(--color-accent)]" style={{ width: `${v}%` }} />
              </div>
              <span className="text-[10px] text-[var(--color-text-muted)]">{v}%</span>
            </div>
          );
        },
      },
      {
        accessorKey: "retries",
        header: "Retries",
        cell: ({ getValue }) => {
          const r = getValue() as number;
          return (
            <span className={`text-xs ${r > 0 ? "text-[var(--color-warning)]" : "text-[var(--color-text-muted)]"}`}>
              {r}
            </span>
          );
        },
      },
    ],
    [],
  );

  const filteredData = useMemo(
    () => data.filter((t) => !filter || t.name.toLowerCase().includes(filter.toLowerCase())),
    [data, filter],
  );

  const table = useReactTable({
    data: filteredData,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ListChecks size={16} className="text-[var(--color-accent)]" />
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Current Tasks</h3>
          {data.length > 0 && (
            <span className="rounded-full bg-[var(--color-accent)]/10 px-1.5 py-0.5 text-[10px] text-[var(--color-accent)]">
              {data.filter((t) => t.status === "running").length} running
            </span>
          )}
        </div>
        <div className="relative">
          <Search size={10} className="absolute left-2 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" />
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Search tasks..."
            className="w-32 rounded bg-[var(--color-bg-base)] py-1 pl-6 pr-2 text-[10px] text-[var(--color-text-primary)] outline-none ring-1 ring-white/10 focus:ring-[var(--color-accent)]"
          />
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b border-white/5">
                {hg.headers.map((h) => (
                  <th key={h.id} className="cursor-pointer pb-2 pr-2 text-left text-[10px] font-medium text-[var(--color-text-muted)]" onClick={h.column.getToggleSortingHandler()}>
                    <div className="flex items-center gap-1">
                      {flexRender(h.column.columnDef.header, h.getContext())}
                      <ArrowUpDown size={10} />
                    </div>
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.length === 0 && (
              <tr><td colSpan={7} className="py-8 text-center text-xs text-[var(--color-text-muted)]">No tasks</td></tr>
            )}
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="border-b border-white/5 last:border-0">
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="py-2 pr-2">{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Need to import flexRender
import { flexRender } from "@tanstack/react-table";
