import { create } from "zustand";
import type { Notification, ProposalResponse } from "@/lib/types";
import { proposalsApi } from "@/lib/api";

interface NotificationState {
  notifications: Notification[];
  pendingProposalCount: number;
  unreadCount: number;
  isLoading: boolean;

  addNotification: (notification: Notification) => void;
  markRead: (notificationId: string) => void;
  markAllRead: () => void;
  dismissNotification: (notificationId: string) => void;
  fetchPendingProposals: () => Promise<ProposalResponse[]>;
  setNotifications: (notifications: Notification[]) => void;
}

export const useNotificationStore = create<NotificationState>((set, get) => ({
  notifications: [],
  pendingProposalCount: 0,
  unreadCount: 0,
  isLoading: false,

  addNotification: (notification) => {
    set({
      notifications: [notification, ...get().notifications],
      unreadCount: get().unreadCount + 1,
    });
  },

  markRead: (notificationId) => {
    const notifications = get().notifications.map((n) =>
      n.id === notificationId ? { ...n, read: true } : n
    );
    set({
      notifications,
      unreadCount: notifications.filter((n) => !n.read).length,
    });
  },

  markAllRead: () => {
    set({
      notifications: get().notifications.map((n) => ({ ...n, read: true })),
      unreadCount: 0,
    });
  },

  dismissNotification: (notificationId) => {
    const notifications = get().notifications.filter((n) => n.id !== notificationId);
    set({
      notifications,
      unreadCount: notifications.filter((n) => !n.read).length,
    });
  },

  fetchPendingProposals: async () => {
    set({ isLoading: true });
    try {
      const proposals = await proposalsApi.list({ status: "pending" });
      set({ pendingProposalCount: proposals.length, isLoading: false });
      return proposals;
    } catch {
      set({ isLoading: false });
      return [];
    }
  },

  setNotifications: (notifications) =>
    set({
      notifications,
      unreadCount: notifications.filter((n) => !n.read).length,
    }),
}));
