"use client";

import Link from "next/link";
import { useCockpitStore } from "@/hooks/use-store";

const navItems = [
  { id: "dashboard", label: "Dashboard", icon: "⌂" },
  { id: "conversation", label: "Assistant", icon: "💬" },
  { id: "models", label: "Models", icon: "🧠" },
  { id: "missions", label: "Missions", icon: "◆" },
  { id: "agents", label: "Agents", icon: "◈" },
  { id: "runtime", label: "Runtime", icon: "⚡" },
  { id: "code_intelligence", label: "Code Intel", icon: "🧠" },
  { id: "memory", label: "Memory", icon: "◉" },
  { id: "skills", label: "Skills", icon: "✦" },
  { id: "tools", label: "Tools", icon: "🔧" },
  { id: "governance", label: "Governance", icon: "⚖" },
  { id: "events", label: "Events", icon: "↯" },
  { id: "autonomous", label: "Autonomous", icon: "🧬" },
  { id: "security", label: "Security", icon: "🔒" },
  { id: "system", label: "System", icon: "⊞" },
  { id: "deployment", label: "Deploy", icon: "🚀" },
];

export function Sidebar() {
  const { activeView, setActiveView } = useCockpitStore();

  return (
    <aside className="fixed left-0 top-0 z-40 h-screen w-56 border-r border-hermes-border bg-hermes-surface flex flex-col">
      {/* Logo */}
      <div className="flex items-center gap-2 px-5 py-4 border-b border-hermes-border">
        <span className="text-lg font-mono text-hermes-amber-bright tracking-widest">
          HERMES
        </span>
        <span className="text-[10px] text-hermes-muted font-mono ml-auto">v0.1</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-3">
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => setActiveView(item.id)}
            className={`w-full flex items-center gap-3 px-5 py-2.5 text-sm font-medium transition-all duration-150 ${
              activeView === item.id
                ? "bg-hermes-amber/10 text-hermes-amber-bright border-r-2 border-hermes-amber"
                : "text-hermes-muted hover:text-hermes-text hover:bg-hermes-card/50"
            }`}
          >
            <span className="text-base w-5 text-center">{item.icon}</span>
            {item.label}
          </button>
        ))}
      </nav>

      {/* Footer */}
      <div className="border-t border-hermes-border px-5 py-3">
        <div className="text-[10px] text-hermes-muted font-mono">
          Hermes OS · Mission Control
        </div>
      </div>
    </aside>
  );
}
