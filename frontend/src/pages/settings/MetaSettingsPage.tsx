import { useEffect, useState } from "react";
import { ExternalLink, PlugZap } from "lucide-react";
import { useStore } from "@/context/StoreContext";
import { api, type MetaConnection } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { PageLoader } from "@/components/ui/Loading";

export function MetaSettingsPage() {
  const { activeStore, stores } = useStore();
  const storeId = activeStore?.id ?? stores[0]?.id ?? null;
  const [connection, setConnection] = useState<MetaConnection | null>(null);
  const [token, setToken] = useState("");
  const [adAccountId, setAdAccountId] = useState("");
  const [pixelId, setPixelId] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!storeId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    api.connections
      .getMeta(storeId)
      .then((data) => {
        setConnection(data);
        setAdAccountId(data.meta_ad_account_id ?? "");
        setPixelId(data.meta_pixel_id ?? "");
        setToken("");
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load Meta"))
      .finally(() => setLoading(false));
  }, [storeId]);

  const save = async () => {
    if (!storeId) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const payload: Record<string, unknown> = {
        meta_ad_account_id: adAccountId.trim() || null,
        meta_pixel_id: pixelId.trim() || null,
      };
      if (token.trim()) payload.meta_access_token = token.trim();
      const saved = await api.connections.saveMeta(storeId, payload);
      setConnection(saved);
      setToken("");
      setMessage("Meta connection saved. Analytics, Ads, AI Ads, and Server-Side Tracking use it.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save Meta");
    } finally {
      setSaving(false);
    }
  };

  const clearToken = async () => {
    if (!storeId) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const saved = await api.connections.saveMeta(storeId, { clear_access_token: true });
      setConnection(saved);
      setToken("");
      setMessage("Meta token removed.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove token");
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    if (!storeId) return;
    setTesting(true);
    setError("");
    setMessage("");
    try {
      const res = await api.connections.testMeta(storeId, {
        meta_access_token: token.trim() || undefined,
        meta_ad_account_id: adAccountId.trim() || undefined,
      });
      if (res.ok) setMessage(res.message);
      else setError(res.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Meta test failed");
    } finally {
      setTesting(false);
    }
  };

  if (!storeId) {
    return <p className="text-sm text-content-muted">Connect a store before adding Meta.</p>;
  }
  if (loading) return <PageLoader label="Loading Meta" />;

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-content tracking-tight">Meta</h1>
        <p className="text-sm text-content-muted mt-1 leading-relaxed">
          One connection for this store. Analytics, Ads, and AI Ads read it. Server-Side Tracking
          uses the same token unless that option has its own override.
        </p>
      </div>

      <Card padding="lg">
        <CardHeader>
          <div className="flex items-center gap-2">
            <PlugZap className="h-5 w-5 text-brand-600" />
            <CardTitle>Marketing API and Pixel</CardTitle>
          </div>
          <CardDescription>
            Ad account for spend and creatives. Pixel ID for server-side purchases.
          </CardDescription>
        </CardHeader>
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <Badge variant={connection?.meta_configured ? "success" : "warning"}>
              {connection?.meta_configured ? "Ads connected" : "Ads not connected"}
            </Badge>
            <Badge variant={connection?.pixel_configured ? "success" : "muted"}>
              {connection?.pixel_configured ? "Pixel saved" : "No Pixel yet"}
            </Badge>
            {connection?.meta_token_masked && (
              <span className="text-xs text-content-muted self-center">
                Token {connection.meta_token_masked}
              </span>
            )}
          </div>
          <Input
            label="Access token"
            type="password"
            placeholder={connection?.meta_token_masked ? "Leave blank to keep the saved token" : "EAAxxxx…"}
            value={token}
            onChange={(e) => setToken(e.target.value)}
            hint="Long-lived token from Graph API Explorer with ads_read. ads_management is needed later to publish."
          />
          <Input
            label="Ad account ID"
            placeholder="1234567890 (without act_)"
            value={adAccountId}
            onChange={(e) => setAdAccountId(e.target.value)}
          />
          <Input
            label="Pixel ID"
            placeholder="1234567890"
            value={pixelId}
            onChange={(e) => setPixelId(e.target.value)}
            hint="Events Manager → your Pixel. Server-Side Tracking sends purchases to this Pixel."
          />
          <div className="flex flex-wrap gap-2">
            <Button type="button" onClick={() => void save()} disabled={saving}>
              {saving ? "Saving…" : "Save Meta"}
            </Button>
            <Button type="button" variant="secondary" onClick={() => void test()} disabled={testing}>
              {testing ? "Testing…" : "Test ads connection"}
            </Button>
            {connection?.meta_token_masked && (
              <Button type="button" variant="outline" onClick={() => void clearToken()} disabled={saving}>
                Remove token
              </Button>
            )}
            <a
              href="https://developers.facebook.com/tools/explorer/"
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-border px-3 text-sm text-content-muted hover:text-content"
            >
              Graph API Explorer <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </div>
          {message && <p className="text-sm text-emerald-600 dark:text-emerald-400">{message}</p>}
          {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        </div>
      </Card>
    </div>
  );
}
