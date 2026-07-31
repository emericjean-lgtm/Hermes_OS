"use client";

import { usePolicyRules, useApprovals, useApproveAction, useRejectAction, useAuditLog } from "@/hooks/use-api";
import { Card, Badge } from "@/components/ui/card";
import type { PolicyRule, ApprovalRequest, AuditEntry } from "@/types/hermes";

export function GovernanceCenter() {
  const { data: rules } = usePolicyRules();
  const { data: approvals } = useApprovals();
  const { data: auditLog } = useAuditLog();
  const approve = useApproveAction();
  const reject = useRejectAction();

  const pendingApprovals = approvals?.filter((a) => a.status === "PENDING") || [];

  return (
    <div className="animate-fade-in">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-hermes-text font-mono tracking-tight">
            Governance Center
          </h1>
          <p className="text-xs text-hermes-muted mt-1">
            Human approval, policy engine & audit trail
          </p>
        </div>
      </div>

      {/* Pending approvals */}
      {pendingApprovals.length > 0 && (
        <Card
          title="Pending Approvals"
          subtitle={`${pendingApprovals.length} awaiting action`}
          className="mb-6 border-hermes-amber/30"
        >
          <div className="flex flex-col gap-3">
            {pendingApprovals.map((req) => (
              <div key={req.id} className="bg-hermes-bg rounded-lg p-3 border border-hermes-border flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <Badge variant={req.priority === "CRITICAL" ? "danger" : req.priority === "HIGH" ? "warning" : "default"}>
                      {req.priority}
                    </Badge>
                    <span className="text-sm font-medium text-hermes-text font-mono">{req.operation}</span>
                  </div>
                  <div className="text-[10px] text-hermes-muted font-mono">
                    by {req.requested_by} · {new Date(req.created_at).toLocaleString()}
                    {req.expires_at && ` · expires ${new Date(req.expires_at).toLocaleTimeString()}`}
                  </div>
                  {req.metadata && (
                    <pre className="text-[10px] text-hermes-muted mt-1 overflow-x-auto">
                      {JSON.stringify(req.metadata, null, 2)}
                    </pre>
                  )}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => reject.mutate({ id: req.id })}
                    disabled={reject.isPending}
                    className="px-3 py-1.5 text-xs font-mono text-hermes-red border border-hermes-red/30 rounded-lg hover:bg-hermes-red/10 transition-colors disabled:opacity-50"
                  >
                    Reject
                  </button>
                  <button
                    onClick={() => approve.mutate({ id: req.id })}
                    disabled={approve.isPending}
                    className="px-3 py-1.5 text-xs font-mono bg-hermes-green text-black rounded-lg hover:bg-hermes-green/80 transition-colors disabled:opacity-50"
                  >
                    Approve
                  </button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-4">
        {/* Policy Rules */}
        <Card title="Policy Rules" subtitle={`${rules?.length || 0} rules`}>
          <div className="flex flex-col gap-2 max-h-[300px] overflow-y-auto">
            {rules?.map((rule) => (
              <RuleCard key={rule.id} rule={rule} />
            ))}
          </div>
        </Card>

        {/* Audit Log */}
        <Card title="Audit Log" subtitle={`${auditLog?.length || 0} entries`}>
          <div className="flex flex-col gap-1 max-h-[300px] overflow-y-auto">
            {auditLog?.slice(0, 30).map((entry) => (
              <AuditEntryRow key={entry.id} entry={entry} />
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

function RuleCard({ rule }: { rule: PolicyRule }) {
  // /api/v1/policy/rules envoie `decision` en minuscules ("allow", "deny",
  // "review_required"). Ce composant lisait `rule.action` en majuscules — un
  // champ que l'endpoint n'a jamais renvoyé, donc un badge toujours vide (P-001).
  const decisionColors: Record<string, keyof typeof statusColors> = {
    allow: "success",
    deny: "danger",
    review_required: "warning",
  };
  const statusColors = { success: "success", danger: "danger", warning: "warning" } as const;

  return (
    <div className="bg-hermes-bg rounded-lg p-3 border border-hermes-border/50 flex items-center justify-between">
      <div>
        <div className="text-sm font-medium text-hermes-text">{rule.name}</div>
        <div className="text-[10px] text-hermes-muted">{rule.description}</div>
      </div>
      <div className="flex items-center gap-2">
        <Badge variant={rule.enabled ? "success" : "default"}>
          {rule.enabled ? "ON" : "OFF"}
        </Badge>
        <Badge variant={decisionColors[rule.decision] ?? "default"}>
          {rule.decision}
        </Badge>
      </div>
    </div>
  );
}

function AuditEntryRow({ entry }: { entry: AuditEntry }) {
  return (
    <div className="flex items-center gap-2 py-1.5 text-[10px] font-mono border-b border-hermes-border/20 last:border-0">
      <span className="text-hermes-muted w-16 flex-shrink-0">
        {new Date(entry.created_at).toLocaleTimeString()}
      </span>
      <span className="text-hermes-text w-24 flex-shrink-0 truncate">{entry.principal}</span>
      <span className="text-hermes-muted w-20 flex-shrink-0 truncate">{entry.operation}</span>
      <Badge variant={entry.result === "APPROVED" || entry.result === "ALLOWED" ? "success" : "danger"}>
        {entry.result}
      </Badge>
      <span className="text-hermes-muted ml-auto">{entry.duration_ms}ms</span>
    </div>
  );
}
