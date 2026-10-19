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
  const doneCount = steps.filter((s) => s.done).length;

  return (
    <Card padding="none" className="border-brand-500/25 bg-brand-500/5">
      <div className="flex flex-col gap-3 p-3.5 sm:flex-row sm:items-center sm:justify-between sm:gap-4 sm:px-4 sm:py-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-content">Finish setup to unlock your apps</p>
          <ol className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1">
            {steps.map((step) => (
              <li
                key={step.id}
                className={cn(
                  "inline-flex items-center gap-1.5 text-xs",
                  step.done ? "text-content-muted" : "font-medium text-content"
                )}
              >
                {step.done ? (
                  <Check className="h-3.5 w-3.5 shrink-0 text-emerald-600" />
                ) : (
                  <Circle className="h-3.5 w-3.5 shrink-0 text-content-subtle" />
                )}
                <span className={step.done ? "line-through" : undefined}>{step.label}</span>
              </li>
            ))}
          </ol>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <p className="text-xs tabular-nums text-content-subtle">
            {doneCount}/{steps.length}
          </p>
          <Link to={next.href}>
            <Button variant="primary" size="sm">
              {next.label}
            </Button>
          </Link>
        </div>
      </div>
    </Card>
  );
}
