import { useEffect, useState, useCallback } from "react";
import { GraphCanvas, NodeDetailPanel } from "@/components/graph";
import { useGraphStore } from "@/stores/graphStore";
import {
  formatNodeType,
  cn,
} from "@/lib/utils";

export function GraphView() {
  const {
    selectedNodeId,
    selectNode,
    fetchNodes,
    fetchNeighborhood,
    search,
    searchResults,
    clearSearch,
    isLoading,
  } = useGraphStore();
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    fetchNodes({ limit: 100 });
  }, [fetchNodes]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      search(searchQuery);
    } else {
      clearSearch();
    }
  };

  const handleNodeClick = useCallback(
    (nodeId: string) => {
      selectNode(nodeId);
      fetchNeighborhood(nodeId);
      clearSearch();
      setSearchQuery("");
    },
    [selectNode, fetchNeighborhood, clearSearch]
  );

  const handleCloseDetail = useCallback(() => {
    selectNode(null);
  }, [selectNode]);

  return (
    <div className="flex h-full">
      <div className="flex-1 relative">
        {/* Search overlay */}
        <div className="absolute top-3 left-3 z-10">
          <form onSubmit={handleSearch}>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search graph..."
              className="w-64 px-3 py-1.5 text-sm bg-surface-raised border border-border rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
          </form>
          {searchResults.length > 0 && (
            <div className="mt-1 bg-surface-raised border border-border rounded-lg shadow-xl max-h-64 overflow-y-auto">
              {searchResults.map((result) => (
                <button
                  key={result.node.id}
                  onClick={() => handleNodeClick(result.node.id)}
                  className="w-full px-3 py-2 text-left hover:bg-surface-overlay transition-colors"
                >
                  <p className="text-sm text-slate-200 truncate">
                    {result.node.title}
                  </p>
                  <div className="flex gap-2 text-xs text-slate-500">
                    <span>{formatNodeType(result.node.node_type)}</span>
                    <span
                      className={cn(
                        result.score >= 0.8
                          ? "text-green-500"
                          : result.score >= 0.5
                            ? "text-yellow-500"
                            : "text-slate-500"
                      )}
                    >
                      {Math.round(result.score * 100)}% match
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {isLoading && (
          <div className="absolute top-3 right-14 z-10">
            <span className="text-xs text-slate-500 animate-pulse">Loading...</span>
          </div>
        )}

        <GraphCanvas />
      </div>

      {selectedNodeId && (
        <NodeDetailPanel
          nodeId={selectedNodeId}
          onClose={handleCloseDetail}
          onNavigateToNode={handleNodeClick}
        />
      )}
    </div>
  );
}
