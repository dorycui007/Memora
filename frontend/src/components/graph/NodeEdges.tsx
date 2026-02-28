import { useMemo, memo } from "react";
import { useGraphStore } from "@/stores/graphStore";
import { formatNodeType, EDGE_CATEGORY_COLORS } from "@/lib/utils";
import type { GraphEdge } from "@/lib/types";

interface NodeEdgesProps {
  edges: GraphEdge[];
  currentNodeId: string;
  isLoading: boolean;
  onNavigateToNode: (nodeId: string) => void;
}

export const NodeEdges = memo(function NodeEdges({
  edges,
  currentNodeId,
  isLoading,
  onNavigateToNode,
}: NodeEdgesProps) {
  const { nodes } = useGraphStore();

  const groupedEdges = useMemo(() => {
    const groups = new Map<string, GraphEdge[]>();
    for (const edge of edges) {
      const cat = edge.edge_category;
      if (!groups.has(cat)) groups.set(cat, []);
      groups.get(cat)!.push(edge);
    }
    return groups;
  }, [edges]);

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-12 bg-slate-800/50 rounded animate-pulse" />
        ))}
      </div>
    );
  }

  if (edges.length === 0) {
    return (
      <div className="text-center py-8 text-sm text-slate-500">
        No connected edges
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {Array.from(groupedEdges.entries()).map(([category, categoryEdges]) => (
        <div key={category}>
          <div className="flex items-center gap-2 mb-2">
            <div
              className="w-2 h-2 rounded-full"
              style={{ backgroundColor: EDGE_CATEGORY_COLORS[category] ?? "#6b7280" }}
            />
            <h4 className="text-xs text-slate-500 uppercase tracking-wider">
              {formatNodeType(category)} ({categoryEdges.length})
            </h4>
          </div>
          <div className="space-y-1">
            {categoryEdges.map((edge) => {
              const targetId =
                edge.source_id === currentNodeId ? edge.target_id : edge.source_id;
              const targetNode = nodes.get(targetId);
              const direction = edge.source_id === currentNodeId ? "out" : "in";

              return (
                <button
                  key={edge.id}
                  onClick={() => onNavigateToNode(targetId)}
                  className="w-full text-left px-2 py-1.5 rounded hover:bg-surface-overlay transition-colors group"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-slate-600 w-3">
                      {direction === "out" ? "\u2192" : "\u2190"}
                    </span>
                    <span className="text-xs text-slate-400">
                      {edge.edge_type.replace(/_/g, " ")}
                    </span>
                  </div>
                  <div className="flex items-center justify-between ml-5">
                    <span className="text-xs text-slate-300 truncate">
                      {targetNode?.title ?? targetId.slice(0, 8) + "..."}
                    </span>
                    <div className="flex gap-2 text-[10px] text-slate-600 shrink-0">
                      <span>c:{Math.round(edge.confidence * 100)}%</span>
                      <span>w:{edge.weight.toFixed(1)}</span>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
});
