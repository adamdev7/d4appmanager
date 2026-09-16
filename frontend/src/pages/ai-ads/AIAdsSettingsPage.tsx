import { useEffect, useState, type ReactNode } from "react";
import { AlertTriangle, CalendarClock, Plug, UserSquare2 } from "lucide-react";
import { useStore } from "@/context/StoreContext";
import { api, type AIAdsSettings } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Switch } from "@/components/ui/Switch";
import { PageLoader } from "@/components/ui/Loading";
import { OpenAIModuleKeyCard } from "@/components/settings/OpenAIModuleKeyCard";
import { WhatsAppAlertsCard } from "@/components/settings/WhatsAppAlertsCard";
import { cn } from "@/lib/cn";

const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];

export function AIAdsSettingsPage() {
  const { activeStore, stores } = useStore();
  const storeId = activeStore?.id ?? stores[0]?.id ?? null;
  const [settings, setSettings] = useState<AIAdsSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState("");
  const [error, setError] = useState("");
  const [avatarName, setAvatarName] = useState("");
  const [avatarDesc, setAvatarDesc] = useState("");
  const [whatsappKeyInput, setWhatsappKeyInput] = useState("");
  const [testingWhatsapp, setTestingWhatsapp] = useState(false);
  const [whatsappTestOk, setWhatsappTestOk] = useState("");

  useEffect(() => {
    if (!storeId) {
      setLoading(false);
      return;
    }
    api.aiAds
      .getSettings(storeId)
      .then(setSettings)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [storeId]);

  async function save(extra?: Record<string, unknown>) {
    if (!storeId || !settings) return false;
    setSaving(true);
    setError("");
    try {
      const key = (extra?.whatsapp_api_key as string | undefined) ?? whatsappKeyInput.trim();
      const next = await api.aiAds.updateSettings(storeId, {
        ...settings,
        ...extra,
        whatsapp_api_key: key || undefined,
      });
      setSettings(next);
      setWhatsappKeyInput("");
      setSavedAt(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function testWhatsApp() {
    if (!storeId) return;
    const saved = await save();
    if (!saved) return;
    setTestingWhatsapp(true);
    setWhatsappTestOk("");
    setError("");
    try {
      const result = await api.aiAds.testWhatsAppAlert(storeId);
      setWhatsappTestOk(result.message);
      window.setTimeout(() => setWhatsappTestOk(""), 6000);
      setSettings(await api.aiAds.getSettings(storeId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not send the WhatsApp test");
      try {
        setSettings(await api.aiAds.getSettings(storeId));
      } catch {
        /* ignore */
      }
    } finally {
      setTestingWhatsapp(false);
    }
  }

  async function saveAvatar() {
    if (!storeId || !avatarName.trim()) return;
    setSaving(true);
    try {
      await api.aiAds.upsertAvatar(storeId, {
        name: avatarName,
        description: avatarDesc,
        active: true,
      });
      setAvatarName("");
      setAvatarDesc("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Avatar save failed");
    } finally {
      setSaving(false);
    }
  }

  if (!storeId) return <p className="text-sm text-content-muted">Select a store first.</p>;
  if (loading || !settings) return <PageLoader label="Loading settings" />;

  return (
    <div className="max-w-3xl space-y-5">
      {error && (
        <p className="flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-600">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </p>
      )}

      <Card>
        <CardHeader className="mb-4">
          <div className="flex items-center gap-2">
            <Plug className="h-4 w-4 text-brand-600 dark:text-brand-400" />
            <CardTitle>Connections</CardTitle>
          </div>
          <CardDescription>
            Meta tokens live in Ads / Analytics settings. OpenAI for this module is stored
            separately from AI Email Assistant and Ads reports.
          </CardDescription>
        </CardHeader>
        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
          <Connection label="Meta Ads" ok={settings.meta_configured}>
            {settings.meta_configured ? "Connected" : "Not connected"}
          </Connection>
          <Connection label="OpenAI" ok={settings.openai_configured}>
            {settings.openai_configured
              ? settings.openai_key_masked || "Configured"
              : "Missing — rendering will fail"}
          </Connection>
          <Connection label="Video model" ok>
            {settings.video_model || "sora-2"}
          </Connection>
          <Connection label="Strategy model" ok>
            {settings.strategy_model}
          </Connection>
        </dl>
        <div className="mt-5 border-t border-border pt-5">
          <OpenAIModuleKeyCard
            status={settings}
            moduleName="AI Ads"
            description="Used only to generate and analyze creatives in AI Ads. Removing it will not disconnect AI Email Assistant."
            onSave={api.aiAds.saveOpenAIKey}
            onRemove={api.aiAds.deleteOpenAIKey}
            onStatus={(status) =>
              setSettings((prev) =>
                prev
                  ? {
                      ...prev,
                      openai_configured: status.openai_configured,
                      openai_key_masked: status.openai_key_masked,
                      openai_key_is_user_owned: status.openai_key_is_user_owned,
                      openai_uses_server_fallback: status.openai_uses_server_fallback,
                    }
                  : prev
              )
            }
          />
        </div>
      </Card>

      <Card>
        <CardHeader className="mb-4">
          <div className="flex items-center gap-2">
            <CalendarClock className="h-4 w-4 text-brand-600 dark:text-brand-400" />
            <CardTitle>Weekly automation</CardTitle>
          </div>
          <CardDescription>
            Syncs Meta, then queues a small batch of stills and videos modelled on your winning ads.
            Nothing is auto-published, and every file still needs your approval.
          </CardDescription>
        </CardHeader>
        <div className="space-y-5">
          <div className="rounded-lg border border-border bg-surface-muted/40 p-3.5">
            <Switch
              checked={settings.weekly_generation_enabled}
              onChange={(v) => setSettings({ ...settings, weekly_generation_enabled: v })}
              label="Run a batch for this store every week"
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Select
              label="Generation day"
              value={(settings.generation_day || "monday").toLowerCase()}
              onChange={(e) => setSettings({ ...settings, generation_day: e.target.value })}
            >
              {DAYS.map((d) => (
                <option key={d} value={d}>
                  {d.charAt(0).toUpperCase() + d.slice(1)}
                </option>
              ))}
            </Select>
            <Select
              label="Stills per run"
              value={String(Math.min(8, Math.max(0, settings.image_count ?? 2)))}
              onChange={(e) => setSettings({ ...settings, image_count: Number(e.target.value) })}
              hint="Each still spends model credits"
            >
              {[0, 1, 2, 3, 4].map((n) => (
                <option key={n} value={n}>
                  {n} still{n === 1 ? "" : "s"}
                </option>
              ))}
            </Select>
            <Select
              label="Videos per run"
              value={String(Math.min(4, Math.max(0, settings.video_count ?? 1)))}
              onChange={(e) => setSettings({ ...settings, video_count: Number(e.target.value) })}
              hint="Each clip spends model credits"
            >
              {[0, 1, 2, 3, 4].map((n) => (
                <option key={n} value={n}>
                  {n} video{n === 1 ? "" : "s"}
                </option>
              ))}
            </Select>
            <Input
              label="Brand style"
              placeholder="e.g. warm morning light, matte tones"
              value={settings.brand_style}
              onChange={(e) => setSettings({ ...settings, brand_style: e.target.value })}
            />
            <Input
              label="Default audience"
              placeholder="Who these ads are for"
              value={settings.default_audience}
              onChange={(e) => setSettings({ ...settings, default_audience: e.target.value })}
            />
          </div>
          <Input
            label="Meta Page ID"
            hint="Required later, when you publish an approved video to Meta."
            value={settings.meta_page_id || ""}
            onChange={(e) => setSettings({ ...settings, meta_page_id: e.target.value || null })}
          />
          <p className="rounded-lg bg-surface-muted/60 px-3 py-2.5 text-xs text-content-subtle">
            Weekly runs also need <code>AI_AD_GENERATION_ENABLED=true</code> on the server.
            Auto-publish is{" "}
            {settings.env_auto_publish ? "allowed by server config" : "disabled globally"}, and
            human approval is required either way.
          </p>
          <div className="flex items-center gap-3">
            <Button onClick={() => void save()} isLoading={saving}>
              Save settings
            </Button>
            {savedAt && !saving && (
              <span className="text-xs text-content-subtle">Saved at {savedAt}</span>
            )}
          </div>
        </div>
      </Card>

      <WhatsAppAlertsCard
        moduleName="AI Ads"
        title="WhatsApp when the weekly batch is done"
        description="When this week's stills and videos finish generating, you get a recap on your phone: what was made, for which product, and that nothing was published. Customers are never messaged."
        enableLabel="Send me a recap on WhatsApp"
        enableDescription="Fires after the weekly generation job completes or fails. Turn this on if WhatsApp is already connected for another module — no extra setup."
        enabled={Boolean(settings.whatsapp_weekly_alerts_enabled)}
        onEnabledChange={(v) => setSettings({ ...settings, whatsapp_weekly_alerts_enabled: v })}
        phone={settings.whatsapp_phone || ""}
        onPhoneChange={(v) => setSettings({ ...settings, whatsapp_phone: v })}
        configured={Boolean(settings.whatsapp_configured)}
        apiKeyHint={settings.whatsapp_api_key_hint ?? null}
        lastError={settings.whatsapp_last_error ?? null}
        setupUrl={settings.whatsapp_setup_url}
        allowMessage={settings.whatsapp_allow_message}
        connectedModules={settings.whatsapp_connected_modules || []}
        keyInput={whatsappKeyInput}
        onKeyInputChange={setWhatsappKeyInput}
        saving={saving}
        testing={testingWhatsapp}
        testOk={whatsappTestOk}
        onSaveAndTest={() => testWhatsApp()}
      />

      <Card>
        <CardHeader className="mb-4">
          <div className="flex items-center gap-2">
            <UserSquare2 className="h-4 w-4 text-brand-600 dark:text-brand-400" />
            <CardTitle>Brand avatar</CardTitle>
          </div>
          <CardDescription>
            Optional. Used only for UGC-style concepts when you select it on a run.
          </CardDescription>
        </CardHeader>
        <div className="space-y-3">
          <Input
            label="Name"
            placeholder="e.g. Maya — 32, runs a home studio"
            value={avatarName}
            onChange={(e) => setAvatarName(e.target.value)}
          />
          <Input
            label="Description / usage rules"
            placeholder="How this person should appear and speak"
            value={avatarDesc}
            onChange={(e) => setAvatarDesc(e.target.value)}
          />
          <Button
            variant="outline"
            onClick={() => void saveAvatar()}
            isLoading={saving}
            disabled={!avatarName.trim()}
          >
            Save avatar
          </Button>
        </div>
      </Card>
    </div>
  );
}

function Connection({
  label,
  ok,
  children,
}: {
  label: string;
  ok: boolean;
  children: ReactNode;
}) {
  return (
    <div className="flex items-start gap-2.5">
      <span
        className={cn(
          "mt-1.5 h-2 w-2 shrink-0 rounded-full",
          ok ? "bg-emerald-500" : "bg-amber-500"
        )}
      />
      <div className="min-w-0">
        <dt className="text-xs uppercase tracking-wide text-content-subtle">{label}</dt>
        <dd
          className={cn(
            "truncate text-sm font-medium",
            ok ? "text-content" : "text-amber-600 dark:text-amber-400"
          )}
        >
          {children}
        </dd>
      </div>
    </div>
  );
}
