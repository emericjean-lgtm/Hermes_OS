"use client";

import { useTools, useToolsHealth, useMCPServers, useExecuteTool } from "@/hooks/use-api";
import { Card, Badge } from "@/components/ui/card";
import type { ToolDefinition, MCPServer, ToolHealth } from "@/types/hermes";
import { CenterHeader } from "@/components/center-scaffold";

export function ToolsCenter() {
  const { data: tools } = useTools();
  const { data: toolHealth } = useToolsHealth();
  const { data: mcpServers } = useMCPServers();
  const executeTool = useExecuteTool();

  // /tools/health reports fleet totals, not per-tool rows. This used to
  // build a Map by calling .map() on that object, which throws (R-003).
  const healthMap = new Map<string, ToolHealth>();

  return (
    <div className="animate-fade-in">
      <CenterHeader
        title="Tools Center"
        subtitle="Plateforme MCP et gouvernance des outils externes"
      />

      <div className="grid grid-cols-2 gap-4 mb-6">
        {/* Native tools */}
        <Card title="Outils natifs" subtitle={`${tools?.length || 0} enregistré(s)`}>
          <div className="flex flex-col gap-2 max-h-[300px] overflow-y-auto">
            {tools?.map((tool) => {
              const h = healthMap.get(tool.id);
              return <ToolCard key={tool.id} tool={tool} health={h} />;
            })}
          </div>
        </Card>

        {/* MCP Servers */}
        <Card title="Serveurs MCP" subtitle={`${mcpServers?.length || 0} connecté(s)`}>
          <div className="flex flex-col gap-2 max-h-[300px] overflow-y-auto">
            {mcpServers?.map((srv) => (
              <MCPServerCard key={srv.id} server={srv} />
            ))}
            {mcpServers?.length === 0 && (
              <p className="text-xs text-hermes-muted py-8 text-center">Aucun serveur MCP connecté</p>
            )}
          </div>
        </Card>
      </div>

      {/* Tool Health Overview.
          /api/v1/tools/health reports fleet totals — it has never returned a
          per-tool row. This block used to slice and map over it as if it were a
          list of tools, which throws on an object; it showed nothing only
          because the Cockpit could not reach the backend at all (R-003). */}
      {toolHealth && (
        <Card title="Aperçu de la santé">
          <div className="grid grid-cols-4 gap-3">
            {[
              { label: "Outils", value: toolHealth.total },
              { label: "Sains", value: toolHealth.healthy },
              { label: "Dégradés", value: toolHealth.degraded_or_unhealthy },
              { label: "Latence moy.", value: `${toolHealth.avg_latency_ms.toFixed(0)}ms` },
            ].map((s) => (
              <div key={s.label} className="bg-hermes-bg rounded-lg p-3 text-center">
                <div className="text-[10px] text-hermes-muted font-mono uppercase mb-1">
                  {s.label}
                </div>
                <div className="text-sm font-bold text-hermes-text font-mono">
                  {s.value}
                </div>
              </div>
            ))}
          </div>
          <p className="text-[10px] text-hermes-muted font-mono mt-2">
            La santé par outil n&apos;est pas exposée par ce endpoint.
          </p>
        </Card>
      )}
    </div>
  );
}

function ToolCard({ tool, health }: { tool: ToolDefinition; health?: ToolHealth }) {
  const typeColors: Record<string, string> = {
    GITHUB: "text-hermes-violet",
    GITLAB: "text-hermes-amber",
    DOCKER: "text-hermes-blue",
    DATABASE: "text-hermes-green",
    FILESYSTEM: "text-hermes-amber",
    REST_API: "text-hermes-cyan",
    BROWSER: "text-hermes-magenta",
    MCP: "text-hermes-amber",
  };

  return (
    <div className="bg-hermes-bg rounded-lg p-3 border border-hermes-border/50 hover:border-hermes-border transition-colors">
      <div className="flex items-center justify-between mb-1">
        <span className={`text-sm font-medium font-mono ${typeColors[tool.type] || "text-hermes-text"}`}>
          {tool.name}
        </span>
        <Badge variant={tool.status === "AVAILABLE" ? "success" : tool.status === "ERROR" ? "danger" : "default"}>
          {tool.status}
        </Badge>
      </div>
      <div className="text-[10px] text-hermes-muted mb-1">{tool.type}</div>
      {health && (
        <div className="flex items-center gap-3 text-[10px] font-mono">
          <span className="text-hermes-muted">{health.latency_ms}ms</span>
          <span className="text-hermes-muted">{(health.success_rate * 100).toFixed(0)}%</span>
        </div>
      )}
      {tool.permissions?.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1">
          {tool.permissions.map((p) => (
            <span key={p} className="text-[9px] text-hermes-muted font-mono px-1 py-0.5 bg-hermes-border/20 rounded">
              {p}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function MCPServerCard({ server }: { server: MCPServer }) {
  return (
    <div className="bg-hermes-bg rounded-lg p-3 border border-hermes-border/50">
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-medium text-hermes-text font-mono">{server.name}</span>
        <Badge variant={server.status === "CONNECTED" ? "success" : server.status === "ERROR" ? "danger" : "default"}>
          {server.status}
        </Badge>
      </div>
      <div className="flex items-center gap-3 text-[10px] text-hermes-muted font-mono">
        <span>{server.transport}</span>
        <span>{server.tool_count} outil(s)</span>
        {server.connected_at && <span>{new Date(server.connected_at).toLocaleTimeString()}</span>}
      </div>
    </div>
  );
}
