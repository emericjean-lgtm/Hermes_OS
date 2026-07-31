"use client";

import { useState } from "react";
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
import { Card, Badge } from "@/components/ui/card";
import type { SearchResult, Experience, KnowledgeNode, AlexandrieMergeResult } from "@/types/hermes";

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
  const [query, setQuery] = useState("");
  const [alexQuery, setAlexQuery] = useState("");
  const { data: results } = useMemorySearch(query);
  const { data: graph } = useKnowledgeGraph();
  const { data: experiences } = useExperiences();
  const { data: stats } = useMemoryStatistics();

  // Alexandrie
  const { data: alexStatus } = useAlexandrieStatus();
  const { data: alexHealth } = useAlexandrieHealth();
  const { data: alexSearchResults } = useAlexandrieSearch(alexQuery);
  const { data: alexSyncHistory } = useAlexandrieSyncHistory();
  const { data: alexDocuments } = useAlexandrieDocuments();
  const { data: alexGraph } = useAlexandrieGraph();
  const alexSync = useAlexandrieSync();

  return (
    <div className="animate-fade-in">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-hermes-text font-mono tracking-tight">
            Memory Center
          </h1>
          <p className="text-xs text-hermes-muted mt-1">
            Unified memory, knowledge graph & retrieval
          </p>
        </div>
      </div>

      {/* Stats.
          /api/v1/memory/statistics returns one nested object per store —
          working: {active_memories, active_missions}, episodic: {total, ...},
          semantic: {total, categories}, and so on. This rendered `val`
          directly, which throws "Objects are not valid as a React child" and,
          because the crash escaped the Center, blanked the whole Cockpit
          (R-004). Each tile now shows that store's headline count. */}
      {stats && (
        <div className="grid grid-cols-5 gap-3 mb-6">
          {Object.entries(stats).slice(0, 5).map(([key, val]) => (
            <div key={key} className="bg-hermes-card border border-hermes-border rounded-lg p-3 text-center">
              <div className="text-xl font-bold font-mono text-hermes-amber-bright">
                {headlineCount(val)}
              </div>
              <div className="text-[10px] text-hermes-muted font-mono uppercase">{key}</div>
            </div>
          ))}
        </div>
      )}

      {/* Search */}
      <div className="mb-6">
        <div className="relative">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search memory (hybrid: graph + embeddings + keyword)..."
            className="w-full bg-hermes-card border border-hermes-border rounded-lg px-4 py-3 text-sm text-hermes-text font-mono focus:border-hermes-amber outline-none placeholder:text-hermes-muted"
          />
        </div>

        {results && results.length > 0 && (
          <div className="mt-3 flex flex-col gap-2 max-h-[300px] overflow-y-auto">
            {results.map((r, i) => (
              <div key={i} className="bg-hermes-card border border-hermes-border rounded-lg p-3 flex items-start gap-3">
                <Badge variant={r.score > 0.7 ? "success" : r.score > 0.4 ? "warning" : "default"}>
                  {(r.score * 100).toFixed(0)}%
                </Badge>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-hermes-text truncate">
                    {r.entry?.content?.slice(0, 120) || "—"}
                  </div>
                  <div className="text-[10px] text-hermes-muted mt-1">
                    {r.justification}
                  </div>
                </div>
                <Badge>{r.entry?.type}</Badge>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Knowledge Graph */}
        <Card title="Knowledge Graph" subtitle={graph ? `${graph.nodes.length} nodes, ${graph.edges.length} edges` : "Loading..."}>
          {graph ? (
            <div className="h-[250px] overflow-y-auto">
              <div className="flex flex-wrap gap-2">
                {graph.nodes.slice(0, 30).map((node) => (
                  <NodeChip key={node.id} node={node} />
                ))}
              </div>
              {graph.nodes.length > 30 && (
                <p className="text-[10px] text-hermes-muted mt-2 text-center">
                  +{graph.nodes.length - 30} more nodes
                </p>
              )}
            </div>
          ) : (
            <div className="flex items-center justify-center h-[250px] text-xs text-hermes-muted">
              No graph data
            </div>
          )}
        </Card>

        {/* Experiences */}
        <Card title="Experiences" subtitle={experiences ? `${experiences.length} lessons learned` : "Loading..."}>
          <div className="flex flex-col gap-2 max-h-[250px] overflow-y-auto">
            {experiences?.slice(0, 10).map((exp) => (
              <ExperienceCard key={exp.id} experience={exp} />
            ))}
          </div>
        </Card>
      </div>

      {/* Alexandrie Integration */}
      <div className="mt-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-bold text-hermes-text font-mono tracking-tight">
              📚 Alexandrie Document Integration
            </h2>
            {alexHealth && (
              <Badge variant={alexHealth.healthy ? "success" : "warning"}>
                {alexHealth.healthy ? "CONNECTED" : "OFFLINE"}
              </Badge>
            )}
          </div>
          <button
            onClick={() => alexSync.mutate({ incremental: true })}
            disabled={alexSync.isPending}
            className="px-3 py-1.5 text-[11px] font-mono bg-hermes-amber/10 text-hermes-amber-bright border border-hermes-amber/30 rounded-md hover:bg-hermes-amber/20 transition-colors disabled:opacity-50"
          >
            {alexSync.isPending ? "Syncing..." : "Sync Now"}
          </button>
        </div>

        {/* Alexandrie Status Cards */}
        {alexStatus && (
          <div className="grid grid-cols-5 gap-3 mb-4">
            <StatusCard label="Synced" value={alexStatus.documents_synced} />
            <StatusCard label="Indexed" value={alexStatus.documents_indexed} />
            <StatusCard label="Graph Edges" value={alexStatus.graph_edges} />
            <StatusCard label="Cache" value={`${alexStatus.cache?.entries || 0}`} />
            <StatusCard label="Circuit" value={alexStatus.circuit_breaker?.open ? "OPEN" : "CLOSED"} state={alexStatus.circuit_breaker?.open ? "warning" : "success"} />
          </div>
        )}

        <div className="grid grid-cols-2 gap-4">
          {/* Alexandrie Hybrid Search */}
          <Card title="Hybrid Search (Alexandrie + Hermes)" subtitle={alexSearchResults ? `${alexSearchResults.total} results` : "Enter a query"}>
            <div className="mb-3">
              <input
                type="text"
                value={alexQuery}
                onChange={(e) => setAlexQuery(e.target.value)}
                placeholder="Search documents across Alexandrie & Hermes..."
                className="w-full bg-hermes-bg border border-hermes-border rounded-md px-3 py-2 text-xs text-hermes-text font-mono focus:border-hermes-amber outline-none placeholder:text-hermes-muted"
              />
            </div>
            {alexSearchResults?.results && alexSearchResults.results.length > 0 && (
              <div className="flex flex-col gap-2 max-h-[200px] overflow-y-auto">
                {alexSearchResults.results.slice(0, 8).map((r, i) => (
                  <div key={i} className="bg-hermes-bg rounded-md p-2 border border-hermes-border/50 flex items-start gap-2">
                    <Badge variant={r.source === "alexandrie" ? "default" : "warning"}>
                      {r.source}
                    </Badge>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium text-hermes-text truncate">{r.title}</div>
                      <div className="text-[10px] text-hermes-muted mt-0.5 line-clamp-2">{r.content.slice(0, 150)}</div>
                    </div>
                    <span className="text-[10px] text-hermes-amber font-mono">{(r.score * 100).toFixed(0)}%</span>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* Alexandrie Sync History */}
          <Card title="Sync History" subtitle={alexStatus?.last_sync_at ? `Last: ${new Date(alexStatus.last_sync_at).toLocaleString()}` : "No sync yet"}>
            <div className="flex flex-col gap-1.5 max-h-[200px] overflow-y-auto">
              {alexSyncHistory?.events?.slice(0, 10).map((evt, i) => (
                <div key={i} className="flex items-center gap-2 text-[10px] font-mono">
                  <span className="text-hermes-muted w-16 shrink-0">
                    {new Date(evt.timestamp).toLocaleTimeString()}
                  </span>
                  <Badge variant={evt.status === "synced" ? "success" : evt.status === "failed" ? "danger" : "default"}>
                    {evt.status}
                  </Badge>
                  <span className="text-hermes-text truncate">{evt.type}</span>
                </div>
              ))}
              {(!alexSyncHistory?.events || alexSyncHistory.events.length === 0) && (
                <div className="text-[10px] text-hermes-muted text-center py-4">No sync events yet</div>
              )}
            </div>
          </Card>
        </div>

        {/* Alexandrie Document Graph */}
        {alexGraph && alexGraph.total > 0 && (
          <div className="mt-4">
            <Card title="Document Relations" subtitle={`${alexGraph.total} edges`}>
              <div className="flex flex-wrap gap-1.5 max-h-[100px] overflow-y-auto">
                {alexGraph.edges.slice(0, 20).map((edge, i) => (
                  <span key={i} className="px-2 py-0.5 rounded text-[10px] font-mono bg-hermes-bg border border-hermes-border/50 text-hermes-muted">
                    {edge.relation}: {edge.source.slice(0, 12)}→{edge.target.slice(0, 12)}
                  </span>
                ))}
              </div>
            </Card>
          </div>
        )}

        {/* Synced Documents List */}
        {alexDocuments && alexDocuments.total > 0 && (
          <div className="mt-4">
            <Card title={`Synced Documents (${alexDocuments.total})`} subtitle="From Alexandrie">
              <div className="flex flex-wrap gap-1.5 max-h-[80px] overflow-y-auto">
                {alexDocuments.documents.slice(0, 15).map((doc) => (
                  <span key={doc.id} className="px-2 py-0.5 rounded text-[10px] font-mono bg-hermes-amber/10 border border-hermes-amber/20 text-hermes-amber-bright">
                    {doc.title.slice(0, 40)}
                  </span>
                ))}
              </div>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}

function StatusCard({ label, value, state }: { label: string; value: string | number; state?: "success" | "warning" | "danger" }) {
  const colors = {
    success: "text-hermes-green",
    warning: "text-hermes-amber-bright",
    danger: "text-hermes-red",
  };
  const textColor = state ? colors[state] : "text-hermes-amber-bright";
  return (
    <div className="bg-hermes-card border border-hermes-border rounded-lg p-3 text-center">
      <div className={`text-xl font-bold font-mono ${textColor}`}>{value}</div>
      <div className="text-[10px] text-hermes-muted font-mono uppercase">{label}</div>
    </div>
  );
}

function NodeChip({ node }: { node: KnowledgeNode }) {
  const colors: Record<string, string> = {
    MISSION: "bg-hermes-purple/20 border-hermes-purple/30 text-hermes-purple",
    AGENT: "bg-hermes-blue/20 border-hermes-blue/30 text-hermes-blue",
    RUNTIME: "bg-hermes-green/20 border-hermes-green/30 text-hermes-green",
    SKILL: "bg-hermes-amber/20 border-hermes-amber/30 text-hermes-amber",
    TOOL: "bg-hermes-red/20 border-hermes-red/30 text-hermes-red",
  };

  return (
    <span className={`px-2 py-1 rounded text-[10px] font-mono border ${colors[node.type] || "bg-hermes-border/20 border-hermes-border text-hermes-muted"}`}>
      {node.label.slice(0, 30)}
    </span>
  );
}

function ExperienceCard({ experience }: { experience: Experience }) {
  return (
    <div className="bg-hermes-bg rounded-lg p-3 border border-hermes-border/50">
      <div className="flex items-center gap-2 mb-1">
        <Badge variant={experience.success ? "success" : "danger"}>
          {experience.success ? "SUCCESS" : "FAILURE"}
        </Badge>
        <span className="text-[10px] text-hermes-muted font-mono">
          {experience.pattern}
        </span>
        <Badge>{(experience.confidence * 100).toFixed(0)}%</Badge>
      </div>
      <ul className="text-[10px] text-hermes-muted list-disc list-inside">
        {experience.learnings?.slice(0, 3).map((l, i) => (
          <li key={i}>{l}</li>
        ))}
      </ul>
    </div>
  );
}
