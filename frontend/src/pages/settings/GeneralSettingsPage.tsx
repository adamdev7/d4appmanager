import { useEffect, useState } from "react";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Switch } from "@/components/ui/Switch";
import { Button } from "@/components/ui/Button";
import { WhatsAppAlertsCard } from "@/components/settings/WhatsAppAlertsCard";
import { useAuth } from "@/context/AuthContext";
import { api, type WhatsAppConnection } from "@/lib/api";

export function GeneralSettingsPage() {
  const { user } = useAuth();
  const [emailNotifs, setEmailNotifs] = useState(true);
  const [weeklyDigest, setWeeklyDigest] = useState(false);
  const [whatsapp, setWhatsapp] = useState<WhatsAppConnection | null>(null);
  const [phone, setPhone] = useState("");
  const [keyInput, setKeyInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testOk, setTestOk] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api.notifications
      .getWhatsApp()
      .then((data) => {
        setWhatsapp(data);
        setPhone(data.whatsapp_phone || "");
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load WhatsApp settings"));
  }, []);

  const saveAndTest = async () => {
    setSaving(true);
    setTesting(true);
    setError("");
    setTestOk("");
    try {
      const result = await api.notifications.testWhatsApp({
        phone,
        api_key: keyInput.trim() || undefined,
      });
      setWhatsapp(result);
      setPhone(result.whatsapp_phone || phone);
      setKeyInput("");
      setTestOk(result.message);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save or send a test WhatsApp");
      try {
        const refreshed = await api.notifications.getWhatsApp();
        setWhatsapp(refreshed);
        setPhone(refreshed.whatsapp_phone || phone);
      } catch {
        /* keep current form values */
      }
    } finally {
      setSaving(false);
      setTesting(false);
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
        phone={phone}
        onPhoneChange={setPhone}
        configured={Boolean(whatsapp?.whatsapp_configured)}
        apiKeyHint={whatsapp?.whatsapp_api_key_hint ?? null}
        lastError={whatsapp?.whatsapp_last_error ?? null}
        error={error}
        setupUrl={whatsapp?.whatsapp_setup_url}
        allowMessage={whatsapp?.whatsapp_allow_message}
        connectedModules={whatsapp?.whatsapp_connected_modules}
        keyInput={keyInput}
        onKeyInputChange={setKeyInput}
        onSaveAndTest={saveAndTest}
        saving={saving}
        testing={testing}
        testOk={testOk}
      />
    </div>
  );
}
