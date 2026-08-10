"use client";

import {
  useMissions,
  useMission,
  useCreateMission,
  useMissionAction,
  useMissionReport,
  useProjects,
} from "@/hooks/use-api";
import { useCockpitStore } from "@/hooks/use-store";
import { Card, Badge, ProgressBar, Button } from "@/components/ui/card";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { Mission, MissionStatus } from "@/types/hermes";
import { CenterHeader } from "@/components/center-scaffold";
import { Play, Pause, XCircle, AlertCircle } from "lucide-react";

const statusBadge: Record<MissionStatus, keyof typeof statusColors> = {
  CREATED: "default",
  PLANNING: "info",
  READY: "info",
  RUNNING: "purple",
  PAUSED: "warning",
  WAITING_APPROVAL: "warning",
  VALIDATED: "info",
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
  const [localPath, setLocalPath] = useState("");
  const [repository, setRepository] = useState("");
  const [branch, setBranch] = useState("");
  const [projectId, setProjectId] = useState("");
  const { data: projects } = useProjects();
  // Only a validated, active Project actually grants RealTaskExecutor's
  // tool-calling loop real filesystem access (execution/task_executor.py's
  // _workspace_project_for) — listing anything else here would let a user
  // pick a binding that silently does nothing.
  const usableProjects = (projects ?? []).filter(
    (p) => p.status === "active" && p.validation_status === "valid",
  );

  // The list endpoint never sends description/created_at (see toMission in
  // services/client.ts) — the detail panel needs a real per-mission fetch,
  // not a lookup into the list's own (intentionally thinner) rows.
  const { data: selected } = useMission(selectedMissionId);
  const action = useMissionAction(selectedMissionId ?? "");
  const report = useMissionReport(selectedMissionId ?? undefined);

  const handleCreate = () => {
    if (title.trim()) {
      createMission.mutate({
        title: title.trim(),
        description: description.trim(),
        local_path: localPath.trim() || undefined,
        repository: repository.trim() || undefined,
        branch: branch.trim() || undefined,
        project_id: projectId || undefined,
      });
      setTitle("");
      setDescription("");
      setLocalPath("");
      setRepository("");
      setBranch("");
      setProjectId("");
      setShowCreate(false);
    }
  };

  const rep = report.data;
  const busy = action.start.isPending || action.pause.isPending || action.resume.isPending || action.cancel.isPending;

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
            <Card title="Nouvelle mission" className="border-hermes-amber/30">
              <div className="flex flex-col gap-3">
                <input
                  type="text"
                  placeholder="Titre de la mission…"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="bg-hermes-bg border border-hermes-border rounded-lg px-3 py-2 text-sm text-hermes-text font-mono focus:border-hermes-amber outline-none"
                />
                <textarea
                  placeholder="Description (optionnel)…"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={2}
                  className="bg-hermes-bg border border-hermes-border rounded-lg px-3 py-2 text-sm text-hermes-text font-mono focus:border-hermes-amber outline-none resize-none"
                />
                {/* Project binding (HOS-068) — optional. A mission bound to
                    either requires Aegis validation before it starts (see the
                    "paused" status in the detail panel) instead of the
                    unconditional pass-through a plain, unbound mission gets. */}
                <div className="grid grid-cols-3 gap-2">
                  <input
                    type="text"
                    placeholder="Dossier local (optionnel)"
                    value={localPath}
                    onChange={(e) => setLocalPath(e.target.value)}
                    className="bg-hermes-bg border border-hermes-border rounded-lg px-3 py-2 text-[11px] text-hermes-text font-mono focus:border-hermes-amber outline-none"
                  />
                  <input
                    type="text"
                    placeholder="Dépôt GitHub (optionnel)"
                    value={repository}
                    onChange={(e) => setRepository(e.target.value)}
                    className="bg-hermes-bg border border-hermes-border rounded-lg px-3 py-2 text-[11px] text-hermes-text font-mono focus:border-hermes-amber outline-none"
                  />
                  <input
                    type="text"
                    placeholder="Branche (optionnel)"
                    value={branch}
                    onChange={(e) => setBranch(e.target.value)}
                    className="bg-hermes-bg border border-hermes-border rounded-lg px-3 py-2 text-[11px] text-hermes-text font-mono focus:border-hermes-amber outline-none"
                  />
                </div>
                {/* Workspace/Filesystem tool layer (HOS-084) — independent
                    of local_path/repository/branch above. Binding a
                    validated Project here is what lets this mission's tasks
                    really call workspace_list/read/write via Aegis, not
                    just carry a path string for HOS-068's older pre-flight
                    check. */}
                <div className="flex flex-col gap-1">
                  <select
                    value={projectId}
                    onChange={(e) => setProjectId(e.target.value)}
                    className="bg-hermes-bg border border-hermes-border rounded-lg px-3 py-2 text-[11px] text-hermes-text font-mono focus:border-hermes-amber outline-none"
                  >
                    <option value="">Aucun workspace (pas d&apos;accès fichiers réel)</option>
                    {usableProjects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name} — {p.root_path}
                      </option>
                    ))}
                  </select>
                  {usableProjects.length === 0 && (
                    <p className="text-[10px] text-hermes-muted">
                      Aucun workspace validé — enregistrez-en un dans l&apos;onglet Assistant pour donner à cette mission un accès fichiers réel.
                    </p>
                  )}
                </div>
                <div className="flex gap-2 justify-end">
                  <button
                    onClick={() => setShowCreate(false)}
                    className="px-3 py-1.5 text-xs text-hermes-muted hover:text-hermes-text transition-colors"
                  >
                    Annuler
                  </button>
                  <button
                    onClick={handleCreate}
                    disabled={!title.trim() || createMission.isPending}
                    className="px-4 py-1.5 text-xs font-mono bg-hermes-amber text-black rounded-lg hover:bg-hermes-amber-bright transition-colors disabled:opacity-50"
                  >
                    {createMission.isPending ? "Création…" : "Créer"}
                  </button>
                </div>
              </div>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="grid grid-cols-2 gap-4">
        {/* Mission list */}
        <Card title="Missions" subtitle={isLoading ? "Chargement…" : `${missions?.length || 0} missions`}>
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
                  <span className="flex min-w-0 items-center gap-1.5">
                    {mission.plan_is_generic && (
                      <span
                        title="Décomposition réelle échouée — plan générique, sans rapport avec la demande"
                        className="shrink-0"
                      >
                        <AlertCircle size={12} className="text-hermes-amber" />
                      </span>
                    )}
                    <span className="text-sm font-medium text-hermes-text truncate max-w-[200px]">
                      {mission.title}
                    </span>
                  </span>
                  <Badge variant={statusBadge[mission.status]}>{mission.status}</Badge>
                </div>
                <ProgressBar value={mission.progress} size="sm" className="mb-1" />
                <div className="flex items-center gap-3 text-[10px] text-hermes-muted font-mono">
                  {mission.priority && <span>{mission.priority}</span>}
                  {/* The list endpoint only reports a node total, not how
                      many are done — that per-node breakdown only exists
                      on the detail fetch (see the panel to the right). */}
                  <span>{mission.node_count ?? "?"} nœuds</span>
                </div>
              </button>
            ))}
            {missions?.length === 0 && (
              <p className="text-xs text-hermes-muted py-8 text-center">Aucune mission pour l&apos;instant</p>
            )}
          </div>
        </Card>

        {/* Mission detail */}
        <Card
          title={selected ? selected.title : "Détail"}
          subtitle={selected ? `Nœuds : ${selected.completed_nodes || 0}/${selected.node_count || "?"}` : "Sélectionner une mission"}
        >
          {selected ? (
            <div className="flex flex-col gap-3">
              <div className="grid grid-cols-2 gap-2">
                <div className="text-[10px] text-hermes-muted font-mono">Type</div>
                <div className="text-[10px] text-hermes-text font-mono">{selected.type}</div>
                <div className="text-[10px] text-hermes-muted font-mono">Priorité</div>
                <Badge variant={selected.priority === "CRITICAL" ? "danger" : "default"}>
                  {selected.priority}
                </Badge>
                <div className="text-[10px] text-hermes-muted font-mono">Créée</div>
                <div className="text-[10px] text-hermes-text font-mono">
                  {selected.created_at ? new Date(selected.created_at).toLocaleDateString() : "—"}
                </div>
              </div>
              <ProgressBar value={selected.progress} />
              <p className="text-xs text-hermes-muted">{selected.description || "Aucune description"}</p>

              {(selected.local_path || selected.repository || selected.project_id) && (
                <div className="pt-2 border-t border-hermes-border/30 flex flex-col gap-1 text-[10px] font-mono">
                  {selected.local_path && (
                    <div>
                      <span className="text-hermes-muted uppercase">Local : </span>
                      <span className="text-hermes-text">{selected.local_path}</span>
                    </div>
                  )}
                  {selected.repository && (
                    <div>
                      <span className="text-hermes-muted uppercase">Dépôt : </span>
                      <span className="text-hermes-text">
                        {selected.repository}{selected.branch ? `@${selected.branch}` : ""}
                      </span>
                    </div>
                  )}
                  {selected.project_id && (
                    <div>
                      <span className="text-hermes-muted uppercase">Workspace : </span>
                      <span className="text-hermes-text">
                        {projects?.find((p) => p.id === selected.project_id)?.name ?? selected.project_id}
                        {" "}(accès fichiers réel activé)
                      </span>
                    </div>
                  )}
                </div>
              )}

              {selected.status === "PAUSED" && (
                <div className="pt-2 border-t border-hermes-border/30 text-[10px] font-mono text-hermes-amber flex items-center gap-2">
                  <AlertCircle className="w-3 h-3 shrink-0" />
                  Cette mission touche un projet réel et nécessite une
                  validation humaine (Aegis) avant de pouvoir démarrer —
                  augmentez autonomy_level, ou reprenez-la une fois approuvée.
                </div>
              )}

              {selected.plan_is_generic && (
                <div className="pt-2 border-t border-hermes-border/30 text-[10px] font-mono text-hermes-red flex items-start gap-2">
                  <AlertCircle className="w-3 h-3 shrink-0 mt-0.5" />
                  La décomposition réelle de cette mission a échoué (timeout
                  ou réponse du modèle non interprétable) — chaque tâche
                  ci-dessous vient d&apos;un modèle générique, sans rapport
                  avec la demande réelle. Relancez la mission plutôt que de
                  faire confiance à ces résultats.
                </div>
              )}

              {/* Controls */}
              <div className="pt-2 border-t border-hermes-border/30 flex gap-2">
                <button
                  onClick={() => action.start.mutate()}
                  disabled={busy || !["CREATED", "PLANNING", "READY", "VALIDATED"].includes(selected.status)}
                  className="px-3 py-1.5 bg-hermes-green/10 text-hermes-green border border-hermes-green/30 rounded-lg hover:bg-hermes-green/20 transition-colors flex items-center gap-1.5 text-[10px] font-mono disabled:opacity-40"
                >
                  <Play className="w-3 h-3" /> Démarrer
                </button>
                <button
                  onClick={() => action.pause.mutate()}
                  disabled={busy || selected.status !== "RUNNING"}
                  className="px-3 py-1.5 bg-hermes-amber/10 text-hermes-amber border border-hermes-amber/30 rounded-lg hover:bg-hermes-amber/20 transition-colors flex items-center gap-1.5 text-[10px] font-mono disabled:opacity-40"
                >
                  <Pause className="w-3 h-3" /> Pause
                </button>
                <button
                  onClick={() => action.resume.mutate()}
                  disabled={busy || selected.status !== "PAUSED"}
                  className="px-3 py-1.5 bg-hermes-blue/10 text-hermes-blue border border-hermes-blue/30 rounded-lg hover:bg-hermes-blue/20 transition-colors flex items-center gap-1.5 text-[10px] font-mono disabled:opacity-40"
                >
                  <Play className="w-3 h-3" /> Reprendre
                </button>
                <button
                  onClick={() => action.cancel.mutate()}
                  disabled={busy || ["COMPLETED", "FAILED", "CANCELLED"].includes(selected.status)}
                  className="px-3 py-1.5 bg-hermes-red/10 text-hermes-red border border-hermes-red/30 rounded-lg hover:bg-hermes-red/20 transition-colors flex items-center gap-1.5 text-[10px] font-mono disabled:opacity-40"
                >
                  <XCircle className="w-3 h-3" /> Annuler
                </button>
              </div>

              {/* Report — always available once the mission exists, but only
                  meaningful once it has actually run some nodes (see
                  build_mission_report()). */}
              {rep && (
                <div className="pt-2 border-t border-hermes-border/30">
                  <div className="text-[10px] text-hermes-muted font-mono uppercase mb-1">Rapport</div>
                  <div className="text-[10px] font-mono text-hermes-text bg-hermes-bg p-2 rounded border border-hermes-border/50 mb-2">
                    {rep.summary}
                  </div>
                  <div className="grid grid-cols-2 gap-1.5 text-[10px] font-mono">
                    <div className="flex items-center justify-between">
                      <span className="text-hermes-muted">Tâches</span>
                      <span className="text-hermes-text">{rep.tasks_completed}/{rep.tasks_total} ({rep.tasks_failed} échec(s))</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-hermes-muted">Durée</span>
                      <span className="text-hermes-text">{(rep.total_duration_ms ?? 0).toFixed(0)}ms</span>
                    </div>
                    <div className="flex items-center justify-between col-span-2">
                      <span className="text-hermes-muted">Runtimes</span>
                      <span className="text-hermes-text">{rep.runtimes_used.join(", ") || "aucun"}</span>
                    </div>
                  </div>
                  {rep.errors.length > 0 && (
                    <div className="mt-1.5 flex flex-col gap-1">
                      {rep.errors.map((e, i) => (
                        <div key={`err-${i}`} className="text-[9px] text-hermes-red font-mono">{e}</div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center justify-center h-32 text-xs text-hermes-muted font-mono">
              ← Sélectionner une mission pour voir les détails
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
