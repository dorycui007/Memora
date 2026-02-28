import { useEffect, useState } from "react";
import type { ProposalDetail as ProposalDetailType } from "@/lib/types";
import { proposalsApi } from "@/lib/api";
import { cn, confidenceColor, formatDateTime } from "@/lib/utils";

interface ProposalDetailProps {
  proposalId: string;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  onClose: () => void;
}

const ACTION_STYLES: Record<string, { bg: string; label: string }> = {
  create_node: { bg: "bg-green-500/10 border-green-500/30", label: "Create Node" },
  update_node: { bg: "bg-yellow-500/10 border-yellow-500/30", label: "Update Node" },
  create_edge: { bg: "bg-blue-500/10 border-blue-500/30", label: "Create Edge" },
  update_edge: { bg: "bg-purple-500/10 border-purple-500/30", label: "Update Edge" },
};

export function ProposalDetailView({
  proposalId,
  onApprove,
  onReject,
  onClose,
}: ProposalDetailProps) {
  const [proposal, setProposal] = useState<ProposalDetailType | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    proposalsApi
      .get(proposalId)
      .then(setProposal)
      .finally(() => setLoading(false));
  }, [proposalId]);

  if (loading) {
    return (
      <div className="p-6 text-center text-slate-500">Loading proposal...</div>
    );
  }

  if (!proposal) {
    return (
      <div className="p-6 text-center text-slate-500">Proposal not found</div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h3 className="text-sm font-medium text-slate-200">Proposal Detail</h3>
        <button
          onClick={onClose}
          className="text-slate-500 hover:text-slate-300 text-sm"
        >
          Close
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <div>
          <p className="text-sm text-slate-200 mb-1">
            {proposal.human_summary}
          </p>
          <div className="flex gap-3 text-xs text-slate-500">
            <span className={confidenceColor(proposal.confidence)}>
              Confidence: {Math.round(proposal.confidence * 100)}%
            </span>
            <span>Route: {proposal.route}</span>
            <span>{formatDateTime(proposal.created_at)}</span>
          </div>
        </div>

        <div className="space-y-2">
          <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wider">
            Actions ({proposal.actions.length})
          </h4>
          {proposal.actions.map((action, i) => {
            const style = ACTION_STYLES[action.action] ?? { bg: "bg-slate-500/10 border-slate-500/30", label: "Action" };
            return (
              <div
                key={i}
                className={cn(
                  "border rounded-lg p-3 space-y-1",
                  style.bg
                )}
              >
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-slate-300">
                    {style.label}
                  </span>
                  {action.node_type && (
                    <span className="text-xs text-slate-500">
                      {action.node_type}
                    </span>
                  )}
                  {action.edge_type && (
                    <span className="text-xs text-slate-500">
                      {action.edge_type}
                    </span>
                  )}
                  <span
                    className={cn(
                      "text-xs ml-auto",
                      action.impact === "high"
                        ? "text-red-400"
                        : action.impact === "medium"
                          ? "text-yellow-400"
                          : "text-slate-500"
                    )}
                  >
                    {action.impact} impact
                  </span>
                </div>
                <p className="text-xs text-slate-400">{action.summary}</p>
              </div>
            );
          })}
        </div>
      </div>

      {proposal.status === "pending" && (
        <div className="px-4 py-3 border-t border-border flex gap-2">
          <button
            onClick={() => onApprove(proposal.id)}
            className="flex-1 px-3 py-2 text-sm font-medium rounded bg-green-600 text-white hover:bg-green-500 transition-colors"
          >
            Approve
          </button>
          <button
            onClick={() => onReject(proposal.id)}
            className="flex-1 px-3 py-2 text-sm font-medium rounded bg-red-600/20 text-red-400 hover:bg-red-600/30 transition-colors"
          >
            Reject
          </button>
        </div>
      )}
    </div>
  );
}
