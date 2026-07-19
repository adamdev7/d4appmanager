import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Switch } from "@/components/ui/Switch";
import { Button } from "@/components/ui/Button";
import { useState } from "react";
import { useAuth } from "@/context/AuthContext";

export function GeneralSettingsPage() {
  const { user } = useAuth();
  const [emailNotifs, setEmailNotifs] = useState(true);
  const [weeklyDigest, setWeeklyDigest] = useState(false);

  return (
    <div className="max-w-2xl space-y-6">
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
    </div>
  );
}
