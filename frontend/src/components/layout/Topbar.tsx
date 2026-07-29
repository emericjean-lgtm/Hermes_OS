"use client";

import { Menu, Bell, Search } from "lucide-react";
import { useDashboardStore } from "@/store/dashboard-store";
import { useHealth } from "@/hooks/use-dashboard";

export default function Topbar() {
  const { toggleSidebar } = useDashboardStore();
  const { data: health } = useHealth();

  const isHealthy = health?.status === "HEALTHY";

  return (
    <header className="flex h-14 items-center justify-between border-b border-white/10 bg-[var(--color-bg-surface)] px-4">
      {/* Left: hamburger + search */}
      <div className="flex items-center gap-3">
        <button
          onClick={toggleSidebar}
          className="rounded-md p-1.5 text-[var(--color-text-muted)] transition-colors hover:bg-white/5 hover:text-[var(--color-text-primary)] lg:hidden"
          aria-label="Menu"
        >
          <Menu size={20} />
        </button>

        <div className="relative hidden sm:block">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]"
          />
          <input
            type="text"
            placeholder="Search missions, events, memory..."
            className="w-64 rounded-md bg-[var(--color-bg-base)] py-1.5 pl-8 pr-3 text-sm text-[var(--color-text-primary)] outline-none ring-1 ring-white/10 focus:ring-[var(--color-accent)]"
          />
        </div>
      </div>

      {/* Right: status + notifications */}
      <div className="flex items-center gap-4">
        {/* Health indicator */}
        <div className="flex items-center gap-2">
          <span
            className={`h-2 w-2 rounded-full ${
              isHealthy ? "bg-[var(--color-success)]" : "bg-[var(--color-danger)]"
            }`}
          />
          <span className="hidden text-xs text-[var(--color-text-muted)] sm:inline">
            {isHealthy ? "Operational" : "Degraded"}
          </span>
        </div>

        {/* Notifications */}
        <button
          className="relative rounded-md p-1.5 text-[var(--color-text-muted)] transition-colors hover:bg-white/5 hover:text-[var(--color-text-primary)]"
          aria-label="Notifications"
        >
          <Bell size={18} />
          <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-[var(--color-accent)]" />
        </button>
      </div>
    </header>
  );
}
