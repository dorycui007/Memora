import { useEffect, useState } from "react";
import type { ProposalResponse } from "@/lib/types";
import { proposalsApi } from "@/lib/api";
import { ProposalCard } from "./ProposalCard";
import { ProposalDetailView } from "./ProposalDetail";

type FilterRoute = "all" | "auto" | "digest" | "explicit";
type SortBy = "confidence" | "date" | "impact";

export function ReviewQueue() {
  const [proposals, setProposals] = useState<ProposalResponse[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filterRoute, setFilterRoute] = useState<FilterRoute>("all");
  const [sortBy, setSortBy] = useState<SortBy>("date");
  const [loading, setLoading] = useState(true);

  const fetchProposals = async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = { status: "pending" };
      if (filterRoute !== "all") params.route = filterRoute;
      const data = await proposalsApi.list(params);
      setProposals(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProposals();
  }, [filterRoute]);

  const handleApprove = async (id: string) => {
    await proposalsApi.approve(id);
    setProposals((prev) => prev.filter((p) => p.id !== id));
    if (selectedId === id) setSelectedId(null);
  };

  const handleReject = async (id: string) => {
    await proposalsApi.reject(id);
    setProposals((prev) => prev.filter((p) => p.id !== id));
    if (selectedId === id) setSelectedId(null);
  };

  const handleBatchApprove = async () => {
    const autoProposals = proposals.filter((p) => p.route === "auto");
    await Promise.all(autoProposals.map((p) => proposalsApi.approve(p.id)));
    fetchProposals();
  };

  const sorted = [...proposals].sort((a, b) => {
    if (sortBy === "confidence") return b.confidence - a.confidence;
    if (sortBy === "impact") return b.action_count - a.action_count;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });

  return (
    <div className="flex h-full">
      <div className="flex-1 flex flex-col border-r border-border">
        <div className="px-4 py-3 border-b border-border">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-medium text-slate-200">
              Review Queue ({proposals.length})
            </h2>
            {proposals.some((p) => p.route === "auto") && (
              <button
                onClick={handleBatchApprove}
                className="px-2 py-1 text-xs rounded bg-green-600/20 text-green-400 hover:bg-green-600/30"
              >
                Approve All Auto
              </button>
            )}
          </div>
          <div className="flex gap-2">
            <div className="flex gap-1">
              {(["all", "auto", "digest", "explicit"] as FilterRoute[]).map((r) => (
                <button
                  key={r}
                  onClick={() => setFilterRoute(r)}
                  className={`px-2 py-0.5 text-xs rounded transition-colors ${
                    filterRoute === r
                      ? "bg-blue-500/20 text-blue-400"
                      : "text-slate-500 hover:text-slate-300"
                  }`}
                >
                  {r === "all" ? "All" : r.charAt(0).toUpperCase() + r.slice(1)}
                </button>
              ))}
            </div>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortBy)}
              className="ml-auto text-xs bg-surface border border-border rounded px-2 py-0.5 text-slate-400"
            >
              <option value="date">Newest</option>
              <option value="confidence">Confidence</option>
              <option value="impact">Impact</option>
            </select>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {loading ? (
            <div className="text-center text-slate-500 py-8">Loading...</div>
          ) : sorted.length === 0 ? (
            <div className="text-center text-slate-500 py-8">
              No pending proposals
            </div>
          ) : (
            sorted.map((proposal) => (
              <ProposalCard
                key={proposal.id}
                proposal={proposal}
                onApprove={handleApprove}
                onReject={handleReject}
                onSelect={setSelectedId}
              />
            ))
          )}
        </div>
      </div>

      {selectedId && (
        <div className="w-96 border-l border-border">
          <ProposalDetailView
            proposalId={selectedId}
            onApprove={handleApprove}
            onReject={handleReject}
            onClose={() => setSelectedId(null)}
          />
        </div>
      )}
    </div>
  );
}
