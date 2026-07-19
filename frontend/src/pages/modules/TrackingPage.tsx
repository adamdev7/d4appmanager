import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  Check,
  CheckCircle2,
  Copy,
  ExternalLink,
  Package,
  PackageCheck,
  PackageSearch,
  RefreshCw,
  Search,
  Settings2,
  Store,
  Truck,
} from "lucide-react";
import { useStore } from "@/context/StoreContext";
import { api, type TrackingOverview, type TrackOrderResult } from "@/lib/api";
import { cn } from "@/lib/cn";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { TrackingSettingsPanel } from "@/components/tracking/TrackingSettingsPanel";

type Tab = "orders" | "settings";
type StatusFilter = "all" | "pending" | "in_transit" | "delivered";

const TABS: Array<{ id: Tab; label: string; icon: typeof Package }> = [
  { id: "orders", label: "Orders", icon: Package },
  { id: "settings", label: "Settings", icon: Settings2 },
];

function formatTime(iso: string | null) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function statusBadgeVariant(status: string) {
  if (status === "delivered") return "success" as const;
  if (status === "in_transit") return "brand" as const;
  return "muted" as const;
}

function statusLabel(status: string) {
  if (status === "in_transit") return "On the way";
  if (status === "delivered") return "Delivered";
  return "Preparing";
}

async function copyText(text: string) {
  await navigator.clipboard.writeText(text);
}

function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      onClick={async () => {
        await copyText(value);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }}
    >
      {copied ? <Check className="h-4 w-4 mr-1.5" /> : <Copy className="h-4 w-4 mr-1.5" />}
      {copied ? "Copied" : label}
    </Button>
  );
}

function buildShopifySnippet(storeId: string, apiBase: string) {
  const apiUrl = apiBase.replace(/\/$/, "");
  return `{% comment %} App Manager — Track Your Order {% endcomment %}
<div id="track-order-app" style="max-width:520px;margin:2rem auto;">
  <form id="track-order-form" style="display:grid;gap:1rem;">
    <label>Order number<input type="text" name="order_number" required placeholder="#1001" style="width:100%"></label>
    <label>Email<input type="email" name="email" required style="width:100%"></label>
    <button type="submit">Track order</button>
  </form>
  <div id="track-order-result" style="margin-top:1.5rem;"></div>
</div>
<script>
(function(){
  var STORE_ID = ${JSON.stringify(storeId)};
  var API_BASE = ${JSON.stringify(apiUrl)};
  var form = document.getElementById("track-order-form");
  var resultEl = document.getElementById("track-order-result");
  form.addEventListener("submit", function(e){
    e.preventDefault();
    resultEl.textContent = "Looking up…";
    var url = new URL(API_BASE + "/api/track-order");
    url.searchParams.set("order_number", form.order_number.value.trim());
    url.searchParams.set("email", form.email.value.trim());
    url.searchParams.set("store_id", STORE_ID);
    fetch(url.toString(), { headers: { Accept: "application/json" } })
      .then(function(r){ return r.json().then(function(d){ return { ok: r.ok, data: d }; }); })
      .then(function(res){
        if (!res.ok) { resultEl.textContent = res.data.detail || "Order not found."; return; }
        var d = res.data;
        resultEl.innerHTML = "<p><strong>Status:</strong> " + d.status + "</p>"
          + (d.tracking_number ? "<p><strong>Tracking:</strong> " + d.tracking_number + "</p>" : "")
          + (d.carrier ? "<p><strong>Carrier:</strong> " + d.carrier + "</p>" : "");
      })
      .catch(function(){ resultEl.textContent = "Could not reach tracking service."; });
  });
})();
</script>`;
}

