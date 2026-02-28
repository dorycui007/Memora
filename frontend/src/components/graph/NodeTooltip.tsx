import { useEffect, useState } from "react";
import { useRegisterEvents, useSigma } from "@react-sigma/core";
import { useGraphStore } from "@/stores/graphStore";
import { formatNodeType, formatNetworkType, getNetworkColor, cn } from "@/lib/utils";

interface TooltipData {
  x: number;
  y: number;
  nodeId: string;
}

export function NodeTooltip() {
  const [tooltip, setTooltip] = useState<TooltipData | null>(null);
  const registerEvents = useRegisterEvents();
  const sigma = useSigma();
  const { nodes } = useGraphStore();

  useEffect(() => {
    registerEvents({
      enterNode: (event) => {
        const attrs = sigma.getGraph().getNodeAttributes(event.node);
        const viewportPos = sigma.graphToViewport(
          { x: attrs.x as number, y: attrs.y as number }
        );
        setTooltip({
          x: viewportPos.x,
          y: viewportPos.y,
          nodeId: event.node,
        });
      },
      leaveNode: () => {
        setTooltip(null);
      },
    });
  }, [registerEvents, sigma]);

  if (!tooltip) return null;

  const node = nodes.get(tooltip.nodeId);
  if (!node) return null;

  return (
    <div
      className="absolute pointer-events-none z-50 bg-surface-raised border border-border rounded-lg shadow-xl p-3 max-w-64"
      style={{
        left: tooltip.x + 12,
        top: tooltip.y - 12,
        transform: "translateY(-100%)",
      }}
    >
      <p className="text-sm font-medium text-slate-200 mb-1">{node.title}</p>
      <div className="flex flex-wrap gap-1 mb-2">
        <span className="px-1.5 py-0.5 text-xs rounded bg-slate-700 text-slate-300">
          {formatNodeType(node.node_type)}
        </span>
        {node.networks.map((net) => (
          <span
            key={net}
            className={cn(
              "px-1.5 py-0.5 text-xs rounded",
              getNetworkColor(net).badge
            )}
          >
            {formatNetworkType(net)}
          </span>
        ))}
      </div>
      <div className="flex gap-3 text-xs text-slate-500">
        <span>Confidence: {Math.round(node.confidence * 100)}%</span>
        <span>Decay: {Math.round(node.decay_score * 100)}%</span>
      </div>
    </div>
  );
}
