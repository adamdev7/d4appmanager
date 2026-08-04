export type MetaCapiSettings = {
  enabled: boolean;
  meta_pixel_id: string | null;
  meta_token_masked: string | null;
  has_access_token: boolean;
  use_analytics_token: boolean;
  test_event_code: string | null;
  event_id_scheme: string;
  trigger_topic: string;
  api_version: string;
  send_initiate_checkout: boolean;
  browser_event_token: string | null;
  configured: boolean;
  ready: boolean;
};

export type MetaCapiStats = {
  settings: MetaCapiSettings;
  sent_today: number;
  failed_today: number;
  skipped_today: number;
  total_sent: number;
  last_successful_send_at: string | null;
  last_event_id: string | null;
  last_order_id: string | null;
};

export type MetaCapiEvent = {
  id: string;
  shopify_order_id: string;
  topic: string;
  event_name?: string;
  event_id: string;
  status: string;
  attempts: number;
  meta_events_received: number | null;
  meta_fbtrace_id: string | null;
  error_message: string | null;
  order_value: string | null;
  currency: string | null;
  sent_at: string | null;
  created_at: string | null;
};
