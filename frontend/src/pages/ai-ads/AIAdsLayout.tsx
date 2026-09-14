import { NavLink, Outlet } from "react-router-dom";
import {
  Compass,
  History,
  Images,
  LayoutDashboard,
  Lightbulb,
  LineChart,
  Settings2,
  Sparkles,
  WandSparkles,
} from "lucide-react";
import { cn } from "@/lib/cn";

/** The four screens of the actual workflow, in the order an operator uses them. */
const WORKFLOW = [
  { to: "/ai-ads", end: true, icon: LayoutDashboard, label: "Overview" },
  { to: "/ai-ads/generate", icon: Sparkles, label: "Generate" },
  { to: "/ai-ads/creatives", icon: Images, label: "Library" },
  { to: "/ai-ads/progress", icon: History, label: "Jobs" },
];

/** Reference screens — read when you want to dig, not on every run. */
const INSIGHTS = [
  { to: "/ai-ads/strategy", icon: Compass, label: "Strategy" },
  { to: "/ai-ads/performance", icon: LineChart, label: "Performance" },
  { to: "/ai-ads/recommendations", icon: Lightbulb, label: "Recommendations" },
  { to: "/ai-ads/settings", icon: Settings2, label: "Settings" },
];

export function AIAdsLayout() {
  return (
    <div className="space-y-5">
      <header className="flex items-start gap-3.5">
        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-brand-500/10 ring-1 ring-inset ring-brand-500/25">
          <WandSparkles className="h-5 w-5 text-brand-600 dark:text-brand-400" />
        </span>
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-content-subtle">
            Apps
          </p>
          <h1 className="text-2xl font-semibold tracking-tight text-content">AI Ads</h1>
          <p className="mt-1.5 max-w-2xl text-sm text-content-muted">
            Astra learns from your live Meta campaigns, then renders stills and vertical video from
            your real product photos. Files come back as clean plates — no burned-in text, no
            voice — and nothing spends until you approve it.
          </p>
        </div>
      </header>

      <nav
        aria-label="AI Ads sections"
        className="sticky top-14 z-20 -mx-2 bg-surface-muted/95 px-2 py-2 backdrop-blur-sm xl:top-16"
      >
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-2xl border border-brand-line/30 bg-surface p-1.5 shadow-card dark:border-border">
          <ul className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
            {WORKFLOW.map(({ to, end, icon: Icon, label }) => (
              <li key={to}>
                <NavLink to={to} end={end} className={workflowTab}>
                  {({ isActive }) => (
                    <>
                      <Icon
                        className={cn(
                          "h-4 w-4 shrink-0",
                          isActive && "text-brand-600 dark:text-brand-400"
                        )}
                      />
                      {label}
                    </>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
          <ul className="flex items-center gap-0.5 overflow-x-auto">
            {INSIGHTS.map(({ to, icon: Icon, label }) => (
              <li key={to}>
                <NavLink to={to} className={insightTab} title={label}>
                  <Icon className="h-4 w-4 shrink-0" />
                  <span className="hidden xl:inline">{label}</span>
                  <span className="sr-only xl:hidden">{label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      </nav>

      <Outlet />
    </div>
  );
}

function workflowTab({ isActive }: { isActive: boolean }) {
  return cn(
    "inline-flex items-center gap-2 whitespace-nowrap rounded-xl px-3.5 py-2 text-sm font-medium transition-all duration-200",
    isActive
      ? "bg-brand-500/10 text-content ring-1 ring-inset ring-brand-500/30 shadow-sm"
      : "text-content-muted hover:bg-surface-muted hover:text-content"
  );
}

function insightTab({ isActive }: { isActive: boolean }) {
  return cn(
    "inline-flex items-center gap-2 whitespace-nowrap rounded-xl px-2.5 py-2 text-sm font-medium transition-colors",
    isActive
      ? "bg-surface-muted text-content"
      : "text-content-subtle hover:bg-surface-muted hover:text-content"
  );
}
