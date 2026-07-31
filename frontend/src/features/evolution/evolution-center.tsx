"use client";

import { useState } from "react";
import { Card, Badge } from "@/components/ui/card";
import {
  useEvolutionAction,
  useEvolutionAnalyze,
  useEvolutionProposals,
  useEvolutionReports,
} from "@/hooks/use-api";
import { ConfirmAction } from "@/components/confirm-action";
import {
  Activity,
  TrendingUp,
  Lightbulb,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Clock,
  BrainCircuit,
  Target,
  Zap,
} from "lucide-react";
import { CenterHeader } from "@/components/center-scaffold";

// ── Types ────────────────────────────────────────────────

interface EvolutionProposal {
  proposal_id: string;
  evolution_type: string;
  target_component: string;
  description: string;
  expected_gain: number;
  risk_level: string;
  confidence: number;
  status: string;
}

interface EvolutionReport {
  report_id: string;
  improvements_found: number;
  applied_changes: string[];
  rejected_changes: string[];
  total_gain_percent: number;
}


const evolutionTypeColor = (type: string) => {
  const colors: Record<string, string> = {
    runtime_optimization: "text-hermes-blue",
    skill_improvement: "text-hermes-green",
    model_switch: "text-hermes-purple",
    workflow_optimization: "text-hermes-amber",
    agent_improvement: "text-hermes-pink",
    memory_optimization: "text-hermes-green",
    architecture_improvement: "text-hermes-red",
  };
  return colors[type] || "text-hermes-muted";
};

const statusBadge = (status: string) => {
  const variants: Record<string, "success" | "warning" | "danger" | "default"> = {
    detected: "warning", simulated: "default",
    approved: "warning", applied: "success",
    rejected: "danger", failed: "danger",
  };
  return <Badge variant={variants[status] || "default"} className="text-[9px]">{status}</Badge>;
};

// ── Component ────────────────────────────────────────────

