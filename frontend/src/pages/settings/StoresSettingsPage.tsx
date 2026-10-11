import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useStore } from "@/context/StoreContext";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Store, Plus, CheckCircle, Unplug, Trash2, ExternalLink } from "lucide-react";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import type { Store as StoreType } from "@/types";

export function StoresSettingsPage() {
  const { stores, activeStore, setActiveStoreId, refresh } = useStore();
  const [searchParams, setSearchParams] = useSearchParams();
  const [showConnect, setShowConnect] = useState(false);
  const [installUrl, setInstallUrl] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [claimedName, setClaimedName] = useState("");
  const claimStarted = useRef(false);
  const connected = searchParams.get("connected") === "1" || Boolean(claimedName);
  const claim = searchParams.get("shopify_claim");

  useEffect(() => {
    api.stores
      .shopifyInstallLink()
      .then(({ url }) => setInstallUrl(url))
      .catch(() => setInstallUrl(null));
  }, []);

  useEffect(() => {
    if (!claim || claimStarted.current) return;
    claimStarted.current = true;
    api.stores
      .claimShopifyInstall(claim)
      .then(async (store) => {
        setClaimedName(store.name);
        await refresh();
        setActiveStoreId(store.id);
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not finish connecting your Shopify store")
      )
      .finally(() => {
        searchParams.delete("shopify_claim");
        setSearchParams(searchParams, { replace: true });
      });
  }, [claim, refresh, searchParams, setActiveStoreId, setSearchParams]);

  useEffect(() => {
    if (connected) {
      refresh();
      const t = setTimeout(() => {
        searchParams.delete("connected");
        searchParams.delete("store_id");
        setSearchParams(searchParams, { replace: true });
        setClaimedName("");
      }, 5000);
      return () => clearTimeout(t);
    }
  }, [connected, refresh, searchParams, setSearchParams]);

  const handleDisconnect = async (store: StoreType) => {
    setError("");
    setBusyId(store.id);
    try {
      await api.stores.disconnect(store.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not disconnect store");
    } finally {
      setBusyId(null);
    }
  };

  const handleReconnect = async (store: StoreType) => {
    setError("");
    setBusyId(store.id);
    try {
      const { authorize_url } = await api.stores.shopifyReauthorize(store.id);
      window.location.href = authorize_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start Shopify reconnection");
      setBusyId(null);
    }
  };

  const handleDelete = async (store: StoreType) => {
    const ok = window.confirm(
      `Remove ${store.name} (${store.domain}) from App Manager? Related automation, tracking, and analytics data for this store will be deleted. You can connect it again later.`
    );
    if (!ok) return;
    setError("");
    setBusyId(store.id);
    try {
      await api.stores.delete(store.id);
      if (activeStore?.id === store.id) {
        localStorage.removeItem("active_store_id");
      }
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete store");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="w-full min-w-0 max-w-4xl 2xl:max-w-5xl space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-content">Stores</h1>
          <p className="text-content-muted mt-1">
            Install App Manager from Shopify to connect a store. Webhooks register automatically on
            connect.
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
          {claimedName ? `${claimedName} is connected.` : "Shopify store connected successfully."}
        </div>
      )}

      {error && <p className="text-sm text-red-500">{error}</p>}

      {showConnect && (
        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}>
          <Card padding="lg" className="border-brand-500/30 bg-brand-500/5">
            <CardHeader>
              <CardTitle>Connect Shopify store</CardTitle>
              <CardDescription>
                Install App Manager from Shopify and approve access. Shopify brings you back here
                and the store is added to this account.
              </CardDescription>
            </CardHeader>
            {installUrl ? (
              <Button onClick={() => (window.location.href = installUrl)}>
                <ExternalLink className="h-4 w-4" />
                Install from Shopify
              </Button>
            ) : (
              <p className="text-sm text-content-muted">
                Open App Manager from the Shopify App Store or from Apps in your Shopify admin to
                install it on a store.
              </p>
            )}
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
                      className="capitalize"
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
                <div className="flex flex-wrap items-center justify-end gap-2 shrink-0">
                  {store.id !== activeStore?.id && store.status === "connected" && (
                    <Button size="sm" variant="outline" onClick={() => setActiveStoreId(store.id)}>
                      Set active
                    </Button>
                  )}
                  {store.status === "connected" ? (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busyId === store.id}
                      isLoading={busyId === store.id}
                      onClick={() => handleDisconnect(store)}
                    >
                      <Unplug className="h-3.5 w-3.5" />
                      Disconnect
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      variant="primary"
                      disabled={busyId === store.id}
                      isLoading={busyId === store.id}
                      onClick={() => handleReconnect(store)}
                    >
                      Reconnect
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Delete ${store.name}`}
                    title="Delete store"
                    disabled={busyId === store.id}
                    onClick={() => handleDelete(store)}
                    className="text-red-500 hover:text-red-600 hover:bg-red-500/10"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </Card>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
