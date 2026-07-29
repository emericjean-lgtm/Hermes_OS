"use client";

import DashboardLayout from "@/components/layout/DashboardLayout";
import { DashboardProvider } from "@/store/dashboard-store";
import { Bot } from "lucide-react";

export default function AgentsPage() {
  return (
    <DashboardProvider>
      <DashboardLayout>
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <Bot size={40} className="text-[var(--color-text-muted)]" />
          <h2 className="mt-4 text-lg font-semibold text-[var(--color-text-primary)]">Agents</h2>
          <p className="mt-2 max-w-md text-sm text-[var(--color-text-muted)]">
            Agent management and monitoring. Create, configure, and monitor AI agents.
          </p>
          <p className="mt-8 text-xs text-[var(--color-text-muted)]">Coming soon</p>
        </div>
      </DashboardLayout>
    </DashboardProvider>
  );
}
