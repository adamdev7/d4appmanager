import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useStore } from "@/context/StoreContext";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { Store, Plus, CheckCircle } from "lucide-react";
import { motion } from "framer-motion";
import { api } from "@/lib/api";

export function StoresSettingsPage() {
  const { stores, activeStore, setActiveStoreId, refresh } = useStore();
  const [searchParams, setSearchParams] = useSearchParams();
  const [showConnect, setShowConnect] = useState(false);
  const [shopDomain, setShopDomain] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState("");
  const connected = searchParams.get("connected") === "1";

  useEffect(() => {
    if (connected) {
      refresh();
      const t = setTimeout(() => {
        searchParams.delete("connected");
        searchParams.delete("store_id");
        setSearchParams(searchParams, { replace: true });
      }, 5000);
      return () => clearTimeout(t);
    }
  }, [connected, refresh, searchParams, setSearchParams]);

  const handleConnectShopify = async () => {
    setError("");
    setConnecting(true);
    try {
      const shop = shopDomain.trim();
      if (!shop) {
        setError("Enter your store domain");
        return;
      }
      const { authorize_url } = await api.stores.shopifyInstall(shop);
      window.location.href = authorize_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start Shopify authorization");
    } finally {
      setConnecting(false);
    }
  };

  return (
    <div className="max-w-3xl space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-content">Stores</h1>
          <p className="text-content-muted mt-1">
            Connect Shopify stores via OAuth. Webhooks register automatically on connect.
          </p>
        </div>
        <Button onClick={() => setShowConnect(!showConnect)} variant="primary">
          <Plus className="h-4 w-4" />
          Connect store
        </Button>
      </div>

      {connected && (
        <div className="flex items-center gap-2 rounded-lg border border-brand-500/30 bg-brand-500/10 px-4 py-3 text-sm text-brand-700 dark:text-brand-400">
          <CheckCircle className="h-4 w-4 shrink-0" />
          Shopify store connected successfully.
        </div>
      )}

      {showConnect && (
        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}>
          <Card padding="lg" className="border-brand-500/30 bg-brand-500/5">
            <CardHeader>
              <CardTitle>Connect Shopify store</CardTitle>
              <CardDescription>
                Enter your <code className="text-xs">myshopify.com</code> domain. You will be
                redirected to Shopify to approve access.
              </CardDescription>
            </CardHeader>
            <div className="flex flex-col sm:flex-row gap-3">
              <Input
                className="flex-1"
                placeholder="your-store.myshopify.com"
                value={shopDomain}
                onChange={(e) => setShopDomain(e.target.value)}
              />
              <Button onClick={handleConnectShopify} isLoading={connecting}>
                Authorize with Shopify
              </Button>
            </div>
            {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
            <p className="mt-3 text-xs text-content-subtle">
              For local dev, set <code>APP_URL</code> to your public URL (e.g. ngrok) so Shopify
              can reach OAuth and webhooks.
            </p>
          </Card>
        </motion.div>
      )}

      {stores.length === 0 && (
        <Card padding="lg">
          <p className="text-content-muted text-sm">No stores connected yet.</p>
        </Card>
      )}

      <div className="space-y-3">
        {stores.map((store, i) => (
          <motion.div
            key={store.id}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
          >
            <Card
              padding="lg"
              className={store.id === activeStore?.id ? "ring-2 ring-brand-500/30" : ""}
            >
              <div className="flex items-start gap-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-surface-muted">
                  <Store className="h-6 w-6 text-content-muted" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="font-semibold text-content">{store.name}</h3>
                    <Badge
                      variant={
                        store.status === "connected"
                          ? "success"
                          : store.status === "pending"
                            ? "warning"
                            : "muted"
                      }
                    >
                      {store.status}
                    </Badge>
                  </div>
                  <p className="text-sm text-content-muted mt-0.5">{store.domain}</p>
                  <div className="mt-2 flex flex-wrap gap-3 text-xs text-content-subtle">
                    <span>Plan: {store.plan}</span>
                    <span>·</span>
                    <span>{store.timezone}</span>
                    <span>·</span>
                    <span>{store.currency}</span>
                  </div>
                </div>
                <div className="flex flex-col gap-2 shrink-0">
                  {store.id !== activeStore?.id && (
                    <Button size="sm" variant="outline" onClick={() => setActiveStoreId(store.id)}>
                      Set active
                    </Button>
                  )}
                </div>
              </div>
            </Card>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
