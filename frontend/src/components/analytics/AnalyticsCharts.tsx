import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";

type DailyPoint = {
  date: string;
  revenue: number;
  ad_spend: number;
  orders: number;
  profit: number;
};

function formatChartDate(date: string, granularity: "daily" | "monthly" = "daily") {
  try {
    const d = new Date(date + "T12:00:00");
    if (granularity === "monthly") {
      return d.toLocaleDateString(undefined, { month: "short", year: "numeric" });
    }
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return date;
  }
}

function ChartTooltip({
  active,
  payload,
  label,
  currency,
  granularity = "daily",
}: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string }>;
  label?: string;
  currency: string;
  granularity?: "daily" | "monthly";
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2 shadow-elevated text-sm">
      <p className="font-medium text-content mb-1">{formatChartDate(String(label), granularity)}</p>
      {payload.map((entry) => (
        <p key={entry.name} style={{ color: entry.color }} className="text-content-muted">
          {entry.name}: {currency} {entry.value.toLocaleString(undefined, { minimumFractionDigits: 2 })}
        </p>
      ))}
    </div>
  );
}

export function RevenueSpendChart({
  data,
  currency,
  granularity = "daily",
}: {
  data: DailyPoint[];
  currency: string;
  granularity?: "daily" | "monthly";
}) {
  const periodLabel = granularity === "monthly" ? "Monthly" : "Daily";
  return (
    <Card padding="lg">
      <CardHeader>
        <CardTitle>Revenue vs Ad Spend</CardTitle>
        <CardDescription>{periodLabel} store revenue compared to Meta ad spend</CardDescription>
      </CardHeader>
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="revGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#0d9488" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#0d9488" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="spendGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" opacity={0.5} />
            <XAxis
              dataKey="date"
              tickFormatter={(d) => formatChartDate(d, granularity)}
              tick={{ fontSize: 11, fill: "var(--color-content-muted)" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "var(--color-content-muted)" }}
              axisLine={false}
              tickLine={false}
              width={48}
            />
            <Tooltip content={<ChartTooltip currency={currency} granularity={granularity} />} />
            <Legend />
            <Area
              type="monotone"
              dataKey="revenue"
              name="Revenue"
              stroke="#0d9488"
              fill="url(#revGrad)"
              strokeWidth={2}
            />
            <Area
              type="monotone"
              dataKey="ad_spend"
              name="Ad Spend"
              stroke="#6366f1"
              fill="url(#spendGrad)"
              strokeWidth={2}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

export function ProfitChart({
  data,
  currency,
  granularity = "daily",
}: {
  data: DailyPoint[];
  currency: string;
  granularity?: "daily" | "monthly";
}) {
  const periodLabel = granularity === "monthly" ? "Monthly" : "Daily";
  return (
    <Card padding="lg">
      <CardHeader>
        <CardTitle>{periodLabel} Net Profit</CardTitle>
        <CardDescription>Estimated profit after product costs, fees, and ad spend</CardDescription>
      </CardHeader>
      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" opacity={0.5} />
            <XAxis
              dataKey="date"
              tickFormatter={(d) => formatChartDate(d, granularity)}
              tick={{ fontSize: 11, fill: "var(--color-content-muted)" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "var(--color-content-muted)" }}
              axisLine={false}
              tickLine={false}
              width={48}
            />
            <Tooltip content={<ChartTooltip currency={currency} granularity={granularity} />} />
            <Bar dataKey="profit" name="Net Profit" fill="#0d9488" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

export function OrdersChart({
  data,
  granularity = "daily",
}: {
  data: DailyPoint[];
  granularity?: "daily" | "monthly";
}) {
  const periodLabel = granularity === "monthly" ? "Orders per Month" : "Orders per Day";
  return (
    <Card padding="lg">
      <CardHeader>
        <CardTitle>{periodLabel}</CardTitle>
        <CardDescription>Shopify orders in the selected period</CardDescription>
      </CardHeader>
      <div className="h-48 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" opacity={0.5} />
            <XAxis
              dataKey="date"
              tickFormatter={(d) => formatChartDate(d, granularity)}
              tick={{ fontSize: 11, fill: "var(--color-content-muted)" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "var(--color-content-muted)" }}
              axisLine={false}
              tickLine={false}
              width={32}
              allowDecimals={false}
            />
            <Tooltip />
            <Bar dataKey="orders" name="Orders" fill="#14b8a6" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
