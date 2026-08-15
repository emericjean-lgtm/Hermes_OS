"use client";

import { useMissionGraph } from "@/hooks/use-api";
import { Badge, Card } from "@/components/ui/card";

/**
 * La décomposition réelle d'une mission, pas son compteur.
 *
 * Le Center annonçait « Nœuds : 0/7 » et rien d'autre : combien, jamais
 * *lesquelles*. Le DAG était pourtant construit côté backend et exposé
 * entièrement par `GET /missions/{id}/graph` — statuts, dépendances,
 * durées mesurées, ordre topologique, vagues parallèles. Il ne manquait
 * que l'écran (HOS-116).
 *
 * Ce qui est affiché vient de ce que l'exécuteur a **constaté**, jamais
 * estimé : `duration_ms` est écrit après exécution, et `runtime` est le
 * runtime qui a réellement servi le nœud, pas celui qu'on avait prévu.
 * Un nœud à 0 ms n'a pas tourné — la distinction que la vue précédente
 * était incapable de faire.
 */
const ETATS: Record<string, { libelle: string; variant?: "danger" | "default" }> = {
  completed: { libelle: "terminé" },
  running: { libelle: "en cours" },
  failed: { libelle: "échoué", variant: "danger" },
  pending: { libelle: "en attente" },
  blocked: { libelle: "bloqué", variant: "danger" },
  skipped: { libelle: "ignoré" },
};

export function DecompositionPanel({ missionId }: { missionId: string | null }) {
  const graph = useMissionGraph(missionId);
  const noeuds = graph.data?.nodes ?? [];
  const vagues = graph.data?.parallel_groups ?? [];

  if (!missionId) return null;

  return (
    <Card
      title="Décomposition"
      subtitle={
        noeuds.length
          ? `${noeuds.length} nœud(s)${vagues.length ? ` · ${vagues.length} vague(s) parallèle(s)` : ""}`
          : "Aucun nœud"
      }
    >
      {graph.isLoading && (
        <p className="text-[10px] text-hermes-muted font-mono">Chargement du graphe…</p>
      )}

      {graph.isError && (
        <p className="text-[10px] text-hermes-danger font-mono">
          Graphe indisponible : {String(graph.error)}
        </p>
      )}

      {!graph.isLoading && !graph.isError && noeuds.length === 0 && (
        <p className="text-[10px] text-hermes-muted font-mono">
          Cette mission n&apos;a pas encore été décomposée.
        </p>
      )}

      <div className="flex flex-col gap-1.5">
        {noeuds.map((n, i) => {
          const etat = ETATS[n.status] ?? { libelle: n.status };
          return (
            <div
              key={n.id}
              className="bg-hermes-bg rounded border border-hermes-border/40 p-2"
            >
              <div className="flex items-start justify-between gap-2">
                <span className="text-[10px] font-mono text-hermes-text">
                  <span className="text-hermes-muted">{String(i + 1).padStart(2, "0")}</span>{" "}
                  {n.title}
                </span>
                <Badge variant={etat.variant}>{etat.libelle}</Badge>
              </div>

              <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1 text-[9px] font-mono text-hermes-muted">
                {/* 0 ms veut dire « n'a pas tourné », pas « instantané ». */}
                <span>
                  {n.duration_ms > 0 ? `${n.duration_ms.toFixed(0)} ms` : "jamais exécuté"}
                </span>
                {n.runtime && <span>servi par {n.runtime}</span>}
                {n.depends_on.length > 0 && (
                  <span>dépend de {n.depends_on.join(", ")}</span>
                )}
              </div>

              {n.result_summary && (
                <p className="text-[9px] text-hermes-muted mt-1 line-clamp-2">
                  {n.result_summary}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}
