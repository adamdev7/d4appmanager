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
import { formatMoney } from "@/lib/formatMoney";
import type { AdsDashboard } from "@/lib/adsTypes";

function formatChartDate(date: string) {
  try {
    return new Date(date + "T12:00:00").toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    });
  } catch {
    return date;
  }
}

export function AdsSpendCpmChart({
  data,
  currency,
}: {
  data: AdsDashboard["daily"];
  currency: string;
}) {
  return (
    <Card padding="lg">
      <CardHeader>
        <CardTitle>Spend & CPM</CardTitle>
        <CardDescription>Auction cost pressure day by day</CardDescription>
      </CardHeader>
      <div className="h-64 xl:h-80 2xl:h-96 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="adsSpend" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="var(--color-brand-500)" stopOpacity={0.35} />
                <stop offset="95%" stopColor="var(--color-brand-500)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            <XAxis dataKey="date" tickFormatter={formatChartDate} tick={{ fontSize: 11 }} />
            <YAxis yAxisId="left" tick={{ fontSize: 11 }} width={48} />
            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} width={40} />
            <Tooltip
              labelFormatter={(l) => formatChartDate(String(l))}
              formatter={(value, name) => [
                formatMoney(Number(value ?? 0), currency),
                String(name),
              ]}
            />
            <Legend />
            <Area
              yAxisId="left"
              type="monotone"
              dataKey="spend"
              name="Spend"
              stroke="var(--color-brand-600)"
              fill="url(#adsSpend)"
            />
            <Area
              yAxisId="right"
              type="monotone"
              dataKey="cpm"
              name="CPM"
              stroke="#d97706"
              fill="transparent"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

export function AdsCreativeHealthChart({ data }: { data: AdsDashboard["daily"] }) {
  return (
    <Card padding="lg">
      <CardHeader>
        <CardTitle>Creative health</CardTitle>
        <CardDescription>Hook rate, outbound CTR, and frequency (fatigue)</CardDescription>
      </CardHeader>
      <div className="h-64 xl:h-80 2xl:h-96 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            <XAxis dataKey="date" tickFormatter={formatChartDate} tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} width={40} />
            <Tooltip labelFormatter={(l) => formatChartDate(String(l))} />
            <Legend />
            <Bar dataKey="hook_rate" name="Hook %" fill="var(--color-brand-500)" radius={[3, 3, 0, 0]} />
            <Bar dataKey="outbound_ctr" name="Outbound CTR %" fill="#059669" radius={[3, 3, 0, 0]} />
            <Bar dataKey="frequency" name="Frequency" fill="#d97706" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
