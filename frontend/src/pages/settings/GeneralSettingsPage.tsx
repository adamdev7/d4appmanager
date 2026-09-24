import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Switch } from "@/components/ui/Switch";
import { Button } from "@/components/ui/Button";
import { WhatsAppAlertsCard } from "@/components/settings/WhatsAppAlertsCard";
import { useAuth } from "@/context/AuthContext";
import { api, type WhatsAppConnection, type WhatsAppRecipient } from "@/lib/api";

type FormState = {
  id?: string;
  label: string;
  phone: string;
  apiKey: string;
};

const emptyForm = (): FormState => ({ label: "", phone: "", apiKey: "" });

export function GeneralSettingsPage() {
  const { user, updateUser } = useAuth();
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [emailNotifs, setEmailNotifs] = useState(user?.email_notifications ?? true);
  const [weeklyDigest, setWeeklyDigest] = useState(user?.weekly_digest ?? false);
  const [whatsapp, setWhatsapp] = useState<WhatsAppConnection | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm());
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testOk, setTestOk] = useState("");
  const [saveOk, setSaveOk] = useState("");
  const [error, setError] = useState("");
  const [saveError, setSaveError] = useState("");

  const connections: WhatsAppRecipient[] = whatsapp?.whatsapp_connections?.length
    ? whatsapp.whatsapp_connections
    : whatsapp?.whatsapp_configured
      ? [
          {
            id: "legacy",
            label: "",
            phone: whatsapp.whatsapp_phone || "",
            api_key_hint: whatsapp.whatsapp_api_key_hint,
            last_error: whatsapp.whatsapp_last_error,
            configured: true,
          },
        ]
      : [];

  useEffect(() => {
    if (!user) return;
    setFullName(user.full_name ?? "");
    setEmailNotifs(user.email_notifications ?? true);
    setWeeklyDigest(user.weekly_digest ?? false);
  }, [user]);

  useEffect(() => {
    api.notifications
      .getWhatsApp()
      .then((data) => {
        setWhatsapp(data);
        const list = data.whatsapp_connections ?? [];
        if (list.length === 0 && !data.whatsapp_configured) {
          setEditingId("new");
          setForm(emptyForm());
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load WhatsApp settings"));
  }, []);

  const applyResult = (data: WhatsAppConnection, message?: string) => {
    setWhatsapp(data);
    setForm(emptyForm());
    setEditingId(null);
    if (message) setTestOk(message);
  };

  const whatsappFormHasInput =
    editingId !== null &&
    (form.phone.trim().length > 0 || form.apiKey.trim().length > 0 || form.label.trim().length > 0);

  const saveWhatsAppDraft = async () => {
    if (!whatsappFormHasInput) return;
    const isNew = editingId === "new";
    const missingKey = isNew && !form.apiKey.trim();
    if (!form.phone.trim() || missingKey) {
      throw new Error(
        isNew
          ? "Enter a WhatsApp number and CallMeBot API key before saving."
          : "Enter a WhatsApp number before saving."
      );
    }
    const payload = {
      id: form.id,
      phone: form.phone,
      api_key: form.apiKey.trim() || undefined,
      label: form.label.trim() || undefined,
    };
    const data = await api.notifications.saveWhatsApp(payload);
    applyResult(data);
  };

  const saveAll = async () => {
    setSaving(true);
    setSaveError("");
    setSaveOk("");
    setTestOk("");
    try {
      const name = fullName.trim();
      if (!name) {
        throw new Error("Full name cannot be empty.");
      }
      const updated = await api.auth.updateProfile({
        full_name: name,
        email_notifications: emailNotifs,
        weekly_digest: weeklyDigest,
      });
      updateUser(updated);
      await saveWhatsAppDraft();
      setSaveOk("All general settings saved.");
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Could not save general settings");
    } finally {
      setSaving(false);
    }
  };

  const saveAndTest = async () => {
    setBusy(true);
    setError("");
    setTestOk("");
    setSaveOk("");
    try {
      const payload = {
        id: form.id,
        phone: form.phone,
        api_key: form.apiKey.trim() || undefined,
        label: form.label.trim() || undefined,
      };
      const result = await api.notifications.testWhatsApp(payload);
      applyResult(result, result.message);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save or send a test WhatsApp");
      try {
        const refreshed = await api.notifications.getWhatsApp();
        setWhatsapp({ ...refreshed, whatsapp_last_error: null });
      } catch {
        /* keep form */
      }
    } finally {
      setBusy(false);
    }
  };

  const testExisting = async (id: string) => {
    setBusy(true);
    setError("");
    setTestOk("");
    setSaveOk("");
    try {
      const result = await api.notifications.testWhatsApp({ id });
      applyResult(result, result.message);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not send a test WhatsApp");
      try {
        const refreshed = await api.notifications.getWhatsApp();
        setWhatsapp({ ...refreshed, whatsapp_last_error: null });
      } catch {
        /* ignore */
      }
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    if (!window.confirm("Remove this WhatsApp number? Alerts will stop going to it.")) return;
    setBusy(true);
    setError("");
    setTestOk("");
    setSaveOk("");
    try {
      const data = await api.notifications.deleteWhatsApp(id);
      setWhatsapp(data);
      if ((data.whatsapp_connections?.length ?? 0) === 0) {
        setEditingId("new");
        setForm(emptyForm());
      } else if (editingId === id) {
        setEditingId(null);
        setForm(emptyForm());
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not remove WhatsApp number");
    } finally {
      setBusy(false);
    }
  };

  const pageBusy = busy || saving;

  return (
    <div className="w-full min-w-0 max-w-4xl 2xl:max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-content">General settings</h1>
        <p className="text-content-muted mt-1">Manage your account and workspace preferences.</p>
      </div>

      <Card padding="lg">
        <CardHeader>
          <CardTitle>Profile</CardTitle>
          <CardDescription>Your personal account information.</CardDescription>
        </CardHeader>
        <div className="space-y-4">
          <Input
            label="Full name"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            autoComplete="name"
          />
          <Input label="Email" type="email" defaultValue={user?.email} disabled />
        </div>
      </Card>

      <Card padding="lg">
        <CardHeader>
          <CardTitle>Notifications</CardTitle>
          <CardDescription>Choose what you want to be notified about.</CardDescription>
        </CardHeader>
        <div className="space-y-6">
          <Switch
            checked={emailNotifs}
            onChange={setEmailNotifs}
            label="Email notifications"
            description="Order alerts, automation failures, and system updates."
          />
          <Switch
            checked={weeklyDigest}
            onChange={setWeeklyDigest}
            label="Weekly digest"
            description="Summary of performance across all stores."
          />
        </div>
      </Card>

      <WhatsAppAlertsCard
        connections={connections}
        maxConnections={whatsapp?.whatsapp_max_connections ?? 5}
        setupUrl={whatsapp?.whatsapp_setup_url}
        allowMessage={whatsapp?.whatsapp_allow_message}
        connectedModules={whatsapp?.whatsapp_connected_modules}
        error={error}
        testOk={testOk}
        busy={pageBusy}
        editingId={editingId}
        form={form}
        onFormChange={(patch) => setForm((f) => ({ ...f, ...patch }))}
        onStartAdd={() => {
          setEditingId("new");
          setForm(emptyForm());
          setError("");
          setTestOk("");
          setSaveOk("");
        }}
        onStartEdit={(row) => {
          setEditingId(row.id);
          setForm({
            id: row.id === "legacy" ? undefined : row.id,
            label: row.label || "",
            phone: row.phone || "",
            apiKey: "",
          });
          setError("");
          setTestOk("");
          setSaveOk("");
        }}
        onCancelForm={() => {
          setEditingId(null);
          setForm(emptyForm());
          setError("");
        }}
        onSaveAndTest={saveAndTest}
        onTestExisting={testExisting}
        onRemove={remove}
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between pt-2 pb-4">
        <div className="min-h-[1.25rem] space-y-1">
          {saveError ? (
            <p className="text-sm text-red-600 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
              {saveError}
            </p>
          ) : null}
          {saveOk ? (
            <span className="text-sm text-green-600 dark:text-green-400 flex items-center gap-1">
              <Check className="h-4 w-4" /> {saveOk}
            </span>
          ) : null}
        </div>
        <Button
          type="button"
          variant="primary"
          className="sm:ml-auto shrink-0"
          disabled={pageBusy}
          onClick={() => void saveAll()}
        >
          {saving ? "Saving…" : "Save changes"}
        </Button>
      </div>
    </div>
  );
}
