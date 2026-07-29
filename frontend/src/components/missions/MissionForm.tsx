"use client";

import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useCreateMission } from "@/hooks/use-missions";
import { Loader2, Send } from "lucide-react";
import type { PlanningStrategy, PlannerType } from "@/types/mission-control";

const missionSchema = z.object({
  title: z.string().min(2, "Title must be at least 2 characters").max(100),
  description: z.string().max(500).optional(),
  objective: z.string().max(500).optional(),
  priority: z.enum(["LOW", "MEDIUM", "HIGH", "CRITICAL"]),
  strategy: z.enum(["SEQUENTIAL", "BALANCED", "PARALLEL", "CONSERVATIVE"]),
  planner: z.enum(["LOCAL", "FREEBUFF"]),
  runtime: z.string().optional(),
});

type MissionFormData = z.infer<typeof missionSchema>;

interface MissionFormProps {
  onSuccess?: () => void;
}

const PRIORITY_OPTIONS = [
  { value: "LOW", label: "Low", color: "text-[var(--color-text-muted)]" },
  { value: "MEDIUM", label: "Medium", color: "text-[var(--color-text-muted)]" },
  { value: "HIGH", label: "High", color: "text-[var(--color-warning)]" },
  { value: "CRITICAL", label: "Critical", color: "text-[var(--color-danger)]" },
] as const;

const STRATEGY_OPTIONS = [
  { value: "SEQUENTIAL", label: "Sequential", desc: "One task at a time" },
  { value: "BALANCED", label: "Balanced", desc: "Parallel groups where possible" },
  { value: "PARALLEL", label: "Parallel", desc: "Maximum parallelism" },
  { value: "CONSERVATIVE", label: "Conservative", desc: "Minimal resource usage" },
] as const;

const PLANNER_OPTIONS = [
  { value: "LOCAL", label: "Local", desc: "Hermes OS local planner" },
  { value: "FREEBUFF", label: "Freebuff", desc: "Advanced planning via Freebuff" },
] as const;

export default function MissionForm({ onSuccess }: MissionFormProps) {
  const createMission = useCreateMission();

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    reset,
  } = useForm<MissionFormData>({
    resolver: zodResolver(missionSchema),
    defaultValues: {
      title: "",
      description: "",
      objective: "",
      priority: "MEDIUM",
      strategy: "BALANCED",
      planner: "LOCAL",
    },
  });

  const onSubmit = async (data: MissionFormData) => {
    try {
      await createMission.mutateAsync(data);
      reset();
      onSuccess?.();
    } catch {
      // Error handled by mutation state
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      {/* Title */}
      <div>
        <label className="block text-xs font-medium text-[var(--color-text-muted)] mb-1">Title *</label>
        <input
          {...register("title")}
          placeholder="e.g., Analyze codebase for security vulnerabilities"
          className="w-full rounded-md bg-[var(--color-bg-base)] px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none ring-1 ring-white/10 focus:ring-[var(--color-accent)]"
        />
        {errors.title && <p className="mt-1 text-xs text-[var(--color-danger)]">{errors.title.message}</p>}
      </div>

      {/* Description */}
      <div>
        <label className="block text-xs font-medium text-[var(--color-text-muted)] mb-1">Description</label>
        <textarea
          {...register("description")}
          rows={2}
          placeholder="Brief description of the mission..."
          className="w-full rounded-md bg-[var(--color-bg-base)] px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none ring-1 ring-white/10 focus:ring-[var(--color-accent)] resize-none"
        />
      </div>

      {/* Objective */}
      <div>
        <label className="block text-xs font-medium text-[var(--color-text-muted)] mb-1">Objective</label>
        <textarea
          {...register("objective")}
          rows={2}
          placeholder="What should this mission achieve?"
          className="w-full rounded-md bg-[var(--color-bg-base)] px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none ring-1 ring-white/10 focus:ring-[var(--color-accent)] resize-none"
        />
      </div>

      {/* Priority + Strategy row */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-[var(--color-text-muted)] mb-1">Priority</label>
          <select
            {...register("priority")}
            className="w-full rounded-md bg-[var(--color-bg-base)] px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none ring-1 ring-white/10 focus:ring-[var(--color-accent)]"
          >
            {PRIORITY_OPTIONS.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-[var(--color-text-muted)] mb-1">Strategy</label>
          <select
            {...register("strategy")}
            className="w-full rounded-md bg-[var(--color-bg-base)] px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none ring-1 ring-white/10 focus:ring-[var(--color-accent)]"
          >
            {STRATEGY_OPTIONS.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Planner */}
      <div>
        <label className="block text-xs font-medium text-[var(--color-text-muted)] mb-1">Planner</label>
        <div className="grid grid-cols-2 gap-2">
          {PLANNER_OPTIONS.map((p) => (
            <label
              key={p.value}
              className="flex cursor-pointer items-center gap-2 rounded-md border border-white/10 bg-[var(--color-bg-base)] p-3 transition-colors has-checked:border-[var(--color-accent)] has-checked:bg-[var(--color-accent)]/5 hover:border-white/20"
            >
              <input
                type="radio"
                value={p.value}
                {...register("planner")}
                className="accent-[var(--color-accent)]"
              />
              <div>
                <span className="text-xs font-medium text-[var(--color-text-primary)]">{p.label}</span>
                <p className="text-[10px] text-[var(--color-text-muted)]">{p.desc}</p>
              </div>
            </label>
          ))}
        </div>
      </div>

      {/* Submit */}
      <button
        type="submit"
        disabled={isSubmitting || createMission.isPending}
        className="flex w-full items-center justify-center gap-2 rounded-md bg-[var(--color-accent)] px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
      >
        {createMission.isPending ? (
          <>
            <Loader2 size={14} className="animate-spin" />
            Planning mission...
          </>
        ) : (
          <>
            <Send size={14} />
            Create & Plan Mission
          </>
        )}
      </button>

      {createMission.isError && (
        <p className="text-xs text-[var(--color-danger)]">
          Failed to create mission: {createMission.error.message}
        </p>
      )}

      {createMission.isSuccess && (
        <p className="text-xs text-[var(--color-success)]">Mission created and planned successfully!</p>
      )}
    </form>
  );
}
