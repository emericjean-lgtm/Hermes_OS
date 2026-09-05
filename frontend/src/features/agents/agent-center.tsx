"use client";

import {
  useAgents,
  useCollaborationMessages,
  useExecutionStatistics,
  useMissions,
  useMonitoringResources,
} from "@/hooks/use-api";
import { useCockpitStore } from "@/hooks/use-store";
import { Card, Badge, ProgressBar } from "@/components/ui/card";
import type { Agent, AgentStatus } from "@/types/hermes";
import { CenterHeader } from "@/components/center-scaffold";
import { formatGioPair, vramOccupee, vramPourcent } from "@/lib/format";

// Real agent status/metrics/trust — before HOS-070, AgentRegistry.
// update_status()/update_metrics() were only ever called from a dispatch
// path (AgentSupervisor.dispatch_node()) nothing in real Mission/Autonomous
// execution ever reached, so every agent showed its initial "READY, 0
// tasks" state forever. MissionExecutor now syncs real outcomes here.
//
// AgentStatus case-mismatch (also fixed here, in toAgent() — client.ts):
// the backend's AgentStatus enum is lowercase ("ready", "busy", ...); this
// component's status-keyed lookups only ever worked once that was
// normalized to uppercase on the way in.

const statusBadge: Record<AgentStatus, keyof typeof statusColors> = {
  CREATED: "default",
  STARTING: "info",
  READY: "success",
  BUSY: "purple",
  PAUSED: "warning",
  COMPLETED: "success",
  FAILED: "danger",
  STOPPING: "warning",
  STOPPED: "default",
  RECOVERING: "warning",
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
  const { data: missions } = useMissions();
  const { data: execStats } = useExecutionStatistics();
  const { data: resources } = useMonitoringResources() as { data?: import("@/types/hermes").ResourceStatus };
  const { selectedAgentId, selectAgent } = useCockpitStore();
  const selected = agents?.find((a) => a.id === selectedAgentId);

  const statusCounts = agents?.reduce((acc, a) => {
    acc[a.status] = (acc[a.status] || 0) + 1;
    return acc;
  }, {} as Record<string, number>) || {};

  const activeMissions = missions?.filter((m) => m.status === "RUNNING").length ?? 0;
  const scheduler = execStats?.executor_stats?.scheduler;
  const gpu = resources?.gpu;

  return (
    <div className="animate-fade-in">
      <CenterHeader
        title="Agent Center"
        subtitle="Supervision multi-agents et collaboration"
      />

      {/* Overview stats — real agent status counts */}
      <div className="grid grid-cols-4 gap-3 mb-4">
        {(["READY", "BUSY", "FAILED", "COMPLETED"] as AgentStatus[]).map((s) => (
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

      {/* Resource + task volume — real data from Execution (HOS-069) and
          Runtime resource monitoring, reused rather than re-fetched */}
      <div className="grid grid-cols-2 gap-4 mb-4">
        <Card title="Ressources">
          {gpu ? (
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between text-[10px] font-mono">
                <span className="text-hermes-muted">VRAM ({gpu.name || "GPU"})</span>
                <span className="text-hermes-text">
                  {formatGioPair(vramOccupee(gpu), gpu.vram_total_bytes)}
                </span>
              </div>
              <ProgressBar
                value={vramPourcent(gpu) ?? 0}
                size="sm"
              />
              {gpu.utilization_pct != null && (
                <div className="flex items-center justify-between text-[10px] font-mono">
                  <span className="text-hermes-muted">Utilisation GPU</span>
                  <span className="text-hermes-text">{gpu.utilization_pct.toFixed(0)}%</span>
                </div>
              )}
            </div>
          ) : (
            <div className="text-[10px] text-hermes-muted font-mono py-2">Indisponible</div>
          )}
        </Card>
        <Card title="Activité">
          <div className="grid grid-cols-2 gap-2 text-[10px] font-mono">
            <div className="text-hermes-muted">Missions actives</div>
            <div className="text-hermes-text text-right">{activeMissions}</div>
            <div className="text-hermes-muted">Tâches en cours</div>
            <div className="text-hermes-text text-right">{scheduler?.running ?? 0}</div>
            <div className="text-hermes-muted">Tâches terminées</div>
            <div className="text-hermes-text text-right">{scheduler?.completed ?? 0}</div>
            <div className="text-hermes-muted">Échecs</div>
            <div className="text-hermes-text text-right">{scheduler?.failed ?? 0}</div>
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Agent list */}
        <Card title="Agents" subtitle={isLoading ? "Chargement…" : `${agents?.length || 0} agents`}>
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
                  {agent.current_task_id ? `Tâche : ${agent.current_task_id.slice(0, 24)}` : "Inactif"}
                </div>
              </button>
            ))}
            {agents?.length === 0 && (
              <p className="text-xs text-hermes-muted py-8 text-center">Aucun agent enregistré</p>
            )}
          </div>
        </Card>

        {/* Agent detail — real performance + trust (HOS-070) */}
        <Card
          title={selected ? selected.name : "Détail de l'agent"}
          subtitle={selected ? selected.type : "Sélectionner un agent"}
        >
          {selected ? (
            <AgentDetail agent={selected} />
          ) : (
            <div className="flex items-center justify-center h-32 text-xs text-hermes-muted font-mono">
              ← Sélectionner un agent pour voir les détails
            </div>
          )}
        </Card>
      </div>

      {/* Messages */}
      <div className="mt-4">
        <CollaborationMessages missionId={selected?.current_mission_id} />
      </div>
    </div>
  );
}

