import { useEffect, useRef, useMemo, memo } from "react";
import Graph from "graphology";
import {
  SigmaContainer,
  useLoadGraph,
  useRegisterEvents,
  useSigma,
} from "@react-sigma/core";
import { useGraphStore } from "@/stores/graphStore";
import { NODE_TYPE_COLORS, EDGE_CATEGORY_COLORS } from "@/lib/utils";
import { GraphControls } from "./GraphControls";
import { NodeTooltip } from "./NodeTooltip";

function GraphLoader() {
  const loadGraph = useLoadGraph();
  const { nodes, edges } = useGraphStore();

  useEffect(() => {
    const graph = new Graph();

    for (const [id, node] of nodes) {
      const color = NODE_TYPE_COLORS[node.node_type] ?? "#6b7280";
      const size = Math.max(3, Math.min(15, 3 + node.access_count * 0.5));
      graph.addNode(id, {
        label: node.title,
        x: Math.random() * 100,
        y: Math.random() * 100,
        size,
        color,
        nodeType: node.node_type,
        networks: node.networks,
        confidence: node.confidence,
        decayScore: node.decay_score,
      });
    }

    for (const [id, edge] of edges) {
      if (graph.hasNode(edge.source_id) && graph.hasNode(edge.target_id)) {
        try {
          graph.addEdge(edge.source_id, edge.target_id, {
            id,
            label: edge.edge_type.replace(/_/g, " "),
            color: EDGE_CATEGORY_COLORS[edge.edge_category] ?? "#6b7280",
            size: Math.max(1, edge.weight * 2),
            type: "arrow",
          });
        } catch {
          // Skip duplicate edges
        }
      }
    }

    loadGraph(graph);
  }, [loadGraph, nodes, edges]);

  return null;
}

function GraphEvents() {
  const registerEvents = useRegisterEvents();
  const sigma = useSigma();
  const { selectNode } = useGraphStore();

  useEffect(() => {
    registerEvents({
      clickNode: (event) => {
        selectNode(event.node);
      },
      clickStage: () => {
        selectNode(null);
      },
    });
  }, [registerEvents, selectNode]);

  useEffect(() => {
    const selectedNodeId = useGraphStore.getState().selectedNodeId;
    if (!selectedNodeId) return;

    const camera = sigma.getCamera();
    const pos = sigma.getGraph().getNodeAttributes(selectedNodeId);
    if (pos) {
      camera.animate({ x: pos.x, y: pos.y, ratio: 0.5 }, { duration: 300 });
    }
  }, [sigma]);

  return null;
}

export const GraphCanvas = memo(function GraphCanvas() {
  const containerRef = useRef<HTMLDivElement>(null);
  const { nodes } = useGraphStore();

  const sigmaSettings = useMemo(
    () => ({
      renderLabels: true,
      labelSize: 11,
      labelColor: { color: "#94a3b8" },
      defaultEdgeType: "arrow",
      defaultNodeColor: "#6b7280",
      defaultEdgeColor: "#334155",
      labelRenderedSizeThreshold: 6,
      zIndex: true,
    }),
    []
  );

  if (nodes.size === 0) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500">
        <div className="text-center">
          <p className="text-lg mb-1">No nodes to display</p>
          <p className="text-sm">Capture some knowledge to see your graph</p>
        </div>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="relative w-full h-full bg-surface">
      <SigmaContainer
        style={{ width: "100%", height: "100%" }}
        settings={sigmaSettings}
      >
        <GraphLoader />
        <GraphEvents />
        <GraphControls />
      </SigmaContainer>
      <NodeTooltip />
    </div>
  );
});
