"use client";

import React, { useState } from "react";
import {
  useResourceStatus,
  useSubsystemAssembly,
  useSubsystemHealth,
  useSubsystemStatistics,
} from "@/hooks/use-api";
import { CenterHeader } from "@/components/center-scaffold";
import { Badge } from "@/components/ui/card";

// This Center was fabricated end to end, and dangerously so: it reported an
// "NVIDIA A100 80GB" with 81920 MB VRAM, an "AMD EPYC (8C/16T)" CPU and
// "Linux 6.2.0" on whatever machine it was opened on, twelve invented healthy
// components with invented latencies, six invented services (PostgreSQL, Redis,
// ChromaDB) that need not exist, and three invented backup files. "Create
// backup" slept 1500 ms, appended an entry sized `Math.random() * 20 + 30` and
// announced "Backup created successfully" for an operation that never happened.
//
// Everything below now comes from /api/v1/system/health, /system/assembly,
// /system/statistics and /runtime/resources. Hermes exposes no backup API, so
// that tab says so instead of pretending (R-002 P3/P5).

const TABS = ["overview", "profile", "services", "backups", "health"] as const;

const bytesToGB = (n: number) => (n / 1024 ** 3).toFixed(1);

function ProfileCard({
  title,
  value,
  icon,
}: {
  title: string;
  value: string | boolean;
  icon: string;
}) {
  return (
    <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-4 hover:border-hermes-cyan/40 transition-all">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-lg">{icon}</span>
        <span className="text-hermes-muted text-xs uppercase tracking-wider">{title}</span>
      </div>
      <div className="text-hermes-text-bright font-mono text-sm">
        {typeof value === "boolean" ? (
          <span className={value ? "text-hermes-green" : "text-hermes-red"}>
            {value ? "✓ Available" : "✗ Not available"}
          </span>
        ) : (
          value
        )}
      </div>
    </div>
  );
}

const dotColour = (status: string | undefined) =>
  status === "healthy"
    ? "bg-hermes-green"
    : status === "degraded"
      ? "bg-hermes-amber"
      : status === "unknown"
        ? "bg-hermes-dim"
        : "bg-hermes-red";

