"use client";

import DashboardLayout from "@/components/layout/DashboardLayout";
import { DashboardProvider } from "@/store/dashboard-store";
import { Brain } from "lucide-react";

export default function MemoryPage() {
  return (
    <DashboardProvider>
      <DashboardLayout>
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <Brain size={40} className="text-[var(--color-text-muted)]" />
          <h2 className="mt-4 text-lg font-semibold text-[var(--color-text-primary)]">Memory</h2>
          <p className="mt-2 max-w-md text-sm text-[var(--color-text-muted)]">
            Memory explorer. Browse, search, and manage Hermes OS memory across all scopes.
          </p>
          <p className="mt-8 text-xs text-[var(--color-text-muted)]">Coming soon</p>
        </div>
      </DashboardLayout>
    </DashboardProvider>
  );
}
