import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  ExternalLink,
  Package,
  RefreshCw,
  Search,
  Truck,
} from "lucide-react";
import { useStore } from "@/context/StoreContext";
import { api, type TrackingOverview, type TrackOrderResult } from "@/lib/api";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { TrackingGuide } from "@/components/tracking/TrackingGuide";
import { TrackingSettingsPanel } from "@/components/tracking/TrackingSettingsPanel";

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
  if (status === "in_transit") return "In transit";
  if (status === "delivered") return "Delivered";
  return "Pending";
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
  const api = apiBase.replace(/\/$/, "");
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
  var API_BASE = ${JSON.stringify(api)};
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
  const [overview, setOverview] = useState<TrackingOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [setupOpen, setSetupOpen] = useState(false);

  const [testOrder, setTestOrder] = useState("");
  const [testEmail, setTestEmail] = useState("");
  const [testLoading, setTestLoading] = useState(false);
  const [testResult, setTestResult] = useState<TrackOrderResult | null>(null);
  const [testError, setTestError] = useState("");

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

  useEffect(() => {
    load();
  }, [load]);

  const shopifySnippet = useMemo(() => {
    if (!overview) return "";
    return buildShopifySnippet(overview.store_id, overview.track_endpoint.replace(/\/api\/track-order$/, ""));
  }, [overview]);

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
          <CardTitle>Select a store</CardTitle>
          <CardDescription className="mt-2">
            Choose a store from the sidebar, or{" "}
            <Link to="/settings/stores" className="text-brand-600 hover:underline">
              connect your Shopify store
            </Link>{" "}
            to use order tracking.
          </CardDescription>
        </Card>
      </div>
    );
  }

  const stats = overview?.stats;

  return (
    <div className="max-w-4xl mx-auto space-y-8 pb-10">
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
            Tracking System
          </h1>
          <p className="text-content-muted mt-2 max-w-lg">
            Let customers track orders on your Shopify store. Data syncs from webhooks for{" "}
            <strong className="text-content">{activeStore.name}</strong>.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-1.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {error && (
        <p className="text-sm text-red-600 dark:text-red-400 bg-red-500/10 rounded-xl px-4 py-3">
          {error}
        </p>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <div className="rounded-xl border border-border bg-surface p-4">
          <p className="text-2xl font-semibold text-content">{stats?.orders_synced ?? "—"}</p>
          <p className="text-xs text-content-muted mt-1">Orders synced</p>
        </div>
        <div className="rounded-xl border border-border bg-surface p-4">
          <p className="text-2xl font-semibold text-content">{stats?.with_tracking ?? "—"}</p>
          <p className="text-xs text-content-muted mt-1">With tracking number</p>
        </div>
        <div className="rounded-xl border border-border bg-surface p-4 col-span-2 sm:col-span-1">
          <p className="text-sm font-medium text-content truncate">
            {overview?.carrier_enrichment.auto_enrich ? "Auto-enrich on" : "Auto-enrich off"}
          </p>
          <p className="text-xs text-content-muted mt-1">
            {overview?.carrier_enrichment.track17 || overview?.carrier_enrichment.yunexpress
              ? "17TRACK / YunExpress configured"
              : "Add API keys below"}
          </p>
        </div>
      </div>

      <TrackingGuide />

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
            <CardTitle>Shopify connection</CardTitle>
            <CardDescription>
              Use these values in your theme. Customers need order number + email to look up a
              shipment.
            </CardDescription>
          </CardHeader>
          <div className="space-y-4 px-6 pb-6">
            <div className="rounded-xl bg-surface-muted border border-border p-4 space-y-3">
              <div>
                <p className="text-xs font-medium text-content-subtle uppercase tracking-wide">
                  Store ID
                </p>
                <p className="text-sm font-mono text-content mt-1 break-all">{overview.store_id}</p>
              </div>
              <div>
                <p className="text-xs font-medium text-content-subtle uppercase tracking-wide">
                  API endpoint
                </p>
                <p className="text-sm font-mono text-content mt-1 break-all">
                  {overview.track_endpoint}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <CopyButton value={overview.store_id} label="Copy store ID" />
                <CopyButton value={overview.track_endpoint} label="Copy endpoint" />
              </div>
            </div>

            <button
              type="button"
              className="flex w-full items-center justify-between text-sm font-medium text-content hover:text-brand-600 dark:hover:text-brand-400"
              onClick={() => setSetupOpen((o) => !o)}
            >
              <span>Theme setup &amp; embed code</span>
              {setupOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>

            {setupOpen && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                className="space-y-3 text-sm text-content-muted"
              >
                <ol className="list-decimal list-inside space-y-2">
                  <li>
                    In Shopify Admin, create a page titled <strong className="text-content">Track Your Order</strong>.
                  </li>
                  <li>
                    Theme → Edit code → add template{" "}
                    <code className="text-xs bg-surface-muted px-1 rounded">page.track-order.liquid</code>
                  </li>
                  <li>Paste the snippet below and assign the template to your page.</li>
                  <li>
                    Set <code className="text-xs bg-surface-muted px-1 rounded">API_BASE</code> to your
                    public App Manager URL (same host as the endpoint above).
                  </li>
                </ol>
                <div className="relative">
                  <pre className="text-xs overflow-x-auto rounded-xl border border-border bg-surface-muted p-4 max-h-64">
                    {shopifySnippet}
                  </pre>
                  <div className="mt-2">
                    <CopyButton value={shopifySnippet} label="Copy theme snippet" />
                  </div>
                </div>
              </motion.div>
            )}
          </div>
        </Card>
      )}

      <Card padding="lg">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Search className="h-5 w-5 text-content-muted" />
            Test lookup
          </CardTitle>
          <CardDescription>
            Same request your Shopify page will make — verifies order number and email.
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
            label="Email"
            type="email"
            placeholder="customer@example.com"
            value={testEmail}
            onChange={(e) => setTestEmail(e.target.value)}
            required
          />
          <div className="sm:col-span-2">
            <Button type="submit" isLoading={testLoading} disabled={!overview}>
              Look up order
            </Button>
          </div>
        </form>
        {testError && (
          <p className="px-6 pb-4 text-sm text-red-600 dark:text-red-400">{testError}</p>
        )}
        {testResult && (
          <div className="mx-6 mb-6 rounded-xl border border-brand-500/30 bg-brand-500/5 p-4 space-y-2">
            <div className="flex items-center gap-2">
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
                {testResult.timeline.slice().reverse().map((ev, i) => (
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

      <Card padding="lg">
        <CardHeader>
          <CardTitle>Synced orders</CardTitle>
          <CardDescription>
            Updated when Shopify sends order and fulfillment webhooks.
            {overview?.shop_domain && (
              <>
                {" "}
                <a
                  href={`https://${overview.shop_domain}/admin`}
                  target="_blank"
                  rel="noreferrer"
                  className="text-brand-600 hover:underline inline-flex items-center gap-0.5"
                >
                  Open Shopify admin
                  <ExternalLink className="h-3 w-3" />
                </a>
              </>
            )}
          </CardDescription>
        </CardHeader>
        {!overview?.recent_orders.length ? (
          <p className="text-sm text-content-muted px-6 pb-6">
            No orders yet. Fulfill an order in Shopify or use test lookup after a webhook arrives.
          </p>
        ) : (
          <ul className="divide-y divide-border border-t border-border">
            {overview.recent_orders.map((order) => (
              <li
                key={order.id}
                className="px-6 py-4 flex flex-wrap items-start justify-between gap-3"
              >
                <div>
                  <p className="font-medium text-content text-sm">{order.order_number}</p>
                  <p className="text-sm text-content-muted mt-0.5">{order.customer_email}</p>
                  {order.tracking_number && (
                    <p className="text-xs text-content-subtle mt-1 font-mono">
                      {order.tracking_number}
                      {order.carrier ? ` · ${order.carrier}` : ""}
                    </p>
                  )}
                </div>
                <div className="text-right">
                  <Badge variant={statusBadgeVariant(order.status)}>
                    {statusLabel(order.status)}
                  </Badge>
                  <p className="text-xs text-content-subtle mt-1">
                    {formatTime(order.last_updated_at)}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
