import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Activity,
  Copy,
  OctagonX,
  Radio,
  RotateCcw,
  Sparkles,
  Trash2,
  Zap,
} from "lucide-react";
import type { AIAdsJob } from "@/lib/aiAdsTypes";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { cn } from "@/lib/cn";

function isLive(status: string) {
  return status === "QUEUED" || status === "RUNNING";
}

function callsign(job: AIAdsJob) {
  const id = job.job_id || job.id || "";
  return id.replace(/-/g, "").slice(0, 8).toUpperCase() || "--------";
}

function barPct(job: AIAdsJob) {
  const live = Number(job.progress_pct || 0);
  if (live > 0) return Math.min(100, live);
  if (job.total_items) {
    return Math.round(((job.completed_items || 0) / Math.max(job.total_items, 1)) * 100);
  }
  return isLive(String(job.status)) ? 4 : 0;
}

function elapsedLabel(from?: string | null, until?: string | null) {
  if (!from) return "—";
  const start = new Date(from).getTime();
  if (Number.isNaN(start)) return "—";
  const end = until ? new Date(until).getTime() : Date.now();
  const sec = Math.max(0, Math.floor((end - start) / 1000));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m >= 60) {
    const h = Math.floor(m / 60);
    return `${h}h ${m % 60}m`;
  }
  return `${m}:${String(s).padStart(2, "0")}`;
}

function lampClass(job: AIAdsJob) {
  const status = String(job.status);
  if (status === "RUNNING" && job.worker_alive) return "bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.7)]";
  if (status === "QUEUED") return "bg-amber-400 shadow-[0_0_10px_rgba(251,191,36,0.6)]";
  if (status === "RUNNING" && !job.worker_alive) return "bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.7)]";
  if (status === "FAILED") return "bg-red-500";
  if (status === "CANCELLED") return "bg-slate-400";
  if (status === "PARTIAL") return "bg-amber-400";
  if (status === "COMPLETED") return "bg-emerald-400";
  return "bg-slate-400";
}

function heartbeatCopy(job: AIAdsJob) {
  const status = String(job.status);
  if (status === "RUNNING" && job.worker_alive) return "Worker locked on";
  if (status === "QUEUED" && job.worker_alive) return "Worker spinning up";
  if (isLive(status) && !job.worker_alive) return "Signal lost — nudge to wake";
  if (status === "CANCELLED") return "Halted by operator";
  if (status === "FAILED") return "Run aborted";
  if (status === "PARTIAL") return "Finished with leftovers";
  if (status === "COMPLETED") return "Channel clear";
  return status;
}

function badgeVariant(status: string): "brand" | "success" | "warning" | "muted" {
  if (status === "COMPLETED") return "success";
  if (status === "FAILED" || status === "PARTIAL" || status === "CANCELLED") return "warning";
  if (status === "QUEUED" || status === "RUNNING") return "brand";
  return "muted";
}

export function shouldShowWorkplaceConsole(job: AIAdsJob | null | undefined) {
  if (!job) return false;
  return isLive(String(job.status));
}

