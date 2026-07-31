"use client";

import { useAgents, useCollaborationMessages } from "@/hooks/use-api";
import { useCockpitStore } from "@/hooks/use-store";
import { Card, Badge, ProgressBar } from "@/components/ui/card";
import type { Agent, AgentStatus } from "@/types/hermes";
import { CenterHeader } from "@/components/center-scaffold";

const statusBadge: Record<AgentStatus, keyof typeof statusColors> = {
  CREATED: "default",
  STARTING: "info",
  READY: "success",
  BUSY: "purple",
  PAUSED: "warning",
  ERROR: "danger",
  STOPPED: "default",
  COMPLETED: "success",
};

const statusColors = {
  default: "default",
  info: "info",
  purple: "purple",
  warning: "warning",
  success: "success",
  danger: "danger",
} as const;

export function AgentCenter() {
  const { data: agents, isLoading } = useAgents();
  const { selectedAgentId, selectAgent } = useCockpitStore();
  const selected = agents?.find((a) => a.id === selectedAgentId);

  // Count statuses
  const statusCounts = agents?.reduce((acc, a) => {
    acc[a.status] = (acc[a.status] || 0) + 1;
    return acc;
  }, {} as Record<string, number>) || {};

  return (
    <div className="animate-fade-in">
      <CenterHeader
        title="Agent Center"
        subtitle="Supervision multi-agents et collaboration"
      />

      {/* Overview stats */}
      <div className="grid grid-cols-4 gap-3 mb-6">
        {(["READY", "BUSY", "ERROR", "COMPLETED"] as AgentStatus[]).map((s) => (
          <div
            key={s}
            className="bg-hermes-card border border-hermes-border rounded-lg p-3 text-center"
          >
            <div className="text-2xl font-bold font-mono text-hermes-amber-bright">
              {statusCounts[s] || 0}
            </div>
            <div className="text-[10px] text-hermes-muted font-mono uppercase mt-1">{s}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Agent list */}
        <Card title="Agents" subtitle={isLoading ? "Loading..." : `${agents?.length || 0} agents`}>
          <div className="flex flex-col gap-2 max-h-[400px] overflow-y-auto">
            {agents?.map((agent) => (
              <button
                key={agent.id}
                onClick={() => selectAgent(agent.id)}
                className={`text-left p-3 rounded-lg border transition-all ${
                  selectedAgentId === agent.id
                    ? "border-hermes-amber/50 bg-hermes-amber/5"
                    : "border-hermes-border/50 hover:border-hermes-border"
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-hermes-text">{agent.name}</span>
                  <Badge variant={statusBadge[agent.status]}>{agent.status}</Badge>
                </div>
                <div className="flex flex-wrap gap-1 mb-1">
                  {agent.capabilities?.slice(0, 3).map((c) => (
                    <span key={c} className="text-[10px] text-hermes-muted font-mono px-1.5 py-0.5 bg-hermes-bg rounded">
                      {c}
                    </span>
                  ))}
                </div>
                <div className="text-[10px] text-hermes-muted font-mono">
                  {agent.current_mission ? `Mission: ${agent.current_mission}` : "Idle"}
                </div>
              </button>
            ))}
          </div>
        </Card>

        {/* Agent detail */}
        <Card
          title={selected ? selected.name : "Agent Detail"}
          subtitle={selected ? selected.type : "Select an agent"}
        >
          {selected ? (
            <div className="flex flex-col gap-3">
              <div className="grid grid-cols-2 gap-2">
                <div className="text-[10px] text-hermes-muted font-mono">Status</div>
                <Badge variant={statusBadge[selected.status]}>{selected.status}</Badge>
                <div className="text-[10px] text-hermes-muted font-mono">Runtime</div>
                <div className="text-[10px] text-hermes-text font-mono">{selected.runtime || "—"}</div>
                <div className="text-[10px] text-hermes-muted font-mono">Tasks Done</div>
                <div className="text-[10px] text-hermes-text font-mono">{selected.metrics?.tasks_completed || 0}</div>
                <div className="text-[10px] text-hermes-muted font-mono">Success Rate</div>
                <div className="text-[10px] text-hermes-text font-mono">
                  {((selected.metrics?.success_rate || 0) * 100).toFixed(0)}%
                </div>
              </div>
              {selected.metrics && (
                <ProgressBar value={selected.metrics.success_rate * 100} size="sm" />
              )}
              <p className="text-xs text-hermes-muted">
                Tokens: {selected.metrics?.tokens_consumed?.toLocaleString() || 0}
              </p>
            </div>
          ) : (
            <div className="flex items-center justify-center h-32 text-xs text-hermes-muted font-mono">
              ← Select an agent to view details
            </div>
          )}
        </Card>
      </div>

      {/* Messages */}
      <div className="mt-4">
        <CollaborationMessages missionId={selected?.current_mission} />
      </div>
    </div>
  );
}

function CollaborationMessages({ missionId }: { missionId?: string }) {
  const { data: messages } = useCollaborationMessages(missionId);

  return (
    <Card title="Collaboration" subtitle={messages?.length ? `${messages.length} messages` : "No messages"}>
      <div className="flex flex-col gap-2 max-h-[200px] overflow-y-auto">
        {messages?.slice(-20).map((msg) => (
          <div key={msg.id} className="flex items-start gap-2 p-2 rounded bg-hermes-bg/50 text-xs">
            <Badge variant={msg.type === "HELP_REQUEST" ? "warning" : "info"}>{msg.type}</Badge>
            <span className="text-hermes-amber font-mono">{msg.from_agent}</span>
            {msg.to_agent && (
              <>
                <span className="text-hermes-muted">→</span>
                <span className="text-hermes-text font-mono">{msg.to_agent}</span>
              </>
            )}
            <span className="text-hermes-muted ml-auto text-[10px]">
              {new Date(msg.timestamp).toLocaleTimeString()}
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}
