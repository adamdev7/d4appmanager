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
  { id: "start", label: "Starting", match: ["queued", "start"] },
  { id: "product", label: "Locking product photos", match: ["product"] },
  { id: "learn", label: "Astra studying Meta ads", match: ["sync", "learn"] },
  { id: "plan", label: "Astra planning creatives", match: ["plan"] },
  { id: "render", label: "Astra rendering files", match: ["image", "video"] },
  { id: "done", label: "Finishing", match: ["done", "error"] },
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
      <Card>
        <CardHeader className="mb-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle className="flex flex-wrap items-center gap-x-1.5">
                <span>Generation</span>
                <span>in progress</span>
              </CardTitle>
              <CardDescription className="flex flex-wrap items-center gap-x-1.5">
                <span>{job.progress_message || status}</span>
                <span aria-hidden>·</span>
                <span>
                  {job.completed_items ?? 0}/{job.total_items ?? 0} creatives
                </span>
              </CardDescription>
            </div>
            <Badge variant={failed ? "warning" : "brand"}>{status}</Badge>
          </div>
        </CardHeader>
        <div className="h-2 rounded-full bg-surface-muted overflow-hidden mb-3">
          <div
            className="h-full bg-brand-600 transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        {thinking && (
          <p className="text-sm text-content-muted mb-4 flex items-start gap-2">
            {active && <Loader2 className="h-4 w-4 shrink-0 mt-0.5 animate-spin text-brand-600" />}
            <span>{thinking}</span>
          </p>
        )}
        <Link to={`/ai-ads/progress/${job.job_id || job.id}`}>
          <Button variant="outline" size="sm">
            Open live studio
          </Button>
        </Link>
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
              Creative generation studio
            </CardTitle>
            <CardDescription>
              Live view of what the AI is doing — not a frozen spinner.
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
          <p className="text-sm text-content-muted mt-1">Working — this can take a minute per image.</p>
        )}
        <p className="text-xs text-content-subtle mt-2">
          {job.completed_items ?? 0}/{job.total_items ?? 0} creatives ready
          {job.failed_items ? ` · ${job.failed_items} failed` : ""}
        </p>
      </div>

      {creatives.length > 0 && (
        <div className="mb-5">
          <p className="text-xs uppercase tracking-wide text-content-subtle mb-2">
            Live previews
          </p>
          <div className="grid gap-6 sm:grid-cols-2">
            {creatives.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => setViewer(c)}
                className="text-left"
              >
                <CreativeFrame ad={previewFromGenerated(c)} />
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
