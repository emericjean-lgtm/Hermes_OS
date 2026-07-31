"use client";

import { Card, Badge } from "@/components/ui/card";
import {
  useKlaatCodeCapabilities,
  useKlaatCodeStatus,
  useOhMyPiCapabilities,
  useOhMyPiStatus,
} from "@/hooks/use-api";
import { Brain, AlertTriangle, Activity } from "lucide-react";

// This Center used to render a fabricated agent — MOCK_STATUS claimed 142 tasks
// at a 92.3% success rate across a 68/53/21 KlaatCode/OhMyPi/hybrid split — and
// MOCK_TASK_TYPES supplied ten hand-written routing tables. Clicking a task ran
// a client-side "// Simulate routing" block that assembled a decision object
// from those constants and cleared a spinner after 800 ms. No request was ever
// made, and none could be: Hermes exposes no /api/v1/code-intelligence routes
// and builds no code_intelligence service.
//
// Adding that backend would be a new engine, which R-002 forbids. So this
// Center now shows only what genuinely exists — the two providers it would
// route between, live from their own endpoints — and states the gap plainly
// rather than inventing numbers to fill it (R-002 P3/P5).

export function CodeIntelligenceCenter() {
  const kcStatus = useKlaatCodeStatus();
  const kcCaps = useKlaatCodeCapabilities();
  const ompStatus = useOhMyPiStatus();
  const ompCaps = useOhMyPiCapabilities();

  const kc = kcStatus.data?.status;
  const omp = ompStatus.data?.status;

  const providers = [
    {
      key: "klaatcode",
      label: "KlaatCode",
      installed: Boolean(kc?.installed),
      version: kc?.version ?? null,
      tools: kcCaps.data?.count ?? kc?.tools_count ?? 0,
      bound: Boolean(kc?.server_bound),
      stats: kc?.client_stats,
      loading: kcStatus.isLoading,
      error: kcStatus.isError,
    },
    {
      key: "ohmypi",
      label: "Oh My Pi",
      installed: Boolean(omp?.installed),
      version: omp?.version ?? null,
      tools: ompCaps.data?.count ?? omp?.tools_count ?? 0,
      bound: Boolean(omp?.server_bound),
      stats: omp?.client_stats,
      loading: ompStatus.isLoading,
      error: ompStatus.isError,
    },
  ];

  return (
    <div className="animate-fade-in p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-hermes-text font-mono">
            Code Intelligence
          </h2>
          <p className="text-xs text-hermes-muted mt-1">
            Meta-agent routing between KlaatCode and Oh My Pi — HOS-055
          </p>
        </div>
        <Badge variant="warning">
          <Brain className="w-3 h-3 mr-1" />
          Router not exposed
        </Badge>
      </div>

      {/* The honest statement of what is missing */}
      <Card title="Routing backend" className="mb-6">
        <div className="flex items-start gap-3">
          <AlertTriangle className="w-4 h-4 text-hermes-amber mt-0.5 shrink-0" />
          <div className="text-xs text-hermes-text leading-relaxed">
            Hermes exposes no <span className="font-mono">/api/v1/code-intelligence</span>{" "}
            endpoints and builds no <span className="font-mono">code_intelligence</span>{" "}
            service, so there is no routing decision to display. This panel
            previously showed a simulated one computed in the browser. The two
            providers below are real and their figures come from their own
            endpoints.
          </div>
        </div>
      </Card>

      {/* Providers — live */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        {providers.map((p) => (
          <Card key={p.key} title={p.label}>
            {p.loading ? (
              <div className="text-xs text-hermes-muted font-mono py-2">
                Checking {p.label}…
              </div>
            ) : p.error ? (
              <div className="text-xs text-hermes-red font-mono py-2">
                /{p.key}/status unreachable
              </div>
            ) : (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-hermes-muted font-mono">Installed</span>
                  <Badge variant={p.installed ? "success" : "warning"}>
                    {p.installed ? "yes" : "no"}
                  </Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-hermes-muted font-mono">MCP bound</span>
                  <Badge variant={p.bound ? "success" : "default"}>
                    {p.bound ? "bound" : "unbound"}
                  </Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-hermes-muted font-mono">Version</span>
                  <span className="text-[10px] font-mono text-hermes-text">
                    {p.version || "—"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-hermes-muted font-mono">Tools</span>
                  <span className="text-[10px] font-mono text-hermes-text">{p.tools}</span>
                </div>
                {p.stats && (
                  <div className="pt-2 mt-1 border-t border-hermes-border/30 grid grid-cols-3 gap-2">
                    <div>
                      <div className="text-[9px] text-hermes-muted font-mono uppercase">Runs</div>
                      <div className="text-sm font-mono text-hermes-text">
                        {p.stats.total_executions}
                      </div>
                    </div>
                    <div>
                      <div className="text-[9px] text-hermes-muted font-mono uppercase">Success</div>
                      <div className="text-sm font-mono text-hermes-green">
                        {p.stats.success_rate.toFixed(0)}%
                      </div>
                    </div>
                    <div>
                      <div className="text-[9px] text-hermes-muted font-mono uppercase">Avg ms</div>
                      <div className="text-sm font-mono text-hermes-text">
                        {p.stats.avg_duration_ms.toFixed(0)}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </Card>
        ))}
      </div>

      {/* Capabilities actually reported by each provider */}
      <div className="grid grid-cols-2 gap-4">
        <Card title={`KlaatCode capabilities (${kcCaps.data?.count ?? 0})`}>
          {kcCaps.isLoading && (
            <div className="text-xs text-hermes-muted font-mono">Loading…</div>
          )}
          {kcCaps.isError && (
            <div className="text-xs text-hermes-red font-mono">
              /klaatcode/capabilities unreachable
            </div>
          )}
          <div className="flex flex-wrap gap-1">
            {kcCaps.data?.capabilities.map((c) => (
              <span
                key={c.name}
                className="text-[9px] font-mono px-1.5 py-0.5 bg-hermes-bg rounded border border-hermes-border/50 text-hermes-text"
              >
                {c.name}
              </span>
            ))}
          </div>
        </Card>

        <Card title={`Oh My Pi capabilities (${ompCaps.data?.count ?? 0})`}>
          {ompCaps.isLoading && (
            <div className="text-xs text-hermes-muted font-mono">Loading…</div>
          )}
          {ompCaps.isError && (
            <div className="text-xs text-hermes-red font-mono">
              /ohmypi/capabilities unreachable
            </div>
          )}
          <div className="flex flex-wrap gap-1">
            {ompCaps.data?.capabilities.map((c) => (
              <span
                key={c.name}
                className="text-[9px] font-mono px-1.5 py-0.5 bg-hermes-bg rounded border border-hermes-border/50 text-hermes-text"
              >
                {c.name}
              </span>
            ))}
          </div>
        </Card>
      </div>

      <div className="flex items-center gap-2 mt-4 text-[10px] text-hermes-muted font-mono">
        <Activity className="w-3 h-3" />
        Provider figures refresh every 15 s from the live agents.
      </div>
    </div>
  );
}
