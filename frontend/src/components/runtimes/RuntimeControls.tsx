"use client";
import { useRuntimeControl } from "@/hooks/use-runtimes";
import { RefreshCw, Activity, RotateCcw, XCircle, CheckCircle, Download, Loader2 } from "lucide-react";

function Btn({ icon, label, onClick, loading, variant = "default" }: { icon: React.ReactNode; label: string; onClick: () => void; loading?: boolean; variant?: "default" | "danger" | "warning" }) {
  const c = { default: "bg-white/5 text-[var(--color-text-muted)] hover:bg-white/10", danger: "bg-[var(--color-danger)]/10 text-[var(--color-danger)] hover:bg-[var(--color-danger)]/20", warning: "bg-[var(--color-warning)]/10 text-[var(--color-warning)] hover:bg-[var(--color-warning)]/20" };
  return <button onClick={onClick} disabled={loading} className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition disabled:opacity-30 ${c[variant]}`}>{loading ? <Loader2 size={12} className="animate-spin" /> : icon}<span className="hidden sm:inline">{label}</span></button>;
}

interface Props { runtimeName: string | null; }

export default function RuntimeControls({ runtimeName }: Props) {
  const ctl = useRuntimeControl();
  if (!runtimeName) return <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] px-4 py-3"><p className="text-xs text-[var(--color-text-muted)]">Select a runtime to see actions</p></div>;

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-white/10 bg-[var(--color-bg-surface)] px-4 py-3">
      <span className="mr-2 text-xs font-medium text-[var(--color-text-muted)]">Runtime Controls:</span>
      <Btn icon={<RefreshCw size={12} />} label="Refresh" onClick={() => ctl.refresh.mutate(runtimeName)} loading={ctl.refresh.isPending} />
      <Btn icon={<Activity size={12} />} label="Health Check" onClick={() => ctl.healthCheck.mutate(runtimeName)} loading={ctl.healthCheck.isPending} />
      <Btn icon={<RotateCcw size={12} />} label="Reset Circuit" onClick={() => ctl.resetCircuit.mutate(runtimeName)} loading={ctl.resetCircuit.isPending} variant="warning" />
      <Btn icon={<XCircle size={12} />} label="Disable" onClick={() => ctl.disable.mutate(runtimeName)} loading={ctl.disable.isPending} variant="danger" />
      <Btn icon={<CheckCircle size={12} />} label="Enable" onClick={() => ctl.enable.mutate(runtimeName)} loading={ctl.enable.isPending} />
    </div>
  );
}
