export type AnalyticsPeriod = "7d" | "30d" | "90d" | "all";

export type AnalyticsStripeAccount = {
  id: string;
  label: string;
  secret_key_masked: string | null;
  is_active: boolean;
  last_error: string | null;
  last_mrr: number;
  last_subscribers: number;
  last_synced_at: string | null;
};

export type AnalyticsSettings = {
  store_id: string;
  store_name: string;
  shop_domain: string;
  currency: string;
  shopify_connected: boolean;
  meta_configured: boolean;
  meta_token_masked: string | null;
  meta_ad_account_id: string | null;
  default_shipping_cost: number;
  transaction_fee_percent: number;
  transaction_fee_fixed: number;
  analytics_start_date: string | null;
  prior_external_revenue: number;
  prior_external_costs: number;
  prior_external_label: string;
  mrr_enabled: boolean;
  mrr_source: "manual" | "multi_stripe";
  mrr_manual_amount: number;
  mrr_manual_subscribers: number;
  mrr_manual_churn_pct: number;
  mrr_webhook_configured: boolean;
  mrr_webhook_secret_masked: string | null;
  mrr_webhook_secret: string | null;
  mrr_last_synced_at: string | null;
  stripe_accounts: AnalyticsStripeAccount[];
};

export type AnalyticsProduct = {
  shopify_product_id: string;
  shopify_variant_id: string;
  product_title: string;
  variant_title: string;
  image_url: string | null;
  shopify_price: string;
  cost_per_unit: number;
  sku: string;
};

export type AnalyticsProductsResponse = {
  store_id: string;
  currency: string;
  products: AnalyticsProduct[];
  total_variants: number;
  missing_costs: number;
};

export type AnalyticsInsight = {
  level: "info" | "warning" | "danger" | "success";
  title: string;
  message: string;
  action?: string;
};

export type AnalyticsDashboard = {
  store_id: string;
  store_name: string;
  currency: string;
  period: AnalyticsPeriod;
  chart_granularity: "daily" | "monthly";
  date_range: { since: string; until: string };
  connections: {
    shopify: boolean;
    meta: boolean;
    meta_error: string | null;
  };
  summary: {
    revenue: number;
    shopify_revenue: number;
    approx_revenue: number;
    meta_approx_revenue: number;
    revenue_source: "shopify" | "meta_approx" | "none";
    prior_external_revenue: number;
    prior_external_costs: number;
    prior_external_label: string;
    analytics_start_date: string | null;
    refunds: number;
    orders: number;
    aov: number;
    meta_aov: number;
    cogs: number;
    shipping_costs: number;
    transaction_fees: number;
    gross_profit: number;
    ad_spend: number;
    net_profit: number;
    meta_est_gross_profit: number;
    meta_est_net_profit: number;
    variable_cost_rate_pct: number;
    mer: number;
    roas: number;
    meta_roas: number;
    cpa: number;
    meta_cpa: number;
    ctr: number;
    cpc: number;
    impressions: number;
    clicks: number;
    meta_purchases: number;
    meta_purchase_value: number;
    meta_add_to_cart: number;
    meta_initiate_checkout: number;
    meta_view_content: number;
    meta_landing_page_views: number;
    meta_link_clicks: number;
    click_to_atc_pct: number;
    atc_to_checkout_pct: number;
    checkout_to_purchase_pct: number;
    attribution_gap: number;
    attribution_coverage_pct: number;
    margin_before_ads_pct: number;
    net_margin_pct: number;
    break_even_roas: number;
  };
  daily_chart: Array<{
    date: string;
    revenue: number;
    shopify_revenue?: number;
    meta_purchase_value?: number;
    ad_spend: number;
    orders: number;
    profit: number;
  }>;
  campaigns: Array<{
    campaign_id: string;
    campaign_name: string;
    spend: number;
    impressions: number;
    clicks: number;
    ctr: number;
    cpc: number;
    purchases: number;
    purchase_value: number;
    roas: number;
    cpa: number;
    add_to_cart?: number;
    initiate_checkout?: number;
  }>;
  top_products: Array<{
    title: string;
    units_sold: number;
    revenue: number;
    cogs: number;
    profit: number;
    margin_pct: number;
  }>;
  recent_orders: Array<{
    order_number: string;
    total: number;
    cogs: number;
    profit: number;
    created_at: string;
  }>;
  insights: AnalyticsInsight[];
  mrr: {
    enabled: boolean;
    source: "manual" | "multi_stripe" | string;
    mrr: number;
    arr: number;
    subscribers: number;
    arpu: number;
    churn_pct: number;
    mrr_delta: number;
    last_synced_at: string | null;
    history: Array<{
      date: string;
      mrr: number;
      subscribers: number;
      churn_pct: number;
      source: string;
    }>;
    stripe_account_count: number;
  } | null;
};
