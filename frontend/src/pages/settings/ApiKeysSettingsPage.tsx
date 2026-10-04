import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { OpenAIModuleKeyCard } from "@/components/settings/OpenAIModuleKeyCard";

type KeyStatus = {
  openai_configured: boolean;
  openai_key_masked: string | null;
  openai_key_is_user_owned?: boolean;
  openai_uses_server_fallback?: boolean;
};

const emptyStatus = (): KeyStatus => ({
  openai_configured: false,
  openai_key_masked: null,
  openai_key_is_user_owned: false,
  openai_uses_server_fallback: false,
});

export function ApiKeysSettingsPage() {
  const [emailKey, setEmailKey] = useState<KeyStatus>(emptyStatus());
  const [adsKey, setAdsKey] = useState<KeyStatus>(emptyStatus());
  const [aiAdsKey, setAiAdsKey] = useState<KeyStatus>(emptyStatus());

  useEffect(() => {
    api.aiEmailAssistant.openaiKeyStatus().then(setEmailKey).catch(() => undefined);
    api.ads.openaiKeyStatus().then(setAdsKey).catch(() => undefined);
    api.aiAds.openaiKeyStatus().then(setAiAdsKey).catch(() => undefined);
  }, []);

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-content tracking-tight">API keys</h1>
        <p className="text-sm text-content-muted mt-1 leading-relaxed">
          Each option keeps its own OpenAI key, so a bad key in one place does not blank the
          others. Pick the model inside that option. The default, Sol, is the one that spends
          less for results close to the flagship.
        </p>
      </div>

      <Card padding="lg">
        <CardHeader>
          <CardTitle>AI Email Assistant</CardTitle>
          <CardDescription>
            Drafts customer replies. Choose the model under{" "}
            <Link to="/modules/ai-email" className="text-brand-600 hover:underline">
              AI Email → Settings
            </Link>
            .
          </CardDescription>
        </CardHeader>
        <OpenAIModuleKeyCard
          status={emailKey}
          moduleName="AI Email Assistant"
          description="Used only when this option drafts or sends a reply."
          onSave={api.aiEmailAssistant.saveOpenAIKey}
          onRemove={api.aiEmailAssistant.deleteOpenAIKey}
          onStatus={setEmailKey}
        />
      </Card>

      <Card padding="lg">
        <CardHeader>
          <CardTitle>Ads reports</CardTitle>
          <CardDescription>
            Campaign write-ups. Choose the model under{" "}
            <Link to="/modules/ads" className="text-brand-600 hover:underline">
              Ads → Settings
            </Link>
            .
          </CardDescription>
        </CardHeader>
        <OpenAIModuleKeyCard
          status={adsKey}
          moduleName="Ads reports"
          description="Used only when Ads generates a performance report."
          onSave={api.ads.saveOpenAIKey}
          onRemove={api.ads.deleteOpenAIKey}
          onStatus={setAdsKey}
        />
      </Card>

      <Card padding="lg">
        <CardHeader>
          <CardTitle>AI Ads</CardTitle>
          <CardDescription>
            Strategy, analysis, and ad copy. Image and video models stay on the server. Choose
            the text model under{" "}
            <Link to="/ai-ads/settings" className="text-brand-600 hover:underline">
              AI Ads → Settings
            </Link>
            .
          </CardDescription>
        </CardHeader>
        <OpenAIModuleKeyCard
          status={aiAdsKey}
          moduleName="AI Ads"
          description="Used for creative direction and copy. It does not replace the image or video model."
          onSave={api.aiAds.saveOpenAIKey}
          onRemove={api.aiAds.deleteOpenAIKey}
          onStatus={setAiAdsKey}
        />
      </Card>
    </div>
  );
}
