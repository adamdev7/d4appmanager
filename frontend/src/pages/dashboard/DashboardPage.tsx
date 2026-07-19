import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Settings, Store, Mail } from "lucide-react";
import { OverviewCards } from "@/components/dashboard/OverviewCards";
import { ActivityFeed } from "@/components/dashboard/ActivityFeed";
import { AppModulesGrid } from "@/components/dashboard/AppModulesGrid";
import { ModuleHighlights } from "@/components/dashboard/ModuleHighlights";
import { WorkspaceSetup } from "@/components/dashboard/WorkspaceSetup";
import { useStore } from "@/context/StoreContext";
import { Badge } from "@/components/ui/Badge";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { EMPTY_DASHBOARD_OVERVIEW, type DashboardOverview } from "@/lib/dashboardTypes";
import { cn } from "@/lib/cn";

export function DashboardPage() {
  const { activeStore } = useStore();
  const [overview, setOverview] = useState<DashboardOverview>(EMPTY_DASHBOARD_OVERVIEW);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.dashboard
      .overview(activeStore?.id)
      .then(setOverview)
      .catch(() => setOverview(EMPTY_DASHBOARD_OVERVIEW))
      .finally(() => setLoading(false));
  }, [activeStore?.id]);

  const setupIncomplete = overview.setup_steps.some((s) => !s.done);

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4"
      >
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-content">Overview</h1>
          <p className="mt-1 text-content-muted max-w-xl">
            {activeStore
              ? `Workspace for ${activeStore.name} — tracking, email flows, and AI replies in one place.`
              : "Your automation hub — connect Shopify and Gmail, then open any app below."}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {activeStore && (
            <Badge variant={activeStore.status === "connected" ? "success" : "warning"}>
              {activeStore.name} · {activeStore.currency}
            </Badge>
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

      {setupIncomplete && <WorkspaceSetup steps={overview.setup_steps} />}

      <section className={cn(loading && "opacity-70 transition-opacity")}>
        <h2 className="text-sm font-medium text-content-subtle uppercase tracking-wider mb-3">
          Workspace
        </h2>
        <OverviewCards metrics={overview.metrics} loading={loading} />
      </section>

      <section>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-semibold text-content">Active apps</h2>
            <p className="text-sm text-content-muted mt-0.5">
              Live modules — open for configuration and daily use
            </p>
          </div>
        </div>
        <ModuleHighlights highlights={overview.highlights} loading={loading} />
      </section>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-3 space-y-6">
          <section>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-semibold text-content">All apps</h2>
                <p className="text-sm text-content-muted mt-0.5">
                  Including upcoming Analytics, SMS, and Support
                </p>
              </div>
            </div>
            <AppModulesGrid />
          </section>

          <div className="flex flex-wrap gap-3 text-sm">
            <Link
              to="/settings/stores"
              className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-content-muted hover:bg-surface-muted hover:text-content transition-colors"
            >
              <Store className="h-4 w-4" />
              Stores
            </Link>
            <Link
              to="/settings/gmail"
              className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-content-muted hover:bg-surface-muted hover:text-content transition-colors"
            >
              <Mail className="h-4 w-4" />
              Gmail
            </Link>
          </div>
        </div>
        <div className="lg:col-span-2">
          <ActivityFeed />
        </div>
      </div>
    </div>
  );
}
