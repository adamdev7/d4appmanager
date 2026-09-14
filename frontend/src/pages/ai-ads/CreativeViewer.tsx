import { useEffect, useMemo, useState } from "react";
import { Pause, Play, SkipBack, SkipForward, X } from "lucide-react";
import type { AIAdsGeneratedCreative, AIAdsMetaCreative } from "@/lib/aiAdsTypes";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";

export type AdPreviewModel = {
  kind: "generated" | "meta";
  type: string;
  headline: string;
  primaryText: string;
  hook: string;
  cta: string;
  previewUrl: string | null;
  videoUrl: string | null;
  visualDirection: string;
  aspectRatio: string;
  storyboard: AIAdsGeneratedCreative["storyboard"];
  status?: string;
  hasRenderedMedia?: boolean;
};

export function previewFromGenerated(c: AIAdsGeneratedCreative): AdPreviewModel {
  return {
    kind: "generated",
    type: c.type || "IMAGE",
    headline: c.headline || c.hook || "Untitled",
    primaryText: c.primary_text || c.hook || "",
    hook: c.hook || "",
    cta: (c.cta || "SHOP NOW").replace(/_/g, " "),
    previewUrl: c.preview_url || null,
    videoUrl: c.video_url || null,
    visualDirection: c.visual_direction || "",
    aspectRatio: c.aspect_ratio || c.storyboard?.format || "4:5",
    storyboard: c.storyboard,
    status: c.status,
    hasRenderedMedia: Boolean(c.has_rendered_media || c.video_url || c.preview_url),
  };
}

export function previewFromMeta(c: AIAdsMetaCreative): AdPreviewModel {
  return {
    kind: "meta",
    type: c.format || "IMAGE",
    headline: c.headline || c.ad_name || "Untitled ad",
    primaryText: c.primary_text || c.headline || "",
    hook: c.primary_text || "",
    cta: (c.cta || "SHOP NOW").replace(/_/g, " "),
    previewUrl: c.preview_url || null,
    videoUrl: null,
    visualDirection: "",
    aspectRatio: "4:5",
    storyboard: null,
    hasRenderedMedia: Boolean(c.preview_url),
  };
}

export function AdPlacementMockup({
  ad,
  compact = false,
}: {
  ad: AdPreviewModel;
  compact?: boolean;
}) {
  const tall = ad.aspectRatio === "9:16" || ad.type === "VIDEO";
  return (
    <div
      className={cn(
        "overflow-hidden rounded-lg border border-border bg-[#1c1c1e] text-white",
        compact ? "h-44" : tall ? "min-h-[420px]" : "min-h-[320px]"
      )}
    >
      <div className="flex items-center gap-2 px-3 py-2 text-[11px] text-white/70">
        <span className="h-6 w-6 rounded-full bg-white/15" />
        <span className="font-medium text-white/90">Your Page</span>
        <span className="ml-auto uppercase tracking-wide text-white/40">
          {ad.type === "VIDEO" ? "Video" : "Sponsored"}
        </span>
      </div>
      {!compact && ad.primaryText && (
        <p className="px-3 pb-2 text-sm leading-snug text-white/90">{ad.primaryText}</p>
      )}
      <CreativeStage ad={ad} compact={compact} />
      <div className="flex items-center justify-between gap-2 px-3 py-2.5 bg-black/40">
        <div className="min-w-0">
          <p className={cn("font-semibold truncate", compact ? "text-xs" : "text-sm")}>
            {ad.headline}
          </p>
          {!compact && ad.hook && ad.hook !== ad.headline && (
            <p className="text-xs text-white/60 line-clamp-1">{ad.hook}</p>
          )}
        </div>
        <span className="shrink-0 rounded bg-white/90 px-2 py-1 text-[10px] font-semibold uppercase text-black">
          {ad.cta}
        </span>
      </div>
    </div>
  );
}

function CreativeStage({ ad, compact }: { ad: AdPreviewModel; compact: boolean }) {
  const [broken, setBroken] = useState(false);
  const videoUrl = ad.videoUrl;
  const showImage = Boolean(ad.previewUrl) && !broken && !videoUrl;

  if (videoUrl) {
    return (
      <div className={cn("relative bg-black", compact ? "h-[7.5rem]" : "h-64 sm:h-80")}>
        <video
          src={videoUrl}
          poster={ad.previewUrl || undefined}
          className="h-full w-full object-cover"
          controls={!compact}
          muted
          playsInline
          loop={compact}
          autoPlay={compact}
        />
      </div>
    );
  }

  if (showImage) {
    return (
      <div className={cn("relative bg-black", compact ? "h-[7.5rem]" : "h-64 sm:h-80")}>
        <img
          src={ad.previewUrl!}
          alt=""
          className="h-full w-full object-cover"
          onError={() => setBroken(true)}
        />
      </div>
    );
  }

  const scene = ad.storyboard?.scenes?.[0];
  const body = scene?.visual || ad.visualDirection || (ad.status === "FAILED"
    ? "Media was not rendered for this concept."
    : "No rendered file yet.");

  return (
    <div
      className={cn(
        "flex flex-col justify-end bg-gradient-to-br from-zinc-800 to-zinc-950 px-3 py-3",
        compact ? "h-[7.5rem]" : "h-64 sm:h-80"
      )}
    >
      <p className={cn("text-white/85 line-clamp-5", compact ? "text-[11px]" : "text-sm")}>{body}</p>
    </div>
  );
}

