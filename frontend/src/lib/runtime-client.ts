import type {
  RuntimeInfo, RuntimeHealthInfo, RuntimeMetrics,
  RuntimeDetail, RuntimeDecisionInfo, RuntimePolicyInfo,
  RuntimeEvent, RuntimeControlAction,
} from "@/types/mission-control";

const API = (process.env.NEXT_PUBLIC_MC_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const PREFIX = "/api/hermes-os";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API}${PREFIX}${path}`, {
    headers: { "Content-Type": "application/json", Accept: "application/json", ...init?.headers },
    ...init,
  });
  if (!r.ok) throw new Error(`[${r.status}] ${path}: ${(await r.text().catch(() => r.statusText)).slice(0, 200)}`);
  return r.json() as Promise<T>;
}

export const RuntimeClient = {
  list: (): Promise<RuntimeInfo[]> => request("/runtimes"),
  get: (name: string): Promise<RuntimeDetail> => request(`/runtimes/${name}`),
  health: (name?: string): Promise<RuntimeHealthInfo[] | RuntimeHealthInfo> => request(name ? `/runtimes/${name}/health` : "/runtimes/health"),
  metrics: (name?: string): Promise<RuntimeMetrics[] | RuntimeMetrics> => request(name ? `/runtimes/${name}/metrics` : "/runtimes/metrics"),
  decisions: (): Promise<RuntimeDecisionInfo[]> => request("/runtimes/decisions"),
  decision: (name: string): Promise<RuntimeDecisionInfo> => request(`/runtimes/${name}/decision`),
  policies: (): Promise<RuntimePolicyInfo[]> => request("/runtimes/policies"),
  events: (runtime?: string, limit = 50): Promise<RuntimeEvent[]> => request(runtime ? `/runtimes/events?runtime=${runtime}&limit=${limit}` : `/runtimes/events?limit=${limit}`),
  refresh: (name: string): Promise<RuntimeControlAction> => request(`/runtimes/${name}/refresh`, { method: "POST" }),
  healthCheck: (name: string): Promise<RuntimeControlAction> => request(`/runtimes/${name}/health`, { method: "POST" }),
  resetCircuit: (name: string): Promise<RuntimeControlAction> => request(`/runtimes/${name}/circuit/reset`, { method: "POST" }),
  disable: (name: string): Promise<RuntimeControlAction> => request(`/runtimes/${name}/disable`, { method: "POST" }),
  enable: (name: string): Promise<RuntimeControlAction> => request(`/runtimes/${name}/enable`, { method: "POST" }),
  exportMetrics: (name?: string): Promise<Blob> => fetch(`${API}${PREFIX}/runtimes/${name ?? ""}/export`).then(r => r.blob()),
  exportEvents: (name?: string): Promise<Blob> => fetch(`${API}${PREFIX}/runtimes/${name ?? ""}/events/export`).then(r => r.blob()),

  sampleRuntimes: (): RuntimeInfo[] => [
    { name: "ollama", version: "0.5.0", healthy: true, status: "healthy", capabilities: ["chat", "chat_stream", "tools"], reliability_score: 0.95, performance_score: 0.88, success_rate: 97.2, executions: 1243, failures: 35, avg_latency_ms: 3200, last_execution: new Date().toISOString() },
    { name: "openai", version: "1.0.0", healthy: true, status: "healthy", capabilities: ["chat", "chat_stream", "tools", "vision"], reliability_score: 0.98, performance_score: 0.92, success_rate: 99.1, executions: 892, failures: 8, avg_latency_ms: 1800 },
    { name: "claude", version: "3.5", healthy: true, status: "healthy", capabilities: ["chat", "tools", "vision", "reasoning"], reliability_score: 0.97, performance_score: 0.94, success_rate: 98.5, executions: 567, failures: 9, avg_latency_ms: 2400 },
    { name: "vllm", version: "0.8.0", healthy: false, status: "degraded", capabilities: ["chat", "chat_stream"], reliability_score: 0.72, performance_score: 0.85, success_rate: 88.3, executions: 345, failures: 45, avg_latency_ms: 5600, last_execution: new Date(Date.now() - 300000).toISOString() },
    { name: "stub", version: "1.0.0", healthy: true, status: "available", capabilities: ["chat"], reliability_score: 1.0, performance_score: 0.5, success_rate: 100, executions: 234, failures: 0, avg_latency_ms: 50 },
  ],
  sampleDecisions: (): RuntimeDecisionInfo[] => [
    { runtime: "ollama", health_score: 95, reliability_score: 95, performance_score: 88, capability_score: 80, policy_score: 100, circuit_penalty: 0, final_score: 943, confidence: 0.94, reason: "Best local runtime with high reliability", candidate_scores: { ollama: 943, openai: 912, stub: 450 }, timestamp: new Date().toISOString() },
    { runtime: "openai", health_score: 100, reliability_score: 98, performance_score: 92, capability_score: 90, policy_score: 70, circuit_penalty: 0, final_score: 912, confidence: 0.91, reason: "Best cloud runtime with high performance", candidate_scores: { ollama: 850, openai: 912, claude: 905 }, timestamp: new Date(Date.now() - 60000).toISOString() },
  ],
  samplePolicies: (): RuntimePolicyInfo[] => [
    { id: "p1", name: "Local-first", enabled: true, priority: 10, description: "Prefer local runtimes when available", rules: [{ field: "type", operator: "eq", value: "local" }], runtimes_allowed: ["ollama", "vllm"], runtimes_denied: [], preference: "local" },
    { id: "p2", name: "High-reliability", enabled: true, priority: 8, description: "Minimum 90% reliability required", rules: [{ field: "reliability_score", operator: "gte", value: 0.9 }], runtimes_allowed: ["ollama", "openai", "claude"], runtimes_denied: ["vllm"], preference: "any" },
  ],
  sampleEvents: (): RuntimeEvent[] => [
    { id: "re1", type: "runtime.selected", runtime: "ollama", timestamp: new Date().toISOString(), severity: "INFO", message: "Runtime 'ollama' selected for chat task" },
    { id: "re2", type: "runtime.started", runtime: "ollama", timestamp: new Date(Date.now() - 5000).toISOString(), severity: "INFO", message: "Task started on ollama" },
    { id: "re3", type: "runtime.completed", runtime: "openai", timestamp: new Date(Date.now() - 15000).toISOString(), severity: "INFO", message: "Task completed on openai (2.4s)" },
    { id: "re4", type: "runtime.degraded", runtime: "vllm", timestamp: new Date(Date.now() - 60000).toISOString(), severity: "WARNING", message: "Runtime 'vllm' degraded: high latency (5.6s)" },
    { id: "re5", type: "runtime.circuit_opened", runtime: "vllm", timestamp: new Date(Date.now() - 120000).toISOString(), severity: "ERROR", message: "Circuit breaker opened for 'vllm' after 5 failures" },
  ],
};
