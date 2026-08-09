"use client";

import { useState } from "react";
import { Card, Badge } from "@/components/ui/card";
import {
  useAutonomousAction,
  useAutonomousReport,
  useAutonomousStatus,
  useAutonomousTimeline,
  useStartAutonomousGoal,
} from "@/hooks/use-api";
import {
  BrainCircuit,
  Play,
  Pause,
  XCircle,
  CheckCircle,
  AlertCircle,
} from "lucide-react";
import { CenterHeader } from "@/components/center-scaffold";

// This Center used to render four module-level constants — MOCK_GOAL,
// MOCK_SESSION, MOCK_DECISIONS and MOCK_TIMELINE — describing a fabricated
// mission on a "ktransformers" runtime, plus a "Pipeline Flow" card with five
// hard-coded green ticks (Security Validation ✓, Policy Check ✓, ...) that were
// true regardless of what the system had done. Meanwhile /api/v1/autonomous
// executed real missions against Ollama. Everything below is now live
// (R-002 P3).

const statusBadge = (status: string | undefined) => {
  const v: Record<string, "success" | "warning" | "danger" | "default"> = {
    completed: "success", executing: "warning", analyzing: "default",
    planning: "default", failed: "danger", cancelled: "danger", paused: "warning",
  };
  return <Badge variant={v[status ?? ""] || "default"}>{status ?? "unknown"}</Badge>;
};

