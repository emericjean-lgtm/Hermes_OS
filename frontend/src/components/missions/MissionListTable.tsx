"use client";

import { useMemo, useState } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  type SortingState,
  type ColumnDef,
} from "@tanstack/react-table";
import { useMissionList } from "@/hooks/use-missions";
import { MISSION_STATUS_COLORS, PRIORITY_ORDER } from "@/types/mission-control";
import type { Mission } from "@/types/mission-control";
import { Search, Target, ArrowUpDown } from "lucide-react";

interface MissionListTableProps {
  onSelect: (id: string) => void;
  selectedId: string | null;
}

export default function MissionListTable({ onSelect, selectedId }: MissionListTableProps) {
  const { data: missions, isLoading } = useMissionList();
  const [globalFilter, setGlobalFilter] = useState("");
  const [sorting, setSorting] = useState<SortingState>([{ id: "created_at", desc: true }]);

  const columns = useMemo<ColumnDef<Mission>[]>(
    () => [
      {
        accessorKey: "title",
        header: "Mission",
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: MISSION_STATUS_COLORS[row.original.status] ?? "var(--color-text-muted)" }}
            />
            <span className="truncate text-sm font-medium">{row.original.title}</span>
          </div>
        ),
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ getValue }) => (
          <span className="text-xs uppercase text-[var(--color-text-muted)]">
            {getValue() as string}
          </span>
        ),
      },
      {
        accessorKey: "priority",
        header: "Priority",
        sortingFn: (a, b) => (PRIORITY_ORDER[a.original.priority] ?? 0) - (PRIORITY_ORDER[b.original.priority] ?? 0),
        cell: ({ getValue }) => {
          const p = getValue() as string;
          const color = p === "CRITICAL" ? "var(--color-danger)" : p === "HIGH" ? "var(--color-warning)" : "var(--color-text-muted)";
          return <span className="text-xs font-medium" style={{ color }}>{p}</span>;
        },
      },
      {
        accessorKey: "progress",
        header: "Progress",
        cell: ({ getValue }) => {
          const v = getValue() as number;
          return (
            <div className="flex items-center gap-2">
              <div className="h-1.5 w-16 overflow-hidden rounded-full bg-white/10">
                <div
                  className="h-full rounded-full bg-[var(--color-accent)]"
                  style={{ width: `${Math.min(v, 100)}%` }}
                />
              </div>
              <span className="text-[10px] text-[var(--color-text-muted)]">{v}%</span>
            </div>
          );
        },
      },
      {
        accessorKey: "duration_ms",
        header: "Duration",
        cell: ({ getValue }) => {
          const ms = getValue() as number | null;
          return (
            <span className="text-xs text-[var(--color-text-muted)]">
              {ms != null ? `${(ms / 1000).toFixed(1)}s` : "—"}
            </span>
          );
        },
      },
      {
        accessorKey: "created_at",
        header: "Created",
        cell: ({ getValue }) => (
          <span className="text-xs text-[var(--color-text-muted)]">
            {new Date(getValue() as string).toLocaleDateString()}
          </span>
        ),
      },
    ],
    [],
  );

  const table = useReactTable({
    data: missions ?? [],
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  if (isLoading) {
    return (
      <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
        <div className="animate-pulse space-y-3">
          <div className="h-8 w-full rounded bg-white/5" />
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-10 w-full rounded bg-white/5" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
      {/* Search */}
      <div className="mb-3 flex items-center gap-2">
        <Target size={16} className="text-[var(--color-accent)]" />
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
          Missions ({missions?.length ?? 0})
        </h3>
        <div className="relative ml-auto">
          <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" />
          <input
            value={globalFilter}
            onChange={(e) => setGlobalFilter(e.target.value)}
            placeholder="Search missions..."
            className="w-40 rounded-md bg-[var(--color-bg-base)] py-1 pl-7 pr-2 text-xs text-[var(--color-text-primary)] outline-none ring-1 ring-white/10 focus:ring-[var(--color-accent)]"
          />
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b border-white/5">
                {hg.headers.map((header) => (
                  <th
                    key={header.id}
                    className="cursor-pointer pb-2 pr-3 text-left text-[10px] font-medium text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
                    onClick={header.column.getToggleSortingHandler()}
                  >
                    <div className="flex items-center gap-1">
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      <ArrowUpDown size={10} />
                    </div>
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="py-12 text-center text-xs text-[var(--color-text-muted)]">
                  {globalFilter ? "No missions match your search." : "No missions yet. Create one to get started."}
                </td>
              </tr>
            )}
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                onClick={() => onSelect(row.original.id)}
                className={`cursor-pointer border-b border-white/5 last:border-0 hover:bg-white/[0.02] ${
                  selectedId === row.original.id ? "bg-[var(--color-accent)]/5" : ""
                }`}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="py-2.5 pr-3">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
