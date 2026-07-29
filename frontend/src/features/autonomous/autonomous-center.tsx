"use client";

import { useState } from "react";
import { Card, Badge } from "@/components/ui/card";
import {
  BrainCircuit,
  Target,
  Play,
  Pause,
  XCircle,
  CheckCircle,
  Activity,
  Users,
  Server,
  Wrench,
  Zap,
  BarChart3,
  Lightbulb,
} from "lucide-react";

// ── Types ────────────────────────────────────────────────

interface AutonomousGoal {
  goal_id: string;
  user_request: string;
  interpreted_goal: string;
  status: string;
  domain: string;
  language: string;
  complexity: number;
}

interface AutonomousSession {
  session_id: string;
  goal_id: string;
  active_agents: string[];
  runtime: string;
  status: string;
}

// ── Mock Data ────────────────────────────────────────────

const MOCK_GOAL: AutonomousGoal = {
  goal_id: "goal_1700000000_123",
  user_request: "Create a web application for managing maintenance operations",
  interpreted_goal: "Interpreted goal: Create a web application for managing maintenance operations. Domain: web. Analysis complete.",
  status: "completed",
  domain: "web",
  language: "python",
  complexity: 0.72,
};

const MOCK_SESSION: AutonomousSession = {
  session_id: "session_goal_1700000000_123",
  goal_id: "goal_1700000000_123",
  active_agents: ["klaatcode", "ohmypi"],
  runtime: "ktransformers",
  status: "completed",
};

const MOCK_DECISIONS = [
  { type: "agent_selection", selected: "code_intelligence", confidence: 0.90, reason: "Meta-agent best for routing" },
  { type: "runtime_selection", selected: "ktransformers", confidence: 0.85, reason: "High-performance inference" },
  { type: "tool_selection", selected: "mcp_klaatcode", confidence: 0.88, reason: "Code analysis tools" },
  { type: "skill_selection", selected: "code_analysis", confidence: 0.88, reason: "Analysis fit" },
];

const MOCK_TIMELINE = [
  { event: "Goal received", status: "done", time: "0s" },
  { event: "Analyzing request", status: "done", time: "0.5s" },
  { event: "Planning mission", status: "done", time: "1.2s" },
  { event: "Agents selected", status: "done", time: "1.5s" },
  { event: "Executing", status: "done", time: "3.0s" },
  { event: "Validating", status: "done", time: "4.5s" },
  { event: "Learning", status: "done", time: "4.8s" },
  { event: "Completed", status: "done", time: "5.0s" },
];

const statusBadge = (status: string) => {
  const v: Record<string, "success" | "warning" | "danger" | "default"> = {
    completed: "success", executing: "warning", analyzing: "default",
    planning: "default", failed: "danger", cancelled: "danger", paused: "warning",
  };
  return <Badge variant={v[status] || "default"}>{status}</Badge>;
};

// ── Component ────────────────────────────────────────────

