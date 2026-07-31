"use client";

import { useRuntimes, useResourceStatus } from "@/hooks/use-api";
import { Card, Badge, ProgressBar } from "@/components/ui/card";
import type { RuntimeInfo, RuntimeStatus } from "@/types/hermes";

const statusBadge: Record<RuntimeStatus, keyof typeof statusColors> = {
  AVAILABLE: "success",
  DEGRADED: "warning",
  UNAVAILABLE: "danger",
};

const statusColors = { success: "success", warning: "warning", danger: "danger" } as const;

/** Bytes to GB, one decimal. The endpoint reports bytes; the meters show GB. */
const gib = (n: number) => (n / 1024 ** 3).toFixed(1);

export function RuntimeCenter() {
  const { data: runtimes, isLoading } = useRuntimes();
  const { data: resources } = useResourceStatus();

  return (
    <div className="animate-fade-in">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-hermes-text font-mono tracking-tight">
            Runtime Center
          </h1>
          <p className="text-xs text-hermes-muted mt-1">
            Model health, resources & intelligent selection
          </p>
        </div>
      </div>

      {/* Resource status.
          These meters read the fields /api/v1/runtime/resources actually sends.
          They previously read cpu_percent / ram_percent / vram_total_gb /
          gpu_temp_c — none of which the endpoint has ever returned — so every
          gauge here rendered `undefined` and silently fell back to zero or
          blank. The declared type matched the reading, not the API, so nothing
          caught it (R-002 P3). */}
      {resources && (
        <div className="grid grid-cols-4 gap-3 mb-6">
          <ResourceMeter
            label="RAM"
            value={resources.ram.usage_pct}
            unit="%"
            detail={`${gib(resources.ram.used_bytes)}/${gib(resources.ram.total_bytes)} GB`}
          />
          <ResourceMeter
            label="Allocations"
            value={resources.allocations > 0 ? 100 : 0}
            unit=""
            detail={`${resources.allocations} active · ${gib(resources.allocated_bytes)} GB`}
          />
          {resources.gpu.available ? (
            <>
              <ResourceMeter
                label="VRAM"
                value={
                  resources.gpu.vram_total_bytes > 0
                    ? (resources.gpu.vram_used_bytes / resources.gpu.vram_total_bytes) * 100
                    : 0
                }
                unit="%"
                detail={`${gib(resources.gpu.vram_used_bytes)}/${gib(resources.gpu.vram_total_bytes)} GB`}
              />
              {resources.gpu.temperature_celsius != null && (
                <ResourceMeter
                  label="GPU Temp"
                  value={Math.min(100, resources.gpu.temperature_celsius)}
                  unit="°C"
                  detail={`${resources.gpu.temperature_celsius}°C · ${resources.gpu.name}`}
                />
              )}
            </>
          ) : (
            <div className="col-span-2 flex items-center justify-center text-xs text-hermes-muted font-mono border border-hermes-border/50 rounded-lg">
              No GPU detected by the resource manager
            </div>
          )}
        </div>
      )}

      {/* Runtime cards */}
      <div className="grid grid-cols-2 gap-4">
        {runtimes?.map((rt) => (
          <RuntimeCard key={rt.name} runtime={rt} />
        ))}
        {runtimes?.length === 0 && (
          <div className="col-span-2 flex items-center justify-center h-32 text-xs text-hermes-muted font-mono">
            No runtimes registered
          </div>
        )}
      </div>
    </div>
  );
}

function ResourceMeter({ label, value, unit, detail }: {
  label: string; value: number; unit: string; detail?: string;
}) {
  const color = value > 90 ? "from-hermes-red to-hermes-red/50" :
    value > 70 ? "from-hermes-amber to-hermes-amber/50" :
    "from-hermes-green to-hermes-green/50";

  return (
    <div className="bg-hermes-card border border-hermes-border rounded-lg p-4">
      <div className="text-[10px] text-hermes-muted font-mono uppercase mb-2">{label}</div>
      <div className="text-2xl font-bold font-mono text-hermes-text">
        {typeof value === "number" ? value.toFixed(0) : value}
        <span className="text-sm text-hermes-muted ml-1">{unit}</span>
      </div>
      <div className="mt-2 h-2 w-full bg-hermes-bg rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full bg-gradient-to-r ${color} transition-all duration-500`}
          style={{ width: `${Math.min(100, value)}%` }}
        />
      </div>
      {detail && <div className="text-[10px] text-hermes-muted mt-1 font-mono">{detail}</div>}
    </div>
  );
}

function RuntimeCard({ runtime }: { runtime: RuntimeInfo }) {
  const health = runtime.health;
  const metrics = runtime.metrics;

  return (
    <Card title={runtime.name} subtitle={runtime.type}>
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <Badge variant={statusBadge[runtime.status]}>{runtime.status}</Badge>
          <Badge variant={health?.circuit_breaker === "CLOSED" ? "success" : health?.circuit_breaker === "OPEN" ? "danger" : "warning"}>
            {health?.circuit_breaker || "?"}
          </Badge>
        </div>

        {metrics && (
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-hermes-bg rounded p-2">
              <div className="text-[10px] text-hermes-muted font-mono">Reliability</div>
              <div className="text-sm font-bold font-mono text-hermes-text">
                {((metrics.reliability || 0) * 100).toFixed(0)}%
              </div>
              <ProgressBar value={(metrics.reliability || 0) * 100} size="sm" className="mt-1" />
            </div>
            <div className="bg-hermes-bg rounded p-2">
              <div className="text-[10px] text-hermes-muted font-mono">Performance</div>
              <div className="text-sm font-bold font-mono text-hermes-text">
                {((metrics.performance || 0) * 100).toFixed(0)}%
              </div>
              <ProgressBar value={(metrics.performance || 0) * 100} size="sm" className="mt-1" />
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[10px] font-mono">
          <span className="text-hermes-muted">Latency</span>
          <span className="text-hermes-text">{health?.latency_ms || "?"} ms</span>
          <span className="text-hermes-muted">Success</span>
          <span className="text-hermes-text">{((health?.success_rate || 0) * 100).toFixed(1)}%</span>
          <span className="text-hermes-muted">Executions</span>
          <span className="text-hermes-text">{metrics?.total_executions || 0}</span>
        </div>
      </div>
    </Card>
  );
}
