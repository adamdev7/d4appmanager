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

const brandLoaderSize = {
  sm: { wrap: "h-10 w-10", logo: "h-5 w-5", ring: "border-[2.5px]" },
  md: { wrap: "h-14 w-14", logo: "h-7 w-7", ring: "border-[3px]" },
  lg: { wrap: "h-16 w-16", logo: "h-8 w-8", ring: "border-[3px]" },
} as const;

/**
 * Brand loader — green spinning ring with the App Manager logo centered.
 * Use for page loads and soft-refresh overlays.
 */
export function BrandLoader({
  size = "md",
  className,
  label,
}: {
  size?: keyof typeof brandLoaderSize;
  className?: string;
  label?: string;
}) {
  const s = brandLoaderSize[size];
  return (
    <div
      role="status"
      aria-label={label ?? "Loading"}
      className={cn("inline-flex flex-col items-center gap-3", className)}
    >
      <div className={cn("relative", s.wrap)}>
        <span
          className={cn(
            "absolute inset-0 rounded-full border-brand-500/25 border-t-brand-600 border-r-brand-500 animate-spin",
            s.ring
          )}
        />
        <span className="absolute inset-0 flex items-center justify-center">
          <img
            src="/app-manager-logo.png"
            alt=""
            className={cn("object-contain rounded-md", s.logo)}
          />
        </span>
      </div>
      {label ? <p className="text-sm text-content-muted">{label}</p> : null}
    </div>
  );
}

/** Centered brand loader for full page / section first loads. */
export function PageLoader({
  label,
  className,
  size = "md",
}: {
  label?: string;
  className?: string;
  size?: keyof typeof brandLoaderSize;
}) {
  return (
    <div
      className={cn(
        "flex min-h-[min(420px,55vh)] w-full items-center justify-center py-16",
        className
      )}
      aria-busy="true"
    >
      <BrandLoader size={size} label={label} />
    </div>
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
 * Soft refetch wrapper: keep prior content visible, dim it, and show brand loader.
 * Use for currency / timeframe / stats refreshes instead of blanking the page.
 */
export function SoftLoading({
  active,
  children,
  className,
  label,
  showOverlay = true,
}: {
  active: boolean;
  children: ReactNode;
  className?: string;
  label?: string;
  /** Floating brand loader over content (set false if the page header already shows UpdatingBadge). */
  showOverlay?: boolean;
}) {
  return (
    <div className={cn("relative", className)} aria-busy={active || undefined}>
      <div
        className={cn(
          "transition-opacity duration-200",
          active && "opacity-50 pointer-events-none"
        )}
      >
        {children}
      </div>
      {active && showOverlay && (
        <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center">
          <div className="rounded-full bg-surface/95 p-2.5 shadow-elevated backdrop-blur-sm border border-border/80">
            <BrandLoader size="sm" label={label} />
          </div>
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

/** Full dashboard body first-load — centered brand loader. */
export function DashboardBodySkeleton() {
  return <PageLoader />;
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

/** @deprecated Prefer PageLoader — kept as alias for older call sites. */
export function PageSpinner({ label }: { label?: string }) {
  return <PageLoader label={label} />;
}
