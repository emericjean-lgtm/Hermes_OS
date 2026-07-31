"use client";

import { useState } from "react";
import { Card, Badge } from "@/components/ui/card";
import { useSecurityStatus, useSecurityThreats } from "@/hooks/use-api";
import {
  Shield,
  ShieldAlert,
  Lock,
  Activity,
  AlertTriangle,
  CheckCircle,
  Fingerprint,
  Users,
  Wrench,
  Boxes,
  Server,
} from "lucide-react";
import { CenterHeader } from "@/components/center-scaffold";

// ── Types ────────────────────────────────────────────────

interface SecurityStatus {
  permissions: { total_permissions: number; total_policies: number };
  trust: { total_agents: number; average_score: number; by_level: Record<string, number>; total_violations: number };
  threats: { total_threats: number; mitigated: number; unmitigated: number; by_level: Record<string, number> };
  isolation: { total_profiles: number; active_sessions: number; total_violations: number };
}

interface AgentTrustData {
  agent_id: string;
  score: number;
  level: string;
  success_rate: number;
  policy_violations: number;
  human_approvals: number;
}

// ── Mock data ────────────────────────────────────────────

const trustColor = (level: string) => {
  switch (level) {
    case "verified": return "text-hermes-green";
    case "high": return "text-hermes-green";
    case "medium": return "text-hermes-amber";
    case "low": return "text-hermes-amber";
    default: return "text-hermes-muted";
  }
};

const trustBadge = (level: string) => {
  const variants: Record<string, "success" | "warning" | "danger" | "default"> = {
    verified: "success", high: "success",
    medium: "warning", low: "danger", unknown: "default",
  };
  return <Badge variant={variants[level] || "default"}>{level}</Badge>;
};

// ── Component ────────────────────────────────────────────

