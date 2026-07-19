import { cn } from "@/lib/cn";

type BadgeVariant = "default" | "success" | "warning" | "muted" | "brand";

const variants: Record<BadgeVariant, string> = {
  default: "bg-surface-muted text-content-muted border-border",
  success: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20",
  warning: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
  muted: "bg-slate-500/10 text-content-subtle border-border",
  brand: "bg-brand-500/10 text-brand-700 dark:text-brand-400 border-brand-500/20",
};

export function Badge({
  children,
  variant = "default",
  className,
}: {
  children: React.ReactNode;
  variant?: BadgeVariant;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium",
        variants[variant],
        className
      )}
    >
      {children}
    </span>
  );
}
