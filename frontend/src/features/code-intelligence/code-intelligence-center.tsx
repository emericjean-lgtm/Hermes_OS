"use client";

import { useState } from "react";
import { Card, Badge } from "@/components/ui/card";
import {
  Activity,
  BrainCircuit,
  GitCompare,
  Layers,
  TrendingUp,
  Clock,
  Target,
  Play,
  Code2,
  Bug,
} from "lucide-react";

// ── Types ─────────────────────────────────────────────────

interface ProviderScore {
  provider: string;
  score: number;
  factors: Record<string, number>;
  reasoning: string[];
}

interface RoutingDecision {
  task_type: string;
  selected_provider: string;
  strategy: string;
  primary_reason: string;
  scores: ProviderScore[];
  hybrid_order: string[];
}

interface CIRuntimeScore {
  provider: string;
  suitability: number;
  historical_success: number;
  avg_duration_ms: number;
  resource_cost: number;
  available: boolean;
}

interface CITaskRecord {
  task_id: string;
  task_type: string;
  selected_provider: string;
  strategy: string;
  success: boolean;
  duration_ms: number;
  kc_score: number;
  omp_score: number;
  primary_reason: string;
  timestamp: string;
}

interface CIAgentStatus {
  agent_id: string;
  status: string;
  op_status: string;
  total_tasks: number;
  successful_tasks: number;
  klaatcode_tasks: number;
  ohmypi_tasks: number;
  hybrid_tasks: number;
  success_rate: number;
  router_stats: {
    klaatcode: { total: number; success_rate: number };
    ohmypi: { total: number; success_rate: number };
    total_executions: number;
  };
}

// ── Mock data ─────────────────────────────────────────────

const MOCK_STATUS: CIAgentStatus = {
  agent_id: "ci_demo001",
  status: "READY",
  op_status: "idle",
  total_tasks: 142,
  successful_tasks: 131,
  klaatcode_tasks: 68,
  ohmypi_tasks: 53,
  hybrid_tasks: 21,
  success_rate: 92.3,
  router_stats: {
    klaatcode: { total: 68, success_rate: 94.1 },
    ohmypi: { total: 53, success_rate: 90.6 },
    total_executions: 142,
  },
};

const MOCK_TASK_TYPES = [
  { type: "code_analysis", kc: 0.92, omp: 0.65, best: "klaatcode" as const },
  { type: "refactoring", kc: 0.45, omp: 0.94, best: "ohmypi" as const },
  { type: "debugging", kc: 0.22, omp: 0.96, best: "ohmypi" as const },
  { type: "architecture_review", kc: 0.90, omp: 0.35, best: "klaatcode" as const },
  { type: "code_generation", kc: 0.60, omp: 0.88, best: "ohmypi" as const },
  { type: "test_generation", kc: 0.78, omp: 0.55, best: "klaatcode" as const },
  { type: "optimization", kc: 0.72, omp: 0.68, best: "hybrid" as const },
  { type: "diagnostics", kc: 0.85, omp: 0.62, best: "hybrid" as const },
  { type: "code_review", kc: 0.88, omp: 0.60, best: "hybrid" as const },
  { type: "documentation", kc: 0.75, omp: 0.30, best: "klaatcode" as const },
];

// ── Component ─────────────────────────────────────────────

