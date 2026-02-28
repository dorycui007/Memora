import { useState, useRef, useEffect } from "react";
import { cn } from "@/lib/utils";
import { useNotificationStore } from "@/stores/notificationStore";
import { timeAgo, priorityColor } from "@/lib/utils";

export type ViewKey =
  | "capture"
  | "graph"
  | "networks"
  | "briefing"
  | "review"
  | "council";

const NAV_ITEMS: { key: ViewKey; label: string; shortcut: string }[] = [
  { key: "capture", label: "Capture", shortcut: "C" },
  { key: "graph", label: "Graph", shortcut: "G" },
  { key: "networks", label: "Networks", shortcut: "N" },
  { key: "briefing", label: "Briefing", shortcut: "B" },
  { key: "review", label: "Review", shortcut: "R" },
  { key: "council", label: "Council", shortcut: "Q" },
];

interface LayoutProps {
  activeView: ViewKey;
  onNavigate: (view: ViewKey) => void;
  children: React.ReactNode;
}

export function Layout({ activeView, onNavigate, children }: LayoutProps) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const { notifications, unreadCount, pendingProposalCount, markRead, markAllRead } =
    useNotificationStore();
  const notifRef = useRef<HTMLDivElement>(null);

  // Close notifications on outside click
  useEffect(() => {
    if (!notificationsOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setNotificationsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [notificationsOpen]);

  return (
    <div className="flex h-screen bg-surface">
      {/* Sidebar */}
      <aside
        className={cn(
          "flex flex-col border-r border-border bg-surface-raised transition-all",
          sidebarCollapsed ? "w-14" : "w-48"
        )}
      >
        <div className="px-3 py-4 border-b border-border">
          <button
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            className="flex items-center gap-2 text-slate-200 hover:text-white transition-colors"
            title="Toggle sidebar (Cmd+/)"
          >
            <span className="text-lg font-bold">M</span>
            {!sidebarCollapsed && (
              <span className="text-sm font-semibold">Memora</span>
            )}
          </button>
        </div>

        <nav className="flex-1 px-2 py-3 space-y-1">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.key}
              onClick={() => onNavigate(item.key)}
              className={cn(
                "w-full flex items-center gap-3 px-2 py-2 rounded-lg text-sm transition-colors",
                activeView === item.key
                  ? "bg-blue-500/10 text-blue-400"
                  : "text-slate-400 hover:text-slate-200 hover:bg-surface-overlay"
              )}
            >
              <span className="w-5 text-center font-mono text-xs">
                {item.shortcut}
              </span>
              {!sidebarCollapsed && <span>{item.label}</span>}
              {!sidebarCollapsed && item.key === "review" && pendingProposalCount > 0 && (
                <span className="ml-auto px-1.5 py-0.5 text-xs rounded-full bg-yellow-500/20 text-yellow-400">
                  {pendingProposalCount}
                </span>
              )}
            </button>
          ))}
        </nav>

        {!sidebarCollapsed && (
          <div className="px-3 py-3 border-t border-border">
            <p className="text-[10px] text-slate-600 text-center">
              Cmd+K for commands
            </p>
          </div>
        )}
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="h-10 flex items-center justify-between px-4 border-b border-border bg-surface-raised">
          <span className="text-xs text-slate-500 uppercase tracking-wider">
            {NAV_ITEMS.find((n) => n.key === activeView)?.label}
          </span>
          <div className="flex items-center gap-3">
            {/* Notifications */}
            <div className="relative" ref={notifRef}>
              <button
                onClick={() => setNotificationsOpen(!notificationsOpen)}
                className="relative text-slate-400 hover:text-slate-200 text-sm"
                title="Notifications"
              >
                N
                {unreadCount > 0 && (
                  <span className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-red-500 text-white text-[8px] flex items-center justify-center">
                    {unreadCount > 9 ? "9+" : unreadCount}
                  </span>
                )}
              </button>

              {notificationsOpen && (
                <div className="absolute right-0 top-8 w-80 bg-surface-raised border border-border rounded-lg shadow-xl z-50 overflow-hidden">
                  <div className="flex items-center justify-between px-3 py-2 border-b border-border">
                    <span className="text-xs text-slate-400 font-medium">
                      Notifications ({unreadCount} unread)
                    </span>
                    {unreadCount > 0 && (
                      <button
                        onClick={() => markAllRead()}
                        className="text-[10px] text-blue-400 hover:text-blue-300"
                      >
                        Mark all read
                      </button>
                    )}
                  </div>
                  <div className="max-h-64 overflow-y-auto">
                    {notifications.length === 0 ? (
                      <div className="px-3 py-6 text-center text-xs text-slate-600">
                        No notifications yet
                      </div>
                    ) : (
                      notifications.slice(0, 20).map((notif) => (
                        <button
                          key={notif.id}
                          onClick={() => markRead(notif.id)}
                          className={cn(
                            "w-full px-3 py-2 text-left hover:bg-surface-overlay transition-colors border-b border-border/50",
                            !notif.read && "bg-blue-500/5"
                          )}
                        >
                          <div className="flex items-start gap-2">
                            {!notif.read && (
                              <div className="w-1.5 h-1.5 rounded-full bg-blue-400 mt-1.5 shrink-0" />
                            )}
                            <div className="min-w-0">
                              <p className="text-xs text-slate-300 truncate">
                                {notif.message}
                              </p>
                              <div className="flex gap-2 mt-0.5">
                                <span className={cn("text-[10px]", priorityColor(notif.priority))}>
                                  {notif.type}
                                </span>
                                <span className="text-[10px] text-slate-600">
                                  {timeAgo(notif.created_at)}
                                </span>
                              </div>
                            </div>
                          </div>
                        </button>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Command Palette trigger */}
            <button
              className="text-slate-400 hover:text-slate-200 text-xs font-mono px-1.5 py-0.5 rounded border border-border hover:border-slate-600 transition-colors"
              title="Command Palette (Cmd+K)"
            >
              Cmd+K
            </button>
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-hidden">{children}</main>
      </div>
    </div>
  );
}
