import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Sparkles,
  RefreshCw,
  Mail,
  Settings2,
  ScrollText,
  Send,
  X,
  Check,
  AlertCircle,
  Filter,
  Ban,
  KeyRound,
  Bot,
} from "lucide-react";
import { useStore } from "@/context/StoreContext";
import { api } from "@/lib/api";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Switch } from "@/components/ui/Switch";
import { Input } from "@/components/ui/Input";
import { cn } from "@/lib/cn";
import type { GmailAccount } from "@/types";

type Tab = "inbox" | "settings" | "logs";

type InboxItem = {
  id: string;
  sender: string;
  sender_email: string;
  subject: string;
  body_text: string;
  detected_intent: string | null;
  skip_reason: string | null;
  filter_category: string | null;
  status: string;
  received_at: string;
  latest_reply: {
    id: string;
    effective_body: string;
    status: string;
    model_used: string;
  } | null;
};

type Settings = {
  business_name: string;
  business_type: string;
  tone_of_voice: string;
  rules: string;
  policies: string;
  faq: string;
  auto_send_enabled: boolean;
  gmail_account_id: string | null;
  openai_model: string | null;
  email_filter_enabled: boolean;
  filter_automated_emails: boolean;
  filter_non_business_emails: boolean;
  filter_custom_rules: string;
  openai_configured: boolean;
  openai_key_masked: string | null;
  openai_key_is_user_owned: boolean;
  openai_uses_server_fallback: boolean;
  automation_enabled: boolean;
  automation_interval_minutes: number;
  automation_max_emails_per_run: number;
  automation_last_run_at: string | null;
  automation_last_error: string | null;
  one_reply_per_thread: boolean;
  sync_only_customer_unread: boolean;
  verify_gmail_thread_before_reply: boolean;
  use_thread_context: boolean;
  default_model: string;
};

type LogEntry = {
  id: string;
  subject: string;
  sender_email: string;
  status: string;
  model_used: string;
  body_preview: string;
  created_at: string;
  sent_at: string | null;
};

const TABS: { id: Tab; label: string; icon: typeof Mail }[] = [
  { id: "inbox", label: "Inbox", icon: Mail },
  { id: "settings", label: "Business context", icon: Settings2 },
  { id: "logs", label: "AI audit log", icon: ScrollText },
];

function intentLabel(intent: string | null) {
  if (!intent) return null;
  return intent.replace(/_/g, " ");
}

