"use client";

import { useState } from "react";
import { Card, Badge } from "@/components/ui/card";
import { useSecurityStatus, useSecurityThreats, useSecurityPolicies } from "@/hooks/use-api";
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
  //
  // G-39 : cette passe-la avait retire les mocks NOMMES et laisse trois
  // tableaux fabriques INLINES dans le JSX — quatre menaces (« Unauthorized
  // file access · agent.unknown_dev · 3 occurrences »), six politiques
  // (« tool.exec: allow (Safety First) ») et six profils d'isolation. Rien
  // de tout cela n'existait nulle part. Pire, `useSecurityThreats()` etait
  // deja appele et sa donnee LIEE puis jetee : la vraie liste est vide, et
  // l'ecran montrait quatre menaces detectees.
  //
  // Un mock nomme se trouve en cherchant `MOCK_` ; un tableau litteral
  // dans le JSX, non. C'est pour cela que le nettoyage precedent l'a
  // manque, et pour cela qu'une garde le cherche desormais.
  const { data: status, isLoading, isError, error } = useSecurityStatus();
  const { data: threatList } = useSecurityThreats();
  const { data: policyList } = useSecurityPolicies();

  const empty: SecurityStatus = {
    permissions: { total_permissions: 0, total_policies: 0 },
    trust: { total_agents: 0, average_score: 0, by_level: {}, total_violations: 0 },
    threats: { total_threats: 0, mitigated: 0, unmitigated: 0, by_level: {} },
    isolation: { total_profiles: 0, active_sessions: 0, total_violations: 0 },
  };
  const s = (status as SecurityStatus | undefined) ?? empty;
  const threats = Array.isArray(threatList) ? threatList : [];
  const policies = Array.isArray(policyList) ? policyList : [];
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
            {threats.length === 0 && (
              <p className="text-[10px] text-hermes-dim p-2">
                Aucune menace enregistrée. `ThreatDetector` n&apos;a pas de
                producteur sur cette installation : lire « aucune détection »,
                jamais « aucune menace ».
              </p>
            )}
            {(threats as {
              type?: string; level?: string; source?: string; count?: number;
            }[]).map((threat, i) => (
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
            {policies.length === 0 && (
              <p className="text-[10px] text-hermes-dim p-2">
                `SecurityEngine` ne porte aucune politique sur cette
                installation. La politique <strong>réellement appliquée</strong>
                est la matrice d&apos;Aegis, qu&apos;`AegisEngine` relit à
                chaque évaluation — Governance Center, onglet « Politique en
                vigueur ».
              </p>
            )}
            {policies.map((p, i) => (
              <div key={String(p.id ?? i)} className="flex items-center justify-between p-2 rounded-lg border border-hermes-border/50">
                <div>
                  <div className="text-[10px] font-mono text-hermes-text">
                    {String(p.resource_type ?? p.name ?? "—")}
                  </div>
                  <div className="text-[9px] text-hermes-muted">
                    {String(p.name ?? "—")} · {String(p.action ?? "—")}
                  </div>
                </div>
                <Badge variant={
                  p.effect === "allow" ? "success" :
                  p.effect === "deny" ? "danger" : "warning"
                } className="text-[9px]">{String(p.effect ?? "—")}</Badge>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Isolation Profiles — G-39 : six profils inventes (« Default LOW »,
          « Air Gap MAX », avec sessions, memoire et CPU) y etaient ecrits en
          dur. `IsolationManager` en sert le COMPTE dans `/security/status`, et
          aucune route ne les enumere : on affiche donc ce qu'on a, et on dit
          ce qu'on n'a pas. */}
      <Card title="Isolation Profiles">
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: "Profils", value: s.isolation.total_profiles },
            { label: "Sessions actives", value: s.isolation.active_sessions },
            { label: "Violations", value: s.isolation.total_violations },
          ].map((c) => (
            <div key={c.label} className="p-3 rounded-lg border border-hermes-border bg-hermes-card/50">
              <div className="text-[9px] text-hermes-muted font-mono uppercase tracking-wider">
                {c.label}
              </div>
              <div className="num text-[20px] text-hermes-text mt-1">{c.value}</div>
            </div>
          ))}
        </div>
        <p className="pt-3 text-[10px] text-hermes-dim">
          Aucune route n&apos;énumère les profils : `/security/status` en donne
          le compte, pas le détail. Les afficher un par un demanderait une
          route qui n&apos;existe pas.
        </p>
      </Card>
    </div>
  );
}
