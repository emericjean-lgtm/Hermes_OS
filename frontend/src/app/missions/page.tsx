"use client";

import DashboardLayout from "@/components/layout/DashboardLayout";
import { DashboardProvider } from "@/store/dashboard-store";
import { Target } from "lucide-react";

export default function MissionsPage() {
  return (
    <DashboardProvider>
      <DashboardLayout>
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <Target size={40} className="text-[var(--color-text-muted)]" />
          <h2 className="mt-4 text-lg font-semibold text-[var(--color-text-primary)]">Missions</h2>
          <p className="mt-2 max-w-md text-sm text-[var(--color-text-muted)]">
            Mission management and planning. Create, monitor, and manage your AI missions.
          </p>
          <p className="mt-8 text-xs text-[var(--color-text-muted)]">
            Coming soon — HOS-030
          </p>
        </div>
      </DashboardLayout>
    </DashboardProvider>
  );
}
