"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";

/* ══════════════════════════════════════════════════════════════════════
   Instrument primitives — "SODIUM".

   Every one of the 22 Centers composes from this file, which makes it the
   single lever that sets the visual language of the whole cockpit. The
   props are unchanged from the previous system on purpose: the Centers
   keep working untouched and simply inherit the new material.

   The governing idea is that these are machined plates on a lit surface,
   not web cards: chamfered corners rather than uniform rounding, a hairline
   that carries the room's single light source, registration ticks instead
   of a drawn border, and a spotlight that tracks the real cursor so depth
   responds to the operator instead of glowing on every hover.
   ══════════════════════════════════════════════════════════════════════ */

interface CardProps {
  title?: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
  action?: React.ReactNode;
  /** Running edge — reserve for panels genuinely streaming or executing,
   *  so "live" keeps meaning something. */
  live?: boolean;
  /** Scanline sweep. Opt-in; everywhere at once is nausea, not mood. */
  scan?: boolean;
  accent?: "cyan" | "magenta" | "violet" | "green" | "amber" | "red";
  /** Technical reference printed in the header, drawing-style. */
  ref_?: string;
}

const accentVar: Record<string, string> = {
  cyan: "var(--hermes-sodium)",
  magenta: "var(--hermes-glacier)",
  violet: "var(--hermes-steel)",
  green: "var(--hermes-arc)",
  amber: "var(--hermes-gold)",
  red: "var(--hermes-alarm)",
};

/** Tracks the pointer within an element and exposes it as --mx/--my, which
 *  the `.spotlight` rule reads. Pointer position is written straight to the
 *  node's style rather than into React state: this fires on every mousemove
 *  and re-rendering a panel at that rate would be pure waste. */
function useSpotlight<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const onMouseMove = useCallback((e: React.MouseEvent) => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    el.style.setProperty("--mx", `${e.clientX - r.left}px`);
    el.style.setProperty("--my", `${e.clientY - r.top}px`);
  }, []);
  return { ref, onMouseMove };
}

export function Card({
  title,
  subtitle,
  children,
  className = "",
  action,
  live = false,
  scan = false,
  accent = "cyan",
  ref_,
}: CardProps) {
  const { ref, onMouseMove } = useSpotlight<HTMLDivElement>();

  return (
    <motion.div
      ref={ref}
      onMouseMove={onMouseMove}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 260, damping: 28 }}
      className={`group relative clip-corner glass neon-edge bracket spotlight
        ${live ? "neon-edge-live" : ""}
        ${scan ? "scanline" : ""}
        ${className}`}
    >
      {title && (
        <div className="relative flex items-center justify-between gap-3 px-4 py-2.5
          border-b border-hermes-border/70">
          {/* Accent tick at the header's leading edge — a short, solid mark
              that names the panel's domain, rather than a full rule. */}
          <span
            className="absolute left-0 top-1/2 -translate-y-1/2 h-3.5 w-[2px]"
            style={{ background: accentVar[accent] }}
          />
          <div className="min-w-0 pl-2">
            <h3 className="display text-[12.5px] leading-tight text-hermes-text truncate">
              {title}
            </h3>
            {subtitle && (
              <p className="text-[10.5px] text-hermes-muted mt-0.5 truncate">{subtitle}</p>
            )}
          </div>
          <div className="flex items-center gap-3 shrink-0">
            {ref_ && <span className="tech-label hidden sm:inline">{ref_}</span>}
            {action}
          </div>
        </div>
      )}
      <div className="relative p-4">{children}</div>
    </motion.div>
  );
}

/* ── Badge ────────────────────────────────────────────────────────────
   A stamped chip: flat fill, hairline edge, no shadow. Badges appear in
   dense tables, and a glowing badge in every row destroys the hierarchy
   that glow is supposed to create. */

const badgeStyles = {
  default: "text-hermes-muted border-hermes-border bg-hermes-elevated/60",
  success: "text-hermes-arc border-hermes-arc/45 bg-hermes-arc/[0.09]",
  warning: "text-hermes-gold border-hermes-gold/45 bg-hermes-gold/[0.09]",
  danger: "text-hermes-alarm border-hermes-alarm/45 bg-hermes-alarm/[0.09]",
  info: "text-hermes-sodium border-hermes-sodium/45 bg-hermes-sodium/[0.09]",
  purple: "text-hermes-steel border-hermes-steel/45 bg-hermes-steel/[0.09]",
  magenta: "text-hermes-glacier border-hermes-glacier/45 bg-hermes-glacier/[0.09]",
};

interface BadgeProps {
  children: React.ReactNode;
  variant?: keyof typeof badgeStyles;
  className?: string;
}

