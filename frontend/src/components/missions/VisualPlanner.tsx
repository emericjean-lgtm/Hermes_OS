"use client";

import { useMemo, useCallback } from "react";
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
import { useMissionGraph } from "@/hooks/use-missions";
import type { GraphNode, GraphEdge, ExecutionGraphData } from "@/types/mission-control";

const NODE_STATUS_COLORS: Record<string, string> = {
  completed: "#10b981",
  running: "#6366f1",
  ready: "#6366f1",
  pending: "#64748b",
  failed: "#ef4444",
  skipped: "#64748b",
};

const NODE_TYPE_SHAPES: Record<string, string> = {
  task: "border-radius: 8px; padding: 12px 16px;",
  start: "border-radius: 50%; width: 60px; height: 60px; display: flex; align-items: center; justify-content: center;",
  end: "border-radius: 50%; width: 60px; height: 60px; display: flex; align-items: center; justify-content: center;",
  condition: "border-radius: 4px; transform: rotate(45deg); width: 50px; height: 50px; display: flex; align-items: center; justify-content: center;",
};

function TaskNode({ data }: { data: { label: string; status: string; capability?: string; complexity?: string; estimated_ms?: number } }) {
  const color = NODE_STATUS_COLORS[data.status] ?? "#64748b";
  return (
    <div
      className="flex flex-col rounded-lg border-2 bg-[var(--color-bg-surface)] px-3 py-2 text-xs shadow-lg transition-all hover:shadow-xl"
      style={{ borderColor: color, minWidth: 120 }}
    >
      <span className="font-medium text-[var(--color-text-primary)]">{data.label}</span>
      <div className="mt-1 flex items-center gap-2 text-[10px] text-[var(--color-text-muted)]">
        {data.capability && <span>{data.capability}</span>}
        {data.complexity && (
          <span style={{ color: data.complexity === "high" ? "var(--color-danger)" : data.complexity === "medium" ? "var(--color-warning)" : "var(--color-success)" }}>
            {data.complexity}
          </span>
        )}
      </div>
      {data.estimated_ms && (
        <span className="mt-0.5 text-[9px] text-[var(--color-text-muted)]">
          ~{(data.estimated_ms / 1000).toFixed(0)}s
        </span>
      )}
    </div>
  );
}

const nodeTypes: NodeTypes = { taskNode: TaskNode };

function toReactFlow(data: ExecutionGraphData | undefined): { nodes: Node[]; edges: Edge[] } {
  if (!data) return { nodes: [], edges: [] };

  const nodes: Node[] = data.nodes.map((n: GraphNode, index: number) => ({
    id: n.id,
    type: "taskNode",
    position: { x: (index % 4) * 200 + 50, y: Math.floor(index / 4) * 150 + 50 },
    data: {
      label: n.label,
      status: n.status,
      capability: n.capability,
      complexity: n.complexity,
      estimated_ms: n.estimated_ms,
    },
    style: {
      borderColor: NODE_STATUS_COLORS[n.status] ?? "#64748b",
    },
  }));

  const edges: Edge[] = data.edges.map((e: GraphEdge) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.label,
    style: { stroke: "#64748b", strokeWidth: 1.5 },
    markerEnd: { type: MarkerType.ArrowClosed, color: "#64748b" },
    labelStyle: { fill: "#64748b", fontSize: 10 },
  }));

  return { nodes, edges };
}

interface VisualPlannerProps {
  missionId: string | null;
}

export default function VisualPlanner({ missionId }: VisualPlannerProps) {
  const { data: graphData, isLoading } = useMissionGraph(missionId);

  const { nodes: initialNodes, edges: initialEdges } = useMemo(
    () => toReactFlow(graphData),
    [graphData],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(initialEdges);

  // Sync when data changes
  const prevData = useMemo(() => graphData, [graphData]);
  if (prevData !== graphData && graphData) {
    const { nodes: newNodes, edges: newEdges } = toReactFlow(graphData);
    // Only update if actually different
    if (JSON.stringify(newNodes) !== JSON.stringify(nodes)) {
      setTimeout(() => {
        setNodes(newNodes);
      }, 0);
    }
  }

  const onConnect = useCallback(() => {}, []);

  if (!missionId) {
    return (
      <div className="flex h-full min-h-[300px] items-center justify-center rounded-xl border border-dashed border-white/10 bg-[var(--color-bg-surface)] p-8">
        <p className="text-sm text-[var(--color-text-muted)]">Select a mission to visualize its execution graph</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex h-full min-h-[300px] items-center justify-center rounded-xl border border-white/10 bg-[var(--color-bg-surface)] p-8">
        <div className="animate-pulse text-sm text-[var(--color-text-muted)]">Loading execution graph...</div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-bg-surface)]">
      <div className="px-4 py-3 border-b border-white/10">
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Visual Planner</h3>
      </div>
      <div style={{ height: 450 }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          nodeTypes={nodeTypes}
          fitView
          attributionPosition="bottom-left"
        >
          <Background color="#ffffff10" gap={20} />
          <Controls className="!bg-[var(--color-bg-surface)] !border-white/10 !text-[var(--color-text-primary)]" />
          <MiniMap
            className="!border-white/10"
            style={{ background: "var(--color-bg-surface)" }}
            nodeColor={(n) => NODE_STATUS_COLORS[(n.data?.status as string) ?? "pending"] ?? "#64748b"}
          />
        </ReactFlow>
      </div>
    </div>
  );
}
