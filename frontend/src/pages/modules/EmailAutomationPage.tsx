import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  Mail,
  RefreshCw,
  Sparkles,
  ShoppingBag,
  Truck,
  PackageCheck,
  UserPlus,
  Heart,
  MapPin,
  Send,
} from "lucide-react";
import { useStore } from "@/context/StoreContext";
import { api } from "@/lib/api";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Switch } from "@/components/ui/Switch";
import { RuleActionsMenu } from "@/components/email/RuleActionsMenu";
import {
  TemplateEditorModal,
  type BrandingData,
  type TemplateData,
} from "@/components/email/TemplateEditorModal";
import { eventLabel, previewWithSamples } from "@/lib/emailPersonalization";
import { DEFAULT_THEME_COLOR } from "@/lib/emailLayouts";

type Rule = {
  id: string;
  event_type: string;
  template_id: string;
  template_name: string | null;
  gmail_email: string | null;
  is_enabled: boolean;
};

type EventMeta = { event_type: string; label: string; description: string };

type SendLog = {
  id: string;
  event_type: string;
  recipient: string;
  subject: string;
  status: string;
  sent_at: string;
};

const EVENT_ICONS: Record<string, typeof Mail> = {
  ORDER_PAID: ShoppingBag,
  ORDER_FULFILLED: Truck,
  ORDER_DELIVERED: PackageCheck,
  CUSTOMER_CREATED: UserPlus,
  FIRST_PURCHASE: Sparkles,
  REPEAT_PURCHASE: Heart,
  TRACKING_ADDED: MapPin,
  IN_TRANSIT_UPDATE: Truck,
};

