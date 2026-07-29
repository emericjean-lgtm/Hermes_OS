"use client";

import { useState } from "react";
import { Card, Badge } from "@/components/ui/card";
import {
  Activity,
  Code2,
  Bug,
  Search,
  FileEdit,
  Play,
  Zap,
  GitBranch,
  Boxes,
} from "lucide-react";

// ── Types ─────────────────────────────────────────────────

interface OhMyPiStatus {
  installed: boolean;
  version: string | null;
  server_bound: boolean;
  lsp_available: boolean;
  dap_available: boolean;
  tools_count: number;
  capabilities: string[];
  client_stats: {
    total_executions: number;
    success_count: number;
    failure_count: number;
    timeout_count: number;
    success_rate: number;
    avg_duration_ms: number;
    installed: boolean;
    version: string | null;
  };
}

interface OhMyPiCapability {
  name: string;
  description: string;
  category: string;
  requires_workspace: boolean;
  requires_sandbox: boolean;
}

interface OhMyPiExecutionResult {
  id: string;
  action: string;
  status: string;
  data: unknown;
  error: string;
  duration_ms: number;
  success: boolean;
}

interface OhMyPiPanelProps {
  onExecute?: (action: string, params: Record<string, unknown>) => Promise<OhMyPiExecutionResult>;
  status?: OhMyPiStatus;
}

// ── Capability icons ──────────────────────────────────────

const CAPABILITY_ICONS: Record<string, React.ReactNode> = {
  lsp: <Code2 className="w-3.5 h-3.5" />,
  dap: <Bug className="w-3.5 h-3.5" />,
  ast: <Boxes className="w-3.5 h-3.5" />,
  execution: <Play className="w-3.5 h-3.5" />,
  search: <Search className="w-3.5 h-3.5" />,
  edit: <FileEdit className="w-3.5 h-3.5" />,
  git: <GitBranch className="w-3.5 h-3.5" />,
};

const CAPABILITY_COLORS: Record<string, string> = {
  lsp: "text-hermes-blue",
  dap: "text-orange-400",
  ast: "text-hermes-purple",
  execution: "text-hermes-green",
  search: "text-hermes-amber",
  edit: "text-hermes-red",
  git: "text-emerald-400",
};

// ── Mock capabilities ─────────────────────────────────────

const MOCK_CAPABILITIES: OhMyPiCapability[] = [
  {
    name: "lsp_open_file",
    description: "Open a file for LSP analysis — get diagnostics, symbols, and references",
    category: "lsp",
    requires_workspace: true,
    requires_sandbox: true,
  },
  {
    name: "lsp_edit",
    description: "Edit a file with LSP-aware precision — policy-gated write operation",
    category: "edit",
    requires_workspace: true,
    requires_sandbox: true,
  },
  {
    name: "ast_transform",
    description: "Transform code using tree-sitter AST — safe structural changes",
    category: "ast",
    requires_workspace: true,
    requires_sandbox: true,
  },
  {
    name: "debug_start",
    description: "Start a DAP debug session with breakpoints",
    category: "dap",
    requires_workspace: false,
    requires_sandbox: false,
  },
  {
    name: "debug_step",
    description: "Step through execution — step over, into, out, continue",
    category: "dap",
    requires_workspace: false,
    requires_sandbox: false,
  },
  {
    name: "execute_python",
    description: "Execute Python code in a sandboxed environment",
    category: "execution",
    requires_workspace: false,
    requires_sandbox: true,
  },
  {
    name: "execute_javascript",
    description: "Execute JavaScript code in a sandboxed environment",
    category: "execution",
    requires_workspace: false,
    requires_sandbox: true,
  },
  {
    name: "git_operation",
    description: "Perform git operations — branch, commit, diff",
    category: "git",
    requires_workspace: true,
    requires_sandbox: true,
  },
  {
    name: "code_search",
    description: "Search codebase using Oh My Pi's indexed knowledge",
    category: "search",
    requires_workspace: false,
    requires_sandbox: false,
  },
];

// ── Component ─────────────────────────────────────────────

