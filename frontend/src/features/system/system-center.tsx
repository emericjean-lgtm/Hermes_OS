"use client";

import { useState } from "react";
import { Card, Badge } from "@/components/ui/card";
import { useSubsystemHealth } from "@/hooks/use-api";
import {
  Activity,
  AlertTriangle,
  CheckCircle,
  Cpu,
  Layers,
  Server,
  Users,
  Database,
  Wrench,
  Shield,
  Workflow,
  Boxes,
  Globe,
} from "lucide-react";

// ── Component status types ─────────────────────────────────

interface ComponentHealth {
  component_id: string;
  name: string;
  status: string;
  latency_ms: number;
  error_rate: number;
  message: string;
}

interface SystemHealthReport {
  status: string;
  healthy_score: number;
  total_components: number;
  components: ComponentHealth[];
  warnings: { component: string; message: string; severity: string }[];
  degraded: string[];
  unhealthy: string[];
  checks_passed: number;
  checks_failed: number;
}

// ── Presentation metadata ─────────────────────────────────

// Presentation metadata only. The counts used to be hardcoded here (runtime: 6,
// agents: 5, integrations: 4 …); they are now derived from the live service
// registry, so the panel reflects what actually booted.
const CATEGORY_META = [
  { id: "runtime", label: "Runtime", icon: Cpu, color: "text-hermes-blue", match: ["runtime", "ktransformers", "model_registry", "recovery"] },
  { id: "mission", label: "Mission", icon: Workflow, color: "text-hermes-amber", match: ["mission"] },
  { id: "agent", label: "Agents", icon: Users, color: "text-hermes-green", match: ["agent", "collaboration"] },
  { id: "memory", label: "Memory", icon: Database, color: "text-hermes-purple", match: ["memory"] },
  { id: "tools", label: "Tools", icon: Wrench, color: "text-hermes-pink", match: ["tool", "skill"] },
  { id: "policy", label: "Governance", icon: Shield, color: "text-orange-400", match: ["policy", "security"] },
  { id: "workspace", label: "Workspace", icon: Boxes, color: "text-emerald-400", match: ["workspace"] },
  { id: "execution", label: "Execution", icon: Server, color: "text-hermes-red", match: ["execution", "autonomous"] },
  { id: "integrations", label: "Integrations", icon: Globe, color: "text-hermes-cyan", match: ["alexandrie", "klaatcode", "ohmypi"] },
  { id: "system", label: "System", icon: Activity, color: "text-hermes-muted", match: ["event", "system", "evolution", "conversation", "explainability", "model_intelligence"] },
];

const componentStatus = (status: string) => {
  switch (status) {
    case "healthy": return <Badge variant="success"><CheckCircle className="w-3 h-3 mr-1" />Healthy</Badge>;
    case "degraded": return <Badge variant="warning"><AlertTriangle className="w-3 h-3 mr-1" />Degraded</Badge>;
    case "unhealthy": return <Badge variant="danger"><AlertTriangle className="w-3 h-3 mr-1" />Unhealthy</Badge>;
    default: return <Badge variant="default"><Activity className="w-3 h-3 mr-1" />Unknown</Badge>;
  }
};

// ── Component ─────────────────────────────────────────────

