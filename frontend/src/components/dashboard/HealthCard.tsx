"use client";

import { useHealth } from "@/hooks/use-dashboard";
import { Activity, CheckCircle, AlertTriangle, XCircle } from "lucide-react";

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case "healthy":
      return <CheckCircle size={14} className="text-[var(--color-success)]" />;
    case "degraded":
      return <AlertTriangle size={14} className="text-[var(--color-warning)]" />;
    default:
      return <XCircle size={14} className="text-[var(--color-danger)]" />;
  }
}

function SubsystemRow({ name, status, message }: { name: string; status: string; message?: string }) {
  return (
    <div className="flex items-center justify-between rounded-md px-3 py-1.5 text-xs transition-colors hover:bg-white/5">
      <div className="flex items-center gap-2">
        <StatusIcon status={status} />
        <span className="text-[var(--color-text-primary)]">{name}</span>
      </div>
      {message && (
        <span className="text-[var(--color-text-muted)] truncate ml-2 max-w-[160px]" title={message}>
          {message}
        </span>
      )}
    </div>
  );
}

export default function HealthCard() {
  const { data: health, isLoading, isError, error } = useHealth();

  if (isLoading) {
    return (
      <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
        <div className="animate-pulse space-y-3">
          <div className="h-4 w-24 rounded bg-white/10" />
          <div className="h-3 w-32 rounded bg-white/10" />
          <div className="space-y-2">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-6 rounded bg-white/5" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-4">
        <div className="flex items-center gap-2 text-sm text-[var(--color-danger)]">
          <XCircle size={16} />
          <span>Failed to load health: {error instanceof Error ? error.message : "Unknown error"}</span>
        </div>
      </div>
    );
  }

  if (!health) return null;

  const allSubsystems = [
    ...(health.kernel_status ?? []),
    ...(health.runtime_status ?? []),
    ...(health.memory_status ?? []),
    ...(health.integrations_status ?? []),
    ...(health.event_bus_status ?? []),
  ];

  const healthyCount = allSubsystems.filter((s) => s.status === "healthy").length;
  const totalCount = allSubsystems.length;

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4 transition-colors hover:border-white/20">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity size={16} className="text-[var(--color-accent)]" />
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
            System Health
          </h3>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`text-xs font-medium ${
              health.status === "HEALTHY"
                ? "text-[var(--color-success)]"
                : health.status === "DEGRADED"
                  ? "text-[var(--color-warning)]"
                  : "text-[var(--color-danger)]"
            }`}
          >
            {health.status}
          </span>
          <span className="text-[10px] text-[var(--color-text-muted)]">
            v{health.version}
          </span>
        </div>
      </div>

      {/* Uptime */}
      <div className="mb-3 text-xs text-[var(--color-text-muted)]">
        Uptime: {Math.floor(health.uptime / 60)}m · {healthyCount}/{totalCount} healthy
      </div>

      {/* Subsystems */}
      <div className="space-y-0.5">
        {allSubsystems.map((sub) => (
          <SubsystemRow
            key={sub.name}
            name={sub.name}
            status={sub.status}
            message={sub.message}
          />
        ))}
      </div>
    </div>
  );
}
