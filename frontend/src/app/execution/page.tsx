"use client";

import { Group, Panel, Separator } from "react-resizable-panels";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { DashboardProvider } from "@/store/dashboard-store";
import ExecutionOverview from "@/components/execution/ExecutionOverview";
import LiveGraph from "@/components/execution/LiveGraph";
import TaskTable from "@/components/execution/TaskTable";
import ExecutionTimeline from "@/components/execution/ExecutionTimeline";
import PerformanceCharts from "@/components/execution/PerformanceCharts";
import ExecutionControls from "@/components/execution/ExecutionControls";

export default function ExecutionPage() {
  return (
    <DashboardProvider>
      <DashboardLayout>
        <div className="mx-auto max-w-7xl space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-lg font-bold text-[var(--color-text-primary)]">
                Execution Center
              </h1>
              <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                Real-time mission execution monitoring and control
              </p>
            </div>
          </div>

          <ExecutionControls />

          <Group orientation="vertical" style={{ minHeight: 700 }}>
            {/* Top row: Overview + Graph */}
            <Panel defaultSize={40} minSize={25}>
              <Group orientation="horizontal">
                <Panel defaultSize={33} minSize={20}>
                  <ExecutionOverview />
                </Panel>
                <Separator className="w-2 rounded-md transition-colors hover:bg-white/10" />
                <Panel defaultSize={67} minSize={35}>
                  <LiveGraph />
                </Panel>
              </Group>
            </Panel>

            <Separator className="h-2 rounded-md transition-colors hover:bg-white/10" />

            {/* Bottom row: Tasks + Timeline + Charts */}
            <Panel defaultSize={60} minSize={30}>
              <Group orientation="horizontal">
                <Panel defaultSize={40} minSize={25}>
                  <TaskTable />
                </Panel>
                <Separator className="w-2 rounded-md transition-colors hover:bg-white/10" />
                <Panel defaultSize={30} minSize={20}>
                  <ExecutionTimeline />
                </Panel>
                <Separator className="w-2 rounded-md transition-colors hover:bg-white/10" />
                <Panel defaultSize={30} minSize={20}>
                  <PerformanceCharts />
                </Panel>
              </Group>
            </Panel>
          </Group>
        </div>
      </DashboardLayout>
    </DashboardProvider>
  );
}
