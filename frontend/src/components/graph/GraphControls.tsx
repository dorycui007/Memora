import { useSigma } from "@react-sigma/core";
import { useGraphStore } from "@/stores/graphStore";
import { cn } from "@/lib/utils";

const VIEW_MODES = [
  { key: "local" as const, label: "Local" },
  { key: "network" as const, label: "Network" },
  { key: "global" as const, label: "Global" },
];

export function GraphControls() {
  const sigma = useSigma();
  const { viewMode, setViewMode } = useGraphStore();

  const handleZoomIn = () => {
    const camera = sigma.getCamera();
    camera.animate({ ratio: camera.getState().ratio / 1.5 }, { duration: 200 });
  };

  const handleZoomOut = () => {
    const camera = sigma.getCamera();
    camera.animate({ ratio: camera.getState().ratio * 1.5 }, { duration: 200 });
  };

  const handleReset = () => {
    const camera = sigma.getCamera();
    camera.animate({ x: 0.5, y: 0.5, ratio: 1 }, { duration: 300 });
  };

  return (
    <div className="absolute top-3 right-3 flex flex-col gap-2">
      <div className="bg-surface-raised border border-border rounded-lg shadow-lg overflow-hidden">
        <button
          onClick={handleZoomIn}
          className="block w-8 h-8 text-slate-400 hover:text-slate-200 hover:bg-surface-overlay transition-colors text-sm"
          title="Zoom in"
        >
          +
        </button>
        <div className="border-t border-border" />
        <button
          onClick={handleZoomOut}
          className="block w-8 h-8 text-slate-400 hover:text-slate-200 hover:bg-surface-overlay transition-colors text-sm"
          title="Zoom out"
        >
          -
        </button>
        <div className="border-t border-border" />
        <button
          onClick={handleReset}
          className="block w-8 h-8 text-slate-400 hover:text-slate-200 hover:bg-surface-overlay transition-colors text-xs"
          title="Reset view"
        >
          R
        </button>
      </div>

      <div className="bg-surface-raised border border-border rounded-lg shadow-lg p-1">
        {VIEW_MODES.map((mode) => (
          <button
            key={mode.key}
            onClick={() => setViewMode(mode.key)}
            className={cn(
              "block w-full px-2 py-1 text-xs rounded transition-colors text-left",
              viewMode === mode.key
                ? "bg-blue-500/20 text-blue-400"
                : "text-slate-500 hover:text-slate-300"
            )}
          >
            {mode.label}
          </button>
        ))}
      </div>
    </div>
  );
}
