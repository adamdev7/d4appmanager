import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Check, Circle, Loader2, Sparkles, X } from "lucide-react";
import type { AIAdsGeneratedCreative, AIAdsJob, AIAdsJobLogEntry } from "@/lib/aiAdsTypes";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import {
  CreativeFrame,
  CreativeViewer,
  previewFromGenerated,
} from "@/pages/ai-ads/CreativeViewer";

const STAGES = [
  { id: "start", label: "Starting the worker", match: ["queued", "start"] },
  { id: "product", label: "Locking product photos", match: ["product"] },
  { id: "learn", label: "Studying your Meta ads", match: ["sync", "learn"] },
  { id: "plan", label: "Writing the concepts", match: ["plan"] },
  { id: "render", label: "Rendering the video", match: ["image", "video"] },
  { id: "done", label: "Finishing up", match: ["done", "error"] },
] as const;

function isActiveStatus(status: string) {
  return status === "QUEUED" || status === "RUNNING";
}

function stageIndex(job: AIAdsJob): number {
  const status = String(job.status);
  if (status === "COMPLETED" || status === "PARTIAL") return STAGES.length - 1;
  const step = job.progress_step || "";
  const found = STAGES.findIndex((s) => (s.match as readonly string[]).includes(step));
  return found >= 0 ? found : 0;
}

function barPct(job: AIAdsJob): number {
  const live = Number(job.progress_pct || 0);
  if (live > 0) return Math.min(100, live);
  if (job.total_items) {
    return Math.round(((job.completed_items || 0) / Math.max(job.total_items, 1)) * 100);
  }
  return isActiveStatus(String(job.status)) ? 4 : 0;
}

