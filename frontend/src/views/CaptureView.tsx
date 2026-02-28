import { useEffect } from "react";
import { CaptureBar } from "@/components/capture";
import { useCaptureStore } from "@/stores/captureStore";
import { timeAgo } from "@/lib/utils";

export function CaptureView() {
  const { recentCaptures, fetchRecent, pendingCaptures } = useCaptureStore();

  useEffect(() => {
    fetchRecent();
  }, [fetchRecent]);

  return (
    <div className="flex flex-col h-full">
      <CaptureBar />
      <div className="flex-1 overflow-y-auto p-4">
        <h2 className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3">
          Recent Captures
        </h2>

        {pendingCaptures.length > 0 && (
          <div className="mb-4 space-y-2">
            {pendingCaptures.map((capture) => (
              <div
                key={capture.id}
                className="border border-blue-500/30 bg-blue-500/5 rounded-lg p-3"
              >
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
                  <span className="text-xs text-blue-400">
                    Processing (stage {capture.pipeline_stage})
                  </span>
                  <span className="text-xs text-slate-500 ml-auto">
                    {timeAgo(capture.created_at)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}

        {recentCaptures.length === 0 && pendingCaptures.length === 0 ? (
          <div className="text-center text-slate-500 py-12">
            <p className="text-lg mb-1">No captures yet</p>
            <p className="text-sm">Start by typing something above</p>
          </div>
        ) : (
          <div className="space-y-2">
            {recentCaptures.map((capture) => (
              <div
                key={capture.id}
                className="border border-border rounded-lg p-3 hover:border-slate-500 transition-colors"
              >
                <p className="text-sm text-slate-300 line-clamp-3">
                  {capture.raw_content}
                </p>
                <div className="flex items-center gap-3 mt-2 text-xs text-slate-500">
                  <span className="capitalize">{capture.modality}</span>
                  {capture.language && <span>{capture.language}</span>}
                  <span className="ml-auto">{timeAgo(capture.created_at)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
