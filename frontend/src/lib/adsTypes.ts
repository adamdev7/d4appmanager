export type AdsPeriod = "7d" | "30d" | "90d";

export type AdsEntityRow = {
  id: string;
  name: string;
  campaign_id?: string;
  campaign_name?: string;
  adset_id?: string;
  adset_name?: string;
  spend: number;
  impressions: number;
  reach: number;
  frequency: number;
  clicks: number;
  ctr: number;
  cpm: number;
  cpc: number;
  outbound_clicks: number;
  outbound_ctr: number;
  hook_rate: number;
  video_3s_plays: number;
  purchases: number;
  purchase_value: number;
  platform_roas: number;
  cpa: number;
  add_to_cart: number;
  initiate_checkout: number;
  view_content: number;
  landing_page_views: number;
  quality_ranking?: string | null;
  engagement_rate_ranking?: string | null;
  conversion_rate_ranking?: string | null;
};

export type AdsAlert = {
  severity: "info" | "warning" | "danger";
  code: string;
  title: string;
  message: string;
  entity_id?: string;
};

export type AdsMissedAngle = {
  id: string;
  title: string;
  why: string;
  value: string;
  compare: string;
};

export type AdsAiReport = {
  id: string;
  report_type: string;
  period: string;
  title: string;
  summary: string;
  body_markdown: string;
  model_used: string;
  error_message: string | null;
  created_at: string | null;
};

export type AdsSettings = {
  store_id: string;
  meta_configured: boolean;
  meta_token_masked: string | null;
  meta_ad_account_id: string | null;
  ai_reports_consent: boolean;
  daily_ai_reports: boolean;
  weekly_ai_reports: boolean;
  last_daily_report_at: string | null;
  last_weekly_report_at: string | null;
  openai_configured: boolean;
  openai_key_masked: string | null;
  openai_key_is_user_owned: boolean;
  openai_uses_server_fallback: boolean;
};

export type AdsDashboard = {
  store_id: string;
  period: AdsPeriod;
  since: string;
  until: string;
  currency: string;
  meta_configured: boolean;
  meta_error: string | null;
  shopify_error: string | null;
  summary: {
    spend: number;
    impressions: number;
    reach: number;
    frequency: number;
    clicks: number;
    ctr: number;
    cpm: number;
    outbound_clicks: number;
    outbound_ctr: number;
    hook_rate: number;
    video_3s_plays: number;
    purchases: number;
    purchase_value: number;
    platform_roas: number;
    cpa: number;
    store_revenue: number;
    store_orders: number;
    mer: number | null;
    new_customers: number;
    returning_customers: number;
    blended_ncac: number | null;
    funnel: {
      view_content: number;
      landing_page_views: number;
      link_clicks: number;
      add_to_cart: number;
      initiate_checkout: number;
      purchases: number;
      view_to_cart_pct: number;
      cart_to_checkout_pct: number;
      checkout_to_purchase_pct: number;
    };
  };
  attribution: {
    purchases_1d_click: number;
    purchases_7d_click: number;
    purchases_1d_view: number;
    purchase_value_1d_click: number;
    purchase_value_7d_click: number;
    gap_7d_vs_1d_pct: number;
  };
  daily: Array<{
    date: string;
    spend: number;
    impressions: number;
    clicks: number;
    cpm: number;
    ctr: number;
    frequency: number;
    outbound_ctr: number;
    hook_rate: number;
    purchases: number;
    purchase_value: number;
    cpa: number;
  }>;
  campaigns: AdsEntityRow[];
  adsets: AdsEntityRow[];
  ads: AdsEntityRow[];
  winners: AdsEntityRow[];
  needs_check: AdsEntityRow[];
  alerts: AdsAlert[];
  missed_angles: AdsMissedAngle[];
  ai: {
    consent: boolean;
    daily_enabled: boolean;
    weekly_enabled: boolean;
    openai_configured: boolean;
    latest_report: AdsAiReport | null;
  };
};
