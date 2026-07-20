import { AlertTriangle, CheckCircle2, Info, Lightbulb } from "lucide-react";
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
        <CardDescription>Actionable recommendations based on your data</CardDescription>
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
              <div>
                <p className="font-medium text-content text-sm">{insight.title}</p>
                <p className="text-sm text-content-muted mt-0.5">{insight.message}</p>
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

export function ProfitBreakdown({
  summary,
  currency,
}: {
  summary: AnalyticsDashboard["summary"];
  currency: string;
}) {
  const rows = [
    { label: "Revenue", value: summary.revenue, type: "positive" as const },
    { label: "Product costs (COGS)", value: -summary.cogs, type: "negative" as const },
    { label: "Shipping", value: -summary.shipping_costs, type: "negative" as const },
    { label: "Payment fees", value: -summary.transaction_fees, type: "negative" as const },
    { label: "Gross profit", value: summary.gross_profit, type: "subtotal" as const },
    { label: "Meta ad spend", value: -summary.ad_spend, type: "negative" as const },
    { label: "Net profit", value: summary.net_profit, type: "total" as const },
  ];

  return (
    <Card padding="lg">
      <CardHeader>
        <CardTitle>Profit Breakdown</CardTitle>
        <CardDescription>How your revenue flows to net profit</CardDescription>
      </CardHeader>
      <div className="space-y-2">
        {rows.map((row) => (
          <div
            key={row.label}
            className={cn(
              "flex justify-between items-center py-2",
              row.type === "subtotal" && "border-t border-border pt-3 font-medium",
              row.type === "total" && "border-t-2 border-brand-500/30 pt-3 font-bold text-lg"
            )}
          >
            <span
              className={cn(
                row.type === "total" ? "text-content" : "text-content-muted",
                row.type === "subtotal" && "text-content"
              )}
            >
              {row.label}
            </span>
            <span
              className={cn(
                row.value >= 0 ? "text-content" : "text-red-600 dark:text-red-400",
                row.type === "total" && (row.value >= 0 ? "text-emerald-600" : "text-red-600")
              )}
            >
              {row.value < 0 ? "−" : ""}
              {currency} {Math.abs(row.value).toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-4 pt-4 border-t border-border grid grid-cols-2 gap-4 text-sm">
        <div>
          <p className="text-content-muted">Break-even ROAS</p>
          <p className="font-semibold text-content">{summary.break_even_roas}x</p>
        </div>
        <div>
          <p className="text-content-muted">Net margin</p>
          <p className="font-semibold text-content">{summary.net_margin_pct}%</p>
        </div>
      </div>
    </Card>
  );
}
