"use client";

import { motion } from "framer-motion";
import { useRuntimes, useResourceStatus, useLoadedModels, useUnloadModel } from "@/hooks/use-api";
import { Card, Badge, ProgressBar, Beacon, Button } from "@/components/ui/card";
import { CenterHeader, PanelLoading } from "@/components/center-scaffold";
import type { RuntimeInfo, RuntimeStatus } from "@/types/hermes";
import { Cpu, HardDrive, Thermometer, Layers, Gauge, Brain, Power } from "lucide-react";

/** Le badge acceptait uniquement AVAILABLE/DEGRADED/UNAVAILABLE alors que
 *  l'API renvoie le cycle de vie du runtime (`started`, `stopped`…). Un
 *  statut non listé donnait `undefined` comme variante de badge. */
const statusBadge: Record<RuntimeStatus, "success" | "warning" | "danger" | "default"> = {
  AVAILABLE: "success",
  started: "success",
  DEGRADED: "warning",
  starting: "warning",
  UNAVAILABLE: "danger",
  error: "danger",
  stopped: "default",
};

/** Bytes to GB, one decimal. The endpoint reports bytes; the meters show GB. */
const gib = (n: number | undefined | null) =>
  typeof n === "number" ? (n / 1024 ** 3).toFixed(1) : "—";

