"use client";

import React, { useState } from "react";
import {
  useResourceStatus,
  useSubsystemAssembly,
  useSubsystemHealth,
  useSubsystemStatistics,
} from "@/hooks/use-api";

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
    <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-4 hover:border-cyan-500/40 transition-all">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-lg">{icon}</span>
        <span className="text-gray-400 text-xs uppercase tracking-wider">{title}</span>
      </div>
      <div className="text-white font-mono text-sm">
        {typeof value === "boolean" ? (
          <span className={value ? "text-green-400" : "text-red-400"}>
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
    ? "bg-green-400"
    : status === "degraded"
      ? "bg-yellow-400"
      : status === "unknown"
        ? "bg-gray-500"
        : "bg-red-400";

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
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Deployment Center</h1>
          <p className="text-gray-400 text-sm mt-1">
            Production readiness &amp; system management
          </p>
        </div>
        <div className="flex items-center gap-2">
          {health.isLoading ? (
            <span className="text-gray-400 text-sm">checking…</span>
          ) : health.isError ? (
            <>
              <span className="w-3 h-3 rounded-full bg-red-400" />
              <span className="text-gray-300 text-sm">unreachable</span>
            </>
          ) : (
            <>
              <span className={`w-3 h-3 rounded-full ${dotColour(health.data?.status)}`} />
              <span className="text-gray-300 text-sm capitalize">
                {health.data?.status}
              </span>
            </>
          )}
        </div>
      </div>

      {/* Tab Nav */}
      <div className="flex gap-1 bg-gray-800/50 rounded-lg p-1">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
              activeTab === tab
                ? "bg-cyan-500/20 text-cyan-300"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* Overview */}
      {activeTab === "overview" && (
        <div className="space-y-4">
          <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-5">
            <h2 className="text-lg font-semibold text-white mb-4">System Overview</h2>
            {health.isError ? (
              <div className="text-red-400 text-sm">
                /api/v1/system/health is unreachable.
              </div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <div className="text-gray-400 text-xs uppercase">Subsystems</div>
                  <div className="text-3xl font-bold text-white">
                    {health.data?.services ?? "—"}
                  </div>
                </div>
                <div>
                  <div className="text-gray-400 text-xs uppercase">Healthy</div>
                  <div className="text-3xl font-bold text-green-400">
                    {byStatus.healthy ?? 0}
                  </div>
                </div>
                <div>
                  <div className="text-gray-400 text-xs uppercase">Not reporting</div>
                  <div className="text-3xl font-bold text-gray-400">{silent.length}</div>
                </div>
                <div>
                  <div className="text-gray-400 text-xs uppercase">Unhealthy</div>
                  <div className="text-3xl font-bold text-red-400">
                    {unhealthy.length}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Registries — the numbers the composition root actually seeded */}
          <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-5">
            <h3 className="text-white font-semibold mb-3">Registries</h3>
            {assembly.isLoading ? (
              <div className="text-gray-400 text-sm">Loading assembly…</div>
            ) : Object.keys(registries).length === 0 ? (
              <div className="text-gray-400 text-sm">
                The bootstrap reported no registry counts.
              </div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                {(["agents", "tools", "mcp_servers", "runtimes", "skills"] as const).map(
                  (key) => (
                    <div key={key} className="bg-gray-900/50 rounded-lg p-3">
                      <div className="text-gray-400 text-xs uppercase">
                        {key.replace(/_/g, " ")}
                      </div>
                      <div className="text-xl font-bold text-cyan-400 font-mono">
                        {String(registries[key] ?? "—")}
                      </div>
                    </div>
                  ),
                )}
              </div>
            )}
          </div>

          <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-5">
            <h3 className="text-white font-semibold mb-3">Component Health</h3>
            {Object.keys(detail).length === 0 ? (
              <div className="text-gray-400 text-sm">No component detail reported.</div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {Object.entries(detail).map(([name, info]) => (
                  <div
                    key={name}
                    className="flex items-center justify-between bg-gray-900/50 rounded-lg px-3 py-2"
                  >
                    <div className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${dotColour(info.status)}`} />
                      <span className="text-gray-200 text-sm font-mono">{name}</span>
                    </div>
                    <span className="text-gray-400 text-xs">
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
        <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-5">
          <h2 className="text-lg font-semibold text-white mb-4">System Profile</h2>
          {resources.isLoading && (
            <div className="text-gray-400 text-sm">Reading host resources…</div>
          )}
          {resources.isError && (
            <div className="text-red-400 text-sm">
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
              <p className="text-gray-500 text-xs mt-4">
                Reported by the resource manager. Fields it cannot detect read
                &quot;unknown&quot; rather than being filled in.
              </p>
            </>
          )}
        </div>
      )}

      {/* Services — the subsystems that actually built */}
      {activeTab === "services" && (
        <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-5">
          <h2 className="text-lg font-semibold text-white mb-4">
            Services {built.length > 0 && `(${built.length})`}
          </h2>
          {assembly.isLoading && (
            <div className="text-gray-400 text-sm">Loading assembly…</div>
          )}
          {assembly.isError && (
            <div className="text-red-400 text-sm">
              /api/v1/system/assembly is unreachable.
            </div>
          )}
          {built.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-700">
                    <th className="text-left py-2 px-3 text-gray-400 font-medium">Service</th>
                    <th className="text-left py-2 px-3 text-gray-400 font-medium">Health</th>
                    <th className="text-left py-2 px-3 text-gray-400 font-medium">Detail</th>
                    <th className="text-right py-2 px-3 text-gray-400 font-medium">Stats</th>
                  </tr>
                </thead>
                <tbody>
                  {built.map((name) => (
                    <tr key={name} className="border-b border-gray-700/50 hover:bg-gray-700/20">
                      <td className="py-2 px-3 text-white font-mono">{name}</td>
                      <td className="py-2 px-3">
                        <div className="flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${dotColour(detail[name]?.status)}`} />
                          <span className="text-gray-300">
                            {detail[name]?.status ?? "unknown"}
                          </span>
                        </div>
                      </td>
                      <td className="py-2 px-3 text-gray-400 text-xs">
                        {detail[name]?.detail ?? ""}
                      </td>
                      <td className="py-2 px-3 text-right text-gray-400 text-xs">
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
        <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-5">
          <h2 className="text-lg font-semibold text-white mb-4">Backups</h2>
          <div className="text-gray-300 text-sm">
            Hermes exposes no backup API. This tab previously listed three
            invented archives and its &quot;Create backup&quot; button reported
            success without performing one — so it now reports the real state
            instead.
          </div>
        </div>
      )}

      {/* Health detail */}
      {activeTab === "health" && (
        <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-5">
          <h2 className="text-lg font-semibold text-white mb-4">Health Details</h2>
          {health.isLoading && <div className="text-gray-400 text-sm">Loading…</div>}
          {health.isError && (
            <div className="text-red-400 text-sm">
              /api/v1/system/health is unreachable.
            </div>
          )}
          {Object.keys(detail).length > 0 && (
            <div className="space-y-2">
              {Object.entries(detail).map(([name, info]) => (
                <div
                  key={name}
                  className="flex items-start justify-between bg-gray-900/50 rounded-lg px-3 py-2"
                >
                  <div className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${dotColour(info.status)}`} />
                    <span className="text-gray-200 text-sm font-mono">{name}</span>
                  </div>
                  <div className="text-right">
                    <div className="text-gray-300 text-xs capitalize">{info.status}</div>
                    {info.detail && (
                      <div className="text-gray-500 text-[11px]">{info.detail}</div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
          {silent.length > 0 && (
            <p className="text-gray-500 text-xs mt-4">
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
