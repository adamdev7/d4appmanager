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
        <CardDescription>
          Beyond ROAS / CPC — metrics that change decisions
        </CardDescription>
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
  return (
    <Card padding="lg">
      <CardHeader>
        <CardTitle>Funnel health</CardTitle>
        <CardDescription>Where buyers leak — often not an ads targeting issue</CardDescription>
      </CardHeader>
      <div className="grid gap-3 sm:grid-cols-4">
        {steps.map((s) => (
          <div key={s.label} className="rounded-lg border border-border p-3 text-center">
            <p className="text-xs text-content-muted">{s.label}</p>
            <p className="mt-1 text-lg font-semibold text-content">{s.value.toLocaleString()}</p>
            {s.rate != null && (
              <p className="mt-0.5 text-xs text-content-subtle">{s.rate}% from prior</p>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}

function EntityTable({
  title,
  description,
  rows,
  currency,
  showCampaign,
}: {
  title: string;
  description: string;
  rows: AdsEntityRow[];
  currency: string;
  showCampaign?: boolean;
}) {
  return (
    <Card padding="lg">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <div className="overflow-x-auto -mx-1">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs text-content-muted">
              <th className="pb-2 pr-3 font-medium">Name</th>
              {showCampaign && <th className="pb-2 pr-3 font-medium">Campaign</th>}
              <th className="pb-2 pr-3 font-medium text-right">Spend</th>
              <th className="pb-2 pr-3 font-medium text-right">ROAS</th>
              <th className="pb-2 pr-3 font-medium text-right">CPA</th>
              <th className="pb-2 pr-3 font-medium text-right">Hook %</th>
              <th className="pb-2 pr-3 font-medium text-right">Out CTR</th>
              <th className="pb-2 font-medium text-right">Freq</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={showCampaign ? 8 : 7} className="py-6 text-center text-content-muted">
                  No data for this period
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr key={r.id || r.name} className="border-b border-border/60 last:border-0">
                  <td className="py-2.5 pr-3 font-medium text-content max-w-[220px] truncate">
                    {r.name || "—"}
                  </td>
                  {showCampaign && (
                    <td className="py-2.5 pr-3 text-content-muted max-w-[160px] truncate">
                      {r.campaign_name || "—"}
                    </td>
                  )}
                  <td className="py-2.5 pr-3 text-right tabular-nums">{formatMoney(r.spend, currency)}</td>
                  <td className="py-2.5 pr-3 text-right tabular-nums">{r.platform_roas.toFixed(2)}x</td>
                  <td className="py-2.5 pr-3 text-right tabular-nums">
                    {r.cpa > 0 ? formatMoney(r.cpa, currency) : "—"}
                  </td>
                  <td className="py-2.5 pr-3 text-right tabular-nums">{r.hook_rate.toFixed(1)}</td>
                  <td className="py-2.5 pr-3 text-right tabular-nums">{r.outbound_ctr.toFixed(2)}</td>
                  <td
                    className={cn(
                      "py-2.5 text-right tabular-nums",
                      r.frequency >= 3.5 && "text-amber-600 dark:text-amber-400 font-medium"
                    )}
                  >
                    {r.frequency.toFixed(2)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
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
  return (
    <EntityTable
      title="Campaigns"
      description="Efficiency by campaign — reallocate before scaling losers"
      rows={rows}
      currency={currency}
    />
  );
}

export function AdsCreativesTable({
  rows,
  currency,
}: {
  rows: AdsEntityRow[];
  currency: string;
}) {
  return (
    <EntityTable
      title="Ads / creatives"
      description="Hook rate + frequency beat vanity CTR for creative decisions"
      rows={rows}
      currency={currency}
      showCampaign
    />
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
        <CardDescription>
          1-day click vs 7-day click — your modeling delta
        </CardDescription>
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
