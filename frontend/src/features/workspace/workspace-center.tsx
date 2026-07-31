"use client";

import { useState } from "react";
import { useWorkspaceAction, useWorkspaces } from "@/hooks/use-api";
import {
  AsyncPanel,
  CenterHeader,
  DataTable,
  StatGrid,
  Toolbar,
} from "@/components/center-scaffold";
import { Badge } from "@/components/ui/card";
import { ConfirmAction } from "@/components/confirm-action";

// Les espaces de travail viennent de /api/v1/workspace. Le backend expose
// verrouillage, libération et suppression depuis HOS-047 et aucun écran ne les
// atteignait : ces trois actions sont réellement câblées ici (P-001).

const FILTERS = ["Tous", "Verrouillés", "Libres"] as const;

export function WorkspaceCenter() {
  const workspaces = useWorkspaces();
  const action = useWorkspaceAction();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<string>("Tous");
  const [lastError, setLastError] = useState<string | null>(null);

  const all = workspaces.data ?? [];
  const visible = all.filter((w) => {
    const hay = `${w.workspace_id} ${w.mission_id ?? ""} ${w.agent_id ?? ""}`.toLowerCase();
    if (search && !hay.includes(search.toLowerCase())) return false;
    if (filter === "Verrouillés") return Boolean(w.locked);
    if (filter === "Libres") return !w.locked;
    return true;
  });

  const run = (id: string, verb: "lock" | "release" | "remove") => {
    setLastError(null);
    action.mutate(
      { id, action: verb },
      {
        onError: (e) =>
          setLastError(e instanceof Error ? e.message : "Action refusée"),
      },
    );
  };

  return (
    <div className="animate-fade-in">
      <CenterHeader
        title="Workspace Center"
        subtitle="Espaces de travail des missions — verrouillage, libération, suppression"
      />

      <StatGrid
        columns={4}
        stats={[
          { label: "Espaces", value: all.length },
          { label: "Verrouillés", value: all.filter((w) => w.locked).length, tone: "warn" },
          { label: "Libres", value: all.filter((w) => !w.locked).length, tone: "ok" },
          { label: "Affichés", value: visible.length },
        ]}
      />

      <Toolbar
        search={search}
        onSearch={setSearch}
        placeholder="Rechercher par identifiant, mission ou agent…"
        filters={[...FILTERS]}
        activeFilter={filter}
        onFilter={setFilter}
      />

      {lastError && (
        <div className="mb-3 px-3 py-2 rounded-lg bg-hermes-red/10 border border-hermes-red/30 text-hermes-red text-xs font-mono">
          {lastError}
        </div>
      )}

      <AsyncPanel
        title="Espaces de travail"
        subtitle={`${visible.length} affiché(s) sur ${all.length}`}
        isLoading={workspaces.isLoading}
        isError={workspaces.isError}
        error={workspaces.error}
        isEmpty={visible.length === 0}
        emptyLabel={
          all.length === 0
            ? "Aucun espace de travail. Ils sont créés par les missions qui en réclament un."
            : "Aucun espace ne correspond à ce filtre."
        }
      >
        <DataTable
          rows={visible}
          rowKey={(w) => w.workspace_id}
          columns={[
            { header: "Identifiant", cell: (w) => w.workspace_id.slice(0, 20) },
            { header: "Mission", cell: (w) => w.mission_id || "—" },
            { header: "Agent", cell: (w) => w.agent_id || "—" },
            {
              header: "État",
              cell: (w) => (
                <Badge variant={w.locked ? "warning" : "success"}>
                  {w.locked ? "verrouillé" : "libre"}
                </Badge>
              ),
            },
            {
              header: "Actions",
              align: "right",
              cell: (w) => (
                <div className="flex gap-1 justify-end">
                  <button
                    onClick={() => run(w.workspace_id, w.locked ? "release" : "lock")}
                    disabled={action.isPending}
                    className="px-2 py-1 text-[10px] font-mono rounded border border-hermes-border text-hermes-text hover:border-hermes-amber/50 disabled:opacity-40"
                  >
                    {w.locked ? "Libérer" : "Verrouiller"}
                  </button>
                  <ConfirmAction
                    label="Supprimer"
                    severity="destructive"
                    description="Supprime l'espace de travail et son contenu. Irréversible."
                    target={w.workspace_id}
                    pending={action.isPending}
                    onConfirm={() => run(w.workspace_id, "remove")}
                  />
                </div>
              ),
            },
          ]}
        />
      </AsyncPanel>
    </div>
  );
}
