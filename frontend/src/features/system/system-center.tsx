"use client";

import { useState } from "react";
import { Card, Badge } from "@/components/ui/card";
import { useSubsystemHealth } from "@/hooks/use-api";
import {
  Activity,
  AlertTriangle,
  CheckCircle,
  Cpu,
  Layers,
  Server,
  Users,
  Database,
  Wrench,
  Shield,
  Workflow,
  Boxes,
  Globe,
} from "lucide-react";
import { CenterHeader } from "@/components/center-scaffold";

// ── Component status types ─────────────────────────────────

interface ComponentHealth {
  component_id: string;
  name: string;
  status: string;
  latency_ms: number;
  error_rate: number;
  message: string;
}

interface SystemHealthReport {
  status: string;
  healthy_score: number;
  total_components: number;
  components: ComponentHealth[];
  warnings: { component: string; message: string; severity: string }[];
  degraded: string[];
  unhealthy: string[];
  checks_passed: number;
  checks_failed: number;
}

// ── Presentation metadata ─────────────────────────────────

// Presentation metadata only. The counts used to be hardcoded here (runtime: 6,
// agents: 5, integrations: 4 …); they are now derived from the live service
// registry, so the panel reflects what actually booted.
const CATEGORY_META = [
  { id: "runtime", label: "Runtime", icon: Cpu, color: "text-hermes-blue", match: ["runtime", "ktransformers", "model_registry", "recovery"] },
  { id: "mission", label: "Mission", icon: Workflow, color: "text-hermes-amber", match: ["mission"] },
  { id: "agent", label: "Agents", icon: Users, color: "text-hermes-green", match: ["agent", "collaboration"] },
  { id: "memory", label: "Memory", icon: Database, color: "text-hermes-purple", match: ["memory"] },
  { id: "tools", label: "Tools", icon: Wrench, color: "text-hermes-pink", match: ["tool", "skill"] },
  { id: "policy", label: "Governance", icon: Shield, color: "text-hermes-amber", match: ["policy", "security"] },
  { id: "workspace", label: "Workspace", icon: Boxes, color: "text-hermes-green", match: ["workspace"] },
  { id: "execution", label: "Execution", icon: Server, color: "text-hermes-red", match: ["execution", "autonomous"] },
  { id: "integrations", label: "Integrations", icon: Globe, color: "text-hermes-cyan", match: ["alexandrie", "klaatcode", "ohmypi"] },
  { id: "system", label: "System", icon: Activity, color: "text-hermes-muted", match: ["event", "system", "evolution", "conversation", "explainability", "model_intelligence"] },
];

const componentStatus = (status: string) => {
  switch (status) {
    case "healthy": return <Badge variant="success"><CheckCircle className="w-3 h-3 mr-1" />Sain</Badge>;
    case "degraded": return <Badge variant="warning"><AlertTriangle className="w-3 h-3 mr-1" />Dégradé</Badge>;
    case "unhealthy": return <Badge variant="danger"><AlertTriangle className="w-3 h-3 mr-1" />Défaillant</Badge>;
    default: return <Badge variant="default"><Activity className="w-3 h-3 mr-1" />Inconnu</Badge>;
  }
};

// ── Component ─────────────────────────────────────────────

/** `imbrique` supprime l'en-tete : ce Center est alors rendu sous
 *  celui du System Center, qui porte deja titre et onglets (HOS-177). */
