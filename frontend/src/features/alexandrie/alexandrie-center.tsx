"use client";

import { useState } from "react";
import {
  useAlexandrieDocuments,
  useAlexandrieGraph,
  useAlexandrieHealth,
  useAlexandrieSearch,
  useAlexandrieStatus,
  useAlexandrieSync,
  useAlexandrieSyncHistory,
} from "@/hooks/use-api";
import {
  AsyncPanel,
  CenterHeader,
  DataTable,
  StatGrid,
  Toolbar,
} from "@/components/center-scaffold";
import { Badge } from "@/components/ui/card";

// Alexandrie possède la surface API la plus large du produit (19 routes) et
// n'avait aucun écran dédié — seulement un encart dans le Memory Center.
// L'état de santé est affiché tel quel : si le service est injoignable, le
// Center le dit au lieu de présenter des compteurs à zéro comme un état normal
// (P-001).

export function AlexandrieCenter() {
  const health = useAlexandrieHealth();
  const status = useAlexandrieStatus();
  const documents = useAlexandrieDocuments();
  const graph = useAlexandrieGraph();
  const history = useAlexandrieSyncHistory();
  const sync = useAlexandrieSync();

  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("Tous");
  const [lastError, setLastError] = useState<string | null>(null);
  const results = useAlexandrieSearch(query);

  const docs = documents.data?.documents ?? [];
  const visible = docs.filter((d) => {
    const hay = JSON.stringify(d).toLowerCase();
    return !search || hay.includes(search.toLowerCase());
  });

  const offline = health.data && !health.data.healthy;

  return (
    <div className="animate-fade-in">
      <CenterHeader
        title="Alexandrie Center"
        subtitle="Corpus documentaire, synchronisation et recherche hybride"
        right={
          health.isLoading ? (
            <Badge variant="default">Vérification…</Badge>
          ) : (
            <Badge variant={health.data?.healthy ? "success" : "danger"}>
              {health.data?.healthy ? "CONNECTÉ" : "HORS LIGNE"}
            </Badge>
          )
        }
      />

      {offline && (
        <div className="mb-4 px-3 py-2 rounded-lg bg-hermes-red/10 border border-hermes-red/30 text-xs font-mono text-hermes-text">
          Alexandrie est injoignable —{" "}
          <span className="text-hermes-muted">
            {String(health.data?.error ?? "aucun détail").slice(0, 160)}
          </span>
          . Les compteurs ci-dessous sont donc vides parce que le service ne
          répond pas, pas parce que le corpus est vide.
        </div>
      )}

      <StatGrid
        columns={5}
        stats={[
          { label: "Documents", value: documents.data?.total ?? 0 },
          { label: "Synchronisés", value: status.data?.documents_synced ?? 0 },
          { label: "Indexés", value: status.data?.documents_indexed ?? 0 },
          { label: "Arêtes", value: ((graph.data?.edges ?? []) as unknown[]).length },
          {
            label: "Service",
            value: health.data?.healthy ? "en ligne" : "hors ligne",
            tone: health.data?.healthy ? "ok" : "bad",
          },
        ]}
      />

      <Toolbar
        search={search}
        onSearch={setSearch}
        placeholder="Filtrer les documents chargés…"
        filters={["Tous"]}
        activeFilter={filter}
        onFilter={setFilter}
        actions={
          <button
            onClick={() => {
              setLastError(null);
              sync.mutate(
                { incremental: true },
                {
                  onError: (e) =>
                    setLastError(e instanceof Error ? e.message : "Synchronisation refusée"),
                },
              );
            }}
            disabled={sync.isPending}
            className="px-3 py-2 rounded-lg text-xs font-mono border border-hermes-amber/30 bg-hermes-amber/10 text-hermes-amber-bright hover:bg-hermes-amber/20 disabled:opacity-40"
          >
            {sync.isPending ? "Synchronisation…" : "Synchroniser"}
          </button>
        }
      />

      {lastError && (
        <div className="mb-3 px-3 py-2 rounded-lg bg-hermes-red/10 border border-hermes-red/30 text-hermes-red text-xs font-mono">
          {lastError}
        </div>
      )}

      <div className="mb-4">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Recherche hybride dans le corpus (graphe + embeddings + mots-clés)…"
          className="w-full bg-hermes-bg border border-hermes-border rounded-lg px-3 py-2 text-sm text-hermes-text font-mono focus:outline-none focus:border-hermes-amber/50 placeholder:text-hermes-muted/50"
        />
      </div>

      {query && (
        <div className="mb-4">
          <AsyncPanel
            title="Résultats de recherche"
            subtitle={`requête : ${query}`}
            isLoading={results.isLoading}
            isError={results.isError}
            error={results.error}
            isEmpty={((results.data?.results ?? []) as unknown[]).length === 0}
            emptyLabel="Aucun résultat pour cette requête."
          >
            <DataTable
              rows={(results.data?.results ?? []) as unknown as Record<string, unknown>[]}
              rowKey={(_r, i) => String(i)}
              columns={[{ header: "Résultat", cell: (r) => JSON.stringify(r).slice(0, 120) }]}
            />
          </AsyncPanel>
        </div>
      )}

      <AsyncPanel
        title="Documents"
        subtitle={`${visible.length} affiché(s) sur ${docs.length}`}
        isLoading={documents.isLoading}
        isError={documents.isError}
        error={documents.error}
        isEmpty={visible.length === 0}
        emptyLabel={
          offline
            ? "Service injoignable : impossible de lister le corpus."
            : "Aucun document indexé. Lancez une synchronisation."
        }
      >
        <DataTable
          rows={visible.slice(0, 100)}
          rowKey={(_d, i) => String(i)}
          columns={[{ header: "Document", cell: (d) => JSON.stringify(d).slice(0, 130) }]}
        />
      </AsyncPanel>

      <div className="mt-4">
        <AsyncPanel
          title="Historique de synchronisation"
          subtitle="/api/v1/alexandrie/sync/history"
          isLoading={history.isLoading}
          isError={history.isError}
          error={history.error}
          isEmpty={!history.data || ((history.data as { history?: unknown[] }).history ?? []).length === 0}
          emptyLabel="Aucune synchronisation enregistrée."
        >
          <pre className="text-[10px] text-hermes-muted font-mono whitespace-pre-wrap max-h-[220px] overflow-y-auto">
            {JSON.stringify(history.data, null, 1)}
          </pre>
        </AsyncPanel>
      </div>
    </div>
  );
}