function AgentDetail({ agent }: { agent: Agent }) {
  const hasTrust = agent.trust_score != null;
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-2">
        <div className="text-[10px] text-hermes-muted font-mono">Statut</div>
        <Badge variant={statusBadge[agent.status]}>{agent.status}</Badge>

        <div className="text-[10px] text-hermes-muted font-mono">Runtime</div>
        <div className="text-[10px] text-hermes-text font-mono">{agent.preferred_runtime || "—"}</div>

        <div className="text-[10px] text-hermes-muted font-mono">Modèle</div>
        <div className="text-[10px] text-hermes-text font-mono">{agent.preferred_model || "—"}</div>

        <div className="text-[10px] text-hermes-muted font-mono">Tâches terminées</div>
        <div className="text-[10px] text-hermes-text font-mono">
          {agent.total_tasks || 0}
          {agent.total_tasks ? (
            <span className="text-hermes-muted">
              {" "}({agent.successful_tasks ?? 0} ok, {agent.failed_tasks ?? 0} échec(s))
            </span>
          ) : null}
        </div>

        <div className="text-[10px] text-hermes-muted font-mono">Taux de réussite</div>
        <div className="text-[10px] font-mono">
          {/* HOS-236 : « — » et non 100 %.
              `GET /api/v1/agents` rend `success_rate: 100.0` avec
              `total_tasks: 0` — un agent qui n'a **jamais rien fait**,
              rapporté parfait — et cette ligne aggravait avec un
              `?? 100`. Zéro tâche n'est pas cent pour cent : c'est
              *aucune mesure*, et un taux affiché sur rien fait choisir
              un agent sur une réputation qu'il n'a pas gagnée. */}
          {agent.total_tasks ? (
            <span className="text-hermes-text">
              {(agent.success_rate ?? 0).toFixed(0)}%
            </span>
          ) : (
            <span className="text-hermes-muted" title="aucune tâche exécutée — rien à mesurer">
              — <span className="text-hermes-muted/70">jamais mesuré</span>
            </span>
          )}
        </div>

        <div className="text-[10px] text-hermes-muted font-mono">Confiance</div>
        <div className="text-[10px] font-mono">
          {hasTrust ? (
            <span className="text-hermes-text">
              {agent.trust_score!.toFixed(0)}/100
              <span className="text-hermes-muted"> ({agent.trust_level})</span>
            </span>
          ) : (
            <span className="text-hermes-muted">Non disponible</span>
          )}
        </div>
      </div>

      {/* Pas de barre pleine sur zéro mesure : une barre à 100 % est une
          affirmation, et il n'y a rien à affirmer. */}
      {agent.total_tasks ? (
        <ProgressBar value={agent.success_rate ?? 0} size="sm" />
      ) : null}

      {(agent.current_task_id || agent.current_mission_id) && (
        <div className="pt-2 border-t border-hermes-border/30 text-[10px] font-mono">
          {agent.current_mission_id && (
            <div>
              <span className="text-hermes-muted uppercase">Mission : </span>
              <span className="text-hermes-text">{agent.current_mission_id}</span>
            </div>
          )}
          {agent.current_task_id && (
            <div>
              <span className="text-hermes-muted uppercase">Tâche : </span>
              <span className="text-hermes-text">{agent.current_task_id}</span>
            </div>
          )}
        </div>
      )}

      <div className="flex flex-wrap gap-1">
        {agent.capabilities?.map((c) => (
          <span key={c} className="text-[9px] text-hermes-muted font-mono px-1.5 py-0.5 bg-hermes-bg rounded">
            {c}
          </span>
        ))}
      </div>
    </div>
  );
}

function CollaborationMessages({ missionId }: { missionId?: string }) {
  const { data: messages } = useCollaborationMessages(missionId);

  return (
    <Card title="Collaboration" subtitle={messages?.length ? `${messages.length} messages` : "Aucun message"}>
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
        {(!messages || messages.length === 0) && (
          <p className="text-[10px] text-hermes-muted font-mono py-4 text-center">
            Aucun message — la collaboration multi-agents n&apos;est pas encore utilisée par le
            pipeline d&apos;exécution réel (voir CollaborationEngine).
          </p>
        )}
      </div>
    </Card>
  );
}
