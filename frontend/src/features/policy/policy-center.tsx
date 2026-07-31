"use client";

import { useState } from "react";
import {
  useApprovals,
  useApproveAction,
  useAuditLog,
  usePolicyRules,
  useRejectAction,
} from "@/hooks/use-api";
import {
  AsyncPanel,
  CenterHeader,
  DataTable,
  StatGrid,
  Toolbar,
} from "@/components/center-scaffold";
import { Badge } from "@/components/ui/card";

// Règles, approbations et journal d'audit, servis par /api/v1/policy/rules,
// /api/v1/approval et /api/v1/audit. Approuver et rejeter appellent réellement
// les endpoints correspondants (P-001).

export function PolicyCenter() {
  const rules = usePolicyRules();
  const approvals = useApprovals();
  const audit = useAuditLog();
  const approve = useApproveAction();
  const reject = useRejectAction();

  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("Tous");
  const [lastError, setLastError] = useState<string | null>(null);

  const allRules = rules.data ?? [];
  const categories = [
    "Tous",
    ...Array.from(new Set(allRules.map((r) => r.category).filter(Boolean))).slice(0, 6),
  ];

  const visibleRules = allRules.filter((r) => {
    const hay = `${r.name} ${r.category} ${r.decision}`.toLowerCase();
    if (search && !hay.includes(search.toLowerCase())) return false;
    return filter === "Tous" || r.category === filter;
  });

  const pending = (approvals.data ?? []).filter(
    (a) => String(a.status).toUpperCase() === "PENDING",
  );

  const decide = (id: string, verb: "approve" | "reject") => {
    setLastError(null);
    const mutation = verb === "approve" ? approve : reject;
    mutation.mutate(
      { id },
      { onError: (e) => setLastError(e instanceof Error ? e.message : "Décision refusée") },
    );
  };

  return (
    <div className="animate-fade-in">
      <CenterHeader
        title="Policy Center"
        subtitle="Règles de gouvernance, approbations en attente et journal d'audit"
      />

      <StatGrid
        columns={4}
        stats={[
          { label: "Règles", value: allRules.length },
          { label: "Catégories", value: Math.max(categories.length - 1, 0) },
          {
            label: "En attente",
            value: pending.length,
            tone: pending.length > 0 ? "warn" : "ok",
          },
          { label: "Entrées d'audit", value: (audit.data ?? []).length },
        ]}
      />

      <Toolbar
        search={search}
        onSearch={setSearch}
        placeholder="Rechercher une règle par nom, catégorie ou décision…"
        filters={categories}
        activeFilter={filter}
        onFilter={setFilter}
      />

      {lastError && (
        <div className="mb-3 px-3 py-2 rounded-lg bg-hermes-red/10 border border-hermes-red/30 text-hermes-red text-xs font-mono">
          {lastError}
        </div>
      )}

      <AsyncPanel
        title="Approbations en attente"
        subtitle={`${pending.length} demande(s)`}
        isLoading={approvals.isLoading}
        isError={approvals.isError}
        error={approvals.error}
        isEmpty={pending.length === 0}
        emptyLabel="Aucune approbation en attente."
      >
        <DataTable
          rows={pending}
          rowKey={(a) => a.id}
          columns={[
            { header: "Opération", cell: (a) => a.operation || "—" },
            { header: "Priorité", cell: (a) => <Badge variant="warning">{a.priority}</Badge> },
            {
              header: "Décision",
              align: "right",
              cell: (a) => (
                <div className="flex gap-1 justify-end">
                  <button
                    onClick={() => decide(a.id, "approve")}
                    disabled={approve.isPending}
                    className="px-2 py-1 text-[10px] font-mono rounded border border-hermes-green/40 text-hermes-green hover:bg-hermes-green/10 disabled:opacity-40"
                  >
                    Approuver
                  </button>
                  <button
                    onClick={() => decide(a.id, "reject")}
                    disabled={reject.isPending}
                    className="px-2 py-1 text-[10px] font-mono rounded border border-hermes-red/40 text-hermes-red hover:bg-hermes-red/10 disabled:opacity-40"
                  >
                    Rejeter
                  </button>
                </div>
              ),
            },
          ]}
        />
      </AsyncPanel>

      <div className="mt-4 grid grid-cols-2 gap-4">
        <AsyncPanel
          title="Règles de politique"
          subtitle={`${visibleRules.length} affichée(s) sur ${allRules.length}`}
          isLoading={rules.isLoading}
          isError={rules.isError}
          error={rules.error}
          isEmpty={visibleRules.length === 0}
          emptyLabel={
            allRules.length === 0
              ? "Aucune règle chargée."
              : "Aucune règle ne correspond à ce filtre."
          }
        >
          <DataTable
            rows={visibleRules}
            rowKey={(r) => r.id}
            columns={[
              { header: "Règle", cell: (r) => r.name },
              { header: "Catégorie", cell: (r) => <Badge>{r.category}</Badge> },
              { header: "Décision", cell: (r) => r.decision },
            ]}
          />
        </AsyncPanel>

        <AsyncPanel
          title="Journal d'audit"
          subtitle="/api/v1/audit"
          isLoading={audit.isLoading}
          isError={audit.isError}
          error={audit.error}
          isEmpty={(audit.data ?? []).length === 0}
          emptyLabel="Le journal d'audit est vide."
        >
          <div className="max-h-[280px] overflow-y-auto flex flex-col gap-1">
            {(audit.data ?? []).slice(0, 60).map((e, i) => (
              <div key={i} className="text-[10px] font-mono bg-hermes-bg rounded px-2 py-1 text-hermes-muted">
                {JSON.stringify(e).slice(0, 120)}
              </div>
            ))}
          </div>
        </AsyncPanel>
      </div>
    </div>
  );
}
