"use client";

import { useState } from "react";
import { useSubsystemStatistics, useVerificationRunners, useRunVerification } from "@/hooks/use-api";
import {
  AsyncPanel,
  CenterHeader,
  DataTable,
  StatGrid,
  Toolbar,
} from "@/components/center-scaffold";
import { Badge, Button, Card } from "@/components/ui/card";
import { AutonomyPanel } from "./autonomy-panel";

// Deux sources réelles pour l'inventaire, une troisième pour le déclenchement.
//
// Les *runners* de vérification viennent de GET /verification/runners (route
// héritée, servie sans le préfixe /api/v1). Les compteurs du moteur de
// validation viennent de /api/v1/system/statistics → execution_engine.validator.
// Le déclenchement passe par POST /verification/run — dont la charge utile
// *est* documentée (VerificationRunRequest, backend/api/routes/verification.py,
// visible sur /openapi.json) malgré ce que ce fichier affirmait auparavant.
//
// Selon le niveau d'autonomie, Aegis refusera tout ou partie des appels
// (verdict != "allow", ran=false) : c'est la vraie réponse honnête du
// système, pas une raison de cacher le déclencheur. Ce commentaire
// annonçait « le niveau "low" livré » alors que config/security.yaml est à
// "medium" — et le niveau se règle désormais depuis cette page même
// (AutonomyPanel), donc l'écrire en dur ici recommencerait à décrire un
// état que personne ne garantit (HOS-115).

export function ValidationCenter() {
  const runners = useVerificationRunners();
  const stats = useSubsystemStatistics();
  const runVerification = useRunVerification();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("Tous");
  const [repoPath, setRepoPath] = useState("");
  const [selectedRunner, setSelectedRunner] = useState("");

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

      <AutonomyPanel />

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

      <div className="mt-4">
        <Card
          title="Lancer une vérification"
          subtitle="POST /verification/run — soumis à l'évaluation Aegis (verification_run)"
        >
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-2 gap-3">
              <input
                type="text"
                placeholder="Chemin du dépôt (repo_path)…"
                value={repoPath}
                onChange={(e) => setRepoPath(e.target.value)}
                className="bg-hermes-bg border border-hermes-border rounded-lg px-3 py-2 text-xs text-hermes-text font-mono focus:border-hermes-cyan outline-none"
              />
              <select
                value={selectedRunner}
                onChange={(e) => setSelectedRunner(e.target.value)}
                className="bg-hermes-bg border border-hermes-border rounded-lg px-3 py-2 text-xs text-hermes-text font-mono focus:border-hermes-cyan outline-none"
              >
                <option value="">Choisir un runner…</option>
                {all.map((r) => (
                  <option key={r.name} value={r.name}>
                    {r.name} ({r.kind})
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-center justify-between">
              <Button
                variant="primary"
                disabled={!repoPath.trim() || !selectedRunner || runVerification.isPending}
                onClick={() =>
                  runVerification.mutate({ repo_path: repoPath.trim(), runner: selectedRunner })
                }
              >
                {runVerification.isPending ? "Exécution…" : "Lancer"}
              </Button>
              {runVerification.data && (
                <Badge variant={runVerification.data.ran ? (runVerification.data.passed ? "success" : "danger") : "warning"}>
                  {runVerification.data.ran
                    ? runVerification.data.passed
                      ? "Réussi"
                      : "Échoué"
                    : `Refusé — ${runVerification.data.verdict}`}
                </Badge>
              )}
            </div>

            {runVerification.isError && (
              <p className="text-[11px] text-hermes-red font-mono">
                {(runVerification.error as Error)?.message || "La requête a échoué."}
              </p>
            )}

            {runVerification.data && (
              <div className="bg-hermes-bg rounded-lg p-3 flex flex-col gap-1.5">
                {runVerification.data.reason && (
                  <p className="text-[11px] text-hermes-muted font-mono">{runVerification.data.reason}</p>
                )}
                {runVerification.data.output && (
                  <pre className="text-[10px] text-hermes-text font-mono whitespace-pre-wrap max-h-64 overflow-y-auto">
                    {runVerification.data.output}
                  </pre>
                )}
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
