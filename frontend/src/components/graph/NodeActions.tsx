import { useState, memo } from "react";
import { graphApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { GraphNode } from "@/lib/types";

interface NodeActionsProps {
  node: GraphNode;
  onDelete: () => void;
  onUpdate: (updates: Record<string, unknown>) => void;
}

const QUALITY_LABELS = [
  { value: 0, label: "Complete blackout", color: "bg-red-500" },
  { value: 1, label: "Incorrect, remembered something", color: "bg-red-400" },
  { value: 2, label: "Incorrect, easy to recall", color: "bg-orange-400" },
  { value: 3, label: "Correct, significant difficulty", color: "bg-yellow-400" },
  { value: 4, label: "Correct, some hesitation", color: "bg-green-400" },
  { value: 5, label: "Perfect response", color: "bg-green-500" },
];

export const NodeActions = memo(function NodeActions({
  node,
  onDelete,
  onUpdate,
}: NodeActionsProps) {
  const [isReviewing, setIsReviewing] = useState(false);
  const [reviewSubmitted, setReviewSubmitted] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const handleReview = async (quality: number) => {
    setIsReviewing(true);
    try {
      await graphApi.submitReview(node.id, quality);
      setReviewSubmitted(true);
    } catch {
      // Error handled silently
    } finally {
      setIsReviewing(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* SM-2 Review */}
      <div>
        <h4 className="text-xs text-slate-500 uppercase tracking-wider mb-2">
          Spaced Repetition Review
        </h4>
        {reviewSubmitted ? (
          <div className="px-3 py-2 bg-green-500/10 border border-green-500/20 rounded text-xs text-green-400">
            Review submitted. Next review date updated.
          </div>
        ) : (
          <div className="space-y-1">
            <p className="text-xs text-slate-400 mb-2">
              How well do you recall this knowledge?
            </p>
            {QUALITY_LABELS.map(({ value, label, color }) => (
              <button
                key={value}
                onClick={() => handleReview(value)}
                disabled={isReviewing}
                className={cn(
                  "w-full flex items-center gap-2 px-2 py-1.5 rounded text-xs text-left transition-colors",
                  "hover:bg-surface-overlay disabled:opacity-50"
                )}
              >
                <div className={cn("w-2 h-2 rounded-full shrink-0", color)} />
                <span className="text-slate-400">
                  <span className="text-slate-500 font-mono mr-1">{value}</span>
                  {label}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Edit Actions */}
      <div>
        <h4 className="text-xs text-slate-500 uppercase tracking-wider mb-2">
          Node Actions
        </h4>
        <div className="space-y-1">
          {!node.human_approved && (
            <button
              onClick={() => onUpdate({ human_approved: true })}
              className="w-full px-3 py-2 text-xs text-left rounded bg-green-500/10 text-green-400 hover:bg-green-500/20 transition-colors"
            >
              Mark as Reviewed
            </button>
          )}

          {confirmDelete ? (
            <div className="flex gap-1">
              <button
                onClick={onDelete}
                className="flex-1 px-3 py-2 text-xs rounded bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors"
              >
                Confirm Delete
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                className="flex-1 px-3 py-2 text-xs rounded bg-slate-700 text-slate-400 hover:bg-slate-600 transition-colors"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmDelete(true)}
              className="w-full px-3 py-2 text-xs text-left rounded text-red-400 hover:bg-red-500/10 transition-colors"
            >
              Delete Node
            </button>
          )}
        </div>
      </div>
    </div>
  );
});
