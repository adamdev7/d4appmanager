import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  Filter,
  Info,
  List,
  Radar,
  RefreshCw,
  Save,
  Settings2,
  TestTube2,
  Activity,
  Upload,
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

type Tab = "overview" | "events" | "settings";

const TABS: Array<{ id: Tab; label: string; icon: typeof Radar }> = [
  { id: "overview", label: "Overview", icon: Activity },
  { id: "events", label: "Events", icon: List },
  { id: "settings", label: "Settings", icon: Settings2 },
];

const FUNNEL_EVENT_ORDER = [
  "PageView",
  "ViewContent",
  "Search",
  "AddToCart",
  "InitiateCheckout",
  "AddPaymentInfo",
  "Purchase",
] as const;

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

function eventBadgeVariant(name: string) {
  if (name === "Purchase") return "success" as const;
  if (name === "InitiateCheckout" || name === "AddToCart") return "brand" as const;
  return "muted" as const;
}

function formatEntity(ev: MetaCapiEvent) {
  const raw = ev.shopify_order_id || "";
  if (raw.startsWith("browser:")) {
    const parts = raw.split(":");
    return parts.slice(2).join(":") || raw;
  }
  return raw || "—";
}

export function MetaCapiPage() {
  const { activeStore, stores } = useStore();
  const storeId = activeStore?.id ?? stores[0]?.id ?? null;

  const [tab, setTab] = useState<Tab>("overview");
  const [stats, setStats] = useState<MetaCapiStats | null>(null);
  const [settings, setSettings] = useState<MetaCapiSettings | null>(null);
  const [events, setEvents] = useState<MetaCapiEvent[]>([]);
  const [eventTypeCounts, setEventTypeCounts] = useState<Record<string, number>>({});
  const [eventNameFilter, setEventNameFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [error, setError] = useState("");

  const [enabled, setEnabled] = useState(false);
  const [pixelId, setPixelId] = useState("");
  const [token, setToken] = useState("");
  const [useAnalyticsToken, setUseAnalyticsToken] = useState(true);
  const [testCode, setTestCode] = useState("");
  const [eventIdScheme, setEventIdScheme] = useState("order_id");
  const [triggerTopic, setTriggerTopic] = useState("orders/paid");
  const [apiVersion, setApiVersion] = useState("v25.0");
  const [sendInitiateCheckout, setSendInitiateCheckout] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState("");
  const [saveError, setSaveError] = useState("");
  const [orderRef, setOrderRef] = useState("");
  const [backfilling, setBackfilling] = useState(false);
  const [backfillRecentBusy, setBackfillRecentBusy] = useState(false);
  const [backfillMsg, setBackfillMsg] = useState("");
  const [backfillErr, setBackfillErr] = useState("");

  const loadEvents = useCallback(async () => {
    if (!storeId) {
      setEvents([]);
      setEventTypeCounts({});
      return;
    }
    setEventsLoading(true);
    try {
      const e = await api.metaCapi.events(storeId, {
        limit: 150,
        event_name: eventNameFilter,
        status: statusFilter,
      });
      setEvents(e.events);
      setEventTypeCounts(e.event_type_counts || {});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load events");
    } finally {
      setEventsLoading(false);
    }
  }, [storeId, eventNameFilter, statusFilter]);

  const load = useCallback(async () => {
    if (!storeId) {
      setLoading(false);
      setStats(null);
      setSettings(null);
      setEvents([]);
      setEventTypeCounts({});
      return;
    }
    setLoading(true);
    setError("");
    try {
      const s = await api.metaCapi.stats(storeId);
      setStats(s);
      setSettings(s.settings);
      setEnabled(Boolean(s.settings.enabled));
      setPixelId(s.settings.meta_pixel_id ?? "");
      setUseAnalyticsToken(Boolean(s.settings.use_analytics_token));
      setTestCode(s.settings.test_event_code ?? "");
      setEventIdScheme(s.settings.event_id_scheme || "order_id");
      setTriggerTopic(s.settings.trigger_topic || "orders/paid");
      setApiVersion(s.settings.api_version || "v25.0");
      setSendInitiateCheckout(s.settings.send_initiate_checkout !== false);
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

  useEffect(() => {
    void loadEvents();
  }, [loadEvents]);

  const filterOptions = useMemo(() => {
    const known = new Set<string>([...FUNNEL_EVENT_ORDER]);
    Object.keys(eventTypeCounts).forEach((k) => known.add(k));
    Object.keys(stats?.sent_today_by_event || {}).forEach((k) => known.add(k));
    const ordered = FUNNEL_EVENT_ORDER.filter((n) => known.has(n));
    const extras = [...known].filter((n) => !FUNNEL_EVENT_ORDER.includes(n as (typeof FUNNEL_EVENT_ORDER)[number])).sort();
    return ["all", ...ordered, ...extras];
  }, [eventTypeCounts, stats?.sent_today_by_event]);

  const totalLogged = useMemo(
    () => Object.values(eventTypeCounts).reduce((a, b) => a + b, 0),
    [eventTypeCounts]
  );

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
        send_initiate_checkout: sendInitiateCheckout,
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

  const backfillOne = async () => {
    if (!storeId || !orderRef.trim()) return;
    setBackfilling(true);
    setBackfillErr("");
    setBackfillMsg("");
    try {
      const res = await api.metaCapi.backfillOrder(storeId, {
        order_ref: orderRef.trim(),
      });
      if (res.skipped) {
        setBackfillMsg(`Already sent: order ${res.order_name || res.shopify_order_id}`);
      } else if (res.ok) {
        setBackfillMsg(
          `Sent ${res.order_name || res.shopify_order_id} to Meta (event_id=${res.event_id}). Check Events Manager.`
        );
        setOrderRef("");
        await load();
      } else {
        setBackfillErr(res.error || "Backfill failed");
      }
    } catch (err) {
      setBackfillErr(err instanceof Error ? err.message : "Backfill failed");
    } finally {
      setBackfilling(false);
    }
  };

  const backfillToday = async () => {
    if (!storeId) return;
    setBackfillRecentBusy(true);
    setBackfillErr("");
    setBackfillMsg("");
    try {
      const res = await api.metaCapi.backfillRecent(storeId, { hours: 24, limit: 50 });
      setBackfillMsg(
        `Last 24h: examined ${res.examined}, sent ${res.sent}, already sent ${res.skipped}, failed ${res.failed}.`
      );
      if (res.failed > 0) setBackfillErr(`${res.failed} order(s) failed — see event log.`);
      await load();
    } catch (err) {
      setBackfillErr(err instanceof Error ? err.message : "Backfill failed");
    } finally {
      setBackfillRecentBusy(false);
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
            Full Meta funnel via Conversions API: PageView, ViewContent, Search, AddToCart,
            InitiateCheckout, and Purchase — with match-quality fields (fbp/fbc/IP/UA). Theme
            beacons + Shopify webhooks; deduplicates when <code className="text-xs">event_id</code>{" "}
            matches the browser Pixel.
          </p>
        </div>
        <Button
          type="button"
          variant="secondary"
          onClick={() => {
            void load();
            void loadEvents();
          }}
          disabled={loading}
        >
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
              <div className="flex items-center gap-2">
                <Upload className="h-4 w-4 text-brand-600" />
                <CardTitle>Backfill missed sales</CardTitle>
              </div>
              <CardDescription>
                Orders that paid before server-side tracking was enabled were not sent to Meta.
                Push them now (Meta accepts events up to 7 days old).
              </CardDescription>
            </CardHeader>
            <div className="space-y-4">
              <div className="flex flex-wrap gap-2 items-end">
                <div className="flex-1 min-w-[180px]">
                  <Input
                    label="Order number or ID"
                    placeholder="#1042 or Shopify order id"
                    value={orderRef}
                    onChange={(e) => setOrderRef(e.target.value)}
                  />
                </div>
                <Button
                  type="button"
                  onClick={() => void backfillOne()}
                  disabled={backfilling || !orderRef.trim()}
                >
                  {backfilling ? "Sending…" : "Send this order"}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => void backfillToday()}
                  disabled={backfillRecentBusy}
                >
                  {backfillRecentBusy ? "Scanning…" : "Backfill last 24 hours"}
                </Button>
              </div>
              {(backfillMsg || backfillErr) && (
                <div
                  className={cn(
                    "flex items-start gap-2 rounded-lg px-3 py-2 text-sm",
                    backfillErr
                      ? "border border-red-200 bg-red-50 text-red-800 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-200"
                      : "border border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900/40 dark:bg-emerald-950/30 dark:text-emerald-200"
                  )}
                >
                  {backfillErr ? (
                    <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                  ) : (
                    <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" />
                  )}
                  <span>{backfillErr || backfillMsg}</span>
                </div>
              )}
            </div>
          </Card>

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
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <CardTitle>Funnel today</CardTitle>
                  <CardDescription>
                    Sent events by type (PageView through Purchase). Open the Events tab to filter.
                  </CardDescription>
                </div>
                <Button type="button" variant="secondary" onClick={() => setTab("events")}>
                  <Filter className="h-4 w-4" />
                  View all events
                </Button>
              </div>
            </CardHeader>
            {Object.keys(stats?.sent_today_by_event || {}).length === 0 && totalLogged === 0 ? (
              <p className="text-sm text-content-muted">
                No funnel events logged yet. Publish the theme with the browser token, then browse the
                store.
              </p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {(Object.keys(stats?.sent_today_by_event || {}).length
                  ? Object.entries(stats?.sent_today_by_event || {})
                  : Object.entries(eventTypeCounts)
                )
                  .sort((a, b) => {
                    const ai = FUNNEL_EVENT_ORDER.indexOf(a[0] as (typeof FUNNEL_EVENT_ORDER)[number]);
                    const bi = FUNNEL_EVENT_ORDER.indexOf(b[0] as (typeof FUNNEL_EVENT_ORDER)[number]);
                    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
                  })
                  .map(([name, count]) => (
                    <button
                      key={name}
                      type="button"
                      onClick={() => {
                        setEventNameFilter(name);
                        setTab("events");
                      }}
                      className="rounded-lg border border-border bg-surface-muted/40 px-3 py-2 text-left hover:border-brand-400 transition-colors"
                    >
                      <p className="text-xs text-content-muted">{name}</p>
                      <p className="text-lg font-semibold text-content">{count}</p>
                    </button>
                  ))}
              </div>
            )}
          </Card>

          <Card padding="lg">
            <CardHeader>
              <CardTitle>Recent events</CardTitle>
              <CardDescription>
                Latest CAPI sends (all types). Use the Events tab for filters.
              </CardDescription>
            </CardHeader>
            {events.length === 0 ? (
              <p className="text-sm text-content-muted">
                No events yet. Theme beacons + paid orders will appear here.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-content-subtle">
                      <th className="py-2 pr-3 font-medium">When</th>
                      <th className="py-2 pr-3 font-medium">Type</th>
                      <th className="py-2 pr-3 font-medium">Ref</th>
                      <th className="py-2 pr-3 font-medium">Status</th>
                      <th className="py-2 pr-3 font-medium">Value</th>
                      <th className="py-2 font-medium">Meta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.slice(0, 12).map((ev) => (
                      <tr key={ev.id} className="border-b border-border/60">
                        <td className="py-2.5 pr-3 text-content-muted whitespace-nowrap">
                          {formatTs(ev.sent_at || ev.created_at)}
                        </td>
                        <td className="py-2.5 pr-3">
                          <Badge variant={eventBadgeVariant(ev.event_name || "Purchase")}>
                            {ev.event_name || "Purchase"}
                          </Badge>
                        </td>
                        <td
                          className="py-2.5 pr-3 font-mono text-xs max-w-[160px] truncate"
                          title={ev.shopify_order_id}
                        >
                          {formatEntity(ev)}
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

      {tab === "events" && (
        <div className="space-y-4">
          <Card padding="lg">
            <CardHeader>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <CardTitle>Event log</CardTitle>
                  <CardDescription>
                    All Meta CAPI events App Manager sent or tried to send ({totalLogged} logged).
                  </CardDescription>
                </div>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => void loadEvents()}
                  disabled={eventsLoading}
                >
                  <RefreshCw className={cn("h-4 w-4", eventsLoading && "animate-spin")} />
                  Refresh
                </Button>
              </div>
            </CardHeader>

            <div className="space-y-3 mb-4">
              <p className="text-xs font-medium uppercase tracking-wider text-content-subtle">
                Event type
              </p>
              <div className="flex flex-wrap gap-2">
                {filterOptions.map((name) => {
                  const count =
                    name === "all" ? totalLogged : eventTypeCounts[name] || 0;
                  const active = eventNameFilter === name;
                  return (
                    <button
                      key={name}
                      type="button"
                      onClick={() => setEventNameFilter(name)}
                      className={cn(
                        "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                        active
                          ? "border-brand-500 bg-brand-50 text-brand-800 dark:bg-brand-950/40 dark:text-brand-200"
                          : "border-border text-content-muted hover:text-content"
                      )}
                    >
                      {name === "all" ? "All" : name}
                      <span className="ml-1 opacity-70">({count})</span>
                    </button>
                  );
                })}
              </div>

              <p className="text-xs font-medium uppercase tracking-wider text-content-subtle pt-1">
                Status
              </p>
              <div className="flex flex-wrap gap-2">
                {["all", "sent", "failed", "pending", "skipped"].map((st) => {
                  const active = statusFilter === st;
                  return (
                    <button
                      key={st}
                      type="button"
                      onClick={() => setStatusFilter(st)}
                      className={cn(
                        "rounded-full border px-3 py-1 text-xs font-medium capitalize transition-colors",
                        active
                          ? "border-brand-500 bg-brand-50 text-brand-800 dark:bg-brand-950/40 dark:text-brand-200"
                          : "border-border text-content-muted hover:text-content"
                      )}
                    >
                      {st}
                    </button>
                  );
                })}
              </div>
            </div>

            {eventsLoading && events.length === 0 ? (
              <p className="text-sm text-content-muted">Loading events…</p>
            ) : events.length === 0 ? (
              <p className="text-sm text-content-muted">
                No events match this filter. Try All, or confirm the theme browser token is set.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-content-subtle">
                      <th className="py-2 pr-3 font-medium">When</th>
                      <th className="py-2 pr-3 font-medium">Type</th>
                      <th className="py-2 pr-3 font-medium">Source</th>
                      <th className="py-2 pr-3 font-medium">Ref</th>
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
                        <td className="py-2.5 pr-3">
                          <Badge variant={eventBadgeVariant(ev.event_name || "Purchase")}>
                            {ev.event_name || "Purchase"}
                          </Badge>
                        </td>
                        <td className="py-2.5 pr-3 text-xs text-content-muted">
                          {ev.topic || "—"}
                        </td>
                        <td
                          className="py-2.5 pr-3 font-mono text-xs max-w-[140px] truncate"
                          title={ev.shopify_order_id}
                        >
                          {formatEntity(ev)}
                        </td>
                        <td
                          className="py-2.5 pr-3 font-mono text-xs max-w-[140px] truncate"
                          title={ev.event_id}
                        >
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
                        <td className="py-2.5 text-xs text-content-muted max-w-[220px]">
                          {ev.error_message ? (
                            <span className="text-red-600 dark:text-red-400" title={ev.error_message}>
                              {ev.error_message.slice(0, 100)}
                            </span>
                          ) : (
                            <span title={ev.meta_fbtrace_id ?? undefined}>
                              recv={ev.meta_events_received ?? "—"}
                              {ev.attempts > 1 ? ` · try ${ev.attempts}` : ""}
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

              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-medium text-content">Send InitiateCheckout</p>
                  <p className="text-xs text-content-muted">
                    Also fire Meta InitiateCheckout on Shopify <code>checkouts/create</code> (native
                    checkout). Phoenix checkout fires InitiateCheckout from the theme on redirect.
                  </p>
                </div>
                <Switch checked={sendInitiateCheckout} onChange={setSendInitiateCheckout} />
              </div>

              {settings?.browser_event_token && (
                <div className="rounded-lg border border-border bg-surface-muted/40 px-3 py-3 space-y-1">
                  <p className="text-sm font-medium text-content">Theme browser event token</p>
                  <p className="text-xs text-content-muted">
                    Paste into Shopify theme settings → <strong>Meta CAPI (App Manager)</strong> →
                    Browser event token. Required for PageView, ViewContent, Search, AddToCart, and
                    Phoenix InitiateCheckout.
                  </p>
                  <code className="block text-xs break-all text-content mt-1">
                    {settings.browser_event_token}
                  </code>
                </div>
              )}

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
