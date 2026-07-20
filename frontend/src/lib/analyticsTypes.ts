export type AnalyticsPeriod = "7d" | "30d" | "90d" | "all";

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
    refunds: number;
    orders: number;
    aov: number;
    cogs: number;
    shipping_costs: number;
    transaction_fees: number;
    gross_profit: number;
    ad_spend: number;
    net_profit: number;
    mer: number;
    roas: number;
    cpa: number;
    ctr: number;
    cpc: number;
    impressions: number;
    clicks: number;
    meta_purchases: number;
    meta_purchase_value: number;
    margin_before_ads_pct: number;
    net_margin_pct: number;
    break_even_roas: number;
  };
  daily_chart: Array<{
    date: string;
    revenue: number;
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
};
