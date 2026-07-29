"use client";

import { useHermesStatus } from "@/hooks/use-dashboard";
import { Bot, CheckCircle, XCircle, Loader2 } from "lucide-react";

export default function HermesCard() {
  const { data: status, isLoading, isError } = useHermesStatus();

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4 transition-colors hover:border-white/20">
      <div className="mb-3 flex items-center gap-2">
        <Bot size={16} className="text-[var(--color-accent)]" />
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
          Hermes Agent
        </h3>
      </div>

      {isLoading ? (
        <div className="animate-pulse space-y-2">
          <div className="h-3 w-32 rounded bg-white/10" />
          <div className="h-3 w-24 rounded bg-white/10" />
        </div>
      ) : isError || !status ? (
        <div>
          <div className="flex items-center gap-2 text-xs text-[var(--color-danger)]">
            <XCircle size={14} />
            <span>Unavailable</span>
          </div>
          <p className="mt-2 text-[10px] text-[var(--color-text-muted)]">
            Hermes Agent not connected.
          </p>
        </div>
      ) : (
        <div>
          <div
            className={`flex items-center gap-2 text-xs ${
              status.status === "CONNECTED"
                ? "text-[var(--color-success)]"
                : status.status === "CONNECTING"
                  ? "text-[var(--color-warning)]"
                  : "text-[var(--color-danger)]"
            }`}
          >
            {status.status === "CONNECTED" ? (
              <CheckCircle size={14} />
            ) : status.status === "CONNECTING" ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <XCircle size={14} />
            )}
            <span>{status.status}</span>
          </div>

          <div className="mt-2 space-y-1 text-[11px]">
            <div className="flex justify-between">
              <span className="text-[var(--color-text-muted)]">Sessions</span>
              <span className="text-[var(--color-text-primary)]">{status.sessions ?? 0}</span>
            </div>
            {status.capabilities && status.capabilities.length > 0 && (
              <div className="flex flex-wrap gap-1 pt-1">
                {status.capabilities.map((cap) => (
                  <span
                    key={cap}
                    className="rounded-full bg-[var(--color-accent)]/10 px-1.5 py-0.5 text-[9px] text-[var(--color-accent)]"
                  >
                    {cap}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
