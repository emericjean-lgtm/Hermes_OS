"use client";

import React, { useState } from "react";
import {
  useResourceStatus,
  useSubsystemAssembly,
  useSubsystemHealth,
  useSubsystemStatistics,
} from "@/hooks/use-api";
import { CenterHeader } from "@/components/center-scaffold";
import { Badge } from "@/components/ui/card";
import { formatGio } from "@/lib/format";

// This Center was fabricated end to end, and dangerously so: it reported an
// "NVIDIA A100 80GB" with 81920 MB VRAM, an "AMD EPYC (8C/16T)" CPU and
// "Linux 6.2.0" on whatever machine it was opened on, twelve invented healthy
// components with invented latencies, six invented services (PostgreSQL, Redis,
// ChromaDB) that need not exist, and three invented backup files. "Create
// backup" slept 1500 ms, appended an entry sized `Math.random() * 20 + 30` and
// announced "Backup created successfully" for an operation that never happened.
//
// Everything below now comes from /api/v1/system/health, /system/assembly,
// /system/statistics and /runtime/resources. Hermes exposes no backup API, so
// that tab says so instead of pretending (R-002 P3/P5).

const TABS = ["overview", "profile", "services", "backups", "health"] as const;

const TAB_LABELS: Record<(typeof TABS)[number], string> = {
  overview: "Vue d'ensemble",
  profile: "Profil",
  services: "Services",
  backups: "Sauvegardes",
  health: "Santé",
};

function ProfileCard({
  title,
  value,
  icon,
}: {
  title: string;
  value: string | boolean;
  icon: string;
}) {
  return (
    <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-4 hover:border-hermes-cyan/40 transition-all">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-lg">{icon}</span>
        <span className="text-hermes-muted text-xs uppercase tracking-wider">{title}</span>
      </div>
      <div className="text-hermes-text-bright font-mono text-sm">
        {typeof value === "boolean" ? (
          <span className={value ? "text-hermes-green" : "text-hermes-red"}>
            {value ? "✓ Disponible" : "✗ Non disponible"}
          </span>
        ) : (
          value
        )}
      </div>
    </div>
  );
}

const dotColour = (status: string | undefined) =>
  status === "healthy"
    ? "bg-hermes-green"
    : status === "degraded"
      ? "bg-hermes-amber"
      : status === "unknown"
        ? "bg-hermes-dim"
        : "bg-hermes-red";

/** `imbrique` supprime l'en-tete : ce Center est alors rendu sous
 *  celui du Runtime Center, qui porte deja titre et onglets (HOS-177). */
