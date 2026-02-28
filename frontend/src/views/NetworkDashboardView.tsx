import { useEffect, useState } from "react";
import { NetworkGrid, NetworkDetailPanel } from "@/components/network";
import { useNetworkStore } from "@/stores/networkStore";

export function NetworkDashboardView() {
  const { networks, fetchNetworks, isLoading } = useNetworkStore();
  const [selectedNetwork, setSelectedNetwork] = useState<string | null>(null);

  useEffect(() => {
    fetchNetworks();
  }, [fetchNetworks]);

  if (isLoading && networks.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500">
        Loading networks...
      </div>
    );
  }

  return (
    <div className="flex h-full">
      <div className="flex-1 overflow-y-auto p-6">
        <NetworkGrid networks={networks} onSelect={setSelectedNetwork} />
      </div>

      {selectedNetwork && (
        <div className="w-96 border-l border-border bg-surface-raised">
          <NetworkDetailPanel
            networkName={selectedNetwork}
            onClose={() => setSelectedNetwork(null)}
          />
        </div>
      )}
    </div>
  );
}
