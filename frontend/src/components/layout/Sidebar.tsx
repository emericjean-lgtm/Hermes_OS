"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  MessageSquare,
  Target,
  Bot,
  Cpu,
  Brain,
  Puzzle,
  Activity,
  Database,
  Settings,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { useDashboardStore } from "@/store/dashboard-store";

interface NavItem {
  label: string;
  href: string;
  icon: React.ReactNode;
  section: string;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: <LayoutDashboard size={18} />, section: "main" },
  { label: "Chat", href: "/", icon: <MessageSquare size={18} />, section: "main" },
  { label: "Missions", href: "/missions", icon: <Target size={18} />, section: "main" },
  { label: "Agents", href: "/agents", icon: <Bot size={18} />, section: "main" },
  { label: "Runtime", href: "/runtimes", icon: <Cpu size={18} />, section: "infra" },
  { label: "Memory", href: "/memory", icon: <Brain size={18} />, section: "infra" },
  { label: "Skills", href: "/skills", icon: <Puzzle size={18} />, section: "infra" },
  { label: "Events", href: "/events", icon: <Activity size={18} />, section: "infra" },
  { label: "Infrastructure", href: "/settings", icon: <Database size={18} />, section: "settings" },
  { label: "Settings", href: "/settings", icon: <Settings size={18} />, section: "settings" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { sidebarOpen, toggleSidebar } = useDashboardStore();

  return (
    <aside
      className={`fixed inset-y-0 left-0 z-40 flex flex-col border-r border-white/10 bg-[var(--color-bg-surface)] transition-all duration-300 ${
        sidebarOpen ? "w-60" : "w-0 lg:w-16"
      } overflow-hidden`}
    >
      {/* Logo */}
      <div className="flex h-14 items-center justify-between border-b border-white/10 px-4">
        {sidebarOpen && (
          <span className="text-sm font-bold tracking-tight text-[var(--color-accent)]">
            Hermes OS
          </span>
        )}
        <button
          onClick={toggleSidebar}
          className="rounded-md p-1.5 text-[var(--color-text-muted)] transition-colors hover:bg-white/5 hover:text-[var(--color-text-primary)]"
          aria-label={sidebarOpen ? "Réduire" : "Développer"}
        >
          {sidebarOpen ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 overflow-y-auto px-2 py-4">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors ${
                isActive
                  ? "bg-[var(--color-accent)]/15 text-[var(--color-accent)]"
                  : "text-[var(--color-text-muted)] hover:bg-white/5 hover:text-[var(--color-text-primary)]"
              }`}
              title={item.label}
            >
              <span className="shrink-0">{item.icon}</span>
              {sidebarOpen && <span className="truncate">{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="border-t border-white/10 px-4 py-3">
        {sidebarOpen && (
          <p className="text-[10px] text-[var(--color-text-muted)]">
            Hermes OS v0.1 · HOS-029
          </p>
        )}
      </div>
    </aside>
  );
}
