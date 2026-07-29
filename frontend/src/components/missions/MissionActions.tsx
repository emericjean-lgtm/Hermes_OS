"use client";

import {
  useStartMission,
  usePauseMission,
  useResumeMission,
  useCancelMission,
  useDeleteMission,
  useDuplicateMission,
  useSyncFreebuff,
} from "@/hooks/use-missions";
import {
  Play,
  Pause,
  RotateCcw,
  XCircle,
  Copy,
  Trash2,
  BookOpen,
  Loader2,
} from "lucide-react";
import type { Mission } from "@/types/mission-control";

interface MissionActionsProps {
  mission: Mission | null;
}

function ActionButton({
  icon,
  label,
  onClick,
  disabled,
  loading,
  variant = "default",
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  loading?: boolean;
  variant?: "default" | "danger";
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled || loading}
      className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all disabled:opacity-30 ${
        variant === "danger"
          ? "bg-[var(--color-danger)]/10 text-[var(--color-danger)] hover:bg-[var(--color-danger)]/20"
          : "bg-white/5 text-[var(--color-text-muted)] hover:bg-white/10 hover:text-[var(--color-text-primary)]"
      }`}
      title={label}
    >
      {loading ? <Loader2 size={12} className="animate-spin" /> : icon}
      <span className="hidden sm:inline">{label}</span>
    </button>
  );
}

export default function MissionActions({ mission }: MissionActionsProps) {
  const start = useStartMission();
  const pause = usePauseMission();
  const resume = useResumeMission();
  const cancel = useCancelMission();
  const del = useDeleteMission();
  const duplicate = useDuplicateMission();
  const syncFreebuff = useSyncFreebuff();

  if (!mission) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-[var(--color-bg-surface)] px-4 py-3">
        <p className="text-xs text-[var(--color-text-muted)]">Select a mission to see available actions</p>
      </div>
    );
  }

  const status = mission.status;

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-white/10 bg-[var(--color-bg-surface)] px-4 py-3">
      <span className="mr-2 text-xs font-medium text-[var(--color-text-muted)]">Actions:</span>

      {status === "READY" || status === "CREATED" ? (
        <ActionButton
          icon={<Play size={12} />}
          label="Start"
          onClick={() => start.mutate(mission.id)}
          loading={start.isPending}
        />
      ) : null}

      {status === "RUNNING" ? (
        <ActionButton
          icon={<Pause size={12} />}
          label="Pause"
          onClick={() => pause.mutate(mission.id)}
          loading={pause.isPending}
        />
      ) : null}

      {status === "PAUSED" ? (
        <ActionButton
          icon={<RotateCcw size={12} />}
          label="Resume"
          onClick={() => resume.mutate(mission.id)}
          loading={resume.isPending}
        />
      ) : null}

      {status === "RUNNING" || status === "PAUSED" ? (
        <ActionButton
          icon={<XCircle size={12} />}
          label="Cancel"
          onClick={() => cancel.mutate(mission.id)}
          loading={cancel.isPending}
          variant="danger"
        />
      ) : null}

      {(status === "CREATED" || status === "READY" || status === "COMPLETED" || status === "FAILED" || status === "CANCELLED") ? (
        <>
          <ActionButton
            icon={<Copy size={12} />}
            label="Duplicate"
            onClick={() => duplicate.mutate(mission.id)}
            loading={duplicate.isPending}
          />
          <ActionButton
            icon={<Trash2 size={12} />}
            label="Delete"
            onClick={() => {
              if (confirm("Delete this mission?")) {
                del.mutate(mission.id);
              }
            }}
            loading={del.isPending}
            variant="danger"
          />
        </>
      ) : null}

      <div className="ml-auto">
        <ActionButton
          icon={<BookOpen size={12} />}
          label="Sync Freebuff"
          onClick={() => syncFreebuff.mutate(mission.id)}
          loading={syncFreebuff.isPending}
        />
      </div>
    </div>
  );
}
