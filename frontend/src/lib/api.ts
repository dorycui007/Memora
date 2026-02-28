import axios, { type AxiosInstance } from "axios";
import type {
  Bridge,
  Capture,
  CaptureCreate,
  CaptureResponse,
  CouncilQueryRequest,
  CouncilQueryResponse,
  CritiqueRequest,
  CritiqueResponse,
  DailyBriefing,
  GraphEdge,
  GraphNode,
  GraphStats,
  NetworkDetail,
  NetworkHealth,
  ProposalDetail,
  ProposalResponse,
  SearchResult,
  StreamToken,
  AgentStateUpdate,
  Subgraph,
  VerifiedFact,
} from "./types";

const BASE_URL = "/api/v1";

const client: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
});

// ── Captures ─────────────────────────────────────────────────────────────────

export const capturesApi = {
  create: (data: CaptureCreate) =>
    client.post<CaptureResponse>("/captures", data).then((r) => r.data),

  get: (captureId: string) =>
    client.get<Capture>(`/captures/${captureId}`).then((r) => r.data),

  list: (params?: { limit?: number; offset?: number }) =>
    client.get<Capture[]>("/captures", { params }).then((r) => r.data),
};

// ── Graph ────────────────────────────────────────────────────────────────────

export const graphApi = {
  queryNodes: (params?: {
    node_type?: string;
    network?: string;
    tag?: string;
    min_confidence?: number;
    limit?: number;
    offset?: number;
  }) => client.get<GraphNode[]>("/graph/nodes", { params }).then((r) => r.data),

  getNode: (nodeId: string) =>
    client.get<GraphNode>(`/graph/nodes/${nodeId}`).then((r) => r.data),

  getNeighborhood: (nodeId: string, hops = 1) =>
    client
      .get<Subgraph>(`/graph/nodes/${nodeId}/neighborhood`, {
        params: { hops },
      })
      .then((r) => r.data),

  updateNode: (nodeId: string, updates: Record<string, unknown>) =>
    client
      .patch<GraphNode>(`/graph/nodes/${nodeId}`, updates)
      .then((r) => r.data),

  deleteNode: (nodeId: string) =>
    client.delete(`/graph/nodes/${nodeId}`).then((r) => r.data),

  getEdges: (params?: {
    node_id?: string;
    direction?: "both" | "in" | "out";
  }) => client.get<GraphEdge[]>("/graph/edges", { params }).then((r) => r.data),

  search: (params: {
    q: string;
    node_type?: string;
    network?: string;
    top_k?: number;
  }) =>
    client
      .get<SearchResult[]>("/graph/search", { params })
      .then((r) => r.data),

  getStats: () =>
    client.get<GraphStats>("/graph/stats").then((r) => r.data),

  submitReview: (nodeId: string, quality: number) =>
    client
      .post(`/graph/review/${nodeId}`, null, { params: { quality } })
      .then((r) => r.data),
};

// ── Proposals ────────────────────────────────────────────────────────────────

export const proposalsApi = {
  list: (params?: {
    status?: string;
    route?: string;
    limit?: number;
    offset?: number;
  }) =>
    client
      .get<ProposalResponse[]>("/proposals", { params })
      .then((r) => r.data),

  get: (proposalId: string) =>
    client
      .get<ProposalDetail>(`/proposals/${proposalId}`)
      .then((r) => r.data),

  approve: (proposalId: string) =>
    client.post(`/proposals/${proposalId}/approve`).then((r) => r.data),

  reject: (proposalId: string, reason?: string) =>
    client
      .post(`/proposals/${proposalId}/reject`, null, {
        params: reason ? { reason } : undefined,
      })
      .then((r) => r.data),

  edit: (
    proposalId: string,
    updates: { human_summary?: string; proposal_data?: Record<string, unknown> }
  ) =>
    client.patch(`/proposals/${proposalId}`, updates).then((r) => r.data),
};

// ── Council ──────────────────────────────────────────────────────────────────

export const councilApi = {
  query: (data: CouncilQueryRequest) =>
    client
      .post<CouncilQueryResponse>("/council/query", data)
      .then((r) => r.data),

  getBriefing: () =>
    client.get<DailyBriefing>("/council/briefing").then((r) => r.data),

  critique: (data: CritiqueRequest) =>
    client
      .post<CritiqueResponse>("/council/critique", data)
      .then((r) => r.data),
};

// ── Networks ─────────────────────────────────────────────────────────────────

