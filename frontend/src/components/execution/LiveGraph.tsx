"use client";

import { useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type NodeTypes,
  MarkerType,
  useNodesState,
  useEdgesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useExecutionGraph } from "@/hooks/use-execution";
import type { ExecutionGraphData, GraphNode } from "@/types/mission-control";

const NODE_COLORS: Record<string, string> = {
  pending: "#64748b",
  ready: "#6366f1",
  running: "#6366f1",
  completed: "#10b981",
  failed: "#ef4444",
  skipped: "#64748b",
  cancelled: "#64748b",
  retry: "#f59e0b",
};

function ExecNode({ data }: { data: { label: string; status: string; runtime?: string; duration_ms?: number; retries?: number } }) {
  const color = NODE_COLORS[data.status] ?? "#64748b";
  return (
    <div
      className="flex flex-col rounded-lg border-2 bg-[var(--color-bg-surface)] px-3 py-2 text-xs shadow-lg"
      style={{ borderColor: color, minWidth: 130 }}
    >
      <div className="flex items-center gap-2">
        <span
          className="h-2 w-2 rounded-full"
          style={{ backgroundColor: color }}
        />
        <span className="font-medium text-[var(--color-text-primary)]">{data.label}</span>
      </div>
      <div className="mt-1 flex flex-wrap gap-1.5 text-[9px] text-[var(--color-text-muted)]">
        {data.runtime && <span>{data.runtime}</span>}
        {data.duration_ms && <span>~{(data.duration_ms / 1000).toFixed(0)}s</span>}
        {data.retries && data.retries > 0 && (
          <span className="text-[var(--color-warning)]">{data.retries} retr{data.retries > 1 ? "ies" : "y"}</span>
        )}
      </div>
    </div>
  );
}

const nodeTypes: NodeTypes = { execNode: ExecNode };

interface LiveGraphProps {
  graphData?: ExecutionGraphData;
}

export default function LiveGraph({ graphData: externalData }: LiveGraphProps) {
  const { data: fetchedData } = useExecutionGraph();
  const data = externalData ?? fetchedData;

  const { nodes: initialNodes, edges: initialEdges } = useMemo(() => {
    if (!data) return { nodes: [], edges: [] };
    return {
      nodes: data.nodes.map((n: GraphNode, i: number) => ({
        id: n.id,
        type: "execNode",
        position: { x: (i % 3) * 220 + 50, y: Math.floor(i / 3) * 140 + 50 },
        data: { label: n.label, status: n.status, runtime: n.runtime, duration_ms: n.estimated_ms },
      })),
      edges: data.edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        label: e.label,
        style: { stroke: "#64748b", strokeWidth: 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: "#64748b" },
        labelStyle: { fill: "#64748b", fontSize: 10 },
      })),
    };
  }, [data]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(initialEdges);

  // Sync when data changes
  if (data && (JSON.stringify(initialNodes) !== JSON.stringify(nodes))) {
    setTimeout(() => setNodes(initialNodes), 0);
  }

  if (!data) {
    return (
      <div className="flex h-full min-h-[250px] items-center justify-center rounded-xl border border-dashed border-white/10 bg-[var(--color-bg-surface)] p-8">
        <p className="text-sm text-[var(--color-text-muted)]">No execution graph available</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)]">
      <div className="border-b border-white/10 px-4 py-3">
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Live Execution Graph</h3>
      </div>
      <div style={{ height: 400 }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          fitView
          attributionPosition="bottom-left"
        >
          <Background color="#ffffff10" gap={20} />
          <Controls className="!bg-[var(--color-bg-surface)] !border-white/10" />
          <MiniMap
            className="!border-white/10"
            style={{ background: "var(--color-bg-surface)" }}
            nodeColor={(n) => NODE_COLORS[(n.data?.status as string) ?? "pending"] ?? "#64748b"}
          />
        </ReactFlow>
      </div>
    </div>
  );
}
