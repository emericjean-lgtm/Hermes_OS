"use client";

import { useAgentControl } from "@/hooks/use-agents";
import { Pause, Play, XCircle, RotateCcw, RefreshCw, Copy, Download, Loader2 } from "lucide-react";
import type { AgentInfo } from "@/types/mission-control";

interface AgentControlsProps { agent: AgentInfo | null | undefined }

function CtlBtn({ icon, label, onClick, disabled, loading, variant = "default" }: {
  icon: React.ReactNode; label: string; onClick: () => void; disabled?: boolean; loading?: boolean; variant?: "default" | "danger" | "warning";
}) {
  const colors = { default: "bg-white/5 text-[var(--color-text-muted)] hover:bg-white/10", danger: "bg-[var(--color-danger)]/10 text-[var(--color-danger)] hover:bg-[var(--color-danger)]/20", warning: "bg-[var(--color-warning)]/10 text-[var(--color-warning)] hover:bg-[var(--color-warning)]/20" };
  return <button onClick={onClick} disabled={disabled || loading} className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition disabled:opacity-30 ${colors[variant]}`}>{loading ? <Loader2 size={12} className="animate-spin" /> : icon}<span className="hidden sm:inline">{label}</span></button>;
}

export default function AgentControls({ agent }: AgentControlsProps) {
  const ctl = useAgentControl();

  if (!agent) return <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] px-4 py-3"><p className="text-xs text-[var(--color-text-muted)]">Select an agent to see available actions</p></div>;

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-white/10 bg-[var(--color-bg-surface)] px-4 py-3">
      <span className="mr-2 text-xs font-medium text-[var(--color-text-muted)]">Agent Controls:</span>
      {agent.state === "RUNNING" && <CtlBtn icon={<Pause size={12} />} label="Pause" onClick={() => ctl.pause.mutate(agent.id)} loading={ctl.pause.isPending} variant="warning" />}
      {agent.state === "PAUSED" && <CtlBtn icon={<Play size={12} />} label="Resume" onClick={() => ctl.resume.mutate(agent.id)} loading={ctl.resume.isPending} />}
      {(agent.state === "RUNNING" || agent.state === "PAUSED") && <CtlBtn icon={<XCircle size={12} />} label="Cancel" onClick={() => ctl.cancel.mutate(agent.id)} loading={ctl.cancel.isPending} variant="danger" />}
      {agent.state === "FAILED" && <CtlBtn icon={<RefreshCw size={12} />} label="Retry" onClick={() => ctl.retry.mutate(agent.id)} loading={ctl.retry.isPending} />}
      {agent.state === "FAILED" && <CtlBtn icon={<RotateCcw size={12} />} label="Recover" onClick={() => ctl.recover.mutate(agent.id)} loading={ctl.recover.isPending} />}
      <CtlBtn icon={<Copy size={12} />} label="Duplicate" onClick={() => ctl.duplicate.mutate(agent.id)} loading={ctl.duplicate.isPending} />
    </div>
  );
}
