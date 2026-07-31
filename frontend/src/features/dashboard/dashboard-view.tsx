"use client";

import { useSystemHealth, useSystemStatistics, useMissions, useAgents, useRuntimes, useExecutions, useApprovals } from "@/hooks/use-api";
import { useWebSocket } from "@/hooks/use-websocket";
import { useCockpitStore } from "@/hooks/use-store";
import { Card, Badge, StatCard, ProgressBar } from "@/components/ui/card";
import { motion } from "framer-motion";
import { Activity, Cpu, HardDrive, Zap, AlertTriangle, CheckCircle2, Clock } from "lucide-react";
import { severityColor, severityBg } from "@/hooks/use-websocket";

export function DashboardView() {
  const { data: health } = useSystemHealth();
  const { data: stats } = useSystemStatistics();
  const { data: missions } = useMissions();
  const { data: agents } = useAgents();
  const { data: runtimes } = useRuntimes();
  const { data: executions } = useExecutions();
  const { data: approvals } = useApprovals();
  const { events: liveEvents, connected } = useWebSocket({ maxEvents: 10 });

  const activeMissions = missions?.filter((m) => ["RUNNING", "PLANNING", "READY"].includes(m.status)).length || 0;
  const completedMissions = missions?.filter((m) => m.status === "COMPLETED").length || 0;
  const failedMissions = missions?.filter((m) => m.status === "FAILED").length || 0;
  const activeAgents = agents?.filter((a) => a.status === "BUSY" || a.status === "STARTING").length || 0;
  const pendingApprovals = approvals?.filter((a) => a.status === "PENDING").length || 0;

  const systemStatus = health?.status || "UNKNOWN";
  const statusColor =
    systemStatus === "HEALTHY" ? "text-hermes-green" :
    systemStatus === "DEGRADED" ? "text-hermes-amber" :
    "text-hermes-red";

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-hermes-text font-mono tracking-tight">
            Hermes OS
          </h1>
          <p className="text-sm text-hermes-muted font-mono mt-1">
            AI Operations Cockpit — Autonomous Mission Control
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border ${statusColor} border-current/30 bg-current/5`}>
            <div className={`w-2 h-2 rounded-full animate-pulse ${statusColor.replace("text-", "bg-")}`} />
            <span className={`text-xs font-mono font-bold ${statusColor}`}>{systemStatus}</span>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-hermes-muted font-mono">
            <Badge variant={connected ? "success" : "danger"}>
              {connected ? "WS LIVE" : "WS OFF"}
            </Badge>
          </div>
        </div>
      </div>

      {/* Key stats */}
      <div className="grid grid-cols-5 gap-3 mb-6">
        <StatCard label="Active Missions" value={activeMissions} trend={activeMissions > 0 ? "up" : "neutral"} />
        <StatCard label="Completed" value={completedMissions} trend="up" />
        <StatCard label="Failed" value={failedMissions} trend={failedMissions > 0 ? "down" : "neutral"} />
        <StatCard label="Active Agents" value={activeAgents} trend={activeAgents > 0 ? "up" : "neutral"} />
        <StatCard label="Pending Approvals" value={pendingApprovals} trend={pendingApprovals > 0 ? "down" : "neutral"} />
      </div>

      <div className="grid grid-cols-3 gap-4 mb-6">
        {/* System health */}
        <Card title="System Health">
          {health ? (
            <div className="flex flex-col gap-2">
              {Object.entries(health.subsystems || {}).slice(0, 6).map(([name, sub]) => (
                <div key={name} className="flex items-center justify-between p-2 bg-hermes-bg rounded text-xs">
                  <span className="text-hermes-text font-mono">{name}</span>
                  <Badge variant={sub.status === "HEALTHY" ? "success" : sub.status === "DEGRADED" ? "warning" : "danger"}>
                    {sub.status}
                  </Badge>
                </div>
              ))}
              <div className="flex items-center justify-between p-2 bg-hermes-bg rounded text-xs">
                <span className="text-hermes-muted font-mono">Uptime</span>
                <span className="text-hermes-text font-mono">{formatUptime(health.uptime_seconds)}</span>
              </div>
            </div>
          ) : (
            <div className="h-32 flex items-center justify-center text-xs text-hermes-muted">Connecting...</div>
          )}
        </Card>

        {/* Runtimes overview */}
        <Card title="Runtimes" subtitle={`${runtimes?.length || 0} available`}>
          <div className="flex flex-col gap-2 max-h-[220px] overflow-y-auto">
            {runtimes?.slice(0, 6).map((rt) => (
              <div key={rt.name} className="flex items-center justify-between p-2 bg-hermes-bg rounded text-xs">
                <div>
                  <span className="text-hermes-text font-mono">{rt.name}</span>
                  <span className="text-hermes-muted ml-2 text-[10px]">{rt.type}</span>
                </div>
                <Badge variant={rt.status === "AVAILABLE" ? "success" : rt.status === "DEGRADED" ? "warning" : "danger"}>
                  {rt.status}
                </Badge>
              </div>
            ))}
          </div>
        </Card>

        {/* Live events */}
        <Card title="Live Events" subtitle={connected ? "Streaming" : "Disconnected"}>
          <div className="flex flex-col gap-1 max-h-[220px] overflow-y-auto font-mono">
            {liveEvents.slice(0, 8).map((evt, i) => (
              <div key={i} className={`flex items-center gap-2 py-1 px-1.5 rounded text-[10px] ${severityBg(evt.severity)}`}>
                <span className={`w-10 flex-shrink-0 ${severityColor(evt.severity)}`}>{evt.severity}</span>
                <span className="text-hermes-purple w-14 flex-shrink-0 truncate">{evt.source}</span>
                <span className="text-hermes-amber flex-shrink-0">{evt.type}</span>
                <span className="text-hermes-muted truncate flex-1">
                  {JSON.stringify(evt.payload).slice(0, 60)}
                </span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Recent missions & agents */}
      <div className="grid grid-cols-2 gap-4">
        <Card title="Recent Missions" subtitle={`${activeMissions} active`}>
          <div className="flex flex-col gap-2 max-h-[250px] overflow-y-auto">
            {missions?.slice(0, 8).map((m) => (
              <div key={m.id} className="flex items-center justify-between p-2.5 bg-hermes-bg rounded-lg text-xs">
                <div className="flex-1 min-w-0">
                  <div className="text-hermes-text font-medium truncate">{m.title}</div>
                  <div className="text-[10px] text-hermes-muted font-mono mt-0.5">
                    {m.priority} · {m.completed_nodes}/{m.node_count || "?"}
                  </div>
                </div>
                <div className="flex items-center gap-2 ml-2">
                  <div className="w-16 hidden sm:block">
                    <ProgressBar value={m.progress} size="sm" />
                  </div>
                  <Badge
                    variant={
                      m.status === "RUNNING" ? "purple" :
                      m.status === "COMPLETED" ? "success" :
                      m.status === "FAILED" ? "danger" :
                      "default"
                    }
                  >
                    {m.status}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Active Agents" subtitle={`${activeAgents} busy`}>
          <div className="flex flex-col gap-2 max-h-[250px] overflow-y-auto">
            {agents?.slice(0, 8).map((a) => (
              <div key={a.id} className="flex items-center justify-between p-2.5 bg-hermes-bg rounded-lg text-xs">
                <div>
                  <div className="text-hermes-text font-medium">{a.name}</div>
                  <div className="text-[10px] text-hermes-muted font-mono mt-0.5">
                    {a.type} · {a.runtime || "no runtime"}
                  </div>
                </div>
                <Badge
                  variant={
                    a.status === "READY" ? "success" :
                    a.status === "BUSY" ? "purple" :
                    a.status === "ERROR" ? "danger" :
                    "default"
                  }
                >
                  {a.status}
                </Badge>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}
