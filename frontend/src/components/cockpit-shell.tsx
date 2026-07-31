"use client";

import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";
import { StatusBar } from "@/components/statusbar";
import { useCockpitStore } from "@/hooks/use-store";
import { CenterBoundary } from "@/components/center-boundary";
import { DashboardView } from "@/features/dashboard/dashboard-view";
import { MissionCenter } from "@/features/missions/mission-center";
import { AgentCenter } from "@/features/agents/agent-center";
import { RuntimeCenter } from "@/features/runtime/runtime-center";
import { MemoryCenter } from "@/features/memory/memory-center";
import { SkillsCenter } from "@/features/skills/skills-center";
import { ToolsCenter } from "@/features/tools/tools-center";
import { GovernanceCenter } from "@/features/governance/governance-center";
import { EventsCenter } from "@/features/events/events-center";
import { AutonomousCenter } from "@/features/autonomous/autonomous-center";
import { CodeIntelligenceCenter } from "@/features/code-intelligence/code-intelligence-center";
import { EvolutionCenter } from "@/features/evolution/evolution-center";
import { SecurityCenter } from "@/features/security/security-center";
import { SystemCenter } from "@/features/system/system-center";
import ConversationCenter from "@/features/conversation/conversation-center";
import DeploymentCenter from "@/features/deployment/deployment-center";
import ModelIntelligenceCenter from "@/features/models/model-intelligence-center";
import { HealthCenter } from "@/features/health/health-center";
import { MonitoringCenter } from "@/features/monitoring/monitoring-center";
import { WorkspaceCenter } from "@/features/workspace/workspace-center";
import { KnowledgeGraphCenter } from "@/features/knowledge/knowledge-graph-center";
import { ExecutionCenter } from "@/features/execution/execution-center";
import { PolicyCenter } from "@/features/policy/policy-center";
import { ValidationCenter } from "@/features/validation/validation-center";
import { AlexandrieCenter } from "@/features/alexandrie/alexandrie-center";

/** Every id offered by the sidebar must resolve to a Center here.
 *
 *  Eight of these were implemented, exported and never imported: the sidebar
 *  advertised Assistant, Models, Code Intel, Autonomous, Security, System and
 *  Deploy, and clicking any of them silently fell through to the dashboard
 *  because `views` had no entry. The `satisfies` below is what stops that
 *  recurring — a new sidebar id that has no Center is now a type error rather
 *  than a dead menu entry. */
const views = {
  dashboard: DashboardView,
  conversation: ConversationCenter,
  models: ModelIntelligenceCenter,
  missions: MissionCenter,
  agents: AgentCenter,
  runtime: RuntimeCenter,
  code_intelligence: CodeIntelligenceCenter,
  memory: MemoryCenter,
  skills: SkillsCenter,
  tools: ToolsCenter,
  governance: GovernanceCenter,
  events: EventsCenter,
  evolution: EvolutionCenter,
  autonomous: AutonomousCenter,
  security: SecurityCenter,
  system: SystemCenter,
  deployment: DeploymentCenter,
  // P-001 : huit capacités backend qui n'avaient aucun écran.
  health: HealthCenter,
  monitoring: MonitoringCenter,
  workspace: WorkspaceCenter,
  knowledge: KnowledgeGraphCenter,
  execution: ExecutionCenter,
  policy: PolicyCenter,
  validation: ValidationCenter,
  alexandrie: AlexandrieCenter,
} satisfies Record<string, React.FC>;

export default function CockpitShell() {
  const { activeView } = useCockpitStore();
  const View = views[activeView as keyof typeof views] ?? DashboardView;

  return (
    <div className="min-h-screen bg-hermes-bg text-hermes-text">
      <Sidebar />
      <Topbar />
      <main className="ml-56 pt-12 pb-7">
        <div className="p-6 max-w-[1400px]">
          {/* A Center that throws must not take the shell with it. */}
          <CenterBoundary viewKey={activeView}>
            <View />
          </CenterBoundary>
        </div>
      </main>
      <StatusBar />
    </div>
  );
}
