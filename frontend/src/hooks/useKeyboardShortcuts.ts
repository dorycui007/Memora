import { useEffect, useCallback } from "react";
import type { ViewKey } from "@/components/common";

interface UseKeyboardShortcutsOptions {
  onNavigate: (view: ViewKey) => void;
  onToggleCommandPalette: () => void;
  onToggleSidebar?: () => void;
}

export function useKeyboardShortcuts({
  onNavigate,
  onToggleCommandPalette,
  onToggleSidebar,
}: UseKeyboardShortcutsOptions) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const isInput =
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable;

      // Cmd/Ctrl shortcuts always fire
      if (e.metaKey || e.ctrlKey) {
        switch (e.key.toLowerCase()) {
          case "k":
            e.preventDefault();
            onToggleCommandPalette();
            return;
          case "n":
            e.preventDefault();
            onNavigate("capture");
            return;
          case "b":
            e.preventDefault();
            onNavigate("briefing");
            return;
          case "/":
            e.preventDefault();
            onToggleSidebar?.();
            return;
        }
      }

      // Single-key shortcuts only when not in an input
      if (isInput) return;

      switch (e.key.toLowerCase()) {
        case "escape":
          // Handled by individual components
          break;
        case "c":
          onNavigate("capture");
          break;
        case "g":
          onNavigate("graph");
          break;
        case "n":
          onNavigate("networks");
          break;
        case "b":
          onNavigate("briefing");
          break;
        case "r":
          onNavigate("review");
          break;
        case "q":
          onNavigate("council");
          break;
      }
    },
    [onNavigate, onToggleCommandPalette, onToggleSidebar]
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);
}