export function AutonomousCenter() {
  const [request, setRequest] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const goal = MOCK_GOAL;
  const session = MOCK_SESSION;

  return (
    <div className="animate-fade-in p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-hermes-text font-mono">Autonomous OS</h2>
          <p className="text-xs text-hermes-muted mt-1">Final Agentic Core — HOS-063</p>
        </div>
        <Badge variant="success"><BrainCircuit className="w-3 h-3 mr-1" />Core Active</Badge>
      </div>

      {/* Goal Input */}
      <Card title="Goal Input" className="mb-6">
        <div className="flex gap-3">
          <input
            type="text"
            value={request}
            onChange={(e) => setRequest(e.target.value)}
            placeholder="Describe your goal... e.g., 'Create a web app for managing maintenance'"
            className="flex-1 bg-hermes-bg border border-hermes-border rounded-lg px-4 py-2.5 text-sm text-hermes-text font-mono focus:outline-none focus:border-hermes-amber/50 placeholder:text-hermes-muted/50"
          />
          <button
            onClick={() => setIsRunning(true)}
            disabled={!request.trim() || isRunning}
            className="px-4 py-2.5 bg-hermes-amber/10 text-hermes-amber-bright border border-hermes-amber/30 rounded-lg hover:bg-hermes-amber/20 transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            <Play className="w-4 h-4" />
            Execute
          </button>
        </div>
      </Card>

      {/* Pipeline Status */}
      <div className="grid grid-cols-8 gap-1 mb-6">
        {["Receive", "Analyze", "Plan", "Select", "Execute", "Validate", "Learn", "Report"].map((step, i) => (
          <div key={step} className="text-center">
            <div className={`w-7 h-7 mx-auto rounded-full flex items-center justify-center text-[9px] font-bold font-mono ${
              i < 6 ? "bg-hermes-green/20 text-hermes-green" :
              i < 7 ? "bg-hermes-amber/20 text-hermes-amber" :
              "bg-hermes-blue/20 text-hermes-blue"
            }`}>{i + 1}</div>
            <div className="text-[7px] font-mono text-hermes-muted mt-1">{step}</div>
          </div>
        ))}
      </div>

      {/* Current Goal */}
      <Card title="Current Goal" className="mb-6">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-[10px] text-hermes-muted font-mono uppercase mb-1">User Request</div>
            <div className="text-xs text-hermes-text font-mono bg-hermes-bg p-2 rounded-lg border border-hermes-border/50">
              {goal.user_request}
            </div>
            <div className="text-[10px] text-hermes-muted font-mono uppercase mt-3 mb-1">Interpretation</div>
            <div className="text-[10px] text-hermes-text">{goal.interpreted_goal}</div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {[
              { label: "Domain", value: goal.domain, color: "text-hermes-blue" },
              { label: "Language", value: goal.language, color: "text-hermes-green" },
              { label: "Complexity", value: `${(goal.complexity * 100).toFixed(0)}%`, color: "text-hermes-amber" },
              { label: "Status", value: goal.status, color: "text-hermes-purple" },
            ].map((s) => (
              <div key={s.label} className="bg-hermes-card/50 border border-hermes-border/50 rounded-lg p-2">
                <div className="text-[9px] text-hermes-muted font-mono uppercase">{s.label}</div>
                <div className={`text-sm font-bold font-mono ${s.color}`}>{s.value}</div>
              </div>
            ))}
          </div>
        </div>
      </Card>

      {/* Active Session */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <Card title="Session">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-hermes-muted font-mono">Agents</span>
              <div className="flex gap-1">
                {session.active_agents.map((a) => (
                  <Badge key={a} variant="default" className="text-[9px]">{a}</Badge>
                ))}
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-hermes-muted font-mono">Runtime</span>
              <span className="text-[10px] font-mono text-hermes-text">{session.runtime}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-hermes-muted font-mono">Status</span>
              {statusBadge(session.status)}
            </div>
          </div>
        </Card>

        <Card title="Decisions">
          <div className="space-y-1.5">
            {MOCK_DECISIONS.map((d, i) => (
              <div key={i} className="flex items-center justify-between text-[9px] font-mono">
                <div className="text-hermes-muted">{d.type.replace(/_/g, ' ')}</div>
                <div className="flex items-center gap-2">
                  <span className="text-hermes-text">{d.selected}</span>
                  <span className="text-hermes-green">{(d.confidence * 100).toFixed(0)}%</span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Timeline */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <Card title="Timeline">
          <div className="space-y-0">
            {MOCK_TIMELINE.map((t, i) => (
              <div key={i} className="flex items-center gap-2 py-1.5 border-b border-hermes-border/20 last:border-0">
                <div className={`w-1.5 h-1.5 rounded-full ${t.status === "done" ? "bg-hermes-green" : "bg-hermes-muted"}`} />
                <span className="text-[10px] font-mono text-hermes-text flex-1">{t.event}</span>
                <span className="text-[9px] text-hermes-muted font-mono">{t.time}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Pipeline Flow">
          <div className="flex flex-col gap-1.5 text-[10px] font-mono">
            {["Security Validation ✓", "Policy Check ✓", "Guard Verified ✓", "Memory Update ✓", "Evolution Feed ✓"].map((msg, i) => (
              <div key={i} className="flex items-center gap-2 text-hermes-green">
                <CheckCircle className="w-3 h-3" />
                {msg}
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Actions */}
      <Card title="Controls">
        <div className="flex gap-3">
          <button className="px-4 py-2 bg-hermes-green/10 text-hermes-green border border-hermes-green/30 rounded-lg hover:bg-hermes-green/20 transition-colors flex items-center gap-2 text-xs font-mono">
            <Play className="w-3 h-3" /> Start
          </button>
          <button className="px-4 py-2 bg-hermes-amber/10 text-hermes-amber border border-hermes-amber/30 rounded-lg hover:bg-hermes-amber/20 transition-colors flex items-center gap-2 text-xs font-mono">
            <Pause className="w-3 h-3" /> Pause
          </button>
          <button className="px-4 py-2 bg-hermes-red/10 text-hermes-red border border-hermes-red/30 rounded-lg hover:bg-hermes-red/20 transition-colors flex items-center gap-2 text-xs font-mono">
            <XCircle className="w-3 h-3" /> Cancel
          </button>
        </div>
      </Card>
    </div>
  );
}
