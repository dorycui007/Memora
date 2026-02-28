import { useState } from "react";
import type { AgentOutput } from "@/lib/types";
import { cn, confidenceColor } from "@/lib/utils";

const AGENT_STYLES: Record<string, { label: string; color: string }> = {
  archivist: { label: "Archivist", color: "text-emerald-400" },
  strategist: { label: "Strategist", color: "text-amber-400" },
  researcher: { label: "Researcher", color: "text-sky-400" },
  orchestrator: { label: "Orchestrator", color: "text-violet-400" },
};

interface AgentResponseProps {
  output: AgentOutput;
}

export function AgentResponse({ output }: AgentResponseProps) {
  const [expanded, setExpanded] = useState(false);
  const style = AGENT_STYLES[output.agent] ?? { label: "Agent", color: "text-slate-400" };

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-3 py-2 hover:bg-surface-overlay transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className={cn("text-xs font-medium", style.color)}>
            {style.label}
          </span>
          <span className={cn("text-xs", confidenceColor(output.confidence))}>
            {Math.round(output.confidence * 100)}%
          </span>
        </div>
        <span className="text-xs text-slate-500">
          {expanded ? "Collapse" : "Expand"}
        </span>
      </button>

      {expanded && (
        <div className="px-3 py-2 border-t border-border">
          <p className="text-xs text-slate-300 whitespace-pre-wrap">
            {output.content}
          </p>

          {output.citations.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {output.citations.map((citation, i) => (
                <span
                  key={i}
                  className="px-1.5 py-0.5 text-xs rounded bg-slate-700 text-slate-400 cursor-pointer hover:text-slate-200"
                  title={citation}
                >
                  [{i + 1}]
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
