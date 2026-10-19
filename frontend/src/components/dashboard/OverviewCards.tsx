import { Card } from "@/components/ui/Card";
import { BrandLoader } from "@/components/ui/Loading";
import type { OverviewMetric } from "@/lib/dashboardTypes";

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
        className="flex min-h-[72px] items-center justify-center rounded-xl border border-border bg-surface"
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
        {metrics.map((m, i) => (
          <div
            key={m.label}
            className={
              i > 0
                ? "border-t border-border p-3.5 sm:p-4 xl:border-t-0 xl:border-l"
                : "p-3.5 sm:p-4"
            }
          >
            <p className="text-xs font-medium uppercase tracking-wide text-content-subtle">
              {m.label}
            </p>
            <p className="mt-1 text-xl font-semibold tabular-nums tracking-tight text-content">
              {m.value}
            </p>
            <p className="mt-0.5 line-clamp-1 text-xs text-content-muted">{m.change}</p>
          </div>
        ))}
      </div>
    </Card>
  );
}
