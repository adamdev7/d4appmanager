import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  Info,
  Radar,
  RefreshCw,
  Save,
  Settings2,
  TestTube2,
  Activity,
} from "lucide-react";
import { useStore } from "@/context/StoreContext";
import {
  api,
  type MetaCapiEvent,
  type MetaCapiSettings,
  type MetaCapiStats,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Switch } from "@/components/ui/Switch";

type Tab = "overview" | "settings";

const TABS: Array<{ id: Tab; label: string; icon: typeof Radar }> = [
  { id: "overview", label: "Overview", icon: Activity },
  { id: "settings", label: "Settings", icon: Settings2 },
];

function formatTs(iso: string | null | undefined) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function statusVariant(status: string) {
  if (status === "sent") return "success" as const;
  if (status === "failed") return "warning" as const;
  if (status === "skipped") return "muted" as const;
  return "brand" as const;
}

export function MetaCapiPage() {
  const { activeStore, stores } = useStore();
  const storeId = activeStore?.id ?? stores[0]?.id ?? null;

  const [tab, setTab] = useState<Tab>("overview");
  const [stats, setStats] = useState<MetaCapiStats | null>(null);
  const [settings, setSettings] = useState<MetaCapiSettings | null>(null);
  const [events, setEvents] = useState<MetaCapiEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [enabled, setEnabled] = useState(false);
  const [pixelId, setPixelId] = useState("");
  const [token, setToken] = useState("");
  const [useAnalyticsToken, setUseAnalyticsToken] = useState(true);
  const [testCode, setTestCode] = useState("");
  const [eventIdScheme, setEventIdScheme] = useState("order_id");
  const [triggerTopic, setTriggerTopic] = useState("orders/paid");
  const [apiVersion, setApiVersion] = useState("v25.0");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState("");
  const [saveError, setSaveError] = useState("");

  const load = useCallback(async () => {
    if (!storeId) {
      setLoading(false);
      setStats(null);
      setSettings(null);
      setEvents([]);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [s, e] = await Promise.all([
        api.metaCapi.stats(storeId),
        api.metaCapi.events(storeId, 40),
      ]);
      setStats(s);
      setSettings(s.settings);
      setEvents(e.events);
      setEnabled(Boolean(s.settings.enabled));
      setPixelId(s.settings.meta_pixel_id ?? "");
      setUseAnalyticsToken(Boolean(s.settings.use_analytics_token));
      setTestCode(s.settings.test_event_code ?? "");
      setEventIdScheme(s.settings.event_id_scheme || "order_id");
      setTriggerTopic(s.settings.trigger_topic || "orders/paid");
      setApiVersion(s.settings.api_version || "v25.0");
      setToken("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async () => {
    if (!storeId) return;
    setSaving(true);
    setSaveError("");
    setMessage("");
    try {
      const payload: Record<string, unknown> = {
        enabled,
        meta_pixel_id: pixelId.trim() || null,
        use_analytics_token: useAnalyticsToken,
        event_id_scheme: eventIdScheme,
        trigger_topic: triggerTopic,
        api_version: apiVersion.trim() || "v25.0",
        test_event_code: testCode.trim() || null,
      };
      if (token.trim()) payload.meta_access_token = token.trim();
      if (!testCode.trim()) payload.clear_test_event_code = true;
      const updated = await api.metaCapi.updateSettings(storeId, payload);
      setSettings(updated);
      setToken("");
      setMessage("Settings saved.");
      await load();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const testSend = async () => {
    if (!storeId) return;
    setTesting(true);
    setSaveError("");
    setMessage("");
    try {
      const res = await api.metaCapi.test(storeId, {
        meta_pixel_id: pixelId.trim() || undefined,
        meta_access_token: token.trim() || undefined,
        test_event_code: testCode.trim() || undefined,
      });
      setMessage(res.message);
      if (!res.ok) setSaveError(res.message);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Test failed");
    } finally {
      setTesting(false);
    }
  };

  if (!storeId) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold text-content tracking-tight">Server-Side Tracking</h1>
        <Card padding="lg">
          <p className="text-sm text-content-muted">
            Connect a Shopify store first.{" "}
            <Link to="/settings/stores" className="text-brand-700 underline dark:text-brand-400">
              Store settings
            </Link>
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Radar className="h-5 w-5 text-brand-600" />
            <h1 className="text-2xl font-semibold text-content tracking-tight">
              Server-Side Tracking
            </h1>
          </div>
          <p className="mt-1 text-sm text-content-muted max-w-xl">
            Shopify order webhooks → Meta Conversions API Purchase events. Runs alongside your
            browser Pixel and deduplicates when <code className="text-xs">event_id</code> matches.
          </p>
        </div>
        <Button type="button" variant="secondary" onClick={() => void load()} disabled={loading}>
          <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
          Refresh
        </Button>
      </div>

      <div className="flex gap-1 border-b border-border">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={cn(
              "flex items-center gap-2 px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
              tab === id
                ? "border-brand-500 text-brand-700 dark:text-brand-400"
                : "border-transparent text-content-muted hover:text-content"
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-200">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
          {error}
        </div>
      )}

      {tab === "overview" && (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Card padding="lg">
              <p className="text-xs font-medium uppercase tracking-wider text-content-subtle">
                Sent today
              </p>
              <p className="mt-2 text-3xl font-semibold text-content">{stats?.sent_today ?? "—"}</p>
            </Card>
            <Card padding="lg">
              <p className="text-xs font-medium uppercase tracking-wider text-content-subtle">
                Failures today
              </p>
              <p className="mt-2 text-3xl font-semibold text-content">{stats?.failed_today ?? "—"}</p>
            </Card>
            <Card padding="lg">
              <p className="text-xs font-medium uppercase tracking-wider text-content-subtle">
                Total sent
              </p>
              <p className="mt-2 text-3xl font-semibold text-content">{stats?.total_sent ?? "—"}</p>
            </Card>
            <Card padding="lg">
              <p className="text-xs font-medium uppercase tracking-wider text-content-subtle">Status</p>
              <div className="mt-3">
                <Badge variant={settings?.ready ? "success" : "warning"}>
                  {settings?.ready ? "Live" : settings?.configured ? "Configured (off)" : "Needs setup"}
                </Badge>
              </div>
              <p className="mt-2 text-xs text-content-muted">
                Last success: {formatTs(stats?.last_successful_send_at)}
              </p>
            </Card>
          </div>

          <Card padding="lg">
            <CardHeader>
              <CardTitle>Dedup checklist</CardTitle>
              <CardDescription>
                Browser Pixel and CAPI must share the same Purchase <code>event_id</code> or Meta
                will double-count.
              </CardDescription>
            </CardHeader>
            <ul className="space-y-2 text-sm text-content-muted">
              <li className="flex gap-2">
                <Info className="h-4 w-4 shrink-0 mt-0.5 text-brand-600" />
                Current scheme:{" "}
                <span className="font-medium text-content">
                  {settings?.event_id_scheme ?? "order_id"}
                </span>
                . Confirm this matches your storefront Pixel Purchase <code>eventID</code>.
              </li>
              <li className="flex gap-2">
                <Info className="h-4 w-4 shrink-0 mt-0.5 text-brand-600" />
                <code>fbp</code> / <code>fbc</code> cookies are read from order note attributes if
                present (<code>_fbp</code>, <code>_fbc</code>). Capture at checkout is a follow-up if
                not already set.
              </li>
              <li className="flex gap-2">
                <Info className="h-4 w-4 shrink-0 mt-0.5 text-brand-600" />
                Trigger topic:{" "}
                <span className="font-medium text-content">
                  {settings?.trigger_topic ?? "orders/paid"}
                </span>
                . Use <code>orders/create</code> for COD / no separate payment capture.
              </li>
            </ul>
          </Card>

          <Card padding="lg">
            <CardHeader>
              <CardTitle>Recent events</CardTitle>
              <CardDescription>Idempotent send log (webhook + order dedup).</CardDescription>
            </CardHeader>
            {events.length === 0 ? (
              <p className="text-sm text-content-muted">No events yet. Place a test order or use Meta Test Events.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-content-subtle">
                      <th className="py-2 pr-3 font-medium">When</th>
                      <th className="py-2 pr-3 font-medium">Order</th>
                      <th className="py-2 pr-3 font-medium">Event ID</th>
                      <th className="py-2 pr-3 font-medium">Status</th>
                      <th className="py-2 pr-3 font-medium">Value</th>
                      <th className="py-2 font-medium">Meta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.map((ev) => (
                      <tr key={ev.id} className="border-b border-border/60">
                        <td className="py-2.5 pr-3 text-content-muted whitespace-nowrap">
                          {formatTs(ev.sent_at || ev.created_at)}
                        </td>
                        <td className="py-2.5 pr-3 font-mono text-xs">{ev.shopify_order_id}</td>
                        <td className="py-2.5 pr-3 font-mono text-xs max-w-[140px] truncate" title={ev.event_id}>
                          {ev.event_id}
                        </td>
                        <td className="py-2.5 pr-3">
                          <Badge variant={statusVariant(ev.status)}>{ev.status}</Badge>
                        </td>
                        <td className="py-2.5 pr-3">
                          {ev.order_value != null && ev.order_value !== ""
                            ? `${ev.currency ?? ""} ${ev.order_value}`.trim()
                            : "—"}
                        </td>
                        <td className="py-2.5 text-xs text-content-muted max-w-[200px]">
                          {ev.error_message ? (
                            <span className="text-red-600 dark:text-red-400" title={ev.error_message}>
                              {ev.error_message.slice(0, 80)}
                            </span>
                          ) : (
                            <span title={ev.meta_fbtrace_id ?? undefined}>
                              recv={ev.meta_events_received ?? "—"}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}

      {tab === "settings" && (
        <div className="space-y-6 max-w-2xl">
          <Card padding="lg">
            <CardHeader>
              <CardTitle>Meta CAPI connection</CardTitle>
              <CardDescription>
                Pixel ID + Conversions API access token from Events Manager (or reuse Analytics
                Marketing token).
              </CardDescription>
            </CardHeader>
            <div className="space-y-4">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-medium text-content">Enable server-side Purchase</p>
                  <p className="text-xs text-content-muted">
                    Fires on Shopify webhook topic below when enabled.
                  </p>
                </div>
                <Switch checked={enabled} onChange={setEnabled} />
              </div>

              <Input
                label="Meta Pixel ID"
                placeholder="1234567890"
                value={pixelId}
                onChange={(e) => setPixelId(e.target.value)}
              />
              <Input
                label="CAPI access token"
                type="password"
                placeholder={
                  settings?.meta_token_masked
                    ? "Leave blank to keep current"
                    : "Generate in Events Manager → Settings → Conversions API"
                }
                value={token}
                onChange={(e) => setToken(e.target.value)}
              />
              {settings?.meta_token_masked && (
                <p className="text-xs text-content-muted">Stored token {settings.meta_token_masked}</p>
              )}

              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-medium text-content">Fall back to Analytics Meta token</p>
                  <p className="text-xs text-content-muted">
                    If no dedicated CAPI token is saved, use the Marketing API token from Ads /
                    Analytics.
                  </p>
                </div>
                <Switch checked={useAnalyticsToken} onChange={setUseAnalyticsToken} />
              </div>

              <Input
                label="Test event code (optional)"
                placeholder="TEST12345"
                value={testCode}
                onChange={(e) => setTestCode(e.target.value)}
              />
              <p className="text-xs text-content-muted -mt-2">
                From Events Manager → Test Events. Clear when going live.
              </p>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-content">
                  Purchase event_id scheme (must match Pixel)
                </label>
                <select
                  className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-content"
                  value={eventIdScheme}
                  onChange={(e) => setEventIdScheme(e.target.value)}
                >
                  <option value="order_id">Shopify order id</option>
                  <option value="checkout_token">Checkout / cart token</option>
                  <option value="order_name">Order name (e.g. 1042)</option>
                </select>
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-content">
                  Shopify trigger topic
                </label>
                <select
                  className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-content"
                  value={triggerTopic}
                  onChange={(e) => setTriggerTopic(e.target.value)}
                >
                  <option value="orders/paid">orders/paid (recommended)</option>
                  <option value="orders/create">orders/create (COD / no capture)</option>
                </select>
              </div>

              <Input
                label="Graph API version"
                value={apiVersion}
                onChange={(e) => setApiVersion(e.target.value)}
              />

              {(message || saveError) && (
                <div
                  className={cn(
                    "flex items-start gap-2 rounded-lg px-3 py-2 text-sm",
                    saveError
                      ? "border border-red-200 bg-red-50 text-red-800 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-200"
                      : "border border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900/40 dark:bg-emerald-950/30 dark:text-emerald-200"
                  )}
                >
                  {saveError ? (
                    <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                  ) : (
                    <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" />
                  )}
                  {saveError || message}
                </div>
              )}

              <div className="flex flex-wrap gap-2">
                <Button type="button" onClick={() => void save()} disabled={saving}>
                  <Save className="h-4 w-4" />
                  {saving ? "Saving…" : "Save settings"}
                </Button>
                <Button type="button" variant="secondary" onClick={() => void testSend()} disabled={testing}>
                  <TestTube2 className="h-4 w-4" />
                  {testing ? "Sending…" : "Send test event"}
                </Button>
                <a
                  href="https://business.facebook.com/events_manager2"
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm text-content-muted hover:text-content"
                >
                  Events Manager
                  <ExternalLink className="h-3.5 w-3.5" />
                </a>
              </div>
            </div>
          </Card>

          <Card padding="lg">
            <CardHeader>
              <CardTitle>Webhook</CardTitle>
              <CardDescription>
                Uses the existing Shopify app webhook at{" "}
                <code className="text-xs">POST /api/v1/webhooks/shopify</code> (HMAC verified). Ensure{" "}
                <code className="text-xs">orders/paid</code> (and/or create) is subscribed — already
                registered with email automation topics.
              </CardDescription>
            </CardHeader>
          </Card>
        </div>
      )}
    </div>
  );
}