export function CreativeViewer({
  ad,
  onClose,
}: {
  ad: AdPreviewModel;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        type="button"
        className="absolute inset-0 bg-black/50 backdrop-blur-[1px]"
        aria-label="Close preview"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="creative-viewer-title"
        className="relative w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-xl border border-border bg-surface p-5 shadow-elevated"
      >
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            <h2 id="creative-viewer-title" className="text-lg font-semibold text-content">
              Ad preview
            </h2>
            <p className="text-sm text-content-muted mt-0.5">
              {ad.videoUrl
                ? "Rendered MP4 — this is the file Meta will receive when you publish."
                : ad.previewUrl
                  ? "Rendered image — this is the file Meta will receive when you publish."
                  : "No rendered file yet. Generate again before publishing."}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-content-muted hover:bg-surface-muted hover:text-content"
            aria-label="Close dialog"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <AdPlacementMockup ad={ad} />

        {ad.type === "VIDEO" && !ad.videoUrl && ad.storyboard?.scenes?.length ? (
          <StoryboardPlayer storyboard={ad.storyboard} previewUrl={ad.previewUrl} />
        ) : null}

        <dl className="mt-4 space-y-2 text-sm">
          {ad.hook && (
            <div>
              <dt className="text-xs uppercase tracking-wide text-content-subtle">Hook</dt>
              <dd className="text-content">{ad.hook}</dd>
            </div>
          )}
          {ad.visualDirection && (
            <div>
              <dt className="text-xs uppercase tracking-wide text-content-subtle">Visual direction</dt>
              <dd className="text-content-muted">{ad.visualDirection}</dd>
            </div>
          )}
        </dl>

        <div className="mt-5 flex justify-end">
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}

function StoryboardPlayer({
  storyboard,
  previewUrl,
}: {
  storyboard: NonNullable<AIAdsGeneratedCreative["storyboard"]>;
  previewUrl?: string | null;
}) {
  const scenes = useMemo(() => storyboard.scenes ?? [], [storyboard.scenes]);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const scene = scenes[index];
  const durationMs = Math.max(1.2, Number(scene?.duration) || 2) * 1000;

  useEffect(() => {
    if (!playing || scenes.length === 0) return;
    const t = window.setTimeout(() => {
      setIndex((i) => {
        if (i + 1 >= scenes.length) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, durationMs);
    return () => window.clearTimeout(t);
  }, [playing, index, durationMs, scenes.length]);

  if (!scene) return null;

  return (
    <div className="mt-4 rounded-lg border border-border bg-surface-muted/40 p-3">
      <div className="flex items-center justify-between gap-2 mb-2">
        <p className="text-xs font-medium uppercase tracking-wide text-content-subtle">
          Scene {index + 1} of {scenes.length} · {storyboard.duration ?? "—"}s
        </p>
        <div className="flex items-center gap-1">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setIndex((i) => Math.max(0, i - 1))}
            disabled={index === 0}
            aria-label="Previous scene"
          >
            <SkipBack className="h-3.5 w-3.5" />
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => setPlaying((p) => !p)}
            aria-label={playing ? "Pause storyboard" : "Play storyboard"}
          >
            {playing ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
            {playing ? "Pause" : "Play"}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setIndex((i) => Math.min(scenes.length - 1, i + 1))}
            disabled={index === scenes.length - 1}
            aria-label="Next scene"
          >
            <SkipForward className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
      <div className="rounded-md bg-zinc-950 text-white overflow-hidden">
        {previewUrl ? (
          <img src={previewUrl} alt="" className="h-48 w-full object-cover" />
        ) : null}
        <div className="p-3 min-h-[7rem]">
          {scene.text_overlay && (
            <p className="text-[10px] uppercase tracking-wide text-white/50 mb-1">On-screen text</p>
          )}
          <p className="text-sm font-medium">{scene.text_overlay || `Scene ${index + 1}`}</p>
          <p className="mt-2 text-sm text-white/80">{scene.visual}</p>
          {scene.voiceover && (
            <p className="mt-2 text-xs italic text-white/60">VO: {scene.voiceover}</p>
          )}
        </div>
      </div>
    </div>
  );
}
