import { Link } from "react-router-dom";
import { Card } from "@/components/ui/Card";
import { BrandLoader } from "@/components/ui/Loading";
import type { OverviewMetric } from "@/lib/dashboardTypes";
import { cn } from "@/lib/cn";

const METRIC_HREF: Record<string, string> = {
  "Revenue (7d)": "/modules/analytics",
  "Net profit (7d)": "/modules/analytics",
  "Ad spend (7d)": "/modules/ads",
  "ROAS (7d)": "/modules/ads",
};

export function OverviewCards({
  metrics,
  loading,
}: {
  metrics: OverviewMetric[];
  loading?: boolean;
}) {
  if (loading) {
    return (
      <div
        className="flex min-h-[88px] items-center justify-center rounded-xl border border-border bg-surface"
        aria-busy="true"
        aria-label="Loading workspace stats"
      >
        <BrandLoader size="sm" />
      </div>
    );
  }

  return (
    <Card padding="none" className="overflow-hidden">
      <div className="grid grid-cols-2 xl:grid-cols-4">
        {metrics.map((m, i) => {
          const href = METRIC_HREF[m.label];
          const valueClass =
            m.trend === "up"
              ? "text-emerald-600 dark:text-emerald-400"
              : m.trend === "down"
                ? "text-red-500"
                : "text-content";
          const cell = (
            <div
              className={cn(
                "p-3.5 sm:p-4",
                i > 0 && "border-t border-border xl:border-t-0 xl:border-l",
                href && "transition-colors group-hover:bg-brand-500/5"
              )}
            >
              <p className="text-xs font-medium uppercase tracking-wide text-content-subtle">
                {m.label}
              </p>
              <p className={cn("mt-1 text-xl font-semibold tabular-nums tracking-tight", valueClass)}>
                {m.value}
              </p>
              <p className="mt-0.5 line-clamp-1 text-xs text-content-muted">{m.change}</p>
            </div>
          );
          return href ? (
            <Link key={m.label} to={href} className="group block min-w-0" aria-label={`Open ${m.label}`}>
              {cell}
            </Link>
          ) : (
            <div key={m.label}>{cell}</div>
          );
        })}
      </div>
    </Card>
  );
}
