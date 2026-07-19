import { motion } from "framer-motion";
import { Minus } from "lucide-react";
import { Card } from "@/components/ui/Card";
import type { OverviewMetric } from "@/lib/dashboardTypes";
import { cn } from "@/lib/cn";

export function OverviewCards({
  metrics,
  loading,
}: {
  metrics: OverviewMetric[];
  loading?: boolean;
}) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {metrics.map((m, i) => (
        <motion.div
          key={m.label}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.05, duration: 0.3 }}
        >
          <Card className={cn(loading && "opacity-60")}>
            <p className="text-sm text-content-muted">{m.label}</p>
            <p className="mt-2 text-2xl font-bold tracking-tight text-content tabular-nums">
              {m.value}
            </p>
            <div className="mt-2 flex items-center gap-1 text-xs font-medium text-content-subtle">
              <Minus className="h-3.5 w-3.5 shrink-0" />
              <span className="line-clamp-2">{m.change}</span>
            </div>
          </Card>
        </motion.div>
      ))}
    </div>
  );
}
