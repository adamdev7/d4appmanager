import { useState, useRef, useEffect } from "react";
import { ChevronDown, Plus, Store, Check } from "lucide-react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { useStore } from "@/context/StoreContext";
import { cn } from "@/lib/cn";
import { Badge } from "@/components/ui/Badge";

export function StoreSwitcher({ compact }: { compact?: boolean }) {
  const { stores, activeStore, setActiveStoreId } = useStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  if (!activeStore) return null;

  const statusVariant = (s: string) =>
    s === "connected" ? "success" : s === "pending" ? "warning" : "muted";

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={cn(
          "flex items-center gap-2 rounded-lg border border-border bg-surface hover:bg-surface-muted transition-colors",
          compact ? "h-9 px-2.5" : "h-10 px-3 min-w-[200px]"
        )}
      >
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-brand-500/10 text-brand-600 dark:text-brand-400">
          <Store className="h-3.5 w-3.5" />
        </div>
        {!compact && (
          <div className="flex-1 text-left min-w-0">
            <p className="text-sm font-medium text-content truncate">{activeStore.name}</p>
            <p className="text-xs text-content-subtle truncate">{activeStore.domain}</p>
          </div>
        )}
        <ChevronDown
          className={cn("h-4 w-4 text-content-subtle shrink-0 transition-transform", open && "rotate-180")}
        />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98 }}
            transition={{ duration: 0.15 }}
            className={cn(
              "absolute top-full z-50 mt-2 w-72 max-w-[calc(100vw-1.5rem)] rounded-xl border border-border bg-surface shadow-elevated overflow-hidden",
              compact ? "right-0" : "left-0"
            )}
          >
            <div className="p-2 border-b border-border">
              <p className="px-2 py-1 text-xs font-medium text-content-subtle uppercase tracking-wider">
                Your stores
              </p>
            </div>
            <ul className="max-h-64 overflow-y-auto p-1">
              {stores.map((store) => (
                <li key={store.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setActiveStoreId(store.id);
                      setOpen(false);
                    }}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-lg px-2 py-2.5 text-left hover:bg-surface-muted transition-colors",
                      store.id === activeStore.id && "bg-brand-500/5"
                    )}
                  >
                    <div className="flex h-8 w-8 items-center justify-center rounded-md bg-surface-muted">
                      <Store className="h-4 w-4 text-content-muted" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-content truncate">{store.name}</p>
                      <p className="text-xs text-content-subtle truncate">{store.domain}</p>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <Badge variant={statusVariant(store.status)} className="capitalize text-[10px]">
                        {store.status}
                      </Badge>
                      {store.id === activeStore.id && (
                        <Check className="h-4 w-4 text-brand-600" />
                      )}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
            <div className="p-2 border-t border-border">
              <Link
                to="/settings/stores"
                onClick={() => setOpen(false)}
                className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-sm text-content-muted hover:bg-surface-muted hover:text-content transition-colors"
              >
                <Plus className="h-4 w-4" />
                Connect new store
              </Link>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
