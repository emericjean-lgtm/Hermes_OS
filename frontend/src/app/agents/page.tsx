"use client";

import { useState } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { DashboardProvider } from "@/store/dashboard-store";
import AgentOverview from "@/components/agents/AgentOverview";
import AgentTable from "@/components/agents/AgentTable";
import AgentInspector from "@/components/agents/AgentInspector";
import AgentGraph from "@/components/agents/AgentGraph";
import AgentTimeline from "@/components/agents/AgentTimeline";
import AgentPerformance from "@/components/agents/AgentPerformance";
import AgentHermesCard from "@/components/agents/AgentHermesCard";
import AgentControls from "@/components/agents/AgentControls";
import { useAgents } from "@/hooks/use-agents";
import { Bot } from "lucide-react";

export default function AgentsPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data: agents } = useAgents();
  const selected = agents?.find((a) => a.id === selectedId);

  return (
    <DashboardProvider>
      <DashboardLayout>
        <div className="mx-auto max-w-7xl space-y-4">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-lg font-bold text-[var(--color-text-primary)]">Agent Center</h1>
              <p className="mt-1 text-xs text-[var(--color-text-muted)]">Real-time agent supervision and inspection</p>
            </div>
          </div>

          {/* Controls */}
          <AgentControls agent={selected ?? null} />

          {/* Resizable panels */}
          <PanelGroup direction="vertical" style={{ minHeight: 800 }}>
            {/* Row 1: Overview */}
            <Panel defaultSize={15} minSize={10}>
              <AgentOverview />
            </Panel>

            <PanelResizeHandle className="h-2 rounded-md transition-colors hover:bg-white/10" />

            {/* Row 2: Table + Inspector + Hermes */}
            <Panel defaultSize={35} minSize={20}>
              <PanelGroup direction="horizontal">
                <Panel defaultSize={45} minSize={25}>
                  <AgentTable onSelect={setSelectedId} selectedId={selectedId} />
                </Panel>
                <PanelResizeHandle className="w-2 rounded-md transition-colors hover:bg-white/10" />
                <Panel defaultSize={35} minSize={20}>
                  <AgentInspector agentId={selectedId} />
                </Panel>
                <PanelResizeHandle className="w-2 rounded-md transition-colors hover:bg-white/10" />
                <Panel defaultSize={20} minSize={15}>
                  <AgentHermesCard />
                </Panel>
              </PanelGroup>
            </Panel>

            <PanelResizeHandle className="h-2 rounded-md transition-colors hover:bg-white/10" />

            {/* Row 3: Graph + Timeline + Performance */}
            <Panel defaultSize={50} minSize={25}>
              <PanelGroup direction="horizontal">
                <Panel defaultSize={40} minSize={25}>
                  <AgentGraph />
                </Panel>
                <PanelResizeHandle className="w-2 rounded-md transition-colors hover:bg-white/10" />
                <Panel defaultSize={28} minSize={18}>
                  <AgentTimeline />
                </Panel>
                <PanelResizeHandle className="w-2 rounded-md transition-colors hover:bg-white/10" />
                <Panel defaultSize={32} minSize={18}>
                  <AgentPerformance />
                </Panel>
              </PanelGroup>
            </Panel>
          </PanelGroup>
        </div>
      </DashboardLayout>
    </DashboardProvider>
  );
}