export function SystemCenter({ imbrique = false }: { imbrique?: boolean }) {
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);

  // Real subsystem health from /api/v1/system/health. Every number below used to
  // be a constant in this file — healthy_score 91.7, total_components 25,
  // checks_passed 23, plus two invented warnings and a fabricated degraded
  // component — while the composition root reported real values (RC3 P1).
  const { data: live, isLoading, isError, error } = useSubsystemHealth();

  const detail = live?.detail ?? {};
  const keys = Object.keys(detail);
  const healthyCount = live?.by_status?.healthy ?? 0;
  const silent = live?.silent ?? [];
  const unhealthy = live?.unhealthy ?? [];

  const health: SystemHealthReport = {
    status: live?.status ?? "unknown",
    // Measured: the share of subsystems reporting healthy telemetry.
    healthy_score: keys.length ? Math.round((healthyCount / keys.length) * 1000) / 10 : 0,
    total_components: live?.services ?? 0,
    components: [],
    // "silent" means the subsystem exposes no telemetry accessor — an absence of
    // reporting, not a fault. Reported as info rather than dressed up as one.
    warnings: silent.map((component) => ({
      component,
      message: "n'expose aucun accesseur de télémétrie",
      severity: "info",
    })),
    degraded: [],
    unhealthy,
    checks_passed: healthyCount,
    checks_failed: unhealthy.length,
  };

  const categories = CATEGORY_META.map((meta) => ({
    ...meta,
    count: keys.filter((k) => meta.match.some((m) => k.includes(m))).length,
  }));

  if (isLoading) {
    return (
      <div className="animate-fade-in p-6 text-xs text-hermes-muted">
        Chargement de la santé des sous-systèmes…
      </div>
    );
  }
  if (isError) {
    return (
      <div className="animate-fade-in p-6">
        <Card title="System" className="p-4 border-hermes-red/40">
          <div className="flex items-center gap-2 text-hermes-red text-sm">
            <AlertTriangle size={16} />
            <span>Impossible de joindre la racine de composition</span>
          </div>
          <p className="mt-2 text-[11px] text-hermes-muted">
            {error instanceof Error ? error.message : "erreur inconnue"}
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div className="animate-fade-in p-6">
      {/* Header */}
      {!imbrique && (
        <CenterHeader
          title="System"
          subtitle={`Supervision de l'intégration globale — ${health.total_components} composants enregistrés`}
          right={
            health.status === "healthy" ? (
              <Badge variant="success">
                <CheckCircle className="w-3 h-3" />
                Système sain
              </Badge>
            ) : health.status === "degraded" ? (
              <Badge variant="warning">
                <AlertTriangle className="w-3 h-3" />
                Dégradé
              </Badge>
            ) : (
              <Badge variant="danger">
                <AlertTriangle className="w-3 h-3" />
                Défaillant
              </Badge>
            )
          }
        />
      )}

      {/* Health Overview */}
      <div className="grid grid-cols-4 gap-3 mb-6">
        {[
          { label: "Score de santé", value: `${health.healthy_score}%`, desc: `${health.checks_passed}/${health.total_components}`, color: "text-hermes-green" },
          { label: "Composants", value: health.total_components, desc: `${CATEGORY_META.length} catégories`, color: "text-hermes-blue" },
          { label: "Avertissements", value: health.warnings.length, desc: health.degraded.length > 0 ? `${health.degraded.length} dégradé(s)` : "Aucun", color: health.warnings.length > 0 ? "text-hermes-amber" : "text-hermes-muted" },
          { label: "% Sains", value: `${Math.round(health.checks_passed / Math.max(health.total_components, 1) * 100)}%`, desc: "Opérationnel", color: "text-hermes-green" },
        ].map((stat) => (
          <div key={stat.label} className="bg-hermes-card border border-hermes-border rounded-lg p-3">
            <div className="text-[10px] text-hermes-muted font-mono uppercase">{stat.label}</div>
            <div className={`text-xl font-bold font-mono ${stat.color} mt-1`}>{stat.value}</div>
            <div className="text-[10px] text-hermes-muted mt-0.5">{stat.desc}</div>
          </div>
        ))}
      </div>

      {/* Categories Grid */}
      <Card title="Catégories de composants" className="mb-6">
        <div className="grid grid-cols-5 gap-3">
          {categories.map((cat) => (
            <button
              key={cat.id}
              onClick={() => setSelectedCategory(selectedCategory === cat.id ? null : cat.id)}
              className={`p-4 rounded-lg border text-center transition-all ${
                selectedCategory === cat.id
                  ? "border-hermes-amber/50 bg-hermes-amber/5"
                  : "border-hermes-border hover:border-hermes-border/70 bg-hermes-card/50"
              }`}
            >
              <cat.icon className={`w-5 h-5 mx-auto mb-1.5 ${cat.color}`} />
              <div className="text-xs font-mono text-hermes-text">{cat.label}</div>
              <div className="text-[9px] text-hermes-muted mt-0.5">{cat.count} composant(s)</div>
            </button>
          ))}
        </div>
      </Card>

      {/* System Dependencies */}
      <Card title="Graphe de dépendances" className="mb-6">
        <div className="grid grid-cols-2 gap-4">
          <div>
            {/* Description d'architecture, pas une mesure : cet ordre ne
                change pas a l'execution et ne pretend rien observer. Il est
                conserve a ce titre — mais il nommait `Policy Engine`, retire
                en G-38, et une description perimee se lit comme une mesure
                fausse. */}
            <div className="text-xs text-hermes-muted font-mono mb-2">
              Ordre topologique <span className="text-hermes-dim">(description, non mesuré)</span>
            </div>
            {[
              { id: "core", label: "Core (Event Hub, Integration)", level: 0 },
              { id: "runtime", label: "Runtime (EventBus, Resource, Orchestrator)", level: 1 },
              { id: "memory", label: "Memory (Unified, Knowledge Graph)", level: 1 },
              { id: "security", label: "Aegis (sécurité, approbations)", level: 1 },
              { id: "workspace", label: "Workspace Manager", level: 2 },
              { id: "mission", label: "Mission (Graph, Planner)", level: 2 },
              { id: "agents", label: "Agent (Supervisor, Collaboration)", level: 2 },
              { id: "execution", label: "Execution Engine", level: 3 },
              { id: "integrations", label: "Integrations (KTC, Alex, KC, OMP, CI)", level: 2 },
              { id: "tools", label: "MCP Tools Platform", level: 3 },
              { id: "skills", label: "Skill Distribution", level: 3 },
            ].map((item) => (
              <div key={item.id} className="flex items-center gap-2 py-1" style={{ paddingLeft: `${item.level * 16}px` }}>
                <div className={`w-1.5 h-1.5 rounded-full ${item.level === 0 ? "bg-hermes-amber" : item.level === 1 ? "bg-hermes-blue" : item.level === 2 ? "bg-hermes-green" : "bg-hermes-purple"}`} />
                <span className="text-[10px] font-mono text-hermes-text">{item.label}</span>
              </div>
            ))}
          </div>
          <div>
            <div className="text-xs text-hermes-muted font-mono mb-2">Avertissements et problèmes</div>
            {health.warnings.length === 0 ? (
              <div className="text-xs text-hermes-muted">Aucun avertissement actif</div>
            ) : (
              health.warnings.map((w, i) => (
                <div key={i} className="flex items-start gap-2 p-2 mb-1 bg-hermes-amber/5 border border-hermes-amber/20 rounded-lg">
                  <AlertTriangle className="w-3 h-3 text-hermes-amber mt-0.5 shrink-0" />
                  <div>
                    <div className="text-[10px] font-mono text-hermes-text">{w.component}</div>
                    <div className="text-[9px] text-hermes-muted">{w.message}</div>
                  </div>
                </div>
              ))
            )}
            {/* G-40 : trois lignes affirmaient ici « aucune dépendance
                cyclique détectée », « 25 composants dans l'ordre
                topologique » et « 42 arêtes de dépendance suivies ».
                `/system/health` rend `status`, `services`, `by_status`,
                `unhealthy`, `silent` et `detail` — ni arête, ni ordre, ni
                détection de cycle. Les deux compteurs n'avaient aucune
                source (la liste ci-contre en montrait onze, pas 25) et la
                troisième ligne affirmait une capacité qui n'existe pas :
                rien n'analyse le graphe de dépendances. */}
            <div className="text-xs text-hermes-muted font-mono mt-3 mb-1">Statistiques de dépendances</div>
            <div className="space-y-1 text-[10px] text-hermes-muted">
              <div className="font-mono">
                {keys.length} sous-système(s) enregistré(s) dans la racine de composition
              </div>
              <div className="text-hermes-dim">
                Aucune analyse du graphe de dépendances n&apos;est exposée :
                le graphe existe à la construction, mais aucune route n&apos;en
                publie les arêtes ni ne signale les cycles.
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* Component List */}
      <Card title="Tous les composants" className="mb-6">
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="text-[10px] text-hermes-muted font-mono uppercase border-b border-hermes-border">
                {/* Trois colonnes, parce que la charge utile en porte trois.
                    « Catégorie » et « Latence » ont disparu avec les douze
                    lignes inventées : `/system/health` ne rend ni l'une ni
                    l'autre par sous-système. Un en-tête sans cellule décale
                    tout ce qui suit. */}
                <th className="pb-2 pr-4">Sous-système</th>
                <th className="pb-2 pr-4">Statut</th>
                <th className="pb-2 pr-4">Raison</th>
              </tr>
            </thead>
            <tbody>
              {/* G-40 : douze lignes etaient ecrites ici en dur, avec des
                  latences (« 1.5 ms »), des compteurs d'evenements et des
                  etats « healthy » — tous inventes, et l'une d'elles
                  nommait `policy.engine`, retire depuis. Le meme fichier
                  porte pourtant un commentaire disant qu'une passe
                  anterieure avait derive les compteurs du registre vivant :
                  elle avait corrige les CONSTANTES NOMMEES et laisse le
                  tableau inline.

                  `/system/health` rend `detail` — chaque sous-systeme, son
                  etat et la raison quand il est inconnu. Il ne rend NI
                  latence NI compteur par sous-systeme : ces deux colonnes
                  n'avaient aucune source, et elles ne sont plus la. */}
              {Object.entries(live?.detail ?? {}).map(([id, d]) => (
                <tr key={id} className="border-b border-hermes-border/30 hover:bg-hermes-card/30">
                  <td className="py-2 pr-4">
                    <span className="text-xs font-mono text-hermes-text">{id}</span>
                  </td>
                  <td className="py-2 pr-4">{componentStatus(d.status)}</td>
                  <td className="py-2 pr-4">
                    <span className="text-[10px] text-hermes-muted">
                      {d.detail ?? "\u2014"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Architecture Diagram Placeholder — description des couches, pas une
          mesure. Conservee a ce titre (G-40) : elle ne pretend observer
          aucun etat, et son titre le dit. */}
      <Card title="Architecture système (description)">
        <div className="grid grid-cols-3 gap-3 text-center">
          {[
            { layer: "Core", items: "Event Hub · Integration · Config", color: "bg-hermes-amber/10 border-hermes-amber/30 text-hermes-amber" },
            { layer: "Runtime", items: "EventBus · Resource · Orchestrator · Simulation · Discovery · KTC", color: "bg-hermes-blue/10 border-hermes-blue/30 text-hermes-blue" },
            { layer: "Mission", items: "Graph · Planner · Execution", color: "bg-hermes-green/10 border-hermes-green/30 text-hermes-green" },
            { layer: "Agents", items: "Supervisor · Collaboration · KC · OMP · CI", color: "bg-hermes-purple/10 border-hermes-purple/30 text-hermes-purple" },
            { layer: "Memory", items: "Unified Memory · Knowledge Graph", color: "bg-hermes-pink/10 border-hermes-pink/30 text-hermes-pink" },
            { layer: "Tools & Gouvernance", items: "MCP · Skills · Aegis · Workspace", color: "bg-hermes-amber/10 border-hermes-amber/30 text-hermes-amber" },
          ].map((item) => (
            <div key={item.layer} className={`p-3 rounded-lg border ${item.color}`}>
              <div className="text-xs font-mono font-bold">{item.layer}</div>
              <div className="text-[9px] font-mono mt-1 opacity-70">{item.items}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
