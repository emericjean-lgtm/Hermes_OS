"use client";

import { useState } from "react";
import {
  useExecutionAction,
  useExecutionStatistics,
  useExecutions,
} from "@/hooks/use-api";
import {
  AsyncPanel,
  CenterHeader,
  DataTable,
  StatGrid,
  Toolbar,
} from "@/components/center-scaffold";
import { Badge } from "@/components/ui/card";
import type { ExecutionSummary } from "@/types/hermes";

// Real task executions, one row per mission node (HOS-069) — before this,
// ExecutionController wrapped a private MissionExecutor nothing ever fed,
// so this Center could structurally never show real Mission/Autonomous
// activity ("Aucune exécution enregistrée" was accurate, not a bug).
// Pause/resume/cancel exist server-side since HOS-050 and had no button
// (P-001); they still apply here, though real Mission-driven executions
// finish in one pass and are rarely "pausable" mid-flight.

const FILTERS = ["Tous", "En cours", "Terminés", "Échoués"] as const;

const stateBadge = (state: string): "success" | "warning" | "danger" | "purple" | "default" => {
  const v: Record<string, "success" | "warning" | "danger" | "purple" | "default"> = {
    completed: "success",
    running: "purple",
    validating: "purple",
    failed: "danger",
    cancelled: "default",
    paused: "warning",
    waiting_approval: "warning",
    ready: "default",
    planning: "default",
    created: "default",
  };
  return v[state] ?? "default";
};

