import { useCallback, useEffect, useState } from "react";
import { useStore } from "@/context/StoreContext";
import { api, type AIAdsAdset, type AIAdsGeneratedCreative, type AIAdsLibrary, type AIAdsMetaCreative } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardTitle } from "@/components/ui/Card";
import { PageLoader } from "@/components/ui/Loading";
import {
  CreativeFrame,
  CreativeViewer,
  DownloadCreativeButton,
  previewFromGenerated,
  previewFromMeta,
  type AdPreviewModel,
} from "@/pages/ai-ads/CreativeViewer";
import { cn } from "@/lib/cn";

type SourceFilter = "generated" | "meta" | "all";

export function CreativesPage() {
  const { activeStore, stores } = useStore();
  const storeId = activeStore?.id ?? stores[0]?.id ?? null;
  const [lib, setLib] = useState<AIAdsLibrary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [source, setSource] = useState<SourceFilter>("generated");
  const [status, setStatus] = useState("");
  const [busyId, setBusyId] = useState("");
  const [viewer, setViewer] = useState<AdPreviewModel | null>(null);
  const [publishFor, setPublishFor] = useState<AIAdsGeneratedCreative | null>(null);
  const [adsets, setAdsets] = useState<AIAdsAdset[]>([]);
  const [adsetId, setAdsetId] = useState("");
  const [activate, setActivate] = useState(false);
  const [publishing, setPublishing] = useState(false);

  const load = useCallback(async () => {
    if (!storeId) return;
    setError("");
    const data = await api.aiAds.getCreatives(storeId, {
      source: source === "all" ? undefined : source,
      status: status || undefined,
    });
    setLib(data);
  }, [storeId, source, status]);

  useEffect(() => {
    if (!storeId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    load()
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load library"))
      .finally(() => setLoading(false));
  }, [load, storeId]);

  async function act(id: string, kind: "approve" | "reject" | "regenerate" | "delete") {
    if (!storeId) return;
    if (kind === "delete") {
      const ok = window.confirm(
        "Delete this creative permanently? The rendered image or MP4 and its database row will be removed."
      );
      if (!ok) return;
    }
    setBusyId(id);
    try {
      if (kind === "approve") await api.aiAds.approveCreative(storeId, id);
      if (kind === "reject") await api.aiAds.rejectCreative(storeId, id);
      if (kind === "regenerate") await api.aiAds.regenerateCreative(storeId, id);
      if (kind === "delete") {
        await api.aiAds.deleteCreative(storeId, id);
        setViewer(null);
      }
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusyId("");
    }
  }

  async function openPublish(creative: AIAdsGeneratedCreative) {
    if (!storeId) return;
    setPublishFor(creative);
    setActivate(false);
    setError("");
    try {
      const rows = await api.aiAds.listAdsets(storeId);
      setAdsets(rows);
      setAdsetId(rows[0]?.id || "");
    } catch (e) {
      setAdsets([]);
      setAdsetId("");
      setError(e instanceof Error ? e.message : "Could not load ad sets");
    }
  }

  async function publish() {
    if (!storeId || !publishFor || !adsetId) return;
    if (activate && !window.confirm("This will create an ACTIVE Meta ad and start spending on that ad set. Continue?")) {
      return;
    }
    setPublishing(true);
    setError("");
    try {
      await api.aiAds.publishCreative(storeId, publishFor.id, { adset_id: adsetId, activate });
      setPublishFor(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Publish failed");
    } finally {
      setPublishing(false);
    }
  }

  const generated = lib?.generated ?? [];
  const meta = lib?.meta ?? [];

  if (!storeId) return <p className="text-sm text-content-muted">Select a store first.</p>;
  if (loading) return <PageLoader label="Loading creative library" />;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center gap-2">
        {(
          [
            ["generated", "Generated"],
            ["meta", "From Meta"],
            ["all", "All"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setSource(id)}
            className={cn(
              "rounded-full border px-3 py-1.5 text-sm font-medium",
              source === id
                ? "border-brand-500 bg-brand-500/10 text-brand-700 dark:text-brand-400"
                : "border-border text-content-muted hover:text-content"
            )}
          >
            {label}
          </button>
        ))}
        {source !== "meta" && (
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="ml-auto h-9 rounded-lg border border-border bg-surface px-3 text-sm"
          >
            <option value="">All statuses</option>
            <option value="READY">Ready</option>
            <option value="APPROVED">Approved</option>
            <option value="FAILED">Failed</option>
            <option value="REJECTED">Rejected</option>
            <option value="PUBLISHED">Published</option>
          </select>
        )}
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {source !== "meta" && (
        <section className="space-y-4">
          <div>
            <h2 className="text-lg font-semibold text-content">Generated creatives</h2>
            <p className="text-sm text-content-muted">
              Open a tile for the full file, or download it.
            </p>
          </div>
          {generated.length === 0 ? (
            <Empty text="No generated creatives yet. Open Generate to create a batch." />
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {generated.map((c) => (
                <GeneratedCard
                  key={c.id}
                  creative={c}
                  busy={busyId === c.id}
                  onOpen={() => setViewer(previewFromGenerated(c))}
                  onApprove={() => void act(c.id, "approve")}
                  onReject={() => void act(c.id, "reject")}
                  onRegen={() => void act(c.id, "regenerate")}
                  onDelete={() => void act(c.id, "delete")}
                  onPublish={() => void openPublish(c)}
                />
              ))}
            </div>
          )}
        </section>
      )}
      {source !== "generated" && (
        <section className="space-y-4">
          <div>
            <h2 className="text-lg font-semibold text-content">Existing Meta ads</h2>
            <p className="text-sm text-content-muted">Imported from your ad account.</p>
          </div>
          {meta.length === 0 ? (
            <Empty text="No Meta creatives imported yet. Sync Meta ads from Overview." />
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {meta.map((c) => (
                <MetaCard key={c.id} creative={c} onOpen={() => setViewer(previewFromMeta(c))} />
              ))}
            </div>
          )}
        </section>
      )}
      {viewer && <CreativeViewer ad={viewer} onClose={() => setViewer(null)} />}
      {publishFor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button
            type="button"
            className="absolute inset-0 bg-black/50"
            aria-label="Close publish"
            onClick={() => setPublishFor(null)}
          />
          <Card className="relative w-full max-w-md z-10">
            <CardTitle>Publish to Meta</CardTitle>
            <CardDescription className="mt-1 mb-4">
              Uploads the rendered {publishFor.video_url ? "MP4" : "image"} into your ad account, then
              creates the ad in the selected ad set.
            </CardDescription>
            <label className="block text-sm font-medium text-content mb-3">
              Ad set
              <select
                value={adsetId}
                onChange={(e) => setAdsetId(e.target.value)}
                className="mt-1.5 flex h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm"
              >
                {adsets.length === 0 && <option value="">No ad sets found</option>}
                {adsets.map((set) => (
                  <option key={set.id} value={set.id}>
                    {set.name}
                    {set.status ? ` · ${set.status}` : ""}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-start gap-2 text-sm text-content mb-4">
              <input
                type="checkbox"
                className="mt-1"
                checked={activate}
                onChange={(e) => setActivate(e.target.checked)}
              />
              <span>Turn the ad on now and start spending. Leave unchecked to create it paused.</span>
            </label>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => void publish()} isLoading={publishing} disabled={!adsetId}>
                {activate ? "Publish and spend" : "Publish paused"}
              </Button>
              <Button variant="outline" onClick={() => setPublishFor(null)} disabled={publishing}>
                Cancel
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <Card>
      <p className="text-sm text-content-subtle">{text}</p>
    </Card>
  );
}

function MetaCard({
  creative,
  onOpen,
}: {
  creative: AIAdsMetaCreative;
  onOpen: () => void;
}) {
  const ad = previewFromMeta(creative);
  const perf = creative.performance;
  return (
    <Card padding="sm" className="flex flex-col gap-3">
      <button type="button" onClick={onOpen} className="text-left">
        <CreativeFrame ad={ad} compact />
      </button>
      <div className="flex items-start justify-between gap-2">
        <CardTitle className="text-base leading-snug">{creative.ad_name || "Untitled ad"}</CardTitle>
        <Badge>{creative.format}</Badge>
      </div>
      <p className="text-sm text-content-muted line-clamp-2">{creative.primary_text || creative.headline}</p>
      <p className="text-xs text-content-subtle">
        {perf?.insufficient_data
          ? "Performance: insufficient data"
          : `CTR ${fmtPct(perf?.ctr)} · ROAS ${fmtNum(perf?.roas)} · Spend ${fmtNum(perf?.spend)}`}
      </p>
      <div className="flex flex-wrap gap-2 mt-auto">
        <DownloadCreativeButton ad={ad} />
        <Button size="sm" variant="outline" onClick={onOpen}>
          Open
        </Button>
      </div>
    </Card>
  );
}

function GeneratedCard({
  creative,
  busy,
  onOpen,
  onApprove,
  onReject,
  onRegen,
  onDelete,
  onPublish,
}: {
  creative: AIAdsGeneratedCreative;
  busy: boolean;
  onOpen: () => void;
  onApprove: () => void;
  onReject: () => void;
  onRegen: () => void;
  onDelete: () => void;
  onPublish: () => void;
}) {
  const ad = previewFromGenerated(creative);
  const canApprove = creative.status === "READY";
  const canRegen = creative.status === "READY" || creative.status === "FAILED" || creative.status === "REJECTED";
  const fileLabel = creative.video_url
    ? "MP4 ready"
    : creative.preview_url
      ? "Image ready"
      : "No file";
  return (
    <Card padding="sm" className="flex flex-col gap-3">
      <button type="button" onClick={onOpen} className="text-left">
        <CreativeFrame ad={ad} compact />
      </button>
      <div className="flex items-start justify-between gap-2">
        <CardTitle className="text-base leading-snug">
          {creative.headline || creative.hook || "Untitled"}
        </CardTitle>
        <Badge variant={statusVariant(creative.status)}>{creative.status}</Badge>
      </div>
      {creative.hook && creative.hook !== creative.headline && (
        <p className="text-sm text-content-muted line-clamp-2">{creative.hook}</p>
      )}
      <p className="text-xs text-content-subtle">
        {fileLabel}
        {creative.ai_score != null ? ` · AI score ${creative.ai_score}/100` : ""}
      </p>
      {creative.failure_reason && (
        <p className="text-sm text-red-600">{creative.failure_reason}</p>
      )}
      <div className="flex flex-wrap gap-2 mt-auto">
        <DownloadCreativeButton ad={ad} />
        <Button size="sm" variant="outline" onClick={onOpen}>
          Open
        </Button>
        {canApprove && (
          <>
            <Button size="sm" onClick={onApprove} isLoading={busy}>
              Approve
            </Button>
            <Button size="sm" variant="ghost" onClick={onReject} disabled={busy}>
              Reject
            </Button>
          </>
        )}
        {creative.status === "APPROVED" && (creative.has_rendered_media || creative.preview_url || creative.video_url) && (
          <Button size="sm" onClick={onPublish} disabled={busy}>
            Publish
          </Button>
        )}
        {canRegen && (
          <Button size="sm" variant="ghost" onClick={onRegen} disabled={busy}>
            Regenerate
          </Button>
        )}
        <Button size="sm" variant="danger" onClick={onDelete} disabled={busy}>
          Delete
        </Button>
      </div>
    </Card>
  );
}

function statusVariant(status?: string) {
  if (status === "APPROVED" || status === "READY") return "success" as const;
  if (status === "FAILED" || status === "REJECTED") return "warning" as const;
  if (status === "PUBLISHED") return "brand" as const;
  return "default" as const;
}

function fmtPct(n?: number | null) {
  if (n == null) return "—";
  return `${n.toFixed(2)}%`;
}
function fmtNum(n?: number | null) {
  if (n == null) return "—";
  return n.toFixed(2);
}
