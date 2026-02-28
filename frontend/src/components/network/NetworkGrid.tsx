import { memo } from "react";
import type { NetworkHealth } from "@/lib/types";
import { NetworkCard } from "./NetworkCard";

interface NetworkGridProps {
  networks: NetworkHealth[];
  onSelect: (name: string) => void;
}

export const NetworkGrid = memo(function NetworkGrid({ networks, onSelect }: NetworkGridProps) {
  if (networks.length === 0) {
    return (
      <div className="text-center text-slate-500 py-12">
        <p className="text-lg mb-1">No network data</p>
        <p className="text-sm">Networks will appear once you start capturing</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
      {networks.map((network) => (
        <NetworkCard
          key={network.name}
          network={network}
          onClick={onSelect}
        />
      ))}
    </div>
  );
});
