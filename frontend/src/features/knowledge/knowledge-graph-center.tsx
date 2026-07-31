"use client";

import { useMemo, useState } from "react";
import { useAlexandrieGraph, useKnowledgeGraph } from "@/hooks/use-api";
import {
  AsyncPanel,
  CenterHeader,
  DataTable,
  StatGrid,
  Toolbar,
} from "@/components/center-scaffold";
import { Badge } from "@/components/ui/card";

// Deux graphes distincts, servis par deux endpoints réels :
// /api/v1/memory/graph (nœuds + arêtes de la mémoire) et /api/v1/alexandrie/graph
// (arêtes documentaires). Rien n'est fusionné artificiellement : chacun est
// présenté avec sa source (P-001).

export function KnowledgeGraphCenter() {
  const memory = useKnowledgeGraph();
  const alexandrie = useAlexandrieGraph();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("Tous");

  const nodes = memory.data?.nodes ?? [];
  const edges = memory.data?.edges ?? [];

  const types = useMemo(() => {
    const set = new Set(nodes.map((n) => n.type).filter(Boolean));
    return ["Tous", ...Array.from(set).slice(0, 6)];
  }, [nodes]);

  const visibleNodes = nodes.filter((n) => {
    const hay = `${n.label ?? ""} ${n.id} ${n.type ?? ""}`.toLowerCase();
    if (search && !hay.includes(search.toLowerCase())) return false;
    return filter === "Tous" || n.type === filter;
  });

  const alexEdges = (alexandrie.data?.edges ?? []) as Record<string, unknown>[];

  return (
    <div className="animate-fade-in">
      <CenterHeader
        title="Knowledge Graph Center"
        subtitle="Graphe de mémoire et graphe documentaire Alexandrie"
      />

      <StatGrid
        columns={4}
        stats={[
          { label: "Nœuds mémoire", value: nodes.length },
          { label: "Arêtes mémoire", value: edges.length },
          { label: "Arêtes Alexandrie", value: alexEdges.length },
          { label: "Types distincts", value: Math.max(types.length - 1, 0) },
        ]}
      />

      <Toolbar
        search={search}
        onSearch={setSearch}
        placeholder="Rechercher un nœud par libellé, identifiant ou type…"
        filters={types}
        activeFilter={filter}
        onFilter={setFilter}
      />

      <AsyncPanel
        title="Nœuds du graphe de mémoire"
        subtitle={`${visibleNodes.length} affiché(s) sur ${nodes.length} — /api/v1/memory/graph`}
        isLoading={memory.isLoading}
        isError={memory.isError}
        error={memory.error}
        isEmpty={visibleNodes.length === 0}
        emptyLabel={
          nodes.length === 0
            ? "Le graphe de mémoire est vide : aucune mission n'y a encore écrit."
            : "Aucun nœud ne correspond à ce filtre."
        }
      >
        <DataTable
          rows={visibleNodes.slice(0, 200)}
          rowKey={(n) => n.id}
          columns={[
            { header: "Libellé", cell: (n) => n.label || n.id.slice(0, 24) },
            { header: "Type", cell: (n) => <Badge>{n.type || "—"}</Badge> },
            {
              header: "Propriétés",
              cell: (n) => (
                <span className="text-hermes-muted">
                  {Object.keys(n.properties ?? {}).length} champ(s)
                </span>
              ),
            },
          ]}
        />
      </AsyncPanel>

      <div className="mt-4 grid grid-cols-2 gap-4">
        <AsyncPanel
          title="Arêtes de mémoire"
          subtitle="Relations entre nœuds"
          isLoading={memory.isLoading}
          isError={memory.isError}
          error={memory.error}
          isEmpty={edges.length === 0}
          emptyLabel="Aucune relation enregistrée."
        >
          <DataTable
            rows={edges.slice(0, 100)}
            rowKey={(e, i) => `${e.from}-${e.to}-${i}`}
            columns={[
              { header: "De", cell: (e) => e.from.slice(0, 18) },
              { header: "Vers", cell: (e) => e.to.slice(0, 18) },
              { header: "Type", cell: (e) => e.type },
            ]}
          />
        </AsyncPanel>

        <AsyncPanel
          title="Graphe Alexandrie"
          subtitle="/api/v1/alexandrie/graph"
          isLoading={alexandrie.isLoading}
          isError={alexandrie.isError}
          error={alexandrie.error}
          isEmpty={alexEdges.length === 0}
          emptyLabel="Aucune arête documentaire : Alexandrie n'a pas encore indexé de corpus."
        >
          <DataTable
            rows={alexEdges.slice(0, 100)}
            rowKey={(_e, i) => String(i)}
            columns={[
              { header: "Arête", cell: (e) => JSON.stringify(e).slice(0, 80) },
            ]}
          />
        </AsyncPanel>
      </div>
    </div>
  );
}