export function TrackingPage() {
  const { activeStore } = useStore();
  const [tab, setTab] = useState<Tab>("orders");
  const [overview, setOverview] = useState<TrackingOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState("");
  const [syncMessage, setSyncMessage] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [searchQuery, setSearchQuery] = useState("");

  const [testOrder, setTestOrder] = useState("");
  const [testEmail, setTestEmail] = useState("");
  const [testLoading, setTestLoading] = useState(false);
  const [testResult, setTestResult] = useState<TrackOrderResult | null>(null);
  const [testError, setTestError] = useState("");
  const [setupOpen, setSetupOpen] = useState(false);

  const load = useCallback(async () => {
    if (!activeStore?.id) return;
    setLoading(true);
    setError("");
    try {
      const data = await api.tracking.overview(activeStore.id);
      setOverview(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load tracking");
      setOverview(null);
    } finally {
      setLoading(false);
    }
  }, [activeStore?.id]);

  const syncFromShopify = useCallback(
    async (silent = false) => {
      if (!activeStore?.id) return;
      setSyncing(true);
      if (!silent) {
        setError("");
        setSyncMessage("");
      }
      try {
        const result = await api.tracking.sync(activeStore.id);
        setOverview(result.overview);
        const changed =
          (result.sync.created || 0) + (result.sync.updated || 0) > 0;
        if (!silent || changed) {
          setSyncMessage(result.message);
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Could not sync from Shopify";
        if (!silent) setError(msg);
      } finally {
        setSyncing(false);
      }
    },
    [activeStore?.id]
  );

  useEffect(() => {
    load();
  }, [load]);

  // Auto-sync Shopify orders when opening the page for a connected store.
  useEffect(() => {
    if (!activeStore?.id) return;
    if (activeStore.status !== "connected") return;
    void syncFromShopify(true);
  }, [activeStore?.id, activeStore?.status, syncFromShopify]);

  const shopifySnippet = useMemo(() => {
    if (!overview) return "";
    return buildShopifySnippet(
      overview.store_id,
      overview.track_endpoint.replace(/\/api\/track-order$/, "")
    );
  }, [overview]);

  const filteredOrders = useMemo(() => {
    const orders = overview?.recent_orders ?? [];
    const q = searchQuery.trim().toLowerCase();
    return orders.filter((order) => {
      if (statusFilter !== "all" && order.status !== statusFilter) return false;
      if (!q) return true;
      return (
        order.order_number.toLowerCase().includes(q) ||
        order.customer_email.toLowerCase().includes(q) ||
        (order.tracking_number || "").toLowerCase().includes(q)
      );
    });
  }, [overview?.recent_orders, searchQuery, statusFilter]);

  const runTestLookup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!overview) return;
    setTestLoading(true);
    setTestError("");
    setTestResult(null);
    try {
      const data = await api.tracking.lookup({
        order_number: testOrder.trim(),
        email: testEmail.trim(),
        store_id: overview.store_id,
      });
      setTestResult(data);
    } catch (err) {
      setTestError(err instanceof Error ? err.message : "Lookup failed");
    } finally {
      setTestLoading(false);
    }
  };

  if (!activeStore) {
    return (
      <div className="max-w-2xl mx-auto">
        <Card padding="lg">
          <CardTitle>Choose a store</CardTitle>
          <CardDescription className="mt-2">
            Pick a store from the sidebar, or{" "}
            <Link to="/settings/stores" className="text-brand-600 hover:underline">
              connect your Shopify store
            </Link>{" "}
            to start tracking orders.
          </CardDescription>
        </Card>
      </div>
    );
  }

  const stats = overview?.stats;
  const shopifyConnected =
    overview?.shopify_connected ?? activeStore.status === "connected";

  return (
    <div className="max-w-5xl mx-auto space-y-6 pb-10">
      <Link
        to="/dashboard"
        className="inline-flex items-center gap-1.5 text-sm text-content-muted hover:text-content"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to overview
      </Link>

      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-content flex items-center gap-2">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-500/10 text-brand-600 dark:text-brand-400">
              <Package className="h-5 w-5" />
            </span>
            Order Tracking
          </h1>
          <p className="text-content-muted mt-2 max-w-xl">
            See where your customers&apos; packages are. Orders sync automatically from{" "}
            <strong className="font-medium text-content">{activeStore.name}</strong> on Shopify.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => syncFromShopify(false)}
            disabled={syncing || !shopifyConnected}
          >
            <RefreshCw className={`h-4 w-4 mr-1.5 ${syncing ? "animate-spin" : ""}`} />
            {syncing ? "Syncing…" : "Sync now"}
          </Button>
        </div>
      </div>

      {error && (
        <p className="text-sm text-red-600 dark:text-red-400 bg-red-500/10 rounded-xl px-4 py-3">
          {error}
        </p>
      )}

      {syncMessage && !error && (
        <p className="text-sm text-green-700 dark:text-green-400 bg-green-500/10 rounded-xl px-4 py-3 flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          {syncMessage}
        </p>
      )}

      <div className="flex gap-1 border-b border-border overflow-x-auto">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors whitespace-nowrap",
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

      {tab === "orders" && (
        <div className="space-y-6">
          <div
            className={cn(
              "rounded-xl border px-4 py-3 flex flex-wrap items-center gap-3 text-sm",
              shopifyConnected
                ? "border-green-500/25 bg-green-500/5 text-content"
                : "border-amber-500/30 bg-amber-500/5 text-content"
            )}
          >
            <Store className="h-4 w-4 shrink-0 text-content-muted" />
            {shopifyConnected ? (
              <span>
                Connected to Shopify
                {overview?.shop_domain ? (
                  <>
                    {" "}
                    ·{" "}
                    <a
                      href={`https://${overview.shop_domain}/admin/orders`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-brand-600 hover:underline inline-flex items-center gap-0.5"
                    >
                      Open orders
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </>
                ) : null}
                . New and updated orders appear here automatically.
              </span>
            ) : (
              <span>
                This store isn&apos;t connected to Shopify yet.{" "}
                <Link to="/settings/stores" className="text-brand-600 hover:underline">
                  Connect it in Settings → Stores
                </Link>{" "}
                so orders can sync.
              </span>
            )}
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard
              label="All orders"
              value={stats?.orders_synced}
              loading={loading && !overview}
            />
            <StatCard
              label="With tracking"
              value={stats?.with_tracking}
              loading={loading && !overview}
            />
            <StatCard
              label="On the way"
              value={stats?.in_transit}
              loading={loading && !overview}
            />
            <StatCard
              label="Delivered"
              value={stats?.delivered}
              loading={loading && !overview}
            />
          </div>

          <Card padding="lg">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Search className="h-5 w-5 text-content-muted" />
                Look up an order
              </CardTitle>
              <CardDescription>
                Check what a customer will see using their order number and email.
              </CardDescription>
            </CardHeader>
            <form onSubmit={runTestLookup} className="px-6 pb-6 grid sm:grid-cols-2 gap-4">
              <Input
                label="Order number"
                placeholder="#1001"
                value={testOrder}
                onChange={(e) => setTestOrder(e.target.value)}
                required
              />
              <Input
                label="Customer email"
                type="email"
                placeholder="customer@example.com"
                value={testEmail}
                onChange={(e) => setTestEmail(e.target.value)}
                required
              />
              <div className="sm:col-span-2">
                <Button type="submit" isLoading={testLoading} disabled={!overview}>
                  Find order
                </Button>
              </div>
            </form>
            {testError && (
              <p className="px-6 pb-4 text-sm text-red-600 dark:text-red-400">{testError}</p>
            )}
            {testResult && (
              <div className="mx-6 mb-6 rounded-xl border border-brand-500/30 bg-brand-500/5 p-4 space-y-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <Truck className="h-4 w-4 text-brand-600" />
                  <span className="font-medium text-content">{testResult.order_number}</span>
                  <Badge variant={statusBadgeVariant(testResult.status)}>
                    {statusLabel(testResult.status)}
                  </Badge>
                </div>
                {testResult.tracking_number && (
                  <p className="text-sm text-content-muted">
                    Tracking: <span className="text-content">{testResult.tracking_number}</span>
                    {testResult.carrier ? ` · ${testResult.carrier}` : ""}
                  </p>
                )}
                {testResult.timeline.length > 0 && (
                  <ul className="text-sm text-content-muted space-y-1 mt-2 border-t border-border pt-2">
                    {testResult.timeline
                      .slice()
                      .reverse()
                      .map((ev, i) => (
                        <li key={i}>
                          {ev.description}
                          {ev.at && (
                            <span className="text-content-subtle text-xs ml-1">
                              ({formatTime(ev.at)})
                            </span>
                          )}
                        </li>
                      ))}
                  </ul>
                )}
              </div>
            )}
          </Card>

          <Card padding="none" className="overflow-hidden">
            <div className="px-6 py-5 border-b border-border space-y-4">
              <div>
                <h3 className="text-base font-semibold text-content">Synced orders</h3>
                <p className="text-sm text-content-muted mt-0.5">
                  From your Shopify store only — updates when orders are created or shipped.
                </p>
              </div>
              <div className="flex flex-col sm:flex-row gap-3">
                <div className="flex-1">
                  <Input
                    placeholder="Search order #, email, or tracking…"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                  />
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {(
                    [
                      ["all", "All"],
                      ["pending", "Preparing"],
                      ["in_transit", "On the way"],
                      ["delivered", "Delivered"],
                    ] as const
                  ).map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setStatusFilter(value)}
                      className={cn(
                        "rounded-lg px-3 py-2 text-xs font-medium transition-colors",
                        statusFilter === value
                          ? "bg-brand-500/15 text-brand-700 dark:text-brand-400"
                          : "bg-surface-muted text-content-muted hover:text-content"
                      )}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {!overview?.recent_orders.length ? (
              <div className="px-6 py-12 text-center">
                <PackageSearch className="h-10 w-10 mx-auto text-content-subtle mb-3" />
                <p className="text-sm font-medium text-content">No orders synced yet</p>
                <p className="text-sm text-content-muted mt-1 max-w-sm mx-auto">
                  {shopifyConnected
                    ? "Click Sync now to pull recent orders from Shopify, or wait for new orders to come in."
                    : "Connect your Shopify store first, then sync."}
                </p>
                {shopifyConnected && (
                  <Button
                    className="mt-4"
                    size="sm"
                    onClick={() => syncFromShopify(false)}
                    isLoading={syncing}
                  >
                    Sync from Shopify
                  </Button>
                )}
              </div>
            ) : filteredOrders.length === 0 ? (
              <p className="text-sm text-content-muted px-6 py-8 text-center">
                No orders match your search or filter.
              </p>
            ) : (
              <ul className="divide-y divide-border">
                {filteredOrders.map((order) => (
                  <li
                    key={order.id}
                    className="px-6 py-4 flex flex-wrap items-start justify-between gap-3 hover:bg-surface-muted/50 transition-colors"
                  >
                    <div className="min-w-0">
                      <p className="font-medium text-content text-sm">{order.order_number}</p>
                      <p className="text-sm text-content-muted mt-0.5 truncate">
                        {order.customer_email}
                      </p>
                      {order.tracking_number ? (
                        <p className="text-xs text-content-subtle mt-1.5 font-mono">
                          {order.tracking_number}
                          {order.carrier ? ` · ${order.carrier}` : ""}
                        </p>
                      ) : (
                        <p className="text-xs text-content-subtle mt-1.5">No tracking number yet</p>
                      )}
                    </div>
                    <div className="text-right shrink-0">
                      <Badge variant={statusBadgeVariant(order.status)}>
                        {statusLabel(order.status)}
                      </Badge>
                      <p className="text-xs text-content-subtle mt-1.5">
                        {formatTime(order.last_updated_at)}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}

      {tab === "settings" && (
        <div className="space-y-6">
          <Card padding="lg">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <PackageCheck className="h-5 w-5 text-content-muted" />
                Shopify order sync
              </CardTitle>
              <CardDescription>
                Tracking only uses orders from your connected Shopify store — nothing else is
                imported.
              </CardDescription>
            </CardHeader>
            <div className="px-6 pb-6 space-y-4">
              <ul className="text-sm text-content-muted space-y-2">
                <li className="flex gap-2">
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-brand-600 mt-0.5" />
                  New orders and shipments sync automatically from Shopify.
                </li>
                <li className="flex gap-2">
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-brand-600 mt-0.5" />
                  Opening this page also pulls your latest Shopify orders.
                </li>
                <li className="flex gap-2">
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-brand-600 mt-0.5" />
                  You can press <strong className="font-medium text-content">Sync now</strong> anytime
                  to refresh.
                </li>
              </ul>
              <div className="flex flex-wrap gap-2">
                <Button
                  onClick={() => syncFromShopify(false)}
                  isLoading={syncing}
                  disabled={!shopifyConnected}
                >
                  <RefreshCw className="h-4 w-4 mr-1.5" />
                  Sync from Shopify
                </Button>
                <Link
                  to="/settings/stores"
                  className="inline-flex h-10 items-center justify-center rounded-lg border border-border bg-surface px-4 text-sm font-medium text-content hover:bg-surface-muted transition-colors"
                >
                  Manage stores
                </Link>
              </div>
            </div>
          </Card>

          {activeStore && (
            <TrackingSettingsPanel
              storeId={activeStore.id}
              settings={overview?.settings ?? null}
              onSaved={load}
            />
          )}

          {overview && (
            <Card padding="lg">
              <CardHeader>
                <CardTitle>Customer track page</CardTitle>
                <CardDescription>
                  Add a simple &quot;Track your order&quot; page on your Shopify store so customers
                  can check status with their order number and email.
                </CardDescription>
              </CardHeader>
              <div className="px-6 pb-6 space-y-4">
                <ol className="list-decimal list-inside space-y-2 text-sm text-content-muted">
                  <li>
                    In Shopify, create a page called{" "}
                    <strong className="text-content">Track Your Order</strong>.
                  </li>
                  <li>
                    Open your theme editor → Edit code → create{" "}
                    <code className="text-xs bg-surface-muted px-1.5 py-0.5 rounded">
                      page.track-order.liquid
                    </code>
                    .
                  </li>
                  <li>Paste the ready-made code below, then assign that template to your page.</li>
                </ol>

                <button
                  type="button"
                  className="text-sm font-medium text-brand-600 hover:underline"
                  onClick={() => setSetupOpen((o) => !o)}
                >
                  {setupOpen ? "Hide install code" : "Show install code"}
                </button>

                {setupOpen && (
                  <div className="space-y-3">
                    <pre className="text-xs overflow-x-auto rounded-xl border border-border bg-surface-muted p-4 max-h-56">
                      {shopifySnippet}
                    </pre>
                    <CopyButton value={shopifySnippet} label="Copy install code" />
                    <p className="text-xs text-content-subtle">
                      This code is already set up for your store. You usually don&apos;t need to
                      change anything.
                    </p>
                  </div>
                )}
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  loading,
}: {
  label: string;
  value: number | undefined;
  loading?: boolean;
}) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <p className="text-2xl font-semibold text-content tabular-nums">
        {loading && value === undefined ? "—" : (value ?? 0)}
      </p>
      <p className="text-xs text-content-muted mt-1">{label}</p>
    </div>
  );
}
