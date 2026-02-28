import { useState } from "react";
import { graphApi } from "@/lib/api";
import type { GraphNode } from "@/lib/types";
import { formatNodeType, cn, getNetworkColor, formatNetworkType } from "@/lib/utils";

interface CitationLinkProps {
  nodeId: string;
  index: number;
  onNavigate?: (nodeId: string) => void;
}

export function CitationLink({ nodeId, index, onNavigate }: CitationLinkProps) {
  const [preview, setPreview] = useState<GraphNode | null>(null);
  const [showPreview, setShowPreview] = useState(false);

  const handleMouseEnter = async () => {
    setShowPreview(true);
    if (!preview) {
      try {
        const node = await graphApi.getNode(nodeId);
        setPreview(node);
      } catch {
        // Node not found
      }
    }
  };

  return (
    <span className="relative inline-block">
      <button
        onMouseEnter={handleMouseEnter}
        onMouseLeave={() => setShowPreview(false)}
        onClick={() => onNavigate?.(nodeId)}
        className="inline-flex items-center justify-center w-5 h-5 text-[10px] rounded bg-blue-500/20 text-blue-400 hover:bg-blue-500/30 cursor-pointer"
      >
        {index}
      </button>

      {showPreview && preview && (
        <div className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-1 w-56 bg-surface-raised border border-border rounded-lg shadow-xl p-3">
          <p className="text-xs font-medium text-slate-200 mb-1">
            {preview.title}
          </p>
          <div className="flex flex-wrap gap-1 mb-1">
            <span className="px-1 py-0.5 text-[10px] rounded bg-slate-700 text-slate-400">
              {formatNodeType(preview.node_type)}
            </span>
            {preview.networks.map((net) => (
              <span
                key={net}
                className={cn(
                  "px-1 py-0.5 text-[10px] rounded",
                  getNetworkColor(net).badge
                )}
              >
                {formatNetworkType(net)}
              </span>
            ))}
          </div>
          {preview.content && (
            <p className="text-[10px] text-slate-500 line-clamp-2">
              {preview.content}
            </p>
          )}
        </div>
      )}
    </span>
  );
}
