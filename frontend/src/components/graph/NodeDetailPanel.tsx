import { useState, useEffect, memo } from "react";
import { useGraphStore } from "@/stores/graphStore";
import { graphApi } from "@/lib/api";
import {
  formatNodeType,
  formatNetworkType,
  formatDateTime,
  timeAgo,
  confidenceColor,
  cn,
  getNetworkColor,
} from "@/lib/utils";
import type { GraphEdge } from "@/lib/types";
import { NodeEdges } from "./NodeEdges";
import { NodeTimeline } from "./NodeTimeline";
import { NodeActions } from "./NodeActions";

interface NodeDetailPanelProps {
  nodeId: string;
  onClose: () => void;
  onNavigateToNode: (nodeId: string) => void;
}

type DetailTab = "details" | "edges" | "timeline" | "actions";

export const NodeDetailPanel = memo(function NodeDetailPanel({
  nodeId,
  onClose,
  onNavigateToNode,
}: NodeDetailPanelProps) {
  const { nodes, updateNode, deleteNode } = useGraphStore();
  const [activeTab, setActiveTab] = useState<DetailTab>("details");
  const [nodeEdges, setNodeEdges] = useState<GraphEdge[]>([]);
  const [isLoadingEdges, setIsLoadingEdges] = useState(false);
  const [tagInput, setTagInput] = useState("");

  const node = nodes.get(nodeId);

  useEffect(() => {
    setIsLoadingEdges(true);
    graphApi
      .getEdges({ node_id: nodeId })
      .then(setNodeEdges)
      .catch(() => setNodeEdges([]))
      .finally(() => setIsLoadingEdges(false));
  }, [nodeId]);

  if (!node) {
    return (
      <div className="w-96 border-l border-border bg-surface-raised p-4">
        <div className="flex justify-between items-center mb-4">
          <span className="text-sm text-slate-500">Node not found</span>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-xs">
            Close
          </button>
        </div>
      </div>
    );
  }

  const handleAddTag = () => {
    const tag = tagInput.trim();
    if (tag && !node.tags.includes(tag)) {
      updateNode(nodeId, { tags: [...node.tags, tag] });
    }
    setTagInput("");
  };

  const handleRemoveTag = (tag: string) => {
    updateNode(nodeId, { tags: node.tags.filter((t) => t !== tag) });
  };

  const handleDelete = async () => {
    await deleteNode(nodeId);
    onClose();
  };

  const tabs: { key: DetailTab; label: string }[] = [
    { key: "details", label: "Details" },
    { key: "edges", label: `Edges (${nodeEdges.length})` },
    { key: "timeline", label: "Timeline" },
    { key: "actions", label: "Actions" },
  ];

  return (
    <div className="w-96 border-l border-border bg-surface-raised flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="px-4 pt-4 pb-2 border-b border-border shrink-0">
        <div className="flex items-start justify-between mb-2">
          <h3 className="text-sm font-medium text-slate-200 leading-tight pr-4">
            {node.title}
          </h3>
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-300 text-xs shrink-0"
          >
            Esc
          </button>
        </div>

        <div className="flex flex-wrap gap-1 mb-2">
          <span className="px-1.5 py-0.5 text-xs rounded bg-slate-700 text-slate-300">
            {formatNodeType(node.node_type)}
          </span>
          <span className={cn("px-1.5 py-0.5 text-xs rounded", confidenceColor(node.confidence))}>
            {Math.round(node.confidence * 100)}% conf
          </span>
          {node.networks.map((net) => (
            <span
              key={net}
              className={cn("px-1.5 py-0.5 text-xs rounded", getNetworkColor(net).badge)}
            >
              {formatNetworkType(net)}
            </span>
          ))}
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mt-2">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                "px-2 py-1 text-xs rounded transition-colors",
                activeTab === tab.key
                  ? "bg-blue-500/20 text-blue-400"
                  : "text-slate-500 hover:text-slate-300"
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === "details" && (
          <div className="space-y-4">
            {/* Content */}
            {node.content && (
              <div>
                <h4 className="text-xs text-slate-500 uppercase tracking-wider mb-1">Content</h4>
                <p className="text-xs text-slate-300 whitespace-pre-wrap">{node.content}</p>
              </div>
            )}

            {/* Properties */}
            {Object.keys(node.properties).length > 0 && (
              <div>
                <h4 className="text-xs text-slate-500 uppercase tracking-wider mb-1">Properties</h4>
                <div className="space-y-1">
                  {Object.entries(node.properties).map(([key, value]) => (
                    <div key={key} className="flex justify-between text-xs">
                      <span className="text-slate-500">{formatNodeType(key)}</span>
                      <span className="text-slate-300">{String(value)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Decay & Access */}
            <div>
              <h4 className="text-xs text-slate-500 uppercase tracking-wider mb-1">Metrics</h4>
              <div className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Decay Score</span>
                  <div className="flex items-center gap-2">
                    <div className="w-16 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-blue-400 rounded-full"
                        style={{ width: `${node.decay_score * 100}%` }}
                      />
                    </div>
                    <span className="text-slate-400">{Math.round(node.decay_score * 100)}%</span>
                  </div>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Access Count</span>
                  <span className="text-slate-400">{node.access_count}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Confidence</span>
                  <span className={confidenceColor(node.confidence)}>
                    {Math.round(node.confidence * 100)}%
                  </span>
                </div>
              </div>
            </div>

            {/* Provenance */}
            <div>
              <h4 className="text-xs text-slate-500 uppercase tracking-wider mb-1">Provenance</h4>
              <div className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Proposed By</span>
                  <span className="text-slate-400">{node.proposed_by || "Unknown"}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Approved</span>
                  <span className={node.human_approved ? "text-green-400" : "text-yellow-400"}>
                    {node.human_approved ? "Yes" : "Pending"}
                  </span>
                </div>
                {node.source_capture_id && (
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-500">Source Capture</span>
                    <span className="text-slate-400 font-mono text-[10px]">
                      {node.source_capture_id.slice(0, 8)}...
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Tags */}
            <div>
              <h4 className="text-xs text-slate-500 uppercase tracking-wider mb-1">Tags</h4>
              <div className="flex flex-wrap gap-1 mb-2">
                {node.tags.length === 0 && (
                  <span className="text-xs text-slate-600">No tags</span>
                )}
                {node.tags.map((tag) => (
                  <span
                    key={tag}
                    className="group px-1.5 py-0.5 text-xs rounded bg-slate-700 text-slate-400 flex items-center gap-1"
                  >
                    #{tag}
                    <button
                      onClick={() => handleRemoveTag(tag)}
                      className="text-slate-600 hover:text-red-400 hidden group-hover:inline"
                    >
                      x
                    </button>
                  </span>
                ))}
              </div>
              <div className="flex gap-1">
                <input
                  type="text"
                  value={tagInput}
                  onChange={(e) => setTagInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleAddTag()}
                  placeholder="Add tag..."
                  className="flex-1 px-2 py-1 text-xs bg-surface border border-border rounded text-slate-300 placeholder-slate-600 focus:outline-none focus:border-blue-500"
                />
                <button
                  onClick={handleAddTag}
                  className="px-2 py-1 text-xs bg-blue-500/20 text-blue-400 rounded hover:bg-blue-500/30"
                >
                  Add
                </button>
              </div>
            </div>

            {/* Timestamps */}
            <div>
              <h4 className="text-xs text-slate-500 uppercase tracking-wider mb-1">Timestamps</h4>
              <div className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Created</span>
                  <span className="text-slate-400">{formatDateTime(node.created_at)}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Updated</span>
                  <span className="text-slate-400">{timeAgo(node.updated_at)}</span>
                </div>
                {node.last_accessed && (
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-500">Last Accessed</span>
                    <span className="text-slate-400">{timeAgo(node.last_accessed)}</span>
                  </div>
                )}
                {node.review_date && (
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-500">Next Review</span>
                    <span className="text-slate-400">{formatDateTime(node.review_date)}</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === "edges" && (
          <NodeEdges
            edges={nodeEdges}
            currentNodeId={nodeId}
            isLoading={isLoadingEdges}
            onNavigateToNode={onNavigateToNode}
          />
        )}

        {activeTab === "timeline" && (
          <NodeTimeline node={node} edges={nodeEdges} />
        )}

        {activeTab === "actions" && (
          <NodeActions
            node={node}
            onDelete={handleDelete}
            onUpdate={(updates) => updateNode(nodeId, updates)}
          />
        )}
      </div>
    </div>
  );
});
