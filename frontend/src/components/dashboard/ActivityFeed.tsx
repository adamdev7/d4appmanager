import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Mail, Package, Store, Zap, Inbox, KeyRound, PlugZap } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { BrandLoader } from "@/components/ui/Loading";
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

const CONNECTIONS = [
  { to: "/settings/stores", label: "Stores", icon: Store },
  { to: "/settings/gmail", label: "Gmail", icon: Mail },
  { to: "/settings/meta", label: "Meta", icon: PlugZap },
  { to: "/settings/api-keys", label: "API keys", icon: KeyRound },
] as const;

export function ActivityFeed() {
  const { activeStore, stores } = useStore();
  const [items, setItems] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.dashboard
      .activity(activeStore?.id, 6)
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [activeStore?.id]);

  return (
    <div className="flex min-h-0 flex-col gap-3">
      <Card padding="sm" className="flex min-h-0 flex-1 flex-col">
        <h2 className="mb-2 text-sm font-semibold text-content">Recent activity</h2>
        {loading ? (
          <div className="flex flex-1 items-center justify-center py-8">
            <BrandLoader size="sm" />
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center px-2 py-6 text-center">
            <Inbox className="mb-2 h-7 w-7 text-content-subtle" />
            <p className="text-sm font-medium text-content">No activity yet</p>
            <p className="mt-1 text-xs text-content-muted">
              {stores.length === 0
                ? "Connect a Shopify store to see orders here."
                : "Webhook events appear here as automations run."}
            </p>
          </div>
        ) : (
          <ul className="min-h-0 space-y-0.5 overflow-y-auto">
            {items.map((item) => {
              const Icon = ICONS[item.type] ?? Zap;
              return (
                <li key={item.id} className="flex gap-2.5 rounded-lg px-1 py-1.5">
                  <div
                    className={cn(
                      "flex h-7 w-7 shrink-0 items-center justify-center rounded-md",
                      item.type === "email" && "bg-blue-500/10 text-blue-600",
                      item.type === "order" && "bg-violet-500/10 text-violet-600",
                      item.type === "store" && "bg-brand-500/10 text-brand-600",
                      item.type === "system" && "bg-amber-500/10 text-amber-600"
                    )}
                  >
                    <Icon className="h-3.5 w-3.5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-content">{item.title}</p>
                    <p className="truncate text-xs text-content-muted">{item.description}</p>
                  </div>
                  <span className="shrink-0 text-[11px] text-content-subtle">{item.timestamp}</span>
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <Card padding="sm">
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-content-subtle">
          Connections
        </p>
        <div className="grid grid-cols-2 gap-1.5">
          {CONNECTIONS.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className="inline-flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-content-muted hover:bg-surface-muted hover:text-content"
            >
              <item.icon className="h-3.5 w-3.5" />
              {item.label}
            </Link>
          ))}
        </div>
      </Card>
    </div>
  );
}
