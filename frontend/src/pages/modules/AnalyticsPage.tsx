import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  AlertTriangle,
  BarChart3,
  Calendar,
  Megaphone,
  Package,
  RefreshCw,
  Settings2,
  ShieldAlert,
  ShoppingBag,
  Store,
  Target,
  TrendingUp,
  Wallet,
  Repeat,
  Landmark,
  ChevronDown,
} from "lucide-react";
import { useStore } from "@/context/StoreContext";
import { api, type AnalyticsDashboard, type AnalyticsPeriod, type AnalyticsSettings } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatMoney } from "@/lib/formatMoney";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
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
import { ManualInvestmentPanel } from "@/components/analytics/ManualInvestmentPanel";

type Tab = "dashboard" | "products" | "investments" | "settings";

const TABS: Array<{ id: Tab; label: string; icon: typeof BarChart3 }> = [
  { id: "dashboard", label: "Dashboard", icon: BarChart3 },
  { id: "products", label: "Product Costs", icon: Package },
  { id: "investments", label: "Investments", icon: Landmark },
  { id: "settings", label: "Settings", icon: Settings2 },
];

const PERIODS: Array<{ id: Exclude<AnalyticsPeriod, "custom">; label: string }> = [
  { id: "7d", label: "7 days" },
  { id: "30d", label: "30 days" },
  { id: "90d", label: "90 days" },
  { id: "all", label: "All time" },
];

const DISPLAY_CURRENCIES = ["USD", "CAD", "GBP"] as const;

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function daysAgoISO(days: number) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

function formatRangeLabel(since: string, until: string) {
  try {
    const fmt = (s: string) =>
      new Date(s + "T12:00:00").toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    return `${fmt(since)} – ${fmt(until)}`;
  } catch {
    return `${since} – ${until}`;
  }
}

