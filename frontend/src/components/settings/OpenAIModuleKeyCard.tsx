import { useState } from "react";
import { KeyRound } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";

type KeyStatus = {
  openai_configured: boolean;
  openai_key_masked: string | null;
  openai_key_is_user_owned?: boolean;
  openai_uses_server_fallback?: boolean;
};

type Props = {
  status: KeyStatus | null;
  moduleName: string;
  description: string;
  onSave: (apiKey: string) => Promise<KeyStatus>;
  onRemove: () => Promise<KeyStatus>;
  onStatus: (status: KeyStatus) => void;
};

export function OpenAIModuleKeyCard({
  status,
  moduleName,
  description,
  onSave,
  onRemove,
  onStatus,
}: Props) {
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const owned = Boolean(status?.openai_key_is_user_owned);

  const save = async () => {
    if (!value.trim()) return;
    setSaving(true);
    setError("");
    try {
      onStatus(await onSave(value.trim()));
      setValue("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save key");
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    setSaving(true);
    setError("");
    try {
      onStatus(await onRemove());
      setValue("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove key");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <KeyRound className="h-4 w-4 text-brand-600" />
        <Badge variant={status?.openai_configured ? "success" : "warning"}>
          {status?.openai_configured ? "OpenAI key ready" : "OpenAI key missing"}
        </Badge>
        {owned && status?.openai_key_masked && (
          <span className="font-mono text-xs text-content-muted">{status.openai_key_masked}</span>
        )}
      </div>
      <p className="text-sm text-content-muted leading-relaxed">{description}</p>
      {status?.openai_uses_server_fallback && !owned && (
        <p className="text-xs text-content-muted rounded-lg bg-surface-muted px-3 py-2">
          Using a temporary shared key for development. Add your own key for {moduleName}.
        </p>
      )}
      <Input
        label={owned ? "Replace key" : "API key"}
        type="password"
        autoComplete="off"
        spellCheck={false}
        placeholder="sk-..."
        className="font-mono"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        hint="Get a key at platform.openai.com/api-keys. This key is only used by this module."
      />
      <div className="flex flex-wrap gap-2">
        <Button type="button" onClick={() => void save()} disabled={saving || !value.trim()}>
          {saving ? "Saving…" : owned ? "Update key" : "Save key"}
        </Button>
        {owned && (
          <Button type="button" variant="outline" onClick={() => void remove()} disabled={saving}>
            Remove
          </Button>
        )}
      </div>
      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
    </div>
  );
}
