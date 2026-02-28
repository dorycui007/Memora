import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { type NetworkType, type NodeType, HealthStatus, Momentum, Priority } from "./types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const DEFAULT_NETWORK_COLOR = { bg: "bg-slate-500/10", text: "text-slate-400", border: "border-slate-500/30", badge: "bg-slate-700 text-slate-400" };

export const NETWORK_COLORS: Record<string, { bg: string; text: string; border: string; badge: string }> = {
  academic: { bg: "bg-academic/10", text: "text-academic", border: "border-academic/30", badge: "bg-academic/20 text-academic" },
  professional: { bg: "bg-professional/10", text: "text-professional", border: "border-professional/30", badge: "bg-professional/20 text-professional" },
  financial: { bg: "bg-financial/10", text: "text-financial", border: "border-financial/30", badge: "bg-financial/20 text-financial" },
  health: { bg: "bg-health/10", text: "text-health", border: "border-health/30", badge: "bg-health/20 text-health" },
  personal_growth: { bg: "bg-personal-growth/10", text: "text-personal-growth", border: "border-personal-growth/30", badge: "bg-personal-growth/20 text-personal-growth" },
  social: { bg: "bg-social/10", text: "text-social", border: "border-social/30", badge: "bg-social/20 text-social" },
  ventures: { bg: "bg-ventures/10", text: "text-ventures", border: "border-ventures/30", badge: "bg-ventures/20 text-ventures" },
};

export const NODE_TYPE_COLORS: Record<string, string> = {
  event: "#3b82f6",
  person: "#8b5cf6",
  commitment: "#ef4444",
  decision: "#f59e0b",
  goal: "#10b981",
  financial_item: "#06b6d4",
  note: "#6b7280",
  idea: "#ec4899",
  project: "#0ea5e9",
  concept: "#6366f1",
  reference: "#78716c",
  insight: "#d946ef",
};

export const EDGE_CATEGORY_COLORS: Record<string, string> = {
  structural: "#6b7280",
  associative: "#3b82f6",
  provenance: "#78716c",
  temporal: "#f59e0b",
  personal: "#ec4899",
  social: "#8b5cf6",
  network: "#10b981",
};

export function formatNodeType(type: NodeType | string): string {
  return type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatNetworkType(type: NetworkType | string): string {
  return type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatDateTime(dateStr: string): string {
  return new Date(dateStr).toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function timeAgo(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return formatDate(dateStr);
}

export function confidenceColor(confidence: number): string {
  if (confidence >= 0.85) return "text-green-400";
  if (confidence >= 0.6) return "text-yellow-400";
  return "text-red-400";
}

export function healthStatusColor(status: HealthStatus): string {
  switch (status) {
    case HealthStatus.ON_TRACK: return "text-green-400";
    case HealthStatus.NEEDS_ATTENTION: return "text-yellow-400";
    case HealthStatus.FALLING_BEHIND: return "text-red-400";
  }
}

export function momentumIcon(momentum: Momentum): string {
  switch (momentum) {
    case Momentum.UP: return "\u2191";
    case Momentum.STABLE: return "\u2192";
    case Momentum.DOWN: return "\u2193";
  }
}

export function priorityColor(priority: Priority): string {
  switch (priority) {
    case Priority.LOW: return "text-slate-400";
    case Priority.MEDIUM: return "text-blue-400";
    case Priority.HIGH: return "text-yellow-400";
    case Priority.CRITICAL: return "text-red-400";
  }
}

export function getNetworkColor(network: string) {
  return NETWORK_COLORS[network] ?? DEFAULT_NETWORK_COLOR;
}

export function truncate(str: string, maxLen: number): string {
  if (str.length <= maxLen) return str;
  return str.slice(0, maxLen - 3) + "...";
}
