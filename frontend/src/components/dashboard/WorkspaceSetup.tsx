import { Link } from "react-router-dom";
import { Check, Circle, Sparkles } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import type { SetupStep } from "@/lib/dashboardTypes";
import { cn } from "@/lib/cn";

export function WorkspaceSetup({ steps }: { steps: SetupStep[] }) {
  const incomplete = steps.filter((s) => !s.done);
  if (incomplete.length === 0) return null;

  const next = incomplete[0];
  const doneCount = steps.filter((s) => s.done).length;
  const progress = Math.round((doneCount / Math.max(steps.length, 1)) * 100);

  return (
    <Card padding="lg" className="border-brand-500/20 bg-brand-500/5 overflow-hidden relative">
      <div className="absolute inset-y-0 left-0 w-1 bg-brand-500" />
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-brand-600" />
            <h2 className="text-lg font-semibold text-content">Finish workspace setup</h2>
          </div>
          <p className="text-sm text-content-muted mt-1 max-w-2xl">
            Connect Shopify and Gmail to unlock Tracking, Email Automation, AI Email Assistant,
            Analytics, and Ads. SMS and Support are coming soon.
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-xs font-medium uppercase tracking-wide text-content-subtle">
            Progress
          </p>
          <p className="text-2xl font-bold tabular-nums text-content">{progress}%</p>
        </div>
      </div>

      <div className="mt-4 h-1.5 rounded-full bg-surface-muted overflow-hidden">
        <div
          className="h-full rounded-full bg-brand-500 transition-all duration-500"
          style={{ width: `${progress}%` }}
        />
      </div>

      <ol className="mt-5 space-y-2">
        {steps.map((step) => (
          <li
            key={step.id}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm",
              step.done ? "text-content-muted" : "text-content bg-surface/80"
            )}
          >
            {step.done ? (
              <Check className="h-4 w-4 shrink-0 text-emerald-600" />
            ) : (
              <Circle className="h-4 w-4 shrink-0 text-content-subtle" />
            )}
            <span className={step.done ? "line-through" : "font-medium"}>{step.label}</span>
          </li>
        ))}
      </ol>

      <div className="mt-4">
        <Link to={next.href}>
          <Button variant="primary">{next.label}</Button>
        </Link>
      </div>
    </Card>
  );
}
