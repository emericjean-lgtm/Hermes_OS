"use client";

import { useState } from "react";
import { Card, Badge, StatCard, Beacon } from "@/components/ui/card";
import { CenterHeader, PanelLoading } from "@/components/center-scaffold";
import {
  useCodeIntelligenceStatus,
  useCodeIntelligenceProviders,
  useCodeIntelligenceHistory,
  useRunCodeIntelligenceTask,
} from "@/hooks/use-api";
import type {
  CodeIntelligenceTaskKind,
  CodeIntelligenceTaskRequest,
} from "@/services/client";
import type {
  CodeIntelligenceExternalProviderStatusDTO,
  CodeIntelligenceTaskResultDTO,
  MCPStatusValue,
} from "@/types/hermes";
import {
  Brain, Cpu, Sparkles, ListChecks, History as HistoryIcon,
  CheckCircle2, XCircle, PlayCircle, Route,
} from "lucide-react";

/**
 * Code Intelligence Center (R-006 Phase 8).
 *
 * The previous version showed a client-side-computed routing decision —
 * Hermes exposed no `/api/v1/code-intelligence` route at all, so nothing
 * real could be displayed (R-002). That surface now exists
 * (backend/api/routes/code_intelligence.py, wired onto the real
 * CodeIntelligenceAgent — R-006 Phases 1-4). Every panel here reads from it.
 *
 * KlaatCode/Oh My Pi's own CLI integrations were found, during this
 * rebuild's verification pass, to be genuinely broken independent of
 * Hermes's wiring — see docs/release/R-006_CODE_INTELLIGENCE_VALIDATION.md.
 * That is a real, disclosed limitation, not something this UI papers over:
 * a task routed to either provider can fail with a real CLI error, and this
 * page shows that error rather than hiding it.
 */

const TASK_KINDS: { kind: CodeIntelligenceTaskKind; label: string }[] = [
  { kind: "analyze", label: "Analyze" },
  { kind: "review", label: "Review" },
  { kind: "debug", label: "Debug" },
  { kind: "explain", label: "Explain" },
];

const PROVIDER_CHOICES: { value: string; label: string }[] = [
  { value: "", label: "Auto" },
  { value: "hermes_native", label: "Hermes Native" },
  { value: "klaatcode", label: "KlaatCode" },
  { value: "ohmypi", label: "Oh My Pi" },
];

const mcpStatusVariant: Record<MCPStatusValue, "success" | "warning" | "danger" | "default"> = {
  connected: "success",
  disconnected: "warning",
  unbound: "warning",
  unavailable: "danger",
  not_configured: "default",
};

