"use client";

import React, { useState } from "react";
import {
  useCloudStatus,
  useModelBenchmarks,
  useModelCatalogue,
  useModelHistory,
  useModelIntelligence,
  useModelOptimize,
  useModelRanking,
  useMonitoringResources,
  useRecommendModel,
  useRunBenchmark,
} from "@/hooks/use-api";
import { CenterHeader } from "@/components/center-scaffold";
import { Badge, Card } from "@/components/ui/card";
import { ComparaisonRadar } from "./comparaison-radar";
import type { BenchAxisDTO } from "@/services/client";
import type { ResourceStatus } from "@/types/hermes";
import { formatGio, formatGioPair, vramLibre, vramOccupee, vramPourcent } from "@/lib/format";

// Every figure in this Center used to come from two module-level constants.
// MOCK_MODELS listed five models with invented scores and success rates;
// MOCK_DECISIONS held two hand-written routing decisions; "Recommend" slept a
// random 600–1000 ms (`setTimeout(r, 600 + Math.random() * 400)`) and returned
// MOCK_DECISIONS[0]; "Run Full Benchmark" slept 1500 ms and did nothing; and the
// Optimizer tab was static text ("Qwen3-Coder 30B", "16,200 MB VRAM", "0.87",
// "Top 1 of 12 configurations"). /api/v1/models, /models/ranking and
// /models/recommend served real data throughout (R-002 P3).
//
// HOS-071 audit/rebuild: /models/recommend's own payload key never matched
// what this Center sent ("description" vs. the route's "task_description"),
// so every real click silently recommended for an empty string — fixed at
// the route (accepts both) and here (sends the documented key). The
// Benchmark tab dumped raw JSON and the Optimizer tab only restated the
// top-ranked model's own numbers without ever calling the real
// ModelRuntimeOptimizer/ModelRuntimeAdapter — both now real: a real
// trigger + stored-results table, and a real cross-runtime/quantization
// comparison via the new GET /models/optimize.

const TASK_TYPES = [
  "code_generation", "code_review", "debug", "refactor", "analysis",
  "chat", "documentation", "optimization", "reasoning", "general",
] as const;

const TABS = ["catalogue", "ranking", "recommend", "benchmark", "optimizer", "history"] as const;

const TAB_LABELS: Record<(typeof TABS)[number], string> = {
  catalogue: "Catalogue mesuré",
  ranking: "Classement",
  recommend: "Recommander",
  benchmark: "Benchmark",
  optimizer: "Optimiseur",
  history: "Historique",
};

const AXIS_LABELS: Record<string, string> = {
  capacite: "Capacité",
  code: "Code",
  raisonnement: "Raisonnement",
  agentique: "Agentique",
  extraction: "Extraction",
  vision: "Vision",
  long_contexte: "Long contexte",
};

/** Une note sur 100 devient une couleur — mais `null` n'en reçoit aucune.
 *  « Non mesuré » et « zéro » doivent rester distincts partout : un modèle
 *  jamais soumis à un axe passerait sinon pour mauvais sur cet axe. */
export function noteColor(note: number | null | undefined): string {
  if (note == null) return "text-hermes-muted";
  if (note >= 80) return "text-hermes-green";
  if (note >= 50) return "text-hermes-cyan";
  if (note >= 25) return "text-hermes-amber";
  return "text-hermes-red";
}

function formatMeasuredAt(epoch: number): string {
  if (!epoch) return "—";
  return new Date(epoch * 1000).toLocaleDateString("fr-FR", {
    day: "2-digit", month: "2-digit", year: "numeric",
  });
}

type Ligne = { cle: string; ok?: boolean; nom: string; note?: string; duree?: number };

/** Ramener une entrée de détail à une ligne affichable.
 *
 *  Chaque campagne a nommé ses clés à sa façon — `level`/`passed` pour le
 *  code, `niveau`/`reussi` pour l'extraction, `trouve` pour le long
 *  contexte, `success` pour l'agentique. Normaliser ici plutôt que
 *  réécrire les mesures : elles ont coûté des heures de GPU et se relisent
 *  très bien telles quelles.
 *
 *  `ok` reste **undefined** quand aucune clé connue ne porte le verdict.
 *  C'est la règle du projet appliquée à l'affichage : une information
 *  absente ne doit pas s'afficher comme un échec. La première version
 *  lisait `passed` seul et montrait cinq croix rouges sur l'extraction de
 *  gpt-oss — un modèle qui avait tout réussi. */
