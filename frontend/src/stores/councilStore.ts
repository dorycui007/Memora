import { create } from "zustand";
import type {
  AgentOutput,
  AgentRole,
  AgentStateUpdate,
  CouncilQueryResponse,
  CritiqueResponse,
  DailyBriefing,
  StreamToken,
} from "@/lib/types";
import { councilApi, wsManager } from "@/lib/api";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  agentOutputs?: AgentOutput[];
  confidence?: number;
  citations?: string[];
  timestamp: string;
}

interface CouncilState {
  isQuerying: boolean;
  activeAgents: Map<AgentRole, "thinking" | "generating" | "done" | "error">;
  streamTokens: StreamToken[];
  streamingContent: string;
  currentBriefing: DailyBriefing | null;
  messages: ChatMessage[];
  error: string | null;

  submitQuery: (query: string, queryType?: string) => Promise<void>;
  submitStreamingQuery: (query: string, queryType?: string) => void;
  submitCritique: (statement: string) => Promise<CritiqueResponse>;
  appendToken: (token: StreamToken) => void;
  updateAgentState: (update: AgentStateUpdate) => void;
  fetchBriefing: () => Promise<void>;
  clearStream: () => void;
  addMessage: (message: ChatMessage) => void;
}

export const useCouncilStore = create<CouncilState>((set, get) => ({
  isQuerying: false,
  activeAgents: new Map(),
  streamTokens: [],
  streamingContent: "",
  currentBriefing: null,
  messages: [],
  error: null,

  submitQuery: async (query, queryType) => {
    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: query,
      timestamp: new Date().toISOString(),
    };
    set({
      isQuerying: true,
      error: null,
      messages: [...get().messages, userMessage],
    });

    try {
      const response: CouncilQueryResponse = await councilApi.query({
        query,
        query_type: queryType as CouncilQueryResponse["query_type"],
      });
      const assistantMessage: ChatMessage = {
        id: response.query_id,
        role: "assistant",
        content: response.synthesis,
        agentOutputs: response.agent_outputs,
        confidence: response.confidence,
        citations: response.citations,
        timestamp: response.created_at,
      };
      set({
        messages: [...get().messages, assistantMessage],
        isQuerying: false,
      });
    } catch (e) {
      set({ error: (e as Error).message, isQuerying: false });
    }
  },

  submitStreamingQuery: (query, queryType) => {
    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: query,
      timestamp: new Date().toISOString(),
    };
    set({
      isQuerying: true,
      streamTokens: [],
      streamingContent: "",
      activeAgents: new Map(),
      messages: [...get().messages, userMessage],
    });

    wsManager.connect({
      onToken: (token) => get().appendToken(token),
      onStateUpdate: (update) => get().updateAgentState(update),
      onClose: () => {
        const content = get().streamingContent;
        if (content) {
          const msg: ChatMessage = {
            id: crypto.randomUUID(),
            role: "assistant",
            content,
            timestamp: new Date().toISOString(),
          };
          set({
            messages: [...get().messages, msg],
            isQuerying: false,
            streamingContent: "",
          });
        }
      },
    });

    wsManager.send({ query, query_type: queryType });
  },

  submitCritique: async (statement) => {
    set({ isQuerying: true, error: null });
    try {
      const response = await councilApi.critique({ statement });
      set({ isQuerying: false });
      return response;
    } catch (e) {
      set({ error: (e as Error).message, isQuerying: false });
      throw e;
    }
  },

  appendToken: (token) => {
    set({
      streamTokens: [...get().streamTokens, token],
      streamingContent: get().streamingContent + token.token,
    });
  },

  updateAgentState: (update) => {
    const agents = new Map(get().activeAgents);
    agents.set(update.agent, update.state);
    set({ activeAgents: agents });
  },

  fetchBriefing: async () => {
    try {
      const briefing = await councilApi.getBriefing();
      set({ currentBriefing: briefing });
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  clearStream: () =>
    set({ streamTokens: [], streamingContent: "", activeAgents: new Map() }),

  addMessage: (message) =>
    set({ messages: [...get().messages, message] }),
}));
