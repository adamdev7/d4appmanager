import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Mail,
  Package,
  BarChart3,
  MessageSquare,
  Headphones,
  Sparkles,
  Megaphone,
  Radar,
  WandSparkles,
  ChevronRight,
} from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { BrandLoader } from "@/components/ui/Loading";
import { api } from "@/lib/api";
import type { AppModule } from "@/types";
import type { ModuleHighlight } from "@/lib/dashboardTypes";
import { cn } from "@/lib/cn";

const ICON_MAP: Record<string, typeof Mail> = {
  mail: Mail,
  package: Package,
  chart: BarChart3,
  message: MessageSquare,
  headphones: Headphones,
  sparkles: Sparkles,
  megaphone: Megaphone,
  radar: Radar,
  wand: WandSparkles,
};

type Filter = "all" | "ready" | "setup" | "soon";

function statusBadge(s: string) {
  if (s === "active" || s === "beta") return "success" as const;
  if (s === "setup") return "warning" as const;
  return "muted" as const;
}

function statusLabel(s: string) {
  if (s === "setup") return "Needs setup";
  if (s === "coming_soon") return "Soon";
  if (s === "active") return "Ready";
  if (s === "beta") return "Beta";
  return s.replace("_", " ");
}

function moduleHref(mod: AppModule): string {
  if (mod.status === "coming_soon") return "#";
  if (mod.slug === "ai-ads") return "/ai-ads";
  if (mod.status === "setup") {
    if (
      mod.slug === "tracking" ||
      mod.slug === "analytics" ||
      mod.slug === "ads" ||
      mod.slug === "ai-ads" ||
      mod.slug === "meta-capi"
    ) {
      return "/settings/stores";
    }
    if (mod.slug === "email" || mod.slug === "ai-email") return "/settings/gmail";
  }
  return `/modules/${mod.slug}`;
}

function matchesFilter(mod: AppModule, filter: Filter) {
  if (filter === "all") return true;
  if (filter === "ready") return mod.status === "active" || mod.status === "beta";
  if (filter === "setup") return mod.status === "setup";
  return mod.status === "coming_soon";
}

export function AppModulesGrid({
  highlights = [],
  loadingHighlights,
}: {
  highlights?: ModuleHighlight[];
  loadingHighlights?: boolean;
}) {
  const [modules, setModules] = useState<AppModule[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Filter>("all");

  useEffect(() => {
    api.modules
      .list()
      .then((data) => setModules(data as AppModule[]))
      .catch(() => setModules([]))
      .finally(() => setLoading(false));
  }, []);

  const statsBySlug = useMemo(() => {
    const map = new Map(highlights.map((h) => [h.slug, h]));
    return map;
  }, [highlights]);

  const counts = useMemo(() => {
    return {
      all: modules.length,
      ready: modules.filter((m) => m.status === "active" || m.status === "beta").length,
      setup: modules.filter((m) => m.status === "setup").length,
      soon: modules.filter((m) => m.status === "coming_soon").length,
    };
  }, [modules]);

  const visible = useMemo(
    () => modules.filter((m) => matchesFilter(m, filter)),
    [modules, filter]
  );

  if (loading) {
    return (
      <div
        className="flex min-h-[180px] items-center justify-center rounded-xl border border-border bg-surface"
        aria-busy="true"
        aria-label="Loading apps"
      >
        <BrandLoader size="sm" />
      </div>
    );
  }

  if (modules.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-surface px-4 py-8 text-center">
        <p className="text-sm text-content-subtle">No apps available right now.</p>
      </div>
    );
  }

  const filters: { id: Filter; label: string; count: number }[] = [
    { id: "all", label: "All", count: counts.all },
    { id: "ready", label: "Ready", count: counts.ready },
    { id: "setup", label: "Needs setup", count: counts.setup },
    { id: "soon", label: "Coming soon", count: counts.soon },
  ];

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold text-content">Apps</h2>
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Filter apps">
          {filters
            .filter((item) => item.id === "all" || item.count > 0)
            .map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={filter === item.id}
                onClick={() => setFilter(item.id)}
                className={cn(
                  "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                  filter === item.id
                    ? "bg-brand-500/15 text-brand-700 dark:text-brand-400"
                    : "text-content-muted hover:bg-surface-muted hover:text-content"
                )}
              >
                {item.label}
                <span className="ml-1 tabular-nums text-content-subtle">{item.count}</span>
              </button>
            ))}
        </div>
      </div>

      {visible.length === 0 ? (
        <p className="rounded-xl border border-border bg-surface px-4 py-8 text-center text-sm text-content-subtle">
          No apps in this group.
        </p>
      ) : (
        <ul className="grid min-h-0 grid-cols-1 content-start gap-2 overflow-y-auto lg:grid-cols-2">
          {visible.map((mod) => {
            const Icon = ICON_MAP[mod.icon] ?? Package;
            const disabled = mod.status === "coming_soon";
            const href = moduleHref(mod);
            const highlight = statsBySlug.get(mod.slug);
            const detail = highlight
              ? `${highlight.stat_label}: ${highlight.stat_value}`
              : mod.description;
            const ready = mod.status === "active" || mod.status === "beta";

            const row = (
              <div
                className={cn(
                  "flex h-full items-center gap-3 rounded-xl border bg-surface px-3 py-2 transition-colors",
                  ready
                    ? "border-brand-500/20"
                    : disabled
                      ? "border-border opacity-75"
                      : "border-border",
                  !disabled && "group-hover:border-brand-500/40 group-hover:bg-brand-500/5"
                )}
              >
                <div
                  className={cn(
                    "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
                    ready
                      ? "bg-brand-500/15 text-brand-600 dark:text-brand-400"
                      : mod.status === "setup"
                        ? "bg-amber-500/10 text-amber-600"
                        : "bg-surface-muted text-content-subtle"
                  )}
                >
                  <Icon className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-semibold leading-tight text-content">{mod.name}</p>
                    <Badge variant={statusBadge(mod.status)} className="shrink-0 capitalize">
                      {statusLabel(mod.status)}
                    </Badge>
                  </div>
                  <p className="mt-0.5 truncate text-xs text-content-muted">
                    {loadingHighlights && !highlight ? "Loading…" : detail}
                  </p>
                </div>
                {!disabled && (
                  <ChevronRight className="h-4 w-4 shrink-0 text-content-subtle group-hover:text-brand-600" />
                )}
              </div>
            );

            return (
              <li key={mod.id}>
                {disabled ? (
                  row
                ) : (
                  <Link to={href} className="group block h-full" aria-label={`Open ${mod.name}`}>
                    {row}
                  </Link>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