export function OhMyPiPanel({ onExecute, status }: OhMyPiPanelProps) {
  const [selectedAction, setSelectedAction] = useState<string>("");
  const [input, setInput] = useState("");
  const [result, setResult] = useState<OhMyPiExecutionResult | null>(null);
  const [executing, setExecuting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const capabilities = MOCK_CAPABILITIES;

  const handleExecute = async () => {
    if (!selectedAction || !onExecute) return;
    setExecuting(true);
    setError(null);
    setResult(null);

    try {
      const params: Record<string, unknown> = { input, file: input };
      const res = await onExecute(selectedAction, params);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setExecuting(false);
    }
  };

  const selectedCap = capabilities.find((c) => c.name === selectedAction);

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-bold text-hermes-text font-mono">
            Oh My Pi
          </h2>
          <p className="text-xs text-hermes-muted mt-0.5">
            LSP · DAP · AST · Code Execution — agentic coding via MCP
          </p>
        </div>
        <div className="flex items-center gap-2">
          {status?.lsp_available && (
            <Badge variant="success" className="text-[10px]">
              <Code2 className="w-3 h-3 mr-1" />
              LSP
            </Badge>
          )}
          {status?.dap_available && (
            <Badge variant="success" className="text-[10px]">
              <Bug className="w-3 h-3 mr-1" />
              DAP
            </Badge>
          )}
          <Badge variant={status?.installed ? "success" : "warning"}>
            <Activity className="w-3 h-3 mr-1" />
            {status?.installed ? "Connected" : "Offline"}
          </Badge>
        </div>
      </div>

      {/* Stats row */}
      {status?.client_stats && (
        <div className="grid grid-cols-4 gap-2 mb-4">
          {[
            { label: "Executions", value: status.client_stats.total_executions },
            { label: "Success Rate", value: `${status.client_stats.success_rate.toFixed(1)}%` },
            { label: "Avg Latency", value: `${status.client_stats.avg_duration_ms.toFixed(0)}ms` },
            { label: "Failures", value: status.client_stats.failure_count },
          ].map((stat) => (
            <div
              key={stat.label}
              className="bg-hermes-card border border-hermes-border rounded-lg p-2 text-center"
            >
              <div className="text-[10px] text-hermes-muted font-mono uppercase">
                {stat.label}
              </div>
              <div className="text-sm font-bold text-hermes-text font-mono mt-0.5">
                {stat.value}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Capability grid */}
      <Card title="MCP Tools" className="mb-4">
        <div className="grid grid-cols-1 gap-2">
          {capabilities.map((cap) => {
            const isSelected = selectedAction === cap.name;
            return (
              <button
                key={cap.name}
                onClick={() => {
                  setSelectedAction(cap.name);
                  setResult(null);
                  setError(null);
                }}
                className={`flex items-start gap-3 p-3 rounded-lg border text-left transition-all ${
                  isSelected
                    ? "border-hermes-amber/50 bg-hermes-amber/5"
                    : "border-hermes-border hover:border-hermes-border/70 hover:bg-hermes-card/80"
                }`}
              >
                <div
                  className={`mt-0.5 ${CAPABILITY_COLORS[cap.category] || "text-hermes-muted"}`}
                >
                  {CAPABILITY_ICONS[cap.category] || (
                    <Activity className="w-3.5 h-3.5" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-sm font-medium text-hermes-text font-mono">
                      {cap.name}
                    </span>
                    <span className="text-[9px] text-hermes-muted px-1 py-0 bg-hermes-bg rounded font-mono uppercase">
                      {cap.category}
                    </span>
                    {cap.requires_workspace && (
                      <Badge variant="default" className="text-[10px] px-1.5 py-0">
                        workspace
                      </Badge>
                    )}
                    {cap.requires_sandbox && (
                      <Badge variant="default" className="text-[10px] px-1.5 py-0">
                        sandbox
                      </Badge>
                    )}
                  </div>
                  <p className="text-[11px] text-hermes-muted line-clamp-2">
                    {cap.description}
                  </p>
                </div>
              </button>
            );
          })}
        </div>
      </Card>

      {/* Execution area */}
      {selectedAction && (
        <Card
          title={`Execute: ${selectedAction}`}
          className="mb-4"
          action={
            <button
              onClick={handleExecute}
              disabled={executing || !onExecute}
              className="px-3 py-1.5 text-xs font-mono bg-hermes-amber/10 text-hermes-amber-bright border border-hermes-amber/30 rounded-lg hover:bg-hermes-amber/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
            >
              <Play className="w-3 h-3" />
              {executing ? "Running..." : "Execute"}
            </button>
          }
        >
          <div className="space-y-3">
            <div>
              <label className="text-[10px] text-hermes-muted font-mono uppercase mb-1 block">
                {selectedCap?.category === "lsp" ? "File path" :
                 selectedCap?.category === "execution" ? "Code" :
                 selectedCap?.category === "dap" ? "File" :
                 selectedCap?.category === "search" ? "Query" :
                 "Input"}
              </label>
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={
                  selectedCap?.category === "lsp" ? "e.g., src/app.py" :
                  selectedCap?.category === "execution" ? "print('hello')" :
                  selectedCap?.category === "dap" ? "e.g., src/app.py:42" :
                  selectedCap?.category === "search" ? "e.g., authenticate" :
                  "Enter input..."
                }
                className="w-full bg-hermes-bg border border-hermes-border rounded-lg px-3 py-2 text-sm text-hermes-text font-mono focus:outline-none focus:border-hermes-amber/50 placeholder:text-hermes-muted/50"
              />
            </div>

            {result && (
              <div className="bg-hermes-bg rounded-lg border border-hermes-border p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-mono text-hermes-muted">
                    Result
                  </span>
                  <div className="flex items-center gap-2">
                    <Badge
                      variant={
                        result.success
                          ? "success"
                          : result.status === "timeout"
                            ? "warning"
                            : "danger"
                      }
                    >
                      {result.status}
                    </Badge>
                    <span className="text-[10px] text-hermes-muted font-mono">
                      {result.duration_ms.toFixed(1)}ms
                    </span>
                  </div>
                </div>
                <pre className="text-xs text-hermes-text font-mono whitespace-pre-wrap break-all max-h-[200px] overflow-y-auto">
                  {result.data
                    ? JSON.stringify(result.data, null, 2)
                    : result.error || "(no output)"}
                </pre>
              </div>
            )}

            {error && (
              <div className="bg-hermes-red/10 border border-hermes-red/30 rounded-lg p-3">
                <div className="text-xs text-hermes-red font-mono">{error}</div>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Integration pipeline */}
      <Card title="Deep Integration Pipeline" className="mb-4">
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: "LSP Bridge", desc: "Symbols → KG", icon: Code2, color: "text-hermes-blue" },
            { label: "AST Adapter", desc: "Tree-sitter → Nodes", icon: Boxes, color: "text-hermes-purple" },
            { label: "Debug Adapter", desc: "DAP → EventBus", icon: Bug, color: "text-orange-400" },
            { label: "Workspace Adapter", desc: "Edits → Sandbox", icon: GitBranch, color: "text-emerald-400" },
            { label: "Runtime Adapter", desc: "Suitability scoring", icon: Zap, color: "text-hermes-amber" },
            { label: "Memory Adapter", desc: "Experience → Episodic", icon: Activity, color: "text-hermes-green" },
          ].map((item) => (
            <div
              key={item.label}
              className="flex items-center gap-2 p-2 bg-hermes-bg rounded-lg border border-hermes-border/50"
            >
              <item.icon className={`w-3.5 h-3.5 ${item.color}`} />
              <div>
                <div className="text-[10px] text-hermes-text font-mono">{item.label}</div>
                <div className="text-[9px] text-hermes-muted">{item.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Hermes ↔ Oh My Pi flow */}
      <Card title="Agentic Coding Flow" className="mb-4">
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2 text-xs font-mono text-hermes-muted">
            <span className="text-hermes-purple">Agent</span>
            <span>→</span>
            <span className="text-hermes-blue">Tool Router</span>
            <span>→</span>
            <span className="text-hermes-pink">Oh My Pi MCP</span>
            <span>→</span>
            <span className="text-hermes-amber">omp CLI</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {[
              "Policy Engine", "Tool Sandbox", "Workspace Mgr",
              "Event Bus", "Knowledge Graph", "LSP Bridge",
              "AST Adapter", "Debug Adapter",
            ].map((label) => (
              <span
                key={label}
                className="text-[9px] text-hermes-muted px-1.5 py-0.5 bg-hermes-bg rounded font-mono border border-hermes-border/50"
              >
                {label}
              </span>
            ))}
          </div>
        </div>
      </Card>

      {/* Quick actions */}
      <div className="grid grid-cols-4 gap-2">
        <button
          onClick={() => {
            setSelectedAction("lsp_open_file");
            setInput(".");
            setResult(null);
            setError(null);
          }}
          className="p-3 bg-hermes-card border border-hermes-border rounded-lg hover:border-hermes-blue/50 hover:bg-hermes-blue/5 transition-all text-center"
        >
          <Code2 className="w-4 h-4 mx-auto mb-1 text-hermes-blue" />
          <span className="text-[10px] font-mono text-hermes-muted">LSP Analyze</span>
        </button>
        <button
          onClick={() => {
            setSelectedAction("debug_start");
            setInput("");
            setResult(null);
            setError(null);
          }}
          className="p-3 bg-hermes-card border border-hermes-border rounded-lg hover:border-orange-400/50 hover:bg-orange-400/5 transition-all text-center"
        >
          <Bug className="w-4 h-4 mx-auto mb-1 text-orange-400" />
          <span className="text-[10px] font-mono text-hermes-muted">Debug</span>
        </button>
        <button
          onClick={() => {
            setSelectedAction("execute_python");
            setInput("");
            setResult(null);
            setError(null);
          }}
          className="p-3 bg-hermes-card border border-hermes-border rounded-lg hover:border-hermes-green/50 hover:bg-hermes-green/5 transition-all text-center"
        >
          <Play className="w-4 h-4 mx-auto mb-1 text-hermes-green" />
          <span className="text-[10px] font-mono text-hermes-muted">Run Python</span>
        </button>
        <button
          onClick={() => {
            setSelectedAction("ast_transform");
            setInput("");
            setResult(null);
            setError(null);
          }}
          className="p-3 bg-hermes-card border border-hermes-border rounded-lg hover:border-hermes-purple/50 hover:bg-hermes-purple/5 transition-all text-center"
        >
          <Boxes className="w-4 h-4 mx-auto mb-1 text-hermes-purple" />
          <span className="text-[10px] font-mono text-hermes-muted">AST Transform</span>
        </button>
      </div>
    </div>
  );
}
