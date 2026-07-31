"use client";

import React from "react";
import { motion } from "framer-motion";

/* ═══════════════════════════════════════════════════════════════════
   Shared surface primitives.
   Every Center composes from these, so this file is the single lever
   that sets the visual language of all 25 screens.
   ═══════════════════════════════════════════════════════════════════ */

interface CardProps {
  title?: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
  action?: React.ReactNode;
  /** Orbiting border segment — reserve for panels that are actively
   *  streaming or executing, so "live" stays meaningful. */
  live?: boolean;
  /** Scanline sweep. Opt-in: everywhere at once is nausea, not mood. */
  scan?: boolean;
  accent?: "cyan" | "magenta" | "violet" | "green" | "amber" | "red";
}

const accentBar: Record<string, string> = {
  cyan: "from-hermes-cyan/80",
  magenta: "from-hermes-magenta/80",
  violet: "from-hermes-violet/80",
  green: "from-hermes-green/80",
  amber: "from-hermes-amber/80",
  red: "from-hermes-red/80",
};

export function Card({
  title,
  subtitle,
  children,
  className = "",
  action,
  live = false,
  scan = false,
  accent = "cyan",
}: CardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className={`
        group relative rounded-xl glass neon-edge bracket
        ${live ? "neon-edge-live" : ""}
        ${scan ? "scanline" : ""}
        transition-shadow duration-300 hover:shadow-glow-cyan
        ${className}
      `}
    >
      {title && (
        <div className="relative flex items-center justify-between gap-3 px-4 py-3 border-b border-hermes-border/60">
          {/* Accent rule under the header — a hairline that fades out. */}
          <div
            className={`absolute bottom-0 left-0 h-px w-1/3 bg-gradient-to-r ${accentBar[accent]} to-transparent`}
          />
          <div className="min-w-0">
            <h3 className="text-[11px] font-semibold text-hermes-text uppercase tracking-[0.14em] font-mono truncate">
              {title}
            </h3>
            {subtitle && (
              <p className="text-[10px] text-hermes-muted mt-0.5 truncate font-mono">
                {subtitle}
              </p>
            )}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </div>
      )}
      <div className="relative p-4">{children}</div>
    </motion.div>
  );
}

/* ── Badge ──────────────────────────────────────────────────────── */

const badgeStyles = {
  default: "bg-hermes-border/40 text-hermes-muted border-hermes-border",
  success: "bg-hermes-green/10 text-hermes-green border-hermes-green/40 shadow-glow-green",
  warning: "bg-hermes-amber/10 text-hermes-amber border-hermes-amber/40 shadow-glow-amber",
  danger: "bg-hermes-red/10 text-hermes-red border-hermes-red/40 shadow-glow-red",
  info: "bg-hermes-cyan/10 text-hermes-cyan border-hermes-cyan/40 shadow-glow-cyan",
  purple: "bg-hermes-violet/10 text-hermes-violet border-hermes-violet/40",
  magenta: "bg-hermes-magenta/10 text-hermes-magenta border-hermes-magenta/40 shadow-glow-magenta",
};

interface BadgeProps {
  children: React.ReactNode;
  variant?: keyof typeof badgeStyles;
  className?: string;
}

