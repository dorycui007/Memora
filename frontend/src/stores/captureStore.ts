import { create } from "zustand";
import type { CaptureResponse, Capture } from "@/lib/types";
import { capturesApi } from "@/lib/api";
import { queueCapture, getQueuedCaptures, flushQueue } from "@/lib/offlineQueue";

interface CaptureState {
  isCapturing: boolean;
  pendingCaptures: CaptureResponse[];
  recentCaptures: Capture[];
  queuedCount: number;
  isLoading: boolean;
  error: string | null;

  createCapture: (content: string, metadata?: Record<string, unknown>) => Promise<CaptureResponse | null>;
  clearPending: () => void;
  fetchRecent: (limit?: number) => Promise<void>;
  setCapturing: (value: boolean) => void;
  flushOfflineQueue: () => Promise<number>;
  refreshQueuedCount: () => void;
}

export const useCaptureStore = create<CaptureState>((set, get) => ({
  isCapturing: false,
  pendingCaptures: [],
  recentCaptures: [],
  queuedCount: getQueuedCaptures().length,
  isLoading: false,
  error: null,

  createCapture: async (content, metadata) => {
    set({ isCapturing: true, error: null });
    try {
      const response = await capturesApi.create({
        modality: "text",
        content,
        metadata,
      });
      set({
        pendingCaptures: [response, ...get().pendingCaptures],
        isCapturing: false,
      });
      return response;
    } catch (e) {
      // Offline: queue the capture
      const captureData = {
        modality: "text" as const,
        content,
        metadata,
      };
      queueCapture(captureData);
      set({
        error: "Capture queued for later (offline)",
        isCapturing: false,
        queuedCount: getQueuedCaptures().length,
      });
      return null;
    }
  },

  clearPending: () => set({ pendingCaptures: [] }),

  fetchRecent: async (limit = 20) => {
    set({ isLoading: true });
    try {
      const captures = await capturesApi.list({ limit });
      set({ recentCaptures: captures, isLoading: false });
    } catch (e) {
      set({ error: (e as Error).message, isLoading: false });
    }
  },

  setCapturing: (value) => set({ isCapturing: value }),

  flushOfflineQueue: async () => {
    const flushed = await flushQueue();
    set({ queuedCount: getQueuedCaptures().length });
    return flushed;
  },

  refreshQueuedCount: () => {
    set({ queuedCount: getQueuedCaptures().length });
  },
}));
