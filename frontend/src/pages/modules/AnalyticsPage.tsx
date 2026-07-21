import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  BarChart3,
  DollarSign,
  Megaphone,
  Package,
  RefreshCw,
  Settings2,
  ShoppingBag,
  Store,
  Target,
  TrendingUp,
  Wallet,
  Repeat,
} from "lucide-react";
import { useStore } from "@/context/StoreContext";
import { api, type AnalyticsDashboard, type AnalyticsPeriod, type AnalyticsSettings } from "@/lib/api";
import { cn } from "@/lib/cn";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardTitle } from "@/components/ui/Card";
import { MetricCard } from "@/components/analytics/MetricCard";
import { OrdersChart, ProfitChart, RevenueSpendChart } from "@/components/analytics/AnalyticsCharts";
import {
  CampaignTable,
  ProfitBreakdown,
  ProfitInsights,
  TopProductsTable,
} from "@/components/analytics/AnalyticsTables";
import { AnalyticsSettingsPanel } from "@/components/analytics/AnalyticsSettingsPanel";
import { ProductCostsPanel } from "@/components/analytics/ProductCostsPanel";

type Tab = "dashboard" | "products" | "settings";

const TABS: Array<{ id: Tab; label: string; icon: typeof BarChart3 }> = [
  { id: "dashboard", label: "Dashboard", icon: BarChart3 },
  { id: "products", label: "Product Costs", icon: Package },
  { id: "settings", label: "Settings", icon: Settings2 },
];

const PERIODS: Array<{ id: AnalyticsPeriod; label: string }> = [
  { id: "7d", label: "7 days" },
  { id: "30d", label: "30 days" },
  { id: "90d", label: "90 days" },
  { id: "all", label: "All time" },
];

