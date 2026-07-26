import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ExternalLink, KeyRound, PlugZap, Save, Sparkles, TestTube2 } from "lucide-react";
import { api, type AdsSettings } from "@/lib/api";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Switch } from "@/components/ui/Switch";
import { Badge } from "@/components/ui/Badge";

type Props = {
  storeId: string;
  settings: AdsSettings | null;
  onSaved: () => void;
};

export function AdsSettingsPanel({ storeId, settings, onSaved }: Props) {
  const [metaToken, setMetaToken] = useState("");
  const [adAccountId, setAdAccountId] = useState("");
  const [consent, setConsent] = useState(false);
  const [daily, setDaily] = useState(false);
  const [weekly, setWeekly] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [testResult, setTestResult] = useState("");

  useEffect(() => {
    if (!settings) return;
    setAdAccountId(settings.meta_ad_account_id ?? "");
    setConsent(Boolean(settings.ai_reports_consent));
    setDaily(Boolean(settings.daily_ai_reports));
    setWeekly(Boolean(settings.weekly_ai_reports));
    setMetaToken("");
  }, [settings]);

  const save = async () => {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const payload: Record<string, unknown> = {
        meta_ad_account_id: adAccountId.trim() || null,
        ai_reports_consent: consent,
        daily_ai_reports: consent ? daily : false,
        weekly_ai_reports: consent ? weekly : false,
      };
      if (metaToken.trim()) payload.meta_access_token = metaToken.trim();
      await api.ads.updateSettings(storeId, payload);
      setMetaToken("");
      setMessage("Ads settings saved.");
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const testMeta = async () => {
    setTesting(true);
    setTestResult("");
    setError("");
    try {
      const res = await api.ads.testMeta(storeId, {
        meta_access_token: metaToken.trim() || undefined,
        meta_ad_account_id: adAccountId.trim() || undefined,
      });
      setTestResult(res.ok ? res.message : res.message);
      if (!res.ok) setError(res.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Meta test failed");
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <Card padding="lg">
        <CardHeader>
          <div className="flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-brand-600" />
            <CardTitle>Meta Ads connection</CardTitle>
          </div>
          <CardDescription>
            Same credentials as Analytics — Marketing API user token + ad account ID. Shared across
            both apps.
          </CardDescription>
        </CardHeader>
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Badge variant={settings?.meta_configured ? "success" : "warning"}>
              {settings?.meta_configured ? "Connected" : "Not connected"}
            </Badge>
            {settings?.meta_token_masked && (
              <span className="text-xs text-content-muted">Token {settings.meta_token_masked}</span>
            )}
          </div>
          <Input
            label="Access token"
            type="password"
            placeholder={settings?.meta_token_masked ? "Leave blank to keep current" : "EAAG…"}
            value={metaToken}
            onChange={(e) => setMetaToken(e.target.value)}
          />
          <Input
            label="Ad account ID"
            placeholder="1234567890 (without act_)"
            value={adAccountId}
            onChange={(e) => setAdAccountId(e.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="secondary" onClick={testMeta} disabled={testing}>
              <TestTube2 className="h-4 w-4" />
              {testing ? "Testing…" : "Test connection"}
            </Button>
            <a
              href="https://developers.facebook.com/tools/explorer/"
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-border px-3 text-sm text-content-muted hover:text-content"
            >
              Graph API Explorer <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </div>
          {testResult && <p className="text-sm text-emerald-600 dark:text-emerald-400">{testResult}</p>}
        </div>
      </Card>

      <Card padding="lg">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-brand-600" />
            <CardTitle>AI ads reports</CardTitle>
          </div>
          <CardDescription>
            Optionally reuse the OpenAI API key from AI Email Assistant for daily and weekly
            campaign analysis. Nothing runs until you opt in.
          </CardDescription>
        </CardHeader>
        <div className="space-y-4">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant={settings?.openai_configured ? "success" : "warning"}>
              {settings?.openai_configured ? "OpenAI key ready" : "OpenAI key missing"}
            </Badge>
            {settings?.openai_key_masked && (
              <span className="text-xs text-content-muted">{settings.openai_key_masked}</span>
            )}
            {!settings?.openai_configured && (
              <Link
                to="/modules/ai-email"
                className="text-xs font-medium text-brand-600 hover:underline"
              >
                Add key in AI Email Assistant
              </Link>
            )}
          </div>

          <Switch
            checked={consent}
            onChange={(v) => {
              setConsent(v);
              if (!v) {
                setDaily(false);
                setWeekly(false);
              }
            }}
            label="I consent to using my OpenAI API key for Ads analysis"
            description="We only call OpenAI with your ads metrics snapshot when you enable reports or click Generate."
          />

          <Switch
            checked={daily}
            onChange={setDaily}
            disabled={!consent}
            label="Daily AI report"
            description="When you open Ads (~once per day), generate a short 7-day campaign health report."
          />

          <Switch
            checked={weekly}
            onChange={setWeekly}
            disabled={!consent}
            label="Weekly AI report"
            description="Deeper 30-day review about once per week when you open Ads."
          />
        </div>
      </Card>

      <div className="flex items-center gap-3">
        <Button onClick={save} disabled={saving}>
          <Save className="h-4 w-4" />
          {saving ? "Saving…" : "Save settings"}
        </Button>
        {message && <p className="text-sm text-emerald-600 dark:text-emerald-400">{message}</p>}
        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      </div>

      <Card padding="md" className="border-dashed">
        <div className="flex gap-3">
          <PlugZap className="h-5 w-5 text-content-muted shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-content">Token tip</p>
            <p className="text-xs text-content-muted mt-1 leading-relaxed">
              Use a System User or long-lived user token with <code>ads_read</code> (and ideally{" "}
              <code>ads_management</code>) on the Business ad account. Paste the numeric ad account
              ID from Ads Manager → Account settings.
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
}
