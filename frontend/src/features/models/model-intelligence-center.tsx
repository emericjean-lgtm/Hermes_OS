"use client";

import React, { useState, useCallback } from "react";

interface ModelData {
  model_id: string;
  name: string;
  score: number;
  parameters_b: number;
  vram_mb: number;
  tps: number;
  success_rate: number;
  tags: string[];
}

interface DecisionData {
  model_id: string;
  model_name: string;
  runtime: string;
  confidence: number;
  reason: string;
  estimated_vram_mb: number;
  alternatives: { name: string; score: number }[];
}

const MOCK_MODELS: ModelData[] = [
  { model_id: "qwen3-coder-30b", name: "Qwen3-Coder 30B", score: 0.92, parameters_b: 30, vram_mb: 18000, tps: 25, success_rate: 0.94, tags: ["code", "reasoning"] },
  { model_id: "deepseek-coder-16b", name: "DeepSeek Coder 16B", score: 0.88, parameters_b: 16, vram_mb: 10000, tps: 35, success_rate: 0.90, tags: ["code"] },
  { model_id: "codellama-7b", name: "CodeLlama 7B", score: 0.82, parameters_b: 7, vram_mb: 5000, tps: 45, success_rate: 0.87, tags: ["code"] },
  { model_id: "mistral-7b", name: "Mistral 7B", score: 0.79, parameters_b: 7, vram_mb: 5000, tps: 50, success_rate: 0.85, tags: ["general", "reasoning"] },
  { model_id: "llama3.2-3b", name: "Llama 3.2 3B", score: 0.71, parameters_b: 3, vram_mb: 2000, tps: 80, success_rate: 0.82, tags: ["general", "lightweight"] },
];

const MOCK_DECISIONS: DecisionData[] = [
  { model_id: "qwen3-coder-30b", model_name: "Qwen3-Coder 30B", runtime: "ktransformers", confidence: 0.94, reason: "Excellent task fit (95%) · High reliability (94%)", estimated_vram_mb: 16200, alternatives: [{ name: "DeepSeek Coder 16B", score: 0.85 }, { name: "CodeLlama 7B", score: 0.76 }] },
  { model_id: "deepseek-coder-16b", model_name: "DeepSeek Coder 16B", runtime: "ollama", confidence: 0.88, reason: "Good task fit (90%) · Fast inference", estimated_vram_mb: 10000, alternatives: [{ name: "CodeLlama 7B", score: 0.82 }, { name: "Qwen3-Coder 30B", score: 0.79 }] },
];

