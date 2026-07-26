import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  Eye,
  Megaphone,
  RefreshCw,
  Settings2,
  Sparkles,
  Store,
  Target,
  TrendingUp,
  Wallet,
  Zap,
} from "lucide-react";
import { useStore } from "@/context/StoreContext";
import { api, type AdsDashboard, type AdsPeriod, type AdsSettings, type AdsAiReport } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatMoney } from "@/lib/formatMoney";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { MetricCard } from "@/components/analytics/MetricCard";
import { AdsCreativeHealthChart, AdsSpendCpmChart } from "@/components/ads/AdsCharts";
import {
  AdsAlertsPanel,
  AdsCampaignTable,
  AdsCreativesTable,
  AttributionPanel,
  FunnelPanel,
  MissedAnglesGrid,
} from "@/components/ads/AdsTables";
import { AdsSettingsPanel } from "@/components/ads/AdsSettingsPanel";

type Tab = "dashboard" | "reports" | "settings";

const TABS: Array<{ id: Tab; label: string; icon: typeof Megaphone }> = [
  { id: "dashboard", label: "Dashboard", icon: Megaphone },
  { id: "reports", label: "AI Reports", icon: Sparkles },
  { id: "settings", label: "Settings", icon: Settings2 },
];

const PERIODS: Array<{ id: AdsPeriod; label: string }> = [
  { id: "7d", label: "7 days" },
  { id: "30d", label: "30 days" },
  { id: "90d", label: "90 days" },
];

