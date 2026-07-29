"use client";

import { useState } from "react";
import { Card, Badge } from "@/components/ui/card";
import {
  Activity,
  Code2,
  Play,
  Search,
  FileEdit,
  FileSearch,
  ShieldCheck,
  Bug,
} from "lucide-react";

// ── Types ─────────────────────────────────────────────────

interface KlaatCodeStatus {
  installed: boolean;
  version: string | null;
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
  server_bound: boolean;
}

interface KlaatCodeCapability {
  name: string;
  description: string;
  inputs: string[];
  outputs: string[];
  requires_git: boolean;
  requires_project: boolean;
}

interface KlaatCodeExecutionResult {
  id: string;
  status: string;
  data: unknown;
  error: string;
  duration_ms: number;
  success: boolean;
}

interface KlaatCodePanelProps {
  onAnalyze?: (path: string) => Promise<KlaatCodeExecutionResult>;
  onDiagnostics?: (file: string) => Promise<KlaatCodeExecutionResult>;
  onSearch?: (query: string) => Promise<KlaatCodeExecutionResult>;
  onInspect?: (file: string) => Promise<KlaatCodeExecutionResult>;
  onPlan?: (prompt: string) => Promise<KlaatCodeExecutionResult>;
  onValidate?: (file: string) => Promise<KlaatCodeExecutionResult>;
  onEdit?: (file: string, content: string) => Promise<KlaatCodeExecutionResult>;
}

// ── Capability icons ──────────────────────────────────────

const CAPABILITY_ICONS: Record<string, React.ReactNode> = {
  analyze_project: <FileSearch className="w-3.5 h-3.5" />,
  inspect_code: <Search className="w-3.5 h-3.5" />,
  generate_code_plan: <Code2 className="w-3.5 h-3.5" />,
  edit_file: <FileEdit className="w-3.5 h-3.5" />,
  search_code: <Search className="w-3.5 h-3.5" />,
  run_diagnostics: <Bug className="w-3.5 h-3.5" />,
  validate_changes: <ShieldCheck className="w-3.5 h-3.5" />,
};

const CAPABILITY_COLORS: Record<string, string> = {
  analyze_project: "text-hermes-blue",
  inspect_code: "text-hermes-purple",
  generate_code_plan: "text-hermes-amber",
  edit_file: "text-hermes-red",
  search_code: "text-hermes-green",
  run_diagnostics: "text-orange-400",
  validate_changes: "text-emerald-400",
};

// ── Mock data for development ─────────────────────────────

const MOCK_CAPABILITIES: KlaatCodeCapability[] = [
  {
    name: "analyze_project",
    description: "Analyze a code project structure, language, framework, and dependencies",
    inputs: ["path"],
    outputs: ["project"],
    requires_git: true,
    requires_project: true,
  },
  {
    name: "inspect_code",
    description: "Inspect a specific file or symbol within the project",
    inputs: ["file", "symbol"],
    outputs: ["file_info"],
    requires_git: false,
    requires_project: true,
  },
  {
    name: "generate_code_plan",
    description: "Generate a code plan from a natural-language prompt",
    inputs: ["prompt"],
    outputs: ["plan"],
    requires_git: false,
    requires_project: true,
  },
  {
    name: "edit_file",
    description: "Edit a file in the workspace (policy-gated write operation)",
    inputs: ["file", "content"],
    outputs: ["result"],
    requires_git: false,
    requires_project: true,
  },
  {
    name: "search_code",
    description: "Search across the codebase using KlaatCode's Knowledge Graph",
    inputs: ["query"],
    outputs: ["results"],
    requires_git: false,
    requires_project: true,
  },
  {
    name: "run_diagnostics",
    description: "Run linter/typechecker diagnostics on a file",
    inputs: ["file"],
    outputs: ["diagnostics"],
    requires_git: false,
    requires_project: true,
  },
  {
    name: "validate_changes",
    description: "Validate recent changes for correctness and style",
    inputs: ["file"],
    outputs: ["validation"],
    requires_git: false,
    requires_project: true,
  },
];

// ── Component ─────────────────────────────────────────────

