"use client";

import React, { useState } from "react";
import {
  useModelIntelligence,
  useModelRanking,
  useRecommendModel,
} from "@/hooks/use-api";
import { modelIntelligenceClient } from "@/services/client";
import { useQuery } from "@tanstack/react-query";

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
      {/* Header — counts and average score come from /api/v1/models */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Model Intelligence</h1>
          <p className="text-gray-400 text-sm mt-1">
            Adaptive model routing &amp; performance intelligence
          </p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          {overview.isLoading ? (
            <span className="text-gray-400">loading…</span>
          ) : overview.isError ? (
            <span className="text-red-400">models unavailable</span>
          ) : (
            <>
              <span className="text-gray-400">{summary?.total_models ?? 0} modèles</span>
              <span className="text-gray-400">{summary?.total_runs ?? 0} runs</span>
              <span className="text-cyan-400 font-medium">
                Succès ∅ {((summary?.average_success_rate ?? 0) * 100).toFixed(0)}%
              </span>
            </>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-800/50 rounded-lg p-1">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
              activeTab === tab
                ? "bg-cyan-500/20 text-cyan-300"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* Model Ranking Tab */}
      {activeTab === "ranking" && (
        <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-5">
          <h2 className="text-lg font-semibold text-white mb-4">Model Rankings</h2>
          {ranking.isLoading && (
            <div className="text-gray-400 text-sm py-2">Loading rankings…</div>
          )}
          {ranking.isError && (
            <div className="text-red-400 text-sm py-2">
              Could not reach /models/ranking —{" "}
              {ranking.error instanceof Error ? ranking.error.message : "unknown error"}
            </div>
          )}
          {!ranking.isLoading && !ranking.isError && models.length === 0 && (
            <div className="text-gray-400 text-sm py-2">
              The model registry is empty.
            </div>
          )}
          {models.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-700">
                    <th className="text-left py-3 px-4 text-gray-400 font-medium">Model</th>
                    <th className="text-right py-3 px-4 text-gray-400 font-medium">Score</th>
                    <th className="text-right py-3 px-4 text-gray-400 font-medium">Params</th>
                    <th className="text-right py-3 px-4 text-gray-400 font-medium">VRAM</th>
                    <th className="text-right py-3 px-4 text-gray-400 font-medium">TPS</th>
                    <th className="text-right py-3 px-4 text-gray-400 font-medium">Success</th>
                    <th className="text-left py-3 px-4 text-gray-400 font-medium">Tags</th>
                  </tr>
                </thead>
                <tbody>
                  {models.map((m, i) => (
                    <tr key={m.model_id} className="border-b border-gray-700/50 hover:bg-gray-700/20">
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-2">
                          <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                            i === 0 ? "bg-yellow-500/20 text-yellow-400" : "bg-gray-700 text-gray-400"
                          }`}>{i + 1}</span>
                          <span className="text-white">{m.name}</span>
                        </div>
                      </td>
                      <td className="py-3 px-4 text-right">
                        <span className="text-cyan-400 font-mono">{m.score.toFixed(3)}</span>
                      </td>
                      <td className="py-3 px-4 text-right text-gray-400">{m.parameters_b}B</td>
                      <td className="py-3 px-4 text-right text-gray-400">{m.vram_mb.toLocaleString()}</td>
                      <td className="py-3 px-4 text-right text-gray-400">{m.tps}</td>
                      <td className="py-3 px-4 text-right">
                        <span className="text-green-400 font-mono">
                          {(m.success_rate * 100).toFixed(0)}%
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex gap-1">
                          {m.tags.map((t) => (
                            <span key={t} className="px-1.5 py-0.5 bg-gray-700 rounded text-[10px] text-gray-300">{t}</span>
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
          <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-5">
            <h2 className="text-lg font-semibold text-white mb-4">Model Recommender</h2>
            <div className="flex gap-3">
              <input
                type="text"
                value={taskInput}
                onChange={(e) => setTaskInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") runRecommend();
                }}
                placeholder="Describe your task... (e.g., 'Create a FastAPI REST API with authentication')"
                className="flex-1 bg-gray-900/50 border border-gray-700 rounded-lg px-4 py-3 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500/50"
              />
              <button
                onClick={runRecommend}
                disabled={!taskInput.trim() || recommend.isPending}
                className="px-5 py-3 bg-cyan-500/20 text-cyan-300 rounded-lg text-sm font-medium hover:bg-cyan-500/30 transition-all disabled:opacity-30"
              >
                {recommend.isPending ? "…" : "Recommend"}
              </button>
            </div>
            {recommend.isError && (
              <div className="text-red-400 text-sm mt-3">
                {recommend.error instanceof Error
                  ? recommend.error.message
                  : "Recommendation failed"}
              </div>
            )}
          </div>

          {decision && (
            <div className="bg-gray-800/60 border border-cyan-500/30 rounded-lg p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-white font-semibold">Recommended Configuration</h3>
                <div className="flex gap-2">
                  <span className="px-2 py-1 bg-cyan-500/20 text-cyan-300 rounded text-xs font-medium">
                    {decision.runtime}
                  </span>
                  {decision.quantization && (
                    <span className="px-2 py-1 bg-gray-700 text-gray-300 rounded text-xs font-medium">
                      {decision.quantization}
                    </span>
                  )}
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <div>
                  <div className="text-gray-400 text-xs uppercase">Model</div>
                  <div className="text-white font-medium">{decision.model_name}</div>
                </div>
                <div>
                  <div className="text-gray-400 text-xs uppercase">Confidence</div>
                  <div className="text-cyan-400 font-mono">
                    {(decision.confidence * 100).toFixed(0)}%
                  </div>
                </div>
                <div>
                  <div className="text-gray-400 text-xs uppercase">Estimated VRAM</div>
                  <div className="text-white font-mono">
                    {decision.estimated_vram_mb.toLocaleString()} MB
                  </div>
                </div>
                <div>
                  <div className="text-gray-400 text-xs uppercase">Estimated throughput</div>
                  <div className="text-white font-mono">
                    {decision.estimated_tps.toFixed(1)} TPS ·{" "}
                    {decision.estimated_latency_ms}ms
                  </div>
                </div>
              </div>
              {decision.alternatives.length > 0 && (
                <div className="mb-4">
                  <div className="text-gray-400 text-xs uppercase mb-1">Alternatives</div>
                  <div className="text-gray-300 text-sm">
                    {decision.alternatives
                      .map((a) => `${a.name} (${a.score.toFixed(2)})`)
                      .join(", ")}
                  </div>
                </div>
              )}
              <div className="bg-gray-900/50 rounded-lg p-3">
                <div className="text-gray-400 text-xs uppercase mb-1">Reason</div>
                <div className="text-gray-200 text-sm">{decision.reason}</div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Benchmark Tab — reads the real benchmark record */}
      {activeTab === "benchmark" && (
        <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-5">
          <h2 className="text-lg font-semibold text-white mb-4">Benchmarks</h2>
          {benchmarks.isLoading && (
            <div className="text-gray-400 text-sm">Loading benchmarks…</div>
          )}
          {benchmarks.isError && (
            <div className="text-red-400 text-sm">
              Could not reach /models/benchmarks
            </div>
          )}
          {benchmarks.data && (
            <pre className="text-xs text-gray-200 font-mono whitespace-pre-wrap max-h-[320px] overflow-y-auto bg-gray-900/50 rounded-lg p-3">
              {JSON.stringify(benchmarks.data, null, 2)}
            </pre>
          )}
        </div>
      )}

      {/* Optimizer Tab — derived from the live ranking, not static text */}
      {activeTab === "optimizer" && (
        <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-5">
          <h2 className="text-lg font-semibold text-white mb-4">Runtime Optimizer</h2>
          {!topModel ? (
            <div className="text-gray-400 text-sm">
              No ranked model available to optimise for.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-gray-900/50 rounded-lg p-4">
                <div className="text-gray-400 text-xs uppercase mb-2">Top-ranked model</div>
                <div className="text-white font-mono text-sm">{topModel.name}</div>
                <div className="text-gray-400 text-xs mt-1">
                  {topModel.parameters_b}B parameters
                </div>
                <div className="text-green-400 text-xs mt-1">
                  tags: {topModel.tags.join(", ") || "none"}
                </div>
              </div>
              <div className="bg-gray-900/50 rounded-lg p-4">
                <div className="text-gray-400 text-xs uppercase mb-2">Measured profile</div>
                <div className="text-white font-mono text-sm">
                  {topModel.vram_mb.toLocaleString()} MB VRAM
                </div>
                <div className="text-gray-400 text-xs mt-1">
                  {topModel.tps} TPS
                </div>
                <div className="text-gray-400 text-xs mt-1">
                  success {(topModel.success_rate * 100).toFixed(0)}%
                </div>
              </div>
              <div className="bg-gray-900/50 rounded-lg p-4">
                <div className="text-gray-400 text-xs uppercase mb-2">Score</div>
                <div className="text-cyan-400 font-mono text-lg">
                  {topModel.score.toFixed(3)}
                </div>
                <div className="text-gray-400 text-xs mt-1">
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
