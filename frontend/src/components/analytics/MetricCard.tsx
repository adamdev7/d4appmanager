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
        "min-w-0 overflow-hidden rounded-xl border p-4 sm:p-5 xl:p-6 2xl:p-7 shadow-card transition-all",
        accentStyles[accent],
        className
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm xl:text-base font-medium text-content-muted truncate">{label}</p>
          <p className="mt-1 text-xl sm:text-2xl xl:text-3xl font-bold tracking-tight text-content break-words">
            {value}
          </p>
          {hint && (
            <p className="mt-1 text-xs xl:text-sm text-content-subtle break-words line-clamp-3">
              {hint}
            </p>
          )}
        </div>
        {Icon && (
          <div className="rounded-lg bg-surface-muted p-2 sm:p-2.5 xl:p-3 shrink-0">
            <Icon className="h-4 w-4 sm:h-5 sm:w-5 xl:h-6 xl:w-6 text-brand-600 dark:text-brand-400" />
          </div>
        )}
      </div>
      {trendLabel && (
        <p
          className={cn(
            "mt-3 text-xs font-medium truncate",
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
