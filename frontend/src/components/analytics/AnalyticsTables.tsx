import { AlertTriangle, ArrowRight, CheckCircle2, Info, Lightbulb } from "lucide-react";
import type { AnalyticsDashboard, AnalyticsInsight } from "@/lib/analyticsTypes";
import { cn } from "@/lib/cn";
import { formatMoney } from "@/lib/formatMoney";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";

const levelStyles = {
  info: {
    icon: Info,
    border: "border-blue-500/20 bg-blue-500/5",
    iconColor: "text-blue-600 dark:text-blue-400",
  },
  warning: {
    icon: AlertTriangle,
    border: "border-amber-500/20 bg-amber-500/5",
    iconColor: "text-amber-600 dark:text-amber-400",
  },
  danger: {
    icon: AlertTriangle,
    border: "border-red-500/20 bg-red-500/5",
    iconColor: "text-red-600 dark:text-red-400",
  },
  success: {
    icon: CheckCircle2,
    border: "border-emerald-500/20 bg-emerald-500/5",
    iconColor: "text-emerald-600 dark:text-emerald-400",
  },
};

export function ProfitInsights({ insights }: { insights: AnalyticsInsight[] }) {
  if (!insights.length) return null;

  return (
    <Card padding="lg">
      <CardHeader>
        <div className="flex items-center gap-2">
          <Lightbulb className="h-5 w-5 text-brand-600" />
          <CardTitle>Profitability Insights</CardTitle>
        </div>
        <CardDescription>What to do next for higher profit</CardDescription>
      </CardHeader>
      <div className="space-y-3">
        {insights.map((insight, i) => {
          const style = levelStyles[insight.level];
          const Icon = style.icon;
          return (
            <div
              key={i}
              className={cn("flex gap-3 rounded-lg border p-4", style.border)}
            >
              <Icon className={cn("h-5 w-5 shrink-0 mt-0.5", style.iconColor)} />
              <div className="min-w-0 flex-1">
                <p className="font-medium text-content text-sm">{insight.title}</p>
                <p className="text-sm text-content-muted mt-0.5">{insight.message}</p>
                {insight.action && (
                  <p className="mt-2 flex items-start gap-1.5 text-sm font-medium text-content">
                    <ArrowRight className="h-4 w-4 shrink-0 mt-0.5 text-brand-600" />
                    <span>{insight.action}</span>
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

export function CampaignTable({
  campaigns,
  currency,
}: {
  campaigns: AnalyticsDashboard["campaigns"];
  currency: string;
}) {
  if (!campaigns.length) {
    return (
      <Card padding="lg">
        <CardHeader>
          <CardTitle>Meta Ad Campaigns</CardTitle>
          <CardDescription>Connect Meta Ads in Settings to see campaign performance</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card padding="none" className="overflow-hidden">
      <div className="p-5 pb-0">
        <CardTitle>Meta Ad Campaigns</CardTitle>
        <CardDescription>Performance by campaign for the selected period</CardDescription>
      </div>
      <div className="overflow-x-auto mt-4">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-y border-border bg-surface-muted/50 text-left text-content-muted">
              <th className="px-5 py-3 font-medium">Campaign</th>
              <th className="px-5 py-3 font-medium text-right">Spend</th>
              <th className="px-5 py-3 font-medium text-right">Purchases</th>
              <th className="px-5 py-3 font-medium text-right">Purchase value</th>
              <th className="px-5 py-3 font-medium text-right">ROAS</th>
              <th className="px-5 py-3 font-medium text-right">CPA</th>
              <th className="px-5 py-3 font-medium text-right">CTR</th>
            </tr>
          </thead>
          <tbody>
            {campaigns.map((c) => (
              <tr key={c.campaign_id} className="border-b border-border last:border-0">
                <td className="px-5 py-3 font-medium text-content max-w-[200px] truncate">
                  {c.campaign_name}
                </td>
                <td className="px-5 py-3 text-right text-content-muted">
                  {formatMoney(c.spend, currency)}
                </td>
                <td className="px-5 py-3 text-right text-content-muted">{c.purchases}</td>
                <td className="px-5 py-3 text-right text-content-muted">
                  {formatMoney(c.purchase_value, currency)}
                </td>
                <td className="px-5 py-3 text-right">
                  <span
                    className={cn(
                      "font-medium",
                      c.roas >= 2 ? "text-emerald-600" : c.roas >= 1 ? "text-amber-600" : "text-red-600"
                    )}
                  >
                    {c.roas}x
                  </span>
                </td>
                <td className="px-5 py-3 text-right text-content-muted">
                  {c.cpa > 0 ? formatMoney(c.cpa, currency) : "—"}
                </td>
                <td className="px-5 py-3 text-right text-content-muted">{c.ctr.toFixed(2)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export function TopProductsTable({
  products,
  currency,
}: {
  products: AnalyticsDashboard["top_products"];
  currency: string;
}) {
  if (!products.length) return null;

  return (
    <Card padding="none" className="overflow-hidden">
      <div className="p-5 pb-0">
        <CardTitle>Top Products by Revenue</CardTitle>
        <CardDescription>See which products drive sales and margin</CardDescription>
      </div>
      <div className="overflow-x-auto mt-4">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-y border-border bg-surface-muted/50 text-left text-content-muted">
              <th className="px-5 py-3 font-medium">Product</th>
              <th className="px-5 py-3 font-medium text-right">Units</th>
              <th className="px-5 py-3 font-medium text-right">Revenue</th>
              <th className="px-5 py-3 font-medium text-right">Profit</th>
              <th className="px-5 py-3 font-medium text-right">Margin</th>
            </tr>
          </thead>
          <tbody>
            {products.map((p, i) => (
              <tr key={i} className="border-b border-border last:border-0">
                <td className="px-5 py-3 font-medium text-content max-w-[220px] truncate">
                  {p.title}
                </td>
                <td className="px-5 py-3 text-right text-content-muted">{p.units_sold}</td>
                <td className="px-5 py-3 text-right text-content-muted">
                  {formatMoney(p.revenue, currency)}
                </td>
                <td className="px-5 py-3 text-right text-content">
                  {formatMoney(p.profit, currency)}
                </td>
                <td className="px-5 py-3 text-right">
                  <span
                    className={cn(
                      "font-medium",
                      p.margin_pct >= 50 ? "text-emerald-600" : p.margin_pct >= 25 ? "text-amber-600" : "text-content-muted"
                    )}
                  >
                    {p.margin_pct}%
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function money(value: number, currency: string) {
  return formatMoney(value, currency);
}

export function ProfitBreakdown({
  summary,
  currency,
}: {
  summary: AnalyticsDashboard["summary"];
  currency: string;
}) {
  const rows = [
    ...(summary.prior_external_revenue > 0
      ? [
          {
            label: summary.prior_external_label || "Prior site (Stripe)",
            value: summary.prior_external_revenue,
            type: "positive" as const,
          },
        ]
      : []),
    ...(summary.prior_external_costs > 0
      ? [
          {
            label: "Prior site costs",
            value: -summary.prior_external_costs,
            type: "negative" as const,
          },
        ]
      : []),
    {
      label:
        summary.revenue_source === "stripe"
          ? "Revenue (Stripe total, net of fees)"
          : "Revenue (orders + subscriptions)",
      value: summary.revenue - (summary.prior_external_revenue || 0),
      type: "positive" as const,
    },
    {
      label: "Product costs (COGS)",
      value: -summary.cogs,
      type: "negative" as const,
    },
    {
      label: "Shipping",
      value: -summary.shipping_costs,
      type: "negative" as const,
    },
    // Only subtract fees when revenue is still gross (Shopify). Stripe net already excludes fees.
    ...(!summary.fees_already_net && summary.transaction_fees > 0
      ? [
          {
            label:
              summary.stripe_fees && summary.stripe_fees > 0
                ? "Payment fees (Stripe)"
                : "Payment fees",
            value: -summary.transaction_fees,
            type: "negative" as const,
          },
        ]
      : []),
    {
      label: "Gross profit",
      value: summary.gross_profit,
      type: "subtotal" as const,
    },
    {
      label: "Meta ad spend",
      value: -summary.ad_spend,
      type: "negative" as const,
    },
    {
      label: "Net profit",
      value: summary.net_profit,
      type: "total" as const,
    },
  ];

  const startNote = summary.analytics_start_date
    ? `Counting from ${summary.analytics_start_date} (analytics start)`
    : null;
  const feeNote =
    summary.fees_already_net && (summary.stripe_fees || 0) > 0
      ? `Stripe fees of ${money(summary.stripe_fees || 0, currency)} are already removed from revenue — not deducted again.`
      : null;
  const stripeBreakdownNote =
    summary.revenue_source === "stripe"
      ? [
          (summary.stripe_subscription_net || 0) > 0
            ? `Subscriptions ${money(summary.stripe_subscription_net || 0, currency)} (${summary.stripe_subscription_charges ?? 0})`
            : null,
          (summary.stripe_one_time_net || 0) > 0
            ? `One-time ${money(summary.stripe_one_time_net || 0, currency)} (${summary.stripe_one_time_charges ?? 0})`
            : null,
        ]
          .filter(Boolean)
          .join(" · ")
      : null;

  return (
    <Card padding="lg">
      <CardHeader>
        <CardTitle>Profit Breakdown</CardTitle>
        <CardDescription>
          P&amp;L is in store currency. Stripe charges are converted with historical daily FX when
          needed; Meta ad spend is never converted to pounds. MRR stays in Stripe&apos;s currency.
        </CardDescription>
      </CardHeader>

      {startNote && <p className="mb-3 text-xs text-content-muted">{startNote}</p>}
      {feeNote && <p className="mb-3 text-xs text-content-muted">{feeNote}</p>}
      {stripeBreakdownNote && (
        <p className="mb-3 text-xs text-content-muted">Stripe mix: {stripeBreakdownNote}</p>
      )}

      <div className="space-y-2">
        {rows.map((row) => (
          <div
            key={row.label}
            className={cn(
              "flex justify-between items-center py-2 gap-3",
              row.type === "subtotal" && "border-t border-border pt-3 font-medium",
              row.type === "total" && "border-t-2 border-brand-500/30 pt-3 font-bold text-lg"
            )}
          >
            <span
              className={cn(
                "truncate",
                row.type === "total" ? "text-content" : "text-content-muted",
                row.type === "subtotal" && "text-content"
              )}
            >
              {row.label}
            </span>
            <span
              className={cn(
                "shrink-0",
                row.value >= 0 ? "text-content" : "text-red-600 dark:text-red-400",
                row.type === "total" && (row.value >= 0 ? "text-emerald-600" : "text-red-600")
              )}
            >
              {money(row.value, currency)}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-4 pt-4 border-t border-border grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
        <div>
          <p className="text-content-muted">Break-even MER</p>
          <p className="font-semibold text-content">{summary.break_even_roas}x</p>
        </div>
        <div>
          <p className="text-content-muted">Net margin</p>
          <p className="font-semibold text-content">{summary.net_margin_pct}%</p>
        </div>
        <div>
          <p className="text-content-muted">MER</p>
          <p className="font-semibold text-content">{summary.mer}x</p>
        </div>
      </div>
    </Card>
  );
}