export function Badge({ children, variant = "default", className = "" }: BadgeProps) {
  return (
    <span
      className={`num inline-flex items-center gap-1 px-1.5 py-[3px] text-[9.5px]
        font-medium uppercase tracking-[0.11em] border clip-corner-sm leading-none
        ${badgeStyles[variant]} ${className}`}
    >
      {children}
    </span>
  );
}

/* ── Beacon ── */

export function Beacon({
  tone = "green",
  className = "",
}: {
  tone?: "green" | "cyan" | "amber" | "red" | "magenta";
  className?: string;
}) {
  const color = {
    green: "text-hermes-arc",
    cyan: "text-hermes-sodium",
    amber: "text-hermes-gold",
    red: "text-hermes-alarm",
    magenta: "text-hermes-glacier",
  }[tone];
  return <span className={`beacon h-1.5 w-1.5 bg-current ${color} ${className}`} />;
}

/* ── StatCard ─────────────────────────────────────────────────────────
   A gauge, not a card: the label sits above a large tabular readout, and
   the value counts up on mount so a changing figure reads as an instrument
   settling rather than a number being replaced. */

interface StatCardProps {
  label: string;
  value: string | number;
  description?: string;
  trend?: "up" | "down" | "neutral";
  icon?: React.ReactNode;
  index?: number;
  className?: string;
}

/* A count-up animation was tried here and deliberately removed.
 *
 * Rolling a readout from 0 to its target means the panel spends a few hundred
 * milliseconds displaying a number that is not the reading — "0 échecs" while
 * there are three. On a cockpit whose whole discipline is that a displayed
 * value is a measured value, that is a decorative flourish which misreports
 * state, and it also put a wrong value in the DOM for anything reading the
 * page synchronously. The panel's own entrance spring already supplies the
 * sense of an instrument settling; the figure itself arrives correct. */

export function StatCard({
  label,
  value,
  description,
  trend,
  icon,
  index = 0,
  className = "",
}: StatCardProps) {
  const { ref, onMouseMove } = useSpotlight<HTMLDivElement>();

  const tone =
    trend === "up"
      ? { text: "text-hermes-arc", bar: "var(--hermes-arc)" }
      : trend === "down"
      ? { text: "text-hermes-alarm", bar: "var(--hermes-alarm)" }
      : { text: "text-hermes-sodium", bar: "var(--hermes-sodium)" };

  return (
    <motion.div
      ref={ref}
      onMouseMove={onMouseMove}
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 300, damping: 30, delay: index * 0.05 }}
      className={`group relative clip-corner glass neon-edge bracket spotlight
        px-4 pt-3.5 pb-4 overflow-hidden transition-transform duration-300
        hover:-translate-y-[2px] ${className}`}
    >
      {/* Measure rail along the bottom edge: a short segment that runs the
          full width on hover, like a scale being read off. */}
      <span
        className="absolute bottom-0 left-0 h-[2px] w-7 transition-all duration-[550ms]
          ease-out-expo group-hover:w-full"
        style={{ background: `linear-gradient(90deg, ${tone.bar}, transparent)` }}
      />
      <div className="flex items-start justify-between gap-2">
        <span className="tech-label">{label}</span>
        {icon && (
          <span className={`${tone.text} opacity-40 group-hover:opacity-90 transition-opacity`}>
            {icon}
          </span>
        )}
      </div>
      <div className={`display num mt-2 text-[30px] leading-none ${tone.text}`}>
        {value}
      </div>
      {description && (
        <div className="text-[10.5px] text-hermes-muted mt-1.5 leading-snug">{description}</div>
      )}
    </motion.div>
  );
}

/* ── ProgressBar ──────────────────────────────────────────────────────
   A segmented meter rather than a smooth capsule: discrete cells read
   faster at a glance and echo real instrument bar graphs. */

interface ProgressBarProps {
  value: number;
  max?: number;
  className?: string;
  size?: "sm" | "md";
  /** Meters where high is bad (VRAM, temperature) invert the colour ramp. */
  invert?: boolean;
  showLabel?: boolean;
}

const SEGMENTS = 24;