export function KlaatCodePanel({
  onAnalyze,
  onDiagnostics,
  onSearch,
  onInspect,
  onPlan,
  onValidate,
  onEdit,
}: KlaatCodePanelProps) {
  const [selectedAction, setSelectedAction] = useState<string>("");
  const [input, setInput] = useState("");
  const [result, setResult] = useState<KlaatCodeExecutionResult | null>(null);
  const [executing, setExecuting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const capabilities = MOCK_CAPABILITIES;

  const handleExecute = async () => {
    if (!selectedAction) return;
    setExecuting(true);
    setError(null);
    setResult(null);

    try {
      let res: KlaatCodeExecutionResult | undefined;
      switch (selectedAction) {
        case "analyze_project":
          res = await onAnalyze?.(input || ".");
          break;
        case "run_diagnostics":
          res = await onDiagnostics?.(input || ".");
          break;
        case "search_code":
          res = await onSearch?.(input);
          break;
        case "inspect_code":
          res = await onInspect?.(input);
          break;
        case "generate_code_plan":
          res = await onPlan?.(input);
          break;
        case "validate_changes":
          res = await onValidate?.(input);
          break;
        case "edit_file":
          res = await onEdit?.(input, "");
          break;
      }
      if (res) setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setExecuting(false);
    }
  };

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-bold text-hermes-text font-mono">
            KlaatCode
          </h2>
          <p className="text-xs text-hermes-muted mt-0.5">
            Agentic coding environment via MCP — analyze, plan, edit, validate
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="success">
            <Activity className="w-3 h-3 mr-1" />
            MCP Connected
          </Badge>
        </div>
      </div>

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
                  className={`mt-0.5 ${CAPABILITY_COLORS[cap.name] || "text-hermes-muted"}`}
                >
                  {CAPABILITY_ICONS[cap.name] || (
                    <Activity className="w-3.5 h-3.5" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-sm font-medium text-hermes-text font-mono">
                      {cap.name}
                    </span>
                    {cap.requires_git && (
                      <Badge variant="default" className="text-[10px] px-1.5 py-0">
                        git
                      </Badge>
                    )}
                    {!cap.requires_project ? null : (
                      <Badge variant="default" className="text-[10px] px-1.5 py-0">
                        project
                      </Badge>
                    )}
                  </div>
                  <p className="text-[11px] text-hermes-muted line-clamp-2">
                    {cap.description}
                  </p>
                  <div className="flex gap-1 mt-1">
                    {cap.inputs.map((inp) => (
                      <span
                        key={inp}
                        className="text-[9px] text-hermes-blue px-1 py-0.5 bg-hermes-blue/5 rounded font-mono"
                      >
                        ← {inp}
                      </span>
                    ))}
                  </div>
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
              disabled={executing}
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
                {capabilities.find((c) => c.name === selectedAction)
                  ?.inputs[0] || "Input"}
              </label>
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={
                  capabilities.find((c) => c.name === selectedAction)
                    ?.inputs[0] === "path"
                    ? "e.g., /home/project"
                    : capabilities.find((c) => c.name === selectedAction)
                        ?.inputs[0] === "query"
                      ? "e.g., authentication"
                      : capabilities.find((c) => c.name === selectedAction)
                            ?.inputs[0] === "prompt"
                        ? "e.g., Add a login page with OAuth"
                        : capabilities.find((c) => c.name === selectedAction)
                              ?.inputs[0] === "file"
                          ? "e.g., src/app.ts"
                          : "Enter input..."
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

      {/* Hermes integration info */}
      <Card title="Integration Pipeline" className="mb-4">
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2 text-xs font-mono text-hermes-muted">
            <span className="text-hermes-purple">Agent</span>
            <span>→</span>
            <span className="text-hermes-blue">Tool Router</span>
            <span>→</span>
            <span className="text-hermes-amber">KlaatCode MCP</span>
            <span>→</span>
            <span className="text-hermes-green">KlaatCode CLI</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {[
              "Policy Engine",
              "Tool Sandbox",
              "Workspace Mgr",
              "Event Bus",
              "Knowledge Graph",
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
      <div className="grid grid-cols-3 gap-2">
        <button
          onClick={() => {
            setSelectedAction("analyze_project");
            setInput(".");
            setResult(null);
            setError(null);
          }}
          className="p-3 bg-hermes-card border border-hermes-border rounded-lg hover:border-hermes-blue/50 hover:bg-hermes-blue/5 transition-all text-center"
        >
          <FileSearch className="w-4 h-4 mx-auto mb-1 text-hermes-blue" />
          <span className="text-[10px] font-mono text-hermes-muted">
            Analyze Project
          </span>
        </button>
        <button
          onClick={() => {
            setSelectedAction("run_diagnostics");
            setInput(".");
            setResult(null);
            setError(null);
          }}
          className="p-3 bg-hermes-card border border-hermes-border rounded-lg hover:border-orange-400/50 hover:bg-orange-400/5 transition-all text-center"
        >
          <Bug className="w-4 h-4 mx-auto mb-1 text-orange-400" />
          <span className="text-[10px] font-mono text-hermes-muted">
            Diagnostics
          </span>
        </button>
        <button
          onClick={() => {
            setSelectedAction("validate_changes");
            setInput("");
            setResult(null);
            setError(null);
          }}
          className="p-3 bg-hermes-card border border-hermes-border rounded-lg hover:border-emerald-400/50 hover:bg-emerald-400/5 transition-all text-center"
        >
          <ShieldCheck className="w-4 h-4 mx-auto mb-1 text-emerald-400" />
          <span className="text-[10px] font-mono text-hermes-muted">
            Validate
          </span>
        </button>
      </div>
    </div>
  );
}
