export type OverviewMetric = {
  label: string;
  value: string;
  change: string;
  trend: string;
};

export type SetupStep = {
  id: string;
  label: string;
  done: boolean;
  href: string;
};

export type ModuleHighlight = {
  slug: string;
  name: string;
  status: string;
  stat_label: string;
  stat_value: string;
  hint: string;
};

export type MoneyPulse = {
  period: string;
  currency: string;
  available: boolean;
  revenue: number;
  net_profit: number;
  ad_spend: number;
  roas: number;
  mer: number | null;
  orders: number;
  hint: string;
};

export type DashboardOverview = {
  metrics: OverviewMetric[];
  setup_steps: SetupStep[];
  highlights: ModuleHighlight[];
  money: MoneyPulse;
};

export const EMPTY_MONEY_PULSE: MoneyPulse = {
  period: "7d",
  currency: "USD",
  available: false,
  revenue: 0,
  net_profit: 0,
  ad_spend: 0,
  roas: 0,
  mer: null,
  orders: 0,
  hint: "",
};

export const EMPTY_DASHBOARD_OVERVIEW: DashboardOverview = {
  metrics: [
    { label: "Connected stores", value: "0", change: "Add a store in Settings", trend: "neutral" },
    { label: "Gmail accounts", value: "0", change: "Connect Gmail in Settings", trend: "neutral" },
    { label: "Orders synced", value: "0", change: "Connect a Shopify store to sync orders", trend: "neutral" },
    { label: "Emails sent (7d)", value: "0", change: "Connect Gmail for automations", trend: "neutral" },
  ],
  setup_steps: [],
  highlights: [],
  money: EMPTY_MONEY_PULSE,
};
