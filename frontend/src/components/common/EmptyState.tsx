import { cn } from "@/lib/utils";

interface EmptyStateProps {
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

export function EmptyState({ title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn("flex flex-col items-center justify-center py-12 px-4", className)}>
      <div className="w-12 h-12 rounded-full bg-slate-800 flex items-center justify-center mb-3">
        <span className="text-slate-600 text-lg">--</span>
      </div>
      <p className="text-sm text-slate-400 mb-1">{title}</p>
      {description && (
        <p className="text-xs text-slate-600 text-center max-w-xs">{description}</p>
      )}
      {action && (
        <button
          onClick={action.onClick}
          className="mt-3 px-3 py-1.5 text-xs bg-blue-500/20 text-blue-400 rounded hover:bg-blue-500/30 transition-colors"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
