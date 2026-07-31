"use client";

import { useMissions, useMissionGraph, useCreateMission } from "@/hooks/use-api";
import { useCockpitStore } from "@/hooks/use-store";
import { Card, Badge, ProgressBar, Button } from "@/components/ui/card";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { Mission, MissionStatus } from "@/types/hermes";
import { CenterHeader } from "@/components/center-scaffold";

const statusBadge: Record<MissionStatus, keyof typeof statusColors> = {
  CREATED: "default",
  PLANNING: "info",
  READY: "info",
  RUNNING: "purple",
  PAUSED: "warning",
  WAITING_APPROVAL: "warning",
  VALIDATING: "info",
  COMPLETED: "success",
  FAILED: "danger",
  CANCELLED: "default",
};

const statusColors = {
  default: "default",
  info: "info",
  purple: "purple",
  warning: "warning",
  success: "success",
  danger: "danger",
} as const;

export function MissionCenter() {
  const { data: missions, isLoading } = useMissions();
  const createMission = useCreateMission();
  const { selectedMissionId, selectMission } = useCockpitStore();
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");

  const selected = missions?.find((m) => m.id === selectedMissionId);

  const handleCreate = () => {
    if (title.trim()) {
      createMission.mutate({ title: title.trim(), description: description.trim() });
      setTitle("");
      setDescription("");
      setShowCreate(false);
    }
  };

  return (
    <div className="animate-fade-in">
      <CenterHeader
        title="Mission Center"
        subtitle="Orchestration autonome de missions en DAG"
        right={
          <Button variant="primary" onClick={() => setShowCreate(!showCreate)}>
            + Nouvelle mission
          </Button>
        }
      />

      {/* Create form */}
      <AnimatePresence>
        {showCreate && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="mb-6 overflow-hidden"
          >
            <Card title="Create Mission" className="border-hermes-amber/30">
              <div className="flex flex-col gap-3">
                <input
                  type="text"
                  placeholder="Mission title..."
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="bg-hermes-bg border border-hermes-border rounded-lg px-3 py-2 text-sm text-hermes-text font-mono focus:border-hermes-amber outline-none"
                />
                <textarea
                  placeholder="Description (optional)..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={2}
                  className="bg-hermes-bg border border-hermes-border rounded-lg px-3 py-2 text-sm text-hermes-text font-mono focus:border-hermes-amber outline-none resize-none"
                />
                <div className="flex gap-2 justify-end">
                  <button
                    onClick={() => setShowCreate(false)}
                    className="px-3 py-1.5 text-xs text-hermes-muted hover:text-hermes-text transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleCreate}
                    disabled={!title.trim() || createMission.isPending}
                    className="px-4 py-1.5 text-xs font-mono bg-hermes-amber text-black rounded-lg hover:bg-hermes-amber-bright transition-colors disabled:opacity-50"
                  >
                    {createMission.isPending ? "Creating..." : "Create"}
                  </button>
                </div>
              </div>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="grid grid-cols-2 gap-4">
        {/* Mission list */}
        <Card title="Missions" subtitle={isLoading ? "Loading..." : `${missions?.length || 0} missions`}>
          <div className="flex flex-col gap-2 max-h-[500px] overflow-y-auto">
            {missions?.map((mission) => (
              <button
                key={mission.id}
                onClick={() => selectMission(mission.id)}
                className={`text-left p-3 rounded-lg border transition-all ${
                  selectedMissionId === mission.id
                    ? "border-hermes-amber/50 bg-hermes-amber/5"
                    : "border-hermes-border/50 hover:border-hermes-border"
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-hermes-text truncate max-w-[200px]">
                    {mission.title}
                  </span>
                  <Badge variant={statusBadge[mission.status]}>{mission.status}</Badge>
                </div>
                <ProgressBar value={mission.progress} size="sm" className="mb-1" />
                <div className="flex items-center gap-3 text-[10px] text-hermes-muted font-mono">
                  <span>{mission.priority}</span>
                  <span>{mission.completed_nodes}/{mission.node_count} nodes</span>
                </div>
              </button>
            ))}
            {missions?.length === 0 && (
              <p className="text-xs text-hermes-muted py-8 text-center">No missions yet</p>
            )}
          </div>
        </Card>

        {/* Mission detail */}
        <Card
          title={selected ? selected.title : "Detail"}
          subtitle={selected ? `Nodes: ${selected.completed_nodes || 0}/${selected.node_count || "?"}` : "Select a mission"}
        >
          {selected ? (
            <div className="flex flex-col gap-3">
              <div className="grid grid-cols-2 gap-2">
                <div className="text-[10px] text-hermes-muted font-mono">Type</div>
                <div className="text-[10px] text-hermes-text font-mono">{selected.type}</div>
                <div className="text-[10px] text-hermes-muted font-mono">Priority</div>
                <Badge variant={selected.priority === "CRITICAL" ? "danger" : "default"}>
                  {selected.priority}
                </Badge>
                <div className="text-[10px] text-hermes-muted font-mono">Created</div>
                <div className="text-[10px] text-hermes-text font-mono">
                  {new Date(selected.created_at).toLocaleDateString()}
                </div>
              </div>
              <ProgressBar value={selected.progress} />
              <p className="text-xs text-hermes-muted">{selected.description || "No description"}</p>
            </div>
          ) : (
            <div className="flex items-center justify-center h-32 text-xs text-hermes-muted font-mono">
              ← Select a mission to view details
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
