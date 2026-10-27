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
  Eraser,
  ChevronRight,
} from "lucide-react";
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
  eraser: Eraser,
};

function moduleHref(mod: AppModule): string {
  if (mod.status === "coming_soon") return "#";
  if (mod.slug === "ai-ads") return "/ai-ads";
  if (mod.status === "setup") {
    if (mod.slug === "email" || mod.slug === "ai-email") return "/settings/gmail";
    return "/settings/stores";
  }
  return `/modules/${mod.slug}`;
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

  useEffect(() => {
    api.modules
      .list()
      .then((data) => setModules(data as AppModule[]))
      .catch(() => setModules([]))
      .finally(() => setLoading(false));
  }, []);

  const statsBySlug = useMemo(() => {
    return new Map(highlights.map((h) => [h.slug, h]));
  }, [highlights]);

  const live = useMemo(
    () => modules.filter((m) => m.status !== "coming_soon"),
    [modules]
  );
  const soon = useMemo(
    () => modules.filter((m) => m.status === "coming_soon"),
    [modules]
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

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      <div className="mb-3 flex items-end justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold text-content">App pulse</h2>
          <p className="text-xs text-content-muted">Live slice of each app · last 7 days</p>
        </div>
      </div>

      <ul className="grid grid-cols-1 content-start gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {live.map((mod) => {
          const Icon = ICON_MAP[mod.icon] ?? Package;
          const href = moduleHref(mod);
          const highlight = statsBySlug.get(mod.slug);
          const ready = mod.status === "active" || mod.status === "beta";
          const value = loadingHighlights && !highlight ? "…" : highlight?.stat_value ?? "—";
          const label = highlight?.stat_label ?? "Open app";
          const hint = highlight?.hint ?? mod.description;

          const row = (
            <div
              className={cn(
                "flex h-full items-center gap-3 rounded-xl border bg-surface px-3 py-2.5 transition-colors",
                ready ? "border-brand-500/20" : "border-border",
                "group-hover:border-brand-500/40 group-hover:bg-brand-500/5"
              )}
            >
              <div
                className={cn(
                  "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
                  ready
                    ? "bg-brand-500/15 text-brand-600 dark:text-brand-400"
                    : "bg-amber-500/10 text-amber-600"
                )}
              >
                <Icon className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium text-content-muted">{mod.name}</p>
                <p className="truncate text-lg font-semibold tabular-nums leading-tight text-content">
                  {value}
                </p>
                <p className="truncate text-xs text-content-subtle">
                  {label}
                  {hint ? ` · ${hint}` : ""}
                </p>
              </div>
              <ChevronRight className="h-4 w-4 shrink-0 text-content-subtle group-hover:text-brand-600" />
            </div>
          );

          return (
            <li key={mod.id}>
              <Link to={href} className="group block h-full" aria-label={`Open ${mod.name}`}>
                {row}
              </Link>
            </li>
          );
        })}
      </ul>

      {soon.length > 0 && (
        <ul className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {soon.map((mod) => {
            const Icon = ICON_MAP[mod.icon] ?? Package;
            return (
              <li
                key={mod.id}
                className="flex items-center gap-3 rounded-xl border border-border bg-surface px-3 py-2 opacity-70"
              >
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-surface-muted text-content-subtle">
                  <Icon className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-content">{mod.name}</p>
                  <p className="truncate text-xs text-content-subtle">Coming soon</p>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
