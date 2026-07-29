"use client";

import DashboardLayout from "@/components/layout/DashboardLayout";
import { DashboardProvider } from "@/store/dashboard-store";
import { Activity } from "lucide-react";

export default function EventsPage() {
  return (
    <DashboardProvider>
      <DashboardLayout>
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <Activity size={40} className="text-[var(--color-text-muted)]" />
          <h2 className="mt-4 text-lg font-semibold text-[var(--color-text-primary)]">Events</h2>
          <p className="mt-2 max-w-md text-sm text-[var(--color-text-muted)]">
            Event viewer. Browse and filter system events, metrics, and observability data.
          </p>
          <p className="mt-8 text-xs text-[var(--color-text-muted)]">Coming soon</p>
        </div>
      </DashboardLayout>
    </DashboardProvider>
  );
}
