"use client";

import { useState } from "react";
import { useSubsystemStatistics, useVerificationRunners } from "@/hooks/use-api";
import {
  AsyncPanel,
  CenterHeader,
  DataTable,
  StatGrid,
  Toolbar,
} from "@/components/center-scaffold";
import { Badge } from "@/components/ui/card";

// Deux sources réelles, et une limite assumée.
//
// Les *runners* de vérification viennent de GET /verification/runners (route
// héritée, servie sans le préfixe /api/v1). Les compteurs du moteur de
// validation viennent de /api/v1/system/statistics → execution_engine.validator.
//
// Il n'existe **aucun** endpoint /api/v1/validation : le déclenchement d'une
// vérification passe par POST /verification/run, qui exige une charge utile non
// documentée dans l'OpenAPI. Ce Center ne propose donc pas de bouton
// « lancer » — l'inventer reviendrait à deviner un contrat (P-001).

export function ValidationCenter() {
  const runners = useVerificationRunners();
  const stats = useSubsystemStatistics();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("Tous");

  const all = runners.data ?? [];
  const kinds = ["Tous", ...Array.from(new Set(all.map((r) => r.kind))).slice(0, 6)];
  const visible = all.filter((r) => {
    const hay = `${r.name} ${r.kind} ${r.description}`.toLowerCase();
    if (search && !hay.includes(search.toLowerCase())) return false;
    return filter === "Tous" || r.kind === filter;
  });

  const services = (stats.data?.services ?? {}) as Record<string, Record<string, unknown>>;
  const validator = (services.execution_engine?.validator ?? {}) as Record<string, unknown>;
  const outcomes = (validator.outcomes ?? {}) as Record<string, number>;

  return (
    <div className="animate-fade-in">
      <CenterHeader
        title="Validation Center"
        subtitle="Runners de vérification disponibles et résultats du moteur de validation"
      />

      <StatGrid
        columns={4}
        stats={[
          { label: "Runners", value: all.length },
          { label: "Familles", value: Math.max(kinds.length - 1, 0) },
          { label: "Tâches validées", value: String(validator.total_validated ?? 0) },
          { label: "Critères définis", value: String(validator.criteria_defined ?? 0) },
        ]}
      />

      <Toolbar
        search={search}
        onSearch={setSearch}
        placeholder="Rechercher un runner par nom, famille ou description…"
        filters={kinds}
        activeFilter={filter}
        onFilter={setFilter}
      />

      <AsyncPanel
        title="Runners de vérification"
        subtitle={`${visible.length} affiché(s) sur ${all.length} — GET /verification/runners`}
        isLoading={runners.isLoading}
        isError={runners.isError}
        error={runners.error}
        isEmpty={visible.length === 0}
        emptyLabel={
          all.length === 0
            ? "Aucun runner déclaré par le backend."
            : "Aucun runner ne correspond à ce filtre."
        }
      >
        <DataTable
          rows={visible}
          rowKey={(r) => r.name}
          columns={[
            { header: "Runner", cell: (r) => r.name },
            { header: "Famille", cell: (r) => <Badge>{r.kind}</Badge> },
            {
              header: "Description",
              cell: (r) => <span className="text-hermes-muted">{r.description}</span>,
            },
          ]}
        />
      </AsyncPanel>

      <div className="mt-4">
        <AsyncPanel
          title="Moteur de validation"
          subtitle="execution_engine.validator — /api/v1/system/statistics"
          isLoading={stats.isLoading}
          isError={stats.isError}
          error={stats.error}
          isEmpty={Object.keys(outcomes).length === 0}
          emptyLabel="Aucune tâche validée pour l'instant : les résultats apparaissent après une mission."
        >
          <div className="grid grid-cols-4 gap-3">
            {Object.entries(outcomes).map(([outcome, count]) => (
              <div key={outcome} className="bg-hermes-bg rounded-lg p-3 text-center">
                <div className="text-[10px] text-hermes-muted font-mono uppercase">
                  {outcome}
                </div>
                <div className="text-sm font-bold font-mono text-hermes-text mt-0.5">
                  {count}
                </div>
              </div>
            ))}
          </div>
        </AsyncPanel>
      </div>

      <p className="text-[11px] text-hermes-muted font-mono mt-4">
        Le déclenchement d'une vérification n'est pas exposé ici : sa charge utile n'est pas décrite dans l'OpenAPI, et aucun
        bouton ne sera câblé sur un contrat deviné.
      </p>
    </div>
  );
}