export function GenerationControlPanel({
  storeId,
  job,
  onChanged,
}: {
  storeId: string;
  job: AIAdsJob;
  onChanged?: (job: AIAdsJob) => void;
}) {
  const navigate = useNavigate();
  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [copied, setCopied] = useState(false);

  const status = String(job.status);
  const live = isLive(status);
  const jobId = job.job_id || job.id;
  const pct = barPct(job);
  const lost = live && !job.worker_alive;

  useEffect(() => {
    if (!live && status !== "CANCELLED") return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [live, status]);

  const elapsed = useMemo(
    () => elapsedLabel(job.started_at || job.created_at, live ? null : job.finished_at),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- tick clock while live
    [job.started_at, job.created_at, job.finished_at, live, now]
  );

  async function run(action: string, fn: () => Promise<AIAdsJob>, next?: (job: AIAdsJob) => void) {
    if (!jobId) return;
    setBusy(action);
    setNotice("");
    try {
      const result = await fn();
      const fullId = result.job_id || result.id;
      const full = fullId ? await api.aiAds.getGenerationJob(storeId, fullId).catch(() => result) : result;
      onChanged?.(full);
      next?.(full);
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Console action failed");
    } finally {
      setBusy(null);
    }
  }

  async function copyCallsign() {
    try {
      await navigator.clipboard.writeText(jobId);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setNotice("Could not copy job id");
    }
  }

  return (
    <Card className="overflow-hidden border-brand-line/40 bg-[radial-gradient(circle_at_top_right,rgba(79,70,229,0.08),transparent_42%)]">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div className="min-w-0">
          <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-content-subtle">
            Workplace console
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <span
              className={cn(
                "h-2.5 w-2.5 rounded-full",
                lampClass(job),
                live && job.worker_alive && "animate-pulse"
              )}
            />
            <h3 className="text-base font-semibold text-content">Generation control</h3>
            <Badge variant={badgeVariant(status)}>{status}</Badge>
          </div>
        </div>
        <button
          type="button"
          onClick={() => void copyCallsign()}
          className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface-muted/60 px-2 py-1 font-mono text-[11px] tracking-wider text-content-muted hover:text-content"
          title="Copy job id"
        >
          <Copy className="h-3 w-3" />
          {copied ? "COPIED" : callsign(job)}
        </button>
      </div>

      <div className="grid gap-2 sm:grid-cols-4 mb-4">
        <Telemetry label="Heartbeat" value={heartbeatCopy(job)} warn={lost} />
        <Telemetry label="Clock" value={elapsed} />
        <Telemetry
          label="Payload"
          value={`${job.completed_items ?? 0} / ${job.total_items ?? 0} ready`}
        />
        <Telemetry label="Step" value={job.progress_message || status} />
      </div>

      <div className="h-2 rounded-full bg-surface-muted overflow-hidden mb-4">
        <div
          className={cn(
            "h-full transition-all duration-500",
            lost || status === "FAILED" ? "bg-amber-500" : "bg-brand-600",
            live && pct < 100 && "animate-pulse"
          )}
          style={{ width: `${Math.max(pct, live ? 4 : 0)}%` }}
        />
      </div>

      {lost && (
        <p className="text-sm text-amber-600 dark:text-amber-400 mb-3">
          Progress can sit still while OpenAI is rendering — or the worker died. Halt cuts the run,
          Nudge restarts the same job if the process is gone, and Replay starts a clean job from the
          same brief.
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="danger"
          disabled={!live || busy !== null}
          isLoading={busy === "halt"}
          onClick={() =>
            void run("halt", () => api.aiAds.stopGenerationJob(storeId, jobId), (next) =>
              setNotice(next.status === "CANCELLED" ? "Run halted. Ready ads were kept." : "Halt sent.")
            )
          }
        >
          <OctagonX className="h-3.5 w-3.5" />
          Halt
        </Button>
        <Button
          size="sm"
          variant="secondary"
          disabled={busy !== null}
          isLoading={busy === "replay"}
          onClick={() =>
            void run("replay", () => api.aiAds.restartGenerationJob(storeId, jobId), (next) => {
              const id = next.job_id || next.id;
              setNotice("Fresh job launched from the same brief.");
              if (id) navigate(`/ai-ads/progress/${id}`);
            })
          }
        >
          <RotateCcw className="h-3.5 w-3.5" />
          Replay
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={!live || busy !== null}
          isLoading={busy === "nudge"}
          onClick={() =>
            void run("nudge", () => api.aiAds.nudgeGenerationJob(storeId, jobId), (next) =>
              setNotice(
                next.nudge === "already_alive"
                  ? "Worker is already alive — waiting on the current step."
                  : "Nudge sent. Watching for a new heartbeat."
              )
            )
          }
        >
          <Zap className="h-3.5 w-3.5" />
          Nudge
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={busy !== null}
          isLoading={busy === "sweep"}
          onClick={() => {
            if (!window.confirm("Delete unfinished or failed leftovers from this job? Ready ads stay.")) {
              return;
            }
            void run("sweep", () => api.aiAds.sweepGenerationJob(storeId, jobId), (next) =>
              setNotice(
                next.swept_count
                  ? `Swept ${next.swept_count} leftover creative${next.swept_count === 1 ? "" : "s"}.`
                  : "No leftovers to sweep."
              )
            );
          }}
        >
          <Trash2 className="h-3.5 w-3.5" />
          Sweep
        </Button>
        <Link to={`/ai-ads/progress/${jobId}`}>
          <Button size="sm" variant="outline">
            <Activity className="h-3.5 w-3.5" />
            Studio
          </Button>
        </Link>
        <Link to="/ai-ads/generate">
          <Button size="sm" variant="ghost">
            <Sparkles className="h-3.5 w-3.5" />
            New brief
          </Button>
        </Link>
      </div>

      {notice && (
        <p className="mt-3 text-sm text-content-muted flex items-start gap-2">
          <Radio className="h-4 w-4 shrink-0 mt-0.5 text-brand-600" />
          <span>{notice}</span>
        </p>
      )}
    </Card>
  );
}

function Telemetry({
  label,
  value,
  warn,
}: {
  label: string;
  value: string;
  warn?: boolean;
}) {
  return (
    <div className="rounded-lg border border-border/80 bg-surface-muted/40 px-3 py-2 min-w-0">
      <p className="text-[10px] uppercase tracking-[0.14em] text-content-subtle">{label}</p>
      <p
        className={cn(
          "mt-0.5 text-sm font-medium leading-snug",
          warn ? "text-amber-600 dark:text-amber-400" : "text-content"
        )}
      >
        {value}
      </p>
    </div>
  );
}
