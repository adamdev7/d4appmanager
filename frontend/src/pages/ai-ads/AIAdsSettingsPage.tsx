import { useEffect, useState } from "react";
import { useStore } from "@/context/StoreContext";
import { api, type AIAdsSettings } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Switch } from "@/components/ui/Switch";
import { PageLoader } from "@/components/ui/Loading";

export function AIAdsSettingsPage() {
  const { activeStore, stores } = useStore();
  const storeId = activeStore?.id ?? stores[0]?.id ?? null;
  const [settings, setSettings] = useState<AIAdsSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [avatarName, setAvatarName] = useState("");
  const [avatarDesc, setAvatarDesc] = useState("");

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

  async function save() {
    if (!storeId || !settings) return;
    setSaving(true);
    setError("");
    try {
      setSettings(await api.aiAds.updateSettings(storeId, settings));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
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
    <div className="space-y-6 max-w-3xl">
      <Card>
        <CardHeader>
          <CardTitle>Connections</CardTitle>
          <CardDescription>
            Meta tokens stay in Ads / Analytics settings. OpenAI keys stay in AI Email Assistant.
            They are never sent to the browser.
          </CardDescription>
        </CardHeader>
        <ul className="text-sm space-y-1 text-content">
          <li>Meta Ads: {settings.meta_configured ? "Connected" : "Not connected"}</li>
          <li>OpenAI: {settings.openai_configured ? settings.openai_key_masked || "Configured" : "Missing"}</li>
          <li>Strategy model: {settings.strategy_model}</li>
          <li>Image model: {settings.image_model}</li>
          <li>Video model: {settings.video_model || "sora-2"}</li>
        </ul>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Weekly automation</CardTitle>
          <CardDescription>
            Syncs Meta, then queues a small generation job from winning ad styles. Ads are never
            auto-published. Keep counts low — each image or video render spends model credits.
          </CardDescription>
        </CardHeader>
        {error && <p className="text-sm text-red-600 mb-3">{error}</p>}
        <div className="space-y-4">
          <Switch
            checked={settings.weekly_generation_enabled}
            onChange={(v) => setSettings({ ...settings, weekly_generation_enabled: v })}
            label="Enable weekly generation for this store"
          />
          <Input
            label="Generation day"
            value={settings.generation_day}
            onChange={(e) => setSettings({ ...settings, generation_day: e.target.value })}
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              label="Default image count (0 = skip, max 8)"
              type="number"
              min={0}
              max={8}
              value={settings.image_count}
              onChange={(e) => setSettings({ ...settings, image_count: Number(e.target.value) })}
            />
            <Input
              label="Default video count (0 = skip, max 4)"
              type="number"
              min={0}
              max={4}
              value={settings.video_count}
              onChange={(e) => setSettings({ ...settings, video_count: Number(e.target.value) })}
            />
          </div>
          <Input
            label="Brand style"
            value={settings.brand_style}
            onChange={(e) => setSettings({ ...settings, brand_style: e.target.value })}
          />
          <Input
            label="Default audience"
            value={settings.default_audience}
            onChange={(e) => setSettings({ ...settings, default_audience: e.target.value })}
          />
          <Input
            label="Meta Page ID (required later to publish)"
            value={settings.meta_page_id || ""}
            onChange={(e) => setSettings({ ...settings, meta_page_id: e.target.value || null })}
          />
          <p className="text-xs text-content-subtle">
            Weekly jobs also require <code>AI_AD_GENERATION_ENABLED=true</code> on the server.
            Auto-publish is {settings.env_auto_publish ? "allowed by server config" : "disabled globally"}.
            Human approval is still required in this version.
          </p>
          <Button onClick={() => void save()} isLoading={saving}>
            Save settings
          </Button>
        </div>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Optional brand avatar</CardTitle>
          <CardDescription>Used only for UGC-style concepts when selected. Not required.</CardDescription>
        </CardHeader>
        <div className="space-y-3">
          <Input label="Name" value={avatarName} onChange={(e) => setAvatarName(e.target.value)} />
          <Input
            label="Description / usage rules"
            value={avatarDesc}
            onChange={(e) => setAvatarDesc(e.target.value)}
          />
          <Button variant="outline" onClick={() => void saveAvatar()} isLoading={saving}>
            Save avatar
          </Button>
        </div>
      </Card>
    </div>
  );
}
