import { useEffect, useState } from "react";
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
} from "lucide-react";
import { Card, CardDescription, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { api } from "@/lib/api";
import type { AppModule } from "@/types";

const ICON_MAP: Record<string, typeof Mail> = {
  mail: Mail,
  package: Package,
  chart: BarChart3,
  message: MessageSquare,
  headphones: Headphones,
  sparkles: Sparkles,
};

const statusBadge = (s: string) => {
  if (s === "active") return "success" as const;
  if (s === "beta") return "brand" as const;
  if (s === "setup") return "warning" as const;
  return "muted" as const;
};

const statusLabel = (s: string) => {
  if (s === "setup") return "Setup required";
  if (s === "coming_soon") return "Coming soon";
  return s.replace("_", " ");
};

function moduleHref(mod: AppModule): string {
  if (mod.status === "coming_soon") return "#";
  if (mod.status === "setup") {
    if (mod.slug === "tracking") return "/settings/stores";
    if (mod.slug === "email" || mod.slug === "ai-email") return "/settings/gmail";
  }
  return `/modules/${mod.slug}`;
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

  if (loading) {
    return <p className="text-sm text-content-subtle">Loading apps…</p>;
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {modules.map((mod, i) => {
        const Icon = ICON_MAP[mod.icon] ?? Package;
        const disabled = mod.status === "coming_soon";
        const href = moduleHref(mod);
        const card = (
          <Card hover={!disabled} className="h-full">
            <div className="flex items-start justify-between gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-500/10 text-brand-600 dark:text-brand-400">
                <Icon className="h-5 w-5" />
              </div>
              <Badge variant={statusBadge(mod.status)} className="capitalize">
                {statusLabel(mod.status)}
              </Badge>
            </div>
            <CardTitle className="mt-4">{mod.name}</CardTitle>
            <CardDescription>{mod.description}</CardDescription>
            {!disabled && (
              <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-brand-600 opacity-0 group-hover:opacity-100 transition-opacity">
                Open app
                <ArrowRight className="h-3.5 w-3.5" />
              </span>
            )}
          </Card>
        );

        return (
          <motion.div
            key={mod.id}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
          >
            {disabled ? (
              <div className="block opacity-75">{card}</div>
            ) : (
              <Link to={href} className="block group">
                {card}
              </Link>
            )}
          </motion.div>
        );
      })}
    </div>
  );
}
