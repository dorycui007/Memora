import type { Bridge } from "@/lib/types";
import { cn, formatNetworkType, getNetworkColor } from "@/lib/utils";

interface BridgeCardProps {
  bridge: Bridge;
  onConfirm?: (id: string) => void;
  onDismiss?: (id: string) => void;
}

export function BridgeCard({ bridge, onConfirm, onDismiss }: BridgeCardProps) {
  const sourceColors = getNetworkColor(bridge.source_network);
  const targetColors = getNetworkColor(bridge.target_network);

  return (
    <div className="border border-border rounded-lg p-3 hover:border-slate-500 transition-colors">
      <div className="flex items-center gap-2 mb-2">
        <span
          className={cn(
            "px-1.5 py-0.5 text-xs rounded",
            sourceColors.badge
          )}
        >
          {formatNetworkType(bridge.source_network)}
        </span>
        <span className="text-slate-500 text-xs">&harr;</span>
        <span
          className={cn(
            "px-1.5 py-0.5 text-xs rounded",
            targetColors.badge
          )}
        >
          {formatNetworkType(bridge.target_network)}
        </span>
        <span className="ml-auto text-xs text-slate-500">
          {Math.round(bridge.similarity_score * 100)}% similar
        </span>
      </div>

      {bridge.description && (
        <p className="text-xs text-slate-400 mb-2">{bridge.description}</p>
      )}

      {(onConfirm || onDismiss) && !bridge.validated && (
        <div className="flex gap-2">
          {onConfirm && (
            <button
              onClick={() => onConfirm(bridge.id)}
              className="px-2 py-0.5 text-xs rounded bg-green-600/20 text-green-400 hover:bg-green-600/30 transition-colors"
            >
              Confirm
            </button>
          )}
          {onDismiss && (
            <button
              onClick={() => onDismiss(bridge.id)}
              className="px-2 py-0.5 text-xs rounded text-slate-500 hover:text-slate-300 hover:bg-surface-overlay transition-colors"
            >
              Dismiss
            </button>
          )}
        </div>
      )}
    </div>
  );
}
