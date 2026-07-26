import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight, Mail, Package, Sparkles, BarChart3, Megaphone } from "lucide-react";
import { Card, CardDescription, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import type { ModuleHighlight } from "@/lib/dashboardTypes";
import { cn } from "@/lib/cn";

const ICONS = {
  "ai-email": Sparkles,
  tracking: Package,
  email: Mail,
  analytics: BarChart3,
  ads: Megaphone,
} as const;

function moduleHref(h: ModuleHighlight): string {
  if (h.status === "setup") {
    if (h.slug === "tracking" || h.slug === "analytics" || h.slug === "ads") {
      return "/settings/stores";
    }
    return "/settings/gmail";
  }
  return `/modules/${h.slug}`;
}

const statusVariant = (s: string) => {
  if (s === "active") return "success" as const;
  if (s === "setup") return "warning" as const;
  return "muted" as const;
};

const statusLabel = (s: string) => {
  if (s === "setup") return "Setup";
  if (s === "active") return "Ready";
  return s.replace("_", " ");
};

export function ModuleHighlights({
  highlights,
  loading,
}: {
  highlights: ModuleHighlight[];
  loading?: boolean;
}) {
  if (!loading && highlights.length === 0) return null;

  const items = loading && highlights.length === 0
    ? Array.from({ length: 5 }).map((_, i) => ({
        slug: `skeleton-${i}`,
        name: "—",
        status: "setup",
        stat_label: "…",
        stat_value: "—",
        hint: "Loading",
      }))
    : highlights;

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
      {items.map((item, i) => {
        const Icon = ICONS[item.slug as keyof typeof ICONS] ?? Package;
        const disabled = item.status === "coming_soon" || loading;

        const inner = (
          <Card
            hover={!disabled && !loading}
            className={cn("h-full", loading && "opacity-60 animate-pulse", disabled && !loading && "opacity-75")}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-500/10 text-brand-600 dark:text-brand-400">
                <Icon className="h-5 w-5" />
              </div>
              <Badge variant={statusVariant(item.status)} className="capitalize shrink-0">
                {statusLabel(item.status)}
              </Badge>
            </div>
            <CardTitle className="mt-3 text-base">{item.name}</CardTitle>
            <CardDescription className="line-clamp-2">{item.hint}</CardDescription>
            <div className="mt-4 flex items-end justify-between gap-2">
              <div>
                <p className="text-xs text-content-subtle uppercase tracking-wide">
                  {item.stat_label}
                </p>
                <p className="text-2xl font-bold text-content tabular-nums">{item.stat_value}</p>
              </div>
              {!disabled && (
                <span className="inline-flex items-center gap-1 text-sm font-medium text-brand-600 opacity-0 group-hover:opacity-100 transition-opacity">
                  Open
                  <ArrowRight className="h-3.5 w-3.5" />
                </span>
              )}
            </div>
          </Card>
        );

        return (
          <motion.div
            key={item.slug}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.04 }}
          >
            {disabled ? (
              inner
            ) : (
              <Link to={moduleHref(item)} className="block group">
                {inner}
              </Link>
            )}
          </motion.div>
        );
      })}
    </div>
  );
}