function fmtMoney(value: number, currency: string) {
  return `${currency} ${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function AnalyticsPage() {
  const { activeStore, stores } = useStore();
  const storeId = activeStore?.id ?? stores[0]?.id ?? null;

  const [tab, setTab] = useState<Tab>("dashboard");
  const [period, setPeriod] = useState<AnalyticsPeriod>("30d");
  const [dashboard, setDashboard] = useState<AnalyticsDashboard | null>(null);
  const [settings, setSettings] = useState<AnalyticsSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!storeId) {
      setLoading(false);
      return;
    }
    setError("");
    try {
      const [dash, sett] = await Promise.all([
        api.analytics.overview(storeId, period),
        api.analytics.getSettings(storeId),
      ]);
      setDashboard(dash);
      setSettings(sett);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load analytics");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [storeId, period]);

  useEffect(() => {
    setLoading(true);
    load();
  }, [load]);

  const refresh = async () => {
    setRefreshing(true);
    await load();
  };

  if (!storeId) {
    return (
      <div className="max-w-lg mx-auto mt-16 text-center space-y-4">
        <Store className="h-12 w-12 mx-auto text-content-muted" />
        <h1 className="text-xl font-semibold text-content">Connect a store first</h1>
        <p className="text-content-muted">
          Analytics needs a connected Shopify store to pull orders and product data.
        </p>
        <Link
          to="/settings/stores"
          className="inline-flex h-10 items-center justify-center rounded-lg bg-brand-600 px-4 text-sm font-medium text-white hover:bg-brand-700"
        >
          Connect Shopify store
        </Link>
      </div>
    );
  }

  const currency = dashboard?.currency ?? settings?.currency ?? "USD";
  const summary = dashboard?.summary;

  return (
    <div className="space-y-6 pb-10">
      {/* Header */}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <Link
            to="/dashboard"
            className="inline-flex items-center gap-1.5 text-sm text-content-muted hover:text-content mb-3"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to overview
          </Link>
          <h1 className="text-2xl font-bold text-content tracking-tight">Store Analytics</h1>
          <p className="text-content-muted mt-1 max-w-xl">
            Triple Whale-style profitability dashboard — Shopify revenue and Meta ad spend in one
            place, with real net profit tracking.
          </p>
          {dashboard?.date_range && (
            <p className="text-xs text-content-subtle mt-2">
              {dashboard.date_range.since} → {dashboard.date_range.until}
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {dashboard?.connections && (
            <>
              <Badge variant={dashboard.connections.shopify ? "success" : "warning"}>
                Shopify {dashboard.connections.shopify ? "connected" : "missing"}
              </Badge>
              <Badge variant={dashboard.connections.meta ? "success" : "muted"}>
                Meta Ads {dashboard.connections.meta ? "connected" : "not set"}
              </Badge>
            </>
          )}
          <Button variant="outline" size="sm" onClick={refresh} disabled={refreshing}>
            <RefreshCw className={cn("h-4 w-4 mr-1.5", refreshing && "animate-spin")} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 rounded-xl bg-surface-muted border border-border w-fit">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={cn(
              "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors",
              tab === id
                ? "bg-surface text-content shadow-sm"
                : "text-content-muted hover:text-content"
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      {error && (
        <Card padding="md" className="border-red-500/30 bg-red-500/5">
          <p className="text-sm text-red-600">{error}</p>
        </Card>
      )}

      {tab === "settings" && (
        <AnalyticsSettingsPanel
          storeId={storeId}
          settings={settings}
          onSaved={() => load()}
        />
      )}

      {tab === "products" && (
        <ProductCostsPanel storeId={storeId} currency={currency} />
      )}

      {tab === "dashboard" && (
        <>
          {/* Period selector */}
          <div className="flex gap-2">
            {PERIODS.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => setPeriod(p.id)}
                className={cn(
                  "px-4 py-2 rounded-lg text-sm font-medium border transition-colors",
                  period === p.id
                    ? "bg-brand-600 text-white border-brand-600"
                    : "border-border text-content-muted hover:border-border-strong hover:text-content"
                )}
              >
                {p.label}
              </button>
            ))}
          </div>

          {loading ? (
            <Card padding="lg">
              <p className="text-content-muted text-sm">Loading analytics…</p>
            </Card>
          ) : dashboard && summary ? (
            <div className="space-y-6">
              {dashboard.connections.meta_error && (
                <Card padding="md" className="border-amber-500/30 bg-amber-500/5">
                  <p className="text-sm text-amber-700 dark:text-amber-400">
                    Meta Ads: {dashboard.connections.meta_error}
                  </p>
                </Card>
              )}

              {/* Hero KPIs */}
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <MetricCard
                  label="Net Profit"
                  value={fmtMoney(summary.net_profit, currency)}
                  hint="After COGS, fees, shipping & ads"
                  icon={Wallet}
                  accent={summary.net_profit >= 0 ? "success" : "danger"}
                  trend={summary.net_profit >= 0 ? "up" : "down"}
                  trendLabel={`${summary.net_margin_pct}% net margin`}
                />
                <MetricCard
                  label={
                    summary.revenue_source === "meta_approx"
                      ? "Approx. Revenue (Meta)"
                      : "Revenue"
                  }
                  value={fmtMoney(summary.revenue, currency)}
                  hint={
                    summary.revenue_source === "meta_approx"
                      ? `${summary.meta_purchases} Meta purchases · est. from purchase value`
                      : `${summary.orders} orders · AOV ${fmtMoney(summary.aov, currency)}`
                  }
                  icon={ShoppingBag}
                  accent="brand"
                />
                <MetricCard
                  label="Ad Spend"
                  value={fmtMoney(summary.ad_spend, currency)}
                  hint={
                    summary.ad_spend > 0
                      ? `Meta ROAS ${summary.meta_roas}x · CPA ${fmtMoney(summary.meta_cpa || summary.cpa, currency)}`
                      : "Connect Meta in Settings"
                  }
                  icon={Megaphone}
                />
                <MetricCard
                  label="MER / Meta ROAS"
                  value={`${summary.mer}x / ${summary.meta_roas}x`}
                  hint={`Break-even: ${summary.break_even_roas}x ROAS`}
                  icon={Target}
                  accent={
                    (summary.meta_roas || summary.mer) >= summary.break_even_roas &&
                    summary.break_even_roas > 0
                      ? "success"
                      : summary.ad_spend > 0
                        ? "warning"
                        : "default"
                  }
                />
              </div>

              {/* Secondary KPIs */}
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <MetricCard
                  label="Gross Profit"
                  value={fmtMoney(summary.gross_profit, currency)}
                  hint={`${summary.margin_before_ads_pct}% margin before ads`}
                  icon={TrendingUp}
                />
                <MetricCard
                  label="Meta Purchase Value"
                  value={fmtMoney(summary.meta_purchase_value, currency)}
                  hint={
                    summary.shopify_revenue > 0
                      ? `${summary.attribution_coverage_pct}% of Shopify revenue`
                      : `${summary.meta_purchases} tracked purchases`
                  }
                  icon={DollarSign}
                />
                <MetricCard
                  label="Meta Funnel"
                  value={`${summary.meta_add_to_cart} ATC`}
                  hint={`${summary.meta_initiate_checkout} checkouts · ${summary.checkout_to_purchase_pct}% convert`}
                  icon={BarChart3}
                />
                <MetricCard
                  label="Meta CTR / CPC"
                  value={`${summary.ctr}%`}
                  hint={`${summary.clicks.toLocaleString()} clicks · CPC ${fmtMoney(summary.cpc, currency)}`}
                  icon={Package}
                />
              </div>

              {dashboard.mrr && (
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <Repeat className="h-4 w-4 text-brand-600" />
                    <h2 className="text-sm font-semibold text-content">Subscription MRR</h2>
                    <Badge variant="muted">{dashboard.mrr.source}</Badge>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    <MetricCard
                      label="MRR"
                      value={fmtMoney(dashboard.mrr.mrr, currency)}
                      hint={
                        dashboard.mrr.mrr_delta !== 0
                          ? `${dashboard.mrr.mrr_delta >= 0 ? "+" : ""}${fmtMoney(dashboard.mrr.mrr_delta, currency)} vs last snapshot`
                          : "Update in Analytics Settings"
                      }
                      icon={Repeat}
                      accent="brand"
                      trend={dashboard.mrr.mrr_delta >= 0 ? "up" : "down"}
                      trendLabel={`${dashboard.mrr.subscribers} subscribers`}
                    />
                    <MetricCard
                      label="ARR"
                      value={fmtMoney(dashboard.mrr.arr, currency)}
                      hint="MRR × 12"
                      icon={TrendingUp}
                    />
                    <MetricCard
                      label="ARPU"
                      value={fmtMoney(dashboard.mrr.arpu, currency)}
                      hint="Average revenue per subscriber / month"
                      icon={Wallet}
                    />
                    <MetricCard
                      label="Churn"
                      value={`${dashboard.mrr.churn_pct}%`}
                      hint={
                        dashboard.mrr.last_synced_at
                          ? `Synced ${dashboard.mrr.last_synced_at.slice(0, 10)}`
                          : "Enter churn in Settings"
                      }
                      icon={Target}
                      accent={dashboard.mrr.churn_pct >= 8 ? "warning" : "default"}
                    />
                  </div>
                </div>
              )}

              {/* Insights */}
              <ProfitInsights insights={dashboard.insights} />

              {/* Charts */}
              <div className="grid gap-6 xl:grid-cols-2">
                <RevenueSpendChart
                  data={dashboard.daily_chart}
                  currency={currency}
                  granularity={dashboard.chart_granularity}
                />
                <ProfitChart
                  data={dashboard.daily_chart}
                  currency={currency}
                  granularity={dashboard.chart_granularity}
                />
              </div>

              <OrdersChart data={dashboard.daily_chart} granularity={dashboard.chart_granularity} />

              {/* Tables & breakdown */}
              <div className="grid gap-6 xl:grid-cols-2">
                <ProfitBreakdown summary={summary} currency={currency} />
                <TopProductsTable products={dashboard.top_products} currency={currency} />
              </div>

              <CampaignTable campaigns={dashboard.campaigns} currency={currency} />

              {dashboard.recent_orders.length > 0 && (
                <Card padding="none" className="overflow-hidden">
                  <div className="p-5 pb-0">
                    <CardTitle>Recent Orders — Profit Snapshot</CardTitle>
                    <CardDescription>Per-order estimated profit for quick review</CardDescription>
                  </div>
                  <div className="overflow-x-auto mt-4">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-y border-border bg-surface-muted/50 text-left text-content-muted">
                          <th className="px-5 py-3 font-medium">Order</th>
                          <th className="px-5 py-3 font-medium text-right">Total</th>
                          <th className="px-5 py-3 font-medium text-right">COGS</th>
                          <th className="px-5 py-3 font-medium text-right">Est. Profit</th>
                        </tr>
                      </thead>
                      <tbody>
                        {dashboard.recent_orders.map((o) => (
                          <tr key={o.order_number + o.created_at} className="border-b border-border last:border-0">
                            <td className="px-5 py-3 font-medium text-content">{o.order_number}</td>
                            <td className="px-5 py-3 text-right text-content-muted">
                              {fmtMoney(o.total, currency)}
                            </td>
                            <td className="px-5 py-3 text-right text-content-muted">
                              {fmtMoney(o.cogs, currency)}
                            </td>
                            <td
                              className={cn(
                                "px-5 py-3 text-right font-medium",
                                o.profit >= 0 ? "text-emerald-600" : "text-red-600"
                              )}
                            >
                              {fmtMoney(o.profit, currency)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              )}
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