export function AutonomousCenter() {
  const [request, setRequest] = useState("");
  const [localPath, setLocalPath] = useState("");
  const [repository, setRepository] = useState("");
  const [branch, setBranch] = useState("");
  const [goalId, setGoalId] = useState<string | undefined>(undefined);

  const status = useAutonomousStatus();
  const start = useStartAutonomousGoal();
  const action = useAutonomousAction();
  const report = useAutonomousReport(goalId);
  const timeline = useAutonomousTimeline(goalId);

  const goal = start.data;
  const rep = report.data;
  const busy = start.isPending;

  const execute = () => {
    const text = request.trim();
    if (!text) return;
    const context: Record<string, unknown> = {};
    if (localPath.trim()) context.local_path = localPath.trim();
    if (repository.trim()) context.repository = repository.trim();
    if (branch.trim()) context.branch = branch.trim();
    start.mutate(
      { userRequest: text, context },
      { onSuccess: (g) => setGoalId(g.goal_id) },
    );
  };

  return (
    <div className="animate-fade-in p-6">
      {/* Header — the badge reflects the engine's real counters */}
      <CenterHeader
        title="Autonomous OS"
        subtitle="Noyau agentique final — HOS-063"
        right={<>{status.isLoading ? (
          <Badge variant="default">Checking core…</Badge>
        ) : status.isError ? (
          <Badge variant="danger">
            <AlertCircle className="w-3 h-3 mr-1" />
            Core unreachable
          </Badge>
        ) : (
          <Badge variant="success">
            <BrainCircuit className="w-3 h-3 mr-1" />
            {status.data?.total_goals ?? 0} goal(s) · {status.data?.active ?? 0} active
          </Badge>
        )}</>}
      />

      {/* Goal Input — now actually starts a mission */}
      <Card title="Goal Input" className="mb-6">
        <div className="flex gap-3">
          <input
            type="text"
            value={request}
            onChange={(e) => setRequest(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") execute();
            }}
            placeholder="Describe your goal... e.g., 'Analyse the authentication module'"
            className="flex-1 bg-hermes-bg border border-hermes-border rounded-lg px-4 py-2.5 text-sm text-hermes-text font-mono focus:outline-none focus:border-hermes-amber/50 placeholder:text-hermes-muted/50"
          />
          <button
            onClick={execute}
            disabled={!request.trim() || busy}
            className="px-4 py-2.5 bg-hermes-amber/10 text-hermes-amber-bright border border-hermes-amber/30 rounded-lg hover:bg-hermes-amber/20 transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            <Play className="w-4 h-4" />
            {busy ? "Running…" : "Execute"}
          </button>
        </div>

        {/* Project binding (HOS-067) — optional. A goal bound to either
            requires Aegis validation before it runs (see the "paused"
            status below) instead of the unconditional pass-through a
            plain, unbound goal gets. */}
        <div className="grid grid-cols-3 gap-3 mt-3">
          <input
            type="text"
            value={localPath}
            onChange={(e) => setLocalPath(e.target.value)}
            placeholder="Local folder (optional) — e.g. C:\projects\my-app"
            className="bg-hermes-bg border border-hermes-border rounded-lg px-3 py-2 text-[11px] text-hermes-text font-mono focus:outline-none focus:border-hermes-amber/50 placeholder:text-hermes-muted/50"
          />
          <input
            type="text"
            value={repository}
            onChange={(e) => setRepository(e.target.value)}
            placeholder="GitHub repo (optional) — e.g. owner/repo"
            className="bg-hermes-bg border border-hermes-border rounded-lg px-3 py-2 text-[11px] text-hermes-text font-mono focus:outline-none focus:border-hermes-amber/50 placeholder:text-hermes-muted/50"
          />
          <input
            type="text"
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
            placeholder="Branch (optional) — default: main"
            className="bg-hermes-bg border border-hermes-border rounded-lg px-3 py-2 text-[11px] text-hermes-text font-mono focus:outline-none focus:border-hermes-amber/50 placeholder:text-hermes-muted/50"
          />
        </div>
        {busy && (
          <div className="text-[10px] text-hermes-muted font-mono mt-2">
            Real inference in progress — this takes as long as the model takes.
          </div>
        )}
        {start.isError && (
          <div className="text-[10px] text-hermes-red font-mono mt-2">
            {start.error instanceof Error ? start.error.message : "Failed to start goal"}
          </div>
        )}
      </Card>

      {/* Engine counters — every number below comes from /autonomous/status */}
      <div className="grid grid-cols-6 gap-2 mb-6">
        {[
          { label: "Goals", value: status.data?.total_goals },
          { label: "Active", value: status.data?.active },
          { label: "Completed", value: status.data?.completed },
          { label: "Failed", value: status.data?.failed },
          { label: "Executions", value: status.data?.total_executions },
          { label: "Decisions", value: status.data?.decisions?.total_decisions },
        ].map((s) => (
          <div key={s.label} className="bg-hermes-card border border-hermes-border rounded-lg p-2 text-center">
            <div className="text-[9px] text-hermes-muted font-mono uppercase">{s.label}</div>
            <div className="text-sm font-bold font-mono text-hermes-text mt-0.5">
              {status.isLoading ? "…" : (s.value ?? "—")}
            </div>
          </div>
        ))}
      </div>

      {!goalId && (
        <Card title="Current Goal" className="mb-6">
          <div className="text-xs text-hermes-muted font-mono py-3">
            No goal running. Describe one above to start a real mission.
          </div>
        </Card>
      )}

      {goalId && goal && (
        <Card title="Current Goal" className="mb-6">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-[10px] text-hermes-muted font-mono uppercase mb-1">User Request</div>
              <div className="text-xs text-hermes-text font-mono bg-hermes-bg p-2 rounded-lg border border-hermes-border/50">
                {goal.user_request}
              </div>
              <div className="text-[10px] text-hermes-muted font-mono uppercase mt-3 mb-1">Interpretation</div>
              <div className="text-[10px] text-hermes-text">{goal.interpreted_goal}</div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {[
                { label: "Domain", value: goal.domain, color: "text-hermes-blue" },
                { label: "Language", value: goal.language, color: "text-hermes-green" },
                {
                  label: "Complexity",
                  value: `${((goal.complexity ?? 0) * 100).toFixed(0)}%`,
                  color: "text-hermes-amber",
                },
                { label: "Status", value: goal.status, color: "text-hermes-purple" },
              ].map((s) => (
                <div key={s.label} className="bg-hermes-card/50 border border-hermes-border/50 rounded-lg p-2">
                  <div className="text-[9px] text-hermes-muted font-mono uppercase">{s.label}</div>
                  <div className={`text-sm font-bold font-mono ${s.color}`}>{s.value || "—"}</div>
                </div>
              ))}
            </div>
          </div>
          {(goal.local_path || goal.repository) && (
            <div className="mt-3 pt-3 border-t border-hermes-border/30 flex gap-4 text-[10px] font-mono">
              {goal.local_path && (
                <div>
                  <span className="text-hermes-muted uppercase">Local: </span>
                  <span className="text-hermes-text">{goal.local_path}</span>
                </div>
              )}
              {goal.repository && (
                <div>
                  <span className="text-hermes-muted uppercase">Repo: </span>
                  <span className="text-hermes-text">
                    {goal.repository}{goal.branch ? `@${goal.branch}` : ""}
                  </span>
                </div>
              )}
            </div>
          )}
          {goal.status === "paused" && (
            <div className="mt-3 pt-3 border-t border-hermes-border/30 text-[10px] font-mono text-hermes-amber flex items-center gap-2">
              <AlertCircle className="w-3 h-3" />
              This goal touches a real project and needs human validation
              (Aegis) before it can run — raise autonomy_level, or resume it
              once approved.
            </div>
          )}
          {goal.knowledge_context && (
            <div className="mt-3 pt-3 border-t border-hermes-border/30">
              <div className="text-[10px] text-hermes-muted font-mono uppercase mb-1">
                From past missions
              </div>
              <div className="text-[10px] text-hermes-text">{goal.knowledge_context}</div>
            </div>
          )}
        </Card>
      )}

      {/* Execution + decisions, both from the report */}
      {goalId && (
        <div className="grid grid-cols-2 gap-4 mb-6">
          <Card title="Execution">
            {report.isLoading && (
              <div className="text-[10px] text-hermes-muted font-mono">Loading report…</div>
            )}
            {report.isError && goal?.status === "paused" && (
              <div className="text-[10px] text-hermes-amber font-mono">
                No report yet — this goal is paused pending human validation
                and hasn&apos;t run.
              </div>
            )}
            {report.isError && goal?.status !== "paused" && (
              <div className="text-[10px] text-hermes-red font-mono">
                Report unavailable
              </div>
            )}
            {rep && (
              <div className="space-y-2">
                <div
                  className={`text-[10px] font-mono p-2 rounded border ${
                    rep.execution_summary?.startsWith("WARNING:")
                      ? "text-hermes-red border-hermes-red/40 bg-hermes-red/5"
                      : "text-hermes-text border-hermes-border/50 bg-hermes-bg"
                  }`}
                >
                  {rep.execution_summary}
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-hermes-muted font-mono">Agents</span>
                  <div className="flex gap-1 flex-wrap justify-end">
                    {rep.agents_used.length === 0 ? (
                      <span className="text-[10px] text-hermes-muted font-mono">none</span>
                    ) : (
                      rep.agents_used.map((a) => (
                        <Badge key={a} variant="default" className="text-[9px]">{a}</Badge>
                      ))
                    )}
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-hermes-muted font-mono">Runtimes</span>
                  <span className="text-[10px] font-mono text-hermes-text">
                    {rep.runtimes_used.join(", ") || "none"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-hermes-muted font-mono">Duration</span>
                  <span className="text-[10px] font-mono text-hermes-text">
                    {rep.total_duration_ms.toFixed(0)}ms
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-hermes-muted font-mono">Outcome</span>
                  {statusBadge(rep.success ? "completed" : "failed")}
                </div>
              </div>
            )}
          </Card>

          <Card title={`Decisions${rep ? ` (${rep.decisions.length})` : ""}`}>
            {report.isLoading && (
              <div className="text-[10px] text-hermes-muted font-mono">Loading decisions…</div>
            )}
            {rep && rep.decisions.length === 0 && (
              <div className="text-[10px] text-hermes-muted font-mono">
                The engine recorded no decisions for this goal.
              </div>
            )}
            <div className="space-y-1.5">
              {rep?.decisions.map((d) => (
                <div key={d.decision_id} className="text-[9px] font-mono">
                  <div className="flex items-center justify-between">
                    <div className="text-hermes-muted">
                      {d.decision_type.replace(/_/g, " ")}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-hermes-text">{d.selected}</span>
                      <span className="text-hermes-green">
                        {(d.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                  <div className="text-[8px] text-hermes-muted/70 truncate">{d.reason}</div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {/* Timeline + lessons, both real */}
      {goalId && (
        <div className="grid grid-cols-2 gap-4 mb-6">
          <Card title="Timeline">
            {timeline.isLoading && (
              <div className="text-[10px] text-hermes-muted font-mono">Loading timeline…</div>
            )}
            {timeline.data?.timeline.length === 0 && (
              <div className="text-[10px] text-hermes-muted font-mono">
                No timeline entries yet.
              </div>
            )}
            <div className="space-y-0">
              {timeline.data?.timeline.map((t, i) => (
                <div key={`${t.event}-${i}`} className="flex items-center gap-2 py-1.5 border-b border-hermes-border/20 last:border-0">
                  <div className="w-1.5 h-1.5 rounded-full bg-hermes-green" />
                  <span className="text-[10px] font-mono text-hermes-text flex-1">
                    {t.event.replace(/_/g, " ")}
                  </span>
                  <span className="text-[9px] text-hermes-muted font-mono">
                    {t.decisions.length} decision(s)
                  </span>
                </div>
              ))}
            </div>
          </Card>

          <Card title="Learning">
            {rep && rep.lessons.length === 0 && rep.improvements.length === 0 && (
              <div className="text-[10px] text-hermes-muted font-mono">
                No lessons recorded for this goal.
              </div>
            )}
            <div className="flex flex-col gap-1.5 text-[10px] font-mono">
              {rep?.lessons.map((l, i) => (
                <div key={`lesson-${i}`} className="flex items-start gap-2 text-hermes-green">
                  <CheckCircle className="w-3 h-3 mt-0.5 shrink-0" />
                  <span className="text-hermes-text">{l}</span>
                </div>
              ))}
              {rep?.improvements.map((im, i) => (
                <div key={`improvement-${i}`} className="flex items-start gap-2 text-hermes-amber">
                  <AlertCircle className="w-3 h-3 mt-0.5 shrink-0" />
                  <span className="text-hermes-text">{im}</span>
                </div>
              ))}
            </div>
            {status.data && (
              <div className="mt-3 pt-2 border-t border-hermes-border/30 text-[9px] font-mono text-hermes-muted">
                memory loop: {status.data.memory_loop.missions} mission(s),{" "}
                {status.data.memory_loop.success_rate}% success,{" "}
                {status.data.memory_loop.total_lessons} lesson(s)
              </div>
            )}
          </Card>
        </div>
      )}

      {/* Controls — these buttons were inert; they now call the real endpoints */}
      <Card title="Controls">
        <div className="flex gap-3 items-center">
          <button
            onClick={() => goalId && action.mutate({ goalId, action: "resume" })}
            disabled={!goalId || action.isPending}
            className="px-4 py-2 bg-hermes-green/10 text-hermes-green border border-hermes-green/30 rounded-lg hover:bg-hermes-green/20 transition-colors flex items-center gap-2 text-xs font-mono disabled:opacity-40"
          >
            <Play className="w-3 h-3" /> Resume
          </button>
          <button
            onClick={() => goalId && action.mutate({ goalId, action: "pause" })}
            disabled={!goalId || action.isPending}
            className="px-4 py-2 bg-hermes-amber/10 text-hermes-amber border border-hermes-amber/30 rounded-lg hover:bg-hermes-amber/20 transition-colors flex items-center gap-2 text-xs font-mono disabled:opacity-40"
          >
            <Pause className="w-3 h-3" /> Pause
          </button>
          <button
            onClick={() => goalId && action.mutate({ goalId, action: "cancel" })}
            disabled={!goalId || action.isPending}
            className="px-4 py-2 bg-hermes-red/10 text-hermes-red border border-hermes-red/30 rounded-lg hover:bg-hermes-red/20 transition-colors flex items-center gap-2 text-xs font-mono disabled:opacity-40"
          >
            <XCircle className="w-3 h-3" /> Cancel
          </button>
          {!goalId && (
            <span className="text-[10px] text-hermes-muted font-mono">
              Start a goal to enable controls.
            </span>
          )}
        </div>
      </Card>
    </div>
  );
}