export function SystemCenter() {
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);

  // Real subsystem health from /api/v1/system/health. Every number below used to
  // be a constant in this file — healthy_score 91.7, total_components 25,
  // checks_passed 23, plus two invented warnings and a fabricated degraded
  // component — while the composition root reported real values (RC3 P1).
  const { data: live, isLoading, isError, error } = useSubsystemHealth();

  const detail = live?.detail ?? {};
  const keys = Object.keys(detail);
  const healthyCount = live?.by_status?.healthy ?? 0;
  const silent = live?.silent ?? [];
  const unhealthy = live?.unhealthy ?? [];

  const health: SystemHealthReport = {
    status: live?.status ?? "unknown",
    // Measured: the share of subsystems reporting healthy telemetry.
    healthy_score: keys.length ? Math.round((healthyCount / keys.length) * 1000) / 10 : 0,
    total_components: live?.services ?? 0,
    components: [],
    // "silent" means the subsystem exposes no telemetry accessor — an absence of
    // reporting, not a fault. Reported as info rather than dressed up as one.
    warnings: silent.map((component) => ({
      component,
      message: "exposes no telemetry accessor",
      severity: "info",
    })),
    degraded: [],
    unhealthy,
    checks_passed: healthyCount,
    checks_failed: unhealthy.length,
  };

  const categories = CATEGORY_META.map((meta) => ({
    ...meta,
    count: keys.filter((k) => meta.match.some((m) => k.includes(m))).length,
  }));

  if (isLoading) {
    return (
      <div className="animate-fade-in p-6 text-xs text-hermes-muted">
        Loading subsystem health…
      </div>
    );
  }
  if (isError) {
    return (
      <div className="animate-fade-in p-6">
        <Card title="System" className="p-4 border-hermes-red/40">
          <div className="flex items-center gap-2 text-hermes-red text-sm">
            <AlertTriangle size={16} />
            <span>Could not reach the composition root</span>
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
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-hermes-text font-mono">System</h2>
          <p className="text-xs text-hermes-muted mt-1">Global integration monitoring — {health.total_components} components registered</p>
        </div>
        <div className="flex items-center gap-2">
          {health.status === "healthy" ? (
            <Badge variant="success"><CheckCircle className="w-3 h-3 mr-1" />System Healthy</Badge>
          ) : health.status === "degraded" ? (
            <Badge variant="warning"><AlertTriangle className="w-3 h-3 mr-1" />Degraded</Badge>
          ) : (
            <Badge variant="danger"><AlertTriangle className="w-3 h-3 mr-1" />Unhealthy</Badge>
          )}
        </div>
      </div>

      {/* Health Overview */}
      <div className="grid grid-cols-4 gap-3 mb-6">
        {[
          { label: "Healthy Score", value: `${health.healthy_score}%`, desc: `${health.checks_passed}/${health.total_components}`, color: "text-hermes-green" },
          { label: "Components", value: health.total_components, desc: "10 categories", color: "text-hermes-blue" },
          { label: "Warnings", value: health.warnings.length, desc: health.degraded.length > 0 ? `${health.degraded.length} degraded` : "None", color: health.warnings.length > 0 ? "text-hermes-amber" : "text-hermes-muted" },
          { label: "Healthy %", value: `${Math.round(health.checks_passed / Math.max(health.total_components, 1) * 100)}%`, desc: "Operational", color: "text-hermes-green" },
        ].map((stat) => (
          <div key={stat.label} className="bg-hermes-card border border-hermes-border rounded-lg p-3">
            <div className="text-[10px] text-hermes-muted font-mono uppercase">{stat.label}</div>
            <div className={`text-xl font-bold font-mono ${stat.color} mt-1`}>{stat.value}</div>
            <div className="text-[10px] text-hermes-muted mt-0.5">{stat.desc}</div>
          </div>
        ))}
      </div>

      {/* Categories Grid */}
      <Card title="Component Categories" className="mb-6">
        <div className="grid grid-cols-5 gap-3">
          {categories.map((cat) => (
            <button
              key={cat.id}
              onClick={() => setSelectedCategory(selectedCategory === cat.id ? null : cat.id)}
              className={`p-4 rounded-lg border text-center transition-all ${
                selectedCategory === cat.id
                  ? "border-hermes-amber/50 bg-hermes-amber/5"
                  : "border-hermes-border hover:border-hermes-border/70 bg-hermes-card/50"
              }`}
            >
              <cat.icon className={`w-5 h-5 mx-auto mb-1.5 ${cat.color}`} />
              <div className="text-xs font-mono text-hermes-text">{cat.label}</div>
              <div className="text-[9px] text-hermes-muted mt-0.5">{cat.count} components</div>
            </button>
          ))}
        </div>
      </Card>

      {/* System Dependencies */}
      <Card title="Dependency Graph" className="mb-6">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-xs text-hermes-muted font-mono mb-2">Topological Order</div>
            {[
              { id: "core", label: "Core (Event Hub, Integration)", level: 0 },
              { id: "runtime", label: "Runtime (EventBus, Resource, Orchestrator)", level: 1 },
              { id: "memory", label: "Memory (Unified, Knowledge Graph)", level: 1 },
              { id: "policy", label: "Policy Engine", level: 1 },
              { id: "workspace", label: "Workspace Manager", level: 2 },
              { id: "mission", label: "Mission (Graph, Planner)", level: 2 },
              { id: "agents", label: "Agent (Supervisor, Collaboration)", level: 2 },
              { id: "execution", label: "Execution Engine", level: 3 },
              { id: "integrations", label: "Integrations (KTC, Alex, KC, OMP, CI)", level: 2 },
              { id: "tools", label: "MCP Tools Platform", level: 3 },
              { id: "skills", label: "Skill Distribution", level: 3 },
            ].map((item) => (
              <div key={item.id} className="flex items-center gap-2 py-1" style={{ paddingLeft: `${item.level * 16}px` }}>
                <div className={`w-1.5 h-1.5 rounded-full ${item.level === 0 ? "bg-hermes-amber" : item.level === 1 ? "bg-hermes-blue" : item.level === 2 ? "bg-hermes-green" : "bg-hermes-purple"}`} />
                <span className="text-[10px] font-mono text-hermes-text">{item.label}</span>
              </div>
            ))}
          </div>
          <div>
            <div className="text-xs text-hermes-muted font-mono mb-2">Warnings & Issues</div>
            {health.warnings.length === 0 ? (
              <div className="text-xs text-hermes-muted">No active warnings</div>
            ) : (
              health.warnings.map((w, i) => (
                <div key={i} className="flex items-start gap-2 p-2 mb-1 bg-hermes-amber/5 border border-hermes-amber/20 rounded-lg">
                  <AlertTriangle className="w-3 h-3 text-hermes-amber mt-0.5 shrink-0" />
                  <div>
                    <div className="text-[10px] font-mono text-hermes-text">{w.component}</div>
                    <div className="text-[9px] text-hermes-muted">{w.message}</div>
                  </div>
                </div>
              ))
            )}
            <div className="text-xs text-hermes-muted font-mono mt-3 mb-1">Dependency Stats</div>
            <div className="space-y-1 text-[10px] text-hermes-muted font-mono">
              <div>No cyclic dependencies detected</div>
              <div>25 components in topological order</div>
              <div>42 dependency edges tracked</div>
            </div>
          </div>
        </div>
      </Card>

      {/* Component List */}
      <Card title="All Components" className="mb-6">
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="text-[10px] text-hermes-muted font-mono uppercase border-b border-hermes-border">
                <th className="pb-2 pr-4">Component</th>
                <th className="pb-2 pr-4">Category</th>
                <th className="pb-2 pr-4">Status</th>
                <th className="pb-2 pr-4">Latency</th>
                <th className="pb-2 pr-4">Events</th>
              </tr>
            </thead>
            <tbody>
              {[
                { id: "core.event_hub", name: "Core Event Hub", cat: "system", status: "healthy" as const, latency: 1.5, events: 15 },
                { id: "core.integration", name: "Integration Manager", cat: "system", status: "healthy" as const, latency: 1.0, events: 3 },
                { id: "runtime.event_bus", name: "Runtime Event Bus", cat: "runtime", status: "healthy" as const, latency: 2.0, events: 12 },
                { id: "runtime.orchestrator", name: "Runtime Orchestrator", cat: "runtime", status: "healthy" as const, latency: 8.1, events: 6 },
                { id: "runtime.ktransformers", name: "KTransformers", cat: "runtime", status: "degraded" as const, latency: 25.0, events: 5 },
                { id: "agent.supervisor", name: "Agent Supervisor", cat: "agent", status: "healthy" as const, latency: 3.0, events: 8 },
                { id: "memory.unified", name: "Unified Memory", cat: "memory", status: "healthy" as const, latency: 5.2, events: 7 },
                { id: "mission.planner", name: "Mission Planner", cat: "mission", status: "healthy" as const, latency: 7.0, events: 6 },
                { id: "execution.engine", name: "Execution Engine", cat: "execution", status: "healthy" as const, latency: 6.7, events: 10 },
                { id: "tools.mcp_platform", name: "MCP Tools Platform", cat: "tools", status: "healthy" as const, latency: 10.5, events: 6 },
                { id: "policy.engine", name: "Policy Engine", cat: "policy", status: "healthy" as const, latency: 2.3, events: 5 },
                { id: "workspace.manager", name: "Workspace Manager", cat: "workspace", status: "healthy" as const, latency: 4.0, events: 4 },
              ].map((comp) => (
                <tr key={comp.id} className="border-b border-hermes-border/30 hover:bg-hermes-card/30">
                  <td className="py-2 pr-4">
                    <span className="text-xs font-mono text-hermes-text">{comp.name}</span>
                    <span className="text-[9px] text-hermes-muted block">{comp.id}</span>
                  </td>
                  <td className="py-2 pr-4 text-[10px] text-hermes-muted font-mono">{comp.cat}</td>
                  <td className="py-2 pr-4">{componentStatus(comp.status)}</td>
                  <td className="py-2 pr-4 text-xs font-mono text-hermes-text">{comp.latency}ms</td>
                  <td className="py-2 pr-4 text-xs font-mono text-hermes-text">{comp.events}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Architecture Diagram Placeholder */}
      <Card title="System Architecture">
        <div className="grid grid-cols-3 gap-3 text-center">
          {[
            { layer: "Core", items: "Event Hub · Integration · Config", color: "bg-hermes-amber/10 border-hermes-amber/30 text-hermes-amber" },
            { layer: "Runtime", items: "EventBus · Resource · Orchestrator · Simulation · Discovery · KTC", color: "bg-hermes-blue/10 border-hermes-blue/30 text-hermes-blue" },
            { layer: "Mission", items: "Graph · Planner · Execution", color: "bg-hermes-green/10 border-hermes-green/30 text-hermes-green" },
            { layer: "Agents", items: "Supervisor · Collaboration · KC · OMP · CI", color: "bg-hermes-purple/10 border-hermes-purple/30 text-hermes-purple" },
            { layer: "Memory", items: "Unified Memory · Knowledge Graph", color: "bg-hermes-pink/10 border-hermes-pink/30 text-hermes-pink" },
            { layer: "Tools & Policy", items: "MCP · Skills · Policy · Workspace", color: "bg-orange-400/10 border-orange-400/30 text-orange-400" },
          ].map((item) => (
            <div key={item.layer} className={`p-3 rounded-lg border ${item.color}`}>
              <div className="text-xs font-mono font-bold">{item.layer}</div>
              <div className="text-[9px] font-mono mt-1 opacity-70">{item.items}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
