import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import type { Store } from "@/types";

interface StoreContextValue {
  stores: Store[];
  activeStore: Store | null;
  setActiveStoreId: (id: string) => void;
  isLoading: boolean;
  refresh: () => Promise<void>;
}

const StoreContext = createContext<StoreContextValue | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [stores, setStores] = useState<Store[]>([]);
  const [activeStoreId, setActiveStoreId] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!isAuthenticated) {
      setStores([]);
      return;
    }
    setIsLoading(true);
    try {
      const data = await api.stores.list();
      const mapped = data.map((s) => ({
        id: s.id,
        name: s.name,
        domain: s.domain,
        status: s.status as Store["status"],
        plan: s.plan,
        timezone: s.timezone,
        currency: s.currency,
      }));
      setStores(mapped);
      if (mapped.length && !mapped.find((s) => s.id === activeStoreId)) {
        const saved = localStorage.getItem("active_store_id");
        const next = mapped.find((s) => s.id === saved)?.id ?? mapped[0].id;
        setActiveStoreId(next);
        localStorage.setItem("active_store_id", next);
      }
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated, activeStoreId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const setActiveStoreIdHandler = (id: string) => {
    setActiveStoreId(id);
    localStorage.setItem("active_store_id", id);
  };

  const activeStore = stores.find((s) => s.id === activeStoreId) ?? stores[0] ?? null;

  return (
    <StoreContext.Provider
      value={{
        stores,
        activeStore,
        setActiveStoreId: setActiveStoreIdHandler,
        isLoading,
        refresh,
      }}
    >
      {children}
    </StoreContext.Provider>
  );
}

export function useStore() {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("useStore must be used within StoreProvider");
  return ctx;
}
