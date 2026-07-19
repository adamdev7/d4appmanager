import { useEffect, useState } from "react";
import { ChevronDown, ChevronUp, KeyRound, PlugZap } from "lucide-react";
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
  {
    value: "auto",
    label: "Automatic (recommended)",
    hint: "Uses YunExpress when the carrier name matches, otherwise 17TRACK.",
  },
  {
    value: "17track",
    label: "17TRACK only",
    hint: "Always check 17TRACK when a key is saved.",
  },
  {
    value: "yunexpress",
    label: "YunExpress only",
    hint: "Always check YunExpress when a key is saved.",
  },
  {
    value: "shopify_only",
    label: "Shopify status only",
    hint: "Only show status from Shopify — no extra carrier lookups.",
  },
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
  const [advancedOpen, setAdvancedOpen] = useState(false);

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
      setMessage("Saved. Live shipment updates will use these settings.");
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
      setMessage("Connection removed.");
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
          Live shipment updates
        </CardTitle>
        <CardDescription>
          Optional. When a tracking number appears on a Shopify order, we can fetch live status from
          your shipping provider so customers see clearer updates.
        </CardDescription>
      </CardHeader>

      <div className="px-6 pb-6 space-y-6">
        <Switch
          checked={autoEnrich}
          onChange={setAutoEnrich}
          label="Update status automatically"
          description="When tracking is added in Shopify, pull the latest shipment status for the customer."
        />

        <div className="space-y-2">
          <label className="block text-sm font-medium text-content">Which provider to use</label>
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
            <div>
              <p className="font-medium text-content text-sm">17TRACK</p>
              <p className="text-xs text-content-muted mt-0.5">Works with most international carriers</p>
            </div>
            {settings?.track17_configured ? (
              <Badge variant="success">Connected {settings.track17_key_masked}</Badge>
            ) : (
              <Badge variant="muted">Not connected</Badge>
            )}
          </div>
          <Input
            label="API key"
            type="password"
            placeholder={settings?.track17_configured ? "Enter a new key to replace" : "Paste your 17TRACK key"}
            value={track17Key}
            onChange={(e) => setTrack17Key(e.target.value)}
            hint="From 17track.net → API. Leave blank to keep your current key."
          />
          {settings?.uses_server_track17_fallback && (
            <p className="text-xs text-amber-600 dark:text-amber-400">
              A shared server key is in use until you save your own.
            </p>
          )}
          {settings?.track17_configured && (
            <Button type="button" variant="outline" size="sm" onClick={() => clearKey("track17_api_key")}>
              Disconnect 17TRACK
            </Button>
          )}
        </div>

        <div className="rounded-xl border border-border p-4 space-y-4">
          <div className="flex items-center justify-between gap-2">
            <div>
              <p className="font-medium text-content text-sm">YunExpress</p>
              <p className="text-xs text-content-muted mt-0.5">Best when you ship with YunExpress</p>
            </div>
            {settings?.yunexpress_configured ? (
              <Badge variant="success">Connected {settings.yunexpress_key_masked}</Badge>
            ) : (
              <Badge variant="muted">Not connected</Badge>
            )}
          </div>
          <Input
            label="API key"
            type="password"
            placeholder={settings?.yunexpress_configured ? "Enter a new key to replace" : "Paste your YunExpress key"}
            value={yunKey}
            onChange={(e) => setYunKey(e.target.value)}
          />
          {settings?.uses_server_yunexpress_fallback && (
            <p className="text-xs text-amber-600 dark:text-amber-400">
              A shared server key is in use until you save your own.
            </p>
          )}
          {settings?.yunexpress_configured && (
            <Button type="button" variant="outline" size="sm" onClick={() => clearKey("yunexpress_api_key")}>
              Disconnect YunExpress
            </Button>
          )}

          <button
            type="button"
            className="flex w-full items-center justify-between text-sm text-content-muted hover:text-content"
            onClick={() => setAdvancedOpen((v) => !v)}
          >
            <span>Advanced YunExpress options</span>
            {advancedOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
          {advancedOpen && (
            <div className="space-y-4 pt-1">
              <Input
                label="API website"
                value={yunUrl}
                onChange={(e) => setYunUrl(e.target.value)}
                hint="Usually leave as the default unless YunExpress gave you a different link."
              />
              <Input
                label="Customer code (optional)"
                value={yunCode}
                onChange={(e) => setYunCode(e.target.value)}
                hint="Only needed if your YunExpress account requires it."
              />
              <Input
                label="Auto-detect words"
                value={yunKeywords}
                onChange={(e) => setYunKeywords(e.target.value)}
                hint="In Automatic mode, use YunExpress when the carrier name contains these words."
              />
            </div>
          )}
        </div>

        <div className="rounded-xl border border-dashed border-border p-4 space-y-3">
          <p className="text-sm font-medium text-content flex items-center gap-2">
            <PlugZap className="h-4 w-4" />
            Test connection
          </p>
          <Input
            label="Sample tracking number (optional)"
            placeholder="Paste a real tracking number to verify"
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
          Save settings
        </Button>
      </div>
    </Card>
  );
}
