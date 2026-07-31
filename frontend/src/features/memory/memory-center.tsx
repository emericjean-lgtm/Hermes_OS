"use client";

import { useMemo, useState } from "react";
import {
  useMemorySearch,
  useKnowledgeGraph,
  useExperiences,
  useMemoryStatistics,
  useAlexandrieStatus,
  useAlexandrieHealth,
  useAlexandrieSearch,
  useAlexandrieSync,
  useAlexandrieSyncHistory,
  useAlexandrieDocuments,
  useAlexandrieGraph,
} from "@/hooks/use-api";
import { Badge, Button, Beacon } from "@/components/ui/card";
import {
  AsyncPanel,
  CenterHeader,
  CenterTabs,
  DataTable,
  StatGrid,
  Toolbar,
} from "@/components/center-scaffold";
import type { Experience } from "@/types/hermes";

/* ═══════════════════════════════════════════════════════════════════
   Memory Center — fusion de Memory, Knowledge Graph et Alexandrie.

   Les trois écrans se recouvraient : Memory appelait déjà les sept
   hooks d'Alexandrie *et* le graphe de connaissances, donc Knowledge
   Graph et Alexandrie n'affichaient rien qu'il ne montrait pas. Trois
   entrées de menu servaient les mêmes endpoints avec trois mises en
   page différentes.

   Ils deviennent trois onglets d'un seul Center. Chaque onglet reprend
   la meilleure implémentation existante : le graphe garde la recherche
   et les tableaux filtrables de Knowledge Graph, Alexandrie garde la
   bannière « service injoignable » et la gestion d'erreur de synchro
   d'Alexandrie Center.
   ═══════════════════════════════════════════════════════════════════ */

type Tab = "memory" | "graph" | "alexandrie";

/** The headline number for one memory store.
 *
 *  Each store reports a different shape: `{total}`, `{total_documents}`,
 *  `{total_procedures}`, `{total_nodes}` or `{active_memories, ...}`. Prefer an
 *  explicit total, else fall back to the first numeric field, else 0 — never
 *  return the object itself, which is what crashed this Center.
 */
function headlineCount(value: unknown): number {
  if (typeof value === "number") return value;
  if (!value || typeof value !== "object") return 0;
  const o = value as Record<string, unknown>;
  for (const key of ["total", "total_documents", "total_procedures",
                     "total_nodes", "active_memories", "count"]) {
    if (typeof o[key] === "number") return o[key] as number;
  }
  const first = Object.values(o).find((v) => typeof v === "number");
  return typeof first === "number" ? first : 0;
}

