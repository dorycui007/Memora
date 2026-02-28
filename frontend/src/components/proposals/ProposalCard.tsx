import type { ProposalResponse } from "@/lib/types";
import { cn, confidenceColor, timeAgo } from "@/lib/utils";
import { ProposalRoute } from "@/lib/types";

interface ProposalCardProps {
  proposal: ProposalResponse;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  onSelect: (id: string) => void;
}

const ROUTE_LABELS: Record<string, { label: string; color: string }> = {
  auto: { label: "Auto", color: "bg-green-500/20 text-green-400" },
  digest: { label: "Digest", color: "bg-yellow-500/20 text-yellow-400" },
  explicit: { label: "Review", color: "bg-red-500/20 text-red-400" },
};

export function ProposalCard({ proposal, onApprove, onReject, onSelect }: ProposalCardProps) {
  const route = ROUTE_LABELS[proposal.route] ?? { label: "Review", color: "bg-red-500/20 text-red-400" };

  return (
    <div
      className="border border-border rounded-lg p-4 hover:border-slate-500 transition-colors cursor-pointer"
      onClick={() => onSelect(proposal.id)}
    >
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-slate-200 line-clamp-2">
            {proposal.human_summary || "Pending proposal"}
          </p>
        </div>
        <span className={cn("px-2 py-0.5 text-xs rounded-full shrink-0", route.color)}>
          {route.label}
        </span>
      </div>

      <div className="flex items-center gap-3 text-xs text-slate-500 mb-3">
        <span className={confidenceColor(proposal.confidence)}>
          {Math.round(proposal.confidence * 100)}%
        </span>
        <span>{proposal.action_count} action{proposal.action_count !== 1 ? "s" : ""}</span>
        <span>{timeAgo(proposal.created_at)}</span>
      </div>

      {proposal.route !== ProposalRoute.AUTO && (
        <div className="flex gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onApprove(proposal.id);
            }}
            className="px-3 py-1 text-xs font-medium rounded bg-green-600/20 text-green-400 hover:bg-green-600/30 transition-colors"
          >
            Approve
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onReject(proposal.id);
            }}
            className="px-3 py-1 text-xs font-medium rounded bg-red-600/20 text-red-400 hover:bg-red-600/30 transition-colors"
          >
            Reject
          </button>
        </div>
      )}
    </div>
  );
}
