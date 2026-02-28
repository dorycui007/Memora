import type { AgentRole } from "@/lib/types";
import { cn } from "@/lib/utils";

const AGENT_STYLES: Record<string, { label: string; color: string }> = {
  archivist: { label: "Archivist", color: "text-emerald-400" },
  strategist: { label: "Strategist", color: "text-amber-400" },
  researcher: { label: "Researcher", color: "text-sky-400" },
  orchestrator: { label: "Orchestrator", color: "text-violet-400" },
};

const STATE_LABELS: Record<string, string> = {
  thinking: "thinking...",
  generating: "generating...",
  done: "done",
  error: "error",
};

interface StreamingIndicatorProps {
  agents: Map<AgentRole, "thinking" | "generating" | "done" | "error">;
}

export function StreamingIndicator({ agents }: StreamingIndicatorProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {Array.from(agents.entries()).map(([agent, state]) => {
        const style = AGENT_STYLES[agent] ?? { label: "Agent", color: "text-slate-400" };
        const isActive = state === "thinking" || state === "generating";

        return (
          <div
            key={agent}
            className={cn(
              "flex items-center gap-1.5 px-2 py-1 rounded-full border text-xs",
              isActive
                ? "border-border bg-surface-raised"
                : state === "done"
                  ? "border-green-500/30 bg-green-500/5"
                  : "border-red-500/30 bg-red-500/5"
            )}
          >
            {isActive && (
              <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
            )}
            <span className={style.color}>{style.label}</span>
            <span className="text-slate-500">{STATE_LABELS[state]}</span>
          </div>
        );
      })}
    </div>
  );
}
