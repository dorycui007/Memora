import { useCallback } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useCaptureStore } from "@/stores/captureStore";
import { cn } from "@/lib/utils";

export function CaptureBar() {
  const { createCapture, isCapturing, pendingCaptures } =
    useCaptureStore();

  const editor = useEditor({
    extensions: [StarterKit],
    editorProps: {
      attributes: {
        class:
          "prose prose-invert prose-sm max-w-none focus:outline-none min-h-[60px] px-3 py-2",
      },
      handleKeyDown: (_view, event) => {
        if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
          handleSubmit();
          return true;
        }
        return false;
      },
    },
  });

  const handleSubmit = useCallback(async () => {
    if (!editor || isCapturing) return;
    const content = editor.getText().trim();
    if (!content) return;

    await createCapture(content);
    editor.commands.clearContent();
  }, [editor, isCapturing, createCapture]);

  return (
    <div className="border-b border-border bg-surface-raised">
      <div className="px-4 py-3">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
            Capture
          </span>
          {pendingCaptures.length > 0 && (
            <span className="ml-auto text-xs text-slate-500">
              {pendingCaptures.length} processing
            </span>
          )}
        </div>

        <div className="rounded-lg border border-border bg-surface overflow-hidden">
          <EditorContent editor={editor} />
          <div className="flex items-center justify-between px-3 py-1.5 border-t border-border">
            <span className="text-xs text-slate-500">
              {isCapturing ? "Processing..." : "Cmd+Enter to submit"}
            </span>
            <button
              onClick={handleSubmit}
              disabled={isCapturing}
              className={cn(
                "px-3 py-1 text-xs font-medium rounded transition-colors",
                isCapturing
                  ? "bg-slate-700 text-slate-500 cursor-not-allowed"
                  : "bg-blue-600 text-white hover:bg-blue-500"
              )}
            >
              {isCapturing ? "Sending..." : "Capture"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
