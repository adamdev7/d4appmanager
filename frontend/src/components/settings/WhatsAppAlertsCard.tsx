import { useState } from "react";
import { Check, ExternalLink, MessageCircle, Plus, Send, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { cn } from "@/lib/cn";
import type { WhatsAppRecipient } from "@/lib/api";

const DEFAULT_SETUP_URL = "https://www.callmebot.com/blog/free-api-whatsapp-messages/";
const DEFAULT_ALLOW = "I allow callmebot to send me messages";

type FormState = {
  id?: string;
  label: string;
  phone: string;
  apiKey: string;
};

type Props = {
  connections: WhatsAppRecipient[];
  maxConnections?: number;
  setupUrl?: string;
  allowMessage?: string;
  connectedModules?: string[];
  error?: string;
  testOk?: string;
  busy?: boolean;
  editingId: string | null;
  form: FormState;
  onFormChange: (patch: Partial<FormState>) => void;
  onStartAdd: () => void;
  onStartEdit: (row: WhatsAppRecipient) => void;
  onCancelForm: () => void;
  onSaveAndTest: () => Promise<void>;
  onTestExisting: (id: string) => Promise<void>;
  onRemove: (id: string) => Promise<void>;
};

export function WhatsAppAlertsCard({
  connections,
  maxConnections = 5,
  setupUrl,
  allowMessage,
  connectedModules = [],
  error = "",
  testOk = "",
  busy = false,
  editingId,
  form,
  onFormChange,
  onStartAdd,
  onStartEdit,
  onCancelForm,
  onSaveAndTest,
  onTestExisting,
  onRemove,
}: Props) {
  const [copied, setCopied] = useState(false);
  const phrase = allowMessage || DEFAULT_ALLOW;
  const showForm = editingId !== null;
  const isNew = editingId === "new";
  const configured = connections.length > 0;
  const atLimit = connections.length >= maxConnections;
  const missingCreds =
    !form.phone.trim() || (isNew && !form.apiKey.trim()) || (!isNew && !configured && !form.apiKey.trim());

  const copyPhrase = async () => {
    try {
      await navigator.clipboard.writeText(phrase);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2500);
    } catch {
      /* parent surfaces errors if needed */
    }
  };

  return (
    <Card padding="lg">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MessageCircle className="h-4 w-4 text-brand-600 dark:text-brand-400" />
          WhatsApp notifications
        </CardTitle>
        <CardDescription>
          Get a message on your phones when something needs you. Each number needs its own CallMeBot
          API key. Alerts go to every number you save.
        </CardDescription>
      </CardHeader>
      <div className="space-y-5">
        {configured ? (
          <div className="space-y-3">
            <p className="text-sm text-content">
              {connections.length} number{connections.length === 1 ? "" : "s"} connected
              {connectedModules.length > 0 ? (
                <> · used by {connectedModules.join(", ")}</>
              ) : null}
              . Turn on alerts in AI Email Assistant or AI Ads when you want them.
            </p>
            <ul className="space-y-2">
              {connections.map((row) => (
                <li
                  key={row.id}
                  className="rounded-lg border border-border bg-surface-muted/50 px-4 py-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-content truncate">
                      {row.label || "WhatsApp"}
                      <span className="font-normal text-content-muted"> · {row.phone}</span>
                    </p>
                    <p className="text-xs text-content-subtle">
                      key {row.api_key_hint || "••••"}
                      {row.last_error ? " · last send failed" : ""}
                    </p>
                    {row.last_error && editingId !== row.id && (
                      <p className="text-xs text-red-500 mt-1">{row.last_error}</p>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-2 shrink-0">
                    <Button
                      type="button"
                      variant="outline"
                      className="h-8 px-2.5 text-xs"
                      disabled={busy}
                      onClick={() => void onTestExisting(row.id)}
                    >
                      <Send className={cn("h-3.5 w-3.5 mr-1.5", busy && "animate-pulse")} />
                      Test
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      className="h-8 px-2.5 text-xs"
                      disabled={busy}
                      onClick={() => onStartEdit(row)}
                    >
                      Edit
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      className="h-8 px-2.5 text-xs text-red-600 hover:text-red-700"
                      disabled={busy}
                      onClick={() => void onRemove(row.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
            {!showForm && !atLimit && (
              <Button type="button" variant="outline" disabled={busy} onClick={onStartAdd}>
                <Plus className="h-4 w-4 mr-2" />
                Add another WhatsApp
              </Button>
            )}
            {!showForm && atLimit && (
              <p className="text-xs text-content-subtle">
                Limit of {maxConnections} WhatsApp numbers reached.
              </p>
            )}
          </div>
        ) : (
          <SetupSteps
            setupUrl={setupUrl || DEFAULT_SETUP_URL}
            phrase={phrase}
            onCopy={copyPhrase}
            copied={copied}
          />
        )}

        {showForm && (
          <div className="rounded-lg border border-border px-4 py-4 space-y-3">
            <p className="text-sm font-medium text-content">
              {isNew ? "Add a WhatsApp number" : "Edit WhatsApp number"}
            </p>
            {isNew && configured && (
              <SetupSteps
                setupUrl={setupUrl || DEFAULT_SETUP_URL}
                phrase={phrase}
                onCopy={copyPhrase}
                copied={copied}
                compact
              />
            )}
            <Input
              label="Label (optional)"
              hint="Example: Adam, Office, Partner"
              placeholder="Adam"
              value={form.label}
              onChange={(e) => onFormChange({ label: e.target.value })}
              autoComplete="off"
            />
            <Input
              label="WhatsApp number"
              hint="Include country code. Example: +1 514 555 0100"
              placeholder="+1 514 555 0100"
              value={form.phone}
              onChange={(e) => onFormChange({ phone: e.target.value })}
              autoComplete="tel"
            />
            <Input
              label="CallMeBot API key"
              hint={
                isNew
                  ? "Paste the API key from the WhatsApp message (not your WhatsApp password)."
                  : "Leave blank to keep the saved key, or paste a new key to replace it."
              }
              placeholder={isNew ? "123123" : "Leave blank to keep saved key"}
              type="password"
              value={form.apiKey}
              onChange={(e) => onFormChange({ apiKey: e.target.value })}
              autoComplete="new-password"
              name="callmebot-api-key"
              data-1p-ignore="true"
              data-lpignore="true"
            />
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <Button
                type="button"
                variant="outline"
                disabled={busy || missingCreds}
                onClick={() => void onSaveAndTest()}
              >
                <Send className={cn("h-4 w-4 mr-2", busy && "animate-pulse")} />
                {busy ? "Saving and sending test…" : "Save and send a test"}
              </Button>
              {configured && (
                <Button type="button" variant="ghost" disabled={busy} onClick={onCancelForm}>
                  Cancel
                </Button>
              )}
            </div>
          </div>
        )}

        {error ? (
          <p className="text-sm text-red-600 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
            {error}
          </p>
        ) : null}
        {(testOk || copied) && (
          <span className="text-sm text-green-600 dark:text-green-400 flex items-center gap-1">
            <Check className="h-4 w-4" /> {copied ? "Copied. Paste that message into WhatsApp." : testOk}
          </span>
        )}
      </div>
    </Card>
  );
}

function SetupSteps({
  setupUrl,
  phrase,
  onCopy,
  copied,
  compact = false,
}: {
  setupUrl: string;
  phrase: string;
  onCopy: () => void;
  copied: boolean;
  compact?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-surface-muted/50 px-4 space-y-4",
        compact ? "py-3" : "py-4"
      )}
    >
      <div>
        <p className="text-sm font-medium text-content">
          {compact ? "Each new phone needs its own CallMeBot key" : "How to connect (about 2 minutes)"}
        </p>
        {!compact && (
          <p className="text-xs text-content-subtle mt-1">
            Uses CallMeBot, a free personal WhatsApp helper. It can only text the phones you connect —
            never your customers.
          </p>
        )}
      </div>
      <ol className="space-y-3 text-sm text-content-muted leading-relaxed">
        <li className="flex gap-3">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface border border-border text-xs font-semibold text-content">
            1
          </span>
          <div>
            <p className="font-medium text-content">Add the CallMeBot number as a contact</p>
            <a
              href={setupUrl}
              target="_blank"
              rel="noreferrer"
              className="mt-1.5 inline-flex items-center gap-1 text-brand-600 dark:text-brand-400 hover:underline"
            >
              Open CallMeBot and get the current number
              <ExternalLink className="h-3 w-3" />
            </a>
          </div>
        </li>
        <li className="flex gap-3">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface border border-border text-xs font-semibold text-content">
            2
          </span>
          <div>
            <p className="font-medium text-content">Send this exact phrase from that phone</p>
            <span className="mt-2 flex flex-wrap items-center gap-2">
              <code className="rounded bg-surface px-2 py-1 text-xs text-content border border-border">
                {phrase}
              </code>
              <button
                type="button"
                onClick={onCopy}
                className="text-xs font-medium text-brand-600 dark:text-brand-400 hover:underline"
              >
                {copied ? "Copied" : "Copy phrase"}
              </button>
            </span>
          </div>
        </li>
        <li className="flex gap-3">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface border border-border text-xs font-semibold text-content">
            3
          </span>
          <div>
            <p className="font-medium text-content">Paste the API key they reply with below</p>
            <p className="mt-0.5 text-xs">
              Lost the key? Send{" "}
              <code className="rounded bg-surface px-1 py-0.5 text-[11px] border border-border text-content">
                Recover APIKey
              </code>{" "}
              to the same contact.
            </p>
          </div>
        </li>
      </ol>
    </div>
  );
}
