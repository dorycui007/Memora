import type { Notification } from "@/lib/types";
import { cn, priorityColor, timeAgo } from "@/lib/utils";

const TYPE_ICONS: Record<string, string> = {
  deadline: "D",
  relationship: "R",
  commitment: "C",
  health: "H",
  bridge: "B",
  goal: "G",
  review: "S",
};

interface AlertCardProps {
  alert: Notification;
  onDismiss: (id: string) => void;
  onSnooze?: (id: string) => void;
}

export function AlertCard({ alert, onDismiss, onSnooze }: AlertCardProps) {
  return (
    <div className="border border-border rounded-lg p-3 hover:border-slate-500 transition-colors">
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "w-6 h-6 rounded flex items-center justify-center text-xs font-mono shrink-0",
            priorityColor(alert.priority),
            "bg-surface-overlay"
          )}
        >
          {TYPE_ICONS[alert.type] ?? "!"}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-slate-200">{alert.message}</p>
          <span className="text-xs text-slate-500">
            {timeAgo(alert.created_at)}
          </span>
        </div>
      </div>
      <div className="flex gap-2 mt-2 pl-9">
        <button
          onClick={() => onDismiss(alert.id)}
          className="px-2 py-0.5 text-xs rounded text-slate-500 hover:text-slate-300 hover:bg-surface-overlay transition-colors"
        >
          Dismiss
        </button>
        {onSnooze && (
          <button
            onClick={() => onSnooze(alert.id)}
            className="px-2 py-0.5 text-xs rounded text-slate-500 hover:text-slate-300 hover:bg-surface-overlay transition-colors"
          >
            Snooze
          </button>
        )}
      </div>
    </div>
  );
}
