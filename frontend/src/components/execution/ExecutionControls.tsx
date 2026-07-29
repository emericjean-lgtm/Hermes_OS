"use client";

import { useExecutionControl, useExecutionOverview } from "@/hooks/use-execution";
import {
  Pause,
  Play,
  XCircle,
  RotateCcw,
  RefreshCw,
  Download,
  Loader2,
} from "lucide-react";

interface ControlButtonProps {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  loading?: boolean;
  variant?: "default" | "danger" | "warning";
}

function ControlButton({ icon, label, onClick, disabled, loading, variant = "default" }: ControlButtonProps) {
  const colors = {
    default: "bg-white/5 text-[var(--color-text-muted)] hover:bg-white/10 hover:text-[var(--color-text-primary)]",
    danger: "bg-[var(--color-danger)]/10 text-[var(--color-danger)] hover:bg-[var(--color-danger)]/20",
    warning: "bg-[var(--color-warning)]/10 text-[var(--color-warning)] hover:bg-[var(--color-warning)]/20",
  };
  return (
    <button
      onClick={onClick}
      disabled={disabled || loading}
      className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all disabled:opacity-30 ${colors[variant]}`}
      title={label}
    >
      {loading ? <Loader2 size={12} className="animate-spin" /> : icon}
      <span className="hidden sm:inline">{label}</span>
    </button>
  );
}

export default function ExecutionControls() {
  const { data: overview } = useExecutionOverview();
  const { pause, resume, cancel, recover, retryFailed, tick } = useExecutionControl();
  const state = overview?.state;

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-white/10 bg-[var(--color-bg-surface)] px-4 py-3">
      <span className="mr-2 text-xs font-medium text-[var(--color-text-muted)]">Controls:</span>

      {state === "RUNNING" ? (
        <ControlButton
          icon={<Pause size={12} />}
          label="Pause"
          onClick={() => pause.mutate()}
          loading={pause.isPending}
          variant="warning"
        />
      ) : null}

      {state === "PAUSED" || state === "WAITING" ? (
        <ControlButton
          icon={<Play size={12} />}
          label="Resume"
          onClick={() => resume.mutate()}
          loading={resume.isPending}
        />
      ) : null}

      {state === "RUNNING" || state === "PAUSED" ? (
        <ControlButton
          icon={<XCircle size={12} />}
          label="Cancel"
          onClick={() => cancel.mutate()}
          loading={cancel.isPending}
          variant="danger"
        />
      ) : null}

      {state === "FAILED" || state === "RECOVERING" ? (
        <ControlButton
          icon={<RotateCcw size={12} />}
          label="Recover"
          onClick={() => recover.mutate()}
          loading={recover.isPending}
        />
      ) : null}

      <ControlButton
        icon={<RefreshCw size={12} />}
        label="Retry Failed"
        onClick={() => retryFailed.mutate()}
        loading={retryFailed.isPending}
      />

      <ControlButton
        icon={<Download size={12} />}
        label="Export Logs"
        onClick={() => {
          ExecutionClient.exportLogs().then((blob) => {
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "execution-logs.json";
            a.click();
            URL.revokeObjectURL(url);
          });
        }}
      />

      <div className="ml-auto">
        <ControlButton
          icon={<RefreshCw size={12} />}
          label="Tick"
          onClick={() => tick.mutate()}
          loading={tick.isPending}
        />
      </div>
    </div>
  );
}

import { ExecutionClient } from "@/lib/execution-client";
