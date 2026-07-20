import { useEffect, useState } from "react";
import { ExternalLink, KeyRound, PlugZap, Save, TestTube2 } from "lucide-react";
import { api, type AnalyticsSettings } from "@/lib/api";
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
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [testResult, setTestResult] = useState("");

  useEffect(() => {
    if (!settings) return;
    setAdAccountId(settings.meta_ad_account_id ?? "");
    setShippingCost(String(settings.default_shipping_cost));
    setFeePercent(String(settings.transaction_fee_percent));
    setFeeFixed(String(settings.transaction_fee_fixed));
    setMetaToken("");
  }, [settings]);

  const save = async () => {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const payload: Record<string, unknown> = {
        meta_ad_account_id: adAccountId.trim() || null,
        default_shipping_cost: parseFloat(shippingCost) || 0,
        transaction_fee_percent: parseFloat(feePercent) || 0,
        transaction_fee_fixed: parseFloat(feeFixed) || 0,
      };
      if (metaToken.trim()) payload.meta_access_token = metaToken.trim();
      await api.analytics.updateSettings(storeId, payload);
      setMetaToken("");
      setMessage("Settings saved. Your dashboard will use these values.");
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
            <label className="block text-sm font-medium text-content mb-1.5">
              Access token
            </label>
            <Input
              type="password"
              placeholder={settings?.meta_token_masked ? "Enter new token to replace" : "EAAxxxx… long-lived token"}
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
              with <code className="text-xs">ads_read</code> permission.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-content mb-1.5">
              Ad account ID
            </label>
            <Input
              placeholder="1234567890 (without act_ prefix)"
              value={adAccountId}
              onChange={(e) => setAdAccountId(e.target.value)}
            />
            <p className="text-xs text-content-subtle mt-1">
              Find this in Meta Ads Manager → Account settings. Use the numeric ID only.
            </p>
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
            Default values used when calculating profit per order. Adjust to match your business.
          </CardDescription>
        </CardHeader>

        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <label className="block text-sm font-medium text-content mb-1.5">
              Avg. shipping cost / order
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
            <label className="block text-sm font-medium text-content mb-1.5">
              Payment fee (%)
            </label>
            <Input
              type="number"
              min="0"
              step="0.1"
              value={feePercent}
              onChange={(e) => setFeePercent(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-content mb-1.5">
              Fixed fee / order
            </label>
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

      <Button onClick={save} disabled={saving}>
        <Save className="h-4 w-4 mr-1.5" />
        {saving ? "Saving…" : "Save settings"}
      </Button>
    </div>
  );
}
