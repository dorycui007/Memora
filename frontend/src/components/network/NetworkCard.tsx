import { memo } from "react";
import type { NetworkHealth } from "@/lib/types";
import {
  cn,
  formatNetworkType,
  healthStatusColor,
  momentumIcon,
  getNetworkColor,
} from "@/lib/utils";
import { HealthStatus } from "@/lib/types";

const STATUS_LABELS: Record<string, string> = {
  on_track: "On Track",
  needs_attention: "Needs Attention",
  falling_behind: "Falling Behind",
};

interface NetworkCardProps {
  network: NetworkHealth;
  onClick: (name: string) => void;
}

export const NetworkCard = memo(function NetworkCard({ network, onClick }: NetworkCardProps) {
  const colors = getNetworkColor(network.name);
  const status = network.health.status;
  const momentum = network.health.momentum;

  return (
    <button
      onClick={() => onClick(network.name)}
      className={cn(
        "border rounded-lg p-4 text-left transition-all hover:shadow-lg",
        colors.border,
        colors.bg,
        "hover:scale-[1.01]"
      )}
    >
      <div className="flex items-center justify-between mb-3">
        <h3 className={cn("text-sm font-semibold", colors.text)}>
          {formatNetworkType(network.name)}
        </h3>
        <span className="text-lg" title={`Momentum: ${momentum}`}>
          {momentumIcon(momentum)}
        </span>
      </div>

      <div className="flex items-center gap-2 mb-3">
        <span
          className={cn(
            "px-2 py-0.5 text-xs rounded-full",
            status === HealthStatus.ON_TRACK && "bg-green-500/20 text-green-400",
            status === HealthStatus.NEEDS_ATTENTION && "bg-yellow-500/20 text-yellow-400",
            status === HealthStatus.FALLING_BEHIND && "bg-red-500/20 text-red-400"
          )}
        >
          {STATUS_LABELS[status] ?? status}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <span className="text-slate-500">Nodes</span>
          <p className="text-slate-300 font-medium">{network.node_count}</p>
        </div>
        <div>
          <span className="text-slate-500">Completion</span>
          <p className={healthStatusColor(status)}>
            {Math.round(network.health.commitment_completion_rate * 100)}%
          </p>
        </div>
        <div>
          <span className="text-slate-500">Alerts</span>
          <p
            className={cn(
              "font-medium",
              network.health.alert_count > 0 ? "text-yellow-400" : "text-slate-500"
            )}
          >
            {network.health.alert_count}
          </p>
        </div>
        <div>
          <span className="text-slate-500">Stale</span>
          <p className="text-slate-400">{network.health.staleness_flags}</p>
        </div>
      </div>
    </button>
  );
});
