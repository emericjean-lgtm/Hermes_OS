"use client";

import { useMemo, useState } from "react";
import {
  useMonitoringResources,
  useResourceAllocations,
  useRuntimeEventLog,
  useRuntimeIntelligence,
  useSubsystemStatistics,
} from "@/hooks/use-api";
import { useWebSocket } from "@/hooks/use-websocket";
import {
  AsyncPanel,
  CenterHeader,
  DataTable,
  LiveBadge,
  StatGrid,
  Toolbar,
} from "@/components/center-scaffold";
import { formatGioPair, vramOccupee } from "@/lib/format";

// Toutes les mesures viennent de /runtime/resources, /runtime/events,
// /runtime/intelligence et /system/statistics. Le flux temps réel est le
// WebSocket /ws déjà utilisé par le Dashboard (P-001).

/** `imbrique` supprime l'en-tete : ce Center est alors rendu sous
 *  celui du Runtime Center, qui porte deja titre et onglets (HOS-177). */
export function MonitoringCenter({ imbrique = false }: { imbrique?: boolean }) {
  const resources = useMonitoringResources();
  const allocations = useResourceAllocations();
  const events = useRuntimeEventLog(100);
  const intelligence = useRuntimeIntelligence();
  const statistics = useSubsystemStatistics();
  const { events: live, connected } = useWebSocket({ maxEvents: 40 });

  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("Tous");

  const gpu = resources.data?.gpu;
  const ram = resources.data?.ram;

  const liveRows = useMemo(() => {
    const term = search.toLowerCase();
    return live
      .filter((e) => {
        const type = String((e as { type?: string }).type ?? "");
        if (filter !== "Tous" && !type.startsWith(filter.toLowerCase())) return false;
        return !term || JSON.stringify(e).toLowerCase().includes(term);
      })
      .slice(0, 40);
  }, [live, search, filter]);

  const services = (statistics.data?.services ?? {}) as Record<string, unknown>;

  return (
    <div className="animate-fade-in">
      {!imbrique && (
        <CenterHeader
          title="Monitoring Center"
          subtitle="Ressources matérielles, allocations et flux d'événements en direct"
          right={<LiveBadge connected={connected} />}
        />
      )}

      <StatGrid
        columns={5}
        stats={[
          { label: "GPU", value: gpu?.available ? gpu.name : "non détecté", tone: gpu?.available ? "ok" : "warn" },
          {
            label: "VRAM utilisée",
            value: gpu ? formatGioPair(vramOccupee(gpu), gpu.vram_total_bytes) : "—",
          },
          { label: "RAM", value: ram ? `${ram.usage_pct}%` : "—", tone: (ram?.usage_pct ?? 0) > 85 ? "bad" : "ok" },
          { label: "Allocations", value: resources.data?.allocations ?? 0 },
          { label: "Services suivis", value: Object.keys(services).length },
        ]}
      />

      <Toolbar
        search={search}
        onSearch={setSearch}
        placeholder="Filtrer les événements en direct…"
        filters={["Tous", "execution", "mission", "runtime", "system"]}
        activeFilter={filter}
        onFilter={setFilter}
      />

      <div className="grid grid-cols-2 gap-4">
        <AsyncPanel
          title="Flux temps réel"
          subtitle={connected ? `${liveRows.length} événement(s)` : "WebSocket déconnecté"}
          isLoading={false}
          isError={!connected}
          error={new Error("Le WebSocket /ws n'est pas connecté")}
          isEmpty={liveRows.length === 0}
          emptyLabel="Aucun événement reçu depuis l'ouverture de cet écran."
        >
          <div className="max-h-[320px] overflow-y-auto flex flex-col gap-1">
            {liveRows.map((e, i) => (
              <div
                key={`${(e as { type?: string }).type}-${i}`}
                className="text-[10px] font-mono bg-hermes-bg rounded px-2 py-1"
              >
                <span className="text-hermes-amber">
                  {String((e as { type?: string }).type ?? "événement")}
                </span>{" "}
                <span className="text-hermes-muted">
                  {JSON.stringify(e).slice(0, 110)}
                </span>
              </div>
            ))}
          </div>
        </AsyncPanel>

        <AsyncPanel
          title="Journal runtime"
          subtitle="/api/v1/runtime/events"
          isLoading={events.isLoading}
          isError={events.isError}
          error={events.error}
          isEmpty={(events.data ?? []).length === 0}
          emptyLabel="Le journal runtime est vide."
        >
          <div className="max-h-[320px] overflow-y-auto flex flex-col gap-1">
            {(events.data ?? []).slice(0, 50).map((e, i) => (
              <div key={i} className="text-[10px] font-mono bg-hermes-bg rounded px-2 py-1 text-hermes-muted">
                {JSON.stringify(e).slice(0, 130)}
              </div>
            ))}
          </div>
        </AsyncPanel>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4">
        <AsyncPanel
          title="Allocations de ressources"
          subtitle="/api/v1/runtime/resources/allocations"
          isLoading={allocations.isLoading}
          isError={allocations.isError}
          error={allocations.error}
          isEmpty={(allocations.data ?? []).length === 0}
          emptyLabel="Aucune ressource allouée actuellement."
        >
          <DataTable
            rows={allocations.data ?? []}
            rowKey={(_r, i) => String(i)}
            columns={[
              { header: "Allocation", cell: (r) => JSON.stringify(r).slice(0, 90) },
            ]}
          />
        </AsyncPanel>

        <AsyncPanel
          title="Intelligence runtime"
          subtitle="/api/v1/runtime/intelligence/scores"
          isLoading={intelligence.isLoading}
          isError={intelligence.isError}
          error={intelligence.error}
          isEmpty={!intelligence.data || Object.keys(intelligence.data).length === 0}
          emptyLabel="Aucun score runtime publié."
        >
          <pre className="text-[10px] text-hermes-muted font-mono whitespace-pre-wrap max-h-[240px] overflow-y-auto">
            {JSON.stringify(intelligence.data, null, 1)}
          </pre>
        </AsyncPanel>
      </div>
    </div>
  );
}
