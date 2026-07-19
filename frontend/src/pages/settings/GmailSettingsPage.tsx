import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { Mail, Plus, Unplug, Star, CheckCircle } from "lucide-react";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { Switch } from "@/components/ui/Switch";
import { api } from "@/lib/api";
import { useStore } from "@/context/StoreContext";
import type { GmailAccount } from "@/types";

export function GmailSettingsPage() {
  const { activeStore } = useStore();
  const [searchParams, setSearchParams] = useSearchParams();
  const [accounts, setAccounts] = useState<GmailAccount[]>([]);
  const [trackOpens, setTrackOpens] = useState(false);
  const [trackClicks, setTrackClicks] = useState(false);
  const [signature, setSignature] = useState("");
  const [replyTo, setReplyTo] = useState("");
  const [dailyLimit, setDailyLimit] = useState("500");
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState("");
  const connected = searchParams.get("connected") === "1";

  const load = async () => {
    try {
      const data = await api.gmail.accounts(activeStore?.id);
      setAccounts(data as GmailAccount[]);
      const s = await api.gmail.settings(activeStore?.id);
      setTrackOpens(s.track_opens);
      setTrackClicks(s.track_clicks);
      setSignature(s.signature_html);
      setReplyTo(s.reply_to ?? "");
      setDailyLimit(String(s.daily_send_limit));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load Gmail settings");
    }
  };

  useEffect(() => {
    load();
  }, [activeStore?.id]);

  useEffect(() => {
    if (connected) {
      load();
      const t = setTimeout(() => {
        searchParams.delete("connected");
        searchParams.delete("account_id");
        setSearchParams(searchParams, { replace: true });
      }, 5000);
      return () => clearTimeout(t);
    }
  }, [connected]);

  const handleConnectGmail = async () => {
    setError("");
    setConnecting(true);
    try {
      const { authorize_url } = await api.gmail.oauthAuthorize(activeStore?.id);
      window.location.href = authorize_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start Google authorization");
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnect = async (id: string) => {
    await api.gmail.disconnect(id);
    await load();
  };

  const handleSaveSettings = async () => {
    await api.gmail.updateSettings(
      {
        reply_to: replyTo || null,
        signature_html: signature,
        track_opens: trackOpens,
        track_clicks: trackClicks,
        daily_send_limit: parseInt(dailyLimit, 10) || 500,
      },
      activeStore?.id
    );
  };

  return (
    <div className="max-w-3xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-content">Gmail & email</h1>
        <p className="text-content-muted mt-1">
          Connect Gmail via Google OAuth for sending automation email.
          {activeStore && (
            <span className="block mt-1 text-sm">
              Active store: <strong className="text-content">{activeStore.name}</strong>
            </span>
          )}
        </p>
      </div>

      {connected && (
        <div className="flex items-center gap-2 rounded-lg border border-brand-500/30 bg-brand-500/10 px-4 py-3 text-sm text-brand-700 dark:text-brand-400">
          <CheckCircle className="h-4 w-4 shrink-0" />
          Gmail account connected successfully.
        </div>
      )}

      {error && <p className="text-sm text-red-500">{error}</p>}

      <Card padding="lg" className="border-dashed">
        <div className="flex flex-col sm:flex-row sm:items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-red-500/10">
            <Mail className="h-6 w-6 text-red-500" />
          </div>
          <div className="flex-1">
            <CardTitle>Connect Gmail</CardTitle>
            <CardDescription>
              Authorize Google to send emails. You will be redirected to Google sign-in.
            </CardDescription>
          </div>
          <Button onClick={handleConnectGmail} isLoading={connecting}>
            <Plus className="h-4 w-4" />
            Connect Gmail
          </Button>
        </div>
      </Card>

      <section>
        <h2 className="text-lg font-semibold text-content mb-4">Sender accounts</h2>
        {accounts.length === 0 && (
          <p className="text-sm text-content-muted">No Gmail accounts connected.</p>
        )}
        <div className="space-y-3">
          {accounts.map((account, i) => (
            <motion.div
              key={account.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
            >
              <Card padding="lg">
                <div className="flex items-start gap-4">
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-surface-muted text-sm font-semibold text-content">
                    {account.display_name.charAt(0)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-medium text-content">{account.display_name}</p>
                      {account.is_default_sender && (
                        <Badge variant="brand">
                          <Star className="h-3 w-3 mr-0.5" />
                          Default
                        </Badge>
                      )}
                      <Badge
                        variant={account.status === "connected" ? "success" : "muted"}
                        className="capitalize"
                      >
                        {account.status}
                      </Badge>
                    </div>
                    <p className="text-sm text-content-muted">{account.email}</p>
                  </div>
                  {account.status === "connected" && (
                    <Button size="sm" variant="outline" onClick={() => handleDisconnect(account.id)}>
                      <Unplug className="h-3.5 w-3.5" />
                      Disconnect
                    </Button>
                  )}
                  {account.status !== "connected" && (
                    <Button size="sm" variant="primary" onClick={handleConnectGmail}>
                      Reconnect
                    </Button>
                  )}
                </div>
              </Card>
            </motion.div>
          ))}
        </div>
      </section>

      <Card padding="lg">
        <CardHeader>
          <CardTitle>Email settings</CardTitle>
          <CardDescription>Defaults for the active store.</CardDescription>
        </CardHeader>
        <div className="space-y-5">
          <Input
            label="Reply-to address"
            type="email"
            value={replyTo}
            onChange={(e) => setReplyTo(e.target.value)}
          />
          <div>
            <label className="block text-sm font-medium text-content mb-1.5">
              Email signature (HTML)
            </label>
            <textarea
              value={signature}
              onChange={(e) => setSignature(e.target.value)}
              rows={4}
              className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-brand-500/30"
            />
          </div>
          <Input
            label="Daily send limit"
            type="number"
            value={dailyLimit}
            onChange={(e) => setDailyLimit(e.target.value)}
          />
          <Switch checked={trackOpens} onChange={setTrackOpens} label="Track email opens" />
          <Switch checked={trackClicks} onChange={setTrackClicks} label="Track link clicks" />
          <Button onClick={handleSaveSettings}>Save email settings</Button>
        </div>
      </Card>
    </div>
  );
}
