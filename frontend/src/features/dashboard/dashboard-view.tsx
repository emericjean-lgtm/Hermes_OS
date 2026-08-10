"use client";

import { motion } from "framer-motion";
import {
  useSystemHealth, useSystemStatistics, useMissions, useAgents,
  useRuntimes, useApprovals, useResourceStatus,
} from "@/hooks/use-api";
import { useWebSocket, severityColor } from "@/hooks/use-websocket";
import { useCockpitStore } from "@/hooks/use-store";
import { Card, Badge, ProgressBar } from "@/components/ui/card";
import { PanelLoading } from "@/components/center-scaffold";
import {
  Target, Users, Zap, ShieldAlert, ArrowUpRight, Radio, Cpu, Database, Check,
} from "lucide-react";

/** The cockpit's landing surface.
 *
 *  Laid out around the operator's real questions, in the order they matter:
 *  is anything waiting on *me*, is the machine healthy, what is running,
 *  and what just happened. That hierarchy — not a grid of equal tiles — is
 *  what decides the sizes here: approvals get width because they block, the
 *  vitals stack gets a narrow permanent column because it is glanced at
 *  rather than read, and missions get the full measure because they are the
 *  thing you actually work on.
 *
 *  Every value comes from a real endpoint. Where data is missing it is shown
 *  as missing; nothing is padded with a plausible-looking number. */
