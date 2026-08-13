"use client";

import { create } from "zustand";
import type { SystemEvent } from "@/types/hermes";

interface CockpitStore {
  // Navigation
  activeView: string;
  setActiveView: (view: string) => void;
  /** Lives in the store rather than in Rail's local state because the
   *  shell, the instrument bar and the status bar all have to offset by
   *  the same rail width; a local useState would leave them out of sync
   *  with whichever one owns the toggle button. Pinned = the rail is
   *  expanded (labels visible, wider) until unpinned; default false
   *  matches the rail's normal narrow-icon-strip state. */
  railPinned: boolean;
  toggleRailPin: () => void;

  // Events
  liveEvents: SystemEvent[];
  addLiveEvent: (event: SystemEvent) => void;
  clearLiveEvents: () => void;

  // Filters
  eventSeverityFilter: string[];
  setEventSeverityFilter: (filter: string[]) => void;
  eventSourceFilter: string[];
  setEventSourceFilter: (filter: string[]) => void;

  // WebSocket
  wsConnected: boolean;
  setWsConnected: (connected: boolean) => void;

  // Selection
  selectedMissionId: string | null;
  selectMission: (id: string | null) => void;
  selectedAgentId: string | null;
  selectAgent: (id: string | null) => void;
  /** The autonomous goal being watched. Kept here rather than in
   *  AutonomousCenter's own useState because the Cockpit shell keys its
   *  AnimatePresence on the active view: switching tabs unmounts the
   *  Center outright, and the goal id went with it while the goal kept
   *  running on the server (HOS-102). MissionCenter has always used
   *  selectedMissionId above for exactly this reason. */
  selectedGoalId: string | null;
  selectGoal: (id: string | null) => void;
}

export const useCockpitStore = create<CockpitStore>((set) => ({
  // Navigation
  activeView: "dashboard",
  setActiveView: (view) => set({ activeView: view }),
  railPinned: false,
  toggleRailPin: () => set((s) => ({ railPinned: !s.railPinned })),

  // Events
  liveEvents: [],
  addLiveEvent: (event) =>
    set((s) => ({ liveEvents: [event, ...s.liveEvents].slice(0, 200) })),
  clearLiveEvents: () => set({ liveEvents: [] }),

  // Filters
  eventSeverityFilter: [],
  setEventSeverityFilter: (filter) => set({ eventSeverityFilter: filter }),
  eventSourceFilter: [],
  setEventSourceFilter: (filter) => set({ eventSourceFilter: filter }),

  // WebSocket
  wsConnected: false,
  setWsConnected: (connected) => set({ wsConnected: connected }),

  // Selection
  selectedMissionId: null,
  selectMission: (id) => set({ selectedMissionId: id }),
  selectedAgentId: null,
  selectAgent: (id) => set({ selectedAgentId: id }),
  selectedGoalId: null,
  selectGoal: (id) => set({ selectedGoalId: id }),
}));