function formatLogTime(iso: string) {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function EmailAutomationPage() {
  const { activeStore } = useStore();
  const [rules, setRules] = useState<Rule[]>([]);
  const [events, setEvents] = useState<EventMeta[]>([]);
  const [logs, setLogs] = useState<SendLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [seeding, setSeeding] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorInitialTab, setEditorInitialTab] = useState<"edit" | "preview">("edit");
  const [editingTemplate, setEditingTemplate] = useState<TemplateData | null>(null);
  const [editingRuleTitle, setEditingRuleTitle] = useState("");
  const [branding, setBranding] = useState<BrandingData>({
    theme_color: DEFAULT_THEME_COLOR,
    logo_url: null,
  });

  const load = useCallback(async () => {
    if (!activeStore?.id) return;
    setLoading(true);
    setError("");
    try {
      const [r, l, ev, br] = await Promise.all([
        api.emailAutomation.rules(activeStore.id),
        api.emailAutomation.sendLogs(activeStore.id),
        api.emailAutomation.events(),
        api.emailAutomation.getBranding(activeStore.id),
      ]);
      setRules(r as Rule[]);
      setLogs(l as SendLog[]);
      setEvents(ev as EventMeta[]);
      setBranding({
        theme_color: br.theme_color || DEFAULT_THEME_COLOR,
        logo_url: br.logo_url,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load automation");
    } finally {
      setLoading(false);
    }
  }, [activeStore?.id]);

  useEffect(() => {
    load();
  }, [load]);

  const seedDefaults = async () => {
    if (!activeStore?.id) return;
    setSeeding(true);
    try {
      await api.emailAutomation.seedDefaults(activeStore.id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load starter emails");
    } finally {
      setSeeding(false);
    }
  };

  const toggleRule = async (rule: Rule, enabled: boolean) => {
    if (!activeStore?.id) return;
    try {
      await api.emailAutomation.updateRule(activeStore.id, rule.id, { is_enabled: enabled });
      setRules((prev) =>
        prev.map((r) => (r.id === rule.id ? { ...r, is_enabled: enabled } : r))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update automation");
    }
  };

  const openTemplateEditor = async (rule: Rule, previewOnly: boolean) => {
    if (!activeStore?.id) return;
    try {
      const t = await api.emailAutomation.getTemplate(activeStore.id, rule.template_id);
      const meta = eventLabel(rule.event_type, events);
      setEditingRuleTitle(meta.label);
      setEditingTemplate({
        id: t.id,
        name: t.name,
        subject: t.subject,
        body_html: t.body_html,
        layout_preset: t.layout_preset || "classic",
      });
      setEditorInitialTab(previewOnly ? "preview" : "edit");
      setEditorOpen(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open email");
    }
  };

  const saveTemplate = async (data: {
    name: string;
    subject: string;
    body_html: string;
    layout_preset: string;
    theme_color: string;
  }) => {
    if (!activeStore?.id || !editingTemplate) return;
    await Promise.all([
      api.emailAutomation.updateTemplate(activeStore.id, editingTemplate.id, {
        name: data.name,
        subject: data.subject,
        body_html: data.body_html,
        layout_preset: data.layout_preset,
      }),
      api.emailAutomation.updateBranding(activeStore.id, { theme_color: data.theme_color }),
    ]);
    setBranding((prev) => ({ ...prev, theme_color: data.theme_color }));
    await load();
  };

  const uploadLogo = async (file: File): Promise<BrandingData> => {
    if (!activeStore?.id) throw new Error("No store selected");
    const br = await api.emailAutomation.uploadLogo(activeStore.id, file);
    const next = { theme_color: br.theme_color, logo_url: br.logo_url };
    setBranding(next);
    return next;
  };

  const removeLogo = async (): Promise<BrandingData> => {
    if (!activeStore?.id) throw new Error("No store selected");
    const br = await api.emailAutomation.removeLogo(activeStore.id);
    const next = { theme_color: br.theme_color, logo_url: br.logo_url };
    setBranding(next);
    return next;
  };

  const activeCount = rules.filter((r) => r.is_enabled).length;
  const sentCount = logs.filter((l) => l.status === "sent").length;

  if (!activeStore) {
    return (
      <div className="max-w-2xl mx-auto">
        <Card padding="lg">
          <CardTitle>Select a store</CardTitle>
          <CardDescription className="mt-2">
            Choose a store from the sidebar, or{" "}
            <Link to="/settings/stores" className="text-brand-600 hover:underline">
              connect your Shopify store
            </Link>{" "}
            to set up email automations.
          </CardDescription>
        </Card>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8 pb-10">
      <Link
        to="/dashboard"
        className="inline-flex items-center gap-1.5 text-sm text-content-muted hover:text-content"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to overview
      </Link>

      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-content flex items-center gap-2">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-500/10 text-brand-600 dark:text-brand-400">
              <Mail className="h-5 w-5" />
            </span>
            Email Automation
          </h1>
          <p className="text-content-muted mt-2 max-w-lg">
            Send the right message automatically when something happens in{" "}
            <strong className="text-content">{activeStore.name}</strong> — orders, shipping,
            and new customers.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-1.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          <Button size="sm" onClick={seedDefaults} isLoading={seeding}>
            Set up starter emails
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <div className="rounded-xl border border-border bg-surface p-4">
          <p className="text-2xl font-semibold text-content">{activeCount}</p>
          <p className="text-xs text-content-muted mt-1">Automations turned on</p>
        </div>
        <div className="rounded-xl border border-border bg-surface p-4">
          <p className="text-2xl font-semibold text-content">{rules.length}</p>
          <p className="text-xs text-content-muted mt-1">Available emails</p>
        </div>
        <div className="rounded-xl border border-border bg-surface p-4 col-span-2 sm:col-span-1">
          <p className="text-2xl font-semibold text-content">{sentCount}</p>
          <p className="text-xs text-content-muted mt-1">Emails sent (recent)</p>
        </div>
      </div>

      {error && (
        <p className="text-sm text-red-600 dark:text-red-400 bg-red-500/10 rounded-xl px-4 py-3">
          {error}
        </p>
      )}

      <section className="space-y-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-lg font-semibold text-content">Your automations</h2>
          <Link
            to="/settings/gmail"
            className="text-sm text-brand-600 hover:underline dark:text-brand-400"
          >
            Manage senders →
          </Link>
        </div>

        {rules.length === 0 ? (
          <Card padding="lg" className="text-center py-12">
            <Mail className="h-10 w-10 text-content-subtle mx-auto mb-3" />
            <CardTitle className="text-lg">No emails set up yet</CardTitle>
            <CardDescription className="mt-2 max-w-sm mx-auto">
              Click &quot;Set up starter emails&quot; to add ready-made messages for orders and
              shipping. You can customize every message before turning them on.
            </CardDescription>
            <Button className="mt-6" onClick={seedDefaults} isLoading={seeding}>
              Set up starter emails
            </Button>
          </Card>
        ) : (
          <ul className="space-y-3">
            {rules.map((rule, i) => {
              const meta = eventLabel(rule.event_type, events);
              const Icon = EVENT_ICONS[rule.event_type] ?? Mail;
              return (
                <motion.li
                  key={rule.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.03 }}
                  className={`rounded-2xl border bg-surface transition-shadow ${
                    rule.is_enabled
                      ? "border-brand-500/30 shadow-sm shadow-brand-500/5"
                      : "border-border"
                  }`}
                >
                  <div className="flex flex-col sm:flex-row sm:items-center gap-4 p-5">
                    <div className="flex items-start gap-4 flex-1 min-w-0">
                      <div
                        className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${
                          rule.is_enabled
                            ? "bg-brand-500/15 text-brand-600 dark:text-brand-400"
                            : "bg-surface-muted text-content-muted"
                        }`}
                      >
                        <Icon className="h-5 w-5" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="font-semibold text-content">{meta.label}</h3>
                          {rule.is_enabled && (
                            <Badge variant="success">Active</Badge>
                          )}
                        </div>
                        <p className="text-sm text-content-muted mt-0.5">{meta.description}</p>
                        <p className="text-xs text-content-subtle mt-2 truncate">
                          {rule.template_name ?? "Email template"}
                          {rule.gmail_email
                            ? ` · Sends from ${rule.gmail_email}`
                            : " · Uses your default sender"}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 sm:shrink-0">
                      <Switch
                        checked={rule.is_enabled}
                        onChange={(on) => toggleRule(rule, on)}
                        label={rule.is_enabled ? "On" : "Off"}
                      />
                      <RuleActionsMenu
                        onEdit={() => openTemplateEditor(rule, false)}
                        onPreview={() => openTemplateEditor(rule, true)}
                      />
                    </div>
                  </div>
                </motion.li>
              );
            })}
          </ul>
        )}
      </section>

      <Card padding="lg">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Send className="h-5 w-5 text-content-muted" />
            Recent activity
          </CardTitle>
          <CardDescription>Emails your automations have tried to send recently.</CardDescription>
        </CardHeader>
        {logs.length === 0 ? (
          <p className="text-sm text-content-muted px-6 pb-6">
            Nothing sent yet. Turn on an automation and trigger a Shopify event (like a new order).
          </p>
        ) : (
          <ul className="divide-y divide-border border-t border-border">
            {logs.slice(0, 15).map((log) => {
              const meta = eventLabel(log.event_type, events);
              return (
                <li
                  key={log.id}
                  className="px-6 py-4 flex flex-wrap items-start justify-between gap-3"
                >
                  <div>
                    <p className="font-medium text-content text-sm">{meta.label}</p>
                    <p className="text-sm text-content-muted mt-0.5">
                      To {log.recipient}
                    </p>
                    <p className="text-xs text-content-subtle mt-1">
                      {previewWithSamples(log.subject, activeStore.name)}
                    </p>
                  </div>
                  <div className="text-right">
                    <Badge
                      variant={
                        log.status === "sent"
                          ? "success"
                          : log.status === "failed"
                            ? "warning"
                            : "muted"
                      }
                    >
                      {log.status === "sent"
                        ? "Sent"
                        : log.status === "failed"
                          ? "Failed"
                          : "Skipped"}
                    </Badge>
                    <p className="text-xs text-content-subtle mt-1">
                      {formatLogTime(log.sent_at)}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <TemplateEditorModal
        key={editingTemplate?.id ?? "closed"}
        open={editorOpen}
        onClose={() => setEditorOpen(false)}
        template={editingTemplate}
        branding={branding}
        automationTitle={editingRuleTitle}
        storeName={activeStore.name}
        initialTab={editorInitialTab}
        onSave={saveTemplate}
        onUploadLogo={uploadLogo}
        onRemoveLogo={removeLogo}
      />
    </div>
  );
}