export function EvolutionCenter() {
  const [selectedProposal, setSelectedProposal] = useState<string | null>(null);

  // Real data from /api/v1/evolution/*. This Center used to render module-level
  // MOCK_PROPOSALS / MOCK_REPORTS, so its counters were fabricated in the
  // browser regardless of what the backend reported (R-001 STEP 10).
  const { data: proposalsData, isLoading, isError, error } = useEvolutionProposals();
  const { data: reportsData } = useEvolutionReports();
  // simulate / approve / apply existent côté backend et n'avaient aucun
  // déclencheur dans le Cockpit. Chacun passe par une confirmation (P-002).
  const evolutionAction = useEvolutionAction();
  const analyze = useEvolutionAnalyze();
  const [actionError, setActionError] = useState<string | null>(null);

  const proposals: EvolutionProposal[] = proposalsData ?? [];
  const reports: EvolutionReport[] = reportsData ?? [];

  const stats = {
    total: proposals.length,
    applied: proposals.filter(p => p.status === "applied").length,
    detected: proposals.filter(p => p.status === "detected").length,
    totalGain: proposals
      .filter(p => p.status === "applied")
      .reduce((sum, p) => sum + p.expected_gain, 0),
  };

  // Loading, empty and failed must be distinguishable — rendering zeros for all
  // three is what made a disconnected backend look like an idle system.
  if (isLoading) {
    return (
      <div className="animate-fade-in p-6 text-xs text-hermes-muted">
        Loading evolution proposals…
      </div>
    );
  }
  if (isError) {
    return (
      <div className="animate-fade-in p-6">
      {actionError && (
        <div className="mb-3 px-3 py-2 rounded-lg bg-hermes-red/10 border border-hermes-red/30 text-hermes-red text-xs font-mono">
          {actionError}
        </div>
      )}
        <Card title="Evolution Engine" className="p-4 border-hermes-red/40">
          <div className="flex items-center gap-2 text-hermes-red text-sm">
            <AlertTriangle size={16} />
            <span>Could not reach the Evolution Engine</span>
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
        title="Self Evolution"
        subtitle="Moteur d'amélioration autonome — détecter, simuler, valider, appliquer, apprendre"
        right={
          <Badge variant="success">
            <BrainCircuit className="w-3 h-3" />
            Actif
          </Badge>
        }
      />

      {/* Stats */}
      <div className="grid grid-cols-5 gap-3 mb-6">
        {[
          { icon: Lightbulb, label: "Proposals", value: stats.total, sub: "found", color: "text-hermes-blue" },
          { icon: TrendingUp, label: "Applied", value: stats.applied, sub: "optimizations", color: "text-hermes-green" },
          { icon: AlertTriangle, label: "Pending", value: stats.detected, sub: "to review", color: "text-hermes-amber" },
          { icon: Target, label: "Total Gain", value: `${stats.totalGain}%`, sub: "estimated", color: "text-hermes-purple" },
          { icon: Zap, label: "Avg Conf", value: stats.total ? `${(proposals.reduce((sum, p) => sum + p.confidence, 0) / stats.total * 100).toFixed(0)}%` : "—", sub: "confidence", color: "text-hermes-green" },
        ].map((stat) => (
          <div key={stat.label} className="bg-hermes-card border border-hermes-border rounded-lg p-3">
            <stat.icon className={`w-4 h-4 mb-1 ${stat.color}`} />
            <div className="text-[10px] text-hermes-muted font-mono uppercase">{stat.label}</div>
            <div className={`text-lg font-bold font-mono ${stat.color} mt-0.5`}>{stat.value}</div>
            <div className="text-[9px] text-hermes-muted">{stat.sub}</div>
          </div>
        ))}
      </div>

      {/* Proposals Table */}
      <Card title="Evolution Proposals" className="mb-6">
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="text-[10px] text-hermes-muted font-mono uppercase border-b border-hermes-border">
                <th className="pb-2 pr-4">Type</th>
                <th className="pb-2 pr-4">Target</th>
                <th className="pb-2 pr-4">Description</th>
                <th className="pb-2 pr-4">Gain</th>
                <th className="pb-2 pr-4">Risk</th>
                <th className="pb-2 pr-4">Conf</th>
                <th className="pb-2 pr-4">Status</th>
                <th className="pb-2 pr-4">Actions</th>
              </tr>
            </thead>
            <tbody>
              {proposals.map((p) => (
                <tr
                  key={p.proposal_id}
                  onClick={() => setSelectedProposal(selectedProposal === p.proposal_id ? null : p.proposal_id)}
                  className={`border-b border-hermes-border/30 hover:bg-hermes-card/30 cursor-pointer ${
                    selectedProposal === p.proposal_id ? "bg-hermes-amber/5" : ""
                  }`}
                >
                  <td className="py-2 pr-4">
                    <span className={`text-[10px] font-mono ${evolutionTypeColor(p.evolution_type)}`}>
                      {p.evolution_type.replace(/_/g, ' ')}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-[10px] font-mono text-hermes-muted">{p.target_component}</td>
                  <td className="py-2 pr-4 text-[10px] text-hermes-text max-w-[200px] truncate">{p.description}</td>
                  <td className="py-2 pr-4 text-xs font-mono text-hermes-green">+{p.expected_gain}%</td>
                  <td className="py-2 pr-4">{statusBadge(p.risk_level)}</td>
                  <td className="py-2 pr-4 text-xs font-mono">{(p.confidence * 100).toFixed(0)}%</td>
                  <td className="py-2 pr-4">{statusBadge(p.status)}</td>
                  <td className="py-2 pr-4" onClick={(e) => e.stopPropagation()}>
                    <div className="flex gap-1 flex-wrap">
                      {(["simulate", "approve", "apply"] as const).map((verb) => (
                        <ConfirmAction
                          key={verb}
                          label={
                            verb === "simulate" ? "Simuler"
                              : verb === "approve" ? "Approuver" : "Appliquer"
                          }
                          severity={verb === "apply" ? "destructive" : "impactful"}
                          description={
                            verb === "simulate"
                              ? "Exécute la proposition à blanc et mesure son effet."
                              : verb === "approve"
                                ? "Marque la proposition comme approuvée."
                                : "Applique la modification au système. Irréversible."
                          }
                          target={`${p.evolution_type} — ${p.target_component}`}
                          pending={evolutionAction.isPending}
                          onConfirm={() => {
                            setActionError(null);
                            evolutionAction.mutate(
                              { id: p.proposal_id, action: verb },
                              {
                                onError: (err) =>
                                  setActionError(
                                    err instanceof Error ? err.message : "Action refusée"),
                              },
                            );
                          }}
                        />
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Pipeline Viz */}
      <Card title="Evolution Pipeline" className="mb-6">
        <div className="flex items-center justify-between gap-2">
          {["Collect", "Analyze", "Detect", "Propose", "Simulate", "Validate", "Apply", "Learn"].map((step, i) => (
            <div key={step} className="flex-1 text-center">
              <div className={`w-8 h-8 mx-auto rounded-full flex items-center justify-center text-[10px] font-bold font-mono ${
                i < 5 ? "bg-hermes-amber/20 text-hermes-amber" :
                i < 7 ? "bg-hermes-green/20 text-hermes-green" :
                "bg-hermes-purple/20 text-hermes-purple"
              }`}>
                {i + 1}
              </div>
              <div className="text-[8px] font-mono text-hermes-muted mt-1">{step}</div>
              {i < 7 && <div className="text-[8px] text-hermes-border mt-0.5">→</div>}
            </div>
          ))}
        </div>
      </Card>

      {/* Patterns & Reports */}
      <div className="grid grid-cols-2 gap-4">
        <Card title="Optimization Patterns">
          <div className="space-y-2">
            {[
              { pattern: "High latency → Runtime optimization", freq: 12, rate: 0.85, gain: 22 },
              { pattern: "Low skill usage → Unload skills", freq: 8, rate: 0.92, gain: 14 },
              { pattern: "Low model score → Switch model", freq: 5, rate: 0.70, gain: 28 },
              { pattern: "High repeat rate → Workflow opt", freq: 4, rate: 0.75, gain: 16 },
            ].map((pt, i) => (
              <div key={i} className="flex items-center justify-between p-2 rounded-lg border border-hermes-border/50">
                <div className="flex-1 min-w-0">
                  <div className="text-[10px] font-mono text-hermes-text truncate">{pt.pattern}</div>
                  <div className="text-[9px] text-hermes-muted">{pt.freq}x · success {(pt.rate * 100).toFixed(0)}%</div>
                </div>
                <span className="text-[10px] font-mono text-hermes-green ml-2">+{pt.gain}%</span>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Recent Reports">
          <div className="space-y-3">
            {reports.map((r) => (
              <div key={r.report_id} className="p-3 rounded-lg border border-hermes-border/50">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-mono text-hermes-text">{r.report_id}</span>
                  <span className="text-[10px] font-mono text-hermes-green">+{r.total_gain_percent}%</span>
                </div>
                <div className="text-[9px] text-hermes-muted">{r.improvements_found} improvements found</div>
                <div className="text-[9px] text-hermes-green mt-1">
                  Applied: {r.applied_changes.join(", ")}
                </div>
                {r.rejected_changes.length > 0 && (
                  <div className="text-[9px] text-hermes-red mt-0.5">
                    Rejected: {r.rejected_changes.join(", ")}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
