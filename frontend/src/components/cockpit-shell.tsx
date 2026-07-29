"use client";

import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";
import { StatusBar } from "@/components/statusbar";
import { useCockpitStore } from "@/hooks/use-store";
import { DashboardView } from "@/features/dashboard/dashboard-view";
import { MissionCenter } from "@/features/missions/mission-center";
import { AgentCenter } from "@/features/agents/agent-center";
import { RuntimeCenter } from "@/features/runtime/runtime-center";
import { MemoryCenter } from "@/features/memory/memory-center";
import { SkillsCenter } from "@/features/skills/skills-center";
import { ToolsCenter } from "@/features/tools/tools-center";
import { GovernanceCenter } from "@/features/governance/governance-center";
import { EventsCenter } from "@/features/events/events-center";

const views: Record<string, React.FC> = {
  dashboard: DashboardView,
  missions: MissionCenter,
  agents: AgentCenter,
  runtime: RuntimeCenter,
  memory: MemoryCenter,
  skills: SkillsCenter,
  tools: ToolsCenter,
  governance: GovernanceCenter,
  events: EventsCenter,
};

export default function CockpitShell() {
  const { activeView } = useCockpitStore();
  const View = views[activeView] || DashboardView;

  return (
    <div className="min-h-screen bg-hermes-bg text-hermes-text">
      <Sidebar />
      <Topbar />
      <main className="ml-56 pt-12 pb-7">
        <div className="p-6 max-w-[1400px]">
          <View />
        </div>
      </main>
      <StatusBar />
    </div>
  );
}
