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
  Building2,
  CheckCircle2,
  ArrowLeft,
  BarChart3,
  Clock,
  Users,
  ShieldCheck,
  TrendingUp,
  Eye,
  MessageSquare,
  UserRound,
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

type Tab = "inbox" | "stats" | "business" | "settings" | "logs";
type InboxFilter = "all" | "needs_reply" | "drafts" | "replied" | "filtered";

type PeriodStats = {
  emails_received: number;
  replies_sent: number;
  drafts_pending: number;
  filtered: number;
  failed: number;
  awaiting_reply: number;
};

type AssistantStats = {
  all_time: PeriodStats;
  today: PeriodStats;
  last_7_days: PeriodStats;
  last_30_days: PeriodStats;
  filter_breakdown: Array<{ name: string; count: number }>;
  intent_breakdown: Array<{ name: string; count: number }>;
  unique_customers_helped: number;
  minutes_saved_estimate: number;
  hours_saved_estimate: number;
  filter_efficiency_pct: number;
  reply_rate_pct: number;
  autopilot_enabled: boolean;
  auto_send_enabled: boolean;
  automation_last_run_at: string | null;
  openai_configured: boolean;
  gmail_connected: boolean;
};

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

type ThreadMessage = {
  message_id: string;
  from_header: string;
  body_text: string;
  is_from_business: boolean;
  sent_at: string | null;
  snippet: string;
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
  { id: "stats", label: "Stats", icon: BarChart3 },
  { id: "business", label: "Business", icon: Building2 },
  { id: "settings", label: "Settings", icon: Settings2 },
  { id: "logs", label: "Activity", icon: ScrollText },
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

function formatRelativeTime(iso: string) {
  try {
    const date = new Date(iso);
    const diffMs = Date.now() - date.getTime();
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return "Just now";
    if (mins < 60) return `${mins}m`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h`;
    const days = Math.floor(hours / 24);
    if (days < 7) return `${days}d`;
    return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}

function displayName(sender: string, email: string) {
  const name = sender.replace(/<[^>]+>/g, "").trim();
  if (name && name.toLowerCase() !== email.toLowerCase()) return name;
  return email.split("@")[0] || email || "Customer";
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return (parts[0]?.slice(0, 2) || "?").toUpperCase();
}

function previewSnippet(body: string, max = 90) {
  const cleaned = body.replace(/\s+/g, " ").trim();
  if (!cleaned) return "No preview";
  return cleaned.length > max ? `${cleaned.slice(0, max)}…` : cleaned;
}

function parseFromName(fromHeader: string) {
  const name = fromHeader.replace(/<[^>]+>/g, "").replace(/"/g, "").trim();
  return name || fromHeader || "Unknown";
}

function isDraftMessage(messageId: string) {
  return messageId.startsWith("draft:");
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

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    new: "Needs reply",
    draft_pending: "Draft ready",
    draft: "Draft",
    replied: "Replied",
    sent: "Sent",
    skipped: "No reply",
    failed: "Failed",
    rejected: "Rejected",
    processed: "Done",
  };
  return labels[status] ?? status;
}

function effectiveStatus(item: InboxItem) {
  if (item.status === "draft_pending" && item.latest_reply?.status === "draft") return "draft";
  return item.status;
}

function matchesInboxFilter(item: InboxItem, filter: InboxFilter) {
  if (filter === "all") return true;
  if (filter === "needs_reply") return item.status === "new";
  if (filter === "drafts") return item.status === "draft_pending" || item.latest_reply?.status === "draft";
  if (filter === "replied") return item.status === "replied" || item.latest_reply?.status === "sent";
  if (filter === "filtered") return item.status === "skipped";
  return true;
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
    already_resolved: "Already answered",
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
  const [stats, setStats] = useState<AssistantStats | null>(null);
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
  const [settingsSaved, setSettingsSaved] = useState(false);
  const [confirmFullScanOpen, setConfirmFullScanOpen] = useState(false);
  const [scanResultMessage, setScanResultMessage] = useState("");
  const [inboxFilter, setInboxFilter] = useState<InboxFilter>("all");
  const [threadMessages, setThreadMessages] = useState<ThreadMessage[]>([]);
  const [assistantNote, setAssistantNote] = useState<string | null>(null);
  const [threadLoading, setThreadLoading] = useState(false);

  const selected = selectedId ? inbox.find((e) => e.id === selectedId) ?? null : null;
  const filteredInbox = inbox.filter((item) => matchesInboxFilter(item, inboxFilter));
  const filterCounts: Record<InboxFilter, number> = {
    all: inbox.length,
    needs_reply: inbox.filter((i) => i.status === "new").length,
    drafts: inbox.filter((i) => i.status === "draft_pending" || i.latest_reply?.status === "draft").length,
    replied: inbox.filter((i) => i.status === "replied" || i.latest_reply?.status === "sent").length,
    filtered: inbox.filter((i) => i.status === "skipped").length,
  };

  const loadAccounts = useCallback(async () => {
    if (!activeStore?.id) {
      setAccounts([]);
      return [];
    }
    const data = await api.gmail.accounts(activeStore.id);
    setAccounts(data as GmailAccount[]);
    return data as GmailAccount[];
  }, [activeStore?.id]);

  const loadInbox = useCallback(async () => {
    if (!activeStore?.id) {
      setInbox([]);
      return;
    }
    const data = await api.aiEmailAssistant.inbox(activeStore.id);
    setInbox(data as InboxItem[]);
    setSelectedId((prev) => prev ?? (data as InboxItem[])[0]?.id ?? null);
  }, [activeStore?.id]);

  const loadThread = useCallback(async (emailId: string) => {
    setThreadLoading(true);
    try {
      const thread = await api.aiEmailAssistant.inboxThread(emailId);
      setThreadMessages(thread.messages as ThreadMessage[]);
      setAssistantNote(thread.assistant_note);
      // Keep list row in sync if thread payload has fresher email state
      if (thread.inbox_email) {
        setInbox((prev) =>
          prev.map((item) =>
            item.id === thread.inbox_email.id
              ? {
                  ...item,
                  status: thread.inbox_email.status,
                  skip_reason: thread.inbox_email.skip_reason,
                  filter_category: thread.inbox_email.filter_category,
                  detected_intent: thread.inbox_email.detected_intent,
                  latest_reply: thread.inbox_email.latest_reply
                    ? {
                        id: thread.inbox_email.latest_reply.id,
                        effective_body: thread.inbox_email.latest_reply.effective_body,
                        status: thread.inbox_email.latest_reply.status,
                        model_used: thread.inbox_email.latest_reply.model_used,
                      }
                    : null,
                }
              : item
          )
        );
      }
    } catch {
      setThreadMessages([]);
      setAssistantNote(null);
    } finally {
      setThreadLoading(false);
    }
  }, []);

  const loadSettings = useCallback(async () => {
    if (!activeStore?.id) {
      setSettings(null);
      return;
    }
    const s = await api.aiEmailAssistant.settings(activeStore.id);
    setSettings(s as Settings);
  }, [activeStore?.id]);

  const loadLogs = useCallback(async () => {
    if (!activeStore?.id) {
      setLogs([]);
      return;
    }
    const l = await api.aiEmailAssistant.logs(activeStore.id);
    setLogs(l as LogEntry[]);
  }, [activeStore?.id]);

  const loadStats = useCallback(async () => {
    if (!activeStore?.id) {
      setStats(null);
      return;
    }
    const s = await api.aiEmailAssistant.stats(activeStore.id);
    setStats(s as AssistantStats);
  }, [activeStore?.id]);

  const loadAll = useCallback(async () => {
    if (!activeStore?.id) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      await loadAccounts();
      await Promise.all([loadInbox(), loadSettings(), loadLogs(), loadStats()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load AI Email Assistant");
    } finally {
      setLoading(false);
    }
  }, [activeStore?.id, loadAccounts, loadInbox, loadSettings, loadLogs, loadStats]);

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

  useEffect(() => {
    if (!selectedId) {
      setThreadMessages([]);
      setAssistantNote(null);
      return;
    }
    loadThread(selectedId);
  }, [selectedId, loadThread]);

  const connectedAccount =
    accounts.find((a) => a.status === "connected" && a.id === settings?.gmail_account_id) ??
    accounts.find((a) => a.status === "connected");

  const syncInbox = async () => {
    const accId = settings?.gmail_account_id ?? connectedAccount?.id;
    if (!accId) {
      setError("Connect Gmail in Settings first.");
      setTab("settings");
      return;
    }
    setConfirmFullScanOpen(true);
  };

  const runFullHistoryScan = async () => {
    const storeId = activeStore?.id;
    const accId = settings?.gmail_account_id ?? connectedAccount?.id;
    if (!storeId || !accId) return;
    setConfirmFullScanOpen(false);
    setSyncing(true);
    setError("");
    setScanResultMessage("Starting full inbox check…");
    try {
      await api.aiEmailAssistant.fullHistoryScan(accId, 100, storeId);

      // Poll status — scan runs in the background to avoid gateway timeouts.
      const started = Date.now();
      const maxWaitMs = 30 * 60 * 1000;
      while (Date.now() - started < maxWaitMs) {
        await new Promise((r) => setTimeout(r, 2000));
        const status = await api.aiEmailAssistant.fullHistoryScanStatus(storeId);
        if (status.message) {
          setScanResultMessage(
            status.status === "running" && status.total
              ? `${status.message} (${status.progress}/${status.total})`
              : status.message
          );
        }
        if (status.status === "completed") {
          if (status.inbox?.length) {
            setInbox(status.inbox as InboxItem[]);
            setSelectedId((status.inbox as InboxItem[])[0].id);
          } else {
            await loadInbox();
          }
          setScanResultMessage(status.message);
          await Promise.all([loadLogs(), loadStats()]);
          return;
        }
        if (status.status === "failed") {
          throw new Error(status.message || "Full inbox check failed");
        }
      }
      throw new Error("Full inbox check is still running. Refresh later to see results.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Full inbox check failed");
    } finally {
      setSyncing(false);
    }
  };

  const replyAnyway = async (emailId: string) => {
    const storeId = activeStore?.id;
    if (!storeId) {
      setError("Select a store first.");
      return;
    }
    setActionId(emailId);
    setError("");
    try {
      await api.aiEmailAssistant.unskipEmail(emailId);
      const reply = await api.aiEmailAssistant.generateReply(emailId, storeId);
      setDraftEdit(reply.effective_body);
      await loadInbox();
      await loadThread(emailId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not enable reply for this email");
    } finally {
      setActionId(null);
    }
  };

  const generateDraft = async (emailId: string) => {
    const storeId = activeStore?.id;
    if (!storeId) {
      setError("Select a store first.");
      return;
    }
    setActionId(emailId);
    setError("");
    try {
      const reply = await api.aiEmailAssistant.generateReply(emailId, storeId);
      setDraftEdit(reply.effective_body);
      await loadInbox();
      await loadThread(emailId);
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
      if (selectedId) await loadThread(selectedId);
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
      await Promise.all([loadInbox(), loadLogs(), loadStats()]);
      if (selectedId) await loadThread(selectedId);
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
      if (selectedId) await loadThread(selectedId);
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
    const storeId = activeStore?.id;
    if (!storeId) {
      setError("Select a store first.");
      return;
    }
    setSavingSettings(true);
    setSettingsSaved(false);
    setError("");
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
        storeId
      );
      await loadSettings();
      setSettingsSaved(true);
      window.setTimeout(() => setSettingsSaved(false), 2500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save settings");
    } finally {
      setSavingSettings(false);
    }
  };

  const runAutomationNow = async () => {
    const storeId = activeStore?.id;
    if (!storeId) {
      setError("Select a store first.");
      return;
    }
    setRunningAutomation(true);
    setError("");
    try {
      const result = await api.aiEmailAssistant.runAutomation(storeId);
      await Promise.all([loadInbox(), loadSettings(), loadLogs(), loadStats()]);
      if (result.stopped && result.error) {
        setError(result.error);
      } else if (!result.ok && result.error) {
        setError(result.error);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Autopilot run failed");
      await loadSettings();
    } finally {
      setRunningAutomation(false);
    }
  };

  const textareaClass = cn(
    "flex min-h-[100px] w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-content",
    "placeholder:text-content-subtle focus:outline-none focus:ring-2 focus:ring-brand-500/30 focus:border-brand-500"
  );

  const selectClass = cn(textareaClass, "h-10 min-h-0");

  const needsSetup =
    settings && (!settings.openai_configured || !connectedAccount);

  const setupSteps = settings
    ? [
        {
          done: Boolean(connectedAccount),
          label: "Connect Gmail to this store",
          action: () => setTab("settings"),
        },
        {
          done: settings.openai_configured,
          label: "Add OpenAI API key",
          action: () => setTab("settings"),
        },
        {
          done: Boolean(settings.business_name.trim()),
          label: "Describe your business",
          action: () => setTab("business"),
        },
      ]
    : [];

  if (!activeStore) {
    return (
      <div className="max-w-2xl mx-auto">
        <Card padding="lg">
          <CardTitle>Select a store</CardTitle>
          <CardDescription className="mt-2">
            AI Email Assistant is per store — each store can use its own Gmail inbox and
            business rules. Choose a store from the sidebar, or{" "}
            <Link to="/settings/stores" className="text-brand-600 hover:underline">
              connect your Shopify store
            </Link>
            .
          </CardDescription>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-content tracking-tight">AI Email Assistant</h1>
          <p className="text-content-muted mt-1 max-w-xl text-sm leading-relaxed">
            Read customer emails for{" "}
            <strong className="text-content">{activeStore.name}</strong>, draft replies in
            your brand voice, and send through this store&apos;s Gmail — manually or on
            autopilot.
          </p>
          {settings && (
            <div className="flex flex-wrap gap-2 mt-3">
              <Badge variant={settings.automation_enabled ? "success" : "muted"}>
                {settings.automation_enabled ? "Autopilot on" : "Autopilot off"}
              </Badge>
              <Badge variant={settings.openai_configured ? "success" : "warning"}>
                {settings.openai_configured ? "API key ready" : "API key needed"}
              </Badge>
              {connectedAccount && (
                <Badge variant="default">{connectedAccount.email}</Badge>
              )}
            </div>
          )}
        </div>
        <div className="flex flex-wrap gap-2 shrink-0">
          <Button variant="outline" onClick={loadAll} disabled={loading}>
            <RefreshCw className={cn("h-4 w-4 mr-2", loading && "animate-spin")} />
            Refresh
          </Button>
          {tab === "inbox" && (
            <Button onClick={syncInbox} disabled={syncing || !connectedAccount}>
              <Mail className="h-4 w-4 mr-2" />
              {syncing ? "Scanning history…" : "Check inbox"}
            </Button>
          )}
        </div>
      </div>

      {confirmFullScanOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <Card className="max-w-lg w-full shadow-lg">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-amber-700 dark:text-amber-400">
                <AlertCircle className="h-5 w-5 shrink-0" />
                Full inbox history check
              </CardTitle>
              <CardDescription className="text-content-muted leading-relaxed pt-1">
                This will scan your Gmail <strong className="text-content">from the beginning</strong>{" "}
                (up to 100 conversations), not only recent unread mail.
              </CardDescription>
            </CardHeader>
            <ul className="px-6 space-y-2 text-sm text-content-muted pb-4">
              <li>
                · Reads the <strong className="text-content">full conversation history</strong> with
                each customer (your team + the client).
              </li>
              <li>
                · Only acts when the <strong className="text-content">customer wrote last</strong> —
                if your team already sent the latest message, it skips.
              </li>
              <li>
                · If a client was <strong className="text-content">never answered</strong> by your
                team, the assistant will draft or send a reply.
              </li>
              <li>
                · Uses OpenAI for each conversation — this can take several minutes and use API
                credits. The scan runs in the background so it won&apos;t time out.
              </li>
            </ul>
            <div className="px-6 pb-5 flex flex-wrap gap-2 justify-end">
              <Button variant="outline" onClick={() => setConfirmFullScanOpen(false)}>
                Cancel
              </Button>
              <Button onClick={runFullHistoryScan}>
                I understand — scan everything
              </Button>
            </div>
          </Card>
        </div>
      )}

      {scanResultMessage && (
        <p className="text-sm text-content bg-brand-500/10 border border-brand-500/20 rounded-lg px-3 py-2">
          {scanResultMessage}
        </p>
      )}

      {needsSetup && (
        <Card className="border-amber-500/30 bg-amber-500/5">
          <CardHeader className="mb-3">
            <CardTitle className="text-base">Finish setup</CardTitle>
            <CardDescription>
              Complete these steps once, then you can sync and reply from the Inbox.
            </CardDescription>
          </CardHeader>
          <ul className="px-5 pb-5 space-y-2">
            {setupSteps.map((step) => (
              <li key={step.label}>
                <button
                  type="button"
                  onClick={step.action}
                  className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm hover:bg-surface transition-colors"
                >
                  {step.done ? (
                    <CheckCircle2 className="h-4 w-4 text-green-600 shrink-0" />
                  ) : (
                    <span className="h-4 w-4 rounded-full border-2 border-amber-500/60 shrink-0" />
                  )}
                  <span
                    className={cn(
                      step.done ? "text-content-muted line-through" : "text-content font-medium"
                    )}
                  >
                    {step.label}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {settings?.automation_last_error && !settings.automation_enabled && (
        <Card className="border-red-500/40 bg-red-500/10">
          <CardHeader className="pb-2 mb-2">
            <CardTitle className="text-base flex items-center gap-2 text-red-700 dark:text-red-400">
              <AlertCircle className="h-4 w-4 shrink-0" />
              Autopilot stopped
            </CardTitle>
            <CardDescription className="text-red-800/90 dark:text-red-300/90">
              {settings.automation_last_error}
            </CardDescription>
          </CardHeader>
          <div className="px-5 pb-4">
            <Button variant="outline" onClick={() => setTab("settings")}>
              Open Settings
            </Button>
          </div>
        </Card>
      )}

      {error && (
        <p className="text-sm text-red-500 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      <div className="flex gap-1 border-b border-border overflow-x-auto">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors whitespace-nowrap",
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
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            {(
              [
                { id: "all", label: "All" },
                { id: "needs_reply", label: "Needs reply" },
                { id: "drafts", label: "Drafts" },
                { id: "replied", label: "Replied" },
                { id: "filtered", label: "Filtered" },
              ] as const
            ).map(({ id, label }) => (
              <button
                key={id}
                type="button"
                onClick={() => setInboxFilter(id)}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                  inboxFilter === id
                    ? "border-brand-500 bg-brand-500/10 text-brand-700 dark:text-brand-400"
                    : "border-border text-content-muted hover:text-content hover:bg-surface-muted"
                )}
              >
                {label}
                <span className="text-content-subtle tabular-nums">{filterCounts[id]}</span>
              </button>
            ))}
          </div>

          <div className="grid gap-4 lg:grid-cols-5 min-h-[min(640px,72vh)]">
            <Card
              className={cn(
                "lg:col-span-2 p-0 overflow-hidden flex flex-col",
                selected && "hidden lg:flex"
              )}
              padding="none"
            >
              <div className="border-b border-border px-4 py-3 flex items-center justify-between shrink-0">
                <div>
                  <span className="text-sm font-medium text-content">Mailbox</span>
                  <p className="text-xs text-content-muted mt-0.5">
                    Conversations your assistant is watching
                  </p>
                </div>
                <Badge variant="muted">{filteredInbox.length}</Badge>
              </div>
              <ul className="flex-1 overflow-y-auto divide-y divide-border max-h-[min(640px,72vh)]">
                {filteredInbox.length === 0 && (
                  <li className="px-4 py-10 text-sm text-content-muted text-center space-y-3">
                    <p>{inbox.length === 0 ? "No conversations yet." : "Nothing in this view."}</p>
                    <p className="text-xs">
                      {inbox.length === 0
                        ? connectedAccount
                          ? 'Click "Check inbox" to scan full Gmail history (you will confirm first).'
                          : "Connect Gmail in Settings to get started."
                        : "Try another filter to see more conversations."}
                    </p>
                  </li>
                )}
                {filteredInbox.map((item) => {
                  const name = displayName(item.sender, item.sender_email);
                  const st = effectiveStatus(item);
                  const needsAttention = item.status === "new" || item.status === "draft_pending";
                  return (
                    <li key={item.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedId(item.id)}
                        className={cn(
                          "w-full text-left px-4 py-3.5 hover:bg-surface-muted transition-colors flex gap-3",
                          selected?.id === item.id && "bg-brand-500/10"
                        )}
                      >
                        <div
                          className={cn(
                            "h-10 w-10 rounded-full flex items-center justify-center text-xs font-semibold shrink-0",
                            needsAttention
                              ? "bg-brand-500/15 text-brand-700 dark:text-brand-400"
                              : "bg-surface-muted text-content-muted"
                          )}
                        >
                          {initials(name)}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-baseline justify-between gap-2">
                            <p
                              className={cn(
                                "text-sm truncate",
                                needsAttention ? "font-semibold text-content" : "font-medium text-content"
                              )}
                            >
                              {name}
                            </p>
                            <span className="text-[11px] text-content-subtle shrink-0 tabular-nums">
                              {formatRelativeTime(item.received_at)}
                            </span>
                          </div>
                          <p
                            className={cn(
                              "text-sm truncate mt-0.5",
                              needsAttention ? "font-medium text-content" : "text-content"
                            )}
                          >
                            {item.subject || "(no subject)"}
                          </p>
                          <p className="text-xs text-content-muted truncate mt-0.5">
                            {previewSnippet(item.body_text)}
                          </p>
                          <div className="flex flex-wrap gap-1.5 mt-2">
                            <Badge variant={statusBadge(st)}>{statusLabel(st)}</Badge>
                            {item.filter_category && item.status === "skipped" && (
                              <Badge variant="muted">{filterCategoryLabel(item.filter_category)}</Badge>
                            )}
                            {item.detected_intent && item.status !== "skipped" && (
                              <Badge variant="default">{intentLabel(item.detected_intent)}</Badge>
                            )}
                          </div>
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </Card>

            <Card
              className={cn(
                "lg:col-span-3 p-0 overflow-hidden flex flex-col",
                !selected && "hidden lg:flex"
              )}
              padding="none"
            >
              {selected ? (
                <>
                  <div className="border-b border-border px-4 sm:px-5 py-4 shrink-0 space-y-3">
                    <button
                      type="button"
                      onClick={() => setSelectedId(null)}
                      className="inline-flex items-center gap-1.5 text-sm text-content-muted hover:text-content lg:hidden"
                    >
                      <ArrowLeft className="h-4 w-4" />
                      Back to mailbox
                    </button>
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h2 className="font-semibold text-content text-lg leading-snug">
                          {selected.subject || "(no subject)"}
                        </h2>
                        <p className="text-sm text-content-muted mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
                          <span className="inline-flex items-center gap-1.5">
                            <UserRound className="h-3.5 w-3.5" />
                            {displayName(selected.sender, selected.sender_email)}
                          </span>
                          <span className="text-content-subtle">&lt;{selected.sender_email}&gt;</span>
                        </p>
                      </div>
                      <Badge variant={statusBadge(effectiveStatus(selected))}>
                        {statusLabel(effectiveStatus(selected))}
                      </Badge>
                    </div>
                    {(assistantNote || selected.status === "skipped") && (
                      <div
                        className={cn(
                          "rounded-lg px-3 py-2.5 text-sm flex items-start gap-2",
                          selected.status === "skipped"
                            ? "bg-surface-muted border border-border text-content-muted"
                            : selected.status === "draft_pending"
                              ? "bg-brand-500/10 border border-brand-500/20 text-content"
                              : "bg-surface-muted/80 border border-border text-content-muted"
                        )}
                      >
                        {selected.status === "skipped" ? (
                          <Ban className="h-4 w-4 shrink-0 mt-0.5" />
                        ) : (
                          <Eye className="h-4 w-4 shrink-0 mt-0.5 text-brand-600 dark:text-brand-400" />
                        )}
                        <div>
                          <p className="font-medium text-content text-xs uppercase tracking-wide mb-0.5">
                            Assistant
                          </p>
                          <p className="leading-relaxed">
                            {assistantNote ||
                              selected.skip_reason ||
                              "Monitoring this conversation."}
                          </p>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="flex-1 overflow-y-auto px-4 sm:px-5 py-4 space-y-4 max-h-[min(420px,48vh)] bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-surface-muted/40 via-transparent to-transparent">
                    {threadLoading && (
                      <p className="text-sm text-content-muted text-center py-8">
                        Loading conversation…
                      </p>
                    )}
                    {!threadLoading && threadMessages.length === 0 && (
                      <div className="rounded-lg bg-surface-muted p-4 text-sm text-content whitespace-pre-wrap leading-relaxed">
                        {selected.body_text || "No message body."}
                      </div>
                    )}
                    {!threadLoading &&
                      threadMessages.map((msg) => {
                        const draft = isDraftMessage(msg.message_id);
                        const fromName = parseFromName(msg.from_header);
                        return (
                          <div
                            key={msg.message_id}
                            className={cn(
                              "flex gap-2.5",
                              msg.is_from_business ? "flex-row-reverse" : "flex-row"
                            )}
                          >
                            <div
                              className={cn(
                                "h-8 w-8 rounded-full flex items-center justify-center text-[10px] font-semibold shrink-0 mt-1",
                                msg.is_from_business
                                  ? draft
                                    ? "bg-brand-500/20 text-brand-700 dark:text-brand-400"
                                    : "bg-content/10 text-content"
                                  : "bg-surface-muted text-content-muted"
                              )}
                            >
                              {msg.is_from_business ? (
                                draft ? (
                                  <Bot className="h-3.5 w-3.5" />
                                ) : (
                                  initials(fromName)
                                )
                              ) : (
                                initials(fromName)
                              )}
                            </div>
                            <div
                              className={cn(
                                "max-w-[min(100%,28rem)] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
                                msg.is_from_business
                                  ? draft
                                    ? "bg-brand-500/10 border border-dashed border-brand-500/40 text-content rounded-tr-md"
                                    : "bg-brand-500 text-white rounded-tr-md"
                                  : "bg-surface-muted text-content border border-border rounded-tl-md"
                              )}
                            >
                              <div
                                className={cn(
                                  "flex items-center justify-between gap-3 mb-1 text-[11px]",
                                  msg.is_from_business && !draft
                                    ? "text-white/80"
                                    : "text-content-muted"
                                )}
                              >
                                <span className="font-medium truncate">
                                  {draft ? "AI Assistant · draft" : fromName}
                                </span>
                                {msg.sent_at && (
                                  <span className="shrink-0 tabular-nums">
                                    {formatTime(msg.sent_at)}
                                  </span>
                                )}
                                {draft && (
                                  <span className="shrink-0 text-brand-700 dark:text-brand-400">
                                    Not sent
                                  </span>
                                )}
                              </div>
                              <p className="whitespace-pre-wrap">{msg.body_text || msg.snippet}</p>
                            </div>
                          </div>
                        );
                      })}
                  </div>

                  <div className="border-t border-border px-4 sm:px-5 py-4 shrink-0 space-y-3 bg-surface">
                    <div className="flex items-center gap-2 text-xs font-medium text-content-muted uppercase tracking-wide">
                      <Bot className="h-3.5 w-3.5" />
                      Assistant desk
                      <span className="font-normal normal-case tracking-normal text-content-subtle">
                        — review what it wrote before it goes out
                      </span>
                    </div>

                    {selected.status === "skipped" && (
                      <div className="space-y-3">
                        <p className="text-sm text-content-muted">
                          {selected.skip_reason ||
                            "The assistant decided a reply was not needed and left this as read."}
                        </p>
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
                        {actionId === selected.id ? "Writing…" : "Write AI reply"}
                      </Button>
                    )}

                    {selected.latest_reply?.status === "draft" && (
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <label className="text-sm font-medium text-content">Draft reply</label>
                          <span className="text-xs text-content-subtle">
                            {selected.latest_reply.model_used}
                          </span>
                        </div>
                        <textarea
                          className={textareaClass}
                          rows={6}
                          value={draftEdit}
                          onChange={(e) => setDraftEdit(e.target.value)}
                        />
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
                            Send
                          </Button>
                          <Button
                            variant="outline"
                            onClick={() => rejectDraft(selected.latest_reply!.id)}
                            disabled={actionId === selected.latest_reply.id}
                          >
                            <X className="h-4 w-4 mr-2" />
                            Discard
                          </Button>
                        </div>
                      </div>
                    )}

                    {selected.latest_reply?.status === "sent" && (
                      <div className="flex items-center gap-2 text-sm text-green-600 dark:text-green-400 rounded-lg bg-green-500/10 px-3 py-2">
                        <Check className="h-4 w-4" />
                        Reply sent via Gmail — conversation above is the live thread
                      </div>
                    )}

                    {selected.latest_reply &&
                      selected.latest_reply.status !== "draft" &&
                      selected.latest_reply.status !== "sent" && (
                        <p className="text-sm text-content-muted">
                          Status: {statusLabel(selected.latest_reply.status)}
                        </p>
                      )}
                  </div>
                </>
              ) : (
                <div className="flex-1 flex flex-col items-center justify-center p-12 text-center text-content-muted text-sm gap-3">
                  <MessageSquare className="h-8 w-8 text-content-subtle" />
                  <p>Select a conversation to watch the assistant handle it.</p>
                  <p className="text-xs max-w-sm">
                    You’ll see the full client thread, what the AI decided, and any draft waiting for
                    your approval.
                  </p>
                </div>
              )}
            </Card>
          </div>
        </div>
      )}

      {tab === "stats" && (
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h2 className="text-lg font-semibold text-content">Assistant impact</h2>
              <p className="text-sm text-content-muted mt-1 max-w-2xl leading-relaxed">
                See how much inbox work the AI handles for you — replies sent, noise filtered, and
                time saved so you can focus on growing the store.
              </p>
            </div>
            <Button variant="outline" onClick={loadStats} disabled={loading}>
              <RefreshCw className={cn("h-4 w-4 mr-2", loading && "animate-spin")} />
              Refresh stats
            </Button>
          </div>

          {!stats ? (
            <Card className="p-10 text-center text-sm text-content-muted">
              Loading stats…
            </Card>
          ) : (
            <>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {[
                  {
                    label: "Replies sent",
                    value: stats.all_time.replies_sent,
                    hint: `${stats.today.replies_sent} today · ${stats.last_7_days.replies_sent} this week`,
                    icon: Send,
                  },
                  {
                    label: "Noise filtered",
                    value: stats.all_time.filtered,
                    hint: `${stats.filter_efficiency_pct}% of inbox skipped as non-actionable`,
                    icon: ShieldCheck,
                  },
                  {
                    label: "Time saved",
                    value:
                      stats.hours_saved_estimate >= 1
                        ? `${stats.hours_saved_estimate}h`
                        : `${stats.minutes_saved_estimate}m`,
                    hint: `~5 min per reply × ${stats.all_time.replies_sent} sent`,
                    icon: Clock,
                  },
                  {
                    label: "Customers helped",
                    value: stats.unique_customers_helped,
                    hint: `${stats.reply_rate_pct}% of received mail got a reply`,
                    icon: Users,
                  },
                ].map(({ label, value, hint, icon: Icon }) => (
                  <Card key={label} className="p-4">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-xs font-medium uppercase tracking-wide text-content-subtle">
                        {label}
                      </p>
                      <Icon className="h-4 w-4 text-brand-600 dark:text-brand-400 shrink-0" />
                    </div>
                    <p className="mt-2 text-3xl font-semibold tabular-nums text-content">{value}</p>
                    <p className="mt-1 text-xs text-content-muted leading-snug">{hint}</p>
                  </Card>
                ))}
              </div>

              <div className="grid gap-4 lg:grid-cols-3">
                {(
                  [
                    ["Today", stats.today],
                    ["Last 7 days", stats.last_7_days],
                    ["Last 30 days", stats.last_30_days],
                  ] as const
                ).map(([label, period]) => (
                  <Card key={label}>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">{label}</CardTitle>
                      <CardDescription>
                        {period.emails_received} emails processed by the assistant
                      </CardDescription>
                    </CardHeader>
                    <div className="px-6 pb-5 grid grid-cols-2 gap-3 text-sm">
                      <div>
                        <p className="text-content-subtle text-xs">Sent</p>
                        <p className="font-semibold tabular-nums text-content">{period.replies_sent}</p>
                      </div>
                      <div>
                        <p className="text-content-subtle text-xs">Filtered</p>
                        <p className="font-semibold tabular-nums text-content">{period.filtered}</p>
                      </div>
                      <div>
                        <p className="text-content-subtle text-xs">Drafts</p>
                        <p className="font-semibold tabular-nums text-content">{period.drafts_pending}</p>
                      </div>
                      <div>
                        <p className="text-content-subtle text-xs">Awaiting</p>
                        <p className="font-semibold tabular-nums text-content">{period.awaiting_reply}</p>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">What got filtered</CardTitle>
                    <CardDescription>
                      Automated mail, duplicates, and other noise the AI kept out of your send queue.
                    </CardDescription>
                  </CardHeader>
                  <div className="px-6 pb-5 space-y-2">
                    {stats.filter_breakdown.length === 0 ? (
                      <p className="text-sm text-content-muted">No filtered emails yet.</p>
                    ) : (
                      stats.filter_breakdown.map((row) => {
                        const max = stats.filter_breakdown[0]?.count || 1;
                        const pct = Math.max(8, Math.round((row.count / max) * 100));
                        return (
                          <div key={row.name}>
                            <div className="flex justify-between text-sm mb-1">
                              <span className="text-content capitalize">
                                {filterCategoryLabel(row.name) ?? row.name}
                              </span>
                              <span className="tabular-nums text-content-muted">{row.count}</span>
                            </div>
                            <div className="h-1.5 rounded-full bg-surface-muted overflow-hidden">
                              <div
                                className="h-full rounded-full bg-brand-500/70"
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Customer intents</CardTitle>
                    <CardDescription>
                      What shoppers write about — useful for staffing and FAQ updates.
                    </CardDescription>
                  </CardHeader>
                  <div className="px-6 pb-5 space-y-2">
                    {stats.intent_breakdown.length === 0 ? (
                      <p className="text-sm text-content-muted">
                        Intents appear after the AI reads customer emails.
                      </p>
                    ) : (
                      stats.intent_breakdown.slice(0, 8).map((row) => {
                        const max = stats.intent_breakdown[0]?.count || 1;
                        const pct = Math.max(8, Math.round((row.count / max) * 100));
                        return (
                          <div key={row.name}>
                            <div className="flex justify-between text-sm mb-1">
                              <span className="text-content capitalize">{row.name}</span>
                              <span className="tabular-nums text-content-muted">{row.count}</span>
                            </div>
                            <div className="h-1.5 rounded-full bg-surface-muted overflow-hidden">
                              <div
                                className="h-full rounded-full bg-emerald-500/70"
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                </Card>
              </div>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <TrendingUp className="h-4 w-4 text-brand-600" />
                    Why this matters
                  </CardTitle>
                  <CardDescription>
                    Snapshot of assistant value for{" "}
                    {activeStore?.name ? (
                      <strong className="text-content">{activeStore.name}</strong>
                    ) : (
                      "your store"
                    )}
                    .
                  </CardDescription>
                </CardHeader>
                <ul className="px-6 pb-5 space-y-2 text-sm text-content-muted">
                  <li>
                    · <span className="text-content font-medium">{stats.all_time.replies_sent}</span>{" "}
                    customer replies sent without you typing each one.
                  </li>
                  <li>
                    · <span className="text-content font-medium">{stats.all_time.filtered}</span>{" "}
                    messages filtered so you do not waste time on no-reply / non-business mail.
                  </li>
                  <li>
                    · About{" "}
                    <span className="text-content font-medium">
                      {stats.hours_saved_estimate >= 1
                        ? `${stats.hours_saved_estimate} hours`
                        : `${stats.minutes_saved_estimate} minutes`}
                    </span>{" "}
                    of support time saved (estimate).
                  </li>
                  <li>
                    · Autopilot is{" "}
                    <span className="text-content font-medium">
                      {stats.autopilot_enabled ? "on" : "off"}
                    </span>
                    {stats.auto_send_enabled ? " with auto-send" : " (drafts need approval)"}
                    {stats.automation_last_run_at
                      ? ` · last run ${formatTime(stats.automation_last_run_at)}`
                      : ""}
                    .
                  </li>
                  {(!stats.gmail_connected || !stats.openai_configured) && (
                    <li className="text-amber-700 dark:text-amber-400">
                      · Finish setup:{" "}
                      {!stats.gmail_connected && "connect Gmail"}
                      {!stats.gmail_connected && !stats.openai_configured && " and "}
                      {!stats.openai_configured && "add your OpenAI key"} in Settings.
                    </li>
                  )}
                </ul>
              </Card>
            </>
          )}
        </motion.div>
      )}

      {tab === "business" && settings && (
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="max-w-2xl space-y-5">
          <div>
            <h2 className="text-lg font-semibold text-content">Your business</h2>
            <p className="text-sm text-content-muted mt-1 leading-relaxed">
              Tell the AI how your store sounds and what customers usually ask. Keep this short —
              API keys and autopilot live under Settings.
            </p>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Basics</CardTitle>
              <CardDescription>Used on every reply so customers recognize your brand.</CardDescription>
            </CardHeader>
            <div className="space-y-4">
              <Input
                label="Business name"
                placeholder="e.g. Northwind Outfitters"
                value={settings.business_name}
                onChange={(e) => setSettings({ ...settings, business_name: e.target.value })}
              />
              <Input
                label="What you sell"
                hint="e.g. online clothing store, electronics, handmade gifts"
                value={settings.business_type}
                onChange={(e) => setSettings({ ...settings, business_type: e.target.value })}
              />
              <Input
                label="Tone of voice"
                hint="e.g. friendly and helpful, short and professional"
                value={settings.tone_of_voice}
                onChange={(e) => setSettings({ ...settings, tone_of_voice: e.target.value })}
              />
            </div>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>How to reply</CardTitle>
              <CardDescription>Guidelines the AI must follow in every message.</CardDescription>
            </CardHeader>
            <div className="space-y-1.5">
              <label className="block text-sm font-medium text-content">Rules</label>
              <textarea
                className={textareaClass}
                rows={4}
                placeholder={"Always be polite.\nNever promise a refund without checking the order first.\nSign off with the store name."}
                value={settings.rules}
                onChange={(e) => setSettings({ ...settings, rules: e.target.value })}
              />
            </div>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Policies & FAQ</CardTitle>
              <CardDescription>
                Shipping, returns, and common answers — the AI uses these instead of guessing.
              </CardDescription>
            </CardHeader>
            <div className="space-y-4">
              <div className="space-y-1.5">
                <label className="block text-sm font-medium text-content">Key policies</label>
                <textarea
                  className={textareaClass}
                  rows={4}
                  placeholder={"Shipping: 3–5 business days.\nReturns within 14 days of delivery.\nFree shipping over $50."}
                  value={settings.policies}
                  onChange={(e) => setSettings({ ...settings, policies: e.target.value })}
                />
              </div>
              <div className="space-y-1.5">
                <label className="block text-sm font-medium text-content">Common questions</label>
                <textarea
                  className={textareaClass}
                  rows={4}
                  placeholder={"Q: How do I track my order?\nA: Use the tracking link in your shipping email.\n\nQ: Can I change my address?\nA: Reply with the new address before we ship."}
                  value={settings.faq}
                  onChange={(e) => setSettings({ ...settings, faq: e.target.value })}
                />
              </div>
            </div>
          </Card>

          <div className="flex items-center gap-3 sticky bottom-4">
            <Button onClick={saveSettings} disabled={savingSettings}>
              {savingSettings ? "Saving…" : "Save business info"}
            </Button>
            {settingsSaved && (
              <span className="text-sm text-green-600 dark:text-green-400 flex items-center gap-1">
                <Check className="h-4 w-4" /> Saved
              </span>
            )}
          </div>
        </motion.div>
      )}

      {tab === "settings" && settings && (
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="max-w-2xl space-y-5">
          <div>
            <h2 className="text-lg font-semibold text-content">Settings</h2>
            <p className="text-sm text-content-muted mt-1 leading-relaxed">
              Connect accounts, turn on autopilot, and choose which emails get a reply.
            </p>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <KeyRound className="h-4 w-4 text-brand-600 dark:text-brand-400" />
                OpenAI API key
              </CardTitle>
              <CardDescription>
                Required for drafting replies. Stored encrypted — billed by OpenAI on your account.
              </CardDescription>
            </CardHeader>
            <div className="space-y-4">
              {settings.openai_key_is_user_owned && settings.openai_key_masked && (
                <div className="flex items-center justify-between rounded-lg bg-surface-muted px-3 py-2 text-sm">
                  <span className="text-content-muted">Saved key</span>
                  <span className="font-mono text-content">{settings.openai_key_masked}</span>
                </div>
              )}
              {settings.openai_uses_server_fallback && !settings.openai_key_is_user_owned && (
                <p className="text-xs text-content-muted rounded-lg bg-surface-muted px-3 py-2">
                  Using a temporary shared key for development. Add your own key for production.
                </p>
              )}
              <div className="space-y-1.5">
                <label htmlFor="openai-api-key" className="block text-sm font-medium text-content">
                  {settings.openai_key_is_user_owned ? "Replace key" : "API key"}
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
                  Get a key at{" "}
                  <a
                    href="https://platform.openai.com/api-keys"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-brand-600 hover:underline"
                  >
                    platform.openai.com/api-keys
                  </a>
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button onClick={saveOpenaiKey} disabled={savingOpenaiKey || !openaiKeyInput.trim()}>
                  {savingOpenaiKey ? "Saving…" : settings.openai_key_is_user_owned ? "Update key" : "Save key"}
                </Button>
                {settings.openai_key_is_user_owned && (
                  <Button variant="outline" onClick={removeOpenaiKey} disabled={savingOpenaiKey}>
                    Remove
                  </Button>
                )}
              </div>
            </div>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Mail className="h-4 w-4 text-brand-600 dark:text-brand-400" />
                Gmail account
              </CardTitle>
              <CardDescription>
                Inbox sync and sending use this connected account. If emails stay unread after
                the bot replies, disconnect and reconnect Gmail so mark-as-read permission is granted.
              </CardDescription>
            </CardHeader>
            <div className="space-y-3">
              {accounts.filter((a) => a.status === "connected").length === 0 ? (
                <p className="text-sm text-content-muted">
                  No Gmail connected yet.{" "}
                  <Link to="/settings/gmail" className="text-brand-600 hover:underline font-medium">
                    Connect Gmail →
                  </Link>
                </p>
              ) : (
                <div className="space-y-1.5">
                  <label className="block text-sm font-medium text-content">Send from</label>
                  <select
                    className={selectClass}
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
            </div>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bot className="h-4 w-4 text-brand-600 dark:text-brand-400" />
                Autopilot
              </CardTitle>
              <CardDescription>
                Automatically check Gmail on a schedule. Drafts replies — or sends them if auto-send
                is on.
              </CardDescription>
            </CardHeader>
            <div className="space-y-4">
              <Switch
                checked={settings.automation_enabled}
                onChange={(v) => setSettings({ ...settings, automation_enabled: v })}
                label="Enable autopilot"
                description="Runs while the App Manager backend is online"
              />
              {settings.automation_enabled && (
                <div className="grid gap-4 sm:grid-cols-2 pl-1 border-l-2 border-brand-500/30 ml-1">
                  <div className="space-y-1.5">
                    <label className="block text-sm font-medium text-content">Check every</label>
                    <select
                      className={selectClass}
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
                    label="Emails per check"
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
                    hint="Max unread emails each cycle"
                  />
                </div>
              )}
              <Switch
                checked={settings.auto_send_enabled}
                onChange={(v) => setSettings({ ...settings, auto_send_enabled: v })}
                label="Auto-send replies"
                description="Send without waiting for your approval (use carefully)"
              />
              {settings.automation_last_run_at && (
                <p className="text-xs text-content-muted">
                  Last run: {formatTime(settings.automation_last_run_at)}
                </p>
              )}
              <Button
                variant="outline"
                disabled={runningAutomation || !settings.openai_configured || !connectedAccount}
                onClick={runAutomationNow}
              >
                <RefreshCw className={cn("h-4 w-4 mr-2", runningAutomation && "animate-spin")} />
                {runningAutomation ? "Running…" : "Run once now"}
              </Button>
            </div>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Filter className="h-4 w-4 text-brand-600 dark:text-brand-400" />
                Which emails get a reply?
              </CardTitle>
              <CardDescription>
                The AI reads the full conversation. Already-answered issues are left as read with no
                reply.
              </CardDescription>
            </CardHeader>
            <div className="space-y-4">
              <Switch
                checked={settings.email_filter_enabled}
                onChange={(v) => setSettings({ ...settings, email_filter_enabled: v })}
                label="Smart reply filter"
                description="Skip newsletters, automated mail, and messages that don’t need a reply"
              />
              {settings.email_filter_enabled && (
                <div className="space-y-4 pl-1 border-l-2 border-brand-500/30 ml-1">
                  <Switch
                    checked={settings.filter_automated_emails}
                    onChange={(v) => setSettings({ ...settings, filter_automated_emails: v })}
                    label="Skip automated emails"
                    description="No-reply, delivery notices, password resets, platform alerts"
                  />
                  <Switch
                    checked={settings.filter_non_business_emails}
                    onChange={(v) => setSettings({ ...settings, filter_non_business_emails: v })}
                    label="Skip non-business emails"
                    description="Personal or unrelated messages"
                  />
                  <div className="space-y-1.5">
                    <label className="block text-sm font-medium text-content">
                      Extra rules (optional)
                    </label>
                    <textarea
                      className={textareaClass}
                      rows={3}
                      placeholder={"Ignore wholesale inquiries\nDo not reply to influencer outreach"}
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
              <CardTitle>Conversation checks</CardTitle>
              <CardDescription>
                Recommended defaults — leave these on unless you have a specific reason to change
                them.
              </CardDescription>
            </CardHeader>
            <div className="space-y-4">
              <Switch
                checked={settings.use_thread_context}
                onChange={(v) => setSettings({ ...settings, use_thread_context: v })}
                label="Read full email history"
                description="AI sees the whole thread, not just the latest message"
              />
              <Switch
                checked={settings.one_reply_per_thread}
                onChange={(v) => setSettings({ ...settings, one_reply_per_thread: v })}
                label="One reply per conversation per run"
                description="Avoids double replies when several unread messages are in the same thread"
              />
              <Switch
                checked={settings.sync_only_customer_unread}
                onChange={(v) => setSettings({ ...settings, sync_only_customer_unread: v })}
                label="Only customer emails"
                description="Ignore unread messages from your own address"
              />
              <Switch
                checked={settings.verify_gmail_thread_before_reply}
                onChange={(v) => setSettings({ ...settings, verify_gmail_thread_before_reply: v })}
                label="Skip if we already sent last"
                description="If your latest message is already in the thread, don’t reply again"
              />
              <Input
                label="AI model (optional)"
                hint={`Default: ${settings.default_model}`}
                placeholder={settings.default_model}
                value={settings.openai_model ?? ""}
                onChange={(e) =>
                  setSettings({ ...settings, openai_model: e.target.value || null })
                }
              />
            </div>
          </Card>

          <div className="flex items-center gap-3 sticky bottom-4">
            <Button onClick={saveSettings} disabled={savingSettings}>
              {savingSettings ? "Saving…" : "Save settings"}
            </Button>
            {settingsSaved && (
              <span className="text-sm text-green-600 dark:text-green-400 flex items-center gap-1">
                <Check className="h-4 w-4" /> Saved
              </span>
            )}
          </div>
        </motion.div>
      )}

      {tab === "logs" && (
        <Card padding="none">
          <div className="p-5 border-b border-border">
            <CardTitle>Activity</CardTitle>
            <CardDescription className="mt-1">
              Recent AI drafts and sent replies.
            </CardDescription>
          </div>
          {/* Mobile: card list */}
          <ul className="divide-y divide-border md:hidden">
            {logs.length === 0 && (
              <li className="px-4 py-10 text-center text-sm text-content-muted">
                No activity yet — sync your inbox and generate a reply to see it here.
              </li>
            )}
            {logs.map((log) => (
              <li key={log.id} className="px-4 py-3 space-y-1.5">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-medium text-content truncate">{log.subject || "(no subject)"}</p>
                  <Badge variant={statusBadge(log.status)}>{statusLabel(log.status)}</Badge>
                </div>
                <p className="text-xs text-content-muted truncate">{log.sender_email}</p>
                <p className="text-xs text-content-subtle">{formatTime(log.created_at)}</p>
                {log.body_preview && (
                  <p className="text-xs text-content-muted line-clamp-2">{log.body_preview}</p>
                )}
              </li>
            ))}
          </ul>

          {/* Desktop / tablet: table */}
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-content-muted">
                  <th className="px-4 py-2.5 font-medium">When</th>
                  <th className="px-4 py-2.5 font-medium">Customer</th>
                  <th className="px-4 py-2.5 font-medium">Subject</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                  <th className="px-4 py-2.5 font-medium">Preview</th>
                </tr>
              </thead>
              <tbody>
                {logs.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-10 text-center text-content-muted">
                      No activity yet — sync your inbox and generate a reply to see it here.
                    </td>
                  </tr>
                )}
                {logs.map((log) => (
                  <tr key={log.id} className="border-b border-border/50">
                    <td className="px-4 py-2.5 whitespace-nowrap text-content-muted">
                      {formatTime(log.created_at)}
                    </td>
                    <td className="px-4 py-2.5">{log.sender_email}</td>
                    <td className="px-4 py-2.5 max-w-[180px] truncate">{log.subject}</td>
                    <td className="px-4 py-2.5">
                      <Badge variant={statusBadge(log.status)}>{statusLabel(log.status)}</Badge>
                    </td>
                    <td className="px-4 py-2.5 max-w-xs truncate text-content-muted">
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