export default function DeploymentCenter() {
  const [activeTab, setActiveTab] = useState<(typeof TABS)[number]>("overview");

  const health = useSubsystemHealth();
  const assembly = useSubsystemAssembly();
  const statistics = useSubsystemStatistics();
  const resources = useResourceStatus();

  const detail = health.data?.detail ?? {};
  const byStatus = health.data?.by_status ?? {};
  const silent = health.data?.silent ?? [];
  const unhealthy = health.data?.unhealthy ?? [];
  const bootstrap = (assembly.data?.bootstrap ?? {}) as Record<string, unknown>;
  const built = (bootstrap.built as string[] | undefined) ?? [];
  const registries = (bootstrap.registries ?? {}) as Record<string, unknown>;
  const services = (statistics.data?.services ?? {}) as Record<string, unknown>;

  const gpu = resources.data?.gpu;
  const ram = resources.data?.ram;

  return (
    <div className="space-y-6">
      <CenterHeader
        title="Deployment Center"
        subtitle="État de préparation à la production et gestion du système"
        right={
          health.isLoading ? (
            <span className="text-hermes-muted text-[11px] font-mono">vérification…</span>
          ) : health.isError ? (
            <Badge variant="danger">injoignable</Badge>
          ) : (
            <Badge
              variant={
                health.data?.status === "healthy" ? "success"
                : health.data?.status === "degraded" ? "warning"
                : "danger"
              }
            >
              <span className={`w-1.5 h-1.5 rounded-full ${dotColour(health.data?.status)}`} />
              {health.data?.status}
            </Badge>
          )
        }
      />

      {/* Tab Nav */}
      <div className="flex gap-1 bg-hermes-elevated/50 rounded-lg p-1">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
              activeTab === tab
                ? "bg-hermes-cyan/20 text-hermes-cyan"
                : "text-hermes-muted hover:text-hermes-text"
            }`}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* Overview */}
      {activeTab === "overview" && (
        <div className="space-y-4">
          <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-5">
            <h2 className="text-lg font-semibold text-hermes-text-bright mb-4">System Overview</h2>
            {health.isError ? (
              <div className="text-hermes-red text-sm">
                /api/v1/system/health is unreachable.
              </div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <div className="text-hermes-muted text-xs uppercase">Subsystems</div>
                  <div className="text-3xl font-bold text-hermes-text-bright">
                    {health.data?.services ?? "—"}
                  </div>
                </div>
                <div>
                  <div className="text-hermes-muted text-xs uppercase">Healthy</div>
                  <div className="text-3xl font-bold text-hermes-green">
                    {byStatus.healthy ?? 0}
                  </div>
                </div>
                <div>
                  <div className="text-hermes-muted text-xs uppercase">Not reporting</div>
                  <div className="text-3xl font-bold text-hermes-muted">{silent.length}</div>
                </div>
                <div>
                  <div className="text-hermes-muted text-xs uppercase">Unhealthy</div>
                  <div className="text-3xl font-bold text-hermes-red">
                    {unhealthy.length}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Registries — the numbers the composition root actually seeded */}
          <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-5">
            <h3 className="text-hermes-text-bright font-semibold mb-3">Registries</h3>
            {assembly.isLoading ? (
              <div className="text-hermes-muted text-sm">Loading assembly…</div>
            ) : Object.keys(registries).length === 0 ? (
              <div className="text-hermes-muted text-sm">
                The bootstrap reported no registry counts.
              </div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                {(["agents", "tools", "mcp_servers", "runtimes", "skills"] as const).map(
                  (key) => (
                    <div key={key} className="bg-hermes-bg-deep/50 rounded-lg p-3">
                      <div className="text-hermes-muted text-xs uppercase">
                        {key.replace(/_/g, " ")}
                      </div>
                      <div className="text-xl font-bold text-hermes-cyan font-mono">
                        {String(registries[key] ?? "—")}
                      </div>
                    </div>
                  ),
                )}
              </div>
            )}
          </div>

          <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-5">
            <h3 className="text-hermes-text-bright font-semibold mb-3">Component Health</h3>
            {Object.keys(detail).length === 0 ? (
              <div className="text-hermes-muted text-sm">No component detail reported.</div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {Object.entries(detail).map(([name, info]) => (
                  <div
                    key={name}
                    className="flex items-center justify-between bg-hermes-bg-deep/50 rounded-lg px-3 py-2"
                  >
                    <div className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${dotColour(info.status)}`} />
                      <span className="text-hermes-text text-sm font-mono">{name}</span>
                    </div>
                    <span className="text-hermes-muted text-xs">
                      {info.detail || info.status}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Profile — real host resources */}
      {activeTab === "profile" && (
        <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-5">
          <h2 className="text-lg font-semibold text-hermes-text-bright mb-4">System Profile</h2>
          {resources.isLoading && (
            <div className="text-hermes-muted text-sm">Reading host resources…</div>
          )}
          {resources.isError && (
            <div className="text-hermes-red text-sm">
              /api/v1/runtime/resources is unreachable.
            </div>
          )}
          {resources.data && (
            <>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <ProfileCard
                  title="RAM total"
                  value={ram ? `${bytesToGB(ram.total_bytes)} GB` : "—"}
                  icon="🧠"
                />
                <ProfileCard
                  title="RAM used"
                  value={ram ? `${bytesToGB(ram.used_bytes)} GB (${ram.usage_pct}%)` : "—"}
                  icon="📊"
                />
                <ProfileCard title="RAM status" value={ram?.status ?? "—"} icon="✅" />
                <ProfileCard title="GPU" value={gpu?.name ?? "—"} icon="🎮" />
                <ProfileCard title="GPU vendor" value={gpu?.vendor ?? "—"} icon="🏷" />
                <ProfileCard title="GPU detected" value={Boolean(gpu?.available)} icon="🔧" />
                <ProfileCard
                  title="VRAM total"
                  value={gpu ? `${bytesToGB(gpu.vram_total_bytes)} GB` : "—"}
                  icon="💾"
                />
                <ProfileCard
                  title="VRAM free"
                  value={gpu ? `${bytesToGB(gpu.vram_free_bytes)} GB` : "—"}
                  icon="💽"
                />
                <ProfileCard
                  title="Allocations"
                  value={String(resources.data.allocations ?? 0)}
                  icon="📦"
                />
              </div>
              <p className="text-hermes-dim text-xs mt-4">
                Reported by the resource manager. Fields it cannot detect read
                &quot;unknown&quot; rather than being filled in.
              </p>
            </>
          )}
        </div>
      )}

      {/* Services — the subsystems that actually built */}
      {activeTab === "services" && (
        <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-5">
          <h2 className="text-lg font-semibold text-hermes-text-bright mb-4">
            Services {built.length > 0 && `(${built.length})`}
          </h2>
          {assembly.isLoading && (
            <div className="text-hermes-muted text-sm">Loading assembly…</div>
          )}
          {assembly.isError && (
            <div className="text-hermes-red text-sm">
              /api/v1/system/assembly is unreachable.
            </div>
          )}
          {built.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-hermes-border">
                    <th className="text-left py-2 px-3 text-hermes-muted font-medium">Service</th>
                    <th className="text-left py-2 px-3 text-hermes-muted font-medium">Health</th>
                    <th className="text-left py-2 px-3 text-hermes-muted font-medium">Detail</th>
                    <th className="text-right py-2 px-3 text-hermes-muted font-medium">Stats</th>
                  </tr>
                </thead>
                <tbody>
                  {built.map((name) => (
                    <tr key={name} className="border-b border-hermes-border/50 hover:bg-hermes-elevated/20">
                      <td className="py-2 px-3 text-hermes-text-bright font-mono">{name}</td>
                      <td className="py-2 px-3">
                        <div className="flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${dotColour(detail[name]?.status)}`} />
                          <span className="text-hermes-muted">
                            {detail[name]?.status ?? "unknown"}
                          </span>
                        </div>
                      </td>
                      <td className="py-2 px-3 text-hermes-muted text-xs">
                        {detail[name]?.detail ?? ""}
                      </td>
                      <td className="py-2 px-3 text-right text-hermes-muted text-xs">
                        {services[name] ? "reporting" : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Backups — no such API exists */}
      {activeTab === "backups" && (
        <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-5">
          <h2 className="text-lg font-semibold text-hermes-text-bright mb-4">Backups</h2>
          <div className="text-hermes-muted text-sm">
            Hermes exposes no backup API. This tab previously listed three
            invented archives and its &quot;Create backup&quot; button reported
            success without performing one — so it now reports the real state
            instead.
          </div>
        </div>
      )}

      {/* Health detail */}
      {activeTab === "health" && (
        <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-5">
          <h2 className="text-lg font-semibold text-hermes-text-bright mb-4">Health Details</h2>
          {health.isLoading && <div className="text-hermes-muted text-sm">Loading…</div>}
          {health.isError && (
            <div className="text-hermes-red text-sm">
              /api/v1/system/health is unreachable.
            </div>
          )}
          {Object.keys(detail).length > 0 && (
            <div className="space-y-2">
              {Object.entries(detail).map(([name, info]) => (
                <div
                  key={name}
                  className="flex items-start justify-between bg-hermes-bg-deep/50 rounded-lg px-3 py-2"
                >
                  <div className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${dotColour(info.status)}`} />
                    <span className="text-hermes-text text-sm font-mono">{name}</span>
                  </div>
                  <div className="text-right">
                    <div className="text-hermes-muted text-xs capitalize">{info.status}</div>
                    {info.detail && (
                      <div className="text-hermes-dim text-[11px]">{info.detail}</div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
          {silent.length > 0 && (
            <p className="text-hermes-dim text-xs mt-4">
              {silent.length} subsystem(s) expose no statistics accessor, so their
              health cannot be probed. They are reported as
              &quot;unknown&quot; rather than assumed healthy.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