export function AdsPage() {
  const { activeStore, stores } = useStore();
  const storeId = activeStore?.id ?? stores[0]?.id ?? null;

  const [tab, setTab] = useState<Tab>("dashboard");
  const [period, setPeriod] = useState<AdsPeriod>("30d");
  const [dashboard, setDashboard] = useState<AdsDashboard | null>(null);
  const [settings, setSettings] = useState<AdsSettings | null>(null);
  const [reports, setReports] = useState<AdsAiReport[]>([]);
  const [activeReport, setActiveReport] = useState<AdsAiReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [reportError, setReportError] = useState("");

  const load = useCallback(async () => {
    if (!storeId) {
      setLoading(false);
      return;
    }
    setError("");
    try {
      const [dash, sett] = await Promise.all([
        api.ads.overview(storeId, period, true),
        api.ads.getSettings(storeId),
      ]);
      setDashboard(dash);
      setSettings(sett);
      if (dash.ai.latest_report) setActiveReport(dash.ai.latest_report);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load ads");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [storeId, period]);

  const loadReports = useCallback(async () => {
    if (!storeId) return;
    try {
      const list = await api.ads.listReports(storeId);
      setReports(list);
      if (list[0] && !activeReport) setActiveReport(list[0]);
    } catch {
      /* ignore */
    }
  }, [storeId, activeReport]);

  useEffect(() => {
    setLoading(true);
    load();
  }, [load]);

  useEffect(() => {
    if (tab === "reports") loadReports();
  }, [tab, loadReports]);

  const refresh = async () => {
    setRefreshing(true);
    await load();
  };

  const generateReport = async (reportType: "on_demand" | "daily" | "weekly" = "on_demand") => {
    if (!storeId) return;
    setGenerating(true);
    setReportError("");
    try {
      const report = await api.ads.generateReport(storeId, {
        report_type: reportType,
        period: reportType === "weekly" ? "30d" : "7d",
      });
      setActiveReport(report);
      setReports((prev) => [report, ...prev.filter((r) => r.id !== report.id)]);
      setTab("reports");
    } catch (err) {
      setReportError(err instanceof Error ? err.message : "Report generation failed");
    } finally {
      setGenerating(false);
    }
  };

  if (!storeId) {
    return (
      <div className="max-w-lg mx-auto mt-16 text-center space-y-4">
        <Store className="h-12 w-12 mx-auto text-content-muted" />
        <h1 className="text-xl font-semibold text-content">Connect a store first</h1>
        <p className="text-content-muted">
          Ads pulls Meta performance and compares it to Shopify revenue for MER and new-customer CAC.
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

  const currency = dashboard?.currency ?? "USD";
  const summary = dashboard?.summary;

  return (
    <div className="space-y-6 pb-10">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Megaphone className="h-5 w-5 text-brand-600" />
            <h1 className="text-2xl font-semibold tracking-tight text-content">Ads</h1>
            {dashboard?.meta_configured ? (
              <Badge variant="success">Live Meta</Badge>
            ) : (
              <Badge variant="warning">Setup required</Badge>
            )}
          </div>
          <p className="text-sm text-content-muted max-w-xl">
            E-commerce Meta dashboard focused on what shops usually miss: MER, hook rate, fatigue,
            outbound CTR, funnel leaks, and attribution gaps — not just ROAS.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {PERIODS.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => setPeriod(p.id)}
              className={cn(
                "h-9 rounded-lg px-3 text-sm font-medium transition-colors",
                period === p.id
                  ? "bg-brand-600 text-white"
                  : "bg-surface-muted text-content-muted hover:text-content"
              )}
            >
              {p.label}
            </button>
          ))}
          <Button variant="secondary" onClick={refresh} disabled={refreshing || loading}>
            <RefreshCw className={cn("h-4 w-4", refreshing && "animate-spin")} />
            Refresh
          </Button>
        </div>
      </div>

      <div className="flex gap-1 border-b border-border">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={cn(
                "inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors",
                tab === t.id
                  ? "border-brand-600 text-brand-700 dark:text-brand-400"
                  : "border-transparent text-content-muted hover:text-content"
              )}
            >
              <Icon className="h-4 w-4" />
              {t.label}
            </button>
          );
        })}
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-700 dark:text-red-300 flex gap-2">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
          {error}
        </div>
      )}

      {loading && !dashboard ? (
        <p className="text-sm text-content-muted">Loading live Meta ads…</p>
      ) : tab === "settings" ? (
        <AdsSettingsPanel storeId={storeId} settings={settings} onSaved={load} />
      ) : tab === "reports" ? (
        <div className="space-y-4">
          <Card padding="lg">
            <CardHeader>
              <CardTitle>AI campaign reports</CardTitle>
              <CardDescription>
                Uses your AI Email Assistant OpenAI key after you opt in under Settings.
              </CardDescription>
            </CardHeader>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => generateReport("on_demand")} disabled={generating}>
                <Sparkles className="h-4 w-4" />
                {generating ? "Analyzing…" : "Generate report now"}
              </Button>
              <Button
                variant="secondary"
                onClick={() => generateReport("weekly")}
                disabled={generating}
              >
                Weekly deep dive
              </Button>
            </div>
            {reportError && (
              <p className="mt-3 text-sm text-red-600 dark:text-red-400">{reportError}</p>
            )}
            {!settings?.ai_reports_consent && (
              <p className="mt-3 text-sm text-content-muted">
                Enable consent in{" "}
                <button
                  type="button"
                  className="text-brand-600 font-medium hover:underline"
                  onClick={() => setTab("settings")}
                >
                  Settings
                </button>{" "}
                first.
              </p>
            )}
          </Card>

          <div className="grid gap-4 lg:grid-cols-[240px_1fr]">
            <Card padding="md" className="h-fit">
              <p className="text-xs font-medium uppercase tracking-wide text-content-subtle mb-2">
                History
              </p>
              <ul className="space-y-1">
                {reports.length === 0 && (
                  <li className="text-sm text-content-muted py-2">No reports yet</li>
                )}
                {reports.map((r) => (
                  <li key={r.id}>
                    <button
                      type="button"
                      onClick={() => setActiveReport(r)}
                      className={cn(
                        "w-full text-left rounded-lg px-2.5 py-2 text-sm transition-colors",
                        activeReport?.id === r.id
                          ? "bg-brand-500/10 text-brand-700 dark:text-brand-400"
                          : "hover:bg-surface-muted text-content"
                      )}
                    >
                      <span className="font-medium block truncate">{r.title}</span>
                      <span className="text-xs text-content-muted">
                        {r.created_at
                          ? new Date(r.created_at).toLocaleString()
                          : r.report_type}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </Card>

            <Card padding="lg">
              {activeReport ? (
                <div className="prose prose-sm dark:prose-invert max-w-none">
                  <div className="not-prose mb-4 flex items-start justify-between gap-3">
                    <div>
                      <h2 className="text-lg font-semibold text-content">{activeReport.title}</h2>
                      <p className="text-xs text-content-muted mt-1">
                        {activeReport.model_used} · {activeReport.period} · {activeReport.report_type}
                      </p>
                    </div>
                    <Badge variant="brand">{activeReport.report_type.replace("_", " ")}</Badge>
                  </div>
                  {activeReport.summary && (
                    <p className="text-sm text-content-muted border-l-2 border-brand-500 pl-3 mb-4 not-prose">
                      {activeReport.summary}
                    </p>
                  )}
                  <div className="whitespace-pre-wrap text-sm text-content leading-relaxed">
                    {activeReport.body_markdown}
                  </div>
                </div>
              ) : (
                <p className="text-sm text-content-muted">Generate a report to see AI analysis here.</p>
              )}
            </Card>
          </div>
        </div>
      ) : !dashboard?.meta_configured ? (
        <Card padding="lg" className="max-w-xl">
          <CardHeader>
            <CardTitle>Connect Meta Ads</CardTitle>
            <CardDescription>
              Paste your Marketing API token and ad account ID to pull live campaigns, creatives,
              and delivery health.
            </CardDescription>
          </CardHeader>
          <Button onClick={() => setTab("settings")}>
            <Settings2 className="h-4 w-4" />
            Open Ads settings
          </Button>
        </Card>
      ) : (
        <div className="space-y-6">
          {dashboard.meta_error && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-sm text-amber-800 dark:text-amber-200">
              Meta API: {dashboard.meta_error}
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="Ad spend"
              value={formatMoney(summary?.spend ?? 0, currency)}
              icon={Wallet}
              hint={`${summary?.impressions?.toLocaleString() ?? 0} impressions`}
            />
            <MetricCard
              label="MER (store ÷ spend)"
              value={summary?.mer != null ? `${summary.mer.toFixed(2)}x` : "—"}
              icon={TrendingUp}
              accent="brand"
              hint={`Store revenue ${formatMoney(summary?.store_revenue ?? 0, currency)}`}
            />
            <MetricCard
              label="Platform ROAS"
              value={`${(summary?.platform_roas ?? 0).toFixed(2)}x`}
              icon={Target}
              hint="Directional only — compare to MER"
            />
            <MetricCard
              label="New customer CAC"
              value={
                summary?.blended_ncac != null
                  ? formatMoney(summary.blended_ncac, currency)
                  : "—"
              }
              icon={Zap}
              hint={`${summary?.new_customers ?? 0} new / ${summary?.returning_customers ?? 0} returning`}
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="Hook rate"
              value={`${(summary?.hook_rate ?? 0).toFixed(1)}%`}
              icon={Eye}
              accent={(summary?.hook_rate ?? 0) < 15 && (summary?.impressions ?? 0) > 5000 ? "warning" : "success"}
              hint="3s video plays ÷ impressions"
            />
            <MetricCard
              label="Frequency"
              value={(summary?.frequency ?? 0).toFixed(2)}
              accent={(summary?.frequency ?? 0) >= 3.5 ? "warning" : "default"}
              hint="Fatigue canary for cold audiences"
            />
            <MetricCard
              label="Outbound CTR"
              value={`${(summary?.outbound_ctr ?? 0).toFixed(2)}%`}
              hint="Real site interest (not all-clicks)"
            />
            <MetricCard
              label="CPA"
              value={
                summary?.cpa
                  ? formatMoney(summary.cpa, currency)
                  : "—"
              }
              hint={`${summary?.purchases ?? 0} Meta purchases`}
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              onClick={() => generateReport("on_demand")}
              disabled={generating || !settings?.ai_reports_consent}
            >
              <Sparkles className="h-4 w-4" />
              {generating ? "Analyzing…" : "AI analyze campaigns"}
            </Button>
            {!settings?.ai_reports_consent && (
              <button
                type="button"
                onClick={() => setTab("settings")}
                className="text-sm text-content-muted hover:text-brand-600"
              >
                Opt in to AI reports →
              </button>
            )}
          </div>

          {dashboard.missed_angles && <MissedAnglesGrid angles={dashboard.missed_angles} />}

          <div className="grid gap-4 lg:grid-cols-2">
            <AdsAlertsPanel alerts={dashboard.alerts} />
            <FunnelPanel funnel={dashboard.summary.funnel} />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <AdsSpendCpmChart data={dashboard.daily} currency={currency} />
            <AdsCreativeHealthChart data={dashboard.daily} />
          </div>

          <AttributionPanel attribution={dashboard.attribution} />

          <AdsCampaignTable rows={dashboard.campaigns} currency={currency} />
          <AdsCreativesTable rows={dashboard.ads.slice(0, 40)} currency={currency} />
        </div>
      )}
    </div>
  );
}
