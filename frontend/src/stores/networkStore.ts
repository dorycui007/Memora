import { create } from "zustand";
import type { NetworkHealth, NetworkDetail, Bridge } from "@/lib/types";
import { networksApi } from "@/lib/api";

interface NetworkState {
  networks: NetworkHealth[];
  selectedNetwork: NetworkDetail | null;
  bridges: Bridge[];
  bridgeCount: number;
  isLoading: boolean;
  error: string | null;

  fetchNetworks: () => Promise<void>;
  fetchNetworkDetail: (name: string) => Promise<void>;
  fetchBridges: (params?: { network?: string; validated_only?: boolean; limit?: number }) => Promise<void>;
  clearSelection: () => void;
}

export const useNetworkStore = create<NetworkState>((set) => ({
  networks: [],
  selectedNetwork: null,
  bridges: [],
  bridgeCount: 0,
  isLoading: false,
  error: null,

  fetchNetworks: async () => {
    set({ isLoading: true, error: null });
    try {
      const networks = await networksApi.list();
      set({ networks, isLoading: false });
    } catch (e) {
      set({ error: (e as Error).message, isLoading: false });
    }
  },

  fetchNetworkDetail: async (name) => {
    set({ isLoading: true, error: null });
    try {
      const detail = await networksApi.get(name);
      set({ selectedNetwork: detail, isLoading: false });
    } catch (e) {
      set({ error: (e as Error).message, isLoading: false });
    }
  },

  fetchBridges: async (params) => {
    try {
      const result = await networksApi.getBridges(params);
      set({ bridges: result.bridges, bridgeCount: result.count });
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  clearSelection: () => set({ selectedNetwork: null }),
}));
