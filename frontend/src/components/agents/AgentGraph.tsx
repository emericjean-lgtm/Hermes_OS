"use client";

import { useMemo } from "react";
import { ReactFlow, Background, Controls, MiniMap, type Node, type Edge, MarkerType, useNodesState, useEdgesState } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useAgentGraph } from "@/hooks/use-agents";
import { Bot } from "lucide-react";

const STATE_COLORS: Record<string, string> = {
  CREATED: "#64748b", READY: "#6366f1", SCHEDULED: "#6366f1", RUNNING: "#6366f1",
  PAUSED: "#f59e0b", WAITING: "#f59e0b", COMPLETED: "#10b981", FAILED: "#ef4444",
  CANCELLED: "#64748b", TIMEOUT: "#ef4444",
};

function AgentFlowNode({ data }: { data: { label: string; state: string; runtime: string; progress: number } }) {
  return (
    <div className="flex flex-col rounded-lg border-2 bg-[var(--color-bg-surface)] px-3 py-2 text-xs shadow-lg" style={{ borderColor: STATE_COLORS[data.state] ?? "#64748b", minWidth: 110 }}>
      <div className="flex items-center gap-1.5">
        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: STATE_COLORS[data.state] ?? "#64748b" }} />
        <span className="font-medium text-[var(--color-text-primary)]">{data.label}</span>
      </div>
      <div className="mt-0.5 flex items-center gap-2 text-[9px] text-[var(--color-text-muted)]">
        <span>{data.runtime}</span>
        {data.progress > 0 && <span>{data.progress}%</span>}
      </div>
    </div>
  );
}

const nodeTypes = { agentNode: AgentFlowNode };

export default function AgentGraph() {
  const { data: graphData } = useAgentGraph();

  const { nodes: initialNodes, edges: initialEdges } = useMemo(() => {
    if (!graphData) return { nodes: [], edges: [] };
    return {
      nodes: graphData.nodes.map((n, i) => ({
        id: n.id,
        type: "agentNode",
        position: { x: (i % 3) * 200 + 50, y: Math.floor(i / 3) * 120 + 50 },
        data: { label: n.label, state: n.state, runtime: n.runtime, progress: n.progress },
      })),
      edges: graphData.edges.map((e, i) => ({
        id: `e${i}`, source: e.source, target: e.target, label: e.label,
        style: { stroke: "#64748b", strokeWidth: 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: "#64748b" },
      })),
    };
  }, [graphData]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(initialEdges);
  if (graphData && JSON.stringify(initialNodes) !== JSON.stringify(nodes)) setTimeout(() => setNodes(initialNodes), 0);

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)]">
      <div className="border-b border-white/10 px-4 py-3"><h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Agent Graph</h3></div>
      <div style={{ height: 350 }}>
        <ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} nodeTypes={nodeTypes} fitView attributionPosition="bottom-left">
          <Background color="#ffffff10" gap={20} />
          <Controls className="!bg-[var(--color-bg-surface)] !border-white/10" />
          <MiniMap className="!border-white/10" style={{ background: "var(--color-bg-surface)" }} nodeColor={(n) => STATE_COLORS[(n.data?.state as string) ?? "CREATED"] ?? "#64748b"} />
        </ReactFlow>
      </div>
    </div>
  );
}
