import { cn } from "@/lib/cn";
import type { LucideIcon } from "lucide-react";

type Props = {
  label: string;
  value: string;
  hint?: string;
  icon?: LucideIcon;
  trend?: "up" | "down" | "neutral";
  trendLabel?: string;
  accent?: "brand" | "success" | "warning" | "danger" | "default";
  className?: string;
};

const accentStyles = {
  default: "border-border bg-surface",
  brand: "border-brand-500/20 bg-brand-500/5",
  success: "border-emerald-500/20 bg-emerald-500/5",
  warning: "border-amber-500/20 bg-amber-500/5",
  danger: "border-red-500/20 bg-red-500/5",
};

export function MetricCard({
  label,
  value,
  hint,
  icon: Icon,
  trend,
  trendLabel,
  accent = "default",
  className,
}: Props) {
  return (
    <div
      className={cn(
        "rounded-xl border p-5 shadow-card transition-all",
        accentStyles[accent],
        className
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-content-muted">{label}</p>
          <p className="mt-1 text-2xl font-bold tracking-tight text-content">{value}</p>
          {hint && <p className="mt-1 text-xs text-content-subtle">{hint}</p>}
        </div>
        {Icon && (
          <div className="rounded-lg bg-surface-muted p-2.5 shrink-0">
            <Icon className="h-5 w-5 text-brand-600 dark:text-brand-400" />
          </div>
        )}
      </div>
      {trendLabel && (
        <p
          className={cn(
            "mt-3 text-xs font-medium",
            trend === "up" && "text-emerald-600 dark:text-emerald-400",
            trend === "down" && "text-red-600 dark:text-red-400",
            trend === "neutral" && "text-content-muted"
          )}
        >
          {trendLabel}
        </p>
      )}
    </div>
  );
}
