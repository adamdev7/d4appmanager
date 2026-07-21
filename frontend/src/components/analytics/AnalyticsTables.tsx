import { AlertTriangle, ArrowRight, CheckCircle2, Info, Lightbulb } from "lucide-react";
import type { AnalyticsDashboard, AnalyticsInsight } from "@/lib/analyticsTypes";
import { cn } from "@/lib/cn";
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
                  {currency} {c.spend.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </td>
                <td className="px-5 py-3 text-right text-content-muted">{c.purchases}</td>
                <td className="px-5 py-3 text-right text-content-muted">
                  {currency}{" "}
                  {c.purchase_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}
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
                  {c.cpa > 0 ? `${currency} ${c.cpa.toFixed(2)}` : "—"}
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
                  {currency} {p.revenue.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </td>
                <td className="px-5 py-3 text-right text-content">
                  {currency} {p.profit.toLocaleString(undefined, { minimumFractionDigits: 2 })}
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
  const sign = value < 0 ? "−" : "";
  return `${sign}${currency} ${Math.abs(value).toLocaleString(undefined, { minimumFractionDigits: 2 })}`;
}

export function ProfitBreakdown({
  summary,
  currency,
}: {
  summary: AnalyticsDashboard["summary"];
  currency: string;
}) {
  const shopifyRows = [
    ...(summary.prior_external_revenue > 0
      ? [
          {
            label: summary.prior_external_label || "Prior site (Stripe)",
            value: summary.prior_external_revenue,
            type: "positive" as const,
            source: "External",
          },
        ]
      : []),
    ...(summary.prior_external_costs > 0
      ? [
          {
            label: "Prior site costs",
            value: -summary.prior_external_costs,
            type: "negative" as const,
            source: "External",
          },
        ]
      : []),
    {
      label: "Shopify revenue",
      value: summary.shopify_revenue,
      type: "positive" as const,
      source: "Shopify",
    },
    {
      label: "Product costs (COGS)",
      value: -summary.cogs,
      type: "negative" as const,
      source: "Shopify",
    },
    {
      label: "Shipping",
      value: -summary.shipping_costs,
      type: "negative" as const,
      source: "Shopify",
    },
    {
      label: "Payment fees",
      value: -summary.transaction_fees,
      type: "negative" as const,
      source: "Shopify",
    },
    {
      label: "Gross profit",
      value: summary.gross_profit,
      type: "subtotal" as const,
      source: "Blended",
    },
    {
      label: "Meta ad spend",
      value: -summary.ad_spend,
      type: "negative" as const,
      source: "Meta",
    },
    {
      label: "Net profit",
      value: summary.net_profit,
      type: "total" as const,
      source: "Blended",
    },
  ];

  const hasMeta = summary.meta_purchase_value > 0 || summary.ad_spend > 0;
  const attributionNote =
    summary.shopify_revenue > 0 && summary.meta_purchase_value > 0
      ? `Meta tracks ${summary.attribution_coverage_pct}% of Shopify revenue`
      : summary.revenue_source === "meta_approx"
        ? "Revenue approximated from Meta purchase value"
        : null;
  const startNote = summary.analytics_start_date
    ? `Counting from ${summary.analytics_start_date} (Shopify launch / analytics start)`
    : null;

  return (
    <Card padding="lg">
      <CardHeader>
        <CardTitle>Profit Breakdown</CardTitle>
        <CardDescription>
          Shopify store P&amp;L combined with Meta ads spend and purchase value
        </CardDescription>
      </CardHeader>

      {/* Dual-source snapshot */}
      <div className="mb-4 grid grid-cols-2 gap-3">
        <div className="rounded-lg border border-border bg-surface-muted/40 p-3">
          <p className="text-xs font-medium uppercase tracking-wide text-content-muted">Shopify</p>
          <p className="mt-1 text-sm font-semibold text-content">
            {money(summary.shopify_revenue, currency)}
          </p>
          <p className="text-xs text-content-muted mt-0.5">
            {summary.orders} orders · AOV {money(summary.aov, currency)}
          </p>
        </div>
        <div className="rounded-lg border border-border bg-surface-muted/40 p-3">
          <p className="text-xs font-medium uppercase tracking-wide text-content-muted">Meta</p>
          <p className="mt-1 text-sm font-semibold text-content">
            {money(summary.meta_purchase_value, currency)}
          </p>
          <p className="text-xs text-content-muted mt-0.5">
            {summary.meta_purchases} purchases · ROAS {summary.meta_roas}x
          </p>
        </div>
      </div>

      {attributionNote && (
        <p className="mb-3 text-xs text-content-muted">{attributionNote}</p>
      )}
      {startNote && (
        <p className="mb-3 text-xs text-content-muted">{startNote}</p>
      )}

      <div className="space-y-2">
        {shopifyRows.map((row) => (
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
                "flex flex-col sm:flex-row sm:items-center sm:gap-2 min-w-0",
                row.type === "total" ? "text-content" : "text-content-muted",
                row.type === "subtotal" && "text-content"
              )}
            >
              <span className="truncate">{row.label}</span>
              <span className="text-[10px] uppercase tracking-wide text-content-subtle font-normal">
                {row.source}
              </span>
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

      {hasMeta && (
        <div className="mt-4 pt-4 border-t border-border space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-content-muted mb-2">
            Meta-attributed estimate
          </p>
          <div className="flex justify-between items-center text-sm">
            <span className="text-content-muted">Meta purchase value</span>
            <span className="text-content">{money(summary.meta_purchase_value, currency)}</span>
          </div>
          <div className="flex justify-between items-center text-sm">
            <span className="text-content-muted">
              Est. variable costs ({summary.variable_cost_rate_pct}%)
            </span>
            <span className="text-red-600 dark:text-red-400">
              {money(-(summary.meta_purchase_value - summary.meta_est_gross_profit), currency)}
            </span>
          </div>
          <div className="flex justify-between items-center text-sm">
            <span className="text-content-muted">Meta ad spend</span>
            <span className="text-red-600 dark:text-red-400">
              {money(-summary.ad_spend, currency)}
            </span>
          </div>
          <div className="flex justify-between items-center text-sm font-medium pt-2 border-t border-border">
            <span className="text-content">Est. Meta-attributed net</span>
            <span
              className={
                summary.meta_est_net_profit >= 0 ? "text-emerald-600" : "text-red-600"
              }
            >
              {money(summary.meta_est_net_profit, currency)}
            </span>
          </div>
        </div>
      )}

      <div className="mt-4 pt-4 border-t border-border grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
        <div>
          <p className="text-content-muted">Break-even ROAS</p>
          <p className="font-semibold text-content">{summary.break_even_roas}x</p>
        </div>
        <div>
          <p className="text-content-muted">Net margin</p>
          <p className="font-semibold text-content">{summary.net_margin_pct}%</p>
        </div>
        <div>
          <p className="text-content-muted">MER (Shopify)</p>
          <p className="font-semibold text-content">{summary.mer}x</p>
        </div>
        <div>
          <p className="text-content-muted">Meta ROAS</p>
          <p className="font-semibold text-content">{summary.meta_roas}x</p>
        </div>
      </div>
    </Card>
  );
}
