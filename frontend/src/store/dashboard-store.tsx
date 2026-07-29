"use client";

import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from "react";

interface DashboardState {
  /** Sidebar ouverte/fermée (mobile) */
  sidebarOpen: boolean;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;

  /** Événements en direct (timeline) */
  liveEventsEnabled: boolean;
  toggleLiveEvents: () => void;

  /** Filtre de sévérité pour les événements */
  eventSeverityFilter: string | null;
  setEventSeverityFilter: (severity: string | null) => void;

  /** Intervalle auto-refresh (ms) */
  refreshInterval: number;
  setRefreshInterval: (ms: number) => void;
}

const DashboardContext = createContext<DashboardState | null>(null);

export function DashboardProvider({ children }: { children: ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [liveEventsEnabled, setLiveEventsEnabled] = useState(true);
  const [eventSeverityFilter, setEventSeverityFilter] = useState<string | null>(null);
  const [refreshInterval, setRefreshInterval] = useState(15_000);

  const toggleSidebar = useCallback(() => setSidebarOpen((p) => !p), []);
  const toggleLiveEvents = useCallback(() => setLiveEventsEnabled((p) => !p), []);

  return (
    <DashboardContext.Provider
      value={{
        sidebarOpen,
        toggleSidebar,
        setSidebarOpen,
        liveEventsEnabled,
        toggleLiveEvents,
        eventSeverityFilter,
        setEventSeverityFilter,
        refreshInterval,
        setRefreshInterval,
      }}
    >
      {children}
    </DashboardContext.Provider>
  );
}

export function useDashboardStore() {
  const ctx = useContext(DashboardContext);
  if (!ctx) throw new Error("useDashboardStore must be inside DashboardProvider");
  return ctx;
}