export function ligneDeDetail(brut: Record<string, unknown>, index: number): Ligne {
  const bool = (...cles: string[]): boolean | undefined => {
    for (const c of cles) if (typeof brut[c] === "boolean") return brut[c] as boolean;
    return undefined;
  };
  const texte = (...cles: string[]): string | undefined => {
    for (const c of cles) if (typeof brut[c] === "string" && brut[c]) return brut[c] as string;
    return undefined;
  };
  const nombre = (...cles: string[]): number | undefined => {
    for (const c of cles) if (typeof brut[c] === "number") return brut[c] as number;
    return undefined;
  };

  const contexte = nombre("contexte");
  const profondeur = nombre("profondeur");
  const nom =
    texte("level", "niveau", "epreuve", "task") ??
    (contexte != null
      ? `${(contexte / 1024).toFixed(0)}k · profondeur ${((profondeur ?? 0) * 100).toFixed(0)} %`
      : `essai ${index + 1}`);

  const appels = nombre("tool_calls");
  const attendu = texte("attendu");
  const recu = texte("recu");
  const ok = bool("passed", "reussi", "trouve", "success");
  const note =
    texte("detail") ??
    (attendu != null
      ? `attendu ${attendu}${ok === false && recu ? ` — reçu « ${recu.slice(-50)} »` : ""}`
      : appels != null
        ? `${appels} appel${appels > 1 ? "s" : ""} d'outil${
            brut.artifact_verified === true ? ", artefact vérifié sur disque" : ""
          }`
        : undefined);

  return {
    cle: `${nom}-${index}`,
    ok,
    nom,
    note,
    duree: nombre("secondes", "duration_s", "seconds"),
  };
}

/** Le détail brut d'un axe, tel que la campagne l'a produit.
 *
 *  Un chiffre sans son justificatif redevient une opinion : l'onglet doit
 *  pouvoir montrer *quel* niveau a cassé et avec quel message, pas
 *  seulement que le modèle plafonne. */
function AxisDetail({ axis, entry }: { axis: string; entry: BenchAxisDTO }) {
  const detail = (entry.detail ?? {}) as Record<string, unknown>;

  const tiers = detail.tiers as
    | { num_ctx: number; context_length?: number; cpu_offload_ratio?: number | null }[]
    | undefined;

  // Les noms sous lesquels les campagnes rangent leurs essais. Un axe peut
  // en porter plusieurs : le code a son échelle à neuf niveaux *et* ses
  // deux séries de départage, et n'en montrer qu'une cacherait précisément
  // ce qui sépare les trois modèles de tête.
  const series = ([
    ["niveaux", ""], ["essais", ""], ["mesures", ""], ["epreuves", ""],
    ["resultats", ""], ["extremes", "départage extrême"],
    ["abyssales", "départage abyssal"],
  ] as const)
    .filter(([cle]) => Array.isArray(detail[cle]))
    .map(([cle, titre]) => ({
      cle,
      titre,
      lignes: (detail[cle] as Record<string, unknown>[]).map(ligneDeDetail),
    }));

  return (
    <div className="space-y-1.5">
      <div className="text-hermes-muted text-[10px] uppercase tracking-wide">
        {AXIS_LABELS[axis] ?? axis} — {entry.verdict || "sans verdict"}
      </div>

      {tiers?.map((t) => (
        <div key={t.num_ctx} className="flex items-baseline gap-2 text-[11px] font-mono">
          <span className="text-hermes-text w-28">
            {(t.num_ctx / 1024).toFixed(0)}k demandés
          </span>
          <span className="text-hermes-muted w-24">
            {t.context_length ? `${(t.context_length / 1024).toFixed(0)}k servis` : "non servi"}
          </span>
          {t.cpu_offload_ratio != null && (
            <span className={t.cpu_offload_ratio > 0.02 ? "text-hermes-red" : "text-hermes-green"}>
              {(t.cpu_offload_ratio * 100).toFixed(0)} % CPU
            </span>
          )}
        </div>
      ))}

      {series.map((serie) => (
        <div key={serie.cle} className="space-y-1.5">
          {serie.titre && (
            <div className="text-hermes-muted text-[10px] uppercase tracking-wide pt-1">
              {serie.titre}
            </div>
          )}
          {serie.lignes.map((l) => (
            <div key={l.cle} className="flex items-baseline gap-2 text-[11px] font-mono">
              <span
                className={
                  l.ok == null
                    ? "text-hermes-muted"
                    : l.ok
                      ? "text-hermes-green"
                      : "text-hermes-red"
                }
              >
                {l.ok == null ? "·" : l.ok ? "✓" : "✗"}
              </span>
              <span className="text-hermes-text w-32 shrink-0 truncate">{l.nom}</span>
              {l.note && <span className="text-hermes-muted truncate">{l.note}</span>}
              {l.duree != null && (
                <span className="text-hermes-muted ml-auto shrink-0">{l.duree.toFixed(0)}s</span>
              )}
            </div>
          ))}
        </div>
      ))}

      {!tiers && series.length === 0 && Object.keys(detail).length > 0 && (
        <pre className="text-[10px] text-hermes-muted font-mono overflow-x-auto">
          {JSON.stringify(detail, null, 2)}
        </pre>
      )}
    </div>
  );
}

