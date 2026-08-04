import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Settings,
  Store,
  Mail,
  Sparkles,
  Package,
  BarChart3,
  Megaphone,
  Radar,
  CheckCircle2,
} from "lucide-react";
import { OverviewCards } from "@/components/dashboard/OverviewCards";
import { ActivityFeed } from "@/components/dashboard/ActivityFeed";
import { AppModulesGrid } from "@/components/dashboard/AppModulesGrid";
import { ModuleHighlights } from "@/components/dashboard/ModuleHighlights";
import { WorkspaceSetup } from "@/components/dashboard/WorkspaceSetup";
import { useStore } from "@/context/StoreContext";
import { useAuth } from "@/context/AuthContext";
import { Badge } from "@/components/ui/Badge";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { EMPTY_DASHBOARD_OVERVIEW, type DashboardOverview } from "@/lib/dashboardTypes";
import { cn } from "@/lib/cn";

const QUICK_LINKS = [
  { to: "/modules/ai-email", label: "AI Email", icon: Sparkles },
  { to: "/modules/tracking", label: "Tracking", icon: Package },
  { to: "/modules/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/modules/ads", label: "Ads", icon: Megaphone },
  { to: "/modules/meta-capi", label: "CAPI", icon: Radar },
  { to: "/settings/stores", label: "Stores", icon: Store },
  { to: "/settings/gmail", label: "Gmail", icon: Mail },
] as const;

function greetingForHour(hour: number) {
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export function DashboardPage() {
  const { activeStore, stores } = useStore();
  const { user } = useAuth();
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.dashboard
      .overview(activeStore?.id)
      .then((data) => {
        if (!cancelled) setOverview(data);
      })
      .catch(() => {
        if (!cancelled) setOverview(EMPTY_DASHBOARD_OVERVIEW);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeStore?.id]);

  const display = overview ?? EMPTY_DASHBOARD_OVERVIEW;

  // Never flash the setup card from empty defaults while overview is still loading.
  // Also hide it once both Shopify and Gmail steps are complete.
  const setupIncomplete =
    !loading &&
    overview != null &&
    overview.setup_steps.some((s) => !s.done);

  const workspaceReady =
    !loading &&
    overview != null &&
    overview.setup_steps.length > 0 &&
    overview.setup_steps.every((s) => s.done);

  const firstName = useMemo(() => {
    const name = user?.full_name?.trim() || "";
    return name.split(/\s+/)[0] || "there";
  }, [user?.full_name]);

  const greeting = greetingForHour(new Date().getHours());
  const connectedStoreCount = stores.filter((s) => s.status === "connected").length;

  return (
    <div className="space-y-8 w-full min-w-0">
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4"
      >
        <div>
          <p className="text-sm xl:text-base font-medium text-brand-600 dark:text-brand-400">
            {greeting}, {firstName}
          </p>
          <h1 className="text-2xl xl:text-3xl 2xl:text-4xl font-bold tracking-tight text-content mt-0.5">
            Overview
          </h1>
          <p className="mt-1 text-content-muted max-w-2xl xl:text-lg">
            {activeStore
              ? `Workspace for ${activeStore.name} — email, tracking, analytics, and ads in one place.`
              : "Your automation hub — connect Shopify and Gmail, then launch any app below."}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {activeStore && (
            <Badge variant={activeStore.status === "connected" ? "success" : "warning"}>
              {activeStore.name} · {activeStore.currency}
            </Badge>
          )}
          {connectedStoreCount > 1 && (
            <Badge variant="muted">{connectedStoreCount} stores</Badge>
          )}
          <Link
            to="/settings"
            className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm text-content-muted hover:bg-surface-muted hover:text-content transition-colors"
          >
            <Settings className="h-3.5 w-3.5" />
            Settings
          </Link>
        </div>
      </motion.div>

      {setupIncomplete && overview && <WorkspaceSetup steps={overview.setup_steps} />}

      {workspaceReady && (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center gap-3 rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-4 py-3"
        >
          <CheckCircle2 className="h-5 w-5 text-emerald-600 shrink-0" />
          <div className="min-w-0">
            <p className="text-sm font-medium text-content">Workspace ready</p>
            <p className="text-xs text-content-muted">
              Shopify and Gmail are connected. Jump into any ready app below.
            </p>
          </div>
        </motion.div>
      )}

      <section className={cn(loading && "opacity-70 transition-opacity")}>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-medium text-content-subtle uppercase tracking-wider">
            Workspace
          </h2>
          <div className="hidden sm:flex flex-wrap gap-1.5">
            {QUICK_LINKS.slice(0, 4).map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-content-muted hover:bg-surface-muted hover:text-content transition-colors"
              >
                <item.icon className="h-3 w-3" />
                {item.label}
              </Link>
            ))}
          </div>
        </div>
        <OverviewCards metrics={display.metrics} loading={loading} />
      </section>

      <section>
        <div className="mb-4">
          <h2 className="text-lg xl:text-xl font-semibold text-content">App pulse</h2>
          <p className="text-sm xl:text-base text-content-muted mt-0.5">
            Live stats for each module — ready apps vs ones that still need a connection
          </p>
        </div>
        <ModuleHighlights highlights={display.highlights} loading={loading} />
      </section>

      <div className="grid gap-6 lg:grid-cols-5 xl:gap-8 2xl:grid-cols-12">
        <div className="lg:col-span-3 2xl:col-span-8 space-y-6">
          <section>
            <div className="mb-4">
              <h2 className="text-lg xl:text-xl font-semibold text-content">Your apps</h2>
              <p className="text-sm xl:text-base text-content-muted mt-0.5">
                Ready modules first, then anything waiting on Shopify or Gmail, then roadmap
              </p>
            </div>
            <AppModulesGrid />
          </section>

          <div className="flex flex-wrap gap-3 text-sm xl:text-base">
            <Link
              to="/settings/stores"
              className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 xl:px-4 xl:py-2.5 text-content-muted hover:bg-surface-muted hover:text-content transition-colors"
            >
              <Store className="h-4 w-4" />
              Manage stores
            </Link>
            <Link
              to="/settings/gmail"
              className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 xl:px-4 xl:py-2.5 text-content-muted hover:bg-surface-muted hover:text-content transition-colors"
            >
              <Mail className="h-4 w-4" />
              Manage Gmail
            </Link>
          </div>
        </div>
        <div className="lg:col-span-2 2xl:col-span-4 space-y-4">
          <ActivityFeed />
          <div className="rounded-xl border border-border bg-surface p-4 xl:p-5">
            <p className="text-xs xl:text-sm font-medium uppercase tracking-wide text-content-subtle mb-3">
              Quick launch
            </p>
            <div className="grid grid-cols-2 gap-2 xl:gap-3">
              {QUICK_LINKS.map((item) => (
                <Link
                  key={item.to}
                  to={item.to}
                  className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2.5 xl:px-4 xl:py-3 text-sm xl:text-base text-content hover:border-brand-500/40 hover:bg-brand-500/5 transition-colors"
                >
                  <item.icon className="h-4 w-4 xl:h-5 xl:w-5 text-brand-600" />
                  {item.label}
                </Link>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
