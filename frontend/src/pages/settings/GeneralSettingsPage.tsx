import { useEffect, useState } from "react";
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
  const { user } = useAuth();
  const [emailNotifs, setEmailNotifs] = useState(true);
  const [weeklyDigest, setWeeklyDigest] = useState(false);
  const [whatsapp, setWhatsapp] = useState<WhatsAppConnection | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm());
  const [busy, setBusy] = useState(false);
  const [testOk, setTestOk] = useState("");
  const [error, setError] = useState("");

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

  const saveAndTest = async () => {
    setBusy(true);
    setError("");
    setTestOk("");
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
          <Input label="Full name" defaultValue={user?.full_name} />
          <Input label="Email" type="email" defaultValue={user?.email} disabled />
        </div>
        <Button className="mt-6" variant="primary">
          Save changes
        </Button>
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
        busy={busy}
        editingId={editingId}
        form={form}
        onFormChange={(patch) => setForm((f) => ({ ...f, ...patch }))}
        onStartAdd={() => {
          setEditingId("new");
          setForm(emptyForm());
          setError("");
          setTestOk("");
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
    </div>
  );
}