export default function ModelIntelligenceCenter() {
  const [activeTab, setActiveTab] = useState<(typeof TABS)[number]>("catalogue");
  const [expandedModel, setExpandedModel] = useState<string | null>(null);
  const [taskInput, setTaskInput] = useState("");
  const [recommendTaskType, setRecommendTaskType] = useState<string>("code_generation");
  const [benchmarkModelId, setBenchmarkModelId] = useState<string>("");
  const [benchmarkTaskType, setBenchmarkTaskType] = useState<string>("code_generation");
  const [optimizeModelId, setOptimizeModelId] = useState<string>("");

  const overview = useModelIntelligence();
  const ranking = useModelRanking();
  const recommend = useRecommendModel();
  const cloudStatus = useCloudStatus();
  const resources = useMonitoringResources() as { data?: ResourceStatus };
  const benchmarks = useModelBenchmarks(benchmarkModelId || undefined);
  const runBenchmark = useRunBenchmark();
  const history = useModelHistory(30);
  const catalogue = useModelCatalogue();

  const models = ranking.data?.models ?? [];
  const decision = recommend.data?.decision;
  const summary = overview.data?.data;
  const topModel = models[0];
  const fastestModel = models.length
    ? models.reduce((a, b) => (b.tps > a.tps ? b : a))
    : undefined;
  const mostEfficientModel = models.filter((m) => m.vram_mb > 0).length
    ? models.filter((m) => m.vram_mb > 0).reduce((a, b) => (b.vram_mb < a.vram_mb ? b : a))
    : undefined;

  const optimizeTarget = optimizeModelId || topModel?.model_id || "";
  const optimize = useModelOptimize(optimizeTarget || undefined);

  const gpu = resources.data?.gpu;

  const runRecommend = () => {
    const text = taskInput.trim();
    if (!text) return;
    recommend.mutate({ task_type: recommendTaskType, task_description: text });
  };

  return (
    <div className="space-y-6">
      {/* En-tête — compteurs et score moyen viennent de /api/v1/models */}
      <CenterHeader
        title="Model Intelligence"
        subtitle="Routage adaptatif des modèles et intelligence de performance"
        right={
          overview.isLoading ? (
            <span className="text-hermes-muted text-[11px] font-mono">chargement…</span>
          ) : overview.isError ? (
            <Badge variant="danger">modèles indisponibles</Badge>
          ) : (
            <>
              <Badge>{summary?.total_models ?? 0} modèles</Badge>
              <Badge>{summary?.total_runs ?? 0} runs</Badge>
              <Badge variant="info">
                Succès ∅ {((summary?.average_success_rate ?? 0) * 100).toFixed(0)}%
              </Badge>
            </>
          )
        }
      />

      {/* Meilleurs par catégorie + VRAM temps réel (HOS-071) — la spec
          demande explicitement que la décision voie la VRAM réellement
          libre, pas un plafond statique. */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card title="Meilleur global">
          {topModel ? (
            <>
              <div className="text-hermes-text-bright font-mono text-sm truncate">{topModel.name}</div>
              <div className="text-hermes-cyan font-mono text-lg mt-1">{topModel.score.toFixed(3)}</div>
            </>
          ) : (
            <div className="text-hermes-muted text-xs">—</div>
          )}
        </Card>
        <Card title="Plus rapide">
          {fastestModel ? (
            <>
              <div className="text-hermes-text-bright font-mono text-sm truncate">{fastestModel.name}</div>
              <div className="text-hermes-green font-mono text-lg mt-1">{fastestModel.tps.toFixed(1)} TPS</div>
            </>
          ) : (
            <div className="text-hermes-muted text-xs">—</div>
          )}
        </Card>
        <Card title="Plus efficient (VRAM)">
          {mostEfficientModel ? (
            <>
              <div className="text-hermes-text-bright font-mono text-sm truncate">{mostEfficientModel.name}</div>
              <div className="text-hermes-amber font-mono text-lg mt-1">
                {mostEfficientModel.vram_mb.toLocaleString()} MB
              </div>
            </>
          ) : (
            <div className="text-hermes-muted text-xs">—</div>
          )}
        </Card>
        <Card title="VRAM réelle (GPU)">
          {gpu ? (
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between text-[10px] font-mono">
                <span className="text-hermes-muted">{gpu.name || "GPU"}</span>
                <span className="text-hermes-text">
                  {formatGioPair(vramOccupee(gpu), gpu.vram_total_bytes)}
                </span>
              </div>
              <div className="h-1.5 rounded-full bg-hermes-elevated overflow-hidden">
                <div
                  className="h-full bg-hermes-cyan"
                  style={{
                    width: `${vramPourcent(gpu) ?? 0}%`,
                  }}
                />
              </div>
              <div className="text-hermes-green text-[10px] font-mono">
                {formatGio(vramLibre(gpu))} Gio libres — c&apos;est ce que les
                recommandations utilisent désormais, pas un plafond fixe.
              </div>
            </div>
          ) : (
            <div className="text-hermes-muted text-[10px] font-mono py-2">Indisponible</div>
          )}
        </Card>
      </div>

      {/* Cloud escalation status (HOS-066C) — read-only, GET /models/cloud/status.
          Local stays the default in every case; this is visibility, not a control. */}
      {!cloudStatus.isLoading && cloudStatus.data && (
        <div className="flex items-center gap-3 bg-hermes-elevated/40 border border-hermes-border rounded-lg px-4 py-2.5 text-xs">
          {!cloudStatus.data.configured ? (
            <>
              <Badge>cloud local uniquement</Badge>
              <span className="text-hermes-muted">
                OpenRouter n&apos;est pas configuré — chaque tâche s&apos;exécute en local.
              </span>
            </>
          ) : cloudStatus.data.authorized ? (
            <>
              <Badge variant="success">cloud actif</Badge>
              <span className="text-hermes-muted">
                {cloudStatus.data.catalog_size ?? 0} modèles gratuits ·{" "}
                {cloudStatus.data.quota_remaining != null
                  ? `${cloudStatus.data.quota_remaining} requêtes restantes aujourd'hui`
                  : "quota inconnu"}
                {" · réserve "}
                {cloudStatus.data.reserve_daily_requests ?? 0}
              </span>
            </>
          ) : (
            <>
              <Badge variant="warning">cloud configuré, non autorisé</Badge>
              <span className="text-hermes-muted">{cloudStatus.data.message}</span>
            </>
          )}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-hermes-elevated/50 rounded-lg p-1">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
              activeTab === tab
                ? "bg-hermes-cyan/20 text-hermes-cyan"
                : "text-hermes-muted hover:text-hermes-text"
            }`}
          >
            {TAB_LABELS[tab]}
          </button>
        ))}
      </div>

      {/* Catalogue mesuré (HOS-108) — GET /models/catalogue.
          Distinct du Classement voisin : celui-ci n'affiche que ce qui a
          été observé sur cette machine, jamais une heuristique. Chaque
          note vient d'une campagne réelle dont le détail est dépliable. */}
      {activeTab === "catalogue" && (
        <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-5">
          <div className="flex items-baseline justify-between mb-1">
            <h2 className="text-lg font-semibold text-hermes-text-bright">Catalogue mesuré</h2>
            <span className="text-hermes-muted text-[11px]">
              {catalogue.data?.total ?? 0} modèles · cliquez une ligne pour le détail
            </span>
          </div>
          <p className="text-hermes-muted text-xs mb-4">
            Une note par axe, jamais de moyenne : un modèle excellent en vision et
            faible en long contexte n&apos;est pas « moyen », il a deux usages
            différents. Une case vide signifie <em>non mesuré</em> — ce n&apos;est
            pas un zéro.
          </p>

          {/* Le profil, avant la table (HOS-179). Une table donne des
              valeurs ; c'est la forme qui départage deux candidats. */}
          {!catalogue.isLoading && <ComparaisonRadar catalogue={catalogue.data} />}

          {catalogue.isLoading && (
            <div className="text-hermes-muted text-sm py-2">Chargement du catalogue…</div>
          )}
          {catalogue.isError && (
            <div className="text-hermes-red text-sm py-2">
              /models/catalogue injoignable —{" "}
              {catalogue.error instanceof Error ? catalogue.error.message : "erreur inconnue"}
            </div>
          )}
          {catalogue.data && catalogue.data.models.length === 0 && (
            <div className="text-hermes-muted text-sm py-2">
              Aucune campagne n&apos;a encore été enregistrée.
            </div>
          )}

          {catalogue.data && catalogue.data.models.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-hermes-border">
                    <th className="text-left py-2 px-3 text-hermes-muted font-medium">Modèle</th>
                    {catalogue.data.axes.map((axe) => (
                      <th key={axe} className="text-right py-2 px-3 text-hermes-muted font-medium whitespace-nowrap">
                        {AXIS_LABELS[axe] ?? axe}
                      </th>
                    ))}
                    <th className="text-right py-2 px-3 text-hermes-muted font-medium">Mesuré le</th>
                  </tr>
                </thead>
                <tbody>
                  {catalogue.data.models.map((entree) => {
                    const ouvert = expandedModel === entree.model;
                    return (
                      <React.Fragment key={entree.model}>
                        <tr
                          onClick={() => setExpandedModel(ouvert ? null : entree.model)}
                          className="border-b border-hermes-border/50 hover:bg-hermes-elevated/20 cursor-pointer"
                        >
                          <td className="py-2 px-3 text-hermes-text-bright font-mono whitespace-nowrap">
                            <span className="text-hermes-muted mr-1.5">{ouvert ? "▾" : "▸"}</span>
                            {entree.model}
                          </td>
                          {catalogue.data!.axes.map((axe) => {
                            const note = entree.notes[axe];
                            const mesure = entree.axes[axe];
                            return (
                              <td key={axe} className="py-2 px-3 text-right whitespace-nowrap">
                                {note == null && !mesure ? (
                                  <span className="text-hermes-muted/50">—</span>
                                ) : (
                                  <>
                                    <span className={`font-mono ${noteColor(note)}`}>
                                      {note == null ? "n.n." : note}
                                    </span>
                                    {mesure?.verdict && (
                                      <div className="text-hermes-muted text-[10px] font-mono">
                                        {mesure.verdict}
                                      </div>
                                    )}
                                  </>
                                )}
                              </td>
                            );
                          })}
                          <td className="py-2 px-3 text-right text-hermes-muted font-mono text-[11px]">
                            {formatMeasuredAt(entree.measured_at)}
                          </td>
                        </tr>
                        {ouvert && (
                          <tr className="border-b border-hermes-border/50 bg-hermes-bg-deep/40">
                            <td colSpan={catalogue.data!.axes.length + 2} className="py-3 px-6">
                              <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-8 gap-y-4">
                                {Object.entries(entree.axes).map(([axe, mesure]) => (
                                  <AxisDetail key={axe} axis={axe} entry={mesure} />
                                ))}
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Model Ranking Tab */}
      {activeTab === "ranking" && (
        <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-5">
          <h2 className="text-lg font-semibold text-hermes-text-bright mb-4">Classement des modèles</h2>
          {ranking.isLoading && (
            <div className="text-hermes-muted text-sm py-2">Chargement du classement…</div>
          )}
          {ranking.isError && (
            <div className="text-hermes-red text-sm py-2">
              /models/ranking injoignable —{" "}
              {ranking.error instanceof Error ? ranking.error.message : "erreur inconnue"}
            </div>
          )}
          {!ranking.isLoading && !ranking.isError && models.length === 0 && (
            <div className="text-hermes-muted text-sm py-2">
              Le registre de modèles est vide.
            </div>
          )}
          {models.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-hermes-border">
                    <th className="text-left py-3 px-4 text-hermes-muted font-medium">Modèle</th>
                    <th className="text-right py-3 px-4 text-hermes-muted font-medium">Score</th>
                    <th className="text-right py-3 px-4 text-hermes-muted font-medium">Paramètres</th>
                    <th className="text-right py-3 px-4 text-hermes-muted font-medium">VRAM</th>
                    <th className="text-right py-3 px-4 text-hermes-muted font-medium">TPS</th>
                    <th className="text-right py-3 px-4 text-hermes-muted font-medium">Réussite</th>
                    <th className="text-left py-3 px-4 text-hermes-muted font-medium">Tags</th>
                  </tr>
                </thead>
                <tbody>
                  {models.map((m, i) => (
                    <tr key={m.model_id} className="border-b border-hermes-border/50 hover:bg-hermes-elevated/20">
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-2">
                          <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                            i === 0 ? "bg-hermes-amber/20 text-hermes-amber" : "bg-hermes-elevated text-hermes-muted"
                          }`}>{i + 1}</span>
                          <span className="text-hermes-text-bright">{m.name}</span>
                        </div>
                      </td>
                      <td className="py-3 px-4 text-right">
                        <span className="text-hermes-cyan font-mono">{m.score.toFixed(3)}</span>
                      </td>
                      <td className="py-3 px-4 text-right text-hermes-muted">{m.parameters_b}B</td>
                      <td className="py-3 px-4 text-right text-hermes-muted">{m.vram_mb.toLocaleString()}</td>
                      <td className="py-3 px-4 text-right text-hermes-muted">{m.tps}</td>
                      <td className="py-3 px-4 text-right">
                        <span className="text-hermes-green font-mono">
                          {(m.success_rate * 100).toFixed(0)}%
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex gap-1">
                          {/* HOS-073: a role whose own tier shares its name (e.g. the
                              "standard" role has tier "standard") produced a tags
                              array with the same string twice — key={t} alone
                              collided. Deduped so the badge isn't shown twice
                              either, indexed key as a defensive backstop. */}
                          {Array.from(new Set(m.tags)).map((t, i) => (
                            <span key={`${t}-${i}`} className="px-1.5 py-0.5 bg-hermes-elevated rounded text-[10px] text-hermes-muted">{t}</span>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Recommend Tab — a real POST /models/recommend, with an explicit
          task_type so the router doesn't have to keyword-guess it from the
          description alone (HOS-071 Phase C) */}
      {activeTab === "recommend" && (
        <div className="space-y-4">
          <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-5">
            <h2 className="text-lg font-semibold text-hermes-text-bright mb-4">Recommandeur de modèle</h2>
            <div className="flex gap-3">
              <select
                value={recommendTaskType}
                onChange={(e) => setRecommendTaskType(e.target.value)}
                className="bg-hermes-bg-deep/50 border border-hermes-border rounded-lg px-3 py-3 text-sm text-hermes-text-bright focus:outline-none focus:border-hermes-cyan/50"
              >
                {TASK_TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
              <input
                type="text"
                value={taskInput}
                onChange={(e) => setTaskInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") runRecommend();
                }}
                placeholder="Décrivez votre tâche… (ex. « Créer une API REST FastAPI avec authentification »)"
                className="flex-1 bg-hermes-bg-deep/50 border border-hermes-border rounded-lg px-4 py-3 text-sm text-hermes-text-bright placeholder-gray-500 focus:outline-none focus:border-hermes-cyan/50"
              />
              <button
                onClick={runRecommend}
                disabled={!taskInput.trim() || recommend.isPending}
                className="px-5 py-3 bg-hermes-cyan/20 text-hermes-cyan rounded-lg text-sm font-medium hover:bg-hermes-cyan/30 transition-all disabled:opacity-30"
              >
                {recommend.isPending ? "…" : "Recommander"}
              </button>
            </div>
            {recommend.isError && (
              <div className="text-hermes-red text-sm mt-3">
                {recommend.error instanceof Error
                  ? recommend.error.message
                  : "Échec de la recommandation"}
              </div>
            )}
          </div>

          {decision && (
            <div className="bg-hermes-elevated/60 border border-hermes-cyan/30 rounded-lg p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-hermes-text-bright font-semibold">Configuration recommandée</h3>
                <div className="flex gap-2">
                  <span className="px-2 py-1 bg-hermes-cyan/20 text-hermes-cyan rounded text-xs font-medium">
                    {decision.runtime}
                  </span>
                  {decision.quantization && (
                    <span className="px-2 py-1 bg-hermes-elevated text-hermes-muted rounded text-xs font-medium">
                      {decision.quantization}
                    </span>
                  )}
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <div>
                  <div className="text-hermes-muted text-xs uppercase">Modèle</div>
                  <div className="text-hermes-text-bright font-medium">{decision.model_name}</div>
                </div>
                <div>
                  <div className="text-hermes-muted text-xs uppercase">Confiance</div>
                  <div className="text-hermes-cyan font-mono">
                    {(decision.confidence * 100).toFixed(0)}%
                  </div>
                </div>
                <div>
                  <div className="text-hermes-muted text-xs uppercase">VRAM estimée</div>
                  <div className="text-hermes-text-bright font-mono">
                    {decision.estimated_vram_mb.toLocaleString()} MB
                  </div>
                </div>
                <div>
                  <div className="text-hermes-muted text-xs uppercase">Débit estimé</div>
                  <div className="text-hermes-text-bright font-mono">
                    {decision.estimated_tps.toFixed(1)} TPS ·{" "}
                    {decision.estimated_latency_ms}ms
                  </div>
                </div>
              </div>
              {decision.alternatives.length > 0 && (
                <div className="mb-4">
                  <div className="text-hermes-muted text-xs uppercase mb-1">Alternatives</div>
                  <div className="text-hermes-muted text-sm">
                    {decision.alternatives
                      .map((a) => `${a.name} (${a.score.toFixed(2)})`)
                      .join(", ")}
                  </div>
                </div>
              )}
              <div className="bg-hermes-bg-deep/50 rounded-lg p-3">
                <div className="text-hermes-muted text-xs uppercase mb-1">Raison</div>
                <div className="text-hermes-text text-sm">{decision.reason}</div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Benchmark Tab — a real trigger (POST /models/benchmark, one real
          Ollama call) and the real, stored results table, not a raw JSON
          dump and not random.uniform() (HOS-065/HOS-071) */}
      {activeTab === "benchmark" && (
        <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-5">
          <h2 className="text-lg font-semibold text-hermes-text-bright mb-4">Benchmarks</h2>
          <div className="flex gap-3 mb-4">
            <select
              value={benchmarkModelId}
              onChange={(e) => setBenchmarkModelId(e.target.value)}
              className="bg-hermes-bg-deep/50 border border-hermes-border rounded-lg px-3 py-2.5 text-sm text-hermes-text-bright focus:outline-none focus:border-hermes-cyan/50"
            >
              <option value="">Tous les modèles</option>
              {models.map((m) => (
                <option key={m.model_id} value={m.model_id}>{m.name}</option>
              ))}
            </select>
            <select
              value={benchmarkTaskType}
              onChange={(e) => setBenchmarkTaskType(e.target.value)}
              className="bg-hermes-bg-deep/50 border border-hermes-border rounded-lg px-3 py-2.5 text-sm text-hermes-text-bright focus:outline-none focus:border-hermes-cyan/50"
            >
              {TASK_TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <button
              onClick={() => benchmarkModelId && runBenchmark.mutate({ model_id: benchmarkModelId, task_type: benchmarkTaskType })}
              disabled={!benchmarkModelId || runBenchmark.isPending}
              className="px-4 py-2.5 bg-hermes-cyan/20 text-hermes-cyan rounded-lg text-sm font-medium hover:bg-hermes-cyan/30 transition-all disabled:opacity-30"
              title={!benchmarkModelId ? "Sélectionnez d'abord un modèle à évaluer" : undefined}
            >
              {runBenchmark.isPending ? "En cours… (inférence réelle, peut prendre un moment)" : "Lancer le benchmark"}
            </button>
          </div>
          {runBenchmark.isError && (
            <div className="text-hermes-red text-sm mb-3">
              {runBenchmark.error instanceof Error ? runBenchmark.error.message : "Échec du benchmark"}
            </div>
          )}

          {benchmarks.isLoading && (
            <div className="text-hermes-muted text-sm">Chargement des benchmarks…</div>
          )}
          {benchmarks.isError && (
            <div className="text-hermes-red text-sm">/models/benchmarks injoignable</div>
          )}
          {benchmarks.data && benchmarks.data.benchmarks.length === 0 && (
            <div className="text-hermes-muted text-sm py-2">
              Aucun benchmark n&apos;a encore été exécuté{benchmarkModelId ? " pour ce modèle" : ""} — les
              résultats réels apparaîtront ici une fois « Lancer le benchmark » terminé.
            </div>
          )}
          {benchmarks.data && benchmarks.data.benchmarks.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-hermes-border">
                    <th className="text-left py-2 px-3 text-hermes-muted font-medium">Modèle</th>
                    <th className="text-left py-2 px-3 text-hermes-muted font-medium">Tâche</th>
                    <th className="text-right py-2 px-3 text-hermes-muted font-medium">Latence</th>
                    <th className="text-right py-2 px-3 text-hermes-muted font-medium">TPS</th>
                    <th className="text-right py-2 px-3 text-hermes-muted font-medium">VRAM</th>
                    <th className="text-right py-2 px-3 text-hermes-muted font-medium">Qualité</th>
                  </tr>
                </thead>
                <tbody>
                  {benchmarks.data.benchmarks.map((b) => (
                    <tr key={b.benchmark_id} className="border-b border-hermes-border/50">
                      <td className="py-2 px-3 text-hermes-text-bright font-mono">{b.model_id}</td>
                      <td className="py-2 px-3 text-hermes-muted">{b.task_type}</td>
                      <td className="py-2 px-3 text-right text-hermes-muted font-mono">{b.latency_ms.toFixed(0)}ms</td>
                      <td className="py-2 px-3 text-right text-hermes-muted font-mono">{b.tokens_per_second.toFixed(1)}</td>
                      <td className="py-2 px-3 text-right text-hermes-muted font-mono">{b.vram_usage_mb.toLocaleString()} MB</td>
                      <td className="py-2 px-3 text-right font-mono">
                        <span className={b.quality_score > 0 ? "text-hermes-green" : "text-hermes-red"}>
                          {b.quality_score > 0 ? "ok" : "vide"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Optimizer Tab — real cross-runtime/quantization comparison
          (GET /models/optimize, HOS-071 Phase D) via ModelRuntimeOptimizer/
          ModelRuntimeAdapter, previously built but never called by
          anything. Estimated, not a guarantee that a runtime is actually
          installed — same caveat the underlying adapter always carried. */}
      {activeTab === "optimizer" && (
        <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-hermes-text-bright">Optimiseur de runtime</h2>
            <select
              value={optimizeTarget}
              onChange={(e) => setOptimizeModelId(e.target.value)}
              className="bg-hermes-bg-deep/50 border border-hermes-border rounded-lg px-3 py-2 text-sm text-hermes-text-bright focus:outline-none focus:border-hermes-cyan/50"
            >
              {models.map((m) => (
                <option key={m.model_id} value={m.model_id}>{m.name}</option>
              ))}
            </select>
          </div>
          {!optimizeTarget ? (
            <div className="text-hermes-muted text-sm">
              Aucun modèle classé disponible à optimiser.
            </div>
          ) : optimize.isLoading ? (
            <div className="text-hermes-muted text-sm py-2">Comparaison des runtimes…</div>
          ) : optimize.isError || !optimize.data?.success ? (
            <div className="text-hermes-red text-sm py-2">
              Impossible de comparer les runtimes pour {optimizeTarget}.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-hermes-border">
                    <th className="text-left py-2 px-3 text-hermes-muted font-medium">Runtime</th>
                    <th className="text-left py-2 px-3 text-hermes-muted font-medium">Quantification</th>
                    <th className="text-right py-2 px-3 text-hermes-muted font-medium">VRAM est.</th>
                    <th className="text-right py-2 px-3 text-hermes-muted font-medium">TPS est.</th>
                    <th className="text-left py-2 px-3 text-hermes-muted font-medium">Risque</th>
                    <th className="text-left py-2 px-3 text-hermes-muted font-medium">Faisable</th>
                  </tr>
                </thead>
                <tbody>
                  {(optimize.data.comparisons ?? []).map((c, i) => (
                    <tr key={`${c.runtime}-${c.quantization}`} className={`border-b border-hermes-border/50 ${i === 0 ? "bg-hermes-cyan/5" : ""}`}>
                      <td className="py-2 px-3 text-hermes-text-bright font-mono">
                        {c.runtime}{i === 0 && <span className="ml-2 text-[10px] text-hermes-amber">meilleur</span>}
                      </td>
                      <td className="py-2 px-3 text-hermes-muted font-mono">{c.quantization}</td>
                      <td className="py-2 px-3 text-right text-hermes-muted font-mono">{c.estimated_vram_mb.toLocaleString()} MB</td>
                      <td className="py-2 px-3 text-right text-hermes-muted font-mono">{c.estimated_tokens_per_second.toFixed(1)}</td>
                      <td className="py-2 px-3">
                        <Badge variant={c.risk_level === "low" ? "success" : c.risk_level === "medium" ? "warning" : "danger"}>
                          {c.risk_level}
                        </Badge>
                      </td>
                      <td className="py-2 px-3 text-hermes-muted">{c.feasible ? "oui" : "non"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* History Tab — real routing decisions (GET /models/history),
          previously built but never surfaced anywhere in the Cockpit. */}
      {activeTab === "history" && (
        <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-5">
          <h2 className="text-lg font-semibold text-hermes-text-bright mb-4">Décisions récentes</h2>
          {history.isLoading && (
            <div className="text-hermes-muted text-sm py-2">Chargement de l&apos;historique…</div>
          )}
          {history.isError && (
            <div className="text-hermes-red text-sm py-2">/models/history injoignable</div>
          )}
          {history.data && history.data.decisions.length === 0 && (
            <div className="text-hermes-muted text-sm py-2">
              Aucune recommandation n&apos;a encore été exécutée dans ce processus.
            </div>
          )}
          {history.data && history.data.decisions.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-hermes-border">
                    <th className="text-left py-2 px-3 text-hermes-muted font-medium">Modèle</th>
                    <th className="text-left py-2 px-3 text-hermes-muted font-medium">Runtime</th>
                    <th className="text-right py-2 px-3 text-hermes-muted font-medium">Confiance</th>
                    <th className="text-right py-2 px-3 text-hermes-muted font-medium">Latence est.</th>
                    <th className="text-left py-2 px-3 text-hermes-muted font-medium">Raison</th>
                  </tr>
                </thead>
                <tbody>
                  {[...history.data.decisions].reverse().map((d, i) => (
                    <tr key={i} className="border-b border-hermes-border/50">
                      <td className="py-2 px-3 text-hermes-text-bright font-mono">{d.model_name || d.model_id}</td>
                      <td className="py-2 px-3 text-hermes-muted font-mono">{d.runtime}</td>
                      <td className="py-2 px-3 text-right text-hermes-cyan font-mono">
                        {(d.confidence * 100).toFixed(0)}%
                      </td>
                      <td className="py-2 px-3 text-right text-hermes-muted font-mono">{d.estimated_latency_ms}ms</td>
                      <td className="py-2 px-3 text-hermes-muted">{d.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