export function CodeIntelligenceCenter() {
  const status = useCodeIntelligenceStatus();
  const providers = useCodeIntelligenceProviders();
  const history = useCodeIntelligenceHistory(20);
  const runTask = useRunCodeIntelligenceTask();

  const [taskKind, setTaskKind] = useState<CodeIntelligenceTaskKind>("analyze");
  const [forceProvider, setForceProvider] = useState("");
  const [projectPath, setProjectPath] = useState(".");
  const [instruction, setInstruction] = useState("");
  const [code, setCode] = useState("");
  const [lastResult, setLastResult] = useState<CodeIntelligenceTaskResultDTO | null>(null);

  const s = status.data;
  const p = providers.data;

  const activeProvider = s
    ? (Object.entries({
        klaatcode: s.klaatcode_tasks,
        ohmypi: s.ohmypi_tasks,
        hermes_native: s.hermes_native_tasks,
        hybrid: s.hybrid_tasks,
      }).sort((a, b) => b[1] - a[1])[0]?.[1] ?? 0) > 0
      ? Object.entries({
          klaatcode: s.klaatcode_tasks,
          ohmypi: s.ohmypi_tasks,
          hermes_native: s.hermes_native_tasks,
          hybrid: s.hybrid_tasks,
        }).sort((a, b) => b[1] - a[1])[0][0]
      : "—"
    : "—";

  const runDisabled = runTask.isPending || !status.data?.is_available;

  const submit = () => {
    const body: CodeIntelligenceTaskRequest = {
      project_path: projectPath,
      parameters: {
        ...(instruction ? { instruction } : {}),
        ...(code ? { code } : {}),
      },
      ...(forceProvider ? { force_provider: forceProvider } : {}),
    };
    runTask.mutate(
      { kind: taskKind, body },
      { onSuccess: (result) => setLastResult(result) },
    );
  };

  return (
    <div className="animate-fade-in p-6">
      <CenterHeader
        title="Code Intelligence"
        subtitle={s ? `${s.agent_id} — ${s.status}` : "Routage entre Hermes Native, KlaatCode et Oh My Pi"}
        right={
          s ? (
            <Badge variant={s.is_available ? "success" : "warning"}>
              <Beacon tone={s.is_available ? "green" : "amber"} className="mr-1" />
              {s.is_available ? "Ready" : s.status}
            </Badge>
          ) : undefined
        }
      />

      {/* ── Overview ──────────────────────────────────────── */}
      {status.isLoading ? (
        <PanelLoading />
      ) : status.isError || !s ? (
        <Card title="Overview" className="mb-6">
          <p className="text-xs text-hermes-red font-mono">/code-intelligence/status unreachable</p>
        </Card>
      ) : (
        <div className="grid grid-cols-4 gap-4 mb-6">
          <StatCard index={0} label="Tâches traitées" value={s.total_tasks}
            icon={<ListChecks size={15} />} trend={s.total_tasks > 0 ? "up" : "neutral"} />
          <StatCard index={1} label="Taux de succès" value={`${s.success_rate.toFixed(0)}%`}
            icon={<CheckCircle2 size={15} />}
            trend={s.success_rate >= 60 ? "up" : s.total_tasks === 0 ? "neutral" : "down"} />
          <StatCard index={2} label="Provider actif" value={activeProvider}
            icon={<Route size={15} />} trend="neutral" />
          <StatCard index={3} label="Dernière tâche" value={s.current_task_id || "—"}
            icon={<HistoryIcon size={15} />} trend="neutral" />
        </div>
      )}

      {/* ── Providers ─────────────────────────────────────── */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <ProviderCard
          title="Hermes Native"
          icon={<Sparkles size={13} />}
          loading={providers.isLoading}
          error={providers.isError}
          available={p?.hermes_native.available}
          detail={p?.hermes_native.status ? `agent ${p.hermes_native.status.agent_id}` : undefined}
        />
        <ExternalProviderCard
          title="KlaatCode"
          icon={<Cpu size={13} />}
          loading={providers.isLoading}
          error={providers.isError}
          available={p?.klaatcode.available}
          status={p?.klaatcode.status ?? null}
        />
        <ExternalProviderCard
          title="Oh My Pi"
          icon={<Brain size={13} />}
          loading={providers.isLoading}
          error={providers.isError}
          available={p?.ohmypi.available}
          status={p?.ohmypi.status ?? null}
        />
      </div>

      {/* ── Code Tasks + last Routing/Execution ─────────────── */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <Card title="Code Tasks" subtitle="Lance une tâche réelle via CodeIntelligenceAgent">
          <div className="space-y-3">
            <div className="flex flex-wrap gap-1.5">
              {TASK_KINDS.map((t) => (
                <button
                  key={t.kind}
                  onClick={() => setTaskKind(t.kind)}
                  className={`px-2.5 py-1 rounded text-[10px] font-mono uppercase tracking-wider border transition-colors
                    ${taskKind === t.kind
                      ? "border-hermes-cyan/50 bg-hermes-cyan/10 text-hermes-cyan"
                      : "border-hermes-border text-hermes-muted hover:text-hermes-text"}`}
                >
                  {t.label}
                </button>
              ))}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {PROVIDER_CHOICES.map((pc) => (
                <button
                  key={pc.value || "auto"}
                  onClick={() => setForceProvider(pc.value)}
                  className={`px-2.5 py-1 rounded text-[10px] font-mono uppercase tracking-wider border transition-colors
                    ${forceProvider === pc.value
                      ? "border-hermes-violet/50 bg-hermes-violet/10 text-hermes-violet"
                      : "border-hermes-border text-hermes-muted hover:text-hermes-text"}`}
                >
                  {pc.label}
                </button>
              ))}
            </div>
            <input
              value={projectPath}
              onChange={(e) => setProjectPath(e.target.value)}
              placeholder="project_path (ex: backend/agents)"
              className="w-full bg-hermes-bg border border-hermes-border rounded px-2.5 py-1.5 text-[11px] font-mono text-hermes-text placeholder-hermes-muted/60 focus:outline-none focus:border-hermes-cyan/50"
            />
            <input
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder="instruction (optionnel)"
              className="w-full bg-hermes-bg border border-hermes-border rounded px-2.5 py-1.5 text-[11px] font-mono text-hermes-text placeholder-hermes-muted/60 focus:outline-none focus:border-hermes-cyan/50"
            />
            <textarea
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="code (optionnel)"
              rows={4}
              className="w-full bg-hermes-bg border border-hermes-border rounded px-2.5 py-1.5 text-[11px] font-mono text-hermes-text placeholder-hermes-muted/60 focus:outline-none focus:border-hermes-cyan/50 resize-none"
            />
            <button
              onClick={submit}
              disabled={runDisabled}
              className="w-full flex items-center justify-center gap-2 rounded border border-hermes-cyan/50 bg-hermes-cyan/10 px-3 py-2 text-[11px] font-mono uppercase tracking-wider text-hermes-cyan hover:bg-hermes-cyan/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <PlayCircle size={13} />
              {runTask.isPending ? "Exécution…" : "Lancer"}
            </button>
          </div>
        </Card>

        <Card title="Routing & Execution" subtitle="Dernière décision et son résultat">
          {!lastResult ? (
            <p className="text-[11px] text-hermes-muted font-mono py-2">
              Aucune tâche lancée depuis l&apos;ouverture de la page.
            </p>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Badge variant={lastResult.success ? "success" : "danger"}>
                  {lastResult.success ? <CheckCircle2 size={10} /> : <XCircle size={10} />}
                  {lastResult.success ? "success" : "failed"}
                </Badge>
                {lastResult.provider && <Badge variant="info">{lastResult.provider}</Badge>}
                <span className="text-[10px] text-hermes-muted font-mono ml-auto">
                  {lastResult.duration_ms.toFixed(0)} ms
                </span>
              </div>

              {lastResult.decision && (
                <div className="text-[10.5px] font-mono space-y-1 border-t border-hermes-border/40 pt-2">
                  <Row label="Classification" value={lastResult.decision.task_type} />
                  <Row label="Provider sélectionné" value={lastResult.decision.selected_provider} />
                  <Row label="Stratégie" value={lastResult.decision.strategy} />
                  <Row label="Raison" value={lastResult.decision.primary_reason} />
                  {lastResult.decision.scores.map((sc) => (
                    <Row key={sc.provider} label={`Score ${sc.provider}`} value={sc.score.toFixed(3)} />
                  ))}
                </div>
              )}

              {lastResult.error && (
                <div className="text-[10.5px] font-mono text-hermes-red border-t border-hermes-border/40 pt-2 break-words">
                  {lastResult.error}
                </div>
              )}

              {!lastResult.error && lastResult.data != null && (
                <pre className="text-[10px] font-mono text-hermes-text bg-hermes-bg border border-hermes-border/40 rounded p-2 max-h-40 overflow-auto whitespace-pre-wrap break-words">
                  {typeof lastResult.data === "string" ? lastResult.data : JSON.stringify(lastResult.data, null, 2)}
                </pre>
              )}
            </div>
          )}
        </Card>
      </div>

      {/* ── History ───────────────────────────────────────── */}
      <Card title="History" subtitle={history.data ? `${history.data.total} tâche(s)` : undefined}>
        {history.isLoading ? (
          <PanelLoading />
        ) : history.isError ? (
          <p className="text-xs text-hermes-red font-mono">/code-intelligence/history unreachable</p>
        ) : !history.data || history.data.history.length === 0 ? (
          <p className="text-[11px] text-hermes-muted font-mono py-2">Aucun historique réel pour le moment.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[10.5px] font-mono">
              <thead>
                <tr className="text-hermes-muted border-b border-hermes-border/40">
                  <th className="text-left py-1.5 pr-3">Tâche</th>
                  <th className="text-left py-1.5 pr-3">Provider</th>
                  <th className="text-left py-1.5 pr-3">Stratégie</th>
                  <th className="text-left py-1.5 pr-3">Résultat</th>
                  <th className="text-right py-1.5 pr-3">Durée</th>
                  <th className="text-left py-1.5">Horodatage</th>
                </tr>
              </thead>
              <tbody>
                {[...history.data.history].reverse().map((h) => (
                  <tr key={h.task_id} className="border-b border-hermes-border/20 text-hermes-text">
                    <td className="py-1.5 pr-3">{h.task_type}</td>
                    <td className="py-1.5 pr-3">{h.selected_provider}</td>
                    <td className="py-1.5 pr-3">{h.strategy}</td>
                    <td className="py-1.5 pr-3">
                      {h.success ? (
                        <span className="text-hermes-green">OK</span>
                      ) : (
                        <span className="text-hermes-red">Échec</span>
                      )}
                    </td>
                    <td className="py-1.5 pr-3 text-right">{h.duration_ms.toFixed(0)} ms</td>
                    <td className="py-1.5 text-hermes-muted">{new Date(h.timestamp).toLocaleTimeString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-hermes-muted">{label}</span>
      <span className="text-hermes-text truncate">{value}</span>
    </div>
  );
}

function ProviderCard({
  title, icon, loading, error, available, detail,
}: {
  title: string;
  icon: React.ReactNode;
  loading: boolean;
  error: boolean;
  available?: boolean;
  detail?: string;
}) {
  return (
    <Card title={title} action={<span className="text-hermes-cyan/70">{icon}</span>}>
      {loading ? (
        <p className="text-[10.5px] text-hermes-muted font-mono py-1">Vérification…</p>
      ) : error ? (
        <p className="text-[10.5px] text-hermes-red font-mono py-1">indisponible</p>
      ) : (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-hermes-muted font-mono">Disponible</span>
            <Badge variant={available ? "success" : "warning"}>{available ? "yes" : "no"}</Badge>
          </div>
          {detail && <p className="text-[10px] text-hermes-muted font-mono truncate">{detail}</p>}
        </div>
      )}
    </Card>
  );
}

function ExternalProviderCard({
  title, icon, loading, error, available, status,
}: {
  title: string;
  icon: React.ReactNode;
  loading: boolean;
  error: boolean;
  available?: boolean;
  status: CodeIntelligenceExternalProviderStatusDTO | null;
}) {
  return (
    <Card title={title} action={<span className="text-hermes-cyan/70">{icon}</span>}>
      {loading ? (
        <p className="text-[10.5px] text-hermes-muted font-mono py-1">Vérification…</p>
      ) : error || !status ? (
        <p className="text-[10.5px] text-hermes-red font-mono py-1">indisponible</p>
      ) : (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-hermes-muted font-mono">Installé</span>
            <Badge variant={status.installed ? "success" : "warning"}>{status.installed ? "yes" : "no"}</Badge>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-hermes-muted font-mono">Disponible</span>
            <Badge variant={available ? "success" : "warning"}>{available ? "yes" : "no"}</Badge>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-hermes-muted font-mono">MCP</span>
            <Badge variant={mcpStatusVariant[status.mcp_status]}>{status.mcp_status}</Badge>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-hermes-muted font-mono">Version</span>
            <span className="text-[10px] font-mono text-hermes-text">{status.version || "—"}</span>
          </div>
          {status.client_stats.total_executions > 0 && (
            <div className="pt-1.5 mt-1 border-t border-hermes-border/30 grid grid-cols-2 gap-2">
              <div>
                <div className="text-[9px] text-hermes-muted font-mono uppercase">Runs</div>
                <div className="text-xs font-mono text-hermes-text">{status.client_stats.total_executions}</div>
              </div>
              <div>
                <div className="text-[9px] text-hermes-muted font-mono uppercase">Succès</div>
                <div className="text-xs font-mono text-hermes-green">
                  {(status.client_stats.success_rate * 100).toFixed(0)}%
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
