import { motion } from "framer-motion";
import { Minus } from "lucide-react";
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
        className="flex min-h-[140px] items-center justify-center rounded-xl border border-border bg-surface py-10"
        aria-busy="true"
        aria-label="Loading workspace stats"
      >
        <BrandLoader size="sm" />
      </div>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4 xl:gap-5 2xl:gap-6">
      {metrics.map((m, i) => (
        <motion.div
          key={m.label}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.05, duration: 0.3 }}
        >
          <Card>
            <p className="text-sm xl:text-base text-content-muted">{m.label}</p>
            <p className="mt-2 text-2xl xl:text-3xl 2xl:text-4xl font-bold tracking-tight text-content tabular-nums">
              {m.value}
            </p>
            <div className="mt-2 flex items-center gap-1 text-xs xl:text-sm font-medium text-content-subtle">
              <Minus className="h-3.5 w-3.5 shrink-0" />
              <span className="line-clamp-2">{m.change}</span>
            </div>
          </Card>
        </motion.div>
      ))}
    </div>
  );
}
