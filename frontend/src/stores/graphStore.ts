import { create } from "zustand";
import type { GraphNode, GraphEdge, Subgraph, SearchResult, GraphStats } from "@/lib/types";
import { graphApi } from "@/lib/api";

type ViewMode = "local" | "network" | "global";

interface GraphState {
  nodes: Map<string, GraphNode>;
  edges: Map<string, GraphEdge>;
  selectedNodeId: string | null;
  viewMode: ViewMode;
  stats: GraphStats | null;
  searchResults: SearchResult[];
  isLoading: boolean;
  error: string | null;

  fetchNodes: (params?: Parameters<typeof graphApi.queryNodes>[0]) => Promise<void>;
  fetchNeighborhood: (nodeId: string, hops?: number) => Promise<void>;
  selectNode: (nodeId: string | null) => void;
  setViewMode: (mode: ViewMode) => void;
  updateNode: (nodeId: string, updates: Record<string, unknown>) => Promise<void>;
  deleteNode: (nodeId: string) => Promise<void>;
  search: (query: string, filters?: { node_type?: string; network?: string }) => Promise<void>;
  fetchStats: () => Promise<void>;
  setSubgraph: (subgraph: Subgraph) => void;
  clearSearch: () => void;
}

export const useGraphStore = create<GraphState>((set, get) => ({
  nodes: new Map(),
  edges: new Map(),
  selectedNodeId: null,
  viewMode: "local",
  stats: null,
  searchResults: [],
  isLoading: false,
  error: null,

  fetchNodes: async (params) => {
    set({ isLoading: true, error: null });
    try {
      const nodes = await graphApi.queryNodes(params);
      const nodeMap = new Map(get().nodes);
      for (const node of nodes) {
        nodeMap.set(node.id, node);
      }
      set({ nodes: nodeMap, isLoading: false });
    } catch (e) {
      set({ error: (e as Error).message, isLoading: false });
    }
  },

  fetchNeighborhood: async (nodeId, hops = 1) => {
    set({ isLoading: true, error: null });
    try {
      const subgraph = await graphApi.getNeighborhood(nodeId, hops);
      const nodeMap = new Map<string, GraphNode>();
      const edgeMap = new Map<string, GraphEdge>();
      for (const node of subgraph.nodes) nodeMap.set(node.id, node);
      for (const edge of subgraph.edges) edgeMap.set(edge.id, edge);
      set({ nodes: nodeMap, edges: edgeMap, isLoading: false });
    } catch (e) {
      set({ error: (e as Error).message, isLoading: false });
    }
  },

  selectNode: (nodeId) => set({ selectedNodeId: nodeId }),

  setViewMode: (mode) => set({ viewMode: mode }),

  updateNode: async (nodeId, updates) => {
    try {
      const updated = await graphApi.updateNode(nodeId, updates);
      const nodeMap = new Map(get().nodes);
      nodeMap.set(updated.id, updated);
      set({ nodes: nodeMap });
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  deleteNode: async (nodeId) => {
    try {
      await graphApi.deleteNode(nodeId);
      const nodeMap = new Map(get().nodes);
      nodeMap.delete(nodeId);
      const edgeMap = new Map(get().edges);
      for (const [id, edge] of edgeMap) {
        if (edge.source_id === nodeId || edge.target_id === nodeId) {
          edgeMap.delete(id);
        }
      }
      set({
        nodes: nodeMap,
        edges: edgeMap,
        selectedNodeId: get().selectedNodeId === nodeId ? null : get().selectedNodeId,
      });
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  search: async (query, filters) => {
    set({ isLoading: true, error: null });
    try {
      const results = await graphApi.search({ q: query, ...filters });
      set({ searchResults: results, isLoading: false });
    } catch (e) {
      set({ error: (e as Error).message, isLoading: false });
    }
  },

  fetchStats: async () => {
    try {
      const stats = await graphApi.getStats();
      set({ stats });
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  setSubgraph: (subgraph) => {
    const nodeMap = new Map<string, GraphNode>();
    const edgeMap = new Map<string, GraphEdge>();
    for (const node of subgraph.nodes) nodeMap.set(node.id, node);
    for (const edge of subgraph.edges) edgeMap.set(edge.id, edge);
    set({ nodes: nodeMap, edges: edgeMap });
  },

  clearSearch: () => set({ searchResults: [] }),
}));