export function ProgressBar({
  value,
  max = 100,
  className = "",
  size = "md",
  invert = false,
  showLabel = false,
}: ProgressBarProps) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  // Default ramp reads "more is better" (progress, success rate); invert
  // flips it for saturation meters.
  const good = invert ? pct < 60 : pct >= 80;
  const mid = invert ? pct < 85 : pct >= 40;
  const sante = good
    ? "var(--hermes-arc)"
    : mid
    ? "var(--hermes-gold)"
    : "var(--hermes-alarm)";

  /* Direction C (HOS-197) : la mesure est portée par le sodium, la santé
     se retire au bord.

     Avant, l'échelle vert/ambre/rouge remplissait la barre entière. Le
     défaut n'est pas esthétique : comme presque tout va bien presque tout
     le temps, l'écran était vert, et un vert de plus ne se distinguait
     d'aucun autre. Mesuré sur le Dashboard en marche le 2026-08-27 —
     quarante et un éléments verts contre treize sodium, alors que le
     sodium est l'accent censé porter « le système qui parle ». Un rouge
     doit redevenir une rupture ; il ne l'est pas s'il n'est qu'une
     troisième valeur d'un dégradé qu'on lit tous les jours.

     Le segment de tête garde donc la teinte de santé — c'est la marque
     que Direction C place au bord du remplissage —, et le halo est le
     seul endroit où la couleur de santé rayonne. Le reste est sodium. */
  const lit = Math.round((pct / 100) * SEGMENTS);
  const accent = "var(--hermes-sodium)";

  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <div
        className={`flex-1 flex gap-[2px] ${size === "sm" ? "h-1.5" : "h-2.5"}`}
        role="progressbar"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        {Array.from({ length: SEGMENTS }).map((_, i) => (
          <motion.span
            key={i}
            initial={{ opacity: 0.15 }}
            animate={{ opacity: i < lit ? 1 : 0.15 }}
            transition={{ duration: 0.24, delay: i * 0.012 }}
            className="flex-1"
            style={{
              // Le dernier segment allumé porte la santé ; tous les autres
              // portent l'accent. La lecture reste immédiate — c'est la
              // tête de la barre qu'on regarde — sans que la santé occupe
              // toute la surface.
              background:
                i >= lit
                  ? "var(--hermes-border)"
                  : i === lit - 1
                  ? sante
                  : accent,
              boxShadow: i === lit - 1 ? `0 0 7px ${sante}` : "none",
            }}
          />
        ))}
      </div>
      {showLabel && (
        <span className="num text-[10px] text-hermes-muted tabular-nums w-9 text-right">
          {pct.toFixed(0)}%
        </span>
      )}
    </div>
  );
}

/* ── Button ───────────────────────────────────────────────────────────
   Keyed switches: flat, chamfered, with a real pressed state. Only the
   primary variant carries the sodium fill — if every control glows,
   nothing reads as the main action.

   HOS-197, planche de pièces retenue (`.design/cockpit/Composants.dc.html`) :
   le remplissage entre par la gauche, dans le sens de lecture, au lieu de
   monter en opacité partout à la fois. Et le clic **enfonce** d'un pixel
   sans rétrécir — un bouton d'instrument s'enfonce, il ne rétrécit pas ;
   `active:scale-[0.985]`, qui faisait exactement cela, est retiré. */

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "ghost" | "danger" | "success";
  size?: "sm" | "md";
  icon?: React.ReactNode;
}

/** Chaque variante déclare sa teinte de remplissage et la couleur que le
 *  libellé prend une fois rempli. Le fond plein réclame un texte sombre :
 *  du sodium sur du sodium ne se lit pas. */
const buttonVariants: Record<string, { classes: string; fill: string }> = {
  primary: {
    classes:
      "border-hermes-sodium/55 bg-hermes-sodium/[0.12] text-hermes-sodium " +
      "hover:border-hermes-sodium hover:shadow-glow-cyan hover:!text-hermes-bg",
    fill: "var(--hermes-sodium)",
  },
  ghost: {
    classes:
      "border-hermes-border text-hermes-muted hover:text-hermes-text " +
      "hover:border-hermes-border-bright",
    fill: "var(--hermes-elevated)",
  },
  danger: {
    classes:
      "border-hermes-alarm/55 bg-hermes-alarm/[0.12] text-hermes-alarm " +
      "hover:border-hermes-alarm hover:!text-hermes-bg",
    fill: "var(--hermes-alarm)",
  },
  success: {
    classes:
      "border-hermes-arc/55 bg-hermes-arc/[0.12] text-hermes-arc " +
      "hover:border-hermes-arc hover:!text-hermes-bg",
    fill: "var(--hermes-arc)",
  },
};

export function Button({
  variant = "ghost",
  size = "md",
  icon,
  children,
  className = "",
  style,
  ...rest
}: ButtonProps) {
  const v = buttonVariants[variant] ?? buttonVariants.ghost;
  return (
    <button
      {...rest}
      style={{ ...style, ["--btn-fill" as string]: v.fill }}
      className={`btn-fill clip-corner-sm num inline-flex items-center justify-center gap-1.5 border
        uppercase tracking-[0.1em] font-medium
        transition-all duration-200
        active:translate-y-[1px]
        disabled:opacity-35 disabled:pointer-events-none
        ${size === "sm" ? "px-2.5 py-1 text-[9.5px]" : "px-3.5 py-1.5 text-[10.5px]"}
        ${v.classes} ${className}`}
    >
      {icon}
      {children}
    </button>
  );
}
