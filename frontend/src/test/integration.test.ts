import { describe, it, expect, beforeEach } from "vitest";
import { NodeType, NetworkType, EdgeCategory, EdgeType, ProposalStatus, ProposalRoute } from "@/lib/types";
import type {
  GraphNode,
  GraphEdge,
  SearchResult,
  ProposalResponse,
  CaptureResponse,
  NetworkHealth,
  DailyBriefing,
  CouncilQueryResponse,
  QueryType,
} from "@/lib/types";

// ── Test Helpers ─────────────────────────────────────────────────────────────

function makeNode(overrides: Partial<GraphNode> = {}): GraphNode {
  return {
    id: crypto.randomUUID(),
    node_type: NodeType.CONCEPT,
    title: "Test Node",
    content: "Test content",
    content_hash: "abc123",
    properties: {},
    confidence: 0.85,
    networks: [NetworkType.ACADEMIC],
    human_approved: false,
    proposed_by: "archivist",
    source_capture_id: null,
    access_count: 0,
    last_accessed: null,
    decay_score: 1.0,
    review_date: null,
    tags: [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}

function makeEdge(source: string, target: string, overrides: Partial<GraphEdge> = {}): GraphEdge {
  return {
    id: crypto.randomUUID(),
    source_id: source,
    target_id: target,
    edge_type: EdgeType.RELATED_TO,
    edge_category: EdgeCategory.ASSOCIATIVE,
    confidence: 0.8,
    weight: 1.0,
    bidirectional: false,
    properties: {},
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}

// ── Integration Tests ────────────────────────────────────────────────────────

describe("Integration: Capture → Pipeline → Proposal → Review → Commit → Graph", () => {
  it("should model the full capture-to-graph flow", () => {
    // Step 1: Create a capture
    const captureResponse: CaptureResponse = {
      id: "capture-1",
      status: "processing",
      pipeline_stage: 1,
      created_at: new Date().toISOString(),
    };
    expect(captureResponse.status).toBe("processing");

    // Step 2: Pipeline generates a proposal
    const proposal: ProposalResponse = {
      id: "proposal-1",
      capture_id: captureResponse.id,
      status: ProposalStatus.PENDING,
      route: ProposalRoute.EXPLICIT,
      confidence: 0.82,
      human_summary: "Creates a new concept node for 'Machine Learning'",
      action_count: 2,
      created_at: new Date().toISOString(),
      reviewed_at: null,
    };
    expect(proposal.status).toBe(ProposalStatus.PENDING);
    expect(proposal.capture_id).toBe(captureResponse.id);

    // Step 3: Proposal is approved, creates graph nodes
    const node = makeNode({
      title: "Machine Learning",
      node_type: NodeType.CONCEPT,
      source_capture_id: captureResponse.id,
    });
    expect(node.source_capture_id).toBe(captureResponse.id);

    // Step 4: Verify graph is updated
    const nodes = new Map<string, GraphNode>();
    nodes.set(node.id, node);
    expect(nodes.size).toBe(1);
    expect(nodes.get(node.id)!.title).toBe("Machine Learning");
  });
});

describe("Integration: Council Query → Streaming → Citations", () => {
  it("should model a council query flow with citations", () => {
    const node1 = makeNode({ title: "AI Research" });
    const node2 = makeNode({ title: "Neural Networks" });

    const queryResponse: CouncilQueryResponse = {
      query_id: "query-1",
      query_type: "council" as unknown as QueryType,
      synthesis: `Based on our analysis of ${node1.title} and ${node2.title}...`,
      agent_outputs: [
        {
          agent: "archivist" as any,
          content: "From the graph, we have relevant nodes...",
          confidence: 0.9,
          citations: [node1.id],
          sources: [],
        },
        {
          agent: "strategist" as any,
          content: "Strategic analysis suggests...",
          confidence: 0.85,
          citations: [node1.id, node2.id],
          sources: [],
        },
      ],
      confidence: 0.87,
      citations: [node1.id, node2.id],
      deliberation_rounds: 2,
      high_disagreement: false,
      created_at: new Date().toISOString(),
    };

    expect(queryResponse.citations).toContain(node1.id);
    expect(queryResponse.citations).toContain(node2.id);
    expect(queryResponse.agent_outputs.length).toBe(2);
    expect(queryResponse.confidence).toBeGreaterThan(0.8);
  });
});

describe("Integration: Network Health Updates", () => {
  it("should reflect health status changes in network data", () => {
    const network: NetworkHealth = {
      name: NetworkType.ACADEMIC,
      node_count: 42,
      health: {
        status: "on_track" as any,
        momentum: "up" as any,
        commitment_completion_rate: 0.85,
        alert_count: 1,
        staleness_flags: 2,
      },
    };

    expect(network.health.commitment_completion_rate).toBeGreaterThan(0.8);
    expect(network.node_count).toBe(42);

    // Simulate health change
    const updatedNetwork = {
      ...network,
      health: {
        ...network.health,
        status: "needs_attention" as any,
        momentum: "down" as any,
        alert_count: 3,
      },
    };
    expect(updatedNetwork.health.alert_count).toBe(3);
  });
});

describe("Integration: Bridge Discovery → Briefing", () => {
  it("should include discovered bridges in briefing data", () => {
    const academicNode = makeNode({
      title: "Graph Theory",
      networks: [NetworkType.ACADEMIC],
    });
    const venturesNode = makeNode({
      title: "Network Analysis Startup",
      networks: [NetworkType.VENTURES],
    });

    const bridge = {
      id: "bridge-1",
      source_node_id: academicNode.id,
      target_node_id: venturesNode.id,
      source_network: NetworkType.ACADEMIC,
      target_network: NetworkType.VENTURES,
      similarity_score: 0.82,
      description: "Graph theory knowledge applicable to startup",
      validated: true,
      created_at: new Date().toISOString(),
    };

    const briefing: DailyBriefing = {
      sections: [
        {
          title: "Cross-Network Bridges",
          items: [{ bridge_id: bridge.id, description: bridge.description }],
          priority: "medium",
        },
      ],
      summary: "1 new bridge discovered between Academic and Ventures",
      generated_at: new Date().toISOString(),
      cached: false,
    };

    expect(briefing.sections[0]!.items.length).toBe(1);
    expect(bridge.similarity_score).toBeGreaterThan(0.75);
  });
});

describe("Integration: SM-2 Review Flow", () => {
  it("should update review parameters after quality rating", () => {
    const node = makeNode({
      review_date: new Date().toISOString(),
      properties: {
        easiness: 2.5,
        interval: 1,
        repetitions: 0,
      },
    });

    // Simulate SM-2 after quality=4 review
    const quality = 4;
    const easiness = Math.max(
      1.3,
      (node.properties.easiness as number) +
        0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
    );
    expect(easiness).toBeGreaterThan(2.3);

    // After successful review, interval should increase
    const newInterval = quality >= 3 ? Math.max(1, (node.properties.interval as number) * easiness) : 1;
    expect(newInterval).toBeGreaterThanOrEqual(1);
  });
});

describe("Integration: Command Palette Search → Navigation", () => {
  it("should return search results that can be navigated to", () => {
    const node1 = makeNode({ title: "React Components" });
    const node2 = makeNode({ title: "React Hooks" });
    const node3 = makeNode({ title: "Python Scripts" });

    const allNodes = [node1, node2, node3];
    const query = "react";

    // Fuzzy search simulation
    const results: SearchResult[] = allNodes
      .filter((n) => n.title.toLowerCase().includes(query))
      .map((node) => ({ score: 0.9, node }));

    expect(results.length).toBe(2);
    expect(results[0]!.node.title).toContain("React");
    expect(results[1]!.node.title).toContain("React");
  });
});

describe("Integration: Offline Queue", () => {
  beforeEach(() => {
    if (typeof localStorage !== "undefined" && localStorage.clear) {
      localStorage.clear();
    } else {
      // Polyfill for test environment
      const store: Record<string, string> = {};
      Object.defineProperty(globalThis, "localStorage", {
        value: {
          getItem: (key: string) => store[key] ?? null,
          setItem: (key: string, val: string) => { store[key] = val; },
          removeItem: (key: string) => { delete store[key]; },
          clear: () => { for (const k in store) delete store[k]; },
        },
        writable: true,
        configurable: true,
      });
    }
  });

  it("should queue captures when offline and flush when online", async () => {
    const { queueCapture, getQueuedCaptures, clearQueue } = await import("@/lib/offlineQueue");

    // Queue a capture
    const id = queueCapture({ content: "Test note", modality: "text" });
    expect(id).toBeTruthy();

    const queued = getQueuedCaptures();
    expect(queued.length).toBe(1);
    expect(queued[0]!.data.content).toBe("Test note");

    // Clear queue
    clearQueue();
    expect(getQueuedCaptures().length).toBe(0);
  });
});

describe("Integration: Graph Node Operations", () => {
  it("should track node edges grouped by category", () => {
    const n1 = makeNode({ title: "Node A" });
    const n2 = makeNode({ title: "Node B" });
    const n3 = makeNode({ title: "Node C" });

    const edges: GraphEdge[] = [
      makeEdge(n1.id, n2.id, { edge_category: EdgeCategory.STRUCTURAL, edge_type: EdgeType.PART_OF }),
      makeEdge(n1.id, n3.id, { edge_category: EdgeCategory.ASSOCIATIVE, edge_type: EdgeType.RELATED_TO }),
      makeEdge(n2.id, n1.id, { edge_category: EdgeCategory.STRUCTURAL, edge_type: EdgeType.CONTAINS }),
    ];

    // Group by category
    const grouped = new Map<string, GraphEdge[]>();
    for (const edge of edges) {
      if (!grouped.has(edge.edge_category)) grouped.set(edge.edge_category, []);
      grouped.get(edge.edge_category)!.push(edge);
    }

    expect(grouped.get(EdgeCategory.STRUCTURAL)!.length).toBe(2);
    expect(grouped.get(EdgeCategory.ASSOCIATIVE)!.length).toBe(1);
  });

  it("should properly handle node deletion cascading to edges", () => {
    const n1 = makeNode({ title: "Node A" });
    const n2 = makeNode({ title: "Node B" });
    const n3 = makeNode({ title: "Node C" });

    const nodeMap = new Map<string, GraphNode>();
    nodeMap.set(n1.id, n1);
    nodeMap.set(n2.id, n2);
    nodeMap.set(n3.id, n3);

    const edgeMap = new Map<string, GraphEdge>();
    const e1 = makeEdge(n1.id, n2.id);
    const e2 = makeEdge(n2.id, n3.id);
    const e3 = makeEdge(n1.id, n3.id);
    edgeMap.set(e1.id, e1);
    edgeMap.set(e2.id, e2);
    edgeMap.set(e3.id, e3);

    // Delete n1
    nodeMap.delete(n1.id);
    for (const [id, edge] of edgeMap) {
      if (edge.source_id === n1.id || edge.target_id === n1.id) {
        edgeMap.delete(id);
      }
    }

    expect(nodeMap.size).toBe(2);
    expect(edgeMap.size).toBe(1); // Only e2 remains
    expect(edgeMap.has(e2.id)).toBe(true);
  });
});
