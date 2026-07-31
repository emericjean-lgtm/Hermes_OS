"use client";

import { useMemo, useState } from "react";
import {
  useSubsystemHealth,
  useSystemHealth,
  useSubsystemAssembly,
} from "@/hooks/use-api";
import {
  AsyncPanel,
  CenterHeader,
  DataTable,
  StatGrid,
  Toolbar,
} from "@/components/center-scaffold";
import { Badge } from "@/components/ui/card";

// Santé des sous-systèmes. Tout vient de /api/v1/system/health, /api/v1/health
// et /api/v1/system/assembly — aucune donnée n'est fabriquée ici. Les
// sous-systèmes qui n'exposent pas d'accesseur de statistiques sont rapportés
// « unknown », pas supposés sains (P-001).

const FILTERS = ["Tous", "Sain", "Inconnu", "Défaillant"] as const;

interface Row {
  name: string;
  status: string;
  detail: string;
}

export function HealthCenter() {
  const health = useSubsystemHealth();
  const uptime = useSystemHealth();
  const assembly = useSubsystemAssembly();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<string>("Tous");

  const rows: Row[] = useMemo(() => {
    const detail = health.data?.detail ?? {};
    return Object.entries(detail).map(([name, info]) => ({
      name,
      status: info.status ?? "unknown",
      detail: info.detail ?? "",
    }));
  }, [health.data]);

  const visible = rows.filter((r) => {
    const matchesSearch = r.name.toLowerCase().includes(search.toLowerCase());
    const matchesFilter =
      filter === "Tous" ||
      (filter === "Sain" && r.status === "healthy") ||
      (filter === "Inconnu" && r.status === "unknown") ||
      (filter === "Défaillant" &&
        r.status !== "healthy" &&
        r.status !== "unknown");
    return matchesSearch && matchesFilter;
  });

  const byStatus = health.data?.by_status ?? {};
  const silent = health.data?.silent ?? [];
  const bootstrap = (assembly.data?.bootstrap ?? {}) as Record<string, unknown>;

  return (
    <div className="animate-fade-in">
      <CenterHeader
        title="Health Center"
        subtitle="Santé des sous-systèmes, disponibilité et complétude de l'assemblage"
        right={
          health.data && (
            <Badge variant={health.data.status === "healthy" ? "success" : "warning"}>
              {health.data.status}
            </Badge>
          )
        }
      />

      <StatGrid
        columns={5}
        stats={[
          { label: "Sous-systèmes", value: health.data?.services ?? "—" },
          { label: "Sains", value: byStatus.healthy ?? 0, tone: "ok" },
          { label: "Sans télémétrie", value: silent.length, tone: "warn" },
          {
            label: "Défaillants",
            value: health.data?.unhealthy?.length ?? 0,
            tone: (health.data?.unhealthy?.length ?? 0) > 0 ? "bad" : "ok",
          },
          {
            label: "Uptime",
            value: uptime.data
              ? `${Math.floor((uptime.data.uptime_seconds ?? 0) / 60)} min`
              : "—",
          },
        ]}
      />

      <Toolbar
        search={search}
        onSearch={setSearch}
        placeholder="Filtrer par nom de sous-système…"
        filters={[...FILTERS]}
        activeFilter={filter}
        onFilter={setFilter}
      />

      <AsyncPanel
        title="Sous-systèmes"
        subtitle={`${visible.length} affiché(s) sur ${rows.length}`}
        isLoading={health.isLoading}
        isError={health.isError}
        error={health.error}
        isEmpty={visible.length === 0}
        emptyLabel={
          rows.length === 0
            ? "Le backend ne rapporte aucun sous-système."
            : "Aucun sous-système ne correspond à ce filtre."
        }
      >
        <DataTable
          rows={visible}
          rowKey={(r) => r.name}
          columns={[
            { header: "Sous-système", cell: (r) => r.name },
            {
              header: "État",
              cell: (r) => (
                <Badge
                  variant={
                    r.status === "healthy"
                      ? "success"
                      : r.status === "unknown"
                        ? "default"
                        : "danger"
                  }
                >
                  {r.status}
                </Badge>
              ),
            },
            {
              header: "Détail",
              cell: (r) => (
                <span className="text-hermes-muted">{r.detail || "—"}</span>
              ),
            },
          ]}
        />
      </AsyncPanel>

      <div className="mt-4">
        <AsyncPanel
          title="Assemblage"
          subtitle="Rapport du composition root"
          isLoading={assembly.isLoading}
          isError={assembly.isError}
          error={assembly.error}
          isEmpty={Object.keys(bootstrap).length === 0}
          emptyLabel="Le bootstrap n'a publié aucun rapport."
        >
          <div className="grid grid-cols-4 gap-3">
            {[
              { label: "Services construits", value: `${bootstrap.services_built ?? "—"} / ${bootstrap.services_expected ?? "—"}` },
              { label: "Routeurs montés", value: String(bootstrap.routers_mounted ?? "—") },
              { label: "Cycles", value: String(((bootstrap.dependency_cycles as unknown[]) ?? []).length) },
              { label: "Services isolés", value: String(((bootstrap.isolated_services as unknown[]) ?? []).length) },
            ].map((s) => (
              <div key={s.label} className="bg-hermes-bg rounded-lg p-3">
                <div className="text-[10px] text-hermes-muted font-mono uppercase">
                  {s.label}
                </div>
                <div className="text-sm font-bold font-mono text-hermes-text mt-0.5">
                  {s.value}
                </div>
              </div>
            ))}
          </div>
        </AsyncPanel>
      </div>

      {silent.length > 0 && (
        <p className="text-[11px] text-hermes-muted font-mono mt-4">
          {silent.length} sous-système(s) n'exposent aucun accesseur de
          statistiques : leur santé ne peut pas être sondée et est rapportée
          « unknown » plutôt que supposée saine.
        </p>
      )}
    </div>
  );
}
