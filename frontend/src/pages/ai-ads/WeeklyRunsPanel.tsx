import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, History, Info, Play } from "lucide-react";
import {
  api,
  type AIAdsWeeklyRun,
  type AIAdsWeeklyRunsResponse,
  type AIAdsWeeklySchedule,
} from "@/lib/api";
import type { AIAdsWeeklyStep } from "@/lib/aiAdsTypes";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";

const POLL_MS = 5000;

const STATUS_LABEL: Record<AIAdsWeeklyRun["status"], string> = {
  QUEUED: "Queued",
  RUNNING: "Running",
  SUCCEEDED: "Succeeded",
  PARTIAL: "Partial",
  FAILED: "Failed",
};

const TRIGGER_LABEL: Record<AIAdsWeeklyRun["trigger"], string> = {
  schedule: "Scheduled",
  catch_up: "Catch-up",
  manual: "Run now",
};

const STEP_DOT: Record<AIAdsWeeklyStep["status"], string> = {
  pending: "bg-slate-300 dark:bg-slate-600",
  running: "bg-brand-500 animate-pulse",
  ok: "bg-emerald-500",
  warning: "bg-amber-500",
  failed: "bg-red-500",
  skipped: "bg-slate-300 dark:bg-slate-600",
};

function statusBadge(status: AIAdsWeeklyRun["status"]) {
  if (status === "SUCCEEDED") return <Badge variant="success">{STATUS_LABEL[status]}</Badge>;
  if (status === "PARTIAL") return <Badge variant="warning">{STATUS_LABEL[status]}</Badge>;
  if (status === "FAILED")
    return (
      <Badge className="border-red-500/20 bg-red-500/10 text-red-600 dark:text-red-400">
        {STATUS_LABEL[status]}
      </Badge>
    );
  return <Badge variant="brand">{STATUS_LABEL[status]}</Badge>;
}

function formatWhen(iso: string | null | undefined, timeZone?: string) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString([], {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    ...(timeZone ? { timeZone, timeZoneName: "short" } : {}),
  });
}

function isActive(run: AIAdsWeeklyRun) {
  return run.status === "QUEUED" || run.status === "RUNNING";
}

