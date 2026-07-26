import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  Calendar,
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
import { Input } from "@/components/ui/Input";
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
import { AdsReportTimeframeModal } from "@/components/ads/AdsReportTimeframeModal";

type Tab = "dashboard" | "reports" | "settings";

const TABS: Array<{ id: Tab; label: string; icon: typeof Megaphone }> = [
  { id: "dashboard", label: "Dashboard", icon: Megaphone },
  { id: "reports", label: "AI Reports", icon: Sparkles },
  { id: "settings", label: "Settings", icon: Settings2 },
];

const PERIODS: Array<{ id: Exclude<AdsPeriod, "custom">; label: string }> = [
  { id: "7d", label: "7 days" },
  { id: "30d", label: "30 days" },
  { id: "90d", label: "90 days" },
  { id: "all", label: "All time" },
];

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

export function AdsPage() {
  const { activeStore, stores } = useStore();
  const storeId = activeStore?.id ?? stores[0]?.id ?? null;

  const [tab, setTab] = useState<Tab>("dashboard");
  const [period, setPeriod] = useState<AdsPeriod>("30d");
  const [customSince, setCustomSince] = useState(daysAgoISO(29));
  const [customUntil, setCustomUntil] = useState(todayISO());
  const [appliedSince, setAppliedSince] = useState(daysAgoISO(29));
  const [appliedUntil, setAppliedUntil] = useState(todayISO());
  const [calendarOpen, setCalendarOpen] = useState(false);
  const calendarRef = useRef<HTMLDivElement>(null);
  const [dashboard, setDashboard] = useState<AdsDashboard | null>(null);
  const [settings, setSettings] = useState<AdsSettings | null>(null);
  const [reports, setReports] = useState<AdsAiReport[]>([]);
  const [activeReport, setActiveReport] = useState<AdsAiReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [reportModalOpen, setReportModalOpen] = useState(false);
  const [error, setError] = useState("");
  const [reportError, setReportError] = useState("");

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
        api.ads.overview(storeId, period, {
          runScheduled: true,
          since: period === "custom" ? appliedSince : undefined,
          until: period === "custom" ? appliedUntil : undefined,
        }),
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
  }, [storeId, period, appliedSince, appliedUntil]);

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

  const selectPreset = (id: Exclude<AdsPeriod, "custom">) => {
    setPeriod(id);
    setCalendarOpen(false);
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

  const openReportModal = () => {
    setReportError("");
    setReportModalOpen(true);
  };

  const generateReport = async (opts: {
    period: AdsPeriod;
    since?: string;
    until?: string;
  }) => {
    if (!storeId) return;
    setGenerating(true);
    setReportError("");
    try {
      const report = await api.ads.generateReport(storeId, {
        report_type: "on_demand",
        period: opts.period,
        since: opts.since,
        until: opts.until,
      });
      setActiveReport(report);
      setReports((prev) => [report, ...prev.filter((r) => r.id !== report.id)]);
      setReportModalOpen(false);
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
  const rangeHint =
    period === "custom"
      ? formatRangeLabel(appliedSince, appliedUntil)
      : dashboard?.since && dashboard?.until
        ? formatRangeLabel(dashboard.since, dashboard.until)
        : null;

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
          {rangeHint && <p className="mt-1 text-xs text-content-subtle">{rangeHint}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {PERIODS.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => selectPreset(p.id)}
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
          <div className="relative" ref={calendarRef}>
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
                "inline-flex h-9 w-9 items-center justify-center rounded-lg transition-colors",
                period === "custom" || calendarOpen
                  ? "bg-brand-600 text-white"
                  : "bg-surface-muted text-content-muted hover:text-content"
              )}
            >
              <Calendar className="h-4 w-4" />
            </button>
            {calendarOpen && (
              <div className="absolute right-0 z-30 mt-2 w-72 rounded-xl border border-border bg-surface p-4 shadow-elevated">
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
                Uses your AI Email Assistant OpenAI key after you opt in under Settings. Reports pull
                Meta ads plus Analytics revenue for the same timeframe — including MRR/Stripe when
                that shop is an MRR business.
              </CardDescription>
            </CardHeader>
            <div className="flex flex-wrap gap-2">
              <Button onClick={openReportModal} disabled={generating}>
                <Sparkles className="h-4 w-4" />
                {generating ? "Analyzing…" : "Generate report now"}
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
              onClick={openReportModal}
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

      <AdsReportTimeframeModal
        open={reportModalOpen}
        generating={generating}
        defaultPeriod={period}
        defaultSince={period === "custom" ? appliedSince : dashboard?.since}
        defaultUntil={period === "custom" ? appliedUntil : dashboard?.until}
        onClose={() => !generating && setReportModalOpen(false)}
        onConfirm={generateReport}
      />
    </div>
  );
}
