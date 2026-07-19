import { Link } from "react-router-dom";
import { Check, Circle } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import type { SetupStep } from "@/lib/dashboardTypes";
import { cn } from "@/lib/cn";

export function WorkspaceSetup({ steps }: { steps: SetupStep[] }) {
  const incomplete = steps.filter((s) => !s.done);
  if (incomplete.length === 0) return null;

  const next = incomplete[0];

  return (
    <Card padding="lg" className="border-brand-500/20 bg-brand-500/5">
      <h2 className="text-lg font-semibold text-content">Finish workspace setup</h2>
      <p className="text-sm text-content-muted mt-1 max-w-2xl">
        Connect Shopify and Gmail to unlock Tracking, Email Automation, and the AI Email
        Assistant. Analytics, SMS, and Support are on the roadmap.
      </p>

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
