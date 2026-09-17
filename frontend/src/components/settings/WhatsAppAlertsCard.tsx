import { useState } from "react";
import { Check, ExternalLink, MessageCircle, Send } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { cn } from "@/lib/cn";

const DEFAULT_SETUP_URL = "https://www.callmebot.com/blog/free-api-whatsapp-messages/";
const DEFAULT_ALLOW = "I allow callmebot to send me messages";

type Props = {
  title?: string;
  description?: string;
  phone: string;
  onPhoneChange: (value: string) => void;
  configured: boolean;
  apiKeyHint: string | null;
  lastError: string | null;
  error?: string;
  setupUrl?: string;
  allowMessage?: string;
  connectedModules?: string[];
  keyInput: string;
  onKeyInputChange: (value: string) => void;
  onSaveAndTest: () => Promise<void>;
  saving?: boolean;
  testing?: boolean;
  testOk?: string;
};

export function WhatsAppAlertsCard({
  title = "WhatsApp notifications",
  description = "Get a message on your own phone when something needs you. Setup takes about two minutes and you only do it once.",
  phone,
  onPhoneChange,
  configured,
  apiKeyHint,
  lastError,
  error = "",
  setupUrl,
  allowMessage,
  connectedModules = [],
  keyInput,
  onKeyInputChange,
  onSaveAndTest,
  saving = false,
  testing = false,
  testOk = "",
}: Props) {
  const [showChange, setShowChange] = useState(!configured);
  const [copied, setCopied] = useState(false);
  const phrase = allowMessage || DEFAULT_ALLOW;
  const busy = saving || testing;
  const missingCreds = !phone.trim() || (!configured && !keyInput.trim());

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
          {title}
        </CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <div className="space-y-5">
        {configured ? (
          <div className="rounded-lg border border-border bg-surface-muted/50 px-4 py-3 space-y-2">
            <p className="text-sm text-content">
              WhatsApp is connected
              {connectedModules.length > 0 ? (
                <> and used by {connectedModules.join(", ")}</>
              ) : null}
              . Turn on alerts in AI Email Assistant or AI Ads when you want them.
            </p>
            <p className="text-xs text-content-subtle">
              Number {phone || "saved"}
              {apiKeyHint ? ` · key ${apiKeyHint}` : ""}.
            </p>
            <button
              type="button"
              className="text-xs font-medium text-brand-600 dark:text-brand-400 hover:underline"
              onClick={() => setShowChange((v) => !v)}
            >
              {showChange ? "Hide number and key" : "Change number or key"}
            </button>
          </div>
        ) : (
          <SetupSteps
            setupUrl={setupUrl || DEFAULT_SETUP_URL}
            phrase={phrase}
            onCopy={copyPhrase}
            copied={copied}
          />
        )}

        {(showChange || !configured) && (
          <div className="space-y-3">
            <Input
              label="Your WhatsApp number"
              hint="Include country code. Example: +1 514 555 0100"
              placeholder="+1 514 555 0100"
              value={phone}
              onChange={(e) => onPhoneChange(e.target.value)}
              autoComplete="tel"
            />
            <Input
              label="CallMeBot API key"
              hint={
                configured
                  ? `Saved key ${apiKeyHint || "••••"}. Leave blank to keep it, or paste a new key to replace it.`
                  : "Paste the API key from the WhatsApp message (not your WhatsApp password)."
              }
              placeholder={configured ? "Leave blank to keep saved key" : "123123"}
              type="password"
              value={keyInput}
              onChange={(e) => onKeyInputChange(e.target.value)}
              autoComplete="new-password"
              name="callmebot-api-key"
              data-1p-ignore="true"
              data-lpignore="true"
            />
          </div>
        )}

        {error ? (
          <p className="text-sm text-red-600 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
            {error}
          </p>
        ) : lastError ? (
          <p className="text-xs text-red-500 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
            Last send failed: {lastError}
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={busy || missingCreds}
            onClick={() => void onSaveAndTest()}
          >
            <Send className={cn("h-4 w-4 mr-2", busy && "animate-pulse")} />
            {busy ? "Saving and sending test…" : "Save and send a test WhatsApp"}
          </Button>
          {(testOk || copied) && (
            <span className="text-sm text-green-600 dark:text-green-400 flex items-center gap-1">
              <Check className="h-4 w-4" /> {copied ? "Copied. Paste that message into WhatsApp." : testOk}
            </span>
          )}
        </div>
        {missingCreds && (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            Nothing will send until both the number and API key are saved.
          </p>
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
}: {
  setupUrl: string;
  phrase: string;
  onCopy: () => void;
  copied: boolean;
}) {
  return (
    <div className="rounded-lg border border-border bg-surface-muted/50 px-4 py-4 space-y-4">
      <div>
        <p className="text-sm font-medium text-content">How to connect (one time, about 2 minutes)</p>
        <p className="text-xs text-content-subtle mt-1">
          Uses CallMeBot, a free personal WhatsApp helper. It can only text you — never your
          customers. You only do this once for the whole app.
        </p>
      </div>
      <ol className="space-y-3 text-sm text-content-muted leading-relaxed">
        <li className="flex gap-3">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface border border-border text-xs font-semibold text-content">
            1
          </span>
          <div>
            <p className="font-medium text-content">Add the CallMeBot number as a contact</p>
            <p className="mt-0.5">Open the setup page and save the WhatsApp number shown there.</p>
            <a
              href={setupUrl}
              target="_blank"
              rel="noreferrer"
              className="mt-1.5 inline-flex items-center gap-1 text-brand-600 dark:text-brand-400 hover:underline"
            >
              Open CallMeBot and get the current number
              <ExternalLink className="h-3 w-3" />
            </a>
            <p className="text-xs text-content-subtle mt-1">
              That number changes when the bot is full. If the page says it is full, wait until a
              new number appears — do not guess an old one.
            </p>
          </div>
        </li>
        <li className="flex gap-3">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface border border-border text-xs font-semibold text-content">
            2
          </span>
          <div>
            <p className="font-medium text-content">Send this exact phrase on WhatsApp</p>
            <p className="mt-0.5">Message the new contact from the same phone that should receive alerts:</p>
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
            <p className="font-medium text-content">Copy the API key they reply with</p>
            <p className="mt-0.5">
              You should get: “API Activated… Your APIKEY is 123123”. If nothing arrives in 2
              minutes, wait 24 hours and send the phrase again. Lost the key later? Send{" "}
              <code className="rounded bg-surface px-1 py-0.5 text-[11px] border border-border text-content">
                Recover APIKey
              </code>{" "}
              to the same contact.
            </p>
          </div>
        </li>
        <li className="flex gap-3">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface border border-border text-xs font-semibold text-content">
            4
          </span>
          <div>
            <p className="font-medium text-content">Paste your number and key below, then send a test</p>
            <p className="mt-0.5">
              After that, turn on alerts in AI Email Assistant (manual reviews) or AI Ads (weekly
              ads).
            </p>
          </div>
        </li>
      </ol>
    </div>
  );
}
