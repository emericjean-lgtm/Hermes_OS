"use client";

import React, { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Brain, Check, ChevronDown, Cpu, Gauge, Sparkles, Telescope, Zap } from "lucide-react";
import type { SystemModelRoleDTO } from "@/services/client";

/**
 * Manual model choice + reasoning-effort presets (HOS-075).
 *
 * Both are the same real mechanism underneath — a forced
 * `config/models.yaml` role, optionally overriding whether the model
 * reasons before answering (`ModelRouter.decision_for_role`, HOS-075). The
 * three "effort" presets are not a continuous dial: Hermes doesn't modulate
 * how much one model thinks, it swaps to a genuinely different, larger
 * model for harder tiers — showing a smooth slider here would claim a
 * capability that doesn't exist under the hood.
 */

export interface ModelSelection {
  /** A real config/models.yaml role name, or "" for automatic routing. */
  role: string;
  /** undefined keeps the task type's own reasoning policy. */
  thinking?: boolean;
}

const AUTO: ModelSelection = { role: "" };

const EFFORT_PRESETS: { role: string; thinking: boolean; label: string; icon: React.ElementType; blurb: string }[] = [
  { role: "standard", thinking: false, label: "Rapide", icon: Zap,
    blurb: "Réponse directe, sans détour par le raisonnement." },
  { role: "reasoning", thinking: true, label: "Réfléchi", icon: Brain,
    blurb: "Le modèle raisonne avant de répondre." },
  { role: "reasoning_escalation", thinking: true, label: "Approfondi", icon: Telescope,
    blurb: "Le modèle le plus capable du parc, raisonnement activé." },
];

function tierIcon(tier: string) {
  if (tier === "turbo") return Zap;
  if (tier === "powerful") return Telescope;
  return Cpu;
}

export function ModelPicker({
  roles, value, onChange,
}: {
  roles: SystemModelRoleDTO[];
  value: ModelSelection;
  onChange: (v: ModelSelection) => void;
}) {
  const [open, setOpen] = useState(false);

  const byRole = useMemo(
    () => new Map(roles.map((r) => [r.role, r])),
    [roles],
  );
  const presetRoleNames = useMemo(() => new Set(EFFORT_PRESETS.map((p) => p.role)), []);
  const otherRoles = useMemo(
    () => roles.filter((r) => r.role !== "embedding" && !presetRoleNames.has(r.role)),
    [roles, presetRoleNames],
  );

  const activePreset = EFFORT_PRESETS.find(
    (p) => p.role === value.role && p.thinking === value.thinking,
  );
  const activeOther = !activePreset ? byRole.get(value.role) : undefined;

  const label = !value.role ? "Auto" : activePreset?.label ?? activeOther?.model ?? value.role;
  const LabelIcon = !value.role ? Sparkles : activePreset?.icon ?? Cpu;

  const pick = (sel: ModelSelection) => { onChange(sel); setOpen(false); };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 rounded-lg border border-hermes-border bg-hermes-elevated/50
          px-2.5 py-1.5 font-mono text-[10px] text-hermes-muted transition-all
          hover:border-hermes-cyan/40 hover:text-hermes-cyan"
      >
        <LabelIcon size={11} />
        <span className="max-w-[110px] truncate">{label}</span>
        <ChevronDown size={10} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      <AnimatePresence>
        {open && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
            <motion.div
              initial={{ opacity: 0, y: -4, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -4, scale: 0.97 }}
              transition={{ duration: 0.15 }}
              className="absolute left-0 top-full z-20 mt-2 w-72 overflow-hidden rounded-xl
                border border-hermes-border bg-hermes-card shadow-2xl"
            >
              <div className="max-h-96 overflow-y-auto p-1.5">
                <Option
                  active={!value.role}
                  icon={<Sparkles size={13} className="text-hermes-cyan" />}
                  label="Auto"
                  detail="Hermes choisit selon la tâche"
                  onClick={() => pick(AUTO)}
                />

                <SectionLabel>Effort de réflexion</SectionLabel>
                {EFFORT_PRESETS.map((p) => {
                  const role = byRole.get(p.role);
                  const Icon = p.icon;
                  return (
                    <Option
                      key={p.role}
                      active={value.role === p.role && value.thinking === p.thinking}
                      icon={<Icon size={13} className="text-hermes-violet" />}
                      label={p.label}
                      detail={role ? `${role.model} · ${p.blurb}` : p.blurb}
                      disabled={!role}
                      onClick={() => role && pick({ role: p.role, thinking: p.thinking })}
                    />
                  );
                })}

                <SectionLabel>Modèle spécifique</SectionLabel>
                {otherRoles.map((r) => {
                  const Icon = tierIcon(r.tier);
                  return (
                    <Option
                      key={r.role}
                      active={value.role === r.role && value.thinking === undefined}
                      icon={<Icon size={13} className="text-hermes-cyan/70" />}
                      label={r.model}
                      detail={r.description || r.role}
                      badge={r.loaded ? "chargé" : undefined}
                      onClick={() => pick({ role: r.role })}
                    />
                  );
                })}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-2.5 pb-1 pt-2.5 font-mono text-[9px] uppercase tracking-[0.14em] text-hermes-dim">
      {children}
    </div>
  );
}

function Option({
  active, icon, label, detail, badge, disabled, onClick,
}: {
  active: boolean;
  icon: React.ReactNode;
  label: string;
  detail: string;
  badge?: string;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors
        disabled:cursor-not-allowed disabled:opacity-40
        ${active ? "bg-hermes-cyan/[0.09]" : "hover:bg-hermes-elevated/60"}`}
    >
      <span className="mt-0.5 shrink-0">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          <span className="truncate font-mono text-[11.5px] text-hermes-text-bright">{label}</span>
          {badge && (
            <span className="shrink-0 rounded border border-hermes-green/40 bg-hermes-green/10
              px-1 py-0 font-mono text-[8.5px] uppercase text-hermes-green">{badge}</span>
          )}
        </span>
        <span className="line-clamp-1 text-[10px] text-hermes-muted">{detail}</span>
      </span>
      {active && <Check size={13} className="mt-0.5 shrink-0 text-hermes-cyan" />}
    </button>
  );
}

/** Context-window usage for the current turn (HOS-075) — an honest
 *  estimate against the selected role's real, benchmarked num_ctx.
 *  Rendered as a fill bar rather than bare digits: a bar reads at a
 *  glance next to the composer, where a percentage competes with the
 *  Auto/model label for the same few pixels of attention. */
export function ContextMeter({ used, window: ctxWindow }: { used: number; window: number }) {
  if (!ctxWindow) return null;
  const pct = Math.min(100, (used / ctxWindow) * 100);
  const tone = pct > 90 ? "bg-hermes-red" : pct > 70 ? "bg-hermes-amber" : "bg-hermes-cyan";
  const textTone = pct > 90 ? "text-hermes-red" : pct > 70 ? "text-hermes-amber" : "text-hermes-dim";
  return (
    <div
      className="flex items-center gap-1.5"
      title={`${used.toLocaleString()} / ${ctxWindow.toLocaleString()} tokens (estimation)`}
    >
      <Gauge size={10} className={textTone} />
      <div className="h-1.5 w-14 overflow-hidden rounded-full border border-hermes-border/60 bg-hermes-bg-deep">
        <motion.div
          className={`h-full rounded-full ${tone}`}
          initial={false}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        />
      </div>
      <span className={`font-mono text-[9.5px] tabular-nums ${textTone}`}>{pct.toFixed(0)}%</span>
    </div>
  );
}
