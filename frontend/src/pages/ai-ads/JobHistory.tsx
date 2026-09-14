import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronRight, Images, RotateCcw } from "lucide-react";
import type { AIAdsGeneratedCreative, AIAdsJob, AIAdsJobLogEntry, AIAdsProduct } from "@/lib/aiAdsTypes";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import {
  CreativeFrame,
  CreativeViewer,
  DownloadCreativeButton,
  previewFromGenerated,
} from "@/pages/ai-ads/CreativeViewer";

export function isLiveJob(job: AIAdsJob | null | undefined) {
  if (!job) return false;
  const status = String(job.status);
  return status === "QUEUED" || status === "RUNNING";
}

export function jobStatusVariant(status: string): "brand" | "success" | "warning" | "muted" {
  if (status === "COMPLETED") return "success";
  if (status === "FAILED" || status === "PARTIAL" || status === "CANCELLED") return "warning";
  if (status === "QUEUED" || status === "RUNNING") return "brand";
  return "muted";
}

export function jobProductTitle(job: AIAdsJob, products: AIAdsProduct[] = []) {
  const match = products.find((p) => p.id === job.product_id);
  return match?.title || "Product";
}

export function formatJobWhen(iso?: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function formatLogTime(iso?: string) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function durationLabel(job: AIAdsJob) {
  const from = job.started_at || job.created_at;
  if (!from) return "";
  const start = new Date(from).getTime();
  if (Number.isNaN(start)) return "";
  const end = job.finished_at ? new Date(job.finished_at).getTime() : Date.now();
  const sec = Math.max(0, Math.floor((end - start) / 1000));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m >= 60) return `${Math.floor(m / 60)}h ${m % 60}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function countsLabel(job: AIAdsJob) {
  const ready = job.completed_items ?? 0;
  const total = job.total_items ?? 0;
  const failed = job.failed_items ?? 0;
  const parts = [`${ready}/${total} ready`];
  if (failed) parts.push(`${failed} failed`);
  const images = job.image_count;
  const videos = job.video_count;
  if (images != null || videos != null) {
    const asked: string[] = [];
    if (images) asked.push(`${images} image${images === 1 ? "" : "s"}`);
    if (videos) asked.push(`${videos} video${videos === 1 ? "" : "s"}`);
    if (asked.length) parts.push(asked.join(" · "));
  }
  return parts.join(" · ");
}

export function JobHistoryList({
  jobs,
  products = [],
  selectedId,
}: {
  jobs: AIAdsJob[];
  products?: AIAdsProduct[];
  selectedId?: string | null;
}) {
  if (!jobs.length) {
    return (
      <Card>
        <CardTitle>No jobs yet</CardTitle>
        <CardDescription className="mt-2">
          Start a run from Generate. Finished jobs will show up here so you can reopen the
          creatives and the activity log.
        </CardDescription>
        <Link to="/ai-ads/generate" className="inline-block mt-4">
          <Button>Generate creatives</Button>
        </Link>
      </Card>
    );
  }

  return (
    <Card padding="none">
      <ul className="divide-y divide-border">
        {jobs.map((job) => {
          const id = job.job_id || job.id;
          const selected = selectedId === id;
          const live = isLiveJob(job);
          return (
            <li key={id}>
              <Link
                to={`/ai-ads/progress/${id}`}
                className={cn(
                  "flex items-start gap-3 px-4 py-3.5 transition-colors",
                  selected ? "bg-brand-500/8" : "hover:bg-surface-muted/60"
                )}
              >
                {selected ? (
                  <ChevronDown className="h-4 w-4 mt-1 shrink-0 text-brand-600" />
                ) : (
                  <ChevronRight className="h-4 w-4 mt-1 shrink-0 text-content-subtle" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-medium text-content truncate">{jobProductTitle(job, products)}</p>
                    <Badge variant={jobStatusVariant(String(job.status))}>{job.status}</Badge>
                    {live && job.worker_alive ? (
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    ) : null}
                  </div>
                  <p className="text-sm text-content-muted mt-0.5 truncate">
                    {countsLabel(job)}
                    {job.progress_message && !live ? ` · ${job.progress_message}` : ""}
                    {live && job.progress_message ? ` · ${job.progress_message}` : ""}
                  </p>
                </div>
                <div className="text-right shrink-0">
                  <p className="text-xs text-content-subtle">{formatJobWhen(job.created_at)}</p>
                  <p className="text-[11px] text-content-subtle mt-0.5">{durationLabel(job)}</p>
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

export function FinishedJobDetail({
  job,
  products = [],
  onReplay,
  replaying,
}: {
  job: AIAdsJob;
  products?: AIAdsProduct[];
  onReplay?: () => void;
  replaying?: boolean;
}) {
  const [viewer, setViewer] = useState<AIAdsGeneratedCreative | null>(null);
  const [showLog, setShowLog] = useState(false);
  const creatives = (job.creatives || []) as AIAdsGeneratedCreative[];
  const log = (job.progress_log || []) as AIAdsJobLogEntry[];
  const status = String(job.status);
  const ready = creatives.filter((c) => c.status === "READY" || c.status === "APPROVED");

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle>{jobProductTitle(job, products)}</CardTitle>
            <CardDescription className="mt-1">
              {formatJobWhen(job.created_at)}
              {durationLabel(job) ? ` · ${durationLabel(job)}` : ""}
              {job.placement ? ` · ${job.placement}` : ""}
              {job.aspect_ratio ? ` · ${job.aspect_ratio}` : ""}
            </CardDescription>
          </div>
          <Badge variant={jobStatusVariant(status)}>{status}</Badge>
        </div>
      </CardHeader>

      <p className="text-sm text-content-muted mb-4">{countsLabel(job)}</p>
      {job.error_message && (
        <p className="text-sm text-amber-700 dark:text-amber-400 mb-4">{job.error_message}</p>
      )}

      <div className="flex flex-wrap gap-2 mb-5">
        <Link to="/ai-ads/creatives">
          <Button size="sm">
            <Images className="h-3.5 w-3.5" />
            Open in Library
          </Button>
        </Link>
        <Link to="/ai-ads/generate">
          <Button size="sm" variant="outline">
            Generate more
          </Button>
        </Link>
        {onReplay && (
          <Button size="sm" variant="ghost" onClick={onReplay} isLoading={replaying}>
            <RotateCcw className="h-3.5 w-3.5" />
            Run again
          </Button>
        )}
      </div>

      {creatives.length > 0 ? (
        <div className="mb-5">
          <p className="text-xs uppercase tracking-wide text-content-subtle mb-2">
            Creatives · {ready.length}/{creatives.length}
          </p>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {creatives.map((c) => {
              const ad = previewFromGenerated(c);
              return (
                <div key={c.id} className="min-w-0">
                  <button type="button" onClick={() => setViewer(c)} className="w-full text-left">
                    <CreativeFrame ad={ad} compact />
                  </button>
                  <div className="mt-2 flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-content line-clamp-2">
                        {c.headline || c.hook || (c.type === "VIDEO" ? "Video" : "Image ad")}
                      </p>
                      <p className="text-xs text-content-subtle mt-0.5">
                        {c.status}
                        {c.video_url ? " · MP4" : c.preview_url ? " · image" : ""}
                      </p>
                    </div>
                    <DownloadCreativeButton ad={ad} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <p className="text-sm text-content-subtle mb-5">No creatives were saved for this job.</p>
      )}

      <button
        type="button"
        onClick={() => setShowLog((v) => !v)}
        className="flex items-center gap-1 text-sm font-medium text-content-muted hover:text-content"
      >
        {showLog ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        Activity log{log.length ? ` (${log.length})` : ""}
      </button>
      {showLog && (
        <div className="mt-3 max-h-80 overflow-y-auto rounded-xl border border-border bg-surface-muted/30 px-3 py-2 space-y-3">
          {log.length === 0 ? (
            <p className="text-sm text-content-subtle py-4 text-center">No log entries.</p>
          ) : (
            log.map((entry, i) => (
              <div key={`${entry.at || i}-${entry.title}`} className="flex gap-3">
                <span className="text-[11px] tabular-nums text-content-subtle w-[72px] shrink-0 pt-0.5">
                  {formatLogTime(entry.at)}
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
        </div>
      )}

      {viewer && (
        <CreativeViewer ad={previewFromGenerated(viewer)} onClose={() => setViewer(null)} />
      )}
    </Card>
  );
}
