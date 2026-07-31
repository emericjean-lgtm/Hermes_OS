"use client";

import { motion } from "framer-motion";
import {
  useSystemHealth, useSystemStatistics, useMissions, useAgents,
  useRuntimes, useApprovals,
} from "@/hooks/use-api";
import { useWebSocket, severityColor } from "@/hooks/use-websocket";
import { useCockpitStore } from "@/hooks/use-store";
import { Card, Badge, StatCard, ProgressBar, Beacon } from "@/components/ui/card";
import { PanelLoading } from "@/components/center-scaffold";
import {
  Target, Users, Zap, ShieldAlert, CheckCircle2, XCircle,
  Activity, ArrowRight, Radio,
} from "lucide-react";

/** Écran d'accueil du cockpit. Tout ce qui est affiché ici vient d'un
 *  endpoint réel ; aucune valeur n'est simulée pour remplir la mise en page.
 *  Quand une donnée manque, elle est montrée comme manquante. */
export function DashboardView() {
  const { data: health, isLoading: healthLoading } = useSystemHealth();
  const { data: stats } = useSystemStatistics();
  const { data: missions } = useMissions();
  const { data: agents } = useAgents();
  const { data: runtimes } = useRuntimes();
  const { data: approvals } = useApprovals();
  const { events: liveEvents, connected } = useWebSocket({ maxEvents: 14 });
  const setActiveView = useCockpitStore((s) => s.setActiveView);

  const activeMissions =
    missions?.filter((m) => ["RUNNING", "PLANNING", "READY"].includes(m.status)).length ?? 0;
  const completedMissions = missions?.filter((m) => m.status === "COMPLETED").length ?? 0;
  const failedMissions = missions?.filter((m) => m.status === "FAILED").length ?? 0;
  const activeAgents =
    agents?.filter((a) => a.status === "BUSY" || a.status === "STARTING").length ?? 0;
  const pendingApprovals = approvals?.filter((a) => a.status === "PENDING").length ?? 0;

  const subsystems = Object.entries(health?.subsystems ?? {});
  const healthy = subsystems.filter(([, s]) => s.status === "HEALTHY").length;
  const healthPct = subsystems.length ? (healthy / subsystems.length) * 100 : 0;

  const status = health?.status ?? "UNKNOWN";
  const tone =
    status === "HEALTHY"
      ? { text: "text-hermes-green", glow: "text-glow-green", beacon: "green" as const }
      : status === "DEGRADED"
      ? { text: "text-hermes-amber", glow: "text-glow-amber", beacon: "amber" as const }
      : { text: "text-hermes-red", glow: "text-glow-red", beacon: "red" as const };

  return (
    <div>
      {/* ── Bandeau titre ─────────────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
        className="relative mb-6 rounded-xl glass neon-edge bracket scanline overflow-hidden"
      >
        <div className="relative flex items-center justify-between gap-6 px-6 py-5">
          <div className="min-w-0">
            <div className="flex items-center gap-3">
              <span className="h-8 w-[3px] rounded-full bg-gradient-to-b from-hermes-cyan to-hermes-magenta shadow-glow-cyan" />
              <div>
                <h1 className="text-3xl font-bold font-mono tracking-tight text-gradient-cyan leading-none">
                  HERMES OS
                </h1>
                <p className="text-[11px] text-hermes-muted font-mono mt-2 tracking-[0.16em] uppercase">
                  AI Operations Cockpit — Autonomous Mission Control
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <div
              className={`flex items-center gap-2.5 px-4 py-2.5 rounded-lg border clip-corner
                glass-bright ${tone.text} border-current/40`}
            >
              <Beacon tone={tone.beacon} />
              <div>
                <div className={`text-sm font-mono font-bold tracking-wider ${tone.glow}`}>
                  {status}
                </div>
                {subsystems.length > 0 && (
                  <div className="text-[10px] text-hermes-muted font-mono tabular-nums mt-0.5">
                    {healthy}/{subsystems.length} sous-systèmes
                  </div>
                )}
              </div>
            </div>
            <Badge variant={connected ? "success" : "danger"}>
              {connected && <Beacon tone="green" />}
              {connected ? "WS LIVE" : "WS OFF"}
            </Badge>
          </div>
        </div>

        {/* Jauge de santé globale, collée au bas du bandeau. */}
        {subsystems.length > 0 && (
          <div className="h-[3px] w-full bg-hermes-bg-deep">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${healthPct}%` }}
              transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1] }}
              className="h-full bg-gradient-to-r from-hermes-green via-hermes-cyan to-hermes-violet shadow-glow-cyan"
            />
          </div>
        )}
      </motion.div>

      {/* ── Tuiles clés ───────────────────────────────────────────── */}
      <div className="grid grid-cols-5 gap-3 mb-6">
        <StatCard index={0} label="Missions actives" value={activeMissions}
          icon={<Target size={15} />} trend={activeMissions > 0 ? "up" : "neutral"} />
        <StatCard index={1} label="Terminées" value={completedMissions}
          icon={<CheckCircle2 size={15} />} trend="up" />
        <StatCard index={2} label="Échouées" value={failedMissions}
          icon={<XCircle size={15} />} trend={failedMissions > 0 ? "down" : "neutral"} />
        <StatCard index={3} label="Agents occupés" value={`${activeAgents}/${agents?.length ?? 0}`}
          icon={<Users size={15} />} trend={activeAgents > 0 ? "up" : "neutral"} />
        <StatCard index={4} label="Approbations" value={pendingApprovals}
          icon={<ShieldAlert size={15} />} trend={pendingApprovals > 0 ? "down" : "neutral"}
          description={pendingApprovals > 0 ? "en attente humaine" : undefined} />
      </div>

      {/* ── Trois colonnes ────────────────────────────────────────── */}
      <div className="grid grid-cols-3 gap-4 mb-4">
        {/* Santé par sous-système */}
        <Card
          title="Santé des sous-systèmes"
          subtitle={subsystems.length ? `${healthy} sains sur ${subsystems.length}` : undefined}
          accent="green"
          action={<GoTo view="health" onGo={setActiveView} />}
        >
          {healthLoading ? (
            <PanelLoading />
          ) : subsystems.length === 0 ? (
            <Empty label="Aucun sous-système rapporté" />
          ) : (
            <div className="flex flex-col gap-1.5 max-h-[248px] overflow-y-auto pr-1">
              {subsystems.slice(0, 12).map(([name, sub], i) => (
                <motion.div
                  key={name}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: Math.min(i * 0.03, 0.3) }}
                  className="group flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-md
                    bg-hermes-bg-deep/50 border border-hermes-border/40
                    hover:border-hermes-cyan/30 transition-colors"
                >
                  <span className="text-[11px] text-hermes-text font-mono truncate">{name}</span>
                  <Badge
                    variant={
                      sub.status === "HEALTHY" ? "success"
                      : sub.status === "DEGRADED" ? "warning"
                      : "danger"
                    }
                  >
                    {sub.status}
                  </Badge>
                </motion.div>
              ))}
            </div>
          )}
        </Card>

        {/* Runtimes */}
        <Card
          title="Runtimes"
          subtitle={`${runtimes?.length ?? 0} enregistré(s)`}
          accent="violet"
          action={<GoTo view="runtime" onGo={setActiveView} />}
        >
          {!runtimes ? (
            <PanelLoading />
          ) : runtimes.length === 0 ? (
            <Empty label="Aucun runtime enregistré" />
          ) : (
            <div className="flex flex-col gap-1.5 max-h-[248px] overflow-y-auto pr-1">
              {runtimes.map((rt) => (
                <div
                  key={rt.name}
                  className="flex items-center justify-between gap-2 px-2.5 py-2 rounded-md
                    bg-hermes-bg-deep/50 border border-hermes-border/40
                    hover:border-hermes-violet/30 transition-colors"
                >
                  <div className="min-w-0">
                    <div className="text-[11px] text-hermes-text font-mono truncate">{rt.name}</div>
                    {rt.type && (
                      <div className="text-[9px] text-hermes-dim font-mono mt-0.5">{rt.type}</div>
                    )}
                  </div>
                  <Badge
                    variant={
                      rt.status === "AVAILABLE" || rt.status === "started" ? "success"
                      : rt.status === "DEGRADED" ? "warning"
                      : "danger"
                    }
                  >
                    {rt.status}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Flux d'événements */}
        <Card
          title="Flux d'événements"
          subtitle={connected ? "temps réel" : "déconnecté"}
          accent="magenta"
          live={connected}
          action={<GoTo view="events" onGo={setActiveView} />}
        >
          {liveEvents.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 py-8">
              <Radio size={18} className={connected ? "text-hermes-cyan/40" : "text-hermes-dim"} />
              <span className="text-[10px] text-hermes-muted font-mono">
                {connected ? "En écoute…" : "Flux indisponible"}
              </span>
            </div>
          ) : (
            <div className="flex flex-col gap-0.5 max-h-[248px] overflow-y-auto font-mono pr-1">
              {liveEvents.map((evt, i) => (
                <motion.div
                  key={`${evt.type}-${i}`}
                  initial={{ opacity: 0, x: 8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.25 }}
                  className="flex items-center gap-2 py-1 px-1.5 rounded text-[10px]
                    hover:bg-hermes-cyan/[0.04] transition-colors"
                >
                  <span className={`w-1 h-1 rounded-full shrink-0 ${severityColor(evt.severity).replace("text-", "bg-")}`} />
                  <span className="text-hermes-violet w-16 shrink-0 truncate">{evt.source}</span>
                  <span className="text-hermes-cyan shrink-0 truncate max-w-[90px]">{evt.type}</span>
                  <span className="text-hermes-dim truncate flex-1">
                    {typeof evt.payload === "object" && evt.payload
                      ? JSON.stringify(evt.payload).slice(0, 48)
                      : ""}
                  </span>
                </motion.div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* ── Missions + Agents ─────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-4">
        <Card
          title="Missions récentes"
          subtitle={`${activeMissions} active(s)`}
          accent="cyan"
          action={<GoTo view="missions" onGo={setActiveView} />}
        >
          {!missions ? (
            <PanelLoading />
          ) : missions.length === 0 ? (
            <Empty label="Aucune mission — lancez-en une depuis le Mission Center" />
          ) : (
            <div className="flex flex-col gap-2 max-h-[260px] overflow-y-auto pr-1">
              {missions.slice(0, 8).map((m) => (
                <div
                  key={m.id}
                  className="group flex items-center justify-between gap-3 p-2.5 rounded-lg
                    bg-hermes-bg-deep/50 border border-hermes-border/40
                    hover:border-hermes-cyan/30 transition-all"
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-[11px] text-hermes-text font-medium truncate">
                      {m.title || "(sans titre)"}
                    </div>
                    <div className="text-[9px] text-hermes-dim font-mono mt-0.5">
                      {m.priority} · {m.completed_nodes ?? 0}/{m.node_count ?? "?"} nœuds
                    </div>
                  </div>
                  <div className="w-20 shrink-0 hidden sm:block">
                    <ProgressBar value={m.progress ?? 0} size="sm" />
                  </div>
                  <Badge
                    variant={
                      m.status === "RUNNING" ? "purple"
                      : m.status === "COMPLETED" ? "success"
                      : m.status === "FAILED" ? "danger"
                      : "default"
                    }
                  >
                    {m.status}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card
          title="Agents"
          subtitle={`${activeAgents} occupé(s) sur ${agents?.length ?? 0}`}
          accent="violet"
          action={<GoTo view="agents" onGo={setActiveView} />}
        >
          {!agents ? (
            <PanelLoading />
          ) : agents.length === 0 ? (
            <Empty label="Aucun agent enregistré" />
          ) : (
            <div className="flex flex-col gap-2 max-h-[260px] overflow-y-auto pr-1">
              {agents.slice(0, 8).map((a) => (
                <div
                  key={a.id}
                  className="flex items-center justify-between gap-3 p-2.5 rounded-lg
                    bg-hermes-bg-deep/50 border border-hermes-border/40
                    hover:border-hermes-violet/30 transition-all"
                >
                  <div className="min-w-0">
                    <div className="text-[11px] text-hermes-text font-medium truncate">{a.name}</div>
                    <div className="text-[9px] text-hermes-dim font-mono mt-0.5 truncate">
                      {a.type}{a.runtime ? ` · ${a.runtime}` : ""}
                    </div>
                  </div>
                  <Badge
                    variant={
                      a.status === "READY" ? "success"
                      : a.status === "BUSY" ? "purple"
                      : a.status === "ERROR" ? "danger"
                      : "default"
                    }
                  >
                    {a.status}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* ── Compteurs du moteur d'exécution ───────────────────────── */}
      {stats && (
        <div className="grid grid-cols-4 gap-3 mt-4">
          <MiniStat label="Tâches planifiées" value={stats.missions_total} icon={<Activity size={13} />} />
          <MiniStat label="Agents enregistrés" value={stats.agents_total} icon={<Users size={13} />} />
          <MiniStat label="Runtimes dispo." value={stats.runtimes_healthy} icon={<Zap size={13} />} />
          <MiniStat label="Entrées mémoire" value={stats.memory_entries} icon={<Target size={13} />} />
        </div>
      )}
    </div>
  );
}

/* ── Sous-composants ────────────────────────────────────────────── */

function GoTo({ view, onGo }: { view: string; onGo: (v: string) => void }) {
  return (
    <button
      onClick={() => onGo(view)}
      className="sweep group flex items-center gap-1 px-2 py-1 rounded border border-hermes-border
        text-[9px] font-mono uppercase tracking-wider text-hermes-muted
        hover:text-hermes-cyan hover:border-hermes-cyan/50 transition-all active:scale-95"
    >
      Ouvrir
      <ArrowRight size={9} className="transition-transform group-hover:translate-x-0.5" />
    </button>
  );
}

function Empty({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 justify-center py-8">
      <span className="text-hermes-dim font-mono text-xs">◇</span>
      <span className="text-[10px] text-hermes-muted font-mono">{label}</span>
    </div>
  );
}

function MiniStat({
  label, value, icon,
}: { label: string; value: number; icon: React.ReactNode }) {
  return (
    <div className="group flex items-center gap-3 px-3.5 py-2.5 rounded-lg glass neon-edge
      hover:shadow-glow-cyan transition-all duration-300">
      <span className="text-hermes-cyan/50 group-hover:text-hermes-cyan transition-colors">
        {icon}
      </span>
      <div className="min-w-0">
        <div className="text-[9px] text-hermes-muted font-mono uppercase tracking-[0.12em] truncate">
          {label}
        </div>
        <div className="text-sm font-bold font-mono text-hermes-text tabular-nums">{value}</div>
      </div>
    </div>
  );
}
