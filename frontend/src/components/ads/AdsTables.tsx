import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Search, Sparkles, TriangleAlert } from "lucide-react";
import { formatMoney } from "@/lib/formatMoney";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/cn";
import type { AdsAlert, AdsDashboard, AdsEntityRow, AdsMissedAngle } from "@/lib/adsTypes";

function severityBadge(s: AdsAlert["severity"]) {
  if (s === "danger") return "warning" as const;
  if (s === "warning") return "warning" as const;
  return "brand" as const;
}

export function AdsAlertsPanel({ alerts }: { alerts: AdsAlert[] }) {
  if (!alerts.length) {
    return (
      <Card padding="lg">
        <CardHeader>
          <CardTitle>Needs checking</CardTitle>
          <CardDescription>No major red flags in this period</CardDescription>
        </CardHeader>
        <p className="text-sm text-content-muted">Keep watching frequency and hook rate as you scale.</p>
      </Card>
    );
  }
  return (
    <Card padding="lg">
      <CardHeader>
        <CardTitle>Needs checking</CardTitle>
        <CardDescription>Signals most shops miss until CPA already rose</CardDescription>
      </CardHeader>
      <ul className="space-y-3">
        {alerts.map((a) => (
          <li
            key={`${a.code}-${a.title}`}
            className={cn(
              "rounded-lg border p-3",
              a.severity === "danger" && "border-red-500/25 bg-red-500/5",
              a.severity === "warning" && "border-amber-500/25 bg-amber-500/5",
              a.severity === "info" && "border-brand-500/20 bg-brand-500/5"
            )}
          >
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm font-medium text-content">{a.title}</p>
              <Badge variant={severityBadge(a.severity)} className="capitalize shrink-0">
                {a.severity}
              </Badge>
            </div>
            <p className="mt-1 text-xs text-content-muted leading-relaxed">{a.message}</p>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function MissedAnglesGrid({ angles }: { angles: AdsMissedAngle[] }) {
  return (
    <Card padding="lg">
      <CardHeader>
        <CardTitle>Angles most e-com shops miss</CardTitle>
        <CardDescription>Beyond ROAS / CPC — metrics that change decisions</CardDescription>
      </CardHeader>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {angles.map((a) => (
          <div key={a.id} className="rounded-lg border border-border bg-surface-muted/40 p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-content-subtle">{a.title}</p>
            <p className="mt-1 text-xl font-semibold text-content">{a.value}</p>
            <p className="mt-1 text-xs text-content-muted">{a.compare}</p>
            <p className="mt-2 text-xs leading-relaxed text-content-subtle">{a.why}</p>
          </div>
        ))}
      </div>
    </Card>
  );
}

export function FunnelPanel({
  funnel,
}: {
  funnel: AdsDashboard["summary"]["funnel"];
}) {
  const steps = [
    { label: "View content", value: funnel.view_content || funnel.landing_page_views },
    { label: "Add to cart", value: funnel.add_to_cart, rate: funnel.view_to_cart_pct },
    { label: "Checkout", value: funnel.initiate_checkout, rate: funnel.cart_to_checkout_pct },
    { label: "Purchase", value: funnel.purchases, rate: funnel.checkout_to_purchase_pct },
  ];
  const max = Math.max(...steps.map((s) => s.value), 1);
  return (
    <Card padding="lg">
      <CardHeader>
        <CardTitle>Funnel health</CardTitle>
        <CardDescription>Where buyers leak — often not an ads targeting issue</CardDescription>
      </CardHeader>
      <div className="grid gap-3 sm:grid-cols-4">
        {steps.map((s) => (
          <div key={s.label} className="rounded-lg border border-border p-3">
            <p className="text-xs text-content-muted">{s.label}</p>
            <p className="mt-1 text-lg font-semibold text-content">{s.value.toLocaleString()}</p>
            {s.rate != null && (
              <p className="mt-0.5 text-xs text-content-subtle">{s.rate}% from prior</p>
            )}
            <div className="mt-2 h-1.5 rounded-full bg-surface-muted overflow-hidden">
              <div
                className="h-full rounded-full bg-brand-500"
                style={{ width: `${Math.max(6, (s.value / max) * 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

function statusVariant(status?: string): "success" | "muted" | "warning" | "default" {
  const s = (status || "").toLowerCase();
  if (s === "active") return "success";
  if (s === "paused" || s === "archived") return "muted";
  if (s === "issues" || s === "disapproved") return "warning";
  return "default";
}

type SortKey =
  | "name"
  | "status"
  | "purchases"
  | "cpa"
  | "spend"
  | "impressions"
  | "cpc"
  | "cpm"
  | "ctr"
  | "purchase_value"
  | "platform_roas"
  | "hook_rate"
  | "outbound_ctr"
  | "frequency";

type LevelTab = "campaigns" | "adsets" | "ads";

const LEVELS: Array<{ id: LevelTab; label: string }> = [
  { id: "campaigns", label: "Campaigns" },
  { id: "adsets", label: "Ad sets" },
  { id: "ads", label: "Ads" },
];

export function AdsPerformanceTable({
  campaigns,
  adsets,
  ads,
  currency,
}: {
  campaigns: AdsEntityRow[];
  adsets: AdsEntityRow[];
  ads: AdsEntityRow[];
  currency: string;
}) {
  const [level, setLevel] = useState<LevelTab>("campaigns");
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("spend");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const source = level === "campaigns" ? campaigns : level === "adsets" ? adsets : ads;

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = q
      ? source.filter(
          (r) =>
            r.name.toLowerCase().includes(q) ||
            (r.campaign_name || "").toLowerCase().includes(q) ||
            (r.status || "").toLowerCase().includes(q)
        )
      : source;
    const sorted = [...filtered].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      const cmp =
        typeof av === "string" && typeof bv === "string"
          ? av.localeCompare(bv)
          : Number(av || 0) - Number(bv || 0);
      return sortDir === "asc" ? cmp : -cmp;
    });
    return sorted;
  }, [source, query, sortKey, sortDir]);

  const totals = useMemo(() => {
    return rows.reduce(
      (acc, r) => {
        acc.spend += r.spend;
        acc.impressions += r.impressions;
        acc.purchases += r.purchases;
        acc.purchase_value += r.purchase_value;
        acc.clicks += r.clicks;
        acc.outbound_clicks += r.outbound_clicks;
        acc.reach += r.reach;
        return acc;
      },
      { spend: 0, impressions: 0, purchases: 0, purchase_value: 0, clicks: 0, outbound_clicks: 0, reach: 0 }
    );
  }, [rows]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDir(key === "name" || key === "status" ? "asc" : "desc");
  };

  const SortHead = ({
    k,
    label,
    align = "right",
    title,
  }: {
    k: SortKey;
    label: string;
    align?: "left" | "right";
    title?: string;
  }) => (
    <th className={cn("pb-2 pr-3 font-medium whitespace-nowrap", align === "right" && "text-right")}>
      <button
        type="button"
        title={title}
        onClick={() => toggleSort(k)}
        className="inline-flex items-center gap-1 hover:text-content"
      >
        {label}
        {sortKey === k &&
          (sortDir === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
      </button>
    </th>
  );

  return (
    <Card padding="lg">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between mb-4">
        <div>
          <CardTitle>Performance</CardTitle>
          <CardDescription>
            Same columns as Ads Manager (link CPC / link CTR) — billed in {currency}. Click headers to sort.
          </CardDescription>
        </div>
        <div className="relative w-full sm:w-64">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-content-subtle" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search name or status"
            className="h-9 w-full rounded-lg border border-border bg-surface pl-9 pr-3 text-sm text-content placeholder:text-content-subtle focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30"
          />
        </div>
      </div>

      <div className="flex gap-1 border-b border-border mb-3">
        {LEVELS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => {
              setLevel(tab.id);
              setQuery("");
            }}
            className={cn(
              "px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
              level === tab.id
                ? "border-brand-600 text-brand-700 dark:text-brand-400"
                : "border-transparent text-content-muted hover:text-content"
            )}
          >
            {tab.label}
            <span className="ml-1.5 text-xs text-content-subtle">
              {tab.id === "campaigns" ? campaigns.length : tab.id === "adsets" ? adsets.length : ads.length}
            </span>
          </button>
        ))}
      </div>

      <div className="overflow-x-auto -mx-1">
        <table className="w-full min-w-[980px] text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs text-content-muted">
              <SortHead k="name" label="Name" align="left" />
              <SortHead k="status" label="Delivery" align="left" />
              {level !== "campaigns" && (
                <th className="pb-2 pr-3 font-medium">Campaign</th>
              )}
              <SortHead k="purchases" label="Results" />
              <SortHead k="cpa" label="Cost / result" />
              <SortHead k="spend" label="Amount spent" />
              <SortHead k="impressions" label="Impressions" />
              <SortHead k="cpc" label="CPC" title="Cost per link click" />
              <SortHead k="cpm" label="CPM" />
              <SortHead k="ctr" label="CTR" title="Link click-through rate" />
              <SortHead k="purchase_value" label="Result value" />
              <SortHead k="platform_roas" label="ROAS" />
              <SortHead k="hook_rate" label="Hook %" />
              <SortHead k="frequency" label="Freq" />
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={level === "campaigns" ? 13 : 14} className="py-8 text-center text-content-muted">
                  No {level} in this period
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr key={r.id || r.name} className="border-b border-border/60 last:border-0">
                  <td className="py-2.5 pr-3 font-medium text-content max-w-[220px] truncate">
                    {r.name || "—"}
                  </td>
                  <td className="py-2.5 pr-3">
                    <Badge variant={statusVariant(r.status)}>{r.status || "—"}</Badge>
                  </td>
                  {level !== "campaigns" && (
                    <td className="py-2.5 pr-3 text-content-muted max-w-[140px] truncate">
                      {r.campaign_name || "—"}
                    </td>
                  )}
                  <td className="py-2.5 pr-3 text-right tabular-nums">{r.purchases || "—"}</td>
                  <td className="py-2.5 pr-3 text-right tabular-nums whitespace-nowrap">
                    {r.cpa > 0 ? formatMoney(r.cpa, currency) : "—"}
                  </td>
                  <td className="py-2.5 pr-3 text-right tabular-nums whitespace-nowrap font-medium">
                    {formatMoney(r.spend, currency)}
                  </td>
                  <td className="py-2.5 pr-3 text-right tabular-nums">
                    {r.impressions.toLocaleString()}
                  </td>
                  <td className="py-2.5 pr-3 text-right tabular-nums whitespace-nowrap">
                    {r.cpc > 0 ? formatMoney(r.cpc, currency) : "—"}
                  </td>
                  <td className="py-2.5 pr-3 text-right tabular-nums whitespace-nowrap">
                    {r.cpm > 0 ? formatMoney(r.cpm, currency) : "—"}
                  </td>
                  <td className="py-2.5 pr-3 text-right tabular-nums">
                    {r.impressions > 0 ? `${r.ctr.toFixed(2)}%` : "—"}
                  </td>
                  <td className="py-2.5 pr-3 text-right tabular-nums whitespace-nowrap">
                    {r.purchase_value > 0 ? formatMoney(r.purchase_value, currency) : "—"}
                  </td>
                  <td
                    className={cn(
                      "py-2.5 pr-3 text-right tabular-nums font-medium",
                      r.platform_roas >= 2
                        ? "text-emerald-600 dark:text-emerald-400"
                        : r.platform_roas >= 1
                          ? "text-amber-600 dark:text-amber-400"
                          : r.spend > 0
                            ? "text-red-600 dark:text-red-400"
                            : "text-content-muted"
                    )}
                  >
                    {r.spend > 0 ? `${r.platform_roas.toFixed(2)}x` : "—"}
                  </td>
                  <td className="py-2.5 pr-3 text-right tabular-nums">
                    {r.hook_rate > 0 ? r.hook_rate.toFixed(1) : "—"}
                  </td>
                  <td
                    className={cn(
                      "py-2.5 text-right tabular-nums",
                      r.frequency >= 3.5 && "text-amber-600 dark:text-amber-400 font-medium"
                    )}
                  >
                    {r.frequency > 0 ? r.frequency.toFixed(2) : "—"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
          {rows.length > 0 && (
            <tfoot>
              <tr className="border-t border-border bg-surface-muted/40 text-sm font-medium">
                <td className="py-2.5 pr-3" colSpan={level === "campaigns" ? 2 : 3}>
                  Results from {rows.length} {level}
                </td>
                <td className="py-2.5 pr-3 text-right tabular-nums">{totals.purchases}</td>
                <td className="py-2.5 pr-3 text-right tabular-nums whitespace-nowrap">
                  {totals.purchases > 0 ? formatMoney(totals.spend / totals.purchases, currency) : "—"}
                </td>
                <td className="py-2.5 pr-3 text-right tabular-nums whitespace-nowrap">
                  {formatMoney(totals.spend, currency)}
                </td>
                <td className="py-2.5 pr-3 text-right tabular-nums">
                  {totals.impressions.toLocaleString()}
                </td>
                <td className="py-2.5 pr-3 text-right tabular-nums whitespace-nowrap">
                  {totals.outbound_clicks > 0
                    ? formatMoney(totals.spend / totals.outbound_clicks, currency)
                    : totals.clicks > 0
                      ? formatMoney(totals.spend / totals.clicks, currency)
                      : "—"}
                </td>
                <td className="py-2.5 pr-3 text-right tabular-nums whitespace-nowrap">
                  {totals.impressions > 0
                    ? formatMoney((totals.spend / totals.impressions) * 1000, currency)
                    : "—"}
                </td>
                <td className="py-2.5 pr-3 text-right tabular-nums">
                  {totals.impressions > 0
                    ? `${(((totals.outbound_clicks || totals.clicks) / totals.impressions) * 100).toFixed(2)}%`
                    : "—"}
                </td>
                <td className="py-2.5 pr-3 text-right tabular-nums whitespace-nowrap">
                  {formatMoney(totals.purchase_value, currency)}
                </td>
                <td className="py-2.5 pr-3 text-right tabular-nums">
                  {totals.spend > 0 ? `${(totals.purchase_value / totals.spend).toFixed(2)}x` : "—"}
                </td>
                <td colSpan={2} />
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </Card>
  );
}

export function AdsCampaignTable({
  rows,
  currency,
}: {
  rows: AdsEntityRow[];
  currency: string;
}) {
  return <AdsPerformanceTable campaigns={rows} adsets={[]} ads={[]} currency={currency} />;
}

export function AdsCreativesTable({
  rows,
  currency,
}: {
  rows: AdsEntityRow[];
  currency: string;
}) {
  return <AdsPerformanceTable campaigns={[]} adsets={[]} ads={rows} currency={currency} />;
}

export function AdsSpotlightRow({
  winners,
  needsCheck,
  currency,
}: {
  winners: AdsEntityRow[];
  needsCheck: AdsEntityRow[];
  currency: string;
}) {
  if (!winners.length && !needsCheck.length) return null;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card padding="lg">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-brand-600" />
            <CardTitle>Winning creatives</CardTitle>
          </div>
          <CardDescription>Highest ROAS / hook among ads with meaningful spend</CardDescription>
        </CardHeader>
        <ul className="space-y-2">
          {winners.length === 0 && (
            <li className="text-sm text-content-muted">Not enough spend to rank winners yet.</li>
          )}
          {winners.map((a) => (
            <li key={a.id} className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2">
              <div className="min-w-0">
                <p className="text-sm font-medium text-content truncate">{a.name}</p>
                <p className="text-xs text-content-muted">
                  {formatMoney(a.spend, currency)} · hook {a.hook_rate.toFixed(1)}%
                </p>
              </div>
              <span className="text-sm font-semibold text-emerald-600 dark:text-emerald-400 shrink-0">
                {a.platform_roas.toFixed(2)}x
              </span>
            </li>
          ))}
        </ul>
      </Card>
      <Card padding="lg">
        <CardHeader>
          <div className="flex items-center gap-2">
            <TriangleAlert className="h-4 w-4 text-amber-500" />
            <CardTitle>Refresh these ads</CardTitle>
          </div>
          <CardDescription>High frequency or weak ROAS — pause or iterate before scaling</CardDescription>
        </CardHeader>
        <ul className="space-y-2">
          {needsCheck.length === 0 && (
            <li className="text-sm text-content-muted">No fatigued creatives in this window.</li>
          )}
          {needsCheck.map((a) => (
            <li key={a.id} className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2">
              <div className="min-w-0">
                <p className="text-sm font-medium text-content truncate">{a.name}</p>
                <p className="text-xs text-content-muted">
                  Freq {a.frequency.toFixed(2)} · {formatMoney(a.spend, currency)}
                </p>
              </div>
              <span className="text-sm font-semibold text-amber-600 dark:text-amber-400 shrink-0">
                {a.platform_roas.toFixed(2)}x
              </span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

export function AttributionPanel({
  attribution,
}: {
  attribution: AdsDashboard["attribution"];
}) {
  return (
    <Card padding="lg">
      <CardHeader>
        <CardTitle>Attribution window gap</CardTitle>
        <CardDescription>1-day click vs 7-day click — your modeling delta</CardDescription>
      </CardHeader>
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg border border-border p-3">
          <p className="text-xs text-content-muted">1d click purchases</p>
          <p className="mt-1 text-lg font-semibold">{attribution.purchases_1d_click}</p>
        </div>
        <div className="rounded-lg border border-border p-3">
          <p className="text-xs text-content-muted">7d click purchases</p>
          <p className="mt-1 text-lg font-semibold">{attribution.purchases_7d_click}</p>
        </div>
        <div className="rounded-lg border border-border p-3">
          <p className="text-xs text-content-muted">Gap (7d vs 1d)</p>
          <p className="mt-1 text-lg font-semibold">
            {attribution.gap_7d_vs_1d_pct ? `+${attribution.gap_7d_vs_1d_pct}%` : "—"}
          </p>
          <p className="text-xs text-content-subtle mt-0.5">
            View-through (1d): {attribution.purchases_1d_view}
          </p>
        </div>
      </div>
    </Card>
  );
}
