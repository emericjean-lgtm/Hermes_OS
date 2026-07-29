"use client";

import { Card, Badge } from "@/components/ui/card";

interface KTPanelProps {
  status?: KTransformersStatus;
  models?: KTModel[];
  benchmarks?: KTBenchmark[];
  onDiscover?: () => void;
  onBenchmark?: (modelId: string) => void;
  onLoad?: (modelId: string, backend: string) => void;
  onUnload?: (modelId: string) => void;
}

interface KTransformersStatus {
  kernel_available: boolean;
  cpu_variant: string;
  mode: string;
  loaded_models: number;
  kernel_error?: string;
}

interface KTModel {
  id: string;
  name: string;
  size_params: string;
  quantization: string;
  backend: string;
  status: string;
  architecture: string;
  size_gb: number;
  tags: string[];
}

interface KTBenchmark {
  task: string;
  tokens_per_second: number;
  success: boolean;
}

export function KTPanel({ status, models = [], benchmarks = [], onDiscover, onBenchmark, onLoad, onUnload }: KTPanelProps) {
  const kernelOk = status?.kernel_available ?? false;
  const cpu = status?.cpu_variant ?? "unknown";

  return (
    <div className="animate-fade-in">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-bold text-hermes-text font-mono">KTransformers</h2>
          <p className="text-xs text-hermes-muted mt-0.5">
            High-performance CPU-GPU heterogeneous inference
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant={kernelOk ? "success" : "warning"}>
            {kernelOk ? `KT-Kernel ${cpu}` : "Simulated"}
          </Badge>
          <button
            onClick={onDiscover}
            className="px-3 py-1.5 text-xs font-mono bg-hermes-amber/10 text-hermes-amber-bright border border-hermes-amber/30 rounded-lg hover:bg-hermes-amber/20 transition-colors"
          >
            Discover Models
          </button>
        </div>
      </div>

      {/* Kernel status */}
      <div className="grid grid-cols-4 gap-3 mb-4">
        <div className="bg-hermes-card border border-hermes-border rounded-lg p-3 text-center">
          <div className="text-xl font-bold font-mono text-hermes-amber-bright">{cpu.toUpperCase()}</div>
          <div className="text-[10px] text-hermes-muted font-mono uppercase mt-1">CPU Variant</div>
        </div>
        <div className="bg-hermes-card border border-hermes-border rounded-lg p-3 text-center">
          <div className="text-xl font-bold font-mono text-hermes-amber-bright">{models.length}</div>
          <div className="text-[10px] text-hermes-muted font-mono uppercase mt-1">Models</div>
        </div>
        <div className="bg-hermes-card border border-hermes-border rounded-lg p-3 text-center">
          <div className="text-xl font-bold font-mono text-hermes-amber-bright">
            {status?.loaded_models ?? 0}
          </div>
          <div className="text-[10px] text-hermes-muted font-mono uppercase mt-1">Loaded</div>
        </div>
        <div className="bg-hermes-card border border-hermes-border rounded-lg p-3 text-center">
          <div className={`text-xl font-bold font-mono ${kernelOk ? "text-hermes-green" : "text-hermes-amber"}`}>
            {status?.mode ?? "?"}
          </div>
          <div className="text-[10px] text-hermes-muted font-mono uppercase mt-1">Mode</div>
        </div>
      </div>

      {/* Model list */}
      <div className="grid gap-2 mb-4">
        {models.map((model) => (
          <div
            key={model.id}
            className="bg-hermes-card border border-hermes-border rounded-lg p-3 flex items-center justify-between"
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm font-medium text-hermes-text font-mono">{model.name}</span>
                <Badge variant={model.status === "loaded" ? "success" : model.status === "available" ? "info" : "default"}>
                  {model.status}
                </Badge>
                <Badge>{model.quantization}</Badge>
              </div>
              <div className="flex items-center gap-2 text-[10px] text-hermes-muted font-mono">
                <span>{model.size_params}</span>
                <span>·</span>
                <span>{model.architecture}</span>
                <span>·</span>
                <span>{model.backend}</span>
                {model.size_gb > 0 && <span>· {model.size_gb.toFixed(1)} GB</span>}
              </div>
              {model.tags?.length > 0 && (
                <div className="flex gap-1 mt-1">
                  {model.tags.map((t) => (
                    <span key={t} className="text-[9px] text-hermes-muted px-1 py-0.5 bg-hermes-bg rounded font-mono">{t}</span>
                  ))}
                </div>
              )}
            </div>
            <div className="flex gap-2 ml-3">
              <button
                onClick={() => onBenchmark?.(model.id)}
                className="px-2 py-1 text-[10px] font-mono text-hermes-blue border border-hermes-blue/30 rounded hover:bg-hermes-blue/10 transition-colors"
              >
                Benchmark
              </button>
              {model.status === "loaded" ? (
                <button
                  onClick={() => onUnload?.(model.id)}
                  className="px-2 py-1 text-[10px] font-mono text-hermes-red border border-hermes-red/30 rounded hover:bg-hermes-red/10 transition-colors"
                >
                  Unload
                </button>
              ) : (
                <button
                  onClick={() => onLoad?.(model.id, model.backend)}
                  className="px-2 py-1 text-[10px] font-mono text-hermes-amber border border-hermes-amber/30 rounded hover:bg-hermes-amber/10 transition-colors"
                >
                  Load
                </button>
              )}
            </div>
          </div>
        ))}
        {models.length === 0 && (
          <p className="text-xs text-hermes-muted py-4 text-center">
            No KT models discovered. Click "Discover Models" to scan.
          </p>
        )}
      </div>

      {/* Recent benchmarks */}
      {benchmarks.length > 0 && (
        <Card title="Recent Benchmarks">
          <div className="flex flex-col gap-1 max-h-[200px] overflow-y-auto">
            {benchmarks.slice(-10).map((b, i) => (
              <div key={i} className="flex items-center justify-between py-1 px-2 bg-hermes-bg rounded text-xs font-mono">
                <span className="text-hermes-text">{b.task}</span>
                <span className="text-hermes-amber">{b.tokens_per_second.toFixed(1)} t/s</span>
                <Badge variant={b.success ? "success" : "danger"}>
                  {b.success ? "OK" : "FAIL"}
                </Badge>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Kernel error info */}
      {status?.kernel_error && (
        <div className="mt-4 p-3 bg-hermes-red/10 border border-hermes-red/30 rounded-lg">
          <div className="text-xs text-hermes-red font-mono">
            kt-kernel not available: {status.kernel_error}
          </div>
          <div className="text-[10px] text-hermes-muted mt-1 font-mono">
            Install: pip install kt-kernel
          </div>
        </div>
      )}
    </div>
  );
}