function formatTime(iso: string) {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function statusBadge(status: string) {
  const map: Record<string, "default" | "success" | "warning" | "muted"> = {
    new: "warning",
    draft_pending: "default",
    replied: "success",
    sent: "success",
    draft: "default",
    failed: "warning",
    rejected: "muted",
    skipped: "muted",
  };
  return map[status] ?? "default";
}

function filterCategoryLabel(category: string | null) {
  if (!category) return null;
  const labels: Record<string, string> = {
    automated: "Automated",
    newsletter: "Newsletter",
    personal: "Non-business",
    spam: "Spam",
    other: "Filtered",
    customer: "Customer",
    acknowledgment: "Thank-you",
  };
  return labels[category] ?? category;
}

export function AIEmailAssistantPage() {
  const { activeStore } = useStore();
  const [tab, setTab] = useState<Tab>("inbox");
  const [accounts, setAccounts] = useState<GmailAccount[]>([]);
  const [inbox, setInbox] = useState<InboxItem[]>([]);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draftEdit, setDraftEdit] = useState("");
  const [savingSettings, setSavingSettings] = useState(false);
  const [openaiKeyInput, setOpenaiKeyInput] = useState("");
  const [savingOpenaiKey, setSavingOpenaiKey] = useState(false);
  const [runningAutomation, setRunningAutomation] = useState(false);
  const [actionId, setActionId] = useState<string | null>(null);

  const selected = inbox.find((e) => e.id === selectedId) ?? inbox[0] ?? null;

  const loadAccounts = useCallback(async () => {
    const data = await api.gmail.accounts(activeStore?.id);
    setAccounts(data as GmailAccount[]);
    return data as GmailAccount[];
  }, [activeStore?.id]);

  const loadInbox = useCallback(async () => {
    const data = await api.aiEmailAssistant.inbox(activeStore?.id);
    setInbox(data as InboxItem[]);
    setSelectedId((prev) => prev ?? (data as InboxItem[])[0]?.id ?? null);
  }, [activeStore?.id]);

  const loadSettings = useCallback(async () => {
    const s = await api.aiEmailAssistant.settings(activeStore?.id);
    setSettings(s as Settings);
  }, [activeStore?.id]);

  const loadLogs = useCallback(async () => {
    const l = await api.aiEmailAssistant.logs();
    setLogs(l as LogEntry[]);
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      await loadAccounts();
      await Promise.all([loadInbox(), loadSettings(), loadLogs()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load AI Email Assistant");
    } finally {
      setLoading(false);
    }
  }, [loadAccounts, loadInbox, loadSettings, loadLogs]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (selected?.latest_reply?.effective_body) {
      setDraftEdit(selected.latest_reply.effective_body);
    } else {
      setDraftEdit("");
    }
  }, [selected?.id, selected?.latest_reply?.effective_body]);

  const connectedAccount =
    accounts.find((a) => a.status === "connected" && a.id === settings?.gmail_account_id) ??
    accounts.find((a) => a.status === "connected");

  const syncInbox = async () => {
    const accId = settings?.gmail_account_id ?? connectedAccount?.id;
    if (!accId) {
      setError("Connect Gmail in Settings first.");
      return;
    }
    setSyncing(true);
    setError("");
    try {
      const data = await api.aiEmailAssistant.syncInbox(accId, 15, activeStore?.id);
      setInbox(data as InboxItem[]);
      if ((data as InboxItem[]).length) {
        setSelectedId((data as InboxItem[])[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  };

  const replyAnyway = async (emailId: string) => {
    setActionId(emailId);
    setError("");
    try {
      await api.aiEmailAssistant.unskipEmail(emailId);
      const reply = await api.aiEmailAssistant.generateReply(emailId, activeStore?.id);
      setDraftEdit(reply.effective_body);
      await loadInbox();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not enable reply for this email");
    } finally {
      setActionId(null);
    }
  };

  const generateDraft = async (emailId: string) => {
    setActionId(emailId);
    setError("");
    try {
      const reply = await api.aiEmailAssistant.generateReply(emailId, activeStore?.id);
      setDraftEdit(reply.effective_body);
      await loadInbox();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate reply");
      await loadSettings();
    } finally {
      setActionId(null);
    }
  };

  const saveDraftEdits = async (replyId: string) => {
    setActionId(replyId);
    try {
      await api.aiEmailAssistant.updateDraft(replyId, draftEdit);
      await loadInbox();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save draft");
    } finally {
      setActionId(null);
    }
  };

  const approveSend = async (replyId: string) => {
    setActionId(replyId);
    try {
      await api.aiEmailAssistant.approveReply(replyId);
      await Promise.all([loadInbox(), loadLogs()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Send failed");
    } finally {
      setActionId(null);
    }
  };

  const rejectDraft = async (replyId: string) => {
    setActionId(replyId);
    try {
      await api.aiEmailAssistant.rejectReply(replyId);
      await loadInbox();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reject draft");
    } finally {
      setActionId(null);
    }
  };

  const applyKeyStatus = (status: {
    openai_configured: boolean;
    openai_key_masked: string | null;
    openai_key_is_user_owned: boolean;
    openai_uses_server_fallback: boolean;
  }) => {
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
    );
  };

  const saveOpenaiKey = async () => {
    const trimmed = openaiKeyInput.trim();
    if (!trimmed) {
      setError("Paste your OpenAI API key to save it.");
      return;
    }
    setSavingOpenaiKey(true);
    setError("");
    try {
      const status = await api.aiEmailAssistant.saveOpenAIKey(trimmed);
      setOpenaiKeyInput("");
      applyKeyStatus(status);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save API key");
    } finally {
      setSavingOpenaiKey(false);
    }
  };

  const removeOpenaiKey = async () => {
    setSavingOpenaiKey(true);
    setError("");
    try {
      const status = await api.aiEmailAssistant.deleteOpenAIKey();
      setOpenaiKeyInput("");
      applyKeyStatus(status);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove API key");
    } finally {
      setSavingOpenaiKey(false);
    }
  };

  const saveSettings = async () => {
    if (!settings) return;
    setSavingSettings(true);
    try {
      await api.aiEmailAssistant.updateSettings(
        {
          business_name: settings.business_name,
          business_type: settings.business_type,
          tone_of_voice: settings.tone_of_voice,
          rules: settings.rules,
          policies: settings.policies,
          faq: settings.faq,
          auto_send_enabled: settings.auto_send_enabled,
          gmail_account_id: settings.gmail_account_id ?? connectedAccount?.id ?? null,
          openai_model: settings.openai_model || null,
          email_filter_enabled: settings.email_filter_enabled,
          filter_automated_emails: settings.filter_automated_emails,
          filter_non_business_emails: settings.filter_non_business_emails,
          filter_custom_rules: settings.filter_custom_rules,
          automation_enabled: settings.automation_enabled,
          automation_interval_minutes: settings.automation_interval_minutes,
          automation_max_emails_per_run: settings.automation_max_emails_per_run,
          one_reply_per_thread: settings.one_reply_per_thread,
          sync_only_customer_unread: settings.sync_only_customer_unread,
          verify_gmail_thread_before_reply: settings.verify_gmail_thread_before_reply,
          use_thread_context: settings.use_thread_context,
        },
        activeStore?.id
      );
      await loadSettings();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save settings");
    } finally {
      setSavingSettings(false);
    }
  };

  const textareaClass = cn(
    "flex min-h-[100px] w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-content",
    "placeholder:text-content-subtle focus:outline-none focus:ring-2 focus:ring-brand-500/30 focus:border-brand-500"
  );

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2 text-brand-600 dark:text-brand-400">
            <Sparkles className="h-5 w-5" />
            <span className="text-sm font-medium">AI Email Assistant</span>
          </div>
          <h1 className="text-2xl font-bold text-content mt-1">Gmail auto-reply</h1>
          <p className="text-content-muted mt-1 max-w-xl">
            Fetch unread customer emails, generate replies with OpenAI using your business rules,
            then approve or auto-send through Gmail.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={loadAll} disabled={loading}>
            <RefreshCw className={cn("h-4 w-4 mr-2", loading && "animate-spin")} />
            Refresh
          </Button>
          {tab === "inbox" && (
            <Button onClick={syncInbox} disabled={syncing || !connectedAccount}>
              <Mail className="h-4 w-4 mr-2" />
              {syncing ? "Syncing…" : "Sync unread"}
            </Button>
          )}
        </div>
      </div>

      {settings && !settings.openai_configured && (
        <Card className="border-amber-500/40 bg-amber-500/5">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <AlertCircle className="h-4 w-4 text-amber-600" />
              OpenAI API key required
            </CardTitle>
            <CardDescription>
              Add your own API key under{" "}
              <button
                type="button"
                className="text-brand-600 hover:underline font-medium"
                onClick={() => setTab("settings")}
              >
                Business context
              </button>
              . Your key is encrypted on the server and never shown in the browser after saving.
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      {settings?.automation_last_error && !settings.automation_enabled && (
        <Card className="border-red-500/40 bg-red-500/10">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2 text-red-700 dark:text-red-400">
              <AlertCircle className="h-4 w-4 shrink-0" />
              Autopilot stopped
            </CardTitle>
            <CardDescription className="text-red-800/90 dark:text-red-300/90">
              {settings.automation_last_error}
            </CardDescription>
          </CardHeader>
          <div className="px-6 pb-4">
            <Button variant="outline" onClick={() => setTab("settings")}>
              Fix in Business context
            </Button>
          </div>
        </Card>
      )}

      {settings?.automation_enabled && (
        <Card className="border-brand-500/30 bg-brand-500/5">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <Bot className="h-4 w-4 text-brand-600" />
              Autopilot is on
            </CardTitle>
            <CardDescription>
              Checking unread Gmail every {settings.automation_interval_minutes} minutes
              {settings.automation_last_run_at && (
                <>
                  {" "}
                  · Last run {formatTime(settings.automation_last_run_at)}
                </>
              )}
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      {settings?.openai_uses_server_fallback && (
        <Card className="border-border">
          <CardHeader className="pb-2">
            <CardDescription className="text-xs">
              Using a shared server API key (development). Save your own key in Business context for
              production.
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      {!connectedAccount && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Connect Gmail</CardTitle>
            <CardDescription>
              OAuth is required to read inbox and send replies.{" "}
              <Link to="/settings/gmail" className="text-brand-600 hover:underline">
                Connect in Gmail settings →
              </Link>
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      {error && (
        <p className="text-sm text-red-500 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      <div className="flex gap-1 border-b border-border">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={cn(
              "flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
              tab === id
                ? "border-brand-500 text-brand-700 dark:text-brand-400"
                : "border-transparent text-content-muted hover:text-content"
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      {tab === "inbox" && (
        <div className="grid gap-4 lg:grid-cols-5">
          <Card className="lg:col-span-2 p-0 overflow-hidden">
            <div className="border-b border-border px-4 py-3 text-sm font-medium text-content">
              Inbox ({inbox.length})
            </div>
            <ul className="max-h-[480px] overflow-y-auto divide-y divide-border">
              {inbox.length === 0 && (
                <li className="px-4 py-8 text-sm text-content-muted text-center">
                  No emails synced. Click &quot;Sync unread&quot; to fetch from Gmail.
                </li>
              )}
              {inbox.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(item.id)}
                    className={cn(
                      "w-full text-left px-4 py-3 hover:bg-surface-muted transition-colors",
                      selected?.id === item.id && "bg-brand-500/10"
                    )}
                  >
                    <p className="text-sm font-medium text-content truncate">{item.subject}</p>
                    <p className="text-xs text-content-muted truncate">{item.sender_email}</p>
                    <div className="flex gap-2 mt-1">
                      <Badge variant={statusBadge(item.status)}>{item.status}</Badge>
                      {item.status === "skipped" && (
                        <Badge variant="muted">No reply</Badge>
                      )}
                      {item.filter_category && (
                        <Badge variant="muted">{filterCategoryLabel(item.filter_category)}</Badge>
                      )}
                      {item.detected_intent && item.status !== "skipped" && (
                        <Badge variant="default">{intentLabel(item.detected_intent)}</Badge>
                      )}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </Card>

          <Card className="lg:col-span-3">
            {selected ? (
              <div className="space-y-4 p-4">
                <div>
                  <h2 className="font-semibold text-content">{selected.subject}</h2>
                  <p className="text-sm text-content-muted mt-1">
                    {selected.sender} · {formatTime(selected.received_at)}
                  </p>
                </div>
                <div className="rounded-lg bg-surface-muted p-3 text-sm text-content whitespace-pre-wrap max-h-40 overflow-y-auto">
                  {selected.body_text}
                </div>

                {selected.status === "skipped" && (
                  <div className="rounded-lg border border-border bg-surface-muted/80 p-4 space-y-3">
                    <div className="flex items-start gap-2">
                      <Ban className="h-4 w-4 text-content-muted shrink-0 mt-0.5" />
                      <div>
                        <p className="text-sm font-medium text-content">Filtered — will not get a reply</p>
                        <p className="text-sm text-content-muted mt-1">
                          {selected.skip_reason ||
                            "This email was excluded by your reply filter settings."}
                        </p>
                        <p className="text-xs text-content-subtle mt-2">
                          App Manager will not draft or auto-send a response. You can still reply
                          manually if this was a mistake.
                        </p>
                      </div>
                    </div>
                    <Button
                      variant="outline"
                      onClick={() => replyAnyway(selected.id)}
                      disabled={!settings?.openai_configured || actionId === selected.id}
                    >
                      Reply anyway
                    </Button>
                  </div>
                )}

                {!selected.latest_reply && selected.status !== "skipped" && (
                  <Button
                    onClick={() => generateDraft(selected.id)}
                    disabled={!settings?.openai_configured || actionId === selected.id}
                  >
                    <Sparkles className="h-4 w-4 mr-2" />
                    Generate AI reply
                  </Button>
                )}

                {selected.latest_reply?.status === "draft" && (
                  <div className="space-y-3">
                    <label className="text-sm font-medium text-content">AI draft</label>
                    <textarea
                      className={textareaClass}
                      rows={8}
                      value={draftEdit}
                      onChange={(e) => setDraftEdit(e.target.value)}
                    />
                    <p className="text-xs text-content-subtle">
                      Model: {selected.latest_reply.model_used}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="outline"
                        onClick={() => saveDraftEdits(selected.latest_reply!.id)}
                        disabled={actionId === selected.latest_reply.id}
                      >
                        Save edits
                      </Button>
                      <Button
                        onClick={() => approveSend(selected.latest_reply!.id)}
                        disabled={actionId === selected.latest_reply.id}
                      >
                        <Send className="h-4 w-4 mr-2" />
                        Approve & send
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => rejectDraft(selected.latest_reply!.id)}
                        disabled={actionId === selected.latest_reply.id}
                      >
                        <X className="h-4 w-4 mr-2" />
                        Reject
                      </Button>
                    </div>
                  </div>
                )}

                {selected.latest_reply?.status === "sent" && (
                  <div className="flex items-center gap-2 text-sm text-green-600 dark:text-green-400">
                    <Check className="h-4 w-4" />
                    Reply sent via Gmail
                  </div>
                )}

                {selected.latest_reply &&
                  selected.latest_reply.status !== "draft" &&
                  selected.latest_reply.status !== "sent" && (
                    <p className="text-sm text-content-muted">
                      Reply status: {selected.latest_reply.status}
                    </p>
                  )}
              </div>
            ) : (
              <div className="p-8 text-center text-content-muted text-sm">
                Select an email or sync your inbox
              </div>
            )}
          </Card>
        </div>
      )}

      {tab === "settings" && settings && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6 max-w-2xl">
          <Card className="border-brand-500/20">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <KeyRound className="h-4 w-4 text-brand-600 dark:text-brand-400" />
                Your OpenAI API key
              </CardTitle>
              <CardDescription>
                Each account uses its own key. We store it encrypted (same security as Gmail tokens).
                It is only sent to OpenAI from the server when generating replies — never exposed in
                the app or API responses.
              </CardDescription>
            </CardHeader>
            <div className="px-6 pb-6 space-y-4">
              {settings.openai_key_is_user_owned && settings.openai_key_masked && (
                <div className="flex items-center justify-between rounded-lg bg-surface-muted px-3 py-2 text-sm">
                  <span className="text-content-muted">Saved key</span>
                  <span className="font-mono text-content">{settings.openai_key_masked}</span>
                </div>
              )}
              <div className="space-y-1.5">
                <label htmlFor="openai-api-key" className="block text-sm font-medium text-content">
                  {settings.openai_key_is_user_owned ? "Replace API key" : "API key"}
                </label>
                <input
                  id="openai-api-key"
                  type="password"
                  autoComplete="off"
                  spellCheck={false}
                  placeholder="sk-..."
                  value={openaiKeyInput}
                  onChange={(e) => setOpenaiKeyInput(e.target.value)}
                  className={cn(
                    "flex h-10 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm font-mono text-content",
                    "placeholder:text-content-subtle focus:outline-none focus:ring-2 focus:ring-brand-500/30 focus:border-brand-500"
                  )}
                />
                <p className="text-xs text-content-subtle">
                  Create a key at{" "}
                  <a
                    href="https://platform.openai.com/api-keys"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-brand-600 hover:underline"
                  >
                    platform.openai.com/api-keys
                  </a>
                  . You are billed directly by OpenAI.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button onClick={saveOpenaiKey} disabled={savingOpenaiKey || !openaiKeyInput.trim()}>
                  {savingOpenaiKey ? "Saving…" : settings.openai_key_is_user_owned ? "Update key" : "Save key"}
                </Button>
                {settings.openai_key_is_user_owned && (
                  <Button
                    variant="outline"
                    onClick={removeOpenaiKey}
                    disabled={savingOpenaiKey}
                  >
                    Remove key
                  </Button>
                )}
              </div>
            </div>
          </Card>

          <Card className="border-brand-500/20">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bot className="h-4 w-4 text-brand-600 dark:text-brand-400" />
                Autopilot
              </CardTitle>
              <CardDescription>
                Runs in the background while the App Manager backend is running. Fetches unread
                emails, applies your filters, generates replies, and sends them if auto-send is on.
              </CardDescription>
            </CardHeader>
            <div className="px-6 pb-6 space-y-4">
              <Switch
                checked={settings.automation_enabled}
                onChange={(v) => setSettings({ ...settings, automation_enabled: v })}
                label="Enable autopilot"
                description="Automatically check Gmail and respond on a schedule"
              />
              {settings.automation_enabled && (
                <div className="grid gap-4 sm:grid-cols-2 pl-1 border-l-2 border-brand-500/30 ml-1">
                  <div className="space-y-1.5">
                    <label className="block text-sm font-medium text-content">
                      Check every (minutes)
                    </label>
                    <select
                      className={textareaClass + " h-10 min-h-0"}
                      value={settings.automation_interval_minutes}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          automation_interval_minutes: Number(e.target.value),
                        })
                      }
                    >
                      {[5, 10, 15, 30, 60, 120].map((m) => (
                        <option key={m} value={m}>
                          {m} minutes
                        </option>
                      ))}
                    </select>
                  </div>
                  <Input
                    label="Max emails per run"
                    type="number"
                    min={1}
                    max={50}
                    value={String(settings.automation_max_emails_per_run)}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        automation_max_emails_per_run: Math.min(
                          50,
                          Math.max(1, parseInt(e.target.value, 10) || 10)
                        ),
                      })
                    }
                    hint="Unread messages processed each cycle"
                  />
                </div>
              )}
              {settings.automation_last_run_at && (
                <p className="text-xs text-content-muted">
                  Last autopilot run: {formatTime(settings.automation_last_run_at)}
                </p>
              )}
              {settings.automation_last_error && settings.automation_enabled && (
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  {settings.automation_last_error}
                </p>
              )}
              {settings.automation_last_error && !settings.automation_enabled && (
                <p className="text-sm text-red-600 dark:text-red-400 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2">
                  {settings.automation_last_error}
                </p>
              )}
              <Button
                variant="outline"
                disabled={runningAutomation || !settings.openai_configured || !connectedAccount}
                onClick={async () => {
                  setRunningAutomation(true);
                  setError("");
                  try {
                    const result = await api.aiEmailAssistant.runAutomation(activeStore?.id);
                    await Promise.all([loadInbox(), loadSettings(), loadLogs()]);
                    if (result.stopped && result.error) {
                      setError(result.error);
                    } else if (!result.ok && result.error) {
                      setError(result.error);
                    } else {
                      setError("");
                    }
                  } catch (err) {
                    setError(err instanceof Error ? err.message : "Autopilot run failed");
                    await loadSettings();
                  } finally {
                    setRunningAutomation(false);
                  }
                }}
              >
                <RefreshCw
                  className={cn("h-4 w-4 mr-2", runningAutomation && "animate-spin")}
                />
                {runningAutomation ? "Running…" : "Run now"}
              </Button>
            </div>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Reply mode</CardTitle>
              <CardDescription>
                With autopilot on: AI still drafts every customer email. Turn on auto-send to post
                replies to Gmail without your approval.
              </CardDescription>
            </CardHeader>
            <div className="px-6 pb-6 flex items-center justify-between">
              <div>
                <p className="font-medium text-content text-sm">Auto-send replies</p>
                <p className="text-xs text-content-muted">Send without manual approval</p>
              </div>
              <Switch
                checked={settings.auto_send_enabled}
                onChange={(v) => setSettings({ ...settings, auto_send_enabled: v })}
              />
            </div>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Duplicate reply prevention</CardTitle>
              <CardDescription>
                Stops sending multiple identical replies when Gmail has several unread messages in
                the same conversation. Enabled by default — recommended.
              </CardDescription>
            </CardHeader>
            <div className="px-6 pb-6 space-y-4">
              <Switch
                checked={settings.one_reply_per_thread}
                onChange={(v) => setSettings({ ...settings, one_reply_per_thread: v })}
                label="One reply per conversation"
                description="Only the first unread message in a thread gets a reply; others are skipped."
              />
              <Switch
                checked={settings.sync_only_customer_unread}
                onChange={(v) => setSettings({ ...settings, sync_only_customer_unread: v })}
                label="Only unread customer emails"
                description="Ignore unread messages sent from your own shop address."
              />
              <Switch
                checked={settings.verify_gmail_thread_before_reply}
                onChange={(v) => setSettings({ ...settings, verify_gmail_thread_before_reply: v })}
                label="Check Gmail before replying"
                description="Skip if your business already sent the latest message in the thread."
              />
            </div>
          </Card>

          <Card className="border-brand-500/20">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Filter className="h-4 w-4 text-brand-600 dark:text-brand-400" />
                Which emails get a reply?
              </CardTitle>
              <CardDescription>
                Not every inbox message needs an answer. Turn on the reply filter to skip
                automated mail, newsletters, and non-business messages so App Manager only drafts
                replies for real customer emails.
              </CardDescription>
            </CardHeader>
            <div className="px-6 pb-6 space-y-5">
              <Switch
                checked={settings.email_filter_enabled}
                onChange={(v) => setSettings({ ...settings, email_filter_enabled: v })}
                label="Smart reply filter"
                description="When on, filtered emails are marked “No reply” and never receive AI drafts or auto-send."
              />

              {settings.email_filter_enabled && (
                <div className="space-y-4 pl-1 border-l-2 border-brand-500/30 ml-1">
                  <Switch
                    checked={settings.filter_automated_emails}
                    onChange={(v) => setSettings({ ...settings, filter_automated_emails: v })}
                    label="Skip automated & system emails"
                    description="No-reply addresses, delivery notifications, password resets, out-of-office, platform alerts."
                  />
                  <Switch
                    checked={settings.filter_non_business_emails}
                    onChange={(v) => setSettings({ ...settings, filter_non_business_emails: v })}
                    label="Skip non-business emails"
                    description="Personal mail, spam, or messages unrelated to your store (uses AI classification on sync)."
                  />
                  <div className="space-y-1.5">
                    <label className="block text-sm font-medium text-content">
                      Custom emails to ignore
                    </label>
                    <p className="text-xs text-content-muted mb-1">
                      Optional. One rule per line — e.g. “Ignore supplier invoices”, “Skip job
                      applications”.
                    </p>
                    <textarea
                      className={textareaClass}
                      rows={3}
                      placeholder={"Ignore emails about wholesale partnerships\nDo not reply to influencer outreach"}
                      value={settings.filter_custom_rules}
                      onChange={(e) =>
                        setSettings({ ...settings, filter_custom_rules: e.target.value })
                      }
                    />
                  </div>
                </div>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Business context</CardTitle>
              <CardDescription>
                Injected into every AI prompt so replies match your brand and policies. The assistant
                also reads the full Gmail thread (not just the latest line) for better context.
              </CardDescription>
            </CardHeader>
            <div className="px-6 pb-6 space-y-4">
              <Switch
                checked={settings.use_thread_context}
                onChange={(v) => setSettings({ ...settings, use_thread_context: v })}
                label="Use full conversation thread"
                description="Recommended. Helps with short messages like “thank you” after an order or support issue."
              />
              <Input
                label="Business name"
                value={settings.business_name}
                onChange={(e) => setSettings({ ...settings, business_name: e.target.value })}
              />
              <Input
                label="Business type"
                hint="e.g. e-commerce, SaaS, services"
                value={settings.business_type}
                onChange={(e) => setSettings({ ...settings, business_type: e.target.value })}
              />
              <Input
                label="Tone of voice"
                hint="e.g. formal, friendly, luxury, brief"
                value={settings.tone_of_voice}
                onChange={(e) => setSettings({ ...settings, tone_of_voice: e.target.value })}
              />
              <div className="space-y-1.5">
                <label className="block text-sm font-medium text-content">Rules</label>
                <textarea
                  className={textareaClass}
                  rows={3}
                  placeholder="Always be polite. Never promise refunds without manager approval."
                  value={settings.rules}
                  onChange={(e) => setSettings({ ...settings, rules: e.target.value })}
                />
              </div>
              <div className="space-y-1.5">
                <label className="block text-sm font-medium text-content">Key policies</label>
                <textarea
                  className={textareaClass}
                  rows={4}
                  placeholder="Shipping: 3–5 business days. Refunds within 14 days..."
                  value={settings.policies}
                  onChange={(e) => setSettings({ ...settings, policies: e.target.value })}
                />
              </div>
              <div className="space-y-1.5">
                <label className="block text-sm font-medium text-content">FAQ knowledge base</label>
                <textarea
                  className={textareaClass}
                  rows={4}
                  placeholder="Q: How do I track my order? A: ..."
                  value={settings.faq}
                  onChange={(e) => setSettings({ ...settings, faq: e.target.value })}
                />
              </div>
              {accounts.length > 0 && (
                <div className="space-y-1.5">
                  <label className="block text-sm font-medium text-content">Gmail account</label>
                  <select
                    className={textareaClass + " h-10 min-h-0"}
                    value={settings.gmail_account_id ?? ""}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        gmail_account_id: e.target.value || null,
                      })
                    }
                  >
                    <option value="">Select account</option>
                    {accounts
                      .filter((a) => a.status === "connected")
                      .map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.email}
                        </option>
                      ))}
                  </select>
                </div>
              )}
              <Input
                label="OpenAI model (optional override)"
                hint={`Server default: ${settings.default_model}`}
                value={settings.openai_model ?? ""}
                onChange={(e) =>
                  setSettings({ ...settings, openai_model: e.target.value || null })
                }
              />
              <Button onClick={saveSettings} disabled={savingSettings}>
                {savingSettings ? "Saving…" : "Save settings"}
              </Button>
            </div>
          </Card>
        </motion.div>
      )}

      {tab === "logs" && (
        <Card>
          <CardHeader>
            <CardTitle>AI audit log</CardTitle>
            <CardDescription>All generated replies for debugging and compliance.</CardDescription>
          </CardHeader>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-content-muted">
                  <th className="px-4 py-2 font-medium">When</th>
                  <th className="px-4 py-2 font-medium">To</th>
                  <th className="px-4 py-2 font-medium">Subject</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Model</th>
                  <th className="px-4 py-2 font-medium">Preview</th>
                </tr>
              </thead>
              <tbody>
                {logs.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-content-muted">
                      No AI replies yet
                    </td>
                  </tr>
                )}
                {logs.map((log) => (
                  <tr key={log.id} className="border-b border-border/50">
                    <td className="px-4 py-2 whitespace-nowrap">{formatTime(log.created_at)}</td>
                    <td className="px-4 py-2">{log.sender_email}</td>
                    <td className="px-4 py-2 max-w-[160px] truncate">{log.subject}</td>
                    <td className="px-4 py-2">
                      <Badge variant={statusBadge(log.status)}>{log.status}</Badge>
                    </td>
                    <td className="px-4 py-2 text-xs">{log.model_used}</td>
                    <td className="px-4 py-2 max-w-xs truncate text-content-muted">
                      {log.body_preview}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