export function RuntimeCenter() {
  const { data: runtimes, isLoading, isError, error } = useRuntimes();
  const { data: resources, isError: resErr } = useResourceStatus();
  const { data: loaded, isLoading: loadedLoading, isError: loadedErr } = useLoadedModels();
  const unloadModel = useUnloadModel();

  // Chaque bloc est facultatif : l'endpoint peut très bien rapporter la RAM
  // sans GPU. Lire `resources.ram.usage_pct` sans garde faisait planter tout
  // le Center dès que la requête ressources échouait.
  const ram = resources?.ram;
  const gpu = resources?.gpu;
  const vramPct =
    gpu && gpu.vram_total_bytes > 0
      ? (gpu.vram_used_bytes / gpu.vram_total_bytes) * 100
      : null;

  const active = runtimes?.filter((r) => r.status === "started" || r.status === "AVAILABLE").length ?? 0;

  return (
    <div>
      <CenterHeader
        title="Runtime Center"
        subtitle="Santé des moteurs d'inférence, ressources matérielles et sélection"
        right={
          <Badge variant={active > 0 ? "success" : "default"}>
            {active > 0 && <Beacon tone="green" />}
            {active}/{runtimes?.length ?? 0} actif(s)
          </Badge>
        }
      />

      {/* ── Ressources matérielles ─────────────────────────────────── */}
      <div className="grid grid-cols-4 gap-3 mb-6">
        <ResourceMeter
          label="RAM"
          icon={<Cpu size={14} />}
          value={ram?.usage_pct ?? null}
          unit="%"
          detail={ram ? `${gib(ram.used_bytes)} / ${gib(ram.total_bytes)} GB` : undefined}
        />
        <ResourceMeter
          label="VRAM"
          icon={<HardDrive size={14} />}
          value={vramPct}
          unit="%"
          detail={gpu?.available ? `${gib(gpu.vram_used_bytes)} / ${gib(gpu.vram_total_bytes)} GB` : "Aucun GPU détecté"}
        />
        <ResourceMeter
          label="Température GPU"
          icon={<Thermometer size={14} />}
          value={gpu?.temperature_celsius ?? null}
          unit="°C"
          max={100}
          detail={gpu?.name ?? undefined}
          unavailableLabel="Non exposée par le pilote"
        />
        <ResourceMeter
          label="Allocations"
          icon={<Layers size={14} />}
          value={resources ? (resources.allocations > 0 ? 100 : 0) : null}
          unit=""
          rawValue={resources?.allocations}
          detail={resources ? `${gib(resources.allocated_bytes)} GB réservés` : undefined}
        />
      </div>

      {resErr && (
        <div className="mb-6 flex items-center gap-2 px-3 py-2 rounded-lg glass border border-hermes-red/30">
          <span className="text-hermes-red text-glow-red">⚠</span>
          <span className="text-[11px] text-hermes-muted font-mono">
            Ressources matérielles injoignables — les jauges ci-dessus restent vides.
          </span>
        </div>
      )}

      {/* ── Modèles chargés (HOS-072) — Ollama /api/ps réel, avec une
          vraie action pour décharger un modèle immédiatement plutôt que
          d'attendre son keep_alive. ─────────────────────────────────── */}
      <Card title="Modèle(s) chargé(s)" className="mb-6">
        {loadedLoading ? (
          <PanelLoading />
        ) : loadedErr || !loaded?.success ? (
          <div className="text-[11px] text-hermes-muted font-mono py-2">
            Ollama injoignable — impossible de savoir quels modèles sont chargés.
          </div>
        ) : loaded.models.length === 0 ? (
          <div className="flex items-center gap-2 justify-center py-6">
            <span className="text-hermes-dim font-mono">◇</span>
            <span className="text-[11px] text-hermes-muted font-mono">
              Aucun modèle chargé en VRAM actuellement
            </span>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {loaded.models.map((m) => (
              <div
                key={m.name}
                className="flex items-center justify-between gap-3 rounded-lg bg-hermes-bg-deep/60 border border-hermes-border/50 px-3 py-2"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <Brain size={14} className="text-hermes-cyan/70 shrink-0" />
                  <span className="text-[12px] font-mono text-hermes-text-bright truncate">{m.name}</span>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <span className="text-[10px] font-mono text-hermes-muted">
                    {gib(m.size_vram_bytes)} GB VRAM
                  </span>
                  <Button
                    variant="danger"
                    size="sm"
                    icon={<Power size={11} />}
                    disabled={unloadModel.isPending}
                    onClick={() => unloadModel.mutate(m.name)}
                  >
                    Décharger
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
        {unloadModel.isError && (
          <div className="text-[10px] text-hermes-red font-mono mt-2">
            Échec du déchargement.
          </div>
        )}
      </Card>

      {/* ── Runtimes ───────────────────────────────────────────────── */}
      {isLoading ? (
        <Card title="Runtimes enregistrés"><PanelLoading /></Card>
      ) : isError ? (
        <Card title="Runtimes enregistrés">
          <div className="flex items-start gap-2.5 py-4">
            <span className="text-hermes-red text-glow-red font-mono text-sm">⚠</span>
            <div className="text-[11px] text-hermes-muted font-mono break-all">
              {error instanceof Error ? error.message : "Endpoint injoignable"}
            </div>
          </div>
        </Card>
      ) : !runtimes?.length ? (
        <Card title="Runtimes enregistrés">
          <div className="flex items-center gap-2 justify-center py-10">
            <span className="text-hermes-dim font-mono">◇</span>
            <span className="text-[11px] text-hermes-muted font-mono">
              Aucun runtime enregistré dans le registre
            </span>
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          {runtimes.map((rt, i) => (
            <RuntimeCard key={rt.name} runtime={rt} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Jauge ──────────────────────────────────────────────────────── */

function ResourceMeter({
  label, icon, value, unit, detail, max = 100, rawValue, unavailableLabel,
}: {
  label: string;
  icon: React.ReactNode;
  /** `null` signifie « non mesuré » — affiché comme tel, jamais comme 0. */
  value: number | null;
  unit: string;
  detail?: string;
  max?: number;
  rawValue?: number;
  unavailableLabel?: string;
}) {
  const has = value !== null && Number.isFinite(value);
  const pct = has ? Math.min(100, (value! / max) * 100) : 0;
  const tone = !has
    ? { text: "text-hermes-dim", grad: "from-hermes-border to-hermes-border" }
    : pct > 90
    ? { text: "text-hermes-red", grad: "from-hermes-red to-hermes-magenta" }
    : pct > 70
    ? { text: "text-hermes-amber", grad: "from-hermes-amber to-hermes-red" }
    : { text: "text-hermes-green", grad: "from-hermes-green to-hermes-cyan" };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className="group relative rounded-xl glass neon-edge bracket p-4 overflow-hidden
        transition-all duration-300 hover:-translate-y-0.5 hover:shadow-glow-cyan"
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] text-hermes-muted font-mono uppercase tracking-[0.12em]">
          {label}
        </span>
        <span className={`${tone.text} opacity-60 group-hover:opacity-100 transition-opacity`}>
          {icon}
        </span>
      </div>

      {has ? (
        <div className={`text-2xl font-bold font-mono tabular-nums ${tone.text}`}>
          {rawValue !== undefined ? rawValue : value!.toFixed(unit === "%" ? 1 : 0)}
          {unit && <span className="text-sm text-hermes-muted ml-1">{unit}</span>}
        </div>
      ) : (
        <div className="text-sm font-mono text-hermes-dim py-1.5">
          {unavailableLabel ?? "Non mesuré"}
        </div>
      )}

      <div className="mt-2.5 h-1.5 w-full bg-hermes-bg-deep rounded-full overflow-hidden border border-hermes-border/50">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
          className={`h-full rounded-full bg-gradient-to-r ${tone.grad}`}
        />
      </div>
      {detail && (
        <div className="text-[10px] text-hermes-muted mt-1.5 font-mono truncate">{detail}</div>
      )}
    </motion.div>
  );
}

/* ── Carte runtime ──────────────────────────────────────────────── */

function RuntimeCard({ runtime, index }: { runtime: RuntimeInfo; index: number }) {
  const health = runtime.health;
  const metrics = runtime.metrics;
  const live = runtime.status === "started" || runtime.status === "AVAILABLE";

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.07, ease: [0.16, 1, 0.3, 1] }}
    >
      <Card
        title={runtime.name}
        subtitle={runtime.runtime_name ?? runtime.type}
        accent={live ? "green" : "amber"}
        live={live}
        action={
          <Badge variant={statusBadge[runtime.status] ?? "default"}>
            {live && <Beacon tone="green" />}
            {runtime.status}
          </Badge>
        }
      >
        <div className="flex flex-col gap-3">
          {/* Capacités — ce que le runtime déclare savoir faire. */}
          {runtime.capabilities?.length ? (
            <div className="flex flex-wrap gap-1.5">
              {runtime.capabilities.map((c) => (
                <span
                  key={c}
                  className="px-2 py-0.5 rounded text-[10px] font-mono
                    bg-hermes-cyan/[0.07] text-hermes-cyan border border-hermes-cyan/25"
                >
                  {c}
                </span>
              ))}
            </div>
          ) : null}

          {metrics ? (
            <div className="grid grid-cols-2 gap-2">
              <MetricTile label="Fiabilité" value={metrics.reliability * 100} />
              <MetricTile label="Latence moy." value={metrics.avg_latency_ms} unit="ms" />
            </div>
          ) : (
            <div className="text-[10px] text-hermes-dim font-mono py-1">
              Aucune tâche réelle exécutée sur ce runtime pour l&apos;instant
            </div>
          )}

          <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[10px] font-mono pt-1">
            <Row label="Version" value={runtime.version ?? "—"} />
            <Row
              label="Sain"
              value={runtime.healthy === undefined ? "—" : runtime.healthy ? "oui" : "non"}
              tone={runtime.healthy === false ? "bad" : undefined}
            />
            {runtime.is_active !== undefined && (
              <Row label="Actif" value={runtime.is_active ? "oui" : "non"} />
            )}
            {health?.latency_ms !== undefined && (
              <Row label="Latence" value={`${health.latency_ms} ms`} />
            )}
            {metrics?.total_executions !== undefined && (
              <Row label="Exécutions" value={String(metrics.total_executions)} />
            )}
          </div>
        </div>
      </Card>
    </motion.div>
  );
}

function MetricTile({ label, value, unit = "%" }: { label: string; value: number; unit?: string }) {
  return (
    <div className="rounded-lg bg-hermes-bg-deep/60 border border-hermes-border/50 p-2.5">
      <div className="flex items-center gap-1.5 text-[10px] text-hermes-muted font-mono">
        <Gauge size={10} className="text-hermes-cyan/50" />
        {label}
      </div>
      <div className="text-sm font-bold font-mono text-hermes-text tabular-nums mt-1">
        {value.toFixed(unit === "%" ? 0 : 1)}{unit === "%" ? "%" : ` ${unit}`}
      </div>
      {unit === "%" && <ProgressBar value={value} size="sm" className="mt-1.5" />}
    </div>
  );
}

function Row({
  label, value, tone,
}: { label: string; value: string; tone?: "bad" }) {
  return (
    <>
      <span className="text-hermes-muted">{label}</span>
      <span className={tone === "bad" ? "text-hermes-red" : "text-hermes-text"}>{value}</span>
    </>
  );
}