export function CodeIntelligenceCenter() {
  const [selectedTask, setSelectedTask] = useState<string>("");
  const [executing, setExecuting] = useState(false);
  const [lastDecision, setLastDecision] = useState<RoutingDecision | null>(null);

  const status = MOCK_STATUS;

  const handleExecute = async (taskType: string) => {
    setSelectedTask(taskType);
    setExecuting(true);
    // Simulate routing
    const mock = MOCK_TASK_TYPES.find((t) => t.type === taskType);
    const decision: RoutingDecision = {
      task_type: taskType,
      selected_provider: mock?.best || "klaatcode",
      strategy: mock?.best === "hybrid" ? "hybrid_both" : "single_best",
      primary_reason: mock?.best === "ohmypi" ? "lsp_required" : "project_analysis",
      scores: [
        {
          provider: "klaatcode",
          score: mock?.kc || 0.5,
          factors: { task_fit: mock?.kc || 0.5, historical_success: 0.94, cost_efficiency: 0.85 },
          reasoning: ["KlaatCode fit for analysis"],
        },
        {
          provider: "ohmypi",
          score: mock?.omp || 0.5,
          factors: { task_fit: mock?.omp || 0.5, historical_success: 0.91, cost_efficiency: 0.60 },
          reasoning: ["OhMyPi fit for LSP tasks"],
        },
      ],
      hybrid_order: ["klaatcode", "ohmypi"],
    };
    setLastDecision(decision);
    setTimeout(() => setExecuting(false), 800);
  };

  return (
    <div className="animate-fade-in p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-hermes-text font-mono">
            Code Intelligence
          </h2>
          <p className="text-xs text-hermes-muted mt-1">
            Intelligent routing between KlaatCode and Oh My Pi — automatic provider selection
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="success">
            <BrainCircuit className="w-3 h-3 mr-1" />
            Router Active
          </Badge>
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-5 gap-3 mb-6">
        {[
          { icon: Target, label: "Total Tasks", value: status.total_tasks, color: "text-hermes-blue" },
          { icon: TrendingUp, label: "Success Rate", value: `${status.success_rate}%`, color: "text-hermes-green" },
          { icon: Layers, label: "KlaatCode", value: status.klaatcode_tasks, color: "text-hermes-amber" },
          { icon: Code2, label: "Oh My Pi", value: status.ohmypi_tasks, color: "text-hermes-purple" },
          { icon: GitCompare, label: "Hybrid", value: status.hybrid_tasks, color: "text-hermes-pink" },
        ].map((stat) => (
          <div
            key={stat.label}
            className="bg-hermes-card border border-hermes-border rounded-lg p-3 text-center"
          >
            <stat.icon className={`w-4 h-4 mx-auto mb-1 ${stat.color}`} />
            <div className="text-[10px] text-hermes-muted font-mono uppercase">{stat.label}</div>
            <div className="text-lg font-bold text-hermes-text font-mono">{stat.value}</div>
          </div>
        ))}
      </div>

      {/* Task Type Grid */}
      <Card title="Task Routing Map" className="mb-6">
        <div className="grid grid-cols-2 gap-2">
          {MOCK_TASK_TYPES.map((task) => (
            <button
              key={task.type}
              onClick={() => handleExecute(task.type)}
              disabled={executing}
              className={`flex items-center justify-between p-3 rounded-lg border text-left transition-all ${
                selectedTask === task.type
                  ? "border-hermes-amber/50 bg-hermes-amber/5"
                  : "border-hermes-border hover:border-hermes-border/70 hover:bg-hermes-card/80"
              } disabled:opacity-50`}
            >
              <div>
                <span className="text-sm font-mono text-hermes-text">{task.type}</span>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-[10px] text-hermes-muted">
                    KC: <span className={task.kc > task.omp ? "text-hermes-amber" : "text-hermes-muted"}>
                      {task.kc.toFixed(2)}
                    </span>
                  </span>
                  <span className="text-[10px] text-hermes-muted">
                    OMP: <span className={task.omp > task.kc ? "text-hermes-purple" : "text-hermes-muted"}>
                      {task.omp.toFixed(2)}
                    </span>
                  </span>
                </div>
              </div>
              <Badge variant={
                task.best === "klaatcode" ? "warning" :
                task.best === "ohmypi" ? "default" : "success"
              }>
                {task.best}
              </Badge>
            </button>
          ))}
        </div>
      </Card>

      {/* Last Decision */}
      {lastDecision && (
        <Card title={`Decision: ${lastDecision.task_type}`} className="mb-6">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-xs text-hermes-muted font-mono mb-2">Selected</div>
              <div className="flex items-center gap-2">
                <span className="text-lg font-bold font-mono text-hermes-text">
                  {lastDecision.selected_provider}
                </span>
                <Badge variant="success">{lastDecision.strategy}</Badge>
              </div>
              <div className="text-[10px] text-hermes-muted mt-1">
                Reason: {lastDecision.primary_reason}
              </div>
            </div>
            <div>
              <div className="text-xs text-hermes-muted font-mono mb-2">Scores</div>
              {lastDecision.scores.map((s) => (
                <div key={s.provider} className="flex items-center justify-between mb-1">
                  <span className="text-xs font-mono text-hermes-text">{s.provider}</span>
                  <div className="flex items-center gap-2">
                    <div className="w-24 h-2 bg-hermes-bg rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${
                          s.provider === "klaatcode" ? "bg-hermes-amber" : "bg-hermes-purple"
                        }`}
                        style={{ width: `${s.score * 100}%` }}
                      />
                    </div>
                    <span className="text-[10px] font-mono text-hermes-muted">
                      {s.score.toFixed(2)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Card>
      )}

      {/* Provider Routing Flow */}
      <Card title="Routing Pipeline" className="mb-6">
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2 text-xs font-mono text-hermes-muted">
            <span className="text-hermes-amber">Mission Planner</span>
            <span>→</span>
            <span className="text-hermes-blue">Code Intelligence Agent</span>
            <span>→</span>
            <span className="text-hermes-purple">Router</span>
            <span>→</span>
            <span className="text-hermes-green">Provider Engine</span>
          </div>
          <div className="flex items-center gap-2 text-xs font-mono text-hermes-muted ml-16">
            <span className="text-hermes-amber">├─ KlaatCode</span>
            <span className="text-hermes-muted">(analysis · diagnostics · review)</span>
          </div>
          <div className="flex items-center gap-2 text-xs font-mono text-hermes-muted ml-16">
            <span className="text-hermes-purple">└─ Oh My Pi</span>
            <span className="text-hermes-muted">(LSP · DAP · AST · execution)</span>
          </div>
        </div>
      </Card>

      {/* Provider Capabilities */}
      <div className="grid grid-cols-2 gap-4">
        <Card title="KlaatCode" className="mb-0">
          <div className="space-y-2">
            {["Project Analysis", "Architecture Review", "Diagnostics", "Test Generation", "Code Review", "Documentation"].map((cap) => (
              <div key={cap} className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-hermes-amber" />
                <span className="text-xs text-hermes-text font-mono">{cap}</span>
              </div>
            ))}
          </div>
        </Card>
        <Card title="Oh My Pi" className="mb-0">
          <div className="space-y-2">
            {["LSP Editing", "DAP Debugging", "AST Transform", "Code Execution", "Git Operations", "40+ LLM Routing"].map((cap) => (
              <div key={cap} className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-hermes-purple" />
                <span className="text-xs text-hermes-text font-mono">{cap}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