export function Badge({ children, variant = "default", className = "" }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-mono font-semibold
        uppercase tracking-wider rounded border clip-corner-sm
        ${badgeStyles[variant]} ${className}`}
    >
      {children}
    </span>
  );
}

/* ── Beacon ─────────────────────────────────────────────────────── */

export function Beacon({
  tone = "green",
  className = "",
}: {
  tone?: "green" | "cyan" | "amber" | "red" | "magenta";
  className?: string;
}) {
  const color = {
    green: "text-hermes-green",
    cyan: "text-hermes-cyan",
    amber: "text-hermes-amber",
    red: "text-hermes-red",
    magenta: "text-hermes-magenta",
  }[tone];
  return (
    <span className={`beacon h-2 w-2 rounded-full bg-current ${color} ${className}`} />
  );
}

/* ── StatCard ───────────────────────────────────────────────────── */

interface StatCardProps {
  label: string;
  value: string | number;
  description?: string;
  trend?: "up" | "down" | "neutral";
  icon?: React.ReactNode;
  /** Staggers the entrance so a row of tiles cascades. */
  index?: number;
  className?: string;
}

export function StatCard({
  label,
  value,
  description,
  trend,
  icon,
  index = 0,
  className = "",
}: StatCardProps) {
  const tone =
    trend === "up"
      ? { text: "text-hermes-green", glow: "text-glow-green", grad: "from-hermes-green/60" }
      : trend === "down"
      ? { text: "text-hermes-red", glow: "text-glow-red", grad: "from-hermes-red/60" }
      : { text: "text-hermes-cyan", glow: "text-glow-cyan", grad: "from-hermes-cyan/60" };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.45, delay: index * 0.06, ease: [0.16, 1, 0.3, 1] }}
      className={`group relative rounded-xl glass neon-edge bracket p-4 overflow-hidden
        transition-all duration-300 hover:-translate-y-0.5 hover:shadow-glow-cyan ${className}`}
    >
      {/* Bottom accent rail, widens on hover. */}
      <div
        className={`absolute bottom-0 left-0 h-[2px] w-8 bg-gradient-to-r ${tone.grad} to-transparent
          transition-all duration-500 group-hover:w-full`}
      />
      <div className="flex items-start justify-between gap-2">
        <div className="text-[10px] text-hermes-muted uppercase tracking-[0.14em] font-mono">
          {label}
        </div>
        {icon && (
          <div className={`${tone.text} opacity-50 group-hover:opacity-100 transition-opacity`}>
            {icon}
          </div>
        )}
      </div>
      <div
        className={`mt-1.5 text-3xl font-bold font-mono tabular-nums ${tone.text} ${tone.glow}`}
      >
        {value}
      </div>
      {description && (
        <div className="text-[10px] text-hermes-muted mt-1 font-mono">{description}</div>
      )}
    </motion.div>
  );
}

/* ── ProgressBar ────────────────────────────────────────────────── */

interface ProgressBarProps {
  value: number;
  max?: number;
  className?: string;
  size?: "sm" | "md";
  /** Meters where high is bad (VRAM, temperature) invert the colour ramp. */
  invert?: boolean;
  showLabel?: boolean;
}

export function ProgressBar({
  value,
  max = 100,
  className = "",
  size = "md",
  invert = false,
  showLabel = false,
}: ProgressBarProps) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  // Default ramp reads "more is better" (progress, success rate).
  // invert flips it for saturation meters.
  const good = invert ? pct < 60 : pct >= 80;
  const mid = invert ? pct < 85 : pct >= 40;
  const grad = good
    ? "from-hermes-green to-hermes-cyan"
    : mid
    ? "from-hermes-amber to-hermes-cyan"
    : "from-hermes-red to-hermes-magenta";
  const glow = good
    ? "shadow-glow-green"
    : mid
    ? "shadow-glow-amber"
    : "shadow-glow-red";

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <div
        className={`relative flex-1 bg-hermes-bg-deep/80 rounded-full overflow-hidden
          border border-hermes-border/60 ${size === "sm" ? "h-1.5" : "h-2.5"}`}
      >
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          className={`h-full rounded-full bg-gradient-to-r ${grad} ${glow}`}
        />
      </div>
      {showLabel && (
        <span className="text-[10px] font-mono text-hermes-muted tabular-nums w-9 text-right">
          {pct.toFixed(0)}%
        </span>
      )}
    </div>
  );
}

/* ── Button ─────────────────────────────────────────────────────── */

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "ghost" | "danger" | "success";
  size?: "sm" | "md";
  icon?: React.ReactNode;
}

const buttonVariants = {
  primary:
    "border-hermes-cyan/50 bg-hermes-cyan/10 text-hermes-cyan hover:bg-hermes-cyan/20 hover:border-hermes-cyan hover:shadow-glow-cyan",
  ghost:
    "border-hermes-border text-hermes-muted hover:text-hermes-text hover:border-hermes-border-bright hover:bg-hermes-elevated/60",
  danger:
    "border-hermes-red/50 bg-hermes-red/10 text-hermes-red hover:bg-hermes-red/20 hover:border-hermes-red hover:shadow-glow-red",
  success:
    "border-hermes-green/50 bg-hermes-green/10 text-hermes-green hover:bg-hermes-green/20 hover:border-hermes-green hover:shadow-glow-green",
};

export function Button({
  variant = "ghost",
  size = "md",
  icon,
  children,
  className = "",
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      className={`sweep clip-corner-sm inline-flex items-center justify-center gap-1.5 rounded-md border
        font-mono font-semibold uppercase tracking-wider
        transition-all duration-200 active:scale-[0.97]
        disabled:opacity-40 disabled:pointer-events-none
        ${size === "sm" ? "px-2.5 py-1 text-[10px]" : "px-3.5 py-1.5 text-[11px]"}
        ${buttonVariants[variant]} ${className}`}
    >
      {icon}
      {children}
    </button>
  );
}
