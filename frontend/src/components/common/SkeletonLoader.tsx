import { cn } from "@/lib/utils";

interface SkeletonLoaderProps {
  variant?: "line" | "card" | "circle" | "block";
  count?: number;
  className?: string;
}

function SkeletonLine({ className }: { className?: string }) {
  return (
    <div className={cn("h-3 bg-slate-800/60 rounded animate-pulse", className)} />
  );
}

function SkeletonCard() {
  return (
    <div className="p-4 bg-surface-raised border border-border rounded-lg animate-pulse">
      <SkeletonLine className="w-2/3 mb-3" />
      <SkeletonLine className="w-full mb-2" />
      <SkeletonLine className="w-4/5 mb-3" />
      <div className="flex gap-2">
        <SkeletonLine className="w-16 h-5" />
        <SkeletonLine className="w-12 h-5" />
      </div>
    </div>
  );
}

function SkeletonCircle({ className }: { className?: string }) {
  return (
    <div className={cn("w-10 h-10 bg-slate-800/60 rounded-full animate-pulse", className)} />
  );
}

function SkeletonBlock({ className }: { className?: string }) {
  return (
    <div className={cn("h-24 bg-slate-800/60 rounded-lg animate-pulse", className)} />
  );
}

export function SkeletonLoader({ variant = "line", count = 1, className }: SkeletonLoaderProps) {
  const items = Array.from({ length: count }, (_, i) => i);

  return (
    <div className={cn("space-y-3", className)}>
      {items.map((i) => {
        switch (variant) {
          case "card":
            return <SkeletonCard key={i} />;
          case "circle":
            return <SkeletonCircle key={i} />;
          case "block":
            return <SkeletonBlock key={i} />;
          default:
            return <SkeletonLine key={i} />;
        }
      })}
    </div>
  );
}
