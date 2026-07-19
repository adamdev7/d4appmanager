import { Bell, Moon, Sun, Search, LogOut, User } from "lucide-react";
import { useTheme } from "@/context/ThemeContext";
import { useAuth } from "@/context/AuthContext";
import { useNavigate } from "react-router-dom";
import { StoreSwitcher } from "@/components/stores/StoreSwitcher";
import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/cn";

export function TopNavbar({ title }: { title?: string }) {
  const { resolved, toggle } = useTheme();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-4 border-b border-border glass px-6">
      {title && (
        <h1 className="text-lg font-semibold text-content hidden sm:block">{title}</h1>
      )}

      <div className="flex-1 max-w-md hidden md:block">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-content-subtle" />
          <input
            type="search"
            placeholder="Search orders, automations..."
            className="w-full h-9 pl-9 pr-4 rounded-lg border border-border bg-surface-muted text-sm placeholder:text-content-subtle focus:outline-none focus:ring-2 focus:ring-brand-500/30"
          />
        </div>
      </div>

      <div className="flex items-center gap-2 ml-auto">
        <div className="lg:hidden">
          <StoreSwitcher compact />
        </div>

        <button
          type="button"
          className="relative flex h-9 w-9 items-center justify-center rounded-lg text-content-muted hover:bg-surface-muted hover:text-content transition-colors"
          aria-label="Notifications"
        >
          <Bell className="h-4 w-4" />
          <span className="absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-brand-500 ring-2 ring-surface" />
        </button>

        <button
          type="button"
          onClick={toggle}
          className="flex h-9 w-9 items-center justify-center rounded-lg text-content-muted hover:bg-surface-muted hover:text-content transition-colors"
          aria-label="Toggle theme"
        >
          {resolved === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </button>

        <div ref={menuRef} className="relative">
          <button
            type="button"
            onClick={() => setMenuOpen(!menuOpen)}
            className="flex h-9 items-center gap-2 rounded-lg pl-1 pr-2 hover:bg-surface-muted transition-colors"
          >
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-600 text-white text-xs font-medium">
              {user?.full_name?.charAt(0) ?? "U"}
            </div>
          </button>
          <AnimatePresence>
            {menuOpen && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                className="absolute right-0 top-full mt-2 w-56 rounded-xl border border-border bg-surface shadow-elevated py-1"
              >
                <div className="px-3 py-2 border-b border-border">
                  <p className="text-sm font-medium text-content truncate">{user?.full_name}</p>
                  <p className="text-xs text-content-subtle truncate">{user?.email}</p>
                </div>
                <button
                  type="button"
                  className="flex w-full items-center gap-2 px-3 py-2 text-sm text-content-muted hover:bg-surface-muted hover:text-content"
                >
                  <User className="h-4 w-4" />
                  Profile
                </button>
                <button
                  type="button"
                  onClick={handleLogout}
                  className={cn(
                    "flex w-full items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-500/5"
                  )}
                >
                  <LogOut className="h-4 w-4" />
                  Sign out
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </header>
  );
}
