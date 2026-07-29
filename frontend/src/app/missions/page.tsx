"use client";

import { useState } from "react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { DashboardProvider } from "@/store/dashboard-store";
import MissionListTable from "@/components/missions/MissionListTable";
import MissionForm from "@/components/missions/MissionForm";
import MissionDetails from "@/components/missions/MissionDetails";
import MissionActions from "@/components/missions/MissionActions";
import VisualPlanner from "@/components/missions/VisualPlanner";
import { useMission } from "@/hooks/use-missions";
import { Target, Plus, PanelRightOpen } from "lucide-react";

export default function MissionsPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [showDetails, setShowDetails] = useState(true);
  const { data: selectedMission } = useMission(selectedId);

  return (
    <DashboardProvider>
      <DashboardLayout>
        <div className="mx-auto max-w-7xl space-y-4">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-lg font-bold text-[var(--color-text-primary)]">Mission Center</h1>
              <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                Create, plan, visualize, and manage AI missions
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowDetails(!showDetails)}
                className="flex items-center gap-1.5 rounded-md bg-white/5 px-3 py-1.5 text-xs text-[var(--color-text-muted)] transition-colors hover:bg-white/10"
              >
                <PanelRightOpen size={14} />
                {showDetails ? "Hide" : "Show"} Details
              </button>
              <button
                onClick={() => setShowForm(!showForm)}
                className="flex items-center gap-1.5 rounded-md bg-[var(--color-accent)] px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90"
              >
                <Plus size={14} />
                New Mission
              </button>
            </div>
          </div>

          {/* Content grid */}
          <div className="grid gap-4 lg:grid-cols-3">
            {/* Left: Mission list */}
            <div className={showDetails ? "lg:col-span-2" : "lg:col-span-3"}>
              <MissionListTable onSelect={setSelectedId} selectedId={selectedId} />

              {/* Actions bar */}
              <div className="mt-4">
                <MissionActions mission={selectedMission ?? null} />
              </div>

              {/* Visual Planner */}
              <div className="mt-4">
                <VisualPlanner missionId={selectedId} />
              </div>
            </div>

            {/* Right side */}
            <div className="space-y-4">
              {/* Details panel */}
              {showDetails && (
                <MissionDetails missionId={selectedId} />
              )}

              {/* Create form */}
              {showForm && (
                <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
                  <div className="mb-4 flex items-center gap-2">
                    <Target size={16} className="text-[var(--color-accent)]" />
                    <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
                      Create Mission
                    </h3>
                  </div>
                  <MissionForm onSuccess={() => setShowForm(false)} />
                </div>
              )}

              {/* Empty state */}
              {!showForm && !showDetails && (
                <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-white/10 bg-[var(--color-bg-surface)] p-8 text-center">
                  <Target size={32} className="text-[var(--color-text-muted)]" />
                  <p className="mt-3 text-sm text-[var(--color-text-muted)]">
                    Click &quot;New Mission&quot; to create your first mission
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </DashboardLayout>
    </DashboardProvider>
  );
}
