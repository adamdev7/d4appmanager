import type { DashboardOverview } from "@/lib/dashboardTypes";

const API_BASE = "/api/v1";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function parseError(res: Response): Promise<string> {
  const err = await res.json().catch(() => ({}));
  const detail = (err as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
  return res.statusText || "Request failed";
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = localStorage.getItem("access_token");
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(options?.headers ?? {}),
  };
  if (token) {
    (headers as Record<string, string>)["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    throw new ApiError(await parseError(res), res.status);
  }
  return res.json();
}

export type AuthUser = {
  id: string;
  email: string;
  full_name: string;
  is_verified?: boolean;
};

export type TrackingSettings = {
  store_id: string;
  carrier_mode: string;
  auto_enrich_enabled: boolean;
  yunexpress_api_url: string;
  yunexpress_customer_code: string | null;
  yunexpress_carrier_keywords: string;
  track17_configured: boolean;
  track17_key_masked: string | null;
  yunexpress_configured: boolean;
  yunexpress_key_masked: string | null;
  uses_server_track17_fallback: boolean;
  uses_server_yunexpress_fallback: boolean;
};

export type TrackingOrder = {
  id: string;
  order_number: string;
  customer_email: string;
  customer_name?: string | null;
  tracking_number: string | null;
  carrier: string | null;
  status: string;
  shopify_financial_status?: string | null;
  shopify_fulfillment_status?: string | null;
  order_total?: string | null;
  currency?: string | null;
  order_placed_at?: string | null;
  line_items?: Array<{
    title: string;
    variant?: string;
    quantity: number;
    image_url?: string;
    price?: string;
  }>;
  fulfillments?: Array<{
    id: string;
    status?: string;
    shipment_status?: string;
    tracking_number?: string;
    carrier?: string;
    tracking_url?: string;
    created_at?: string | null;
    updated_at?: string | null;
    items?: string[];
  }>;
  timeline?: Array<{ status: string; description: string; at: string }>;
  last_updated_at: string | null;
};

export type TrackingOverview = {
  store_id: string;
  store_name: string;
  shop_domain: string;
  store_status: string;
  track_endpoint: string;
  settings: TrackingSettings;
  carrier_enrichment: {
    track17: boolean;
    yunexpress: boolean;
    auto_enrich: boolean;
    mode: string;
  };
  stats: {
    orders_synced: number;
    with_tracking: number;
    pending?: number;
    in_transit?: number;
    delivered?: number;
  };
  shopify_connected?: boolean;
  recent_orders: TrackingOrder[];
};

export type TrackingSyncResult = {
  ok: boolean;
  message: string;
  sync: {
    fetched: number;
    created: number;
    updated: number;
    skipped: number;
  };
  overview: TrackingOverview;
};

export type TrackOrderResult = {
  order_number: string;
  tracking_number: string | null;
  carrier: string | null;
  status: string;
  timeline: Array<{ status: string; description: string; at: string }>;
  last_updated_at: string | null;
};

export const api = {
  auth: {
    login: (email: string, password: string) =>
      request<{ access_token: string; token_type: string; user: AuthUser }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      }),
    register: (email: string, password: string, full_name: string) =>
      request<{
        message: string;
        requires_verification: boolean;
        email: string;
      }>("/auth/register", {
        method: "POST",
        body: JSON.stringify({ email, password, full_name }),
      }),
    verifyEmail: (email: string, code: string) =>
      request<{ access_token: string; token_type: string; user: AuthUser }>("/auth/verify-email", {
        method: "POST",
        body: JSON.stringify({ email, code }),
      }),
    resendVerification: (email: string) =>
      request<{ message: string }>("/auth/resend-verification", {
        method: "POST",
        body: JSON.stringify({ email }),
      }),
    me: () => request<AuthUser>("/auth/me"),
    forgotPassword: (email: string) =>
      request<{ message: string }>("/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify({ email }),
      }),
  },
  dashboard: {
    overview: (storeId?: string) =>
      request<DashboardOverview>(
        `/dashboard/overview${storeId ? `?store_id=${storeId}` : ""}`
      ),
    activity: (storeId?: string) =>
      request<
        Array<{ id: string; title: string; description: string; timestamp: string; type: string }>
      >(`/dashboard/activity${storeId ? `?store_id=${storeId}` : ""}`),
  },
  stores: {
    list: () =>
      request<
        Array<{
          id: string;
          name: string;
          domain: string;
          status: string;
          plan: string;
          timezone: string;
          currency: string;
        }>
      >("/stores"),
    shopifyInstall: (shop: string) =>
      request<{ authorize_url: string }>(
        `/stores/shopify/install?shop=${encodeURIComponent(shop)}`
      ),
    disconnect: (storeId: string) =>
      request(`/stores/${storeId}/disconnect`, { method: "POST" }),
  },
  gmail: {
    accounts: (storeId?: string) =>
      request<
        Array<{
          id: string;
          email: string;
          display_name: string;
          status: string;
          is_default_sender: boolean;
          store_ids: string[];
        }>
      >(`/gmail/accounts${storeId ? `?store_id=${storeId}` : ""}`),
    oauthAuthorize: (storeId?: string) =>
      request<{ authorize_url: string }>(
        `/gmail/oauth/authorize${storeId ? `?store_id=${storeId}` : ""}`
      ),
    settings: (storeId?: string) =>
      request<{
        reply_to: string | null;
        signature_html: string;
        track_opens: boolean;
        track_clicks: boolean;
        daily_send_limit: number;
      }>(`/gmail/settings${storeId ? `?store_id=${storeId}` : ""}`),
    updateSettings: (data: object, storeId?: string) =>
      request(`/gmail/settings${storeId ? `?store_id=${storeId}` : ""}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),
    disconnect: (accountId: string) =>
      request(`/gmail/accounts/${accountId}/disconnect`, { method: "POST" }),
  },
  modules: {
    list: () =>
      request<
        Array<{
          id: string;
          name: string;
          description: string;
          slug: string;
          status: string;
          icon: string;
        }>
      >("/modules"),
  },
  emailAutomation: {
    events: () =>
      request<Array<{ event_type: string; label: string; description: string }>>(
        "/email-automation/events"
      ),
    variables: () => request<{ variables: string[] }>("/email-automation/variables"),
    seedDefaults: (storeId: string) =>
      request(`/email-automation/stores/${storeId}/seed-defaults`, { method: "POST" }),
    rules: (storeId: string) =>
      request<
        Array<{
          id: string;
          event_type: string;
          template_id: string;
          template_name: string | null;
          gmail_email: string | null;
          is_enabled: boolean;
        }>
      >(`/email-automation/stores/${storeId}/rules`),
    updateRule: (storeId: string, ruleId: string, data: { is_enabled?: boolean }) =>
      request(`/email-automation/stores/${storeId}/rules/${ruleId}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    getTemplate: (storeId: string, templateId: string) =>
      request<{
        id: string;
        store_id: string;
        name: string;
        subject: string;
        body_html: string;
      }>(`/email-automation/stores/${storeId}/templates/${templateId}`),
    updateTemplate: (
      storeId: string,
      templateId: string,
      data: { name?: string; subject?: string; body_html?: string }
    ) =>
      request(`/email-automation/stores/${storeId}/templates/${templateId}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    sendLogs: (storeId: string) =>
      request<
        Array<{
          id: string;
          event_type: string;
          recipient: string;
          subject: string;
          status: string;
          sent_at: string;
        }>
      >(`/email-automation/stores/${storeId}/send-logs`),
  },
  aiEmailAssistant: {
    openaiKeyStatus: () =>
      request<{
        openai_configured: boolean;
        openai_key_masked: string | null;
        openai_key_is_user_owned: boolean;
        openai_uses_server_fallback: boolean;
      }>("/ai-email-assistant/openai-key"),
    saveOpenAIKey: (apiKey: string) =>
      request<{
        openai_configured: boolean;
        openai_key_masked: string | null;
        openai_key_is_user_owned: boolean;
        openai_uses_server_fallback: boolean;
      }>("/ai-email-assistant/openai-key", {
        method: "PUT",
        body: JSON.stringify({ api_key: apiKey }),
      }),
    deleteOpenAIKey: () =>
      request<{
        openai_configured: boolean;
        openai_key_masked: string | null;
        openai_key_is_user_owned: boolean;
        openai_uses_server_fallback: boolean;
      }>("/ai-email-assistant/openai-key", { method: "DELETE" }),
    settings: (storeId?: string) =>
      request<{
        id: string;
        business_name: string;
        business_type: string;
        tone_of_voice: string;
        rules: string;
        policies: string;
        faq: string;
        auto_send_enabled: boolean;
        gmail_account_id: string | null;
        openai_model: string | null;
        email_filter_enabled: boolean;
        filter_automated_emails: boolean;
        filter_non_business_emails: boolean;
        filter_custom_rules: string;
        automation_enabled: boolean;
        automation_interval_minutes: number;
        automation_max_emails_per_run: number;
        automation_last_run_at: string | null;
        automation_last_error: string | null;
        one_reply_per_thread: boolean;
        sync_only_customer_unread: boolean;
        verify_gmail_thread_before_reply: boolean;
        use_thread_context: boolean;
        openai_configured: boolean;
        openai_key_masked: string | null;
        openai_key_is_user_owned: boolean;
        openai_uses_server_fallback: boolean;
        default_model: string;
      }>(`/ai-email-assistant/settings${storeId ? `?store_id=${storeId}` : ""}`),
    updateSettings: (data: object, storeId?: string) =>
      request(`/ai-email-assistant/settings${storeId ? `?store_id=${storeId}` : ""}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),
    inbox: (storeId?: string) =>
      request<
        Array<{
          id: string;
          gmail_message_id: string;
          thread_id: string;
          sender: string;
          sender_email: string;
          subject: string;
          body_text: string;
          detected_intent: string | null;
          skip_reason: string | null;
          filter_category: string | null;
          status: string;
          received_at: string;
          latest_reply: {
            id: string;
            inbox_email_id: string;
            generated_body: string;
            edited_body: string | null;
            effective_body: string;
            status: string;
            model_used: string;
            detected_intent: string | null;
            error_message: string | null;
            created_at: string;
            sent_at: string | null;
          } | null;
        }>
      >(`/ai-email-assistant/inbox${storeId ? `?store_id=${storeId}` : ""}`),
    runAutomation: (storeId?: string) =>
      request<{
        ok: boolean;
        processed: number;
        skipped: boolean;
        stopped: boolean;
        reason: string | null;
        error: string | null;
      }>(`/ai-email-assistant/automation/run${storeId ? `?store_id=${storeId}` : ""}`, {
        method: "POST",
      }),
    syncInbox: (gmailAccountId: string, maxResults = 15, storeId?: string) =>
      request(`/ai-email-assistant/inbox/sync${storeId ? `?store_id=${storeId}` : ""}`, {
        method: "POST",
        body: JSON.stringify({ gmail_account_id: gmailAccountId, max_results: maxResults }),
      }),
    unskipEmail: (inboxEmailId: string) =>
      request(`/ai-email-assistant/inbox/${inboxEmailId}/unskip`, { method: "POST" }),
    generateReply: (inboxEmailId: string, storeId?: string) =>
      request<{
        id: string;
        effective_body: string;
        status: string;
        model_used: string;
      }>(
        `/ai-email-assistant/inbox/${inboxEmailId}/generate${storeId ? `?store_id=${storeId}` : ""}`,
        { method: "POST" }
      ),
    approveReply: (replyId: string) =>
      request(`/ai-email-assistant/replies/${replyId}/approve`, { method: "POST" }),
    rejectReply: (replyId: string) =>
      request(`/ai-email-assistant/replies/${replyId}/reject`, { method: "POST" }),
    updateDraft: (replyId: string, body: string) =>
      request(`/ai-email-assistant/replies/${replyId}`, {
        method: "PATCH",
        body: JSON.stringify({ body }),
      }),
    logs: () =>
      request<
        Array<{
          id: string;
          inbox_email_id: string;
          subject: string;
          sender_email: string;
          status: string;
          model_used: string;
          body_preview: string;
          created_at: string;
          sent_at: string | null;
        }>
      >("/ai-email-assistant/logs"),
  },
  tracking: {
    overview: (storeId: string) =>
      request<TrackingOverview>(`/tracking/stores/${storeId}/overview`),
    sync: (storeId: string) =>
      request<TrackingSyncResult>(`/tracking/stores/${storeId}/sync`, { method: "POST" }),
    getSettings: (storeId: string) =>
      request<TrackingSettings>(`/tracking/stores/${storeId}/settings`),
    updateSettings: (storeId: string, data: object) =>
      request<TrackingSettings>(`/tracking/stores/${storeId}/settings`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),
    testCarrier: (
      storeId: string,
      data: { provider: string; tracking_number?: string }
    ) =>
      request<{ ok: boolean; provider: string; message: string; status: string | null }>(
        `/tracking/stores/${storeId}/test-carrier`,
        { method: "POST", body: JSON.stringify(data) }
      ),
    lookup: async (params: {
      order_number: string;
      email: string;
      store_id: string;
    }): Promise<TrackOrderResult> => {
      const url = new URL("/api/track-order", window.location.origin);
      url.searchParams.set("order_number", params.order_number);
      url.searchParams.set("email", params.email);
      url.searchParams.set("store_id", params.store_id);
      const res = await fetch(url.toString(), {
        headers: { Accept: "application/json" },
      });
      if (!res.ok) {
        throw new ApiError(await parseError(res), res.status);
      }
      return res.json();
    },
  },
};