export function MemoryCenter() {
  const [tab, setTab] = useState<Tab>("memory");

  // ── Mémoire ──
  const [query, setQuery] = useState("");
  const { data: results, isLoading: searching } = useMemorySearch(query);
  const { data: experiences } = useExperiences();
  const { data: stats } = useMemoryStatistics();

  // ── Graphe ──
  const memGraph = useKnowledgeGraph();
  const [nodeSearch, setNodeSearch] = useState("");
  const [nodeFilter, setNodeFilter] = useState("Tous");

  // ── Alexandrie ──
  const alexHealth = useAlexandrieHealth();
  const alexStatus = useAlexandrieStatus();
  const alexDocs = useAlexandrieDocuments();
  const alexGraph = useAlexandrieGraph();
  const alexHistory = useAlexandrieSyncHistory();
  const alexSync = useAlexandrieSync();
  const [alexQuery, setAlexQuery] = useState("");
  const [docSearch, setDocSearch] = useState("");
  const [syncError, setSyncError] = useState<string | null>(null);
  const alexResults = useAlexandrieSearch(alexQuery);

  const nodes = memGraph.data?.nodes ?? [];
  const edges = memGraph.data?.edges ?? [];
  const nodeTypes = useMemo(() => {
    const set = new Set(nodes.map((n) => n.type).filter(Boolean));
    return ["Tous", ...Array.from(set).slice(0, 6)];
  }, [nodes]);

  const visibleNodes = nodes.filter((n) => {
    const hay = `${n.label ?? ""} ${n.id} ${n.type ?? ""}`.toLowerCase();
    if (nodeSearch && !hay.includes(nodeSearch.toLowerCase())) return false;
    return nodeFilter === "Tous" || n.type === nodeFilter;
  });

  const alexEdges = (alexGraph.data?.edges ?? []) as Record<string, unknown>[];
  const docs = alexDocs.data?.documents ?? [];
  const visibleDocs = docs.filter(
    (d) => !docSearch || JSON.stringify(d).toLowerCase().includes(docSearch.toLowerCase()),
  );
  const alexOffline = alexHealth.data && !alexHealth.data.healthy;

  return (
    <div className="animate-fade-in">
      <CenterHeader
        title="Memory Center"
        subtitle="Mémoire unifiée, graphe de connaissances et corpus Alexandrie"
        right={
          alexHealth.isLoading ? (
            <Badge>Vérification…</Badge>
          ) : (
            <Badge variant={alexHealth.data?.healthy ? "success" : "danger"}>
              {alexHealth.data?.healthy && <Beacon tone="green" />}
              Alexandrie {alexHealth.data?.healthy ? "connectée" : "hors ligne"}
            </Badge>
          )
        }
      />

      <CenterTabs
        active={tab}
        onChange={setTab}
        tabs={[
          { id: "memory", label: "Mémoire" },
          {
            id: "graph",
            label: "Graphe",
            badge: nodes.length > 0 ? <Badge>{nodes.length}</Badge> : null,
          },
          {
            id: "alexandrie",
            label: "Alexandrie",
            badge: docs.length > 0 ? <Badge>{docs.length}</Badge> : null,
          },
        ]}
      />

      {/* ═══ MÉMOIRE ═══════════════════════════════════════════════ */}
      {tab === "memory" && (
        <>
          {/* /api/v1/memory/statistics renvoie un objet imbriqué par magasin —
              working: {active_memories, …}, episodic: {total, …}. Ce panneau
              rendait `val` directement, ce qui lève « Objects are not valid as
              a React child » et, l'erreur s'échappant du Center, blanchissait
              tout le Cockpit (R-004). Chaque tuile montre le compte principal. */}
          {stats && (
            <StatGrid
              columns={5}
              stats={Object.entries(stats)
                .slice(0, 5)
                .map(([key, val]) => ({ label: key, value: headlineCount(val) }))}
            />
          )}

          <Toolbar
            search={query}
            onSearch={setQuery}
            placeholder="Recherche hybride en mémoire (graphe + embeddings + mots-clés)…"
          />

          {query && (
            <div className="mb-4">
              <AsyncPanel
                title="Résultats de recherche"
                subtitle={`requête : ${query}`}
                isLoading={searching}
                isError={false}
                isEmpty={!results || results.length === 0}
                emptyLabel="Aucun résultat pour cette requête."
              >
                <div className="flex flex-col gap-2 max-h-[320px] overflow-y-auto">
                  {results?.map((r, i) => (
                    <div
                      key={i}
                      className="flex items-start gap-3 p-3 rounded-lg bg-hermes-bg-deep/50
                        border border-hermes-border/50 hover:border-hermes-cyan/30 transition-colors"
                    >
                      <Badge
                        variant={r.score > 0.7 ? "success" : r.score > 0.4 ? "warning" : "default"}
                      >
                        {(r.score * 100).toFixed(0)}%
                      </Badge>
                      <div className="flex-1 min-w-0">
                        <div className="text-[12px] text-hermes-text truncate">
                          {r.entry?.content?.slice(0, 140) || "—"}
                        </div>
                        {r.justification && (
                          <div className="text-[10px] text-hermes-dim mt-1">{r.justification}</div>
                        )}
                      </div>
                      {r.entry?.type && <Badge>{r.entry.type}</Badge>}
                    </div>
                  ))}
                </div>
              </AsyncPanel>
            </div>
          )}

          <AsyncPanel
            title="Expériences"
            subtitle={`${experiences?.length ?? 0} leçon(s) retenue(s) — /api/v1/memory/experiences`}
            isLoading={!experiences}
            isError={false}
            isEmpty={!experiences || experiences.length === 0}
            emptyLabel="Aucune expérience enregistrée : aucune mission n'a encore produit de leçon."
          >
            <div className="grid grid-cols-2 gap-2 max-h-[380px] overflow-y-auto">
              {experiences?.slice(0, 20).map((exp) => (
                <ExperienceCard key={exp.id} experience={exp} />
              ))}
            </div>
          </AsyncPanel>
        </>
      )}

      {/* ═══ GRAPHE ════════════════════════════════════════════════ */}
      {tab === "graph" && (
        <>
          <StatGrid
            columns={4}
            stats={[
              { label: "Nœuds mémoire", value: nodes.length },
              { label: "Arêtes mémoire", value: edges.length },
              { label: "Arêtes Alexandrie", value: alexEdges.length },
              { label: "Types distincts", value: Math.max(nodeTypes.length - 1, 0) },
            ]}
          />

          <Toolbar
            search={nodeSearch}
            onSearch={setNodeSearch}
            placeholder="Rechercher un nœud par libellé, identifiant ou type…"
            filters={nodeTypes}
            activeFilter={nodeFilter}
            onFilter={setNodeFilter}
          />

          <AsyncPanel
            title="Nœuds du graphe de mémoire"
            subtitle={`${visibleNodes.length} affiché(s) sur ${nodes.length} — /api/v1/memory/graph`}
            isLoading={memGraph.isLoading}
            isError={memGraph.isError}
            error={memGraph.error}
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
              isLoading={memGraph.isLoading}
              isError={memGraph.isError}
              error={memGraph.error}
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
              title="Graphe documentaire Alexandrie"
              subtitle="/api/v1/alexandrie/graph"
              isLoading={alexGraph.isLoading}
              isError={alexGraph.isError}
              error={alexGraph.error}
              isEmpty={alexEdges.length === 0}
              emptyLabel="Aucune arête documentaire : Alexandrie n'a pas encore indexé de corpus."
            >
              <DataTable
                rows={alexEdges.slice(0, 100)}
                rowKey={(_e, i) => String(i)}
                columns={[{ header: "Arête", cell: (e) => JSON.stringify(e).slice(0, 80) }]}
              />
            </AsyncPanel>
          </div>
        </>
      )}

      {/* ═══ ALEXANDRIE ════════════════════════════════════════════ */}
      {tab === "alexandrie" && (
        <>
          {alexOffline && (
            <div className="mb-4 flex items-start gap-2.5 px-3 py-2.5 rounded-lg glass border border-hermes-red/40">
              <span className="text-hermes-red text-glow-red font-mono">⚠</span>
              <div className="text-[11px] font-mono text-hermes-text">
                Alexandrie est injoignable —{" "}
                <span className="text-hermes-muted">
                  {String(alexHealth.data?.error ?? "aucun détail").slice(0, 160)}
                </span>
                . Les compteurs ci-dessous sont vides parce que le service ne répond
                pas, pas parce que le corpus est vide.
              </div>
            </div>
          )}

          <StatGrid
            columns={5}
            stats={[
              { label: "Documents", value: alexDocs.data?.total ?? 0 },
              { label: "Synchronisés", value: alexStatus.data?.documents_synced ?? 0 },
              { label: "Indexés", value: alexStatus.data?.documents_indexed ?? 0 },
              { label: "Arêtes", value: alexEdges.length },
              {
                label: "Service",
                value: alexHealth.data?.healthy ? "en ligne" : "hors ligne",
                tone: alexHealth.data?.healthy ? "ok" : "bad",
              },
            ]}
          />

          <Toolbar
            search={docSearch}
            onSearch={setDocSearch}
            placeholder="Filtrer les documents chargés…"
            actions={
              <Button
                variant="primary"
                onClick={() => {
                  setSyncError(null);
                  alexSync.mutate(
                    { incremental: true },
                    {
                      onError: (e) =>
                        setSyncError(
                          e instanceof Error ? e.message : "Synchronisation refusée",
                        ),
                    },
                  );
                }}
                disabled={alexSync.isPending}
              >
                {alexSync.isPending ? "Synchronisation…" : "Synchroniser"}
              </Button>
            }
          />

          {syncError && (
            <div className="mb-3 flex items-start gap-2 px-3 py-2 rounded-lg glass border border-hermes-red/40">
              <span className="text-hermes-red text-glow-red font-mono">⚠</span>
              <span className="text-hermes-red text-[11px] font-mono">{syncError}</span>
            </div>
          )}

          <div className="mb-4">
            <input
              type="text"
              value={alexQuery}
              onChange={(e) => setAlexQuery(e.target.value)}
              placeholder="Recherche hybride dans le corpus (Alexandrie + Hermes)…"
              className="w-full glass rounded-lg border border-hermes-border px-3 py-2 text-sm
                text-hermes-text font-mono placeholder:text-hermes-dim
                focus:outline-none focus:border-hermes-cyan/60 focus:shadow-glow-cyan transition-all"
            />
          </div>

          {alexQuery && (
            <div className="mb-4">
              <AsyncPanel
                title="Résultats de recherche"
                subtitle={`requête : ${alexQuery}`}
                isLoading={alexResults.isLoading}
                isError={alexResults.isError}
                error={alexResults.error}
                isEmpty={(alexResults.data?.results ?? []).length === 0}
                emptyLabel="Aucun résultat pour cette requête."
              >
                <div className="flex flex-col gap-2 max-h-[260px] overflow-y-auto">
                  {(alexResults.data?.results ?? []).slice(0, 12).map((r, i) => (
                    <div
                      key={i}
                      className="flex items-start gap-2.5 p-2.5 rounded-lg bg-hermes-bg-deep/50
                        border border-hermes-border/50"
                    >
                      <Badge variant={r.source === "alexandrie" ? "info" : "warning"}>
                        {r.source}
                      </Badge>
                      <div className="flex-1 min-w-0">
                        <div className="text-[12px] text-hermes-text truncate">{r.title}</div>
                        <div className="text-[10px] text-hermes-dim mt-0.5 line-clamp-2">
                          {r.content?.slice(0, 150)}
                        </div>
                      </div>
                      <span className="text-[10px] text-hermes-cyan font-mono shrink-0">
                        {(r.score * 100).toFixed(0)}%
                      </span>
                    </div>
                  ))}
                </div>
              </AsyncPanel>
            </div>
          )}

          <AsyncPanel
            title="Documents"
            subtitle={`${visibleDocs.length} affiché(s) sur ${docs.length}`}
            isLoading={alexDocs.isLoading}
            isError={alexDocs.isError}
            error={alexDocs.error}
            isEmpty={visibleDocs.length === 0}
            emptyLabel={
              alexOffline
                ? "Service injoignable : impossible de lister le corpus."
                : "Aucun document indexé. Lancez une synchronisation."
            }
          >
            <DataTable
              rows={visibleDocs.slice(0, 100)}
              rowKey={(d, i) => (d as { id?: string }).id ?? String(i)}
              columns={[
                { header: "Titre", cell: (d) => (d as { title?: string }).title ?? "—" },
                {
                  header: "Identifiant",
                  cell: (d) => (
                    <span className="text-hermes-muted">
                      {String((d as { id?: string }).id ?? "—").slice(0, 24)}
                    </span>
                  ),
                },
              ]}
            />
          </AsyncPanel>

          <div className="mt-4">
            <AsyncPanel
              title="Historique de synchronisation"
              subtitle={
                alexStatus.data?.last_sync_at
                  ? `dernière : ${new Date(alexStatus.data.last_sync_at).toLocaleString()}`
                  : "/api/v1/alexandrie/sync/history"
              }
              isLoading={alexHistory.isLoading}
              isError={alexHistory.isError}
              error={alexHistory.error}
              isEmpty={(alexHistory.data?.events ?? []).length === 0}
              emptyLabel="Aucune synchronisation enregistrée."
            >
              <div className="flex flex-col gap-1 max-h-[240px] overflow-y-auto">
                {(alexHistory.data?.events ?? []).slice(0, 30).map((evt, i) => (
                  <div key={i} className="flex items-center gap-2 text-[10px] font-mono py-1">
                    <span className="text-hermes-dim w-16 shrink-0">
                      {evt.timestamp ? new Date(evt.timestamp).toLocaleTimeString() : "—"}
                    </span>
                    <Badge
                      variant={
                        evt.status === "synced" ? "success"
                        : evt.status === "failed" ? "danger"
                        : "default"
                      }
                    >
                      {evt.status}
                    </Badge>
                    <span className="text-hermes-text truncate">{evt.type}</span>
                  </div>
                ))}
              </div>
            </AsyncPanel>
          </div>
        </>
      )}
    </div>
  );
}

/* ── Sous-composants ────────────────────────────────────────────── */

function ExperienceCard({ experience }: { experience: Experience }) {
  return (
    <div
      className="p-3 rounded-lg bg-hermes-bg-deep/50 border border-hermes-border/50
        hover:border-hermes-cyan/30 transition-colors"
    >
      <div className="flex items-center gap-2 mb-1.5">
        <Badge variant={experience.success ? "success" : "danger"}>
          {experience.success ? "SUCCÈS" : "ÉCHEC"}
        </Badge>
        <span className="text-[10px] text-hermes-dim font-mono truncate flex-1">
          {experience.pattern}
        </span>
        <Badge>{(experience.confidence * 100).toFixed(0)}%</Badge>
      </div>
      <ul className="text-[10px] text-hermes-muted list-disc list-inside space-y-0.5">
        {experience.learnings?.slice(0, 3).map((l, i) => (
          <li key={i} className="truncate">{l}</li>
        ))}
      </ul>
    </div>
  );
}
