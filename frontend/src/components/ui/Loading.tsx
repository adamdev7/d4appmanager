import type { HTMLAttributes, ReactNode } from "react";
import { RefreshCw } from "lucide-react";
import { cn } from "@/lib/cn";
import { Badge } from "@/components/ui/Badge";

/** Inline border spinner — matches Button / auth gate style. */
export function Spinner({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={cn(
        "inline-block h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent",
        className
      )}
      {...props}
    />
  );
}

/** Pulse placeholder block. */
export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-xl bg-surface-muted/70 border border-border/60", className)}
      {...props}
    />
  );
}

/** Compact “Updating” chip for header toolbars. */
export function UpdatingBadge({ label = "Updating" }: { label?: string }) {
  return (
    <Badge variant="muted" className="inline-flex items-center gap-1.5">
      <RefreshCw className="h-3 w-3 animate-spin" />
      {label}
    </Badge>
  );
}

/**
 * Soft refetch wrapper: keep prior content visible, dim it, and mark busy.
 * Use for currency / timeframe / stats refreshes instead of blanking the page.
 */
export function SoftLoading({
  active,
  children,
  className,
  label = "Updating…",
  showOverlay = true,
}: {
  active: boolean;
  children: ReactNode;
  className?: string;
  label?: string;
  /** Floating pill over content (set false if the page header already shows UpdatingBadge). */
  showOverlay?: boolean;
}) {
  return (
    <div
      className={cn(
        "relative transition-[opacity,filter] duration-200",
        active && "opacity-55",
        className
      )}
      aria-busy={active || undefined}
    >
      {children}
      {active && showOverlay && (
        <div className="pointer-events-none absolute inset-x-0 top-8 z-10 flex justify-center">
          <span className="inline-flex items-center gap-2 rounded-full border border-border bg-surface/95 px-3 py-1.5 text-xs font-medium text-content shadow-elevated backdrop-blur-sm">
            <Spinner className="h-3.5 w-3.5 text-brand-600" />
            {label}
          </span>
        </div>
      )}
    </div>
  );
}

/** Metric card grid skeleton used by Analytics / Ads / overview. */
export function MetricGridSkeleton({
  rows = 2,
  cols = 4,
}: {
  rows?: number;
  cols?: number;
}) {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading stats">
      {Array.from({ length: rows }).map((_, row) => (
        <div
          key={row}
          className={cn(
            "grid gap-3 sm:gap-4 grid-cols-1 sm:grid-cols-2",
            cols >= 4 ? "xl:grid-cols-4" : cols === 3 ? "lg:grid-cols-3" : ""
          )}
        >
          {Array.from({ length: cols }).map((_, i) => (
            <Skeleton key={i} className="h-[104px]" />
          ))}
        </div>
      ))}
    </div>
  );
}

/** Full dashboard body skeleton (metrics + charts). */
export function DashboardBodySkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading dashboard">
      <MetricGridSkeleton rows={2} cols={4} />
      <div className="grid gap-4 xl:grid-cols-2">
        <Skeleton className="h-72" />
        <Skeleton className="h-72" />
      </div>
      <Skeleton className="h-64" />
    </div>
  );
}

/** Compact list-row skeletons (activity, inbox, reports). */
export function ListSkeleton({ rows = 5, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 px-1 py-2">
          <Skeleton className="h-9 w-9 rounded-lg shrink-0" />
          <div className="flex-1 space-y-2 min-w-0">
            <Skeleton className="h-3.5 w-2/3 max-w-[200px]" />
            <Skeleton className="h-3 w-full max-w-[280px]" />
          </div>
        </div>
      ))}
    </div>
  );
}

/** Centered page-section spinner with optional label. */
export function PageSpinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-content-muted" role="status">
      <Spinner className="h-6 w-6 text-brand-600" />
      <p className="text-sm">{label}</p>
    </div>
  );
}
