"use client";

import { motion } from "framer-motion";

interface CardProps {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
  action?: React.ReactNode;
}

export function Card({ title, subtitle, children, className = "", action }: CardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={`bg-hermes-card border border-hermes-border rounded-lg overflow-hidden ${className}`}
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-hermes-border/50">
        <div>
          <h3 className="text-xs font-semibold text-hermes-text uppercase tracking-wider">
            {title}
          </h3>
          {subtitle && (
            <p className="text-[10px] text-hermes-muted mt-0.5">{subtitle}</p>
          )}
        </div>
        {action && <div>{action}</div>}
      </div>
      <div className="p-4">{children}</div>
    </motion.div>
  );
}

// ── Badge ────────────────────────────────────────────
const badgeStyles = {
  default: "bg-hermes-border/50 text-hermes-muted border-hermes-border",
  success: "bg-hermes-green/15 text-hermes-green border-hermes-green/30",
  warning: "bg-hermes-amber/15 text-hermes-amber border-hermes-amber/30",
  danger: "bg-hermes-red/15 text-hermes-red border-hermes-red/30",
  info: "bg-hermes-blue/15 text-hermes-blue border-hermes-blue/30",
  purple: "bg-hermes-purple/15 text-hermes-purple border-hermes-purple/30",
};

interface BadgeProps {
  children: React.ReactNode;
  variant?: keyof typeof badgeStyles;
  className?: string;
}

export function Badge({ children, variant = "default", className = "" }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 text-[10px] font-mono font-medium rounded border ${badgeStyles[variant]} ${className}`}
    >
      {children}
    </span>
  );
}

// ── StatCard ─────────────────────────────────────────
interface StatCardProps {
  label: string;
  value: string | number;
  description?: string;
  trend?: "up" | "down" | "neutral";
  className?: string;
}

export function StatCard({ label, value, description, trend, className = "" }: StatCardProps) {
  const trendColor =
    trend === "up"
      ? "text-hermes-green"
      : trend === "down"
      ? "text-hermes-red"
      : "text-hermes-muted";

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className={`bg-hermes-card border border-hermes-border rounded-lg p-4 ${className}`}
    >
      <div className="text-[10px] text-hermes-muted uppercase tracking-wider font-mono mb-1">
        {label}
      </div>
      <div className={`text-2xl font-bold font-mono ${trendColor}`}>{value}</div>
      {description && (
        <div className="text-[11px] text-hermes-muted mt-1">{description}</div>
      )}
    </motion.div>
  );
}

// ── ProgressBar ──────────────────────────────────────
interface ProgressBarProps {
  value: number;
  max?: number;
  className?: string;
  size?: "sm" | "md";
}

export function ProgressBar({ value, max = 100, className = "", size = "md" }: ProgressBarProps) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  const color =
    pct >= 80 ? "bg-hermes-green" : pct >= 50 ? "bg-hermes-amber" : "bg-hermes-red";

  return (
    <div
      className={`w-full bg-hermes-border/30 rounded-full overflow-hidden ${
        size === "sm" ? "h-1" : "h-2"
      } ${className}`}
    >
      <div
        className={`h-full rounded-full transition-all duration-500 ${color}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
