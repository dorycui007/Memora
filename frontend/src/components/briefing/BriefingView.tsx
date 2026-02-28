import { useEffect, useState } from "react";
import { useCouncilStore } from "@/stores/councilStore";
import { useNetworkStore } from "@/stores/networkStore";
import { AlertCard } from "./AlertCard";
import { BridgeCard } from "./BridgeCard";
import { cn, formatDateTime } from "@/lib/utils";
import type { Notification } from "@/lib/types";

const SECTION_ICONS: Record<string, string> = {
  "Network Status": "N",
  "Open Alerts": "!",
  "Cross-Network Bridges": "B",
  "Decision Prompts": "?",
  "Recommended Actions": "A",
  "Spaced Repetition": "S",
};

export function BriefingView() {
  const { currentBriefing, fetchBriefing } = useCouncilStore();
  const { bridges, fetchBridges } = useNetworkStore();
  const [collapsedSections, setCollapsedSections] = useState<Set<string>>(
    new Set()
  );
  const [readSections, setReadSections] = useState<Set<string>>(new Set());

  useEffect(() => {
    fetchBriefing();
    fetchBridges({ limit: 10 });
  }, [fetchBriefing, fetchBridges]);

  const toggleSection = (title: string) => {
    const next = new Set(collapsedSections);
    if (next.has(title)) next.delete(title);
    else next.add(title);
    setCollapsedSections(next);
  };

  const markRead = (title: string) => {
    setReadSections((prev) => new Set(prev).add(title));
  };

  if (!currentBriefing) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500">
        <div className="text-center">
          <p className="text-lg mb-1">Loading briefing...</p>
          <p className="text-sm">Your daily intelligence report</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto p-6 space-y-6">
        {/* Header */}
        <div className="border-b border-border pb-4">
          <h2 className="text-lg font-semibold text-slate-200">
            Daily Briefing
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Generated {formatDateTime(currentBriefing.generated_at)}
            {currentBriefing.cached && " (cached)"}
          </p>
          {currentBriefing.summary && (
            <p className="text-sm text-slate-400 mt-2">
              {currentBriefing.summary}
            </p>
          )}
        </div>

        {/* Sections */}
        {currentBriefing.sections.map((section) => {
          const isCollapsed = collapsedSections.has(section.title);
          const isRead = readSections.has(section.title);

          return (
            <div
              key={section.title}
              className={cn(
                "border border-border rounded-lg overflow-hidden",
                isRead && "opacity-60"
              )}
            >
              <button
                onClick={() => toggleSection(section.title)}
                className="w-full flex items-center justify-between px-4 py-3 hover:bg-surface-overlay transition-colors"
              >
                <div className="flex items-center gap-2">
                  <span className="w-5 h-5 rounded bg-surface-overlay flex items-center justify-center text-xs text-slate-400 font-mono">
                    {SECTION_ICONS[section.title] ?? "#"}
                  </span>
                  <h3 className="text-sm font-medium text-slate-200">
                    {section.title}
                  </h3>
                  <span
                    className={cn(
                      "px-1.5 py-0.5 text-xs rounded",
                      section.priority === "high"
                        ? "bg-red-500/20 text-red-400"
                        : section.priority === "medium"
                          ? "bg-yellow-500/20 text-yellow-400"
                          : "bg-slate-700 text-slate-400"
                    )}
                  >
                    {section.items.length}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  {!isRead && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        markRead(section.title);
                      }}
                      className="text-xs text-slate-500 hover:text-slate-300"
                    >
                      Mark read
                    </button>
                  )}
                  <span className="text-xs text-slate-500">
                    {isCollapsed ? "+" : "-"}
                  </span>
                </div>
              </button>

              {!isCollapsed && (
                <div className="px-4 pb-4 space-y-2">
                  {section.title === "Open Alerts" ? (
                    section.items.map((item, i) => (
                      <AlertCard
                        key={i}
                        alert={item as unknown as Notification}
                        onDismiss={() => {}}
                      />
                    ))
                  ) : section.title === "Cross-Network Bridges" ? (
                    bridges.length > 0 ? (
                      bridges.map((bridge) => (
                        <BridgeCard key={bridge.id} bridge={bridge} />
                      ))
                    ) : (
                      <p className="text-xs text-slate-500">
                        No new bridges discovered
                      </p>
                    )
                  ) : (
                    section.items.map((item, i) => (
                      <div
                        key={i}
                        className="border border-border rounded-lg p-3 text-xs text-slate-300"
                      >
                        {typeof item === "object" && item !== null ? (
                          <pre className="whitespace-pre-wrap">
                            {JSON.stringify(item, null, 2)}
                          </pre>
                        ) : (
                          String(item)
                        )}
                      </div>
                    ))
                  )}
                  {section.items.length === 0 && (
                    <p className="text-xs text-slate-500">Nothing to report</p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
