import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Mail,
  Sparkles,
  Package,
  BarChart3,
  MessageSquare,
  Headphones,
  Settings,
  Store,
  Layers,
  ChevronLeft,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { useState } from "react";
import { StoreSwitcher } from "@/components/stores/StoreSwitcher";

const mainNav = [
  { to: "/dashboard", icon: LayoutDashboard, label: "Overview" },
  { to: "/modules/ai-email", icon: Sparkles, label: "AI Email Assistant" },
  { to: "/modules/email", icon: Mail, label: "Email Automation" },
  { to: "/modules/tracking", icon: Package, label: "Tracking" },
  { to: "/modules/analytics", icon: BarChart3, label: "Analytics" },
  { to: "/modules/sms", icon: MessageSquare, label: "SMS" },
  { to: "/modules/support", icon: Headphones, label: "Support" },
];

const settingsNav = [
  { to: "/settings", icon: Settings, label: "General" },
  { to: "/settings/stores", icon: Store, label: "Stores" },
  { to: "/settings/gmail", icon: Mail, label: "Gmail" },
];

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={cn(
        "fixed left-0 top-0 z-40 flex h-screen flex-col border-r border-border bg-surface transition-all duration-300",
        collapsed ? "w-[72px]" : "w-[var(--sidebar-width)]"
      )}
    >
      <div className="flex h-14 items-center gap-2 border-b border-border px-4">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-600 text-white">
          <Layers className="h-4 w-4" />
        </div>
        {!collapsed && (
          <span className="font-semibold text-content tracking-tight">App Manager</span>
        )}
      </div>

      {!collapsed && (
        <div className="p-3 border-b border-border">
          <StoreSwitcher />
        </div>
      )}

      <nav className="flex-1 overflow-y-auto p-3 space-y-6">
        <div>
          {!collapsed && (
            <p className="px-2 mb-2 text-xs font-medium text-content-subtle uppercase tracking-wider">
              Apps
            </p>
          )}
          <ul className="space-y-0.5">
            {mainNav.map(({ to, icon: Icon, label }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-brand-500/10 text-brand-700 dark:text-brand-400"
                        : "text-content-muted hover:bg-surface-muted hover:text-content",
                      collapsed && "justify-center px-2"
                    )
                  }
                  title={collapsed ? label : undefined}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {!collapsed && label}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>

        <div>
          {!collapsed && (
            <p className="px-2 mb-2 text-xs font-medium text-content-subtle uppercase tracking-wider">
              Settings
            </p>
          )}
          <ul className="space-y-0.5">
            {settingsNav.map(({ to, icon: Icon, label }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  end={to === "/settings"}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-brand-500/10 text-brand-700 dark:text-brand-400"
                        : "text-content-muted hover:bg-surface-muted hover:text-content",
                      collapsed && "justify-center px-2"
                    )
                  }
                  title={collapsed ? label : undefined}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {!collapsed && label}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      </nav>

      <div className="border-t border-border p-3">
        <button
          type="button"
          onClick={() => setCollapsed(!collapsed)}
          className="flex w-full items-center justify-center gap-2 rounded-lg py-2 text-content-subtle hover:bg-surface-muted hover:text-content transition-colors"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <ChevronLeft className={cn("h-4 w-4 transition-transform", collapsed && "rotate-180")} />
          {!collapsed && <span className="text-xs">Collapse</span>}
        </button>
      </div>
    </aside>
  );
}
