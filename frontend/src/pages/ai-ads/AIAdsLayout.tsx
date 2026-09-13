import { NavLink, Outlet } from "react-router-dom";
import {
  LayoutDashboard,
  Images,
  Sparkles,
  Compass,
  LineChart,
  Lightbulb,
  Settings2,
} from "lucide-react";
import { cn } from "@/lib/cn";

const TABS = [
  { to: "/ai-ads", end: true, icon: LayoutDashboard, label: "Overview" },
  { to: "/ai-ads/creatives", icon: Images, label: "Library" },
  { to: "/ai-ads/generate", icon: Sparkles, label: "Generate" },
  { to: "/ai-ads/strategy", icon: Compass, label: "Strategy" },
  { to: "/ai-ads/performance", icon: LineChart, label: "Performance" },
  { to: "/ai-ads/recommendations", icon: Lightbulb, label: "Recommendations" },
  { to: "/ai-ads/settings", icon: Settings2, label: "Settings" },
];

export function AIAdsLayout() {
  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-medium uppercase tracking-wider text-content-subtle">Apps</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-content">AI Ads</h1>
        <p className="mt-1 text-sm text-content-muted max-w-2xl">
          Learn from your real Meta creatives and Shopify products, then generate new ads that
          require your approval before anything is published.
        </p>
      </div>
      <nav className="flex flex-wrap gap-1 border-b border-border pb-px">
        {TABS.map(({ to, end, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                "inline-flex items-center gap-2 rounded-t-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-surface text-brand-700 ring-1 ring-inset ring-brand-line/60 dark:text-brand-400"
                  : "text-content-muted hover:text-content hover:bg-surface-muted"
              )
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}