export function DashboardView() {
  const { data: health, isLoading: healthLoading } = useSystemHealth();
  const { data: stats } = useSystemStatistics();
  const { data: missions } = useMissions();
  const { data: agents } = useAgents();
  const { data: runtimes } = useRuntimes();
  const { data: approvals } = useApprovals();
  const { data: res } = useResourceStatus();
  const { events: liveEvents, connected } = useWebSocket({ maxEvents: 18 });
  const setActiveView = useCockpitStore((s) => s.setActiveView);

  const activeMissions =
    missions?.filter((m) => ["RUNNING", "PLANNING", "READY"].includes(m.status)).length ?? 0;
  const failedMissions = missions?.filter((m) => m.status === "FAILED").length ?? 0;
  const activeAgents =
    agents?.filter((a) => a.status === "BUSY" || a.status === "STARTING").length ?? 0;
  const pending = approvals?.filter((a) => a.status === "PENDING") ?? [];

  const subsystems = Object.entries(health?.subsystems ?? {});
  const healthy = subsystems.filter(([, s]) => s.status === "HEALTHY").length;
  // Real, distinct from "degraded" — see types/hermes.ts's SubsystemHealth
  // comment. A subsystem with no telemetry accessor wired yet is an
  // architectural gap, not an incident; showing both as one amber count
  // makes "12 problems" out of what's actually "0 problems, 12 unmeasured".
  const notInstrumented = subsystems.filter(([, s]) => s.status === "NOT_INSTRUMENTED").length;
  const trulyDegraded = subsystems.length - healthy - notInstrumented;

  const status = health?.status ?? "UNKNOWN";
  const statusTone =
    status === "HEALTHY"
      ? { text: "text-hermes-arc", label: "NOMINAL", dot: "bg-hermes-arc" }
      : status === "DEGRADED"
      ? { text: "text-hermes-gold", label: "DÉGRADÉ", dot: "bg-hermes-gold" }
      : status === "UNKNOWN"
      ? { text: "text-hermes-dim", label: "INCONNU", dot: "bg-hermes-dim" }
      : { text: "text-hermes-alarm", label: "CRITIQUE", dot: "bg-hermes-alarm" };

  const vramPct =
    res?.gpu && res.gpu.vram_total_bytes > 0
      ? (res.gpu.vram_used_bytes / res.gpu.vram_total_bytes) * 100
      : null;

  return (
    <div className="grid grid-cols-12 gap-4">
      {/* ══ MASTHEAD ═══════════════════════════════════════════════════
          A nameplate, not a hero banner: the wordmark set once at scale,
          the machine's own name beside it, and the subsystem census read
          as a segmented matrix rather than a percentage bar. */}
      <motion.section
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: "spring", stiffness: 240, damping: 26 }}
        className="col-span-12 relative clip-corner glass neon-edge bracket scanline overflow-hidden"
      >
        <div className="flex flex-wrap items-end justify-between gap-6 px-6 pt-5 pb-4">
          <div className="min-w-0">
            <div className="tech-label mb-2">Cockpit d&apos;opérations · agents autonomes locaux</div>
            <h1 className="display animate-strike text-[38px] leading-[0.92] tracking-[-0.02em]">
              <span className="text-hermes-text">HERMES</span>
              <span className="text-gradient-sodium"> OS</span>
            </h1>
          </div>

          <div className="flex items-end gap-7">
            {res?.gpu?.name && (
              <Readout label="Processeur graphique" value={res.gpu.name} mono={false} wide />
            )}
            {/* Three real states, not one ratio: a "23/35" reads as "12
                problems" whether those 12 are genuinely degraded or simply
                unmeasured — very different things to act on. */}
            <div>
              <div className="tech-label mb-1.5">Sous-systèmes</div>
              {subsystems.length === 0 ? (
                <div className="num text-[13px] text-hermes-text leading-none">––</div>
              ) : (
                <div className="flex items-baseline gap-2.5">
                  <span className="num text-[13px] text-hermes-arc leading-none" title="Sains">
                    {healthy}
                  </span>
                  {trulyDegraded > 0 && (
                    <span className="num text-[13px] text-hermes-alarm leading-none" title="Dégradés">
                      {trulyDegraded} dégr.
                    </span>
                  )}
                  {notInstrumented > 0 && (
                    <span className="num text-[13px] text-hermes-dim leading-none" title="Aucun accesseur de télémétrie — pas une panne">
                      {notInstrumented} non instr.
                    </span>
                  )}
                </div>
              )}
            </div>
            <div>
              <div className="tech-label mb-1.5">État</div>
              <div className="flex items-center gap-2">
                <span className={`relative flex h-2 w-2 ${statusTone.dot}`}>
                  <span className={`absolute inline-flex h-full w-full ${statusTone.dot} opacity-60 animate-ping`} />
                </span>
                <span className={`display text-[15px] leading-none ${statusTone.text}`}>
                  {statusTone.label}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Subsystem census. One cell per subsystem, coloured by its real
            status — a census reads faster than an aggregate percentage, and
            a single red cell in a row of green is impossible to miss. A
            not-instrumented cell is rendered as a dim diagonal hatch rather
            than a solid colour — visually "no reading" is a different claim
            from "bad reading", and collapsing them into one amber signal
            was exactly the ambiguity this render used to have. */}
        <div className="px-6 pb-4">
          {subsystems.length === 0 ? (
            <div className="h-[6px] w-full bg-hermes-border/40" />
          ) : (
            <div className="flex gap-[2px] h-[6px]" title={`${healthy} sains · ${trulyDegraded} dégradés · ${notInstrumented} non instrumentés`}>
              {subsystems.map(([name, sub], i) => (
                <motion.span
                  key={name}
                  initial={{ opacity: 0, scaleY: 0.3 }}
                  animate={{ opacity: 1, scaleY: 1 }}
                  transition={{ delay: Math.min(i * 0.012, 0.4), duration: 0.3 }}
                  title={`${name} — ${statusFr(sub.status)}`}
                  className="flex-1 origin-bottom"
                  style={
                    sub.status === "NOT_INSTRUMENTED"
                      ? {
                          background:
                            "repeating-linear-gradient(135deg, var(--hermes-border-bright) 0px, var(--hermes-border-bright) 2px, transparent 2px, transparent 4px)",
                        }
                      : {
                          background:
                            sub.status === "HEALTHY"
                              ? "var(--hermes-arc)"
                              : sub.status === "DEGRADED"
                              ? "var(--hermes-gold)"
                              : "var(--hermes-alarm)",
                        }
                  }
                />
              ))}
            </div>
          )}
        </div>
      </motion.section>

      {/* ══ MAIN COLUMN ════════════════════════════════════════════════ */}
      <div className="col-span-12 xl:col-span-9 flex flex-col gap-4">
        {/* Primary readouts — three, not five, and sized unequally: the
            count that changes most often carries the most weight. */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <BigReadout
            index={0}
            label="Missions actives"
            value={activeMissions}
            total={missions?.length}
            icon={<Target size={14} />}
            tone="sodium"
            onOpen={() => setActiveView("missions")}
            className="lg:col-span-2"
          />
          <BigReadout
            index={1}
            label="Agents occupés"
            value={activeAgents}
            total={agents?.length}
            icon={<Users size={14} />}
            tone="steel"
            onOpen={() => setActiveView("agents")}
          />
          <BigReadout
            index={2}
            label="Échecs"
            value={failedMissions}
            icon={<ShieldAlert size={14} />}
            tone={failedMissions > 0 ? "alarm" : "muted"}
            onOpen={() => setActiveView("missions")}
          />
        </div>

        {/* Approvals and the live bus, side by side. Approvals lead because
            they are the only thing on this screen that blocks progress. */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
          <Card
            title="En attente de vous"
            subtitle={pending.length ? `${pending.length} décision(s) requise(s)` : undefined}
            accent="magenta"
            ref_="S4.01"
            className="lg:col-span-2"
            action={<GoTo onGo={() => setActiveView("governance")} />}
          >
            {!approvals ? (
              <PanelLoading />
            ) : pending.length === 0 ? (
              /* A composed clear state, not a shrug. Nothing waiting is
                 good news and should read as such. */
              <div className="flex flex-col items-center justify-center gap-2.5 py-9">
                <span className="flex h-8 w-8 items-center justify-center clip-corner-sm
                  border border-hermes-arc/40 bg-hermes-arc/[0.07]">
                  <Check size={14} className="text-hermes-arc" />
                </span>
                <span className="text-[11.5px] text-hermes-muted">Aucune décision en attente</span>
                <span className="tech-label">File d&apos;approbation vide</span>
              </div>
            ) : (
              <div className="flex flex-col gap-1.5 max-h-[210px] overflow-y-auto pr-1">
                {pending.slice(0, 6).map((a, i) => (
                  <motion.button
                    key={a.id ?? i}
                    onClick={() => setActiveView("governance")}
                    initial={{ opacity: 0, x: -6 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: Math.min(i * 0.04, 0.25) }}
                    className="group text-left flex items-start gap-2.5 px-2.5 py-2 clip-corner-sm
                      border border-hermes-glacier/25 bg-hermes-glacier/[0.05]
                      hover:border-hermes-glacier/60 hover:bg-hermes-glacier/[0.1] transition-all"
                  >
                    <span className="mt-[3px] h-1.5 w-1.5 shrink-0 bg-hermes-glacier" />
                    <span className="min-w-0 flex-1">
                      <span className="block text-[11.5px] text-hermes-text truncate">
                        {a.operation}
                      </span>
                      <span className="block num text-[9.5px] text-hermes-dim truncate mt-0.5">
                        {a.requested_by} · {a.priority}
                      </span>
                    </span>
                    <ArrowUpRight
                      size={11}
                      className="shrink-0 mt-0.5 text-hermes-dim group-hover:text-hermes-glacier transition-colors"
                    />
                  </motion.button>
                ))}
              </div>
            )}
          </Card>

          <Card
            title="Bus d'événements"
            subtitle={connected ? "flux temps réel" : "flux indisponible"}
            accent="violet"
            ref_="S5.03"
            live={connected}
            className="lg:col-span-3"
            action={<GoTo onGo={() => setActiveView("events")} />}
          >
            {liveEvents.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-2.5 py-9">
                <Radio size={16} className={connected ? "text-hermes-sodium/50" : "text-hermes-dim"} />
                <span className="text-[11.5px] text-hermes-muted">
                  {connected ? "En écoute — aucun événement encore" : "Bus déconnecté"}
                </span>
              </div>
            ) : (
              <div className="flex flex-col max-h-[210px] overflow-y-auto pr-1">
                {liveEvents.map((evt, i) => (
                  <motion.div
                    key={`${evt.type}-${i}`}
                    initial={{ opacity: 0, x: 10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.22 }}
                    className="group flex items-center gap-2.5 py-[5px] px-1.5
                      border-b border-hermes-border/30 last:border-0
                      hover:bg-hermes-sodium/[0.04] transition-colors"
                  >
                    <span
                      className={`h-1 w-1 shrink-0 ${severityColor(evt.severity).replace("text-", "bg-")}`}
                    />
                    <span className="num text-[9.5px] text-hermes-steel w-[104px] shrink-0 truncate">
                      {evt.source}
                    </span>
                    <span className="num text-[9.5px] text-hermes-sodium shrink-0 truncate max-w-[150px]">
                      {evt.type}
                    </span>
                    <span className="text-[10px] text-hermes-dim truncate flex-1 hidden sm:block">
                      {typeof evt.payload === "object" && evt.payload
                        ? JSON.stringify(evt.payload).slice(0, 60)
                        : ""}
                    </span>
                  </motion.div>
                ))}
              </div>
            )}
          </Card>
        </div>

        {/* Missions get the full measure — the thing you actually work on. */}
        <Card
          title="Missions"
          subtitle={missions?.length ? `${missions.length} au total` : undefined}
          accent="cyan"
          ref_="S1.03"
          action={<GoTo onGo={() => setActiveView("missions")} />}
        >
          {!missions ? (
            <PanelLoading />
          ) : missions.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 py-10">
              <Target size={18} className="text-hermes-dim" />
              <span className="text-[11.5px] text-hermes-muted">Aucune mission enregistrée</span>
              <span className="tech-label">Lancez-en une depuis le Mission Center</span>
            </div>
          ) : (
            <div className="flex flex-col max-h-[300px] overflow-y-auto">
              {missions.slice(0, 10).map((m, i) => (
                <motion.button
                  key={m.id}
                  onClick={() => setActiveView("missions")}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(i * 0.03, 0.3) }}
                  className="group text-left grid grid-cols-12 items-center gap-3 px-2 py-2.5
                    border-b border-hermes-border/30 last:border-0
                    hover:bg-hermes-sodium/[0.04] transition-colors"
                >
                  <span className="col-span-12 sm:col-span-5 min-w-0 flex items-center gap-2.5">
                    <span className="num text-[9px] text-hermes-dim shrink-0 w-5">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span className="min-w-0">
                      <span className="block text-[12px] text-hermes-text truncate">
                        {m.title || "(sans titre)"}
                      </span>
                      {m.plan_is_generic && (
                        <span className="num text-[9px] text-hermes-gold">plan générique</span>
                      )}
                    </span>
                  </span>
                  <span className="col-span-4 sm:col-span-2 num text-[10px] text-hermes-dim">
                    {m.completed_nodes ?? 0}/{m.node_count ?? "?"} nœuds
                  </span>
                  <span className="col-span-5 sm:col-span-3">
                    <ProgressBar value={m.progress ?? 0} size="sm" />
                  </span>
                  <span className="col-span-3 sm:col-span-2 flex justify-end">
                    <Badge
                      variant={
                        m.status === "RUNNING" ? "info"
                        : m.status === "COMPLETED" ? "success"
                        : m.status === "FAILED" ? "danger"
                        : "default"
                      }
                    >
                      {m.status}
                    </Badge>
                  </span>
                </motion.button>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* ══ VITALS STACK ═══════════════════════════════════════════════
          A narrow permanent column, read the way an engine instrument
          stack is read: glanced at, never studied. Deliberately dense and
          deliberately not card-shaped. */}
      <aside className="col-span-12 xl:col-span-3 flex flex-col gap-4">
        <div className="clip-corner glass neon-edge bracket p-4">
          <div className="tech-label mb-3">Ressources</div>

          <VitalRow
            icon={<Cpu size={11} />}
            label="VRAM"
            value={vramPct !== null ? `${Math.round(vramPct)}%` : "––"}
            sub={
              res?.gpu && res.gpu.vram_total_bytes > 0
                ? `${gb(res.gpu.vram_used_bytes)} / ${gb(res.gpu.vram_total_bytes)} Go`
                : "indisponible"
            }
            pct={vramPct}
          />
          <VitalRow
            icon={<Database size={11} />}
            label="RAM"
            value={
              typeof res?.ram?.usage_pct === "number" ? `${Math.round(res.ram.usage_pct)}%` : "––"
            }
            sub={
              res?.ram && res.ram.total_bytes > 0
                ? `${gb(res.ram.used_bytes)} / ${gb(res.ram.total_bytes)} Go`
                : "indisponible"
            }
            pct={typeof res?.ram?.usage_pct === "number" ? res.ram.usage_pct : null}
          />
        </div>

        <div className="clip-corner glass neon-edge bracket p-4 flex-1">
          <div className="flex items-center justify-between mb-3">
            <span className="tech-label">Runtimes</span>
            <GoTo onGo={() => setActiveView("runtime")} />
          </div>
          {!runtimes ? (
            <PanelLoading />
          ) : runtimes.length === 0 ? (
            <p className="text-[11px] text-hermes-muted py-3">Aucun runtime enregistré</p>
          ) : (
            <div className="flex flex-col gap-1.5">
              {runtimes.slice(0, 5).map((rt) => (
                <div
                  key={rt.name}
                  className="flex items-center justify-between gap-2 px-2 py-1.5 clip-corner-sm
                    border border-hermes-border/50 bg-hermes-bg-deep/40"
                >
                  <span className="text-[11px] text-hermes-text truncate">{rt.name}</span>
                  <Badge
                    variant={
                      rt.status === "AVAILABLE" || rt.status === "started" ? "success"
                      : rt.status === "DEGRADED" ? "warning"
                      : "default"
                    }
                  >
                    {rt.status}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="clip-corner glass neon-edge bracket p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="tech-label">Santé détaillée</span>
            <GoTo onGo={() => setActiveView("health")} />
          </div>
          {healthLoading ? (
            <PanelLoading />
          ) : subsystems.length === 0 ? (
            <p className="text-[11px] text-hermes-muted py-3">Aucun sous-système rapporté</p>
          ) : (
            <div className="flex flex-col gap-1 max-h-[220px] overflow-y-auto pr-1">
              {/* Real problems first — the only entries with a warning/danger
                  badge. Deliberately separate from the not-instrumented list
                  below rather than one undifferentiated "non-healthy" list. */}
              {subsystems
                .filter(([, s]) => s.status === "DEGRADED" || s.status === "UNHEALTHY")
                .map(([name, sub]) => (
                  <div key={name} className="flex items-center justify-between gap-2 py-1">
                    <span className="num text-[10px] text-hermes-text truncate">{name}</span>
                    <Badge variant={sub.status === "DEGRADED" ? "warning" : "danger"}>
                      {sub.status}
                    </Badge>
                  </div>
                ))}

              {trulyDegraded === 0 && (
                <div className="flex items-center gap-2 py-1">
                  <Check size={12} className="text-hermes-arc shrink-0" />
                  <span className="text-[11px] text-hermes-muted">Aucun problème réel</span>
                </div>
              )}

              {notInstrumented > 0 && (
                <>
                  <div className="tech-label !text-[8px] mt-2 pt-2 border-t border-hermes-border/50">
                    Non instrumentés — pas des pannes
                  </div>
                  {subsystems
                    .filter(([, s]) => s.status === "NOT_INSTRUMENTED")
                    .slice(0, 8)
                    .map(([name]) => (
                      <div key={name} className="flex items-center justify-between gap-2 py-1">
                        <span className="num text-[10px] text-hermes-dim truncate">{name}</span>
                        <Badge variant="default">sans télémétrie</Badge>
                      </div>
                    ))}
                </>
              )}
            </div>
          )}
        </div>

        {stats && (
          <div className="clip-corner glass neon-edge bracket p-4">
            <div className="tech-label mb-3">Cumuls</div>
            <dl className="grid grid-cols-2 gap-y-2.5 gap-x-3">
              <Cumul label="Missions" value={stats.missions_total} />
              <Cumul label="Agents" value={stats.agents_total} />
              <Cumul label="Runtimes OK" value={stats.runtimes_healthy} />
              <Cumul label="Mémoire" value={stats.memory_entries} />
            </dl>
          </div>
        )}
      </aside>
    </div>
  );
}

/* ── Parts ─────────────────────────────────────────────────────────── */

function gb(bytes: number): string {
  return (bytes / 1024 ** 3).toFixed(1);
}

function statusFr(status: string): string {
  switch (status) {
    case "HEALTHY": return "sain";
    case "DEGRADED": return "dégradé";
    case "UNHEALTHY": return "en panne";
    case "NOT_INSTRUMENTED": return "sans télémétrie";
    default: return status;
  }
}

function Readout({
  label, value, mono = true, wide = false,
}: { label: string; value: string; mono?: boolean; wide?: boolean }) {
  return (
    <div className={wide ? "max-w-[220px] min-w-0" : ""}>
      <div className="tech-label mb-1.5">{label}</div>
      <div
        className={`text-[13px] text-hermes-text leading-none truncate ${mono ? "num" : ""}`}
        title={value}
      >
        {value}
      </div>
    </div>
  );
}

const bigTone = {
  sodium: { text: "text-hermes-sodium", bar: "var(--hermes-sodium)" },
  steel: { text: "text-hermes-steel", bar: "var(--hermes-steel)" },
  alarm: { text: "text-hermes-alarm", bar: "var(--hermes-alarm)" },
  muted: { text: "text-hermes-muted", bar: "var(--hermes-border-bright)" },
};

function BigReadout({
  label, value, total, icon, tone, index = 0, onOpen, className = "",
}: {
  label: string;
  value: number;
  total?: number;
  icon: React.ReactNode;
  tone: keyof typeof bigTone;
  index?: number;
  onOpen: () => void;
  className?: string;
}) {
  const t = bigTone[tone];
  return (
    <motion.button
      onClick={onOpen}
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 300, damping: 30, delay: index * 0.05 }}
      className={`group relative text-left clip-corner glass neon-edge bracket
        px-4 pt-3.5 pb-4 overflow-hidden transition-transform duration-300
        hover:-translate-y-[2px] ${className}`}
    >
      <span
        className="absolute bottom-0 left-0 h-[2px] w-7 transition-all duration-[550ms]
          ease-out-expo group-hover:w-full"
        style={{ background: `linear-gradient(90deg, ${t.bar}, transparent)` }}
      />
      <div className="flex items-start justify-between gap-2">
        <span className="tech-label">{label}</span>
        <span className={`${t.text} opacity-40 group-hover:opacity-90 transition-opacity`}>
          {icon}
        </span>
      </div>
      <div className="mt-2 flex items-baseline gap-1.5">
        <span className={`display num text-[34px] leading-none ${t.text}`}>{value}</span>
        {typeof total === "number" && (
          <span className="num text-[12px] text-hermes-dim">/ {total}</span>
        )}
      </div>
    </motion.button>
  );
}

function VitalRow({
  icon, label, value, sub, pct,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub: string;
  pct: number | null;
}) {
  return (
    <div className="mb-3.5 last:mb-0">
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <span className="flex items-center gap-1.5 text-hermes-muted">
          {icon}
          <span className="num text-[10px] tracking-[0.1em]">{label}</span>
        </span>
        <span className="num text-[12px] text-hermes-text">{value}</span>
      </div>
      {/* invert: on these meters a high reading is the bad one. */}
      <ProgressBar value={pct ?? 0} size="sm" invert />
      <div className="num text-[9px] text-hermes-dim mt-1">{sub}</div>
    </div>
  );
}

function Cumul({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div>
      <dt className="tech-label !text-[8.5px]">{label}</dt>
      <dd className="num text-[15px] text-hermes-text mt-0.5">
        {typeof value === "number" ? value.toLocaleString("fr-FR") : "––"}
      </dd>
    </div>
  );
}

function GoTo({ onGo }: { onGo: () => void }) {
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onGo();
      }}
      className="group num flex items-center gap-1 px-1.5 py-0.5 clip-corner-sm border
        border-hermes-border text-[9px] uppercase tracking-[0.1em] text-hermes-dim
        hover:text-hermes-sodium hover:border-hermes-sodium/50 transition-all"
    >
      Ouvrir
      <ArrowUpRight size={9} className="transition-transform group-hover:translate-x-[1px] group-hover:-translate-y-[1px]" />
    </button>
  );
}
