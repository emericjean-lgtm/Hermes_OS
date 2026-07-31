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

// Exécutions réelles servies par /api/v1/execution et /api/v1/execution/statistics.
// Les actions pause / reprise / annulation existent côté backend depuis HOS-050
// et n'avaient aucun bouton (P-001).

const FILTERS = ["Tous", "En cours", "Terminés", "Échoués"] as const;

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
    const state = String((e as { state?: string }).state ?? "").toLowerCase();
    const hay = JSON.stringify(e).toLowerCase();
    if (search && !hay.includes(search.toLowerCase())) return false;
    if (filter === "En cours") return state.includes("running") || state.includes("pending");
    if (filter === "Terminés") return state.includes("complet");
    if (filter === "Échoués") return state.includes("fail");
    return true;
  });

  const executor = (stats.data?.executor_stats ?? {}) as Record<string, Record<string, number>>;

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
        subtitle="Exécutions en cours, planificateur et pilotage pause / reprise / annulation"
      />

      <StatGrid
        columns={5}
        stats={[
          { label: "Actives", value: String(stats.data?.active_executions ?? 0) },
          { label: "Terminées", value: String(stats.data?.completed_executions ?? 0), tone: "ok" },
          { label: "Total", value: String(stats.data?.total_executions ?? 0) },
          { label: "Tâches planifiées", value: String(executor.scheduler?.total ?? 0) },
          { label: "Validées", value: String(executor.validator?.total_validated ?? 0) },
        ]}
      />

      <Toolbar
        search={search}
        onSearch={setSearch}
        placeholder="Rechercher une exécution…"
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
                  className="px-3 py-2 rounded-lg text-xs font-mono border border-hermes-border text-hermes-text hover:border-hermes-amber/50"
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
        title="Exécutions"
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
        <DataTable
          rows={visible}
          rowKey={(e, i) => String((e as { execution_id?: string }).execution_id ?? i)}
          columns={[
            {
              header: "Identifiant",
              cell: (e) => {
                const id = String((e as { execution_id?: string }).execution_id ?? "");
                return (
                  <button
                    onClick={() => setSelected(id || null)}
                    className={`font-mono ${selected === id ? "text-hermes-amber-bright" : "text-hermes-text hover:text-hermes-amber"}`}
                  >
                    {id.slice(0, 20) || "—"}
                  </button>
                );
              },
            },
            {
              header: "État",
              cell: (e) => <Badge>{String((e as { state?: string }).state ?? "—")}</Badge>,
            },
            {
              header: "Mission",
              cell: (e) => String((e as { mission_id?: string }).mission_id ?? "—").slice(0, 20),
            },
          ]}
        />
      </AsyncPanel>

      <div className="mt-4">
        <AsyncPanel
          title="Moteur d'exécution"
          subtitle="/api/v1/execution/statistics"
          isLoading={stats.isLoading}
          isError={stats.isError}
          error={stats.error}
          isEmpty={Object.keys(executor).length === 0}
          emptyLabel="Le moteur n'a publié aucune statistique."
        >
          <div className="grid grid-cols-5 gap-3">
            {Object.entries(executor).map(([name, values]) => (
              <div key={name} className="bg-hermes-bg rounded-lg p-3">
                <div className="text-[10px] text-hermes-muted font-mono uppercase">
                  {name}
                </div>
                <div className="text-sm font-bold font-mono text-hermes-text mt-0.5">
                  {typeof values === "object" && values
                    ? Object.values(values).find((v) => typeof v === "number") ?? 0
                    : String(values)}
                </div>
              </div>
            ))}
          </div>
        </AsyncPanel>
      </div>
    </div>
  );
}
