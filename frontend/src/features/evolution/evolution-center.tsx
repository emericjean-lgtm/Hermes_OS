"use client";

import { useState } from "react";
import { Card, Badge } from "@/components/ui/card";
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

// ── Mock Data ────────────────────────────────────────────

const MOCK_PROPOSALS: EvolutionProposal[] = [
  { proposal_id: "p1", evolution_type: "runtime_optimization", target_component: "runtime.orchestrator", description: "Reduce runtime latency: 520ms avg → target 300ms", expected_gain: 25, risk_level: "medium", confidence: 0.75, status: "simulated" },
  { proposal_id: "p2", evolution_type: "skill_improvement", target_component: "skills.distribution", description: "Remove 3 unused skills (60% unused ratio)", expected_gain: 12, risk_level: "low", confidence: 0.88, status: "approved" },
  { proposal_id: "p3", evolution_type: "model_switch", target_component: "runtime.orchestrator", description: "Switch to better model: score 0.65 → 0.85", expected_gain: 30, risk_level: "high", confidence: 0.62, status: "detected" },
  { proposal_id: "p4", evolution_type: "workflow_optimization", target_component: "execution.engine", description: "Optimize workflow: 40% repeat rate detected", expected_gain: 15, risk_level: "medium", confidence: 0.65, status: "detected" },
  { proposal_id: "p5", evolution_type: "memory_optimization", target_component: "memory.unified", description: "Improve KG hit rate: 45% → target 70%", expected_gain: 20, risk_level: "low", confidence: 0.72, status: "applied" },
  { proposal_id: "p6", evolution_type: "agent_improvement", target_component: "agent.supervisor", description: "Agent success rate: 55% → target 80%", expected_gain: 28, risk_level: "medium", confidence: 0.68, status: "simulated" },
  { proposal_id: "p7", evolution_type: "architecture_improvement", target_component: "core.integration", description: "Redesign integration layer for parallel dispatch", expected_gain: 35, risk_level: "high", confidence: 0.45, status: "detected" },
  { proposal_id: "p8", evolution_type: "runtime_optimization", target_component: "runtime.ktransformers", description: "KTransformers cache optimization", expected_gain: 18, risk_level: "low", confidence: 0.82, status: "applied" },
];

const MOCK_REPORTS: EvolutionReport[] = [
  { report_id: "r1", improvements_found: 8, applied_changes: ["KG hit rate optimization", "KTC cache tuning"], rejected_changes: ["Architecture redesign"], total_gain_percent: 38 },
  { report_id: "r2", improvements_found: 5, applied_changes: ["Skill cleanup"], rejected_changes: [], total_gain_percent: 12 },
];

const evolutionTypeColor = (type: string) => {
  const colors: Record<string, string> = {
    runtime_optimization: "text-hermes-blue",
    skill_improvement: "text-hermes-green",
    model_switch: "text-hermes-purple",
    workflow_optimization: "text-hermes-amber",
    agent_improvement: "text-hermes-pink",
    memory_optimization: "text-emerald-400",
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

  const stats = {
    total: MOCK_PROPOSALS.length,
    applied: MOCK_PROPOSALS.filter(p => p.status === "applied").length,
    detected: MOCK_PROPOSALS.filter(p => p.status === "detected").length,
    totalGain: MOCK_PROPOSALS.filter(p => p.status === "applied").reduce((s, p) => s + p.expected_gain, 0),
  };

  return (
    <div className="animate-fade-in p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-hermes-text font-mono">Self Evolution</h2>
          <p className="text-xs text-hermes-muted mt-1">
            Autonomous improvement engine — detect, simulate, validate, apply, learn
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="success"><BrainCircuit className="w-3 h-3 mr-1" />Active</Badge>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-5 gap-3 mb-6">
        {[
          { icon: Lightbulb, label: "Proposals", value: stats.total, sub: "found", color: "text-hermes-blue" },
          { icon: TrendingUp, label: "Applied", value: stats.applied, sub: "optimizations", color: "text-hermes-green" },
          { icon: AlertTriangle, label: "Pending", value: stats.detected, sub: "to review", color: "text-hermes-amber" },
          { icon: Target, label: "Total Gain", value: `${stats.totalGain}%`, sub: "estimated", color: "text-hermes-purple" },
          { icon: Zap, label: "Avg Conf", value: `${(MOCK_PROPOSALS.reduce((s, p) => s + p.confidence, 0) / stats.total * 100).toFixed(0)}%`, sub: "confidence", color: "text-emerald-400" },
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
              </tr>
            </thead>
            <tbody>
              {MOCK_PROPOSALS.map((p) => (
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
            {MOCK_REPORTS.map((r) => (
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
