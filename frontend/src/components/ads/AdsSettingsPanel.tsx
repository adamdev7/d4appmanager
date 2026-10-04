import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Save, Sparkles } from "lucide-react";
import { api, type AdsSettings } from "@/lib/api";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Switch } from "@/components/ui/Switch";
import { Badge } from "@/components/ui/Badge";
import { ModelSelect } from "@/components/settings/ModelSelect";

type Props = {
  storeId: string;
  settings: AdsSettings | null;
  onSaved: () => void;
};

export function AdsSettingsPanel({ storeId, settings, onSaved }: Props) {
  const [consent, setConsent] = useState(false);
  const [daily, setDaily] = useState(false);
  const [weekly, setWeekly] = useState(false);
  const [model, setModel] = useState("gpt-6.1-sol");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!settings) return;
    setConsent(Boolean(settings.ai_reports_consent));
    setDaily(Boolean(settings.daily_ai_reports));
    setWeekly(Boolean(settings.weekly_ai_reports));
    setModel(settings.openai_model || settings.default_model || "gpt-6.1-sol");
  }, [settings]);

  const save = async () => {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await api.ads.updateSettings(storeId, {
        ai_reports_consent: consent,
        daily_ai_reports: consent ? daily : false,
        weekly_ai_reports: consent ? weekly : false,
        openai_model: model,
      });
      setMessage("Ads settings saved.");
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <Card padding="lg">
        <CardHeader>
          <CardTitle>Meta</CardTitle>
          <CardDescription>
            The ad account lives in account settings, shared with Analytics and AI Ads.
          </CardDescription>
        </CardHeader>
        <div className="flex flex-wrap items-center gap-3">
          <Badge variant={settings?.meta_configured ? "success" : "warning"}>
            {settings?.meta_configured ? "Connected" : "Not connected"}
          </Badge>
          <Link to="/settings/meta" className="text-sm font-medium text-brand-600 hover:underline">
            Open Meta settings
          </Link>
        </div>
      </Card>

      <Card padding="lg">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-brand-600" />
            <CardTitle>AI ads reports</CardTitle>
          </div>
          <CardDescription>
            Reports use the Ads OpenAI key from account settings and the model you pick here.
          </CardDescription>
        </CardHeader>
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <Badge variant={settings?.openai_configured ? "success" : "warning"}>
              {settings?.openai_configured ? "API key ready" : "API key needed"}
            </Badge>
            <Link to="/settings/api-keys" className="text-sm font-medium text-brand-600 hover:underline">
              Manage API keys
            </Link>
          </div>
          <ModelSelect value={model} onChange={setModel} />

          <Switch
            checked={consent}
            onChange={(v) => {
              setConsent(v);
              if (!v) {
                setDaily(false);
                setWeekly(false);
              }
            }}
            label="I consent to using this OpenAI API key for Ads analysis"
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

    </div>
  );
}
