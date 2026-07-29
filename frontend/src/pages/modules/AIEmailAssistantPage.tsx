import { useCallback, useEffect, useRef, useState, type TextareaHTMLAttributes } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Sparkles,
  RefreshCw,
  Mail,
  Settings2,
  ScrollText,
  Send,
  Check,
  AlertCircle,
  Filter,
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
  PenLine,
  Package,
  ExternalLink,
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

type RelatedOrder = {
  id: string;
  order_number: string;
  customer_email: string;
  customer_name: string | null;
  tracking_number: string | null;
  carrier: string | null;
  status: string;
  shopify_financial_status: string | null;
  shopify_fulfillment_status: string | null;
  order_total: string | null;
  currency: string | null;
  order_placed_at: string | null;
  match_reason: string;
  last_updated_at: string | null;
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

function previewSnippet(body: string, max = 72) {
  const cleaned = body
    .replace(/https?:\/\/\S+/gi, "")
    .replace(/\s+/g, " ")
    .trim();
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

function orderStatusLabel(status: string) {
  if (status === "in_transit") return "On the way";
  if (status === "delivered") return "Delivered";
  return "Preparing";
}

function orderStatusBadge(status: string): "success" | "brand" | "muted" {
  if (status === "delivered") return "success";
  if (status === "in_transit") return "brand";
  return "muted";
}

function fulfillmentLabel(status: string | null) {
  const value = (status || "").toLowerCase();
  if (value === "fulfilled") return "Shipped";
  if (value === "partial") return "Partially shipped";
  if (value === "unfulfilled" || !value) return "Not shipped";
  return value.replace(/_/g, " ");
}

function cleanEmailBody(text: string) {
  return text
    .replace(/\r\n/g, "\n")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function assistantInsight(item: InboxItem): string | null {
  if (item.status === "skipped") {
    const cat = filterCategoryLabel(item.filter_category);
    return cat ? `Filtered · ${cat}` : "Filtered · no reply needed";
  }
  if (item.status === "draft_pending" || item.latest_reply?.status === "draft") {
    return "Draft ready for review";
  }
  if (item.status === "replied" || item.latest_reply?.status === "sent") {
    return "Replied via Gmail";
  }
  if (item.status === "new") return "Needs your attention";
  return null;
}

function statusDotClass(status: string) {
  if (status === "new") return "bg-amber-400";
  if (status === "draft" || status === "draft_pending") return "bg-brand-500";
  if (status === "replied" || status === "sent") return "bg-emerald-500";
  if (status === "skipped") return "bg-content-subtle/50";
  return "bg-content-subtle/40";
}

function EmailBodyText({ text, className }: { text: string; className?: string }) {
  const cleaned = cleanEmailBody(text);
  if (!cleaned) {
    return <p className={cn("text-sm italic opacity-70", className)}>No message body.</p>;
  }
  const parts = cleaned.split(/(https?:\/\/[^\s<>\]"'`]+)/gi);
  return (
    <div className={cn("text-[14px] leading-6 whitespace-pre-wrap break-words", className)}>
      {parts.map((part, i) => {
        if (/^https?:\/\//i.test(part)) {
          let label = part;
          try {
            const u = new URL(part);
            const path =
              u.pathname.length > 1
                ? u.pathname.slice(0, 28) + (u.pathname.length > 28 ? "…" : "")
                : "";
            label = `${u.hostname}${path}`;
          } catch {
            label = part.length > 48 ? `${part.slice(0, 48)}…` : part;
          }
          return (
            <a
              key={`${i}-${part.slice(0, 24)}`}
              href={part}
              target="_blank"
              rel="noopener noreferrer"
              className="underline underline-offset-2 opacity-90 hover:opacity-100 break-all"
            >
              {label}
            </a>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </div>
  );
}

/** Textarea that grows with content, capped so long docs don’t dominate the page. */
function AutoGrowTextarea({
  value,
  className,
  minRows = 4,
  maxHeightPx = 280,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement> & {
  minRows?: number;
  maxHeightPx?: number;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  const resize = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    const next = Math.min(el.scrollHeight, maxHeightPx);
    el.style.height = `${next}px`;
    el.style.overflowY = el.scrollHeight > maxHeightPx ? "auto" : "hidden";
  }, [maxHeightPx]);

  useEffect(() => {
    resize();
  }, [value, resize]);

  return (
    <textarea
      {...props}
      ref={ref}
      value={value}
      rows={minRows}
      onInput={(e) => {
        props.onInput?.(e);
        resize();
      }}
      className={cn(className, "resize-none")}
      style={{ maxHeight: maxHeightPx }}
    />
  );
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
  const [threadLoading, setThreadLoading] = useState(false);
  const [composing, setComposing] = useState(false);
  const [relatedOrders, setRelatedOrders] = useState<RelatedOrder[]>([]);
  const [relatedOrdersMessage, setRelatedOrdersMessage] = useState<string | null>(null);
  const [relatedShopDomain, setRelatedShopDomain] = useState<string | null>(null);
  const [relatedOrdersLoading, setRelatedOrdersLoading] = useState(false);

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
    } finally {
      setThreadLoading(false);
    }
  }, []);

  const loadRelatedOrders = useCallback(async (emailId: string) => {
    setRelatedOrdersLoading(true);
    try {
      const data = await api.aiEmailAssistant.relatedOrders(emailId);
      setRelatedOrders(data.orders as RelatedOrder[]);
      setRelatedOrdersMessage(data.message);
      setRelatedShopDomain(data.shop_domain);
    } catch {
      setRelatedOrders([]);
      setRelatedOrdersMessage(null);
      setRelatedShopDomain(null);
    } finally {
      setRelatedOrdersLoading(false);
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
    // Only auto-open the composer when there is a pending AI/manual draft to review.
    // Sent replies must not pre-fill a new Reply.
    if (selected?.latest_reply?.status === "draft" && selected.latest_reply.effective_body) {
      setDraftEdit(selected.latest_reply.effective_body);
      setComposing(true);
    } else {
      setDraftEdit("");
      setComposing(false);
    }
  }, [selected?.id, selected?.latest_reply?.status, selected?.latest_reply?.effective_body]);

  useEffect(() => {
    if (!selectedId) {
      setThreadMessages([]);
      setComposing(false);
      setRelatedOrders([]);
      setRelatedOrdersMessage(null);
      setRelatedShopDomain(null);
      return;
    }
    loadThread(selectedId);
    loadRelatedOrders(selectedId);
  }, [selectedId, loadThread, loadRelatedOrders]);

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

  const openManualCompose = () => {
    // Manual Reply always starts blank — don't reuse an old AI/sent body.
    setDraftEdit("");
    setComposing(true);
  };

  const sendManualReply = async () => {
    const storeId = activeStore?.id;
    if (!selected || !storeId) {
      setError("Select a store first.");
      return;
    }
    const body = draftEdit.trim();
    if (!body) {
      setError("Write a reply before sending.");
      return;
    }
    setActionId(selected.id);
    setError("");
    try {
      await api.aiEmailAssistant.sendManualReply(selected.id, body, storeId);
      setComposing(false);
      setDraftEdit("");
      await Promise.all([loadInbox(), loadLogs(), loadStats()]);
      await loadThread(selected.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send reply");
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
      // If filtered, unskip so generate is allowed
      const item = inbox.find((e) => e.id === emailId);
      if (item?.status === "skipped") {
        await api.aiEmailAssistant.unskipEmail(emailId);
      }
      const reply = await api.aiEmailAssistant.generateReply(emailId, storeId);
      setDraftEdit(reply.effective_body);
      setComposing(true);
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
      // Persist textarea edits before send
      if (draftEdit.trim()) {
        await api.aiEmailAssistant.updateDraft(replyId, draftEdit);
      }
      await api.aiEmailAssistant.approveReply(replyId);
      setComposing(false);
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
      setComposing(false);
      setDraftEdit("");
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
    <div className="space-y-4 sm:space-y-5 w-full min-w-0">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl xl:text-3xl font-bold text-content tracking-tight">
            AI Email Assistant
          </h1>
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
        <div className="rounded-xl border border-border bg-surface overflow-hidden shadow-card h-[min(820px,calc(100dvh-11rem))] sm:h-[min(860px,calc(100dvh-12rem))] xl:h-[calc(100dvh-9.5rem)] 2xl:h-[calc(100dvh-10rem)] flex flex-col lg:flex-row w-full min-w-0">
          {/* Thread list */}
          <aside
            className={cn(
              "w-full lg:w-[min(400px,34%)] xl:w-[min(440px,32%)] 2xl:w-[480px] shrink-0 border-b lg:border-b-0 lg:border-r border-border flex flex-col min-h-0",
              selected && "hidden lg:flex"
            )}
          >
            <div className="px-3 pt-3 pb-2 shrink-0 space-y-2">
              <div className="flex items-center justify-between px-1">
                <h2 className="text-sm font-semibold text-content tracking-tight">Inbox</h2>
                <span className="text-xs text-content-subtle tabular-nums">
                  {filteredInbox.length}
                </span>
              </div>
              <div className="flex gap-0.5 p-0.5 rounded-lg bg-surface-muted/80">
                {(
                  [
                    { id: "all", label: "All" },
                    { id: "needs_reply", label: "Open" },
                    { id: "drafts", label: "Drafts" },
                    { id: "replied", label: "Sent" },
                    { id: "filtered", label: "Skipped" },
                  ] as const
                ).map(({ id, label }) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => setInboxFilter(id)}
                    className={cn(
                      "flex-1 min-w-0 rounded-md px-1.5 py-1.5 text-[11px] font-medium transition-colors",
                      inboxFilter === id
                        ? "bg-surface text-content shadow-sm"
                        : "text-content-muted hover:text-content"
                    )}
                  >
                    {label}
                    {filterCounts[id] > 0 && (
                      <span className="ml-0.5 text-content-subtle tabular-nums">
                        {filterCounts[id]}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>

            <ul className="flex-1 overflow-y-auto min-h-0">
              {filteredInbox.length === 0 && (
                <li className="px-6 py-16 text-center">
                  <Mail className="h-8 w-8 text-content-subtle mx-auto mb-3 opacity-60" />
                  <p className="text-sm text-content-muted">
                    {inbox.length === 0 ? "Your inbox is empty" : "No conversations here"}
                  </p>
                  <p className="text-xs text-content-subtle mt-1.5 max-w-[220px] mx-auto leading-relaxed">
                    {inbox.length === 0
                      ? connectedAccount
                        ? 'Use "Check inbox" to sync Gmail.'
                        : "Connect Gmail in Settings to get started."
                      : "Try another filter."}
                  </p>
                </li>
              )}
              {filteredInbox.map((item) => {
                const name = displayName(item.sender, item.sender_email);
                const st = effectiveStatus(item);
                const active = selected?.id === item.id;
                const needsAttention = item.status === "new" || item.status === "draft_pending";
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(item.id)}
                      className={cn(
                        "w-full text-left px-4 py-3 transition-colors border-l-2",
                        active
                          ? "bg-surface-muted border-l-brand-500"
                          : "border-l-transparent hover:bg-surface-muted/60"
                      )}
                    >
                      <div className="flex items-center gap-2.5">
                        <span
                          className={cn("h-1.5 w-1.5 rounded-full shrink-0", statusDotClass(st))}
                          title={statusLabel(st)}
                        />
                        <p
                          className={cn(
                            "text-[13px] truncate flex-1 min-w-0",
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
                          "text-[13px] truncate mt-1 pl-4",
                          needsAttention ? "text-content" : "text-content/80"
                        )}
                      >
                        {item.subject || "(no subject)"}
                      </p>
                      <p className="text-[12px] text-content-muted truncate mt-0.5 pl-4 leading-snug">
                        {previewSnippet(item.body_text)}
                      </p>
                    </button>
                  </li>
                );
              })}
            </ul>
          </aside>

          {/* Reading pane */}
          <section
            className={cn(
              "flex-1 min-w-0 flex flex-col min-h-0 bg-surface",
              !selected && "hidden lg:flex"
            )}
          >
            {selected ? (
              <>
                <header className="shrink-0 px-5 sm:px-7 pt-5 pb-4 border-b border-border/80">
                  <button
                    type="button"
                    onClick={() => setSelectedId(null)}
                    className="inline-flex items-center gap-1.5 text-sm text-content-muted hover:text-content lg:hidden mb-3"
                  >
                    <ArrowLeft className="h-4 w-4" />
                    Inbox
                  </button>
                  <h2 className="text-xl font-semibold text-content tracking-tight leading-snug">
                    {selected.subject || "(no subject)"}
                  </h2>
                  <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[13px]">
                    <span className="text-content font-medium">
                      {displayName(selected.sender, selected.sender_email)}
                    </span>
                    <span className="text-content-subtle">{selected.sender_email}</span>
                    {assistantInsight(selected) && (
                      <>
                        <span className="text-content-subtle/40">·</span>
                        <span className="inline-flex items-center gap-1.5 text-content-muted">
                          <Bot className="h-3.5 w-3.5 text-brand-600 dark:text-brand-400" />
                          {assistantInsight(selected)}
                        </span>
                      </>
                    )}
                  </div>

                  {(relatedOrdersLoading || relatedOrders.length > 0 || relatedOrdersMessage) && (
                    <div className="mt-4 rounded-lg border border-border bg-surface-muted/40 overflow-hidden">
                      <div className="flex items-center justify-between gap-2 px-3.5 py-2.5 border-b border-border/70">
                        <div className="flex items-center gap-2 min-w-0">
                          <Package className="h-3.5 w-3.5 text-brand-600 dark:text-brand-400 shrink-0" />
                          <p className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                            Shopify orders
                          </p>
                          {relatedOrders.length > 0 && (
                            <span className="text-xs text-content-subtle tabular-nums">
                              {relatedOrders.length}
                            </span>
                          )}
                        </div>
                        <Link
                          to="/modules/tracking"
                          className="text-xs text-brand-600 dark:text-brand-400 hover:underline shrink-0"
                        >
                          Open Tracking
                        </Link>
                      </div>
                      {relatedOrdersLoading && (
                        <p className="px-3.5 py-3 text-sm text-content-muted">Looking up orders…</p>
                      )}
                      {!relatedOrdersLoading && relatedOrders.length === 0 && relatedOrdersMessage && (
                        <p className="px-3.5 py-3 text-sm text-content-muted">{relatedOrdersMessage}</p>
                      )}
                      {!relatedOrdersLoading && relatedOrders.length > 0 && (
                        <ul className="divide-y divide-border/60">
                          {relatedOrders.map((order) => {
                            const adminUrl =
                              relatedShopDomain && order.order_number
                                ? `https://${relatedShopDomain}/admin/orders?query=${encodeURIComponent(order.order_number)}`
                                : null;
                            return (
                              <li
                                key={order.id}
                                className="px-3.5 py-3 flex flex-wrap items-start justify-between gap-3"
                              >
                                <div className="min-w-0">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <p className="text-sm font-semibold text-content">
                                      {order.order_number}
                                    </p>
                                    <Badge variant={orderStatusBadge(order.status)}>
                                      {orderStatusLabel(order.status)}
                                    </Badge>
                                    {order.match_reason === "order_number_in_email" && (
                                      <span className="text-[11px] text-content-subtle">
                                        Mentioned in email
                                      </span>
                                    )}
                                  </div>
                                  <p className="text-xs text-content-muted mt-1">
                                    {fulfillmentLabel(order.shopify_fulfillment_status)}
                                    {order.order_total
                                      ? ` · ${order.currency || ""} ${order.order_total}`.trim()
                                      : ""}
                                    {order.order_placed_at
                                      ? ` · ${formatTime(order.order_placed_at)}`
                                      : ""}
                                  </p>
                                  {order.tracking_number && (
                                    <p className="text-xs text-content-subtle mt-1 font-mono">
                                      {order.tracking_number}
                                      {order.carrier ? ` · ${order.carrier}` : ""}
                                    </p>
                                  )}
                                </div>
                                {adminUrl && (
                                  <a
                                    href={adminUrl}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="inline-flex items-center gap-1 text-xs text-brand-600 dark:text-brand-400 hover:underline shrink-0"
                                  >
                                    Shopify
                                    <ExternalLink className="h-3 w-3" />
                                  </a>
                                )}
                              </li>
                            );
                          })}
                        </ul>
                      )}
                    </div>
                  )}
                </header>

                <div className="flex-1 overflow-y-auto min-h-0 px-2 sm:px-3 lg:px-4 py-4 bg-surface-muted/20">
                  {threadLoading && (
                    <p className="text-sm text-content-muted text-center py-20">
                      Loading conversation…
                    </p>
                  )}
                  {!threadLoading && threadMessages.length === 0 && (
                    <div className="flex gap-2 w-full justify-start">
                      <div className="h-8 w-8 rounded-full bg-surface-muted text-content-muted flex items-center justify-center text-[10px] font-semibold shrink-0 mt-1">
                        {initials(displayName(selected.sender, selected.sender_email))}
                      </div>
                      <div className="min-w-0 max-w-[78%] sm:max-w-[70%]">
                        <div className="rounded-2xl rounded-tl-md bg-surface border border-border px-3.5 py-2.5 text-content shadow-sm">
                          <EmailBodyText text={selected.body_text} />
                        </div>
                        <p className="text-[11px] text-content-subtle mt-1 px-1">
                          {formatTime(selected.received_at)}
                        </p>
                      </div>
                    </div>
                  )}
                  {!threadLoading && threadMessages.length > 0 && (
                    <div className="w-full space-y-3">
                      {threadMessages.map((msg, index) => {
                        const draft = isDraftMessage(msg.message_id);
                        const fromName = parseFromName(msg.from_header);
                        const mine = msg.is_from_business;
                        const prev = threadMessages[index - 1];
                        const showName =
                          !prev ||
                          prev.is_from_business !== msg.is_from_business ||
                          parseFromName(prev.from_header) !== fromName ||
                          isDraftMessage(prev.message_id) !== draft;

                        return (
                          <div
                            key={msg.message_id}
                            className={cn(
                              "flex gap-2 w-full",
                              mine ? "flex-row-reverse justify-start" : "flex-row justify-start"
                            )}
                          >
                            <div
                              className={cn(
                                "h-8 w-8 rounded-full flex items-center justify-center text-[10px] font-semibold shrink-0 mt-auto mb-5",
                                draft
                                  ? "bg-brand-500/20 text-brand-700 dark:text-brand-400"
                                  : mine
                                    ? "bg-brand-500/15 text-brand-700 dark:text-brand-400"
                                    : "bg-surface-muted text-content-muted"
                              )}
                            >
                              {draft ? <Bot className="h-3.5 w-3.5" /> : initials(fromName)}
                            </div>
                            <div
                              className={cn(
                                "min-w-0 max-w-[78%] sm:max-w-[70%] flex flex-col",
                                mine ? "items-end" : "items-start"
                              )}
                            >
                              {showName && (
                                <p className="text-[11px] font-medium mb-1 px-1 text-content-muted">
                                  {draft ? "AI draft" : mine ? "You" : fromName}
                                  {draft && (
                                    <span className="ml-1.5 text-brand-700 dark:text-brand-400">
                                      · not sent
                                    </span>
                                  )}
                                </p>
                              )}
                              <div
                                className={cn(
                                  "px-3.5 py-2.5 shadow-sm w-fit max-w-full",
                                  draft
                                    ? "rounded-2xl rounded-tr-md bg-brand-500/10 border border-dashed border-brand-500/45 text-content"
                                    : mine
                                      ? "rounded-2xl rounded-tr-md bg-brand-500 text-white"
                                      : "rounded-2xl rounded-tl-md bg-surface border border-border text-content"
                                )}
                              >
                                <EmailBodyText
                                  text={msg.body_text || msg.snippet}
                                  className={
                                    mine && !draft
                                      ? "text-white [&_a]:text-white"
                                      : "text-content"
                                  }
                                />
                              </div>
                              {msg.sent_at && (
                                <time
                                  className={cn(
                                    "text-[10px] text-content-subtle mt-1 px-1 tabular-nums",
                                    mine && "text-right"
                                  )}
                                >
                                  {formatTime(msg.sent_at)}
                                </time>
                              )}
                              {draft && !msg.sent_at && (
                                <span className="text-[10px] text-brand-700 dark:text-brand-400 mt-1 px-1">
                                  Waiting for send
                                </span>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                <footer className="shrink-0 border-t border-border/80 px-4 sm:px-6 lg:px-8 py-4 bg-surface-muted/30">
                  {selected.status === "skipped" && !composing && selected.latest_reply?.status !== "draft" && (
                    <p className="text-sm text-content-muted mb-3 w-full max-w-none">
                      Assistant skipped this thread
                      {selected.filter_category
                        ? ` (${filterCategoryLabel(selected.filter_category)?.toLowerCase()})`
                        : ""}
                      . You can still reply yourself or ask AI to draft one.
                    </p>
                  )}

                  {selected.latest_reply?.status === "sent" && !composing && (
                    <p className="text-sm text-content-muted inline-flex items-center gap-2 mb-3">
                      <Check className="h-4 w-4 text-emerald-500" />
                      Sent via Gmail
                    </p>
                  )}

                  {selected.latest_reply &&
                    selected.latest_reply.status !== "draft" &&
                    selected.latest_reply.status !== "sent" &&
                    !composing && (
                      <p className="text-sm text-content-muted mb-3">
                        {statusLabel(selected.latest_reply.status)}
                      </p>
                    )}

                  {!composing && selected.latest_reply?.status !== "draft" && (
                    <div className="flex flex-wrap gap-2 w-full max-w-none">
                      <Button
                        onClick={openManualCompose}
                        disabled={!connectedAccount || actionId === selected.id}
                      >
                        <PenLine className="h-4 w-4 mr-2" />
                        Reply
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => generateDraft(selected.id)}
                        disabled={!settings?.openai_configured || actionId === selected.id}
                      >
                        <Sparkles className="h-4 w-4 mr-2" />
                        {actionId === selected.id ? "Writing…" : "Draft with AI"}
                      </Button>
                    </div>
                  )}

                  {(composing || selected.latest_reply?.status === "draft") && (
                    <div className="w-full max-w-none space-y-3">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-sm font-medium text-content">
                          {selected.latest_reply?.status === "draft" &&
                          selected.latest_reply.model_used !== "manual"
                            ? "AI draft"
                            : "Your reply"}
                        </p>
                        <span className="text-xs text-content-subtle">
                          {selected.latest_reply?.status === "draft"
                            ? selected.latest_reply.model_used
                            : "Manual"}
                        </span>
                      </div>
                      <textarea
                        className={cn(textareaClass, "min-h-[140px] bg-surface")}
                        rows={5}
                        value={draftEdit}
                        onChange={(e) => setDraftEdit(e.target.value)}
                        placeholder="Write your reply…"
                        autoFocus
                      />
                      <div className="flex flex-wrap gap-2">
                        {selected.latest_reply?.status === "draft" ? (
                          <>
                            <Button
                              onClick={() => approveSend(selected.latest_reply!.id)}
                              disabled={
                                !draftEdit.trim() || actionId === selected.latest_reply.id
                              }
                            >
                              <Send className="h-4 w-4 mr-2" />
                              Send
                            </Button>
                            <Button
                              variant="outline"
                              onClick={() => saveDraftEdits(selected.latest_reply!.id)}
                              disabled={actionId === selected.latest_reply.id}
                            >
                              Save
                            </Button>
                            <Button
                              variant="ghost"
                              onClick={() => rejectDraft(selected.latest_reply!.id)}
                              disabled={actionId === selected.latest_reply.id}
                            >
                              Discard
                            </Button>
                          </>
                        ) : (
                          <>
                            <Button
                              onClick={sendManualReply}
                              disabled={
                                !draftEdit.trim() ||
                                !connectedAccount ||
                                actionId === selected.id
                              }
                            >
                              <Send className="h-4 w-4 mr-2" />
                              {actionId === selected.id ? "Sending…" : "Send"}
                            </Button>
                            <Button
                              variant="outline"
                              onClick={() => generateDraft(selected.id)}
                              disabled={
                                !settings?.openai_configured || actionId === selected.id
                              }
                            >
                              <Sparkles className="h-4 w-4 mr-2" />
                              Draft with AI
                            </Button>
                            <Button
                              variant="ghost"
                              onClick={() => {
                                setComposing(false);
                                setDraftEdit("");
                              }}
                            >
                              Cancel
                            </Button>
                          </>
                        )}
                      </div>
                    </div>
                  )}
                </footer>
              </>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center px-8 text-center">
                <div className="h-12 w-12 rounded-full bg-surface-muted flex items-center justify-center mb-4">
                  <Mail className="h-5 w-5 text-content-subtle" />
                </div>
                <p className="text-sm font-medium text-content">Select a conversation</p>
                <p className="text-sm text-content-muted mt-1 max-w-xs leading-relaxed">
                  Read the full thread and review what your assistant did — or draft a reply.
                </p>
              </div>
            )}
          </section>
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
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="w-full min-w-0 max-w-4xl 2xl:max-w-5xl space-y-5">
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
              <AutoGrowTextarea
                className={textareaClass}
                minRows={4}
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
                <AutoGrowTextarea
                  className={textareaClass}
                  minRows={4}
                  placeholder={"Shipping: 3–5 business days.\nReturns within 14 days of delivery.\nFree shipping over $50."}
                  value={settings.policies}
                  onChange={(e) => setSettings({ ...settings, policies: e.target.value })}
                />
              </div>
              <div className="space-y-1.5">
                <label className="block text-sm font-medium text-content">Common questions</label>
                <AutoGrowTextarea
                  className={textareaClass}
                  minRows={4}
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
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="w-full min-w-0 max-w-4xl 2xl:max-w-5xl space-y-5">
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
