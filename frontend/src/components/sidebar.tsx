"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { useCockpitStore } from "@/hooks/use-store";
import {
  LayoutDashboard, MessageSquare, Brain, Target, Users, Zap, Code2,
  Database, Sparkles, Wrench, Scale, Radio, FlaskConical, Dna,
  ShieldCheck, LayoutGrid, Rocket, Play, FolderTree, Network,
  Library, ScrollText, CheckCircle2, LineChart, HeartPulse,
  ChevronLeft, ChevronRight, Search,
} from "lucide-react";

/** La navigation était une liste plate de 25 entrées : au-delà d'une dizaine,
 *  une liste plate n'est plus une navigation, c'est un inventaire. Les entrées
 *  sont regroupées par domaine — ce qui rend aussi visible la redondance
 *  Governance/Policy (mêmes hooks, mêmes données) signalée dans le rapport. */
const groups: {
  label: string;
  accent: string;
  items: { id: string; label: string; icon: React.ElementType }[];
}[] = [
  {
    label: "Pilotage",
    accent: "cyan",
    items: [
      { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
      { id: "conversation", label: "Assistant", icon: MessageSquare },
      { id: "missions", label: "Missions", icon: Target },
      { id: "execution", label: "Execution", icon: Play },
      { id: "autonomous", label: "Autonomous", icon: Dna },
    ],
  },
  {
    label: "Intelligence",
    accent: "violet",
    items: [
      { id: "models", label: "Models", icon: Brain },
      { id: "agents", label: "Agents", icon: Users },
      { id: "runtime", label: "Runtime", icon: Zap },
      { id: "code_intelligence", label: "Code Intel", icon: Code2 },
      { id: "skills", label: "Skills", icon: Sparkles },
      { id: "tools", label: "Tools", icon: Wrench },
    ],
  },
  {
    label: "Connaissance",
    accent: "magenta",
    items: [
      { id: "memory", label: "Memory", icon: Database },
      { id: "knowledge", label: "Knowledge", icon: Network },
      { id: "alexandrie", label: "Alexandrie", icon: Library },
      { id: "workspace", label: "Workspace", icon: FolderTree },
    ],
  },
  {
    label: "Gouvernance",
    accent: "amber",
    items: [
      { id: "governance", label: "Governance", icon: Scale },
      { id: "policy", label: "Policy", icon: ScrollText },
      { id: "security", label: "Security", icon: ShieldCheck },
      { id: "validation", label: "Validation", icon: CheckCircle2 },
      { id: "evolution", label: "Evolution", icon: FlaskConical },
    ],
  },
  {
    label: "Opérations",
    accent: "green",
    items: [
      { id: "health", label: "Health", icon: HeartPulse },
      { id: "monitoring", label: "Monitoring", icon: LineChart },
      { id: "events", label: "Events", icon: Radio },
      { id: "system", label: "System", icon: LayoutGrid },
      { id: "deployment", label: "Deploy", icon: Rocket },
    ],
  },
];

const accentClasses: Record<string, { text: string; bg: string; shadow: string }> = {
  cyan: { text: "text-hermes-cyan", bg: "bg-hermes-cyan", shadow: "shadow-glow-cyan" },
  violet: { text: "text-hermes-violet", bg: "bg-hermes-violet", shadow: "" },
  magenta: { text: "text-hermes-magenta", bg: "bg-hermes-magenta", shadow: "shadow-glow-magenta" },
  amber: { text: "text-hermes-amber", bg: "bg-hermes-amber", shadow: "shadow-glow-amber" },
  green: { text: "text-hermes-green", bg: "bg-hermes-green", shadow: "shadow-glow-green" },
};

export function Sidebar() {
  const { activeView, setActiveView, navCollapsed: collapsed, toggleNav } = useCockpitStore();
  const [filter, setFilter] = useState("");

  const q = filter.trim().toLowerCase();
  const visible = groups
    .map((g) => ({
      ...g,
      items: q ? g.items.filter((i) => i.label.toLowerCase().includes(q)) : g.items,
    }))
    .filter((g) => g.items.length > 0);

  return (
    <motion.aside
      animate={{ width: collapsed ? 68 : 232 }}
      transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
      className="fixed left-0 top-0 z-40 h-screen flex flex-col
        border-r border-hermes-border glass overflow-hidden"
    >
      {/* Filet lumineux vertical sur le bord droit. */}
      <div className="absolute right-0 top-0 h-full w-px bg-gradient-to-b from-hermes-cyan/50 via-hermes-violet/25 to-transparent" />

      {/* ── Logo ── */}
      <div className="relative flex items-center gap-2.5 px-4 h-14 border-b border-hermes-border/60 shrink-0">
        <div className="relative shrink-0">
          <div className="h-7 w-7 rounded-md bg-gradient-to-br from-hermes-cyan to-hermes-magenta
            flex items-center justify-center shadow-glow-cyan clip-corner-sm">
            <span className="text-[13px] font-bold font-mono text-hermes-bg-deep">H</span>
          </div>
        </div>
        {!collapsed && (
          <motion.div
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            className="min-w-0 flex-1"
          >
            <div className="text-sm font-bold font-mono tracking-[0.2em] text-gradient-cyan leading-none">
              HERMES
            </div>
            <div className="text-[9px] text-hermes-dim font-mono tracking-[0.15em] mt-1">
              MISSION CONTROL
            </div>
          </motion.div>
        )}
        <button
          onClick={toggleNav}
          className="shrink-0 h-6 w-6 rounded flex items-center justify-center
            text-hermes-dim hover:text-hermes-cyan hover:bg-hermes-cyan/10 transition-all"
          aria-label={collapsed ? "Déplier la navigation" : "Replier la navigation"}
        >
          {collapsed ? <ChevronRight size={13} /> : <ChevronLeft size={13} />}
        </button>
      </div>

      {/* ── Filtre ── */}
      {!collapsed && (
        <div className="px-3 py-2.5 border-b border-hermes-border/40 shrink-0">
          <div className="relative group">
            <Search
              size={11}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-hermes-dim
                group-focus-within:text-hermes-cyan transition-colors pointer-events-none"
            />
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filtrer…"
              className="w-full bg-hermes-bg-deep/60 border border-hermes-border rounded-md
                pl-7 pr-2 py-1.5 text-[11px] font-mono text-hermes-text
                placeholder:text-hermes-dim focus:outline-none
                focus:border-hermes-cyan/50 focus:shadow-glow-cyan transition-all"
            />
          </div>
        </div>
      )}

      {/* ── Navigation ── */}
      <nav className="flex-1 overflow-y-auto overflow-x-hidden py-2">
        {visible.map((group) => {
          const a = accentClasses[group.accent];
          return (
            <div key={group.label} className="mb-1">
              {!collapsed && (
                <div className="px-4 pt-2.5 pb-1 flex items-center gap-2">
                  <span className={`text-[9px] font-mono uppercase tracking-[0.18em] ${a.text} opacity-70`}>
                    {group.label}
                  </span>
                  <span className="flex-1 h-px bg-gradient-to-r from-hermes-border to-transparent" />
                </div>
              )}
              {group.items.map((item) => {
                const active = activeView === item.id;
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    onClick={() => setActiveView(item.id)}
                    title={item.label}
                    // Le libellé visible est enveloppé dans des couches
                    // animées ; sans nom explicite, l'arbre d'accessibilité
                    // exposait 25 boutons anonymes.
                    aria-label={item.label}
                    aria-current={active ? "page" : undefined}
                    className={`group relative w-full flex items-center gap-3 px-4 py-2
                      text-[12px] font-medium transition-all duration-200
                      ${active ? a.text : "text-hermes-muted hover:text-hermes-text"}`}
                  >
                    {/* Barre active : animée entre les entrées via layoutId. */}
                    {active && (
                      <motion.span
                        layoutId="nav-active"
                        transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
                        className={`absolute inset-y-0.5 left-0 w-full rounded-r-md
                          bg-gradient-to-r from-current/[0.14] to-transparent`}
                      />
                    )}
                    {active && (
                      <motion.span
                        layoutId="nav-active-rail"
                        transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
                        className={`absolute left-0 inset-y-1 w-[2px] rounded-full ${a.bg} ${a.shadow}`}
                      />
                    )}
                    {/* Halo au survol pour les entrées inactives. */}
                    {!active && (
                      <span className="absolute inset-y-0.5 left-0 w-full rounded-r-md bg-hermes-elevated/0
                        group-hover:bg-hermes-elevated/50 transition-colors" />
                    )}
                    <Icon
                      size={15}
                      className={`relative shrink-0 transition-transform duration-200
                        ${active ? "scale-110" : "group-hover:scale-110 group-hover:translate-x-0.5"}`}
                    />
                    {!collapsed && <span className="relative truncate">{item.label}</span>}
                  </button>
                );
              })}
            </div>
          );
        })}
        {visible.length === 0 && !collapsed && (
          <div className="px-4 py-6 text-center text-[10px] text-hermes-dim font-mono">
            Aucun écran ne correspond
          </div>
        )}
      </nav>

      {/* ── Pied ── */}
      {!collapsed && (
        <div className="border-t border-hermes-border/60 px-4 py-2.5 shrink-0">
          <div className="flex items-center justify-between">
            <span className="text-[9px] text-hermes-dim font-mono tracking-wider">
              {groups.reduce((n, g) => n + g.items.length, 0)} CENTERS
            </span>
            <span className="text-[9px] text-hermes-dim font-mono">v0.1</span>
          </div>
        </div>
      )}
    </motion.aside>
  );
}
