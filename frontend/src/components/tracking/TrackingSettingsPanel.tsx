import { useEffect, useState } from "react";
import { KeyRound, PlugZap } from "lucide-react";
import { api, type TrackingSettings } from "@/lib/api";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Switch } from "@/components/ui/Switch";
import { Badge } from "@/components/ui/Badge";

type Props = {
  storeId: string;
  settings: TrackingSettings | null;
  onSaved: () => void;
};

const CARRIER_MODES = [
  { value: "auto", label: "Auto (recommended)", hint: "YunExpress when carrier/name matches keywords, else 17TRACK" },
  { value: "17track", label: "17TRACK only", hint: "Always use 17TRACK when a key is set" },
  { value: "yunexpress", label: "YunExpress only", hint: "Always use YunExpress when a key is set" },
  { value: "shopify_only", label: "Shopify only", hint: "No carrier APIs — status from Shopify webhooks only" },
];

export function TrackingSettingsPanel({ storeId, settings, onSaved }: Props) {
  const [carrierMode, setCarrierMode] = useState("auto");
  const [autoEnrich, setAutoEnrich] = useState(true);
  const [yunUrl, setYunUrl] = useState("https://api.yunexpress.com");
  const [yunCode, setYunCode] = useState("");
  const [yunKeywords, setYunKeywords] = useState("yun,yunexpress");
  const [track17Key, setTrack17Key] = useState("");
  const [yunKey, setYunKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [testTrack, setTestTrack] = useState("");
  const [testing, setTesting] = useState<string | null>(null);

  useEffect(() => {
    if (!settings) return;
    setCarrierMode(settings.carrier_mode);
    setAutoEnrich(settings.auto_enrich_enabled);
    setYunUrl(settings.yunexpress_api_url);
    setYunCode(settings.yunexpress_customer_code ?? "");
    setYunKeywords(settings.yunexpress_carrier_keywords);
    setTrack17Key("");
    setYunKey("");
  }, [settings]);

  const save = async () => {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const payload: Record<string, unknown> = {
        carrier_mode: carrierMode,
        auto_enrich_enabled: autoEnrich,
        yunexpress_api_url: yunUrl,
        yunexpress_customer_code: yunCode || null,
        yunexpress_carrier_keywords: yunKeywords,
      };
      if (track17Key.trim()) payload.track17_api_key = track17Key.trim();
      if (yunKey.trim()) payload.yunexpress_api_key = yunKey.trim();
      await api.tracking.updateSettings(storeId, payload);
      setTrack17Key("");
      setYunKey("");
      setMessage("Settings saved.");
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save settings");
    } finally {
      setSaving(false);
    }
  };

  const clearKey = async (field: "track17_api_key" | "yunexpress_api_key") => {
    setSaving(true);
    setError("");
    try {
      await api.tracking.updateSettings(storeId, { [field]: "" });
      setMessage("API key removed.");
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove key");
    } finally {
      setSaving(false);
    }
  };

  const testCarrier = async (provider: "17track" | "yunexpress") => {
    setTesting(provider);
    setError("");
    setMessage("");
    try {
      const res = await api.tracking.testCarrier(storeId, {
        provider,
        tracking_number: testTrack.trim() || undefined,
      });
      if (res.ok) {
        setMessage(res.message + (res.status ? ` (status: ${res.status})` : ""));
      } else {
        setError(res.message);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test failed");
    } finally {
      setTesting(null);
    }
  };

  return (
    <Card padding="lg">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <KeyRound className="h-5 w-5 text-content-muted" />
          Carrier API settings
        </CardTitle>
        <CardDescription>
          Add your own 17TRACK and YunExpress keys per store. Keys are encrypted in the database.
          When a supplier adds tracking in Shopify, we can fetch live updates automatically.
        </CardDescription>
      </CardHeader>

      <div className="px-6 pb-6 space-y-6">
        <Switch
          checked={autoEnrich}
          onChange={setAutoEnrich}
          label="Auto-enrich when tracking is added"
          description="Call carrier APIs right after Shopify fulfillment webhooks (recommended)."
        />

        <div className="space-y-2">
          <label className="block text-sm font-medium text-content">Carrier priority</label>
          <select
            value={carrierMode}
            onChange={(e) => setCarrierMode(e.target.value)}
            className="flex h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-content"
          >
            {CARRIER_MODES.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
          <p className="text-xs text-content-muted">
            {CARRIER_MODES.find((m) => m.value === carrierMode)?.hint}
          </p>
        </div>

        <div className="rounded-xl border border-border p-4 space-y-4">
          <div className="flex items-center justify-between gap-2">
            <p className="font-medium text-content text-sm">17TRACK</p>
            {settings?.track17_configured ? (
              <Badge variant="success">Connected {settings.track17_key_masked}</Badge>
            ) : (
              <Badge variant="muted">Not configured</Badge>
            )}
          </div>
          <Input
            label="API key (17token)"
            type="password"
            placeholder={settings?.track17_configured ? "Enter new key to replace" : "Paste API key"}
            value={track17Key}
            onChange={(e) => setTrack17Key(e.target.value)}
            hint="Get your key from 17track.net → API. Leave blank to keep existing key."
          />
          {settings?.uses_server_track17_fallback && (
            <p className="text-xs text-amber-600 dark:text-amber-400">
              Server fallback key from .env is active until you save a store key.
            </p>
          )}
          {settings?.track17_configured && (
            <Button type="button" variant="outline" size="sm" onClick={() => clearKey("track17_api_key")}>
              Remove 17TRACK key
            </Button>
          )}
        </div>

        <div className="rounded-xl border border-border p-4 space-y-4">
          <div className="flex items-center justify-between gap-2">
            <p className="font-medium text-content text-sm">YunExpress</p>
            {settings?.yunexpress_configured ? (
              <Badge variant="success">Connected {settings.yunexpress_key_masked}</Badge>
            ) : (
              <Badge variant="muted">Not configured</Badge>
            )}
          </div>
          <Input
            label="API key"
            type="password"
            placeholder={settings?.yunexpress_configured ? "Enter new key to replace" : "Paste API key"}
            value={yunKey}
            onChange={(e) => setYunKey(e.target.value)}
          />
          <Input
            label="API base URL"
            value={yunUrl}
            onChange={(e) => setYunUrl(e.target.value)}
            hint="Default: https://api.yunexpress.com — change if your account uses a regional endpoint."
          />
          <Input
            label="Customer code (optional)"
            value={yunCode}
            onChange={(e) => setYunCode(e.target.value)}
            hint="Some YunExpress accounts require a customer / merchant code."
          />
          <Input
            label="Auto-detect keywords"
            value={yunKeywords}
            onChange={(e) => setYunKeywords(e.target.value)}
            hint="Comma-separated. In Auto mode, YunExpress is used when carrier or tracking contains these."
          />
          {settings?.uses_server_yunexpress_fallback && (
            <p className="text-xs text-amber-600 dark:text-amber-400">
              Server fallback key from .env is active until you save a store key.
            </p>
          )}
          {settings?.yunexpress_configured && (
            <Button type="button" variant="outline" size="sm" onClick={() => clearKey("yunexpress_api_key")}>
              Remove YunExpress key
            </Button>
          )}
        </div>

        <div className="rounded-xl border border-dashed border-border p-4 space-y-3">
          <p className="text-sm font-medium text-content flex items-center gap-2">
            <PlugZap className="h-4 w-4" />
            Test API connection
          </p>
          <Input
            label="Sample tracking number (optional)"
            placeholder="Use a real YunExpress / 17TRACK number for best results"
            value={testTrack}
            onChange={(e) => setTestTrack(e.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              isLoading={testing === "17track"}
              onClick={() => testCarrier("17track")}
            >
              Test 17TRACK
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              isLoading={testing === "yunexpress"}
              onClick={() => testCarrier("yunexpress")}
            >
              Test YunExpress
            </Button>
          </div>
        </div>

        {message && (
          <p className="text-sm text-green-700 dark:text-green-400 bg-green-500/10 rounded-lg px-3 py-2">
            {message}
          </p>
        )}
        {error && (
          <p className="text-sm text-red-600 dark:text-red-400 bg-red-500/10 rounded-lg px-3 py-2">
            {error}
          </p>
        )}

        <Button onClick={save} isLoading={saving}>
          Save tracking settings
        </Button>
      </div>
    </Card>
  );
}
