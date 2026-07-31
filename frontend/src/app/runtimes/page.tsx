"use client";
import { useState } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { DashboardProvider } from "@/store/dashboard-store";
import RuntimeOverview from "@/components/runtimes/RuntimeOverview";
import RuntimeTable from "@/components/runtimes/RuntimeTable";
import RuntimeInspector from "@/components/runtimes/RuntimeInspector";
import RuntimeDecisionExplorer from "@/components/runtimes/RuntimeDecisionExplorer";
import RuntimeHealth from "@/components/runtimes/RuntimeHealth";
import RuntimePerformance from "@/components/runtimes/RuntimePerformance";
import RuntimePolicies from "@/components/runtimes/RuntimePolicies";
import RuntimeEvents from "@/components/runtimes/RuntimeEvents";
import RuntimeControls from "@/components/runtimes/RuntimeControls";
import { Cpu } from "lucide-react";

export default function RuntimesPage() {
  const [selectedName, setSelectedName] = useState<string | null>(null);

  return (
    <DashboardProvider>
      <DashboardLayout>
        <div className="mx-auto max-w-7xl space-y-4">
          <div className="flex items-center justify-between">
            <div><h1 className="text-lg font-bold text-[var(--color-text-primary)]">Runtime Center</h1><p className="mt-1 text-xs text-[var(--color-text-muted)]">Runtime supervision, administration and analysis</p></div>
          </div>

          <RuntimeControls runtimeName={selectedName} />

          <PanelGroup direction="vertical" style={{ minHeight: 850 }}>
            {/* Row 1: Overview */}
            <Panel defaultSize={14} minSize={10}><RuntimeOverview /></Panel>
            <PanelResizeHandle className="h-2 rounded-md transition-colors hover:bg-white/10" />

            {/* Row 2: Table + Inspector + Decision Explorer */}
            <Panel defaultSize={32} minSize={20}>
              <PanelGroup direction="horizontal">
                <Panel defaultSize={40} minSize={25}><RuntimeTable onSelect={setSelectedName} selectedName={selectedName} /></Panel>
                <PanelResizeHandle className="w-2 rounded-md transition-colors hover:bg-white/10" />
                <Panel defaultSize={32} minSize={20}><RuntimeInspector runtimeName={selectedName} /></Panel>
                <PanelResizeHandle className="w-2 rounded-md transition-colors hover:bg-white/10" />
                <Panel defaultSize={28} minSize={18}><RuntimeDecisionExplorer /></Panel>
              </PanelGroup>
            </Panel>

            <PanelResizeHandle className="h-2 rounded-md transition-colors hover:bg-white/10" />

            {/* Row 3: Health + Performance + Policies + Events */}
            <Panel defaultSize={54} minSize={25}>
              <PanelGroup direction="horizontal">
                <Panel defaultSize={25} minSize={18}><RuntimeHealth /></Panel>
                <PanelResizeHandle className="w-2 rounded-md transition-colors hover:bg-white/10" />
                <Panel defaultSize={30} minSize={20}><RuntimePerformance /></Panel>
                <PanelResizeHandle className="w-2 rounded-md transition-colors hover:bg-white/10" />
                <Panel defaultSize={22} minSize={15}><RuntimePolicies /></Panel>
                <PanelResizeHandle className="w-2 rounded-md transition-colors hover:bg-white/10" />
                <Panel defaultSize={23} minSize={15}><RuntimeEvents /></Panel>
              </PanelGroup>
            </Panel>
          </PanelGroup>
        </div>
      </DashboardLayout>
    </DashboardProvider>
  );
}