export function ExecutionCenter() {
  const executions = useExecutions();
  const stats = useExecutionStatistics();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<string>("Tous");
  const [selected, setSelected] = useState<string | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  const action = useExecutionAction(selected ?? "");

  const all = executions.data ?? [];
  const visible = all.filter((e) => {
    const state = (e.state ?? "").toLowerCase();
    const hay = `${e.execution_id} ${e.mission_id} ${e.user_goal}`.toLowerCase();
    if (search && !hay.includes(search.toLowerCase())) return false;
    if (filter === "En cours") return state === "running" || state === "validating";
    if (filter === "Terminés") return state === "completed";
    if (filter === "Échoués") return state === "failed";
    return true;
  });

  const selectedExecution = all.find((e) => e.execution_id === selected) ?? null;
  const scheduler = stats.data?.executor_stats?.scheduler;

  const run = (verb: "pause" | "resume" | "cancel") => {
    setLastError(null);
    action[verb].mutate(undefined, {
      onError: (e) => setLastError(e instanceof Error ? e.message : "Action refusée"),
    });
  };

  return (
    <div className="animate-fade-in">
      <CenterHeader
        title="Execution Center"
        subtitle="Exécutions de tâches réelles, planificateur et pilotage pause / reprise / annulation"
      />

      <StatGrid
        columns={5}
        stats={[
          { label: "En cours", value: String(scheduler?.running ?? 0) },
          { label: "En attente", value: String(scheduler?.pending ?? 0) },
          { label: "Terminées", value: String(scheduler?.completed ?? 0), tone: "ok" },
          { label: "Échouées", value: String(scheduler?.failed ?? 0), tone: scheduler?.failed ? "bad" : undefined },
          { label: "Total", value: String(scheduler?.total ?? 0) },
        ]}
      />

      <Toolbar
        search={search}
        onSearch={setSearch}
        placeholder="Rechercher par tâche, mission ou identifiant…"
        filters={[...FILTERS]}
        activeFilter={filter}
        onFilter={setFilter}
        actions={
          selected && (
            <div className="flex gap-1">
              {(["pause", "resume", "cancel"] as const).map((verb) => (
                <button
                  key={verb}
                  onClick={() => run(verb)}
                  disabled={action[verb].isPending}
                  className="px-3 py-2 rounded-lg text-xs font-mono border border-hermes-border text-hermes-text hover:border-hermes-amber/50 disabled:opacity-40"
                >
                  {verb === "pause" ? "Pause" : verb === "resume" ? "Reprendre" : "Annuler"}
                </button>
              ))}
            </div>
          )
        }
      />

      {lastError && (
        <div className="mb-3 px-3 py-2 rounded-lg bg-hermes-red/10 border border-hermes-red/30 text-hermes-red text-xs font-mono">
          {lastError}
        </div>
      )}

      <AsyncPanel
        title="Exécutions actives"
        subtitle={
          selected
            ? `Sélection : ${selected.slice(0, 18)} — les actions ci-dessus s'y appliquent`
            : `${visible.length} affichée(s) — cliquez une ligne pour la piloter`
        }
        isLoading={executions.isLoading}
        isError={executions.isError}
        error={executions.error}
        isEmpty={visible.length === 0}
        emptyLabel={
          all.length === 0
            ? "Aucune exécution enregistrée. Lancez une mission pour en créer une."
            : "Aucune exécution ne correspond à ce filtre."
        }
      >
        <DataTable<ExecutionSummary>
          rows={visible}
          rowKey={(e) => e.execution_id}
          columns={[
            {
              header: "Tâche",
              cell: (e) => (
                <button
                  onClick={() => setSelected(e.execution_id)}
                  className={`text-left font-mono truncate max-w-[220px] block ${
                    selected === e.execution_id ? "text-hermes-amber-bright" : "text-hermes-text hover:text-hermes-amber"
                  }`}
                  title={e.user_goal}
                >
                  {e.user_goal || e.execution_id.slice(0, 20)}
                </button>
              ),
            },
            {
              header: "État",
              cell: (e) => <Badge variant={stateBadge(e.state)}>{e.state}</Badge>,
            },
            {
              header: "Mission",
              cell: (e) => (
                <span className="font-mono text-hermes-muted" title={e.mission_id}>
                  {e.mission_id.slice(0, 16) || "—"}
                </span>
              ),
            },
            {
              header: "Agent(s)",
              cell: (e) => e.report?.agents_used.join(", ") || "—",
            },
            {
              header: "Runtime(s)",
              cell: (e) => e.report?.runtimes_used.join(", ") || "—",
            },
            {
              header: "Durée",
              align: "right",
              cell: (e) => (e.report ? `${e.report.duration_ms.toFixed(0)}ms` : "—"),
            },
          ]}
        />
      </AsyncPanel>

      {selectedExecution && (
        <div className="mt-4">
          <AsyncPanel
            title="Détail de l'exécution"
            subtitle={selectedExecution.execution_id}
            isLoading={false}
            isError={false}
            isEmpty={false}
            emptyLabel=""
          >
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5 text-[11px] font-mono">
                <div className="flex justify-between">
                  <span className="text-hermes-muted">Tâche</span>
                  <span className="text-hermes-text text-right">{selectedExecution.user_goal || "—"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-hermes-muted">Mission</span>
                  <span className="text-hermes-text">{selectedExecution.mission_id || "—"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-hermes-muted">État</span>
                  <Badge variant={stateBadge(selectedExecution.state)}>{selectedExecution.state}</Badge>
                </div>
                {selectedExecution.report && (
                  <>
                    <div className="flex justify-between">
                      <span className="text-hermes-muted">Tâches</span>
                      <span className="text-hermes-text">
                        {selectedExecution.report.completed_tasks}/{selectedExecution.report.total_tasks}
                        {selectedExecution.report.failed_tasks > 0 && (
                          <span className="text-hermes-red"> ({selectedExecution.report.failed_tasks} échouée(s))</span>
                        )}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-hermes-muted">Durée</span>
                      <span className="text-hermes-text">{selectedExecution.report.duration_ms.toFixed(0)}ms</span>
                    </div>
                  </>
                )}
              </div>
              <div className="space-y-1.5">
                {/* The blocked/failed explanation the Cockpit needs (HOS-069
                    Phase E) — real reasons: VRAM admission denial, Ollama
                    timeout, validation failure. Empty when nothing failed. */}
                {selectedExecution.report?.errors && selectedExecution.report.errors.length > 0 ? (
                  <div className="bg-hermes-red/5 border border-hermes-red/20 rounded-lg p-2">
                    <div className="text-[10px] text-hermes-red font-mono uppercase mb-1">
                      Pourquoi ça a échoué
                    </div>
                    {selectedExecution.report.errors.map((err, i) => (
                      <div key={i} className="text-[10px] text-hermes-text font-mono">{err}</div>
                    ))}
                  </div>
                ) : selectedExecution.is_terminal ? (
                  <div className="text-[10px] text-hermes-muted font-mono">Aucune erreur.</div>
                ) : (
                  <div className="text-[10px] text-hermes-muted font-mono">En cours…</div>
                )}
              </div>
            </div>
          </AsyncPanel>
        </div>
      )}

      <div className="mt-4">
        <AsyncPanel
          title="Moteur d'exécution"
          subtitle="/api/v1/execution/statistics"
          isLoading={stats.isLoading}
          isError={stats.isError}
          error={stats.error}
          isEmpty={!scheduler}
          emptyLabel="Le moteur n'a publié aucune statistique."
        >
          <div className="grid grid-cols-5 gap-3">
            {[
              { label: "Agents enregistrés", value: stats.data?.executor_stats?.coordinator?.agents_registered ?? 0 },
              { label: "Runtimes dispo.", value: stats.data?.executor_stats?.coordinator?.runtimes_available ?? 0 },
              { label: "Affectations actives", value: stats.data?.executor_stats?.coordinator?.active_assignments ?? 0 },
              { label: "Validées", value: stats.data?.executor_stats?.validator?.total_validated ?? 0 },
              { label: "Événements publiés", value: stats.data?.executor_stats?.events_published ?? 0 },
            ].map((s) => (
              <div key={s.label} className="bg-hermes-bg rounded-lg p-3">
                <div className="text-[10px] text-hermes-muted font-mono uppercase">{s.label}</div>
                <div className="text-sm font-bold font-mono text-hermes-text mt-0.5">{s.value}</div>
              </div>
            ))}
          </div>
        </AsyncPanel>
      </div>
    </div>
  );
}
