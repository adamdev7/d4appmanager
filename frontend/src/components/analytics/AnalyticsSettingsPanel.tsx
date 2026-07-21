import { useEffect, useState } from "react";
import {
  CalendarRange,
  ExternalLink,
  KeyRound,
  PlugZap,
  RefreshCw,
  Repeat,
  Save,
  TestTube2,
  Trash2,
  Wallet,
} from "lucide-react";
import { api, type AnalyticsSettings } from "@/lib/api";
import type { AnalyticsStripeAccount } from "@/lib/analyticsTypes";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";

type Props = {
  storeId: string;
  settings: AnalyticsSettings | null;
  onSaved: () => void;
};

export function AnalyticsSettingsPanel({ storeId, settings, onSaved }: Props) {
  const [metaToken, setMetaToken] = useState("");
  const [adAccountId, setAdAccountId] = useState("");
  const [shippingCost, setShippingCost] = useState("0");
  const [feePercent, setFeePercent] = useState("2.9");
  const [feeFixed, setFeeFixed] = useState("0.30");
  const [analyticsStartDate, setAnalyticsStartDate] = useState("");
  const [priorRevenue, setPriorRevenue] = useState("0");
  const [priorCosts, setPriorCosts] = useState("0");
  const [priorLabel, setPriorLabel] = useState("Prior site (Stripe)");
  const [mrrEnabled, setMrrEnabled] = useState(false);
  const [mrrSource, setMrrSource] = useState<"manual" | "multi_stripe">("manual");
  const [mrrAmount, setMrrAmount] = useState("0");
  const [mrrSubscribers, setMrrSubscribers] = useState("0");
  const [mrrChurn, setMrrChurn] = useState("0");
  const [stripeLabel, setStripeLabel] = useState("");
  const [stripeKey, setStripeKey] = useState("");
  const [stripeAccounts, setStripeAccounts] = useState<AnalyticsStripeAccount[]>([]);
  const [freshWebhookSecret, setFreshWebhookSecret] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [testResult, setTestResult] = useState("");

  useEffect(() => {
    if (!settings) return;
    setAdAccountId(settings.meta_ad_account_id ?? "");
    setShippingCost(String(settings.default_shipping_cost));
    setFeePercent(String(settings.transaction_fee_percent));
    setFeeFixed(String(settings.transaction_fee_fixed));
    setAnalyticsStartDate(settings.analytics_start_date ?? "");
    setPriorRevenue(String(settings.prior_external_revenue ?? 0));
    setPriorCosts(String(settings.prior_external_costs ?? 0));
    setPriorLabel(settings.prior_external_label || "Prior site (Stripe)");
    setMrrEnabled(Boolean(settings.mrr_enabled));
    setMrrSource(settings.mrr_source === "multi_stripe" ? "multi_stripe" : "manual");
    setMrrAmount(String(settings.mrr_manual_amount ?? 0));
    setMrrSubscribers(String(settings.mrr_manual_subscribers ?? 0));
    setMrrChurn(String(settings.mrr_manual_churn_pct ?? 0));
    setStripeAccounts(settings.stripe_accounts ?? []);
    if (settings.mrr_webhook_secret) setFreshWebhookSecret(settings.mrr_webhook_secret);
    setMetaToken("");
  }, [settings]);

  const save = async (extra?: Record<string, unknown>) => {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const payload: Record<string, unknown> = {
        meta_ad_account_id: adAccountId.trim() || null,
        default_shipping_cost: parseFloat(shippingCost) || 0,
        transaction_fee_percent: parseFloat(feePercent) || 0,
        transaction_fee_fixed: parseFloat(feeFixed) || 0,
        analytics_start_date: analyticsStartDate.trim() || "",
        prior_external_revenue: parseFloat(priorRevenue) || 0,
        prior_external_costs: parseFloat(priorCosts) || 0,
        prior_external_label: priorLabel.trim() || "Prior site (Stripe)",
        mrr_enabled: mrrEnabled,
        mrr_source: mrrSource,
        mrr_manual_amount: parseFloat(mrrAmount) || 0,
        mrr_manual_subscribers: parseInt(mrrSubscribers, 10) || 0,
        mrr_manual_churn_pct: parseFloat(mrrChurn) || 0,
        ...extra,
      };
      if (metaToken.trim()) payload.meta_access_token = metaToken.trim();
      const saved = await api.analytics.updateSettings(storeId, payload);
      setMetaToken("");
      if (saved.mrr_webhook_secret) setFreshWebhookSecret(saved.mrr_webhook_secret);
      setStripeAccounts(saved.stripe_accounts ?? []);
      setMessage("Settings saved.");
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save settings");
    } finally {
      setSaving(false);
    }
  };

  const testMeta = async () => {
    setTesting(true);
    setTestResult("");
    setError("");
    try {
      const res = await api.analytics.testMeta(storeId, {
        meta_access_token: metaToken.trim() || undefined,
        meta_ad_account_id: adAccountId.trim() || undefined,
      });
      setTestResult(res.message);
      if (!res.ok) setError(res.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connection test failed");
    } finally {
      setTesting(false);
    }
  };

  const clearMetaToken = async () => {
    setSaving(true);
    try {
      await api.analytics.updateSettings(storeId, { meta_access_token: "" });
      setMessage("Meta access token removed.");
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove token");
    } finally {
      setSaving(false);
    }
  };

  const addStripe = async () => {
    setError("");
    setMessage("");
    try {
      const res = await api.analytics.addStripeAccount(storeId, {
        label: stripeLabel.trim() || `Stripe ${(stripeAccounts.length || 0) + 1}`,
        secret_key: stripeKey.trim(),
      });
      setStripeAccounts(res.accounts as AnalyticsStripeAccount[]);
      setStripeKey("");
      setStripeLabel("");
      setMessage("Stripe account added.");
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add Stripe account");
    }
  };

  const removeStripe = async (id: string) => {
    try {
      const res = await api.analytics.deleteStripeAccount(storeId, id);
      setStripeAccounts(res.accounts as AnalyticsStripeAccount[]);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove account");
    }
  };

  const syncStripeMrr = async () => {
    setSyncing(true);
    setError("");
    try {
      const res = await api.analytics.syncMrrStripe(storeId);
      setMrrAmount(String(res.mrr));
      setMrrSubscribers(String(res.subscribers));
      setMrrSource("multi_stripe");
      setStripeAccounts(res.accounts as AnalyticsStripeAccount[]);
      setMessage(
        res.ok
          ? `Synced MRR ${res.mrr} across ${res.accounts.length} Stripe account(s).`
          : `Partial sync. Errors: ${res.errors.join("; ")}`
      );
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Stripe MRR sync failed");
    } finally {
      setSyncing(false);
    }
  };

  const webhookUrl =
    typeof window !== "undefined"
      ? `${window.location.origin}/api/v1/analytics/stores/${storeId}/mrr/webhook`
      : `/api/v1/analytics/stores/${storeId}/mrr/webhook`;

  return (
    <div className="space-y-6 max-w-2xl">
      {!settings?.shopify_connected && (
        <Card padding="lg" className="border-amber-500/30 bg-amber-500/5">
          <CardTitle className="text-amber-700 dark:text-amber-400">Shopify not connected</CardTitle>
          <CardDescription className="mt-1">
            Connect your store under Settings → Stores to pull orders and products automatically.
          </CardDescription>
        </Card>
      )}

      <Card padding="lg" className="border-brand-500/20 bg-brand-500/5">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Repeat className="h-5 w-5 text-brand-600" />
            <CardTitle>MRR / Subscriptions</CardTitle>
          </div>
          <CardDescription>
            Opt-in recurring revenue analytics. For Phoenix Technologies checkout with many Stripe
            MIDs, use Manual (or webhook) — Phoenix owns subscriptions; Stripe usually only
            processes charges.
          </CardDescription>
        </CardHeader>

        <div className="space-y-4">
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-border"
              checked={mrrEnabled}
              onChange={(e) => setMrrEnabled(e.target.checked)}
            />
            <span className="text-sm font-medium text-content">Enable MRR analytics</span>
          </label>

          {mrrEnabled && (
            <>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => setMrrSource("manual")}
                  className={`px-3 py-1.5 rounded-lg text-sm border ${
                    mrrSource === "manual"
                      ? "bg-brand-600 text-white border-brand-600"
                      : "border-border text-content-muted"
                  }`}
                >
                  Manual / Phoenix
                </button>
                <button
                  type="button"
                  onClick={() => setMrrSource("multi_stripe")}
                  className={`px-3 py-1.5 rounded-lg text-sm border ${
                    mrrSource === "multi_stripe"
                      ? "bg-brand-600 text-white border-brand-600"
                      : "border-border text-content-muted"
                  }`}
                >
                  Multi-Stripe sync
                </button>
              </div>

              {mrrSource === "manual" && (
                <div className="rounded-lg border border-border bg-surface p-4 space-y-3">
                  <p className="text-xs text-content-muted">
                    Copy MRR from your Phoenix dashboard (or CRM). Update weekly/monthly — each save
                    stores a snapshot for trends.
                  </p>
                  <div className="grid gap-3 sm:grid-cols-3">
                    <div>
                      <label className="block text-sm font-medium text-content mb-1.5">
                        Current MRR
                      </label>
                      <Input
                        type="number"
                        min="0"
                        step="0.01"
                        value={mrrAmount}
                        onChange={(e) => setMrrAmount(e.target.value)}
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-content mb-1.5">
                        Active subscribers
                      </label>
                      <Input
                        type="number"
                        min="0"
                        step="1"
                        value={mrrSubscribers}
                        onChange={(e) => setMrrSubscribers(e.target.value)}
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-content mb-1.5">
                        Churn % / mo
                      </label>
                      <Input
                        type="number"
                        min="0"
                        step="0.1"
                        value={mrrChurn}
                        onChange={(e) => setMrrChurn(e.target.value)}
                      />
                    </div>
                  </div>
                </div>
              )}

              {mrrSource === "multi_stripe" && (
                <div className="rounded-lg border border-border bg-surface p-4 space-y-3">
                  <p className="text-xs text-content-muted">
                    Only works if subscriptions live in <strong>Stripe Billing</strong> on each MID.
                    With Phoenix orchestration, rebills often appear as charges — not Stripe
                    subscriptions — so totals may be $0. Prefer Manual / webhook in that case.
                  </p>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Input
                      placeholder="Label (e.g. MID 1)"
                      value={stripeLabel}
                      onChange={(e) => setStripeLabel(e.target.value)}
                    />
                    <Input
                      type="password"
                      placeholder="sk_live_… or restricted key"
                      value={stripeKey}
                      onChange={(e) => setStripeKey(e.target.value)}
                    />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button type="button" variant="outline" onClick={addStripe} disabled={!stripeKey.trim()}>
                      Add Stripe account
                    </Button>
                    <Button type="button" onClick={syncStripeMrr} disabled={syncing || !stripeAccounts.length}>
                      <RefreshCw className={`h-4 w-4 mr-1.5 ${syncing ? "animate-spin" : ""}`} />
                      {syncing ? "Syncing…" : "Sync MRR from all Stripes"}
                    </Button>
                  </div>
                  {stripeAccounts.length > 0 && (
                    <ul className="space-y-2 text-sm">
                      {stripeAccounts.map((a) => (
                        <li
                          key={a.id}
                          className="flex items-center justify-between gap-2 border border-border rounded-lg px-3 py-2"
                        >
                          <div>
                            <p className="font-medium text-content">{a.label}</p>
                            <p className="text-xs text-content-muted">
                              {a.secret_key_masked} · last MRR {a.last_mrr} · {a.last_subscribers} subs
                              {a.last_error ? ` · ${a.last_error}` : ""}
                            </p>
                          </div>
                          <Button type="button" variant="ghost" size="sm" onClick={() => removeStripe(a.id)}>
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              <div className="rounded-lg border border-dashed border-border p-4 space-y-2 text-sm">
                <p className="font-medium text-content">Webhook (Phoenix / Zapier)</p>
                <p className="text-xs text-content-muted">
                  Push MRR automatically:{" "}
                  <code className="text-[11px] break-all">{webhookUrl}</code>
                </p>
                <p className="text-xs text-content-muted">
                  Header <code className="text-[11px]">X-MRR-Webhook-Secret</code> + JSON{" "}
                  <code className="text-[11px]">{"{ mrr, subscribers, churn_pct }"}</code>
                </p>
                {freshWebhookSecret && (
                  <p className="text-xs text-amber-700 dark:text-amber-400 break-all">
                    New secret (copy now): {freshWebhookSecret}
                  </p>
                )}
                {settings?.mrr_webhook_secret_masked && !freshWebhookSecret && (
                  <p className="text-xs text-content-muted">
                    Secret configured: {settings.mrr_webhook_secret_masked}
                  </p>
                )}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => save({ regenerate_mrr_webhook_secret: true, mrr_enabled: true })}
                  disabled={saving}
                >
                  Generate / rotate webhook secret
                </Button>
              </div>
            </>
          )}
        </div>
      </Card>

      <Card padding="lg" className="border-brand-500/20 bg-brand-500/5">
        <CardHeader>
          <div className="flex items-center gap-2">
            <CalendarRange className="h-5 w-5 text-brand-600" />
            <CardTitle>Migrated from another site?</CardTitle>
          </div>
          <CardDescription>
            If you sold on a custom site with Stripe before Shopify, Meta ad spend from that era
            can make profit look deeply negative. Fix it here.
          </CardDescription>
        </CardHeader>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-content mb-1.5">
              Shopify launch / analytics start date
            </label>
            <Input
              type="date"
              value={analyticsStartDate}
              onChange={(e) => setAnalyticsStartDate(e.target.value)}
            />
            <p className="text-xs text-content-subtle mt-1">
              Recommended: the day you switched to Shopify. Meta spend before this date is ignored.
            </p>
          </div>

          <div className="rounded-lg border border-border bg-surface p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Wallet className="h-4 w-4 text-brand-600" />
              <p className="text-sm font-medium text-content">Prior site revenue (optional)</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-content mb-1.5">Label</label>
              <Input
                value={priorLabel}
                onChange={(e) => setPriorLabel(e.target.value)}
                placeholder="Prior site (Stripe)"
              />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="block text-sm font-medium text-content mb-1.5">
                  Prior revenue
                </label>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={priorRevenue}
                  onChange={(e) => setPriorRevenue(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-content mb-1.5">
                  Prior costs (optional)
                </label>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={priorCosts}
                  onChange={(e) => setPriorCosts(e.target.value)}
                />
              </div>
            </div>
          </div>
        </div>
      </Card>

      <Card padding="lg">
        <CardHeader>
          <div className="flex items-center gap-2">
            <PlugZap className="h-5 w-5 text-brand-600" />
            <CardTitle>Meta (Facebook) Ads</CardTitle>
          </div>
          <CardDescription>
            Connect your Meta Marketing API to track ad spend, ROAS, and campaign performance.
          </CardDescription>
        </CardHeader>

        <div className="space-y-4">
          <div className="flex flex-wrap gap-2 items-center">
            <Badge variant={settings?.meta_configured ? "success" : "muted"}>
              {settings?.meta_configured ? "Connected" : "Not connected"}
            </Badge>
            {settings?.meta_token_masked && (
              <span className="text-xs text-content-muted">Token: {settings.meta_token_masked}</span>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-content mb-1.5">Access token</label>
            <Input
              type="password"
              placeholder={settings?.meta_token_masked ? "Enter new token to replace" : "EAAxxxx…"}
              value={metaToken}
              onChange={(e) => setMetaToken(e.target.value)}
            />
            <p className="text-xs text-content-subtle mt-1">
              Create a long-lived token in{" "}
              <a
                href="https://developers.facebook.com/tools/explorer/"
                target="_blank"
                rel="noreferrer"
                className="text-brand-600 hover:underline inline-flex items-center gap-0.5"
              >
                Graph API Explorer <ExternalLink className="h-3 w-3" />
              </a>{" "}
              with <code className="text-xs">ads_read</code>.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-content mb-1.5">Ad account ID</label>
            <Input
              placeholder="1234567890 (without act_ prefix)"
              value={adAccountId}
              onChange={(e) => setAdAccountId(e.target.value)}
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={testMeta} disabled={testing}>
              <TestTube2 className="h-4 w-4 mr-1.5" />
              {testing ? "Testing…" : "Test connection"}
            </Button>
            {settings?.meta_token_masked && (
              <Button type="button" variant="ghost" onClick={clearMetaToken} disabled={saving}>
                Remove token
              </Button>
            )}
          </div>
          {testResult && !error && (
            <p className="text-sm text-emerald-600 dark:text-emerald-400">{testResult}</p>
          )}
        </div>
      </Card>

      <Card padding="lg">
        <CardHeader>
          <div className="flex items-center gap-2">
            <KeyRound className="h-5 w-5 text-brand-600" />
            <CardTitle>Cost assumptions</CardTitle>
          </div>
          <CardDescription>
            Default values used when calculating profit per order.
          </CardDescription>
        </CardHeader>

        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <label className="block text-sm font-medium text-content mb-1.5">
              Avg. shipping / order
            </label>
            <Input
              type="number"
              min="0"
              step="0.01"
              value={shippingCost}
              onChange={(e) => setShippingCost(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-content mb-1.5">Payment fee (%)</label>
            <Input
              type="number"
              min="0"
              step="0.1"
              value={feePercent}
              onChange={(e) => setFeePercent(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-content mb-1.5">Fixed fee / order</label>
            <Input
              type="number"
              min="0"
              step="0.01"
              value={feeFixed}
              onChange={(e) => setFeeFixed(e.target.value)}
            />
          </div>
        </div>
      </Card>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {message && <p className="text-sm text-emerald-600 dark:text-emerald-400">{message}</p>}

      <Button onClick={() => save()} disabled={saving}>
        <Save className="h-4 w-4 mr-1.5" />
        {saving ? "Saving…" : "Save settings"}
      </Button>
    </div>
  );
}
