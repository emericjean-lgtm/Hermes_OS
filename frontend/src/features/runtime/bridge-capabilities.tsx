/**
 * Ce que le cerveau agentique sait reellement faire (HOS-265).
 *
 * Pas un panneau de diagnostic : la reponse a une question que l'operateur
 * se pose vraiment avant de lancer une mission — « est-ce que ce runtime
 * peut steerer, deleguer, approuver ? ». Chaque ligne est une **mesure**
 * prise contre le gateway JSON-RPC de Hermes Agent, jamais une deduction
 * a partir d'un numero de version.
 *
 * Les absences comptent autant que les presences, et sont affichees comme
 * telles : `fork` et `memory` n'existent pas sous ces noms dans la v0.21.0,
 * et `delegation` sait piloter un subagent sans savoir en lancer un. Un
 * panneau qui montrerait tout en vert mentirait exactement la ou ce pont
 * est cense dire la verite.
 */
import { motion } from "framer-motion";
import { Card, Badge, Button } from "@/components/ui/card";
import { PanelLoading } from "@/components/center-scaffold";
import { useBridgeCapabilities, useRefreshBridgeCapabilities } from "@/hooks/use-api";
import type { BridgeCapabilityDTO } from "@/services/client";
import { Plug, RefreshCw } from "lucide-react";

/** COMPLETE / PARTIELLE / ABSENTE — trois etats, pas deux. */
function etatDe(c: BridgeCapabilityDTO): {
  libelle: string;
  ton: "success" | "warning" | "danger";
} {
  if (c.complete) return { libelle: "complète", ton: "success" };
  if (c.disponible) return { libelle: "partielle", ton: "warning" };
  return { libelle: "absente", ton: "danger" };
}

export function BridgeCapabilities() {
  const { data, isLoading, isError, error } = useBridgeCapabilities();
  const refresh = useRefreshBridgeCapabilities();

  if (isLoading) {
    return (
      <Card title="Capacités du cerveau agentique">
        <PanelLoading />
      </Card>
    );
  }

  if (isError) {
    return (
      <Card title="Capacités du cerveau agentique">
        <div className="flex items-start gap-2.5 py-4">
          <span className="text-hermes-red text-glow-red font-mono text-sm">⚠</span>
          <div className="text-[11px] text-hermes-muted font-mono break-all">
            {error instanceof Error ? error.message : "Endpoint injoignable"}
          </div>
        </div>
      </Card>
    );
  }

  // Une negociation qui a echoue n'est pas un runtime sans capacite : le
  // distinguer est tout l'interet du champ `negociee`.
  if (data && !data.negociee) {
    return (
      <Card title="Capacités du cerveau agentique">
        <div className="py-4 space-y-2">
          <div className="text-[11px] text-hermes-amber font-mono">
            Négociation impossible — le gateway n'a pas répondu.
          </div>
          <div className="text-[11px] text-hermes-muted font-mono break-all">
            {data.erreur ?? "cause inconnue"}
          </div>
          <div className="text-[10px] text-hermes-dim font-mono">
            Ce n'est pas « aucune capacité » : c'est une panne, et rien n'est
            mesuré tant qu'elle dure.
          </div>
        </div>
      </Card>
    );
  }

  const capacites = data?.capacites ?? [];
  const completes = capacites.filter((c) => c.complete).length;

  return (
    <Card title="Capacités du cerveau agentique">
      <div className="flex items-center justify-between gap-3 pb-3">
        <div className="flex items-center gap-2 min-w-0">
          <Plug className="w-3.5 h-3.5 text-hermes-cyan shrink-0" />
          <span className="text-[11px] font-mono text-hermes-muted truncate">
            Hermes Agent {data?.version ?? "?"}
            <span className="text-hermes-dim"> · {data?.commit ?? "?"}</span>
          </span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[11px] font-mono text-hermes-muted tabular-nums">
            {completes}/{capacites.length} complètes
          </span>
          <Button
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending}
            aria-label="Re-négocier les capacités"
          >
            <RefreshCw
              className={`w-3 h-3 ${refresh.isPending ? "animate-spin" : ""}`}
            />
            {refresh.isPending ? "Négociation…" : "Re-négocier"}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        {capacites.map((c, i) => {
          const etat = etatDe(c);
          return (
            <motion.div
              key={c.nom}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: Math.min(i * 0.02, 0.3) }}
              className="flex items-start justify-between gap-2 rounded border border-hermes-border/60 px-2.5 py-2"
            >
              <div className="min-w-0">
                <div className="text-[11px] font-mono text-hermes-text">{c.nom}</div>
                {c.methodes_absentes.length > 0 && (
                  <div
                    className="text-[10px] font-mono text-hermes-dim truncate"
                    title={c.methodes_absentes.join(", ")}
                  >
                    manque : {c.methodes_absentes.join(", ")}
                  </div>
                )}
              </div>
              <Badge variant={etat.ton}>{etat.libelle}</Badge>
            </motion.div>
          );
        })}
      </div>
    </Card>
  );
}
