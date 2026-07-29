"use client";

import DashboardLayout from "@/components/layout/DashboardLayout";
import HealthCard from "@/components/dashboard/HealthCard";
import StatisticsCard from "@/components/dashboard/StatisticsCard";
import RuntimeTable from "@/components/dashboard/RuntimeTable";
import MissionList from "@/components/dashboard/MissionList";
import EventTimeline from "@/components/dashboard/EventTimeline";
import FreebuffCard from "@/components/dashboard/FreebuffCard";
import HermesCard from "@/components/dashboard/HermesCard";
import { DashboardProvider } from "@/store/dashboard-store";

export default function DashboardPage() {
  return (
    <DashboardProvider>
      <DashboardLayout>
        <div className="mx-auto max-w-7xl space-y-6">
          {/* Page title */}
          <div>
            <h1 className="text-lg font-bold text-[var(--color-text-primary)]">
              Mission Control
            </h1>
            <p className="mt-1 text-xs text-[var(--color-text-muted)]">
              System dashboard — real-time overview of Hermes OS
            </p>
          </div>

          {/* Top row: Health + Statistics */}
          <div className="grid gap-4 md:grid-cols-2">
            <HealthCard />
            <StatisticsCard />
          </div>

          {/* Middle row: Runtime table */}
          <RuntimeTable />

          {/* Bottom row: Missions + Events */}
          <div className="grid gap-4 lg:grid-cols-2">
            <MissionList />
            <EventTimeline />
          </div>

          {/* Integrations row */}
          <div className="grid gap-4 sm:grid-cols-2">
            <FreebuffCard />
            <HermesCard />
          </div>
        </div>
      </DashboardLayout>
    </DashboardProvider>
  );
}
