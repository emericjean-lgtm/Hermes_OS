"use client";

import { useFreebuffProjects } from "@/hooks/use-dashboard";
import { BookOpen, CheckCircle, XCircle } from "lucide-react";

export default function FreebuffCard() {
  const { data: projects, isLoading, isError } = useFreebuffProjects();

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-4 transition-colors hover:border-white/20">
      <div className="mb-3 flex items-center gap-2">
        <BookOpen size={16} className="text-[var(--color-accent)]" />
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
          Freebuff Integration
        </h3>
      </div>

      {isLoading ? (
        <div className="animate-pulse space-y-2">
          <div className="h-3 w-32 rounded bg-white/10" />
          <div className="h-3 w-24 rounded bg-white/10" />
        </div>
      ) : isError ? (
        <div className="flex items-center gap-2 text-xs text-[var(--color-danger)]">
          <XCircle size={14} />
          <span>Disconnected</span>
        </div>
      ) : !projects || projects.length === 0 ? (
        <div>
          <div className="flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
            <span className="h-2 w-2 rounded-full bg-[var(--color-text-muted)]" />
            <span>Connected · No projects</span>
          </div>
          <p className="mt-2 text-[10px] text-[var(--color-text-muted)]">
            Create a project to sync missions with Freebuff.
          </p>
        </div>
      ) : (
        <div>
          <div className="flex items-center gap-2 text-xs text-[var(--color-success)]">
            <CheckCircle size={14} />
            <span>{projects.length} project{projects.length > 1 ? "s" : ""}</span>
          </div>
          <ul className="mt-2 space-y-1">
            {projects.slice(0, 3).map((p) => (
              <li key={p.id} className="flex items-center justify-between text-[11px]">
                <span className="text-[var(--color-text-primary)] truncate">{p.name}</span>
                <span className="text-[var(--color-text-muted)] shrink-0 ml-2">
                  {p.last_sync ? new Date(p.last_sync).toLocaleDateString() : "—"}
                </span>
              </li>
            ))}
          </ul>
          {projects.length > 3 && (
            <p className="mt-1 text-[10px] text-[var(--color-text-muted)]">
              +{projects.length - 3} more
            </p>
          )}
        </div>
      )}
    </div>
  );
}