export function AnalyticsPage() {
  const { activeStore, stores } = useStore();
  const storeId = activeStore?.id ?? stores[0]?.id ?? null;

  const [tab, setTab] = useState<Tab>("dashboard");
  const [period, setPeriod] = useState<AnalyticsPeriod>("30d");
  const [customSince, setCustomSince] = useState(daysAgoISO(29));
  const [customUntil, setCustomUntil] = useState(todayISO());
  const [appliedSince, setAppliedSince] = useState(daysAgoISO(29));
  const [appliedUntil, setAppliedUntil] = useState(todayISO());
  const [calendarOpen, setCalendarOpen] = useState(false);
  const calendarRef = useRef<HTMLDivElement>(null);
  const [dashboard, setDashboard] = useState<AnalyticsDashboard | null>(null);
  const [settings, setSettings] = useState<AnalyticsSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [holdBreakdownOpen, setHoldBreakdownOpen] = useState(false);
  const [savingCurrency, setSavingCurrency] = useState(false);

  const load = useCallback(async () => {
    if (!storeId) {
      setLoading(false);
      return;
    }
    if (period === "custom" && (!appliedSince || !appliedUntil)) {
      setLoading(false);
      return;
    }
    setError("");
    try {
      const [dash, sett] = await Promise.all([
        api.analytics.overview(storeId, period, {
          since: period === "custom" ? appliedSince : undefined,
          until: period === "custom" ? appliedUntil : undefined,
        }),
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
  }, [storeId, period, appliedSince, appliedUntil]);

  useEffect(() => {
    setLoading(true);
    load();
  }, [load]);

  useEffect(() => {
    if (!calendarOpen) return;
    const onPointer = (e: MouseEvent) => {
      if (calendarRef.current && !calendarRef.current.contains(e.target as Node)) {
        setCalendarOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setCalendarOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [calendarOpen]);

  const refresh = async () => {
    setRefreshing(true);
    await load();
  };

  const selectPreset = (id: Exclude<AnalyticsPeriod, "custom">) => {
    setPeriod(id);
    setCalendarOpen(false);
    setHoldBreakdownOpen(false);
  };

  const applyCustomRange = () => {
    if (!customSince || !customUntil) {
      setError("Pick both a start and end date");
      return;
    }
    if (customSince > customUntil) {
      setError("Start date must be on or before end date");
      return;
    }
    setError("");
    setAppliedSince(customSince);
    setAppliedUntil(customUntil);
    setPeriod("custom");
    setCalendarOpen(false);
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

  const currency = dashboard?.currency ?? settings?.display_currency ?? settings?.currency ?? "USD";
  const storeCurrency = dashboard?.store_currency ?? settings?.currency ?? currency;
  const mrrCurrency = dashboard?.mrr?.currency || currency;

  const setDisplayCurrency = async (code: string) => {
    if (!storeId || savingCurrency || code === currency) return;
    setSavingCurrency(true);
    setError("");
    try {
      await api.analytics.updateSettings(storeId, { display_currency: code });
      setRefreshing(true);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update currency");
    } finally {
      setSavingCurrency(false);
    }
  };

  const summary = dashboard?.summary;
  const stripeBalance = summary?.stripe_balance;
  const balanceHolds = stripeBalance?.holds ?? [];
  const holdsSum =
    balanceHolds.length > 0 ? balanceHolds.reduce((sum, h) => sum + h.amount, 0) : 0;
  const balanceHoldTotal =
    stripeBalance?.reserve_total != null && stripeBalance.reserve_total > 0
      ? stripeBalance.reserve_total
      : holdsSum;
  const balanceHoldDays = balanceHolds.length === 1 ? balanceHolds[0].days : null;
  // Only show when Stripe risk reserve exists — never use pending settlement as "on hold"
  const showBalanceHold = !!stripeBalance && balanceHoldTotal > 0;
  const rangeHint =
    period === "custom"
      ? formatRangeLabel(appliedSince, appliedUntil)
      : dashboard?.date_range
        ? formatRangeLabel(dashboard.date_range.since, dashboard.date_range.until)
        : null;

  return (
    <div className="space-y-6 pb-10 w-full min-w-0 overflow-x-hidden">
      {/* Header */}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <Link
            to="/dashboard"
            className="inline-flex items-center gap-1.5 text-sm text-content-muted hover:text-content mb-3"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to overview
          </Link>
          <h1 className="text-2xl xl:text-3xl font-bold text-content tracking-tight">
            Store Analytics
          </h1>
          <p className="text-content-muted mt-1 max-w-2xl text-sm sm:text-base xl:text-lg">
            Triple Whale-style profitability dashboard — Shopify revenue and Meta ad spend in one
            place, with real net profit tracking.
          </p>
          {rangeHint && (
            <p className="text-xs text-content-subtle mt-2 break-words">{rangeHint}</p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 shrink-0">
          {dashboard?.connections && (
            <>
              <Badge variant={dashboard.connections.shopify ? "success" : "warning"}>
                Shopify {dashboard.connections.shopify ? "connected" : "missing"}
              </Badge>
              <Badge variant={dashboard.connections.meta ? "success" : "muted"}>
                Meta Ads {dashboard.connections.meta ? "connected" : "not set"}
              </Badge>
              <Badge variant={dashboard.connections.stripe ? "success" : "muted"}>
                Stripe {dashboard.connections.stripe ? "connected" : "not set"}
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
      <div className="flex gap-1 p-1 rounded-xl bg-surface-muted border border-border w-full max-w-full overflow-x-auto">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={cn(
              "flex items-center gap-2 px-3 sm:px-4 py-2 rounded-lg text-sm font-medium transition-colors shrink-0 whitespace-nowrap",
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
        <ProductCostsPanel storeId={storeId} currency={storeCurrency} />
      )}

      {tab === "investments" && (
        <ManualInvestmentPanel storeId={storeId} currency={storeCurrency} onChanged={() => load()} />
      )}

      {tab === "dashboard" && (
        <>
          {/* Period + currency selectors */}
          <div className="flex flex-wrap items-center gap-2">
            {PERIODS.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => selectPreset(p.id)}
                className={cn(
                  "px-3 sm:px-4 py-2 rounded-lg text-sm font-medium border transition-colors shrink-0",
                  period === p.id
                    ? "bg-brand-600 text-white border-brand-600"
                    : "border-border text-content-muted hover:border-border-strong hover:text-content"
                )}
              >
                {p.label}
              </button>
            ))}
            <div className="relative ml-auto sm:ml-0" ref={calendarRef}>
              <button
                type="button"
                onClick={() => {
                  setCustomSince(period === "custom" ? appliedSince : daysAgoISO(29));
                  setCustomUntil(period === "custom" ? appliedUntil : todayISO());
                  setCalendarOpen((o) => !o);
                }}
                title="Custom date range"
                aria-label="Custom date range"
                aria-expanded={calendarOpen}
                className={cn(
                  "inline-flex h-9 w-9 items-center justify-center rounded-lg border transition-colors",
                  period === "custom" || calendarOpen
                    ? "bg-brand-600 text-white border-brand-600"
                    : "border-border text-content-muted hover:border-border-strong hover:text-content"
                )}
              >
                <Calendar className="h-4 w-4" />
              </button>
              {calendarOpen && (
                <div className="absolute right-0 z-30 mt-2 w-72 max-w-[calc(100vw-1.5rem)] rounded-xl border border-border bg-surface p-4 shadow-elevated">
                  <p className="text-sm font-medium text-content mb-3">Custom range</p>
                  <div className="space-y-3">
                    <Input
                      label="From"
                      type="date"
                      value={customSince}
                      max={customUntil || todayISO()}
                      onChange={(e) => setCustomSince(e.target.value)}
                    />
                    <Input
                      label="To"
                      type="date"
                      value={customUntil}
                      min={customSince}
                      max={todayISO()}
                      onChange={(e) => setCustomUntil(e.target.value)}
                    />
                    <Button className="w-full" onClick={applyCustomRange}>
                      Apply range
                    </Button>
                  </div>
                </div>
              )}
            </div>
            <div className="flex items-center gap-1 sm:ml-auto border border-border rounded-lg p-0.5">
              {DISPLAY_CURRENCIES.map((code) => (
                <button
                  key={code}
                  type="button"
                  disabled={savingCurrency}
                  onClick={() => setDisplayCurrency(code)}
                  title={`Show analytics in ${code}`}
                  className={cn(
                    "px-2.5 py-1.5 rounded-md text-xs font-semibold transition-colors",
                    currency === code
                      ? "bg-brand-600 text-white"
                      : "text-content-muted hover:text-content"
                  )}
                >
                  {code}
                </button>
              ))}
            </div>
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
              <div className="grid gap-3 sm:gap-4 grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 [&>*]:min-w-0">
                <MetricCard
                  label="Net Profit"
                  value={formatMoney(summary.net_profit, currency)}
                  hint={
                    summary.revenue_source === "stripe" || summary.revenue_source === "stripe_mrr"
                      ? `Stripe revenue − ads (${currency})`
                      : "Revenue − COGS − fees − shipping − ads"
                  }
                  icon={Wallet}
                  accent={summary.net_profit >= 0 ? "success" : "danger"}
                  trend={summary.net_profit >= 0 ? "up" : "down"}
                  trendLabel={`${summary.net_margin_pct}% net margin`}
                />
                <MetricCard
                  label="Revenue"
                  value={formatMoney(summary.revenue, currency)}
                  hint={
                    summary.revenue_source === "stripe"
                      ? `Stripe settlement net (${currency}) · gross ${formatMoney(summary.stripe_revenue_gross || 0, currency)} · ${summary.stripe_charges ?? 0} charges`
                      : `${summary.orders} orders · AOV ${formatMoney(summary.aov, storeCurrency)}`
                  }
                  icon={ShoppingBag}
                  accent="brand"
                />
                <MetricCard
                  label="Ad Spend"
                  value={formatMoney(summary.ad_spend, currency)}
                  hint={
                    summary.ad_spend > 0
                      ? [
                          `CPA ${formatMoney(summary.cpa || 0, currency)}`,
                          summary.ad_spend_native != null && currency !== "CAD"
                            ? `native ${formatMoney(summary.ad_spend_native, "CAD")}`
                            : "Meta billed in CAD",
                        ].join(" · ")
                      : "Connect Meta in Settings"
                  }
                  icon={Megaphone}
                />
                <MetricCard
                  label="MER"
                  value={`${summary.mer}x`}
                  hint={`Break-even ${summary.break_even_roas}x · revenue ÷ ad spend`}
                  icon={Target}
                  accent={
                    summary.mer >= summary.break_even_roas && summary.break_even_roas > 0
                      ? "success"
                      : summary.ad_spend > 0
                        ? "warning"
                        : "default"
                  }
                />
              </div>

              {/* Secondary KPIs */}
              <div className="grid gap-3 sm:gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 [&>*]:min-w-0">
                <MetricCard
                  label="Gross Profit"
                  value={formatMoney(summary.gross_profit, currency)}
                  hint={`${summary.margin_before_ads_pct}% margin before ads`}
                  icon={TrendingUp}
                />
                <MetricCard
                  label="Orders / Charges"
                  value={String(summary.orders || summary.stripe_charges || 0)}
                  hint={`AOV ${formatMoney(summary.aov, currency)}`}
                  icon={ShoppingBag}
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
                  hint={`${summary.clicks.toLocaleString()} clicks · CPC ${formatMoney(summary.cpc, currency)}`}
                  icon={Package}
                />
              </div>

              {stripeBalance && dashboard.connections.stripe && (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Wallet className="h-4 w-4 text-brand-600" />
                    <h2 className="text-sm font-semibold text-content">Stripe Balance</h2>
                    <Badge variant="muted">{currency}</Badge>
                    {stripeBalance.delay_days != null && (
                      <Badge variant="muted">{stripeBalance.delay_days}-day settlement</Badge>
                    )}
                  </div>
                  <div
                    className={cn(
                      "grid gap-3 sm:gap-4 grid-cols-1 sm:grid-cols-2 [&>*]:min-w-0",
                      showBalanceHold ? "lg:grid-cols-3" : "lg:grid-cols-2",
                    )}
                  >
                    <MetricCard
                      label="Available to withdraw"
                      value={formatMoney(stripeBalance.available, currency)}
                      hint={
                        stripeBalance.native_currency &&
                        stripeBalance.native_currency !== currency &&
                        stripeBalance.native_available != null
                          ? `Native ${formatMoney(stripeBalance.native_available, stripeBalance.native_currency)}`
                          : "Ready for payout to your bank"
                      }
                      icon={Wallet}
                      accent={stripeBalance.available > 0 ? "success" : "default"}
                    />
                    <MetricCard
                      label="Pending balance"
                      value={formatMoney(stripeBalance.pending, currency)}
                      hint={
                        stripeBalance.delay_days != null && stripeBalance.pending > 0
                          ? `Settles on a ~${stripeBalance.delay_days}-day rolling basis`
                          : stripeBalance.native_currency &&
                              stripeBalance.native_currency !== currency &&
                              stripeBalance.native_pending != null
                            ? `Native ${formatMoney(stripeBalance.native_pending, stripeBalance.native_currency)}`
                            : "Not yet available to withdraw"
                      }
                      icon={Calendar}
                      accent={stripeBalance.pending > 0 ? "warning" : "default"}
                    />
                    {showBalanceHold && (
                      <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4 sm:p-5 shadow-card min-w-0 overflow-hidden">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-content-muted">
                              {balanceHoldDays != null
                                ? `Risk reserve · ${balanceHoldDays} day${balanceHoldDays === 1 ? "" : "s"}`
                                : "Risk reserve"}
                            </p>
                            {balanceHolds.length > 0 ? (
                              <button
                                type="button"
                                onClick={() => setHoldBreakdownOpen((o) => !o)}
                                aria-expanded={holdBreakdownOpen}
                                className="mt-1 inline-flex max-w-full min-w-0 items-center gap-1.5 text-left text-xl sm:text-2xl font-bold tracking-tight text-content hover:text-brand-600 transition-colors"
                              >
                                <span className="min-w-0 break-words">
                                  {formatMoney(balanceHoldTotal, currency)}
                                </span>
                                <ChevronDown
                                  className={cn(
                                    "h-4 w-4 shrink-0 text-content-muted transition-transform",
                                    holdBreakdownOpen && "rotate-180",
                                  )}
                                />
                              </button>
                            ) : (
                              <p className="mt-1 text-xl sm:text-2xl font-bold tracking-tight text-content break-words">
                                {formatMoney(balanceHoldTotal, currency)}
                              </p>
                            )}
                            <p className="mt-1 text-xs text-content-subtle">
                              {holdBreakdownOpen
                                ? "Click amount to hide release schedule"
                                : "Stripe risk reserve (Réserve pour risque) — not pending payments"}
                            </p>
                            {holdBreakdownOpen && balanceHolds.length > 0 && (
                              <ul className="mt-3 space-y-1.5 border-t border-border/60 pt-3">
                                {balanceHolds.map((h) => (
                                  <li
                                    key={h.days}
                                    className="flex justify-between gap-3 text-xs text-content-muted"
                                  >
                                    <span>
                                      Releases in {h.days} day{h.days === 1 ? "" : "s"}
                                    </span>
                                    <span className="font-medium tabular-nums text-content">
                                      {formatMoney(h.amount, currency)}
                                    </span>
                                  </li>
                                ))}
                              </ul>
                            )}
                          </div>
                          <div className="rounded-lg bg-surface-muted p-2.5 shrink-0">
                            <AlertTriangle className="h-5 w-5 text-brand-600 dark:text-brand-400" />
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {summary.chargebacks && dashboard.connections.stripe && (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <ShieldAlert className="h-4 w-4 text-amber-600" />
                    <h2 className="text-sm font-semibold text-content">Chargebacks &amp; Disputes</h2>
                    <Badge variant="muted">{currency}</Badge>
                    {summary.chargebacks.count === 0 && <Badge variant="success">None</Badge>}
                  </div>
                  <div className="grid gap-3 sm:gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 [&>*]:min-w-0">
                    <MetricCard
                      label="Disputed amount"
                      value={formatMoney(summary.chargebacks.amount, currency)}
                      hint={
                        summary.chargebacks.count > 0
                          ? `${summary.chargebacks.rate_pct}% of Stripe gross · ${summary.chargebacks.count} dispute(s)`
                          : "No disputes in this period"
                      }
                      icon={ShieldAlert}
                      accent={
                        summary.chargebacks.rate_pct >= 1
                          ? "danger"
                          : summary.chargebacks.count > 0
                            ? "warning"
                            : "default"
                      }
                    />
                    <MetricCard
                      label="Open"
                      value={String(summary.chargebacks.open_count)}
                      hint={formatMoney(summary.chargebacks.open_amount, currency)}
                      icon={AlertTriangle}
                      accent={summary.chargebacks.open_count > 0 ? "warning" : "default"}
                    />
                    <MetricCard
                      label="Lost"
                      value={String(summary.chargebacks.lost_count)}
                      hint={formatMoney(summary.chargebacks.lost_amount, currency)}
                      icon={ShieldAlert}
                      accent={summary.chargebacks.lost_count > 0 ? "danger" : "default"}
                    />
                    <MetricCard
                      label="Won"
                      value={String(summary.chargebacks.won_count)}
                      hint={formatMoney(summary.chargebacks.won_amount, currency)}
                      icon={TrendingUp}
                      accent={summary.chargebacks.won_count > 0 ? "success" : "default"}
                    />
                  </div>
                  {summary.chargebacks.reasons &&
                    Object.keys(summary.chargebacks.reasons).length > 0 && (
                      <p className="text-xs text-content-muted">
                        Reasons:{" "}
                        {Object.entries(summary.chargebacks.reasons)
                          .map(([reason, n]) => `${reason.replace(/_/g, " ")} (${n})`)
                          .join(" · ")}
                      </p>
                    )}
                </div>
              )}

              {dashboard.mrr && (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Repeat className="h-4 w-4 text-brand-600" />
                    <h2 className="text-sm font-semibold text-content">Subscription MRR (Stripe)</h2>
                    <Badge variant="muted">{dashboard.mrr.source}</Badge>
                    <Badge variant="muted">{mrrCurrency}</Badge>
                  </div>
                  {dashboard.mrr.mrr_native != null &&
                    dashboard.mrr.native_currency &&
                    dashboard.mrr.native_currency !== mrrCurrency &&
                    dashboard.mrr.fx_rate != null && (
                      <p className="text-xs text-content-muted">
                        {formatMoney(dashboard.mrr.mrr_native, dashboard.mrr.native_currency)}{" "}
                        {dashboard.mrr.native_currency} → {formatMoney(dashboard.mrr.mrr, mrrCurrency)}{" "}
                        {mrrCurrency} at FX {dashboard.mrr.fx_rate.toFixed(4)}
                      </p>
                    )}
                  {dashboard.mrr.fx_error && (
                    <p className="text-xs text-amber-700 dark:text-amber-400">
                      FX conversion failed — showing native Stripe amount. {dashboard.mrr.fx_error}
                    </p>
                  )}
                  <div className="grid gap-3 sm:gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 [&>*]:min-w-0">
                    <MetricCard
                      label="MRR"
                      value={formatMoney(dashboard.mrr.mrr, mrrCurrency)}
                      hint={
                        dashboard.mrr.mrr_delta !== 0
                          ? `${dashboard.mrr.mrr_delta >= 0 ? "+" : ""}${formatMoney(dashboard.mrr.mrr_delta, mrrCurrency)} vs last snapshot`
                          : dashboard.mrr.native_currency &&
                              dashboard.mrr.native_currency !== mrrCurrency
                            ? `Converted from ${dashboard.mrr.native_currency} at latest FX`
                            : "From Stripe Billing / charges"
                      }
                      icon={Repeat}
                      accent="brand"
                      trend={dashboard.mrr.mrr_delta >= 0 ? "up" : "down"}
                      trendLabel={`${dashboard.mrr.subscribers.toLocaleString()} subscribers`}
                    />
                    <MetricCard
                      label="Subscribers"
                      value={dashboard.mrr.subscribers.toLocaleString()}
                      hint="Unique Stripe customers (active / past due / trial)"
                      icon={Wallet}
                    />
                    <MetricCard
                      label="ARR"
                      value={formatMoney(dashboard.mrr.arr, mrrCurrency)}
                      hint="MRR × 12"
                      icon={TrendingUp}
                    />
                    <MetricCard
                      label="ARPU"
                      value={formatMoney(dashboard.mrr.arpu, mrrCurrency)}
                      hint={
                        dashboard.mrr.last_synced_at
                          ? `Synced ${dashboard.mrr.last_synced_at.slice(0, 10)}`
                          : "Avg revenue per subscriber / month"
                      }
                      icon={Target}
                    />
                  </div>
                </div>
              )}

              {dashboard.connections.stripe_error && (
                <Card padding="md" className="border-amber-500/30 bg-amber-500/5">
                  <p className="text-sm text-amber-700 dark:text-amber-400">
                    Stripe: {dashboard.connections.stripe_error}
                  </p>
                </Card>
              )}

              {summary.stripe_fx_note && (
                <Card padding="md" className="border-border bg-surface-muted/40">
                  <p className="text-sm text-content-muted">
                    {summary.stripe_fx_note}
                    {summary.stripe_revenue_native != null && summary.stripe_currency
                      ? ` · Stripe native ${formatMoney(summary.stripe_revenue_native, summary.stripe_currency)}`
                      : ""}
                    {summary.ad_spend_native != null && currency !== "CAD"
                      ? ` · Meta native ${formatMoney(summary.ad_spend_native, "CAD")}`
                      : summary.ad_spend_native != null
                        ? " · Meta billed in CAD"
                        : ""}
                  </p>
                </Card>
              )}

              {currency !== storeCurrency && !summary.stripe_fx_note && (
                <Card padding="md" className="border-border bg-surface-muted/40">
                  <p className="text-sm text-content-muted">
                    Showing {currency}
                    {currency !== "CAD" ? " · Meta Ads from CAD" : ""}
                    {storeCurrency !== currency ? ` · Shopify from ${storeCurrency}` : ""}
                    .
                  </p>
                </Card>
              )}

              {/* Insights */}
              <ProfitInsights insights={dashboard.insights} />

              {/* Charts */}
              <div className="grid gap-4 xl:grid-cols-2 [&>*]:min-w-0">
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
              <div className="grid gap-4 xl:grid-cols-2 [&>*]:min-w-0">
                <ProfitBreakdown summary={summary} currency={currency} />
                <TopProductsTable products={dashboard.top_products} currency={currency} />
              </div>

              <CampaignTable campaigns={dashboard.campaigns} currency={currency} />

              {dashboard.recent_orders.length > 0 && (
                <Card padding="none" className="min-w-0 overflow-hidden">
                  <div className="p-4 sm:p-5 pb-0">
                    <CardTitle>Recent Orders — Profit Snapshot</CardTitle>
                    <CardDescription>Per-order estimated profit for quick review</CardDescription>
                  </div>
                  <div className="overflow-x-auto mt-4">
                    <table className="w-full min-w-[420px] text-sm">
                      <thead>
                        <tr className="border-y border-border bg-surface-muted/50 text-left text-content-muted">
                          <th className="px-3 sm:px-5 py-3 font-medium">Order</th>
                          <th className="px-3 sm:px-5 py-3 font-medium text-right">Total</th>
                          <th className="px-3 sm:px-5 py-3 font-medium text-right">COGS</th>
                          <th className="px-3 sm:px-5 py-3 font-medium text-right">Est. Profit</th>
                        </tr>
                      </thead>
                      <tbody>
                        {dashboard.recent_orders.map((o) => (
                          <tr key={o.order_number + o.created_at} className="border-b border-border last:border-0">
                            <td className="px-3 sm:px-5 py-3 font-medium text-content">{o.order_number}</td>
                            <td className="px-3 sm:px-5 py-3 text-right text-content-muted whitespace-nowrap">
                              {formatMoney(o.total, currency)}
                            </td>
                            <td className="px-3 sm:px-5 py-3 text-right text-content-muted whitespace-nowrap">
                              {formatMoney(o.cogs, currency)}
                            </td>
                            <td
                              className={cn(
                                "px-3 sm:px-5 py-3 text-right font-medium whitespace-nowrap",
                                o.profit >= 0 ? "text-emerald-600" : "text-red-600"
                              )}
                            >
                              {formatMoney(o.profit, currency)}
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
