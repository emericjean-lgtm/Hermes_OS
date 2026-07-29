"use client";

import { useHermesStatus, useAgentControl } from "@/hooks/use-agents";
import { Bot, CheckCircle, XCircle, Loader2, GitBranch, Cpu, BookOpen, Puzzle } from "lucide-react";

export default function AgentHermesCard() {
  const query = useHermesStatus();
  const { hermesConnect, hermesDisconnect, hermesCreateSubagent } = useAgentControl();

  const isLoading = query.isLoading;
  const hermes = query.data;

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4">
      <div className="flex items-center gap-2 mb-3">
        <Bot size={16} className="text-[var(--color-accent)]" />
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Hermes Agent</h3>
      </div>

      {isLoading ? (
        <div className="animate-pulse space-y-2"><div className="h-3 w-32 rounded bg-white/10" /><div className="h-3 w-24 rounded bg-white/10" /></div>
      ) : !hermes ? (
        <div>
          <div className="flex items-center gap-2 text-xs text-[var(--color-danger)]"><XCircle size={14} /><span>Unavailable</span></div>
          <button onClick={() => hermesConnect.mutate()} className="mt-3 rounded-md bg-[var(--color-accent)] px-3 py-1.5 text-xs font-medium text-white transition hover:opacity-90">Connect</button>
        </div>
      ) : (
        <div>
          <StatusContent hermes={hermes as unknown as { status: string; sessions: number; capabilities?: string[] }} onDisconnect={() => hermesDisconnect.mutate()} onCreateSubagent={() => hermesCreateSubagent.mutate()} />
        </div>
      )}
    </div>
  );
}

function StatusContent({ hermes, onDisconnect, onCreateSubagent }: {
  hermes: { status: string; sessions: number; capabilities?: string[] };
  onDisconnect: () => void;
  onCreateSubagent: () => void;
}) {
  const statusColor = hermes.status === "CONNECTED" ? "var(--color-success)" : hermes.status === "CONNECTING" ? "var(--color-warning)" : "var(--color-danger)";
  const StatusIcon = hermes.status === "CONNECTED" ? CheckCircle : hermes.status === "CONNECTING" ? Loader2 : XCircle;

  return (
    <>
      <div className="flex items-center gap-2 text-xs" style={{ color: statusColor }}>
        <StatusIcon size={14} className={hermes.status === "CONNECTING" ? "animate-spin" : ""} />
        <span>{hermes.status}</span>
      </div>
      <div className="mt-2 space-y-1.5 text-[11px]">
        <div className="flex items-center justify-between"><span className="text-[var(--color-text-muted)]">Sessions</span><span className="text-[var(--color-text-primary)]">{hermes.sessions ?? 0}</span></div>
        {hermes.capabilities && hermes.capabilities.length > 0 && (
          <div className="flex flex-wrap gap-1 pt-1">
            {hermes.capabilities.map(c => <span key={c} className="rounded-full bg-[var(--color-accent)]/10 px-1.5 py-0.5 text-[9px] text-[var(--color-accent)]">{c}</span>)}
          </div>
        )}
      </div>
      <div className="mt-3 flex gap-2">
        {hermes.status === "CONNECTED" && <button onClick={onDisconnect} className="rounded-md bg-[var(--color-danger)]/10 px-2 py-1 text-[10px] text-[var(--color-danger)] transition hover:bg-[var(--color-danger)]/20">Disconnect</button>}
        {hermes.status === "CONNECTED" && <button onClick={onCreateSubagent} className="rounded-md bg-[var(--color-accent)]/10 px-2 py-1 text-[10px] text-[var(--color-accent)] transition hover:bg-[var(--color-accent)]/20">+ Sub-agent</button>}
      </div>
    </>
  );
}
