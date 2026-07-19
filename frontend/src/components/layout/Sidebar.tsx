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
  X,
} from "lucide-react";
import { cn } from "@/lib/cn";
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

type SidebarProps = {
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
  mobileOpen: boolean;
  onMobileClose: () => void;
};

export function Sidebar({
  collapsed,
  onCollapsedChange,
  mobileOpen,
  onMobileClose,
}: SidebarProps) {
  // On mobile the drawer is always expanded; collapse only applies at lg+.
  const showLabels = !collapsed || mobileOpen;

  return (
    <aside
      className={cn(
        "fixed left-0 top-0 z-50 flex h-screen flex-col border-r border-border bg-surface transition-all duration-300",
        "w-[min(100vw,var(--sidebar-width))]",
        mobileOpen ? "translate-x-0" : "-translate-x-full",
        "lg:translate-x-0",
        collapsed ? "lg:w-[72px]" : "lg:w-[var(--sidebar-width)]"
      )}
    >
      <div className="flex h-14 items-center gap-2 border-b border-border px-4">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-600 text-white">
          <Layers className="h-4 w-4" />
        </div>
        {showLabels && (
          <span className="font-semibold text-content tracking-tight flex-1 truncate">
            App Manager
          </span>
        )}
        <button
          type="button"
          onClick={onMobileClose}
          className="ml-auto flex h-8 w-8 items-center justify-center rounded-lg text-content-muted hover:bg-surface-muted hover:text-content lg:hidden"
          aria-label="Close navigation"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {showLabels && (
        <div className="p-3 border-b border-border">
          <StoreSwitcher />
        </div>
      )}

      <nav className="flex-1 overflow-y-auto p-3 space-y-6">
        <div>
          {showLabels && (
            <p className="px-2 mb-2 text-xs font-medium text-content-subtle uppercase tracking-wider">
              Apps
            </p>
          )}
          <ul className="space-y-0.5">
            {mainNav.map(({ to, icon: Icon, label }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  onClick={onMobileClose}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-3 rounded-lg px-2.5 py-2.5 text-sm font-medium transition-colors lg:py-2",
                      isActive
                        ? "bg-brand-500/10 text-brand-700 dark:text-brand-400"
                        : "text-content-muted hover:bg-surface-muted hover:text-content",
                      !showLabels && "justify-center px-2"
                    )
                  }
                  title={!showLabels ? label : undefined}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {showLabels && label}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>

        <div>
          {showLabels && (
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
                  onClick={onMobileClose}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-3 rounded-lg px-2.5 py-2.5 text-sm font-medium transition-colors lg:py-2",
                      isActive
                        ? "bg-brand-500/10 text-brand-700 dark:text-brand-400"
                        : "text-content-muted hover:bg-surface-muted hover:text-content",
                      !showLabels && "justify-center px-2"
                    )
                  }
                  title={!showLabels ? label : undefined}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {showLabels && label}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      </nav>

      <div className="hidden border-t border-border p-3 lg:block">
        <button
          type="button"
          onClick={() => onCollapsedChange(!collapsed)}
          className="flex w-full items-center justify-center gap-2 rounded-lg py-2 text-content-subtle hover:bg-surface-muted hover:text-content transition-colors"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <ChevronLeft
            className={cn("h-4 w-4 transition-transform", collapsed && "rotate-180")}
          />
          {!collapsed && <span className="text-xs">Collapse</span>}
        </button>
      </div>
    </aside>
  );
}