export const networksApi = {
  list: () =>
    client
      .get<{ networks: NetworkHealth[] }>("/networks")
      .then((r) => r.data.networks),

  get: (networkName: string) =>
    client
      .get<NetworkDetail>(`/networks/${networkName}`)
      .then((r) => r.data),

  getBridges: (params?: {
    network?: string;
    validated_only?: boolean;
    limit?: number;
  }) =>
    client
      .get<{ bridges: Bridge[]; count: number }>("/networks/bridges", {
        params,
      })
      .then((r) => r.data),
};

// ── Facts ────────────────────────────────────────────────────────────────────

export const factsApi = {
  list: (params?: {
    node_id?: string;
    status?: string;
    lifecycle?: string;
    limit?: number;
    offset?: number;
  }) =>
    client
      .get<VerifiedFact[]>("/facts", { params })
      .then((r) => r.data),

  get: (factId: string) =>
    client.get<VerifiedFact>(`/facts/${factId}`).then((r) => r.data),

  getStale: () =>
    client.get<VerifiedFact[]>("/facts/stale").then((r) => r.data),
};

// ── WebSocket Manager ────────────────────────────────────────────────────────

export type WSMessage = StreamToken | AgentStateUpdate;

export class WebSocketManager {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private onToken: ((token: StreamToken) => void) | null = null;
  private onStateUpdate: ((update: AgentStateUpdate) => void) | null = null;
  private onError: ((error: Event) => void) | null = null;
  private onClose: (() => void) | null = null;

  connect(handlers: {
    onToken?: (token: StreamToken) => void;
    onStateUpdate?: (update: AgentStateUpdate) => void;
    onError?: (error: Event) => void;
    onClose?: () => void;
  }) {
    this.onToken = handlers.onToken ?? null;
    this.onStateUpdate = handlers.onStateUpdate ?? null;
    this.onError = handlers.onError ?? null;
    this.onClose = handlers.onClose ?? null;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/api/v1/ws/stream`;

    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
    };

    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data) as WSMessage;
      if ("token" in data) {
        this.onToken?.(data as StreamToken);
      } else if ("state" in data) {
        this.onStateUpdate?.(data as AgentStateUpdate);
      }
    };

    this.ws.onerror = (error) => {
      this.onError?.(error);
    };

    this.ws.onclose = () => {
      this.onClose?.();
      this.attemptReconnect();
    };
  }

  send(data: { query: string; query_type?: string; context?: Record<string, unknown> }) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  disconnect() {
    this.maxReconnectAttempts = 0;
    this.ws?.close();
    this.ws = null;
  }

  private attemptReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) return;
    this.reconnectAttempts++;
    const delay = Math.min(1000 * 2 ** this.reconnectAttempts, 30000);
    setTimeout(() => {
      this.connect({
        onToken: this.onToken ?? undefined,
        onStateUpdate: this.onStateUpdate ?? undefined,
        onError: this.onError ?? undefined,
        onClose: this.onClose ?? undefined,
      });
    }, delay);
  }

  get isConnected() {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

// ── SSE Manager ──────────────────────────────────────────────────────────────

export class SSEManager {
  private source: EventSource | null = null;
  private handlers = new Map<string, (data: Record<string, unknown>) => void>();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private shouldReconnect = true;

  connect() {
    this.shouldReconnect = true;
    this.source = new EventSource(`${BASE_URL}/council/events`);

    this.source.onopen = () => {
      this.reconnectAttempts = 0;
    };

    this.source.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data) as {
          event_type: string;
          data: Record<string, unknown>;
        };
        const handler = this.handlers.get(parsed.event_type);
        handler?.(parsed.data);
      } catch {
        // Ignore malformed events
      }
    };

    this.source.onerror = () => {
      this.source?.close();
      this.source = null;
      if (this.shouldReconnect && this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts++;
        const delay = Math.min(1000 * 2 ** this.reconnectAttempts, 30000);
        setTimeout(() => this.connect(), delay);
      }
    };
  }

  on(eventType: string, handler: (data: Record<string, unknown>) => void) {
    this.handlers.set(eventType, handler);
  }

  off(eventType: string) {
    this.handlers.delete(eventType);
  }

  disconnect() {
    this.shouldReconnect = false;
    this.reconnectAttempts = 0;
    this.source?.close();
    this.source = null;
    this.handlers.clear();
  }
}

export const wsManager = new WebSocketManager();
export const sseManager = new SSEManager();