export default function DeploymentCenter({ imbrique = false }: { imbrique?: boolean }) {
  const [activeTab, setActiveTab] = useState<(typeof TABS)[number]>("overview");

  const health = useSubsystemHealth();
  const assembly = useSubsystemAssembly();
  const statistics = useSubsystemStatistics();
  const resources = useResourceStatus();

  const detail = health.data?.detail ?? {};
  const byStatus = health.data?.by_status ?? {};
  const silent = health.data?.silent ?? [];
  const unhealthy = health.data?.unhealthy ?? [];
  const bootstrap = (assembly.data?.bootstrap ?? {}) as Record<string, unknown>;
  const built = (bootstrap.built as string[] | undefined) ?? [];
  const registries = (bootstrap.registries ?? {}) as Record<string, unknown>;
  const services = (statistics.data?.services ?? {}) as Record<string, unknown>;

  const gpu = resources.data?.gpu;
  const ram = resources.data?.ram;

  return (
    <div className="space-y-6">
      {!imbrique && (
        <CenterHeader
          title="Deployment Center"
          subtitle="État de préparation à la production et gestion du système"
          right={
            health.isLoading ? (
              <span className="text-hermes-muted text-[11px] font-mono">vérification…</span>
            ) : health.isError ? (
              <Badge variant="danger">injoignable</Badge>
            ) : (
              <Badge
                variant={
                  health.data?.status === "healthy" ? "success"
                  : health.data?.status === "degraded" ? "warning"
                  : "danger"
                }
              >
                <span className={`w-1.5 h-1.5 rounded-full ${dotColour(health.data?.status)}`} />
                {health.data?.status}
              </Badge>
            )
          }
        />
      )}

      {/* Tab Nav */}
      <div className="flex gap-1 bg-hermes-elevated/50 rounded-lg p-1">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
              activeTab === tab
                ? "bg-hermes-cyan/20 text-hermes-cyan"
                : "text-hermes-muted hover:text-hermes-text"
            }`}
          >
            {TAB_LABELS[tab]}
          </button>
        ))}
      </div>

      {/* Overview */}
      {activeTab === "overview" && (
        <div className="space-y-4">
          <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-5">
            <h2 className="text-lg font-semibold text-hermes-text-bright mb-4">Vue d&apos;ensemble système</h2>
            {health.isError ? (
              <div className="text-hermes-red text-sm">
                /api/v1/system/health est injoignable.
              </div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <div className="text-hermes-muted text-xs uppercase">Sous-systèmes</div>
                  <div className="text-3xl font-bold text-hermes-text-bright">
                    {health.data?.services ?? "—"}
                  </div>
                </div>
                <div>
                  <div className="text-hermes-muted text-xs uppercase">Sains</div>
                  <div className="text-3xl font-bold text-hermes-green">
                    {byStatus.healthy ?? 0}
                  </div>
                </div>
                <div>
                  <div className="text-hermes-muted text-xs uppercase">Sans mesure</div>
                  <div className="text-3xl font-bold text-hermes-muted">{silent.length}</div>
                </div>
                <div>
                  <div className="text-hermes-muted text-xs uppercase">Défaillants</div>
                  <div className="text-3xl font-bold text-hermes-red">
                    {unhealthy.length}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Registries — the numbers the composition root actually seeded */}
          <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-5">
            <h3 className="text-hermes-text-bright font-semibold mb-3">Registres</h3>
            {assembly.isLoading ? (
              <div className="text-hermes-muted text-sm">Chargement de l&apos;assemblage…</div>
            ) : Object.keys(registries).length === 0 ? (
              <div className="text-hermes-muted text-sm">
                Le bootstrap n&apos;a rapporté aucun compte de registre.
              </div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                {(["agents", "tools", "mcp_servers", "runtimes", "skills"] as const).map(
                  (key) => (
                    <div key={key} className="bg-hermes-bg-deep/50 rounded-lg p-3">
                      <div className="text-hermes-muted text-xs uppercase">
                        {key.replace(/_/g, " ")}
                      </div>
                      <div className="text-xl font-bold text-hermes-cyan font-mono">
                        {String(registries[key] ?? "—")}
                      </div>
                    </div>
                  ),
                )}
              </div>
            )}
          </div>

          <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-5">
            <h3 className="text-hermes-text-bright font-semibold mb-3">Santé des composants</h3>
            {Object.keys(detail).length === 0 ? (
              <div className="text-hermes-muted text-sm">Aucun détail de composant rapporté.</div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {Object.entries(detail).map(([name, info]) => (
                  <div
                    key={name}
                    className="flex items-center justify-between bg-hermes-bg-deep/50 rounded-lg px-3 py-2"
                  >
                    <div className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${dotColour(info.status)}`} />
                      <span className="text-hermes-text text-sm font-mono">{name}</span>
                    </div>
                    <span className="text-hermes-muted text-xs">
                      {info.detail || info.status}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Profile — real host resources */}
      {activeTab === "profile" && (
        <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-5">
          <h2 className="text-lg font-semibold text-hermes-text-bright mb-4">Profil système</h2>
          {resources.isLoading && (
            <div className="text-hermes-muted text-sm">Lecture des ressources hôte…</div>
          )}
          {resources.isError && (
            <div className="text-hermes-red text-sm">
              /api/v1/runtime/resources est injoignable.
            </div>
          )}
          {resources.data && (
            <>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <ProfileCard
                  title="RAM totale"
                  value={ram ? `${formatGio(ram.total_bytes)} Gio` : "—"}
                  icon="🧠"
                />
                <ProfileCard
                  title="RAM utilisée"
                  value={ram ? `${formatGio(ram.used_bytes)} Gio (${ram.usage_pct}%)` : "—"}
                  icon="📊"
                />
                <ProfileCard title="État RAM" value={ram?.status ?? "—"} icon="✅" />
                <ProfileCard title="GPU" value={gpu?.name ?? "—"} icon="🎮" />
                <ProfileCard title="Fabricant GPU" value={gpu?.vendor ?? "—"} icon="🏷" />
                <ProfileCard title="GPU détecté" value={Boolean(gpu?.available)} icon="🔧" />
                <ProfileCard
                  title="VRAM totale"
                  value={gpu ? `${formatGio(gpu.vram_total_bytes)} Gio` : "—"}
                  icon="💾"
                />
                <ProfileCard
                  title="VRAM libre"
                  value={gpu ? `${formatGio(gpu.vram_free_bytes)} Gio` : "—"}
                  icon="💽"
                />
                <ProfileCard
                  title="Allocations"
                  value={String(resources.data.allocations ?? 0)}
                  icon="📦"
                />
              </div>
              <p className="text-hermes-dim text-xs mt-4">
                Rapporté par le gestionnaire de ressources. Les champs qu&apos;il ne peut
                pas détecter affichent &quot;unknown&quot; plutôt que d&apos;être inventés.
              </p>
            </>
          )}
        </div>
      )}

      {/* Services — the subsystems that actually built */}
      {activeTab === "services" && (
        <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-5">
          <h2 className="text-lg font-semibold text-hermes-text-bright mb-4">
            Services {built.length > 0 && `(${built.length})`}
          </h2>
          {assembly.isLoading && (
            <div className="text-hermes-muted text-sm">Chargement de l&apos;assemblage…</div>
          )}
          {assembly.isError && (
            <div className="text-hermes-red text-sm">
              /api/v1/system/assembly est injoignable.
            </div>
          )}
          {built.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-hermes-border">
                    <th className="text-left py-2 px-3 text-hermes-muted font-medium">Service</th>
                    <th className="text-left py-2 px-3 text-hermes-muted font-medium">Santé</th>
                    <th className="text-left py-2 px-3 text-hermes-muted font-medium">Détail</th>
                    <th className="text-right py-2 px-3 text-hermes-muted font-medium">Stats</th>
                  </tr>
                </thead>
                <tbody>
                  {built.map((name) => (
                    <tr key={name} className="border-b border-hermes-border/50 hover:bg-hermes-elevated/20">
                      <td className="py-2 px-3 text-hermes-text-bright font-mono">{name}</td>
                      <td className="py-2 px-3">
                        <div className="flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${dotColour(detail[name]?.status)}`} />
                          <span className="text-hermes-muted">
                            {detail[name]?.status ?? "inconnu"}
                          </span>
                        </div>
                      </td>
                      <td className="py-2 px-3 text-hermes-muted text-xs">
                        {detail[name]?.detail ?? ""}
                      </td>
                      <td className="py-2 px-3 text-right text-hermes-muted text-xs">
                        {services[name] ? "mesuré" : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Backups — no such API exists */}
      {activeTab === "backups" && (
        <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-5">
          <h2 className="text-lg font-semibold text-hermes-text-bright mb-4">Sauvegardes</h2>
          <div className="text-hermes-muted text-sm">
            Hermes n&apos;expose aucune API de sauvegarde. Cet onglet listait
            auparavant trois archives inventées, et son bouton « Créer une
            sauvegarde » annonçait un succès sans rien exécuter — il rapporte
            désormais l&apos;état réel à la place.
          </div>
        </div>
      )}

      {/* Health detail */}
      {activeTab === "health" && (
        <div className="bg-hermes-elevated/60 border border-hermes-border rounded-lg p-5">
          <h2 className="text-lg font-semibold text-hermes-text-bright mb-4">Détails de santé</h2>
          {health.isLoading && <div className="text-hermes-muted text-sm">Chargement…</div>}
          {health.isError && (
            <div className="text-hermes-red text-sm">
              /api/v1/system/health est injoignable.
            </div>
          )}
          {Object.keys(detail).length > 0 && (
            <div className="space-y-2">
              {Object.entries(detail).map(([name, info]) => (
                <div
                  key={name}
                  className="flex items-start justify-between bg-hermes-bg-deep/50 rounded-lg px-3 py-2"
                >
                  <div className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${dotColour(info.status)}`} />
                    <span className="text-hermes-text text-sm font-mono">{name}</span>
                  </div>
                  <div className="text-right">
                    <div className="text-hermes-muted text-xs capitalize">{info.status}</div>
                    {info.detail && (
                      <div className="text-hermes-dim text-[11px]">{info.detail}</div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
          {silent.length > 0 && (
            <p className="text-hermes-dim text-xs mt-4">
              {silent.length} sous-système(s) n&apos;expose(nt) aucun accesseur de
              statistiques, leur santé ne peut donc pas être mesurée. Ils sont
              rapportés comme &quot;unknown&quot; plutôt que présumés sains.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
