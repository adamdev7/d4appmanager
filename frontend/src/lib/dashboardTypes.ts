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

export type DashboardOverview = {
  metrics: OverviewMetric[];
  setup_steps: SetupStep[];
  highlights: ModuleHighlight[];
};

export const EMPTY_DASHBOARD_OVERVIEW: DashboardOverview = {
  metrics: [
    { label: "Connected stores", value: "0", change: "Add a store in Settings", trend: "neutral" },
    { label: "Gmail accounts", value: "0", change: "Connect Gmail in Settings", trend: "neutral" },
    { label: "Orders synced", value: "0", change: "Connect a Shopify store to sync orders", trend: "neutral" },
    { label: "Emails sent (7d)", value: "0", change: "Connect Gmail for automations", trend: "neutral" },
  ],
  setup_steps: [
    { id: "store", label: "Connect Shopify store", done: false, href: "/settings/stores" },
    { id: "gmail", label: "Connect Gmail", done: false, href: "/settings/gmail" },
  ],
  highlights: [],
};
