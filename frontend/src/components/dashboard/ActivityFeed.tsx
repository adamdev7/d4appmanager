import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Mail, Package, Store, Zap, Inbox } from "lucide-react";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { api } from "@/lib/api";
import { useStore } from "@/context/StoreContext";
import { cn } from "@/lib/cn";

type Activity = {
  id: string;
  title: string;
  description: string;
  timestamp: string;
  type: string;
};

const ICONS: Record<string, typeof Mail> = {
  email: Mail,
  order: Package,
  store: Store,
  system: Zap,
};

export function ActivityFeed() {
  const { activeStore, stores } = useStore();
  const [items, setItems] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.dashboard
      .activity(activeStore?.id)
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [activeStore?.id]);

  return (
    <Card padding="lg">
      <CardHeader>
        <CardTitle>Recent activity</CardTitle>
      </CardHeader>
      {loading ? (
        <p className="text-sm text-content-subtle px-3 py-4">Loading…</p>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-10 px-4 text-center">
          <Inbox className="h-10 w-10 text-content-subtle mb-3" />
          <p className="text-sm font-medium text-content">No activity yet</p>
          <p className="text-xs text-content-muted mt-1 max-w-[240px]">
            {stores.length === 0
              ? "Connect a Shopify store to see orders and webhook events here."
              : "Shopify webhooks and email send logs will show up as your automations run."}
          </p>
        </div>
      ) : (
        <ul className="space-y-1">
          {items.map((item, i) => {
            const Icon = ICONS[item.type] ?? Zap;
            return (
              <motion.li
                key={item.id}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.04 }}
                className="flex gap-3 rounded-lg p-3 hover:bg-surface-muted transition-colors"
              >
                <div
                  className={cn(
                    "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
                    item.type === "email" && "bg-blue-500/10 text-blue-600",
                    item.type === "order" && "bg-violet-500/10 text-violet-600",
                    item.type === "store" && "bg-brand-500/10 text-brand-600",
                    item.type === "system" && "bg-amber-500/10 text-amber-600"
                  )}
                >
                  <Icon className="h-4 w-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-content">{item.title}</p>
                  <p className="text-xs text-content-muted truncate">{item.description}</p>
                </div>
                <span className="text-xs text-content-subtle shrink-0">{item.timestamp}</span>
              </motion.li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
