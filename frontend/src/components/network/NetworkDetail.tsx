import { useEffect } from "react";
import { useNetworkStore } from "@/stores/networkStore";
import {
  cn,
  formatNetworkType,
  formatNodeType,
  healthStatusColor,
  momentumIcon,
  timeAgo,
  getNetworkColor,
} from "@/lib/utils";
import { HealthStatus } from "@/lib/types";

interface NetworkDetailProps {
  networkName: string;
  onClose: () => void;
}

export function NetworkDetailPanel({ networkName, onClose }: NetworkDetailProps) {
  const { selectedNetwork, fetchNetworkDetail, isLoading } = useNetworkStore();

  useEffect(() => {
    fetchNetworkDetail(networkName);
  }, [networkName, fetchNetworkDetail]);

  if (isLoading || !selectedNetwork) {
    return (
      <div className="p-6 text-center text-slate-500">Loading network...</div>
    );
  }

  const net = selectedNetwork;
  const colors = getNetworkColor(net.name);

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h3 className={cn("text-sm font-semibold", colors.text)}>
          {formatNetworkType(net.name)}
        </h3>
        <button
          onClick={onClose}
          className="text-slate-500 hover:text-slate-300 text-sm"
        >
          Close
        </button>
      </div>

      <div className="p-4 space-y-6">
        {/* Health overview */}
        <div className="grid grid-cols-3 gap-3">
          <div className="border border-border rounded-lg p-3 text-center">
            <span className="text-xs text-slate-500 block mb-1">Status</span>
            <span
              className={cn(
                "text-sm font-medium",
                healthStatusColor(net.health.status)
              )}
            >
              {net.health.status === HealthStatus.ON_TRACK
                ? "On Track"
                : net.health.status === HealthStatus.NEEDS_ATTENTION
                  ? "Attention"
                  : "Falling Behind"}
            </span>
          </div>
          <div className="border border-border rounded-lg p-3 text-center">
            <span className="text-xs text-slate-500 block mb-1">Momentum</span>
            <span className="text-lg">
              {momentumIcon(net.health.momentum)}
            </span>
          </div>
          <div className="border border-border rounded-lg p-3 text-center">
            <span className="text-xs text-slate-500 block mb-1">Nodes</span>
            <span className="text-sm font-medium text-slate-200">
              {net.node_count}
            </span>
          </div>
        </div>

        {/* Commitment stats */}
        <div>
          <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">
            Commitments
          </h4>
          <div className="grid grid-cols-4 gap-2">
            {(
              [
                ["Open", net.commitment_stats.open, "text-blue-400"],
                ["Done", net.commitment_stats.completed, "text-green-400"],
                ["Overdue", net.commitment_stats.overdue, "text-red-400"],
                ["Cancelled", net.commitment_stats.cancelled, "text-slate-500"],
              ] as const
            ).map(([label, count, color]) => (
              <div key={label} className="text-center">
                <p className={cn("text-lg font-medium", color)}>{count}</p>
                <p className="text-xs text-slate-500">{label}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Health history */}
        {net.health_history.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">
              Health History
            </h4>
            <div className="space-y-1">
              {net.health_history.slice(0, 10).map((entry, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between text-xs py-1 border-b border-border last:border-0"
                >
                  <span className="text-slate-500">
                    {timeAgo(entry.timestamp)}
                  </span>
                  <span className={healthStatusColor(entry.status)}>
                    {entry.status.replace(/_/g, " ")}
                  </span>
                  <span>{momentumIcon(entry.momentum)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recent nodes */}
        {net.recent_nodes.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">
              Recent Nodes
            </h4>
            <div className="space-y-1">
              {net.recent_nodes.slice(0, 10).map((node) => (
                <div
                  key={node.id}
                  className="flex items-center justify-between text-xs py-1.5 border-b border-border last:border-0"
                >
                  <span className="text-slate-300 truncate max-w-[60%]">
                    {node.title}
                  </span>
                  <span className="text-slate-500">
                    {formatNodeType(node.node_type)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Alerts */}
        {net.alerts.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">
              Active Alerts
            </h4>
            <div className="space-y-2">
              {net.alerts.map((alert) => (
                <div
                  key={alert.id}
                  className="border border-yellow-500/30 bg-yellow-500/5 rounded-lg p-3"
                >
                  <p className="text-xs text-slate-300">{alert.message}</p>
                  <span className="text-xs text-slate-500 mt-1 block">
                    {timeAgo(alert.created_at)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
