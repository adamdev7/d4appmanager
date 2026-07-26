import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Mail,
  Package,
  BarChart3,
  MessageSquare,
  Headphones,
  ArrowRight,
  Sparkles,
  Megaphone,
  Lock,
  Clock,
  Zap,
} from "lucide-react";
import { Card, CardDescription, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { api } from "@/lib/api";
import type { AppModule } from "@/types";
import { cn } from "@/lib/cn";

const ICON_MAP: Record<string, typeof Mail> = {
  mail: Mail,
  package: Package,
  chart: BarChart3,
  message: MessageSquare,
  headphones: Headphones,
  sparkles: Sparkles,
  megaphone: Megaphone,
};

const statusBadge = (s: string) => {
  if (s === "active") return "success" as const;
  if (s === "beta") return "brand" as const;
  if (s === "setup") return "warning" as const;
  return "muted" as const;
};

const statusLabel = (s: string) => {
  if (s === "setup") return "Needs connection";
  if (s === "coming_soon") return "Coming soon";
  if (s === "active") return "Ready";
  return s.replace("_", " ");
};

function moduleHref(mod: AppModule): string {
  if (mod.status === "coming_soon") return "#";
  if (mod.status === "setup") {
    if (mod.slug === "tracking" || mod.slug === "analytics" || mod.slug === "ads") {
      return "/settings/stores";
    }
    if (mod.slug === "email" || mod.slug === "ai-email") return "/settings/gmail";
  }
  return `/modules/${mod.slug}`;
}

function ModuleCard({
  mod,
  index,
  compact,
}: {
  mod: AppModule;
  index: number;
  compact?: boolean;
}) {
  const Icon = ICON_MAP[mod.icon] ?? Package;
  const disabled = mod.status === "coming_soon";
  const href = moduleHref(mod);
  const SectionIcon =
    mod.status === "active" ? Zap : mod.status === "setup" ? Lock : Clock;

  const card = (
    <Card
      hover={!disabled}
      className={cn(
        "h-full relative overflow-hidden",
        mod.status === "active" && "border-brand-500/25",
        mod.status === "coming_soon" && "opacity-80"
      )}
    >
      {mod.status === "active" && (
        <div className="absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r from-brand-500 to-emerald-400" />
      )}
      <div className="flex items-start justify-between gap-3">
        <div
          className={cn(
            "flex h-10 w-10 items-center justify-center rounded-xl",
            mod.status === "active"
              ? "bg-brand-500/15 text-brand-600 dark:text-brand-400"
              : mod.status === "setup"
                ? "bg-amber-500/10 text-amber-600"
                : "bg-surface-muted text-content-subtle"
          )}
        >
          <Icon className="h-5 w-5" />
        </div>
        <Badge variant={statusBadge(mod.status)} className="capitalize">
          {statusLabel(mod.status)}
        </Badge>
      </div>
      <CardTitle className={cn("mt-4", compact && "text-base")}>{mod.name}</CardTitle>
      <CardDescription className={compact ? "line-clamp-2" : undefined}>
        {mod.description}
      </CardDescription>
      {!disabled && (
        <span className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-brand-600">
          {mod.status === "setup" ? "Connect to unlock" : "Open app"}
          <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
        </span>
      )}
      {disabled && (
        <span className="mt-4 inline-flex items-center gap-1.5 text-xs font-medium text-content-subtle">
          <SectionIcon className="h-3.5 w-3.5" />
          On the roadmap
        </span>
      )}
    </Card>
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04 }}
    >
      {disabled ? (
        <div className="block">{card}</div>
      ) : (
        <Link to={href} className="block group">
          {card}
        </Link>
      )}
    </motion.div>
  );
}

function SectionHeader({
  title,
  subtitle,
  count,
}: {
  title: string;
  subtitle: string;
  count: number;
}) {
  return (
    <div className="flex items-end justify-between gap-3 mb-3">
      <div>
        <h3 className="text-base font-semibold text-content">{title}</h3>
        <p className="text-sm text-content-muted mt-0.5">{subtitle}</p>
      </div>
      <span className="text-xs font-medium tabular-nums text-content-subtle">{count}</span>
    </div>
  );
}

export function AppModulesGrid() {
  const [modules, setModules] = useState<AppModule[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.modules
      .list()
      .then((data) => setModules(data as AppModule[]))
      .catch(() => setModules([]))
      .finally(() => setLoading(false));
  }, []);

  const grouped = useMemo(() => {
    const ready = modules.filter((m) => m.status === "active" || m.status === "beta");
    const setup = modules.filter((m) => m.status === "setup");
    const soon = modules.filter((m) => m.status === "coming_soon");
    return { ready, setup, soon };
  }, [modules]);

  if (loading) {
    return (
      <div className="space-y-3">
        <div className="h-4 w-40 rounded bg-surface-muted animate-pulse" />
        <div className="grid gap-4 sm:grid-cols-2">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-36 rounded-xl border border-border bg-surface animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (modules.length === 0) {
    return <p className="text-sm text-content-subtle">No apps available right now.</p>;
  }

  return (
    <div className="space-y-8">
      {grouped.ready.length > 0 && (
        <section>
          <SectionHeader
            title="Ready to use"
            subtitle="Connected and available for daily work"
            count={grouped.ready.length}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            {grouped.ready.map((mod, i) => (
              <ModuleCard key={mod.id} mod={mod} index={i} />
            ))}
          </div>
        </section>
      )}

      {grouped.setup.length > 0 && (
        <section>
          <SectionHeader
            title="Needs a connection"
            subtitle="Link Shopify or Gmail once to unlock these apps"
            count={grouped.setup.length}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            {grouped.setup.map((mod, i) => (
              <ModuleCard key={mod.id} mod={mod} index={i} compact />
            ))}
          </div>
        </section>
      )}

      {grouped.soon.length > 0 && (
        <section>
          <SectionHeader
            title="Coming soon"
            subtitle="Planned modules — not available yet"
            count={grouped.soon.length}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            {grouped.soon.map((mod, i) => (
              <ModuleCard key={mod.id} mod={mod} index={i} compact />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
