"use client";

import React, { useState, useEffect, useCallback } from "react";

interface SystemInfo {
  os: string;
  cpu: string;
  ram: string;
  gpu: string[];
  vram: string;
  disk: string;
  cuda: boolean;
  rocm: boolean;
  wsl: boolean;
  docker: boolean;
}

interface HealthStatus {
  overall: string;
  total_components: number;
  healthy: number;
  degraded: number;
  unhealthy: number;
  components: Record<string, { status: string; message: string; latency_ms: number }>;
}

interface BackupInfo {
  name: string;
  size_mb: number;
  created_at: string;
}

interface ServiceStatus {
  name: string;
  status: string;
  version: string;
}

const MOCK_SERVICES: ServiceStatus[] = [
  { name: "Hermes Backend", status: "healthy", version: "1.0.0" },
  { name: "Hermes Frontend", status: "healthy", version: "1.0.0" },
  { name: "PostgreSQL", status: "healthy", version: "16" },
  { name: "Redis", status: "healthy", version: "7" },
  { name: "ChromaDB", status: "healthy", version: "latest" },
  { name: "Ollama", status: "healthy", version: "latest" },
];

const MOCK_HEALTH: HealthStatus = {
  overall: "healthy",
  total_components: 12,
  healthy: 12,
  degraded: 0,
  unhealthy: 0,
  components: {
    "EventBus": { status: "healthy", message: "", latency_ms: 1.2 },
    "Memory": { status: "healthy", message: "", latency_ms: 2.1 },
    "Runtime": { status: "healthy", message: "", latency_ms: 0.8 },
    "Agents": { status: "healthy", message: "", latency_ms: 3.4 },
    "Tools": { status: "healthy", message: "", latency_ms: 1.5 },
    "Security": { status: "healthy", message: "", latency_ms: 0.9 },
    "Evolution": { status: "healthy", message: "", latency_ms: 2.7 },
    "Autonomous": { status: "healthy", message: "", latency_ms: 1.8 },
    "Config": { status: "healthy", message: "", latency_ms: 0.5 },
    "Database": { status: "healthy", message: "", latency_ms: 4.2 },
    "Monitoring": { status: "healthy", message: "", latency_ms: 1.1 },
    "Logging": { status: "healthy", message: "", latency_ms: 0.3 },
  },
};

