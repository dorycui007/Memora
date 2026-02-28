import { useMemo, memo } from "react";
import { formatDateTime, timeAgo } from "@/lib/utils";
import type { GraphNode, GraphEdge } from "@/lib/types";

interface TimelineEvent {
  date: string;
  type: "created" | "updated" | "accessed" | "review" | "edge_added";
  label: string;
}

interface NodeTimelineProps {
  node: GraphNode;
  edges: GraphEdge[];
}

export const NodeTimeline = memo(function NodeTimeline({ node, edges }: NodeTimelineProps) {
  const events = useMemo(() => {
    const ev: TimelineEvent[] = [];

    ev.push({ date: node.created_at, type: "created", label: "Node created" });

    if (node.updated_at !== node.created_at) {
      ev.push({ date: node.updated_at, type: "updated", label: "Node updated" });
    }

    if (node.last_accessed) {
      ev.push({ date: node.last_accessed, type: "accessed", label: "Last accessed" });
    }

    if (node.review_date) {
      ev.push({ date: node.review_date, type: "review", label: "Scheduled review" });
    }

    for (const edge of edges) {
      ev.push({
        date: edge.created_at,
        type: "edge_added",
        label: `Edge: ${edge.edge_type.replace(/_/g, " ")}`,
      });
    }

    ev.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
    return ev;
  }, [node, edges]);

  if (events.length === 0) {
    return (
      <div className="text-center py-8 text-sm text-slate-500">
        No timeline events
      </div>
    );
  }

  const typeColor = (type: TimelineEvent["type"]) => {
    switch (type) {
      case "created": return "bg-green-400";
      case "updated": return "bg-blue-400";
      case "accessed": return "bg-slate-400";
      case "review": return "bg-yellow-400";
      case "edge_added": return "bg-purple-400";
    }
  };

  return (
    <div className="relative">
      <div className="absolute left-[7px] top-2 bottom-2 w-px bg-slate-700" />
      <div className="space-y-3">
        {events.map((event, i) => (
          <div key={`${event.type}-${i}`} className="flex gap-3 relative">
            <div className={`w-[15px] h-[15px] rounded-full ${typeColor(event.type)} shrink-0 mt-0.5 border-2 border-surface-raised z-10`} />
            <div className="min-w-0">
              <p className="text-xs text-slate-300">{event.label}</p>
              <p className="text-[10px] text-slate-600" title={formatDateTime(event.date)}>
                {timeAgo(event.date)}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
});
