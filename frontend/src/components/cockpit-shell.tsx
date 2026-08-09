"use client";

import { AnimatePresence, motion } from "framer-motion";
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
// KnowledgeGraphCenter et AlexandrieCenter ne sont plus des vues de premier
// niveau : leur contenu est devenu un onglet du Memory Center, qui affichait
// déjà les mêmes données. Voir features/memory/memory-center.tsx.
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
import { ExecutionCenter } from "@/features/execution/execution-center";
import { ValidationCenter } from "@/features/validation/validation-center";

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
  // P-001 : capacités backend qui n'avaient aucun écran.
  health: HealthCenter,
  monitoring: MonitoringCenter,
  workspace: WorkspaceCenter,
  execution: ExecutionCenter,
  validation: ValidationCenter,
  // `policy`, `knowledge` et `alexandrie` ont été fusionnés : Policy
  // interrogeait exactement les mêmes endpoints que Governance, et Memory
  // affichait déjà l'intégralité de Knowledge Graph et d'Alexandrie. Les
  // anciens identifiants restent acceptés pour qu'un lien ou un état
  // persistant pointant dessus n'atterrisse pas silencieusement sur le
  // Dashboard.
  policy: GovernanceCenter,
  knowledge: MemoryCenter,
  alexandrie: MemoryCenter,
} satisfies Record<string, React.FC>;

export default function CockpitShell() {
  const { activeView, navCollapsed } = useCockpitStore();
  const View = views[activeView as keyof typeof views] ?? DashboardView;

  return (
    <div className="min-h-screen text-hermes-text">
      <Sidebar />
      <Topbar />
      <motion.main
        animate={{ marginLeft: navCollapsed ? 68 : 232 }}
        transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
        // h-screen + overflow-hidden here, overflow-y-auto on the inner div:
        // without a bounded height, a Center built to scroll internally
        // (its own flex column with an overflow-y-auto pane, e.g. the
        // Assistant transcript) instead grows the whole document, and
        // anything anchored beside that internal pane — a header, a side
        // rail — scrolls away with it instead of staying in view.
        className="h-screen overflow-hidden pt-14 pb-8"
      >
        <div className="h-full max-w-[1500px] overflow-y-auto p-6 2xl:max-w-[1900px]">
          {/* A Center that throws must not take the shell with it. */}
          <CenterBoundary viewKey={activeView}>
            {/* Keyed on the view so switching tabs replays the entrance
                animation instead of swapping content in place. */}
            <AnimatePresence mode="wait">
              <motion.div
                key={activeView}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                className="h-full"
              >
                <View />
              </motion.div>
            </AnimatePresence>
          </CenterBoundary>
        </div>
      </motion.main>
      <StatusBar />
    </div>
  );
}