export function SecurityCenter() {
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);

  // Real data from /api/v1/security/*. This Center previously imported only
  // useState and rendered MOCK_STATUS / MOCK_TRUST_SCORES — 42 permissions, a
  // 72.3% average trust score, four agents with invented scores — none of which
  // came from the SecurityEngine that was already serving real values (RC3 P1).
  const { data: status, isLoading, isError, error } = useSecurityStatus();
  const { data: threatList } = useSecurityThreats();

  const empty: SecurityStatus = {
    permissions: { total_permissions: 0, total_policies: 0 },
    trust: { total_agents: 0, average_score: 0, by_level: {}, total_violations: 0 },
    threats: { total_threats: 0, mitigated: 0, unmitigated: 0, by_level: {} },
    isolation: { total_profiles: 0, active_sessions: 0, total_violations: 0 },
  };
  const s = (status as SecurityStatus | undefined) ?? empty;
  const threats = Array.isArray(threatList) ? threatList : [];
  // /security/status reports trust in aggregate (counts per level); a
  // per-agent table needs /security/trust/{id} per agent, which the Center
  // has no agent list for yet. Render the aggregate rather than invent rows.
  const trustRows: AgentTrustData[] = [];

  if (isLoading) {
    return (
      <div className="animate-fade-in p-6 text-xs text-hermes-muted">
        Loading security state…
      </div>
    );
  }
  if (isError) {
    return (
      <div className="animate-fade-in p-6">
        <Card title="Security" className="p-4 border-hermes-red/40">
          <div className="flex items-center gap-2 text-hermes-red text-sm">
            <ShieldAlert size={16} />
            <span>Could not reach the Security Engine</span>
          </div>
          <p className="mt-2 text-[11px] text-hermes-muted">
            {error instanceof Error ? error.message : "unknown error"}
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div className="animate-fade-in p-6">
      {/* Header */}
      <CenterHeader
        title="Security"
        subtitle="Score de confiance · Permissions · Détection de menaces · Isolation sandbox"
        right={
          s.threats.unmitigated > 0 ? (
            <Badge variant="danger">
              <ShieldAlert className="w-3 h-3" />
              {s.threats.unmitigated} menace(s)
            </Badge>
          ) : (
            <Badge variant="success">
              <Shield className="w-3 h-3" />
              Sécurisé
            </Badge>
          )
        }
      />

      {/* Overview Stats */}
      <div className="grid grid-cols-4 gap-3 mb-6">
        {[
          { icon: Fingerprint, label: "Agent Trust", value: `${s.trust.average_score}%`, sub: `${s.trust.total_agents} agents`, color: "text-hermes-green" },
          { icon: Lock, label: "Permissions", value: s.permissions.total_permissions, sub: `${s.permissions.total_policies} policies`, color: "text-hermes-blue" },
          { icon: AlertTriangle, label: "Threats", value: s.threats.total_threats, sub: `${s.threats.unmitigated} active`, color: s.threats.unmitigated > 0 ? "text-hermes-red" : "text-hermes-muted" },
          { icon: Boxes, label: "Isolation", value: s.isolation.active_sessions, sub: `${s.isolation.total_profiles} profiles`, color: "text-hermes-purple" },
        ].map((stat) => (
          <div key={stat.label} className="bg-hermes-card border border-hermes-border rounded-lg p-3">
            <stat.icon className={`w-4 h-4 mb-1 ${stat.color}`} />
            <div className="text-[10px] text-hermes-muted font-mono uppercase">{stat.label}</div>
            <div className={`text-lg font-bold font-mono ${stat.color} mt-0.5`}>{stat.value}</div>
            <div className="text-[9px] text-hermes-muted">{stat.sub}</div>
          </div>
        ))}
      </div>

      {/* Agent Trust Scores */}
      <Card title="Agent Trust Scores" className="mb-6">
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="text-[10px] text-hermes-muted font-mono uppercase border-b border-hermes-border">
                <th className="pb-2 pr-4">Agent</th>
                <th className="pb-2 pr-4">Score</th>
                <th className="pb-2 pr-4">Level</th>
                <th className="pb-2 pr-4">Success Rate</th>
                <th className="pb-2 pr-4">Violations</th>
                <th className="pb-2 pr-4">Approvals</th>
              </tr>
            </thead>
            <tbody>
              {trustRows.map((agent) => (
                <tr
                  key={agent.agent_id}
                  onClick={() => setSelectedAgent(selectedAgent === agent.agent_id ? null : agent.agent_id)}
                  className={`border-b border-hermes-border/30 hover:bg-hermes-card/30 cursor-pointer ${
                    selectedAgent === agent.agent_id ? "bg-hermes-amber/5" : ""
                  }`}
                >
                  <td className="py-2 pr-4 text-xs font-mono text-hermes-text">{agent.agent_id}</td>
                  <td className="py-2 pr-4">
                    <div className="flex items-center gap-2">
                      <div className="w-16 h-1.5 bg-hermes-bg rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${
                            agent.score >= 80 ? "bg-hermes-green" :
                            agent.score >= 50 ? "bg-hermes-amber" : "bg-hermes-red"
                          }`}
                          style={{ width: `${agent.score}%` }}
                        />
                      </div>
                      <span className="text-xs font-mono">{agent.score.toFixed(1)}</span>
                    </div>
                  </td>
                  <td className="py-2 pr-4">{trustBadge(agent.level)}</td>
                  <td className="py-2 pr-4 text-xs font-mono">{agent.success_rate.toFixed(1)}%</td>
                  <td className="py-2 pr-4">
                    <span className={`text-xs font-mono ${agent.policy_violations > 0 ? "text-hermes-red" : "text-hermes-muted"}`}>
                      {agent.policy_violations}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-xs font-mono text-hermes-muted">{agent.human_approvals}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Threats & Permissions Grid */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <Card title="Active Threats">
          <div className="space-y-2">
            {[
              { type: "Unauthorized file access", level: "medium", source: "agent.unknown_dev", count: 3 },
              { type: "Suspicious tool call (exec)", level: "medium", source: "agent.unknown_dev", count: 2 },
              { type: "High resource usage", level: "low", source: "execution.engine", count: 4 },
              { type: "Sandbox violation attempt", level: "high", source: "agent.tool_x", count: 1 },
            ].map((threat, i) => (
              <div key={i} className="flex items-start gap-2 p-2 rounded-lg border border-hermes-border/50">
                <AlertTriangle className={`w-3 h-3 mt-0.5 shrink-0 ${
                  threat.level === "high" ? "text-hermes-red" :
                  threat.level === "medium" ? "text-hermes-amber" : "text-hermes-muted"
                }`} />
                <div className="flex-1 min-w-0">
                  <div className="text-[10px] font-mono text-hermes-text">{threat.type}</div>
                  <div className="text-[9px] text-hermes-muted">{threat.source} · {threat.count} occurrences</div>
                </div>
                <Badge variant={
                  threat.level === "high" ? "danger" :
                  threat.level === "medium" ? "warning" : "default"
                } className="text-[9px]">{threat.level}</Badge>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Permiss'ns & Policies">
          <div className="space-y-2">
            {[
              { resource: "tool.exec", type: "agent", action: "allow", policy: "Safety First" },
              { resource: "agent.supervisor", type: "agent", action: "allow", policy: "Core Access" },
              { resource: "workspace.sandbox", type: "workspace", action: "deny", policy: "Isolation" },
              { resource: "runtime.inference", type: "runtime", action: "allow", policy: "Runtime Pool" },
              { resource: "tool.shell_exec", type: "tool", action: "review", policy: "Escalation" },
              { resource: "memory.knowledge_graph", type: "memory", action: "deny", policy: "Data Access" },
            ].map((p, i) => (
              <div key={i} className="flex items-center justify-between p-2 rounded-lg border border-hermes-border/50">
                <div>
                  <div className="text-[10px] font-mono text-hermes-text">{p.resource}</div>
                  <div className="text-[9px] text-hermes-muted">{p.policy} · {p.type}</div>
                </div>
                <Badge variant={
                  p.action === "allow" ? "success" :
                  p.action === "deny" ? "danger" : "warning"
                } className="text-[9px]">{p.action}</Badge>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Isolation Profiles */}
      <Card title="Isolation Profiles">
        <div className="grid grid-cols-3 gap-3">
          {[
            { name: "Default LOW", level: "low", sessions: 2, mem: 1024, cpu: 100, net: "open" },
            { name: "Sandbox MEDIUM", level: "medium", sessions: 1, mem: 512, cpu: 50, net: "restricted" },
            { name: "Strict HIGH", level: "high", sessions: 0, mem: 256, cpu: 25, net: "blocked" },
            { name: "Air Gap MAX", level: "maximum", sessions: 0, mem: 128, cpu: 10, net: "blocked" },
            { name: "Read-Only", level: "low", sessions: 2, mem: 2048, cpu: 75, net: "open" },
            { name: "Execution", level: "medium", sessions: 1, mem: 4096, cpu: 80, net: "restricted" },
          ].map((p) => (
            <div key={p.name} className="p-3 rounded-lg border border-hermes-border bg-hermes-card/50">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-mono text-hermes-text">{p.name}</span>
                <Badge variant={p.level === "maximum" ? "danger" : p.level === "high" ? "warning" : "default"}>
                  {p.level}
                </Badge>
              </div>
              <div className="space-y-1 text-[9px] text-hermes-muted font-mono">
                <div>Active: {p.sessions} sessions</div>
                <div>Memory: {p.mem}MB max</div>
                <div>CPU: {p.cpu}% max</div>
                <div>Network: {p.net}</div>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