function formatTime(iso?: string) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function GenerationStudio({
  job,
  compact = false,
}: {
  job: AIAdsJob;
  compact?: boolean;
}) {
  const status = String(job.status);
  const active = isActiveStatus(status);
  const failed = status === "FAILED";
  const pct = barPct(job);
  const current = stageIndex(job);
  const thinking =
    job.thinking || job.progress_message || (active ? "The AI worker is starting…" : "");
  const log = (job.progress_log || []) as AIAdsJobLogEntry[];
  const creatives = (job.creatives || []) as AIAdsGeneratedCreative[];
  const [viewer, setViewer] = useState<AIAdsGeneratedCreative | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [log.length, job.thinking, job.progress_message]);

  if (compact) {
    return (
      <Card className="border-brand-line/40 bg-[radial-gradient(circle_at_top_right,rgba(34,197,94,0.09),transparent_45%)]">
        <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                {active && (
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand-500/70" />
                )}
                <span
                  className={cn(
                    "relative inline-flex h-2 w-2 rounded-full",
                    failed ? "bg-amber-500" : "bg-brand-500"
                  )}
                />
              </span>
              <CardTitle className="text-base">Rendering in progress</CardTitle>
              <span className="text-sm font-medium tabular-nums text-content-muted">{pct}%</span>
            </div>
            <CardDescription>
              {job.progress_message || status} · {job.completed_items ?? 0}/
              {job.total_items ?? 0} clips ready
            </CardDescription>
          </div>
          <Link to={`/ai-ads/progress/${job.job_id || job.id}`}>
            <Button variant="outline" size="sm">
              Open live studio
            </Button>
          </Link>
        </div>
        <div className="mb-3 h-2 overflow-hidden rounded-full bg-surface-muted">
          <div
            className={cn(
              "h-full transition-all duration-500",
              failed ? "bg-amber-500" : "bg-brand-600"
            )}
            style={{ width: `${Math.max(pct, active ? 4 : 0)}%` }}
          />
        </div>
        {thinking && (
          <p className="flex items-start gap-2 text-sm text-content-muted">
            {active && <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-brand-600" />}
            <span>{thinking}</span>
          </p>
        )}
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-brand-600" />
              Live render studio
            </CardTitle>
            <CardDescription>
              Exactly what the worker is doing right now — not a frozen spinner.
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={failed ? "warning" : status === "COMPLETED" ? "success" : "brand"}>
              {status}
            </Badge>
            <span className="text-sm font-medium tabular-nums text-content">{pct}%</span>
          </div>
        </div>
      </CardHeader>

      <div className="h-2.5 rounded-full bg-surface-muted overflow-hidden mb-6">
        <div
          className={cn(
            "h-full transition-all duration-500",
            failed ? "bg-amber-500" : "bg-brand-600",
            active && pct < 100 && "animate-pulse"
          )}
          style={{ width: `${Math.max(pct, active ? 4 : 0)}%` }}
        />
      </div>

      <ol className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3 mb-6">
        {STAGES.map((stage, i) => {
          const done = i < current || (!active && i <= current && !failed);
          const here = i === current && (active || failed);
          return (
            <li
              key={stage.id}
              className={cn(
                "flex items-center gap-2 rounded-lg border px-3 py-2 text-sm",
                here
                  ? "border-brand-500/50 bg-brand-500/10 text-content"
                  : done
                    ? "border-border bg-surface-muted/50 text-content"
                    : "border-border/60 text-content-subtle"
              )}
            >
              {here && active ? (
                <Loader2 className="h-4 w-4 shrink-0 animate-spin text-brand-600" />
              ) : here && failed ? (
                <X className="h-4 w-4 shrink-0 text-amber-500" />
              ) : done ? (
                <Check className="h-4 w-4 shrink-0 text-brand-600" />
              ) : (
                <Circle className="h-4 w-4 shrink-0" />
              )}
              {stage.label}
            </li>
          );
        })}
      </ol>

      <div
        className={cn(
          "rounded-xl border px-4 py-3 mb-5",
          failed ? "border-amber-500/30 bg-amber-500/5" : "border-brand-line/40 bg-surface-muted/40"
        )}
      >
        <p className="text-xs uppercase tracking-wide text-content-subtle mb-1">
          {active ? "What the AI is doing now" : failed ? "Stopped" : "Latest step"}
        </p>
        <p className="font-medium text-content">{job.progress_message || status}</p>
        {thinking && thinking !== job.progress_message && (
          <p className={cn("text-sm text-content-muted mt-1", active && "animate-pulse")}>{thinking}</p>
        )}
        {thinking && thinking === job.progress_message && active && (
          <p className="text-sm text-content-muted mt-1">
            Working — rendering a clip takes a few minutes.
          </p>
        )}
        <p className="text-xs text-content-subtle mt-2">
          {job.completed_items ?? 0}/{job.total_items ?? 0} clips ready
          {job.failed_items ? ` · ${job.failed_items} failed` : ""}
        </p>
      </div>

      {creatives.length > 0 && (
        <div className="mb-5">
          <p className="text-xs uppercase tracking-wide text-content-subtle mb-2">
            Clips as they land
          </p>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {creatives.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => setViewer(c)}
                className="text-left"
              >
                <CreativeFrame ad={previewFromGenerated(c)} compact />
                <p className="mt-2 text-sm font-medium text-content line-clamp-1">
                  {c.headline || c.hook || (c.type === "VIDEO" ? "Video concept" : "Image ad")}
                </p>
                <p className="text-xs text-content-subtle">
                  {c.status}
                  {c.video_url ? " · MP4 ready" : c.type === "VIDEO" ? " · video" : ""}
                  {!c.preview_url && c.status === "GENERATING" ? " · rendering…" : ""}
                </p>
              </button>
            ))}
          </div>
        </div>
      )}

      <div>
        <p className="text-xs uppercase tracking-wide text-content-subtle mb-2">Activity log</p>
        <div className="max-h-72 overflow-y-auto rounded-xl border border-border bg-surface-muted/30 px-3 py-2 space-y-3">
          {log.length === 0 ? (
            <p className="text-sm text-content-subtle py-6 text-center">
              Waiting for the worker to start…
            </p>
          ) : (
            log.map((entry, i) => (
              <div key={`${entry.at || i}-${entry.title}`} className="flex gap-3">
                <span className="text-[11px] tabular-nums text-content-subtle w-[72px] shrink-0 pt-0.5">
                  {formatTime(entry.at)}
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-content">{entry.title}</p>
                  {entry.detail && (
                    <p className="text-sm text-content-muted mt-0.5">{entry.detail}</p>
                  )}
                </div>
              </div>
            ))
          )}
          <div ref={endRef} />
        </div>
      </div>

      {job.error_message && (
        <p className="text-sm text-red-600 mt-4">{job.error_message}</p>
      )}

      {(status === "COMPLETED" || status === "PARTIAL") && (
        <div className="mt-5 flex flex-wrap gap-2">
          <Link to="/ai-ads/creatives">
            <Button>Open in Library</Button>
          </Link>
          <Link to="/ai-ads/generate">
            <Button variant="outline">Generate more</Button>
          </Link>
        </div>
      )}
      {failed && (
        <div className="mt-5">
          <Link to="/ai-ads/generate">
            <Button>Try again</Button>
          </Link>
        </div>
      )}
      {viewer && (
        <CreativeViewer ad={previewFromGenerated(viewer)} onClose={() => setViewer(null)} />
      )}
    </Card>
  );
}