export default function ModelIntelligenceCenter() {
  const [activeTab, setActiveTab] = useState("ranking");
  const [taskInput, setTaskInput] = useState("");
  const [recommendation, setRecommendation] = useState<DecisionData | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  const handleRecommend = useCallback(async () => {
    if (!taskInput.trim()) return;
    setIsProcessing(true);
    await new Promise((r) => setTimeout(r, 600 + Math.random() * 400));
    setRecommendation(MOCK_DECISIONS[0]);
    setIsProcessing(false);
  }, [taskInput]);

  const handleBenchmark = useCallback(async () => {
    setIsProcessing(true);
    await new Promise((r) => setTimeout(r, 1500));
    setIsProcessing(false);
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Model Intelligence</h1>
          <p className="text-gray-400 text-sm mt-1">Adaptive model routing & performance intelligence</p>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className="text-gray-400">{MOCK_MODELS.length} modèles</span>
          <span className="text-cyan-400 font-medium">Score ∅ 0.82</span>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-800/50 rounded-lg p-1">
        {["ranking", "recommend", "benchmark", "optimizer"].map((tab) => (
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
                {MOCK_MODELS.map((m, i) => (
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
                      <span className="text-green-400 font-mono">{(m.success_rate * 100).toFixed(0)}%</span>
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
        </div>
      )}

      {/* Recommend Tab */}
      {activeTab === "recommend" && (
        <div className="space-y-4">
          <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-5">
            <h2 className="text-lg font-semibold text-white mb-4">Model Recommender</h2>
            <div className="flex gap-3">
              <input
                type="text"
                value={taskInput}
                onChange={(e) => setTaskInput(e.target.value)}
                placeholder="Describe your task... (e.g., 'Create a FastAPI REST API with authentication')"
                className="flex-1 bg-gray-900/50 border border-gray-700 rounded-lg px-4 py-3 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500/50"
              />
              <button
                onClick={handleRecommend}
                disabled={!taskInput.trim() || isProcessing}
                className="px-5 py-3 bg-cyan-500/20 text-cyan-300 rounded-lg text-sm font-medium hover:bg-cyan-500/30 transition-all disabled:opacity-30"
              >
                {isProcessing ? "..." : "Recommend"}
              </button>
            </div>
          </div>

          {recommendation && (
            <div className="bg-gray-800/60 border border-cyan-500/30 rounded-lg p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-white font-semibold">Recommended Configuration</h3>
                <span className="px-2 py-1 bg-cyan-500/20 text-cyan-300 rounded text-xs font-medium">
                  {recommendation.runtime}
                </span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <div>
                  <div className="text-gray-400 text-xs uppercase">Model</div>
                  <div className="text-white font-medium">{recommendation.model_name}</div>
                </div>
                <div>
                  <div className="text-gray-400 text-xs uppercase">Confidence</div>
                  <div className="text-cyan-400 font-mono">{(recommendation.confidence * 100).toFixed(0)}%</div>
                </div>
                <div>
                  <div className="text-gray-400 text-xs uppercase">Estimated VRAM</div>
                  <div className="text-white font-mono">{recommendation.estimated_vram_mb.toLocaleString()} MB</div>
                </div>
                <div>
                  <div className="text-gray-400 text-xs uppercase">Alternatives</div>
                  <div className="text-gray-300 text-sm">
                    {recommendation.alternatives.map((a) => a.name).join(", ")}
                  </div>
                </div>
              </div>
              <div className="bg-gray-900/50 rounded-lg p-3">
                <div className="text-gray-400 text-xs uppercase mb-1">Reason</div>
                <div className="text-gray-200 text-sm">{recommendation.reason}</div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Benchmark Tab */}
      {activeTab === "benchmark" && (
        <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Benchmarks</h2>
            <button
              onClick={handleBenchmark}
              disabled={isProcessing}
              className="px-4 py-2 bg-cyan-500/20 text-cyan-300 rounded-lg text-sm hover:bg-cyan-500/30 transition-all disabled:opacity-30"
            >
              {isProcessing ? "Running..." : "Run Full Benchmark"}
            </button>
          </div>
          <div className="text-gray-400 text-sm">
            {isProcessing
              ? "Benchmarking all models on all task types..."
              : "Run benchmarks to evaluate model performance across different task types."}
          </div>
        </div>
      )}

      {/* Optimizer Tab */}
      {activeTab === "optimizer" && (
        <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-5">
          <h2 className="text-lg font-semibold text-white mb-4">Runtime Optimizer</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-gray-900/50 rounded-lg p-4">
              <div className="text-gray-400 text-xs uppercase mb-2">Model + Runtime</div>
              <div className="text-white font-mono text-sm">Qwen3-Coder 30B</div>
              <div className="text-gray-400 text-xs mt-1">KTransformers · Q4_K_M</div>
              <div className="text-green-400 text-xs mt-1">Best match: code_generation</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-4">
              <div className="text-gray-400 text-xs uppercase mb-2">Estimated Performance</div>
              <div className="text-white font-mono text-sm">16,200 MB VRAM</div>
              <div className="text-gray-400 text-xs mt-1">35.0 TPS · 142ms latency</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-4">
              <div className="text-gray-400 text-xs uppercase mb-2">Efficiency Score</div>
              <div className="text-cyan-400 font-mono text-lg">0.87</div>
              <div className="text-gray-400 text-xs mt-1">Top 1 of 12 configurations</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