export default function DeploymentCenter() {
  const [activeTab, setActiveTab] = useState<string>("overview");
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
  const [health, setHealth] = useState<HealthStatus>(MOCK_HEALTH);
  const [backups, setBackups] = useState<BackupInfo[]>([]);
  const [showCreateBackup, setShowCreateBackup] = useState(false);
  const [backupName, setBackupName] = useState("");
  const [statusMessage, setStatusMessage] = useState("");

  useEffect(() => {
    setSystemInfo({
      os: "Linux 6.2.0",
      cpu: "AMD EPYC (8C/16T)",
      ram: "32.0 GB",
      gpu: ["NVIDIA A100 80GB"],
      vram: "81920 MB",
      disk: "234.5/500.0 GB free",
      cuda: true,
      rocm: false,
      wsl: false,
      docker: true,
    });

    setBackups([
      { name: "hermes_backup_auto", size_mb: 45.2, created_at: "2026-07-29T06:00:00" },
      { name: "hermes_backup_20260728", size_mb: 42.1, created_at: "2026-07-28T06:00:00" },
      { name: "hermes_backup_20260727", size_mb: 38.7, created_at: "2026-07-27T06:00:00" },
    ]);
  }, []);

  const handleCreateBackup = useCallback(async () => {
    setStatusMessage("Creating backup...");
    await new Promise((r) => setTimeout(r, 1500));
    setBackups((prev) => [
      {
        name: backupName || `hermes_backup_${new Date().toISOString().slice(0, 10)}`,
        size_mb: Math.round(Math.random() * 20 + 30),
        created_at: new Date().toISOString(),
      },
      ...prev,
    ]);
    setStatusMessage("Backup created successfully");
    setShowCreateBackup(false);
    setBackupName("");
    setTimeout(() => setStatusMessage(""), 3000);
  }, [backupName]);

  const ProfileCard = ({
    title,
    value,
    icon,
  }: {
    title: string;
    value: string | boolean;
    icon: string;
  }) => (
    <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-4 hover:border-cyan-500/40 transition-all">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-lg">{icon}</span>
        <span className="text-gray-400 text-xs uppercase tracking-wider">{title}</span>
      </div>
      <div className="text-white font-mono text-sm">
        {typeof value === "boolean" ? (
          <span className={value ? "text-green-400" : "text-red-400"}>
            {value ? "✓ Enabled" : "✗ Disabled"}
          </span>
        ) : (
          value
        )}
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Deployment Center</h1>
          <p className="text-gray-400 text-sm mt-1">Production readiness & system management</p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`w-3 h-3 rounded-full ${
              health.overall === "healthy"
                ? "bg-green-400"
                : health.overall === "degraded"
                ? "bg-yellow-400"
                : "bg-red-400"
            }`}
          />
          <span className="text-gray-300 text-sm capitalize">{health.overall}</span>
        </div>
      </div>

      {/* Status message */}
      {statusMessage && (
        <div className="bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 px-4 py-2 rounded-lg text-sm">
          {statusMessage}
        </div>
      )}

      {/* Tab Nav */}
      <div className="flex gap-1 bg-gray-800/50 rounded-lg p-1">
        {["overview", "profile", "services", "backups", "health"].map((tab) => (
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

      {/* Overview Tab */}
      {activeTab === "overview" && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-5 col-span-1 md:col-span-4">
            <h2 className="text-lg font-semibold text-white mb-4">System Overview</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-gray-900/50 rounded-lg p-4 text-center">
                <div className="text-3xl font-bold text-cyan-400">{health.healthy}</div>
                <div className="text-gray-400 text-xs mt-1">Healthy Components</div>
              </div>
              <div className="bg-gray-900/50 rounded-lg p-4 text-center">
                <div className="text-3xl font-bold text-yellow-400">{health.degraded}</div>
                <div className="text-gray-400 text-xs mt-1">Degraded</div>
              </div>
              <div className="bg-gray-900/50 rounded-lg p-4 text-center">
                <div className="text-3xl font-bold text-red-400">{health.unhealthy}</div>
                <div className="text-gray-400 text-xs mt-1">Unhealthy</div>
              </div>
              <div className="bg-gray-900/50 rounded-lg p-4 text-center">
                <div className="text-3xl font-bold text-green-400">{backups.length}</div>
                <div className="text-gray-400 text-xs mt-1">Backups</div>
              </div>
            </div>
          </div>

          {/* Component Health */}
          <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-5 col-span-1 md:col-span-2">
            <h3 className="text-white font-semibold mb-3">Component Health</h3>
            <div className="space-y-2">
              {Object.entries(health.components).map(([name, info]) => (
                <div
                  key={name}
                  className="flex items-center justify-between bg-gray-900/50 rounded px-3 py-2"
                >
                  <span className="text-gray-300 text-sm">{name}</span>
                  <div className="flex items-center gap-3">
                    <span className="text-gray-500 text-xs">{info.latency_ms}ms</span>
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-medium ${
                        info.status === "healthy"
                          ? "bg-green-500/20 text-green-400"
                          : info.status === "degraded"
                          ? "bg-yellow-500/20 text-yellow-400"
                          : "bg-red-500/20 text-red-400"
                      }`}
                    >
                      {info.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Quick Actions */}
          <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-5 col-span-1 md:col-span-2">
            <h3 className="text-white font-semibold mb-3">Quick Actions</h3>
            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={() => setShowCreateBackup(true)}
                className="bg-gray-900/50 hover:bg-gray-700/50 border border-gray-700 rounded-lg p-3 text-left transition-all"
              >
                <div className="text-lg mb-1">💾</div>
                <div className="text-white text-sm font-medium">Create Backup</div>
                <div className="text-gray-500 text-xs">Manual backup point</div>
              </button>
              <button className="bg-gray-900/50 hover:bg-gray-700/50 border border-gray-700 rounded-lg p-3 text-left transition-all">
                <div className="text-lg mb-1">🔄</div>
                <div className="text-white text-sm font-medium">Run Health Check</div>
                <div className="text-gray-500 text-xs">Full system scan</div>
              </button>
              <button className="bg-gray-900/50 hover:bg-gray-700/50 border border-gray-700 rounded-lg p-3 text-left transition-all">
                <div className="text-lg mb-1">📋</div>
                <div className="text-white text-sm font-medium">Export Config</div>
                <div className="text-gray-500 text-xs">Download JSON config</div>
              </button>
              <button className="bg-gray-900/50 hover:bg-gray-700/50 border border-gray-700 rounded-lg p-3 text-left transition-all">
                <div className="text-lg mb-1">📊</div>
                <div className="text-white text-sm font-medium">System Report</div>
                <div className="text-gray-500 text-xs">Full diagnostic</div>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Profile Tab */}
      {activeTab === "profile" && systemInfo && (
        <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-5">
          <h2 className="text-lg font-semibold text-white mb-4">System Profile</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            <ProfileCard title="Operating System" value={systemInfo.os} icon="🖥" />
            <ProfileCard title="CPU" value={systemInfo.cpu} icon="⚡" />
            <ProfileCard title="RAM" value={systemInfo.ram} icon="🧠" />
            <ProfileCard title="GPU" value={systemInfo.gpu.join(", ")} icon="🎮" />
            <ProfileCard title="VRAM" value={systemInfo.vram} icon="💾" />
            <ProfileCard title="Disk" value={systemInfo.disk} icon="💽" />
            <ProfileCard title="CUDA" value={systemInfo.cuda} icon="🔧" />
            <ProfileCard title="ROCm" value={systemInfo.rocm} icon="🔧" />
            <ProfileCard title="Docker" value={systemInfo.docker} icon="🐳" />
          </div>
        </div>
      )}

      {/* Services Tab */}
      {activeTab === "services" && (
        <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-5">
          <h2 className="text-lg font-semibold text-white mb-4">Services</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700">
                  <th className="text-left py-3 px-4 text-gray-400 font-medium">Service</th>
                  <th className="text-left py-3 px-4 text-gray-400 font-medium">Status</th>
                  <th className="text-left py-3 px-4 text-gray-400 font-medium">Version</th>
                  <th className="text-right py-3 px-4 text-gray-400 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {MOCK_SERVICES.map((svc) => (
                  <tr key={svc.name} className="border-b border-gray-700/50 hover:bg-gray-700/20">
                    <td className="py-3 px-4 text-white">{svc.name}</td>
                    <td className="py-3 px-4">
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-medium ${
                          svc.status === "healthy"
                            ? "bg-green-500/20 text-green-400"
                            : "bg-red-500/20 text-red-400"
                        }`}
                      >
                        {svc.status}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-gray-400">{svc.version}</td>
                    <td className="py-3 px-4 text-right">
                      <button className="text-cyan-400 hover:text-cyan-300 text-xs">
                        Restart
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Backups Tab */}
      {activeTab === "backups" && (
        <div className="space-y-4">
          <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-white">Backups</h2>
              <button
                onClick={() => setShowCreateBackup(true)}
                className="px-3 py-1.5 bg-cyan-500/20 text-cyan-300 rounded-lg text-sm hover:bg-cyan-500/30 transition-all"
              >
                + Create Backup
              </button>
            </div>

            {showCreateBackup && (
              <div className="mb-4 bg-gray-900/50 border border-gray-700 rounded-lg p-4">
                <label className="block text-gray-300 text-sm mb-2">
                  Backup Name (optional)
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={backupName}
                    onChange={(e) => setBackupName(e.target.value)}
                    placeholder="my_backup"
                    className="flex-1 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-cyan-500"
                  />
                  <button
                    onClick={handleCreateBackup}
                    className="px-4 py-2 bg-cyan-500/20 text-cyan-300 rounded-lg text-sm hover:bg-cyan-500/30"
                  >
                    Create
                  </button>
                  <button
                    onClick={() => setShowCreateBackup(false)}
                    className="px-4 py-2 bg-gray-700 text-gray-300 rounded-lg text-sm hover:bg-gray-600"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-700">
                    <th className="text-left py-3 px-4 text-gray-400 font-medium">Name</th>
                    <th className="text-left py-3 px-4 text-gray-400 font-medium">Size</th>
                    <th className="text-left py-3 px-4 text-gray-400 font-medium">Created</th>
                    <th className="text-right py-3 px-4 text-gray-400 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {backups.map((b) => (
                    <tr key={b.name} className="border-b border-gray-700/50 hover:bg-gray-700/20">
                      <td className="py-3 px-4 text-white font-mono text-xs">{b.name}</td>
                      <td className="py-3 px-4 text-gray-400">{b.size_mb} MB</td>
                      <td className="py-3 px-4 text-gray-400">
                        {new Date(b.created_at).toLocaleString()}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <button className="text-cyan-400 hover:text-cyan-300 text-xs mr-3">
                          Restore
                        </button>
                        <button className="text-red-400 hover:text-red-300 text-xs">
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Health Tab */}
      {activeTab === "health" && (
        <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-5">
          <h2 className="text-lg font-semibold text-white mb-4">Health Details</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {Object.entries(health.components).map(([name, info]) => (
              <div
                key={name}
                className="bg-gray-900/50 border border-gray-700 rounded-lg p-4"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-white font-medium">{name}</span>
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${
                      info.status === "healthy"
                        ? "bg-green-500/20 text-green-400"
                        : info.status === "degraded"
                        ? "bg-yellow-500/20 text-yellow-400"
                        : "bg-red-500/20 text-red-400"
                    }`}
                  >
                    {info.status}
                  </span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">Latency: {info.latency_ms}ms</span>
                  <span className="text-gray-500">{info.message || "No issues"}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
