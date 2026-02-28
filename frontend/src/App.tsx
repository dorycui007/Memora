import { useState, useEffect, useCallback } from "react";
import { Layout, type ViewKey, CommandPalette, ConnectionStatus } from "@/components/common";
import { CaptureView } from "@/views/CaptureView";
import { GraphView } from "@/views/GraphView";
import { ReviewView } from "@/views/ReviewView";
import { NetworkDashboardView } from "@/views/NetworkDashboardView";
import { CouncilView } from "@/views/CouncilView";
import { BriefingPageView } from "@/views/BriefingPageView";
import { useNotificationStore } from "@/stores/notificationStore";
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";
import { sseManager } from "@/lib/api";
import { flushQueue } from "@/lib/offlineQueue";
import { Priority } from "@/lib/types";

function App() {
  const [activeView, setActiveView] = useState<ViewKey>("capture");
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const { fetchPendingProposals, addNotification } = useNotificationStore();

  useEffect(() => {
    fetchPendingProposals();

    sseManager.connect();

    sseManager.on("proposal_created", () => {
      fetchPendingProposals();
      addNotification({
        id: crypto.randomUUID(),
        type: "proposal",
        trigger_condition: "proposal_created",
        message: "New proposal awaiting review",
        related_node_ids: [],
        priority: Priority.MEDIUM,
        created_at: new Date().toISOString(),
        read: false,
      });
    });

    sseManager.on("health_changed", (data) => {
      addNotification({
        id: crypto.randomUUID(),
        type: "health",
        trigger_condition: "health_changed",
        message: `Network health changed: ${(data.network as string) ?? "unknown"}`,
        related_node_ids: [],
        priority: Priority.MEDIUM,
        created_at: new Date().toISOString(),
        read: false,
      });
    });

    sseManager.on("bridge_discovered", (data) => {
      addNotification({
        id: crypto.randomUUID(),
        type: "bridge",
        trigger_condition: "bridge_discovered",
        message: `New cross-network bridge discovered`,
        related_node_ids: (data.node_ids as string[]) ?? [],
        priority: Priority.LOW,
        created_at: new Date().toISOString(),
        read: false,
      });
    });

    sseManager.on("briefing_ready", () => {
      addNotification({
        id: crypto.randomUUID(),
        type: "briefing",
        trigger_condition: "briefing_ready",
        message: "Your daily briefing is ready",
        related_node_ids: [],
        priority: Priority.LOW,
        created_at: new Date().toISOString(),
        read: false,
      });
    });

    // Flush any offline captures on reconnect
    flushQueue().catch(() => {});

    return () => sseManager.disconnect();
  }, [fetchPendingProposals, addNotification]);

  const handleNavigate = useCallback((view: ViewKey) => {
    setActiveView(view);
  }, []);

  const handleToggleCommandPalette = useCallback(() => {
    setCommandPaletteOpen((prev) => !prev);
  }, []);

  const handleCommandPaletteNavigate = useCallback(
    (view: string) => {
      setActiveView(view as ViewKey);
      setCommandPaletteOpen(false);
    },
    []
  );

  useKeyboardShortcuts({
    onNavigate: handleNavigate,
    onToggleCommandPalette: handleToggleCommandPalette,
  });

  const renderView = () => {
    switch (activeView) {
      case "capture":
        return <CaptureView />;
      case "graph":
        return <GraphView />;
      case "review":
        return <ReviewView />;
      case "networks":
        return <NetworkDashboardView />;
      case "council":
        return <CouncilView />;
      case "briefing":
        return <BriefingPageView />;
    }
  };

  return (
    <>
      <Layout activeView={activeView} onNavigate={handleNavigate}>
        {renderView()}
      </Layout>
      <CommandPalette
        open={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
        onNavigate={handleCommandPaletteNavigate}
      />
      <ConnectionStatus />
    </>
  );
}

export default App;
