import { Link } from "react-router-dom";
import { Settings } from "lucide-react";
import { OverviewCards } from "@/components/dashboard/OverviewCards";
import { ActivityFeed } from "@/components/dashboard/ActivityFeed";
import { AppModulesGrid } from "@/components/dashboard/AppModulesGrid";
import { WorkspaceSetup } from "@/components/dashboard/WorkspaceSetup";
import { useStore } from "@/context/StoreContext";
import { Badge } from "@/components/ui/Badge";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { EMPTY_DASHBOARD_OVERVIEW, type DashboardOverview } from "@/lib/dashboardTypes";

export function DashboardPage() {
  const { activeStore, stores } = useStore();
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
  const setupIncomplete =
    !loading && overview != null && overview.setup_steps.some((s) => !s.done);
  const connectedStoreCount = stores.filter((s) => s.status === "connected").length;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <div className="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight text-content xl:text-2xl">
            Overview
          </h1>
          <p className="mt-0.5 truncate text-sm text-content-muted">
            {activeStore
              ? activeStore.name
              : "Connect a store to start using your apps."}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {activeStore && (
            <Badge variant={activeStore.status === "connected" ? "success" : "warning"}>
              {activeStore.status === "connected" ? "Store connected" : "Store pending"}
            </Badge>
          )}
          {connectedStoreCount > 1 && (
            <Badge variant="muted">{connectedStoreCount} stores</Badge>
          )}
          <Link
            to="/settings"
            className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm text-content-muted hover:bg-surface-muted hover:text-content"
          >
            <Settings className="h-3.5 w-3.5" />
            Settings
          </Link>
        </div>
      </div>

      {setupIncomplete && overview && <WorkspaceSetup steps={overview.setup_steps} />}

      <OverviewCards metrics={display.metrics} loading={loading} />

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,1fr)_20rem] xl:grid-cols-[minmax(0,1fr)_22rem] lg:[&>*]:min-h-0">
        <AppModulesGrid highlights={display.highlights} loadingHighlights={loading} />
        <ActivityFeed />
      </div>
    </div>
  );
}
