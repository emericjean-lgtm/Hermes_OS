"use client";

import React, { useState } from "react";
import {
  useCloudStatus,
  useModelIntelligence,
  useModelRanking,
  useRecommendModel,
} from "@/hooks/use-api";
import { modelIntelligenceClient } from "@/services/client";
import { useQuery } from "@tanstack/react-query";
import { CenterHeader } from "@/components/center-scaffold";
import { Badge } from "@/components/ui/card";

// Every figure in this Center used to come from two module-level constants.
// MOCK_MODELS listed five models with invented scores and success rates;
// MOCK_DECISIONS held two hand-written routing decisions; "Recommend" slept a
// random 600–1000 ms (`setTimeout(r, 600 + Math.random() * 400)`) and returned
// MOCK_DECISIONS[0]; "Run Full Benchmark" slept 1500 ms and did nothing; and the
// Optimizer tab was static text ("Qwen3-Coder 30B", "16,200 MB VRAM", "0.87",
// "Top 1 of 12 configurations"). /api/v1/models, /models/ranking and
// /models/recommend served real data throughout (R-002 P3).

const TABS = ["ranking", "recommend", "benchmark", "optimizer"] as const;

export default function ModelIntelligenceCenter() {
  const [activeTab, setActiveTab] = useState<(typeof TABS)[number]>("ranking");
  const [taskInput, setTaskInput] = useState("");

  const overview = useModelIntelligence();
  const ranking = useModelRanking();
  const recommend = useRecommendModel();
  const cloudStatus = useCloudStatus();
  const benchmarks = useQuery({
    queryKey: ["models", "benchmarks"],
    queryFn: () => modelIntelligenceClient.benchmarks(),
    enabled: activeTab === "benchmark",
  });

  const models = ranking.data?.models ?? [];
  const decision = recommend.data?.decision;
  const summary = overview.data?.data;
  const topModel = models[0];

  const runRecommend = () => {
    const text = taskInput.trim();
    if (!text) return;
    recommend.mutate({ task_type: "code", description: text });
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
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* Model Ranking Tab */}
      {activeTab === "ranking" && (
        <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-5">
          <h2 className="text-lg font-semibold text-hermes-text-bright mb-4">Model Rankings</h2>
          {ranking.isLoading && (
            <div className="text-hermes-muted text-sm py-2">Loading rankings…</div>
          )}
          {ranking.isError && (
            <div className="text-hermes-red text-sm py-2">
              Could not reach /models/ranking —{" "}
              {ranking.error instanceof Error ? ranking.error.message : "unknown error"}
            </div>
          )}
          {!ranking.isLoading && !ranking.isError && models.length === 0 && (
            <div className="text-hermes-muted text-sm py-2">
              The model registry is empty.
            </div>
          )}
          {models.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-hermes-border">
                    <th className="text-left py-3 px-4 text-hermes-muted font-medium">Model</th>
                    <th className="text-right py-3 px-4 text-hermes-muted font-medium">Score</th>
                    <th className="text-right py-3 px-4 text-hermes-muted font-medium">Params</th>
                    <th className="text-right py-3 px-4 text-hermes-muted font-medium">VRAM</th>
                    <th className="text-right py-3 px-4 text-hermes-muted font-medium">TPS</th>
                    <th className="text-right py-3 px-4 text-hermes-muted font-medium">Success</th>
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
                          {m.tags.map((t) => (
                            <span key={t} className="px-1.5 py-0.5 bg-hermes-elevated rounded text-[10px] text-hermes-muted">{t}</span>
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

      {/* Recommend Tab — a real POST /models/recommend */}
      {activeTab === "recommend" && (
        <div className="space-y-4">
          <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-5">
            <h2 className="text-lg font-semibold text-hermes-text-bright mb-4">Model Recommender</h2>
            <div className="flex gap-3">
              <input
                type="text"
                value={taskInput}
                onChange={(e) => setTaskInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") runRecommend();
                }}
                placeholder="Describe your task... (e.g., 'Create a FastAPI REST API with authentication')"
                className="flex-1 bg-hermes-bg-deep/50 border border-hermes-border rounded-lg px-4 py-3 text-sm text-hermes-text-bright placeholder-gray-500 focus:outline-none focus:border-hermes-cyan/50"
              />
              <button
                onClick={runRecommend}
                disabled={!taskInput.trim() || recommend.isPending}
                className="px-5 py-3 bg-hermes-cyan/20 text-hermes-cyan rounded-lg text-sm font-medium hover:bg-hermes-cyan/30 transition-all disabled:opacity-30"
              >
                {recommend.isPending ? "…" : "Recommend"}
              </button>
            </div>
            {recommend.isError && (
              <div className="text-hermes-red text-sm mt-3">
                {recommend.error instanceof Error
                  ? recommend.error.message
                  : "Recommendation failed"}
              </div>
            )}
          </div>

          {decision && (
            <div className="bg-hermes-elevated/60 border border-hermes-cyan/30 rounded-lg p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-hermes-text-bright font-semibold">Recommended Configuration</h3>
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
                  <div className="text-hermes-muted text-xs uppercase">Model</div>
                  <div className="text-hermes-text-bright font-medium">{decision.model_name}</div>
                </div>
                <div>
                  <div className="text-hermes-muted text-xs uppercase">Confidence</div>
                  <div className="text-hermes-cyan font-mono">
                    {(decision.confidence * 100).toFixed(0)}%
                  </div>
                </div>
                <div>
                  <div className="text-hermes-muted text-xs uppercase">Estimated VRAM</div>
                  <div className="text-hermes-text-bright font-mono">
                    {decision.estimated_vram_mb.toLocaleString()} MB
                  </div>
                </div>
                <div>
                  <div className="text-hermes-muted text-xs uppercase">Estimated throughput</div>
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
                <div className="text-hermes-muted text-xs uppercase mb-1">Reason</div>
                <div className="text-hermes-text text-sm">{decision.reason}</div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Benchmark Tab — reads the real benchmark record */}
      {activeTab === "benchmark" && (
        <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-5">
          <h2 className="text-lg font-semibold text-hermes-text-bright mb-4">Benchmarks</h2>
          {benchmarks.isLoading && (
            <div className="text-hermes-muted text-sm">Loading benchmarks…</div>
          )}
          {benchmarks.isError && (
            <div className="text-hermes-red text-sm">
              Could not reach /models/benchmarks
            </div>
          )}
          {benchmarks.data && (
            <pre className="text-xs text-hermes-text font-mono whitespace-pre-wrap max-h-[320px] overflow-y-auto bg-hermes-bg-deep/50 rounded-lg p-3">
              {JSON.stringify(benchmarks.data, null, 2)}
            </pre>
          )}
        </div>
      )}

      {/* Optimizer Tab — derived from the live ranking, not static text */}
      {activeTab === "optimizer" && (
        <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-5">
          <h2 className="text-lg font-semibold text-hermes-text-bright mb-4">Runtime Optimizer</h2>
          {!topModel ? (
            <div className="text-hermes-muted text-sm">
              No ranked model available to optimise for.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-hermes-bg-deep/50 rounded-lg p-4">
                <div className="text-hermes-muted text-xs uppercase mb-2">Top-ranked model</div>
                <div className="text-hermes-text-bright font-mono text-sm">{topModel.name}</div>
                <div className="text-hermes-muted text-xs mt-1">
                  {topModel.parameters_b}B parameters
                </div>
                <div className="text-hermes-green text-xs mt-1">
                  tags: {topModel.tags.join(", ") || "none"}
                </div>
              </div>
              <div className="bg-hermes-bg-deep/50 rounded-lg p-4">
                <div className="text-hermes-muted text-xs uppercase mb-2">Measured profile</div>
                <div className="text-hermes-text-bright font-mono text-sm">
                  {topModel.vram_mb.toLocaleString()} MB VRAM
                </div>
                <div className="text-hermes-muted text-xs mt-1">
                  {topModel.tps} TPS
                </div>
                <div className="text-hermes-muted text-xs mt-1">
                  success {(topModel.success_rate * 100).toFixed(0)}%
                </div>
              </div>
              <div className="bg-hermes-bg-deep/50 rounded-lg p-4">
                <div className="text-hermes-muted text-xs uppercase mb-2">Score</div>
                <div className="text-hermes-cyan font-mono text-lg">
                  {topModel.score.toFixed(3)}
                </div>
                <div className="text-hermes-muted text-xs mt-1">
                  ranked 1 of {models.length}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