export function WeeklyRunsPanel({
  storeId,
  refreshKey,
  beforeRun,
}: {
  storeId: string;
  refreshKey: number;
  beforeRun: () => Promise<boolean>;
}) {
  const [data, setData] = useState<AIAdsWeeklyRunsResponse | null>(null);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await api.aiAds.listWeeklyRuns(storeId, 10));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load weekly runs");
    }
  }, [storeId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const running = Boolean(data?.runs.some(isActive));
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [running, load]);

  async function runNow() {
    setStarting(true);
    setError("");
    try {
      if (!(await beforeRun())) return;
      await api.aiAds.runWeeklyNow(storeId);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the weekly batch");
    } finally {
      setStarting(false);
    }
  }

  const schedule = data?.schedule;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-border p-3.5">
        <ScheduleLines schedule={schedule} />
        <Button
          variant="outline"
          onClick={() => void runNow()}
          isLoading={starting}
          disabled={running}
          title={running ? "A weekly batch is already running" : "Save settings and run this week's batch now"}
        >
          <Play className="h-4 w-4" />
          Run now
        </Button>
      </div>

      {error && (
        <p className="flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-600">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </p>
      )}

      {schedule?.problems.map((p) => (
        <p
          key={p.message}
          className={cn(
            "flex items-start gap-2 rounded-lg border px-3 py-2 text-xs",
            p.level === "error"
              ? "border-red-500/20 bg-red-500/10 text-red-600"
              : "border-amber-500/20 bg-amber-500/10 text-amber-700 dark:text-amber-400"
          )}
        >
          {p.level === "error" ? (
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          ) : (
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          )}
          <span>{p.message}</span>
        </p>
      ))}

      <div>
        <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-content-subtle">
          <History className="h-3.5 w-3.5" />
          Run history
        </div>
        {!data ? (
          <p className="text-sm text-content-muted">Loading…</p>
        ) : data.runs.length === 0 ? (
          <p className="text-sm text-content-muted">No weekly runs yet.</p>
        ) : (
          <ul className="space-y-2">
            {data.runs.map((run) => (
              <RunRow key={run.id} run={run} timeZone={schedule?.timezone} />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function ScheduleLines({ schedule }: { schedule: AIAdsWeeklySchedule | undefined }) {
  if (!schedule) return <p className="text-sm text-content-muted">Loading schedule…</p>;
  const tz = schedule.timezone;
  let next = "Off (turn on the weekly toggle and save)";
  if (!schedule.scheduler_enabled) next = "Scheduler disabled on the server";
  else if (schedule.enabled && schedule.catching_up) next = "Starting now (this week's run is due)";
  else if (schedule.enabled && schedule.next_run_at) next = formatWhen(schedule.next_run_at, tz);
  const last = schedule.last_run_at
    ? `${formatWhen(schedule.last_run_at, tz)}${schedule.last_run_status ? ` · ${STATUS_LABEL[schedule.last_run_status]}` : ""}`
    : "Never";
  return (
    <div className="min-w-0 space-y-1 text-sm">
      <p>
        <span className="text-content-subtle">Next run: </span>
        <span className="font-medium">{next}</span>
      </p>
      <p>
        <span className="text-content-subtle">Last run: </span>
        <span className="font-medium">{last}</span>
      </p>
      <p className="text-xs text-content-subtle">
        {schedule.hour}:00 {tz} on {schedule.generation_day.charAt(0).toUpperCase() + schedule.generation_day.slice(1)}
        {schedule.scheduler_enabled && !schedule.scheduler_alive && " · scheduler has not checked in recently"}
      </p>
    </div>
  );
}

function RunRow({ run, timeZone }: { run: AIAdsWeeklyRun; timeZone?: string }) {
  const counts: string[] = [];
  if (run.images_requested) counts.push(`${run.images_generated}/${run.images_requested} stills`);
  if (run.videos_requested) counts.push(`${run.videos_generated}/${run.videos_requested} videos`);
  return (
    <li className="rounded-lg border border-border p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        {statusBadge(run.status)}
        <span className="font-medium">{formatWhen(run.started_at || run.created_at, timeZone)}</span>
        <span className="text-xs text-content-subtle">
          {TRIGGER_LABEL[run.trigger] ?? run.trigger} · {run.week_key}
        </span>
        {counts.length > 0 && <span className="text-xs text-content-muted">{counts.join(" · ")}</span>}
        {(run.job_ids?.length ?? 0) > 1 ? (
          <span className="ml-auto flex gap-2">
            {run.job_ids!.map((id, i) => (
              <Link key={id} to={`/ai-ads/progress/${id}`} className="text-xs font-medium text-brand-600 underline">
                Job {i + 1}
              </Link>
            ))}
          </span>
        ) : (
          run.job_id && (
            <Link to={`/ai-ads/progress/${run.job_id}`} className="ml-auto text-xs font-medium text-brand-600 underline">
              View job
            </Link>
          )
        )}
        {run.director_report_id && (
          <Link to="/ai-ads/director" className="text-xs font-medium text-brand-600 underline">
            Brief
          </Link>
        )}
      </div>
      {run.product_title && (
        <p className="mt-1 text-xs text-content-muted">
          {(run.job_ids?.length ?? 0) > 1 ? "Products" : "Product"}: {run.product_title}
        </p>
      )}
      <ul className="mt-2 grid gap-x-4 gap-y-1 sm:grid-cols-2">
        {run.steps.map((step) => (
          <li key={step.key} className="flex items-start gap-2 text-xs">
            <span className={cn("mt-1 h-2 w-2 shrink-0 rounded-full", STEP_DOT[step.status])} />
            <span className="min-w-0">
              <span className="font-medium">{step.label}</span>
              <span className="text-content-subtle"> · {step.status}</span>
              {step.detail && <span className="block text-content-muted">{step.detail}</span>}
            </span>
          </li>
        ))}
      </ul>
      {run.error_message && (run.status === "FAILED" || run.status === "PARTIAL") && (
        <p className="mt-2 text-xs text-red-600">{run.error_message}</p>
      )}
    </li>
  );
}
