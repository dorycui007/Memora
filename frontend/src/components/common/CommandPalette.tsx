import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useGraphStore } from "@/stores/graphStore";
import { formatNodeType, formatNetworkType, cn } from "@/lib/utils";
import type { SearchResult } from "@/lib/types";
import { graphApi } from "@/lib/api";

export type CommandAction = {
  id: string;
  label: string;
  category: "navigate" | "create" | "search" | "agent";
  description?: string;
  shortcut?: string;
  onExecute: () => void;
};

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  onNavigate: (view: string) => void;
}

export function CommandPalette({ open, onClose, onNavigate }: CommandPaletteProps) {
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const { selectNode, fetchNeighborhood } = useGraphStore();

  const staticActions = useMemo<CommandAction[]>(
    () => [
      {
        id: "nav-capture",
        label: "Go to Capture",
        category: "navigate",
        shortcut: "C",
        onExecute: () => onNavigate("capture"),
      },
      {
        id: "nav-graph",
        label: "Go to Graph",
        category: "navigate",
        shortcut: "G",
        onExecute: () => onNavigate("graph"),
      },
      {
        id: "nav-networks",
        label: "Go to Networks",
        category: "navigate",
        shortcut: "N",
        onExecute: () => onNavigate("networks"),
      },
      {
        id: "nav-briefing",
        label: "View Daily Briefing",
        category: "navigate",
        shortcut: "B",
        onExecute: () => onNavigate("briefing"),
      },
      {
        id: "nav-review",
        label: "Go to Review Queue",
        category: "navigate",
        shortcut: "R",
        onExecute: () => onNavigate("review"),
      },
      {
        id: "nav-council",
        label: "Query AI Council",
        category: "navigate",
        shortcut: "Q",
        onExecute: () => onNavigate("council"),
      },
      {
        id: "create-capture",
        label: "New Capture",
        category: "create",
        shortcut: "Cmd+N",
        onExecute: () => onNavigate("capture"),
      },
      {
        id: "agent-council",
        label: "Ask AI Council",
        category: "agent",
        onExecute: () => onNavigate("council"),
      },
      {
        id: "agent-briefing",
        label: "Open Daily Briefing",
        category: "agent",
        onExecute: () => onNavigate("briefing"),
      },
    ],
    [onNavigate]
  );

  const filteredActions = useMemo(() => {
    if (!query.trim()) return staticActions;
    const lowerQuery = query.toLowerCase();
    return staticActions.filter(
      (action) =>
        action.label.toLowerCase().includes(lowerQuery) ||
        action.category.toLowerCase().includes(lowerQuery) ||
        action.description?.toLowerCase().includes(lowerQuery)
    );
  }, [query, staticActions]);

  const allItems = useMemo(() => {
    const items: Array<{ type: "action"; data: CommandAction } | { type: "node"; data: SearchResult }> = [];
    for (const action of filteredActions) {
      items.push({ type: "action", data: action });
    }
    for (const result of searchResults) {
      items.push({ type: "node", data: result });
    }
    return items;
  }, [filteredActions, searchResults]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setSelectedIndex(0);
      setSearchResults([]);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  const handleSearch = useCallback(
    (q: string) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      if (!q.trim()) {
        setSearchResults([]);
        setIsSearching(false);
        return;
      }
      setIsSearching(true);
      debounceRef.current = setTimeout(async () => {
        try {
          const results = await graphApi.search({ q, top_k: 8 });
          setSearchResults(results);
        } catch {
          setSearchResults([]);
        } finally {
          setIsSearching(false);
        }
      }, 250);
    },
    []
  );

  const handleQueryChange = (value: string) => {
    setQuery(value);
    handleSearch(value);
  };

  const executeItem = useCallback(
    (index: number) => {
      const item = allItems[index];
      if (!item) return;
      if (item.type === "action") {
        item.data.onExecute();
      } else {
        selectNode(item.data.node.id);
        fetchNeighborhood(item.data.node.id);
        onNavigate("graph");
      }
      onClose();
    },
    [allItems, selectNode, fetchNeighborhood, onNavigate, onClose]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setSelectedIndex((prev) => Math.min(prev + 1, allItems.length - 1));
          break;
        case "ArrowUp":
          e.preventDefault();
          setSelectedIndex((prev) => Math.max(prev - 1, 0));
          break;
        case "Enter":
          e.preventDefault();
          executeItem(selectedIndex);
          break;
        case "Escape":
          e.preventDefault();
          onClose();
          break;
      }
    },
    [allItems.length, selectedIndex, executeItem, onClose]
  );

  useEffect(() => {
    const el = listRef.current?.children[selectedIndex] as HTMLElement | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }, [selectedIndex]);

  if (!open) return null;

  const categoryLabel = (cat: string) => {
    switch (cat) {
      case "navigate": return "Navigate";
      case "create": return "Create";
      case "search": return "Search";
      case "agent": return "Agent";
      default: return cat;
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh]">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative w-full max-w-lg bg-surface-raised border border-border rounded-xl shadow-2xl overflow-hidden">
        <div className="flex items-center px-4 border-b border-border">
          <span className="text-slate-500 text-sm mr-2">&#8984;K</span>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => handleQueryChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a command or search..."
            className="flex-1 py-3 bg-transparent text-sm text-slate-200 placeholder-slate-500 focus:outline-none"
          />
          {isSearching && (
            <span className="text-xs text-slate-500 animate-pulse">Searching...</span>
          )}
        </div>

        <div ref={listRef} className="max-h-80 overflow-y-auto py-1">
          {allItems.length === 0 && (
            <div className="px-4 py-8 text-center text-sm text-slate-500">
              No results found
            </div>
          )}

          {filteredActions.length > 0 && (
            <>
              <div className="px-3 py-1.5 text-xs text-slate-600 uppercase tracking-wider">
                Actions
              </div>
              {filteredActions.map((action, idx) => (
                <button
                  key={action.id}
                  onClick={() => executeItem(idx)}
                  onMouseEnter={() => setSelectedIndex(idx)}
                  className={cn(
                    "w-full flex items-center justify-between px-4 py-2 text-left text-sm transition-colors",
                    selectedIndex === idx
                      ? "bg-blue-500/10 text-blue-300"
                      : "text-slate-300 hover:bg-surface-overlay"
                  )}
                >
                  <div className="flex items-center gap-3">
                    <span
                      className={cn(
                        "px-1.5 py-0.5 text-[10px] rounded uppercase tracking-wider",
                        action.category === "navigate" && "bg-blue-500/20 text-blue-400",
                        action.category === "create" && "bg-green-500/20 text-green-400",
                        action.category === "search" && "bg-yellow-500/20 text-yellow-400",
                        action.category === "agent" && "bg-purple-500/20 text-purple-400"
                      )}
                    >
                      {categoryLabel(action.category)}
                    </span>
                    <span>{action.label}</span>
                  </div>
                  {action.shortcut && (
                    <span className="text-xs text-slate-600 font-mono">
                      {action.shortcut}
                    </span>
                  )}
                </button>
              ))}
            </>
          )}

          {searchResults.length > 0 && (
            <>
              <div className="px-3 py-1.5 text-xs text-slate-600 uppercase tracking-wider mt-1">
                Graph Nodes
              </div>
              {searchResults.map((result, i) => {
                const idx = filteredActions.length + i;
                return (
                  <button
                    key={result.node.id}
                    onClick={() => executeItem(idx)}
                    onMouseEnter={() => setSelectedIndex(idx)}
                    className={cn(
                      "w-full flex items-center justify-between px-4 py-2 text-left text-sm transition-colors",
                      selectedIndex === idx
                        ? "bg-blue-500/10 text-blue-300"
                        : "text-slate-300 hover:bg-surface-overlay"
                    )}
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate">{result.node.title}</p>
                      <div className="flex gap-2 text-xs text-slate-500 mt-0.5">
                        <span>{formatNodeType(result.node.node_type)}</span>
                        {result.node.networks.slice(0, 2).map((net) => (
                          <span key={net}>{formatNetworkType(net)}</span>
                        ))}
                      </div>
                    </div>
                    <span className="text-xs text-slate-600 ml-2 shrink-0">
                      {Math.round(result.score * 100)}%
                    </span>
                  </button>
                );
              })}
            </>
          )}
        </div>

        <div className="px-4 py-2 border-t border-border flex items-center gap-4 text-[10px] text-slate-600">
          <span>
            <kbd className="px-1 py-0.5 bg-slate-800 rounded text-slate-500">&#8593;&#8595;</kbd>{" "}
            navigate
          </span>
          <span>
            <kbd className="px-1 py-0.5 bg-slate-800 rounded text-slate-500">Enter</kbd>{" "}
            select
          </span>
          <span>
            <kbd className="px-1 py-0.5 bg-slate-800 rounded text-slate-500">Esc</kbd>{" "}
            close
          </span>
        </div>
      </div>
    </div>
  );
}
