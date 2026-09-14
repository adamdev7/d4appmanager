import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  Check,
  Film,
  MoreHorizontal,
  Play,
  RefreshCw,
  RotateCcw,
  Send,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { useStore } from "@/context/StoreContext";
import {
  api,
  type AIAdsAdset,
  type AIAdsGeneratedCreative,
  type AIAdsLibrary,
  type AIAdsMetaCreative,
} from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardTitle } from "@/components/ui/Card";
import { Select } from "@/components/ui/Select";
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

type SourceFilter = "generated" | "meta";

const STATUSES = ["READY", "APPROVED", "PUBLISHED", "REJECTED", "FAILED"] as const;

export function CreativesPage() {
  const { activeStore, stores } = useStore();
  const storeId = activeStore?.id ?? stores[0]?.id ?? null;
  const [lib, setLib] = useState<AIAdsLibrary | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [source, setSource] = useState<SourceFilter>("generated");
  const [status, setStatus] = useState("");
  const [busyId, setBusyId] = useState("");
  const [bulk, setBulk] = useState(false);
  const [viewer, setViewer] = useState<AdPreviewModel | null>(null);
  const [publishFor, setPublishFor] = useState<AIAdsGeneratedCreative | null>(null);
  const [adsets, setAdsets] = useState<AIAdsAdset[]>([]);
  const [adsetId, setAdsetId] = useState("");
  const [activate, setActivate] = useState(false);
  const [publishing, setPublishing] = useState(false);

  // Loaded in one shot so switching filters is instant and the counts are honest.
  const load = useCallback(async () => {
    if (!storeId) return;
    setError("");
    setLib(await api.aiAds.getCreatives(storeId, {}));
  }, [storeId]);

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

  async function refresh() {
    setRefreshing(true);
    try {
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Refresh failed");
    } finally {
      setRefreshing(false);
    }
  }

  async function act(id: string, kind: "approve" | "reject" | "regenerate" | "delete") {
    if (!storeId) return;
    if (kind === "delete") {
      const ok = window.confirm(
        "Delete this creative permanently? The rendered MP4 and its database row will be removed."
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

  async function approveAll(ids: string[]) {
    if (!storeId || ids.length === 0) return;
    setBulk(true);
    setError("");
    try {
      for (const id of ids) {
        await api.aiAds.approveCreative(storeId, id);
      }
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not approve every clip");
    } finally {
      setBulk(false);
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
    if (
      activate &&
      !window.confirm(
        "This will create an ACTIVE Meta ad and start spending on that ad set. Continue?"
      )
    ) {
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

  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const c of generated) {
      const key = String(c.status || "");
      counts[key] = (counts[key] || 0) + 1;
    }
    return counts;
  }, [generated]);

  const visibleGenerated = useMemo(
    () => (status ? generated.filter((c) => c.status === status) : generated),
    [generated, status]
  );
  const readyIds = useMemo(
    () => generated.filter((c) => c.status === "READY").map((c) => c.id),
    [generated]
  );

  if (!storeId) return <p className="text-sm text-content-muted">Select a store first.</p>;
  if (loading) return <PageLoader label="Loading creative library" />;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <div className="inline-flex rounded-xl border border-border bg-surface-muted p-1">
          {(
            [
              ["generated", "Astra videos", generated.length],
              ["meta", "Your Meta ads", meta.length],
            ] as const
          ).map(([id, label, count]) => (
            <button
              key={id}
              type="button"
              onClick={() => setSource(id)}
              aria-pressed={source === id}
              className={cn(
                "inline-flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-sm font-medium transition-all duration-150",
                source === id
                  ? "bg-surface text-content shadow-sm ring-1 ring-inset ring-brand-500/25"
                  : "text-content-muted hover:text-content"
              )}
            >
              {label}
              <span className="text-xs tabular-nums text-content-subtle">{count}</span>
            </button>
          ))}
        </div>

        {source === "generated" && (
          <>
            <Select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="h-9 w-auto min-w-[10rem]"
              aria-label="Filter by status"
            >
              <option value="">All statuses ({generated.length})</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s.charAt(0) + s.slice(1).toLowerCase()} ({statusCounts[s] || 0})
                </option>
              ))}
            </Select>
            {readyIds.length > 1 && (
              <Button
                variant="secondary"
                size="sm"
                isLoading={bulk}
                onClick={() => void approveAll(readyIds)}
              >
                <Check className="h-3.5 w-3.5" />
                Approve all {readyIds.length}
              </Button>
            )}
          </>
        )}

        <Button
          variant="ghost"
          size="sm"
          className="ml-auto"
          isLoading={refreshing}
          onClick={() => void refresh()}
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </Button>
      </div>

      {error && (
        <p className="flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-600">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </p>
      )}

      {source === "generated" ? (
        visibleGenerated.length === 0 ? (
          <EmptyState
            icon={Film}
            title={status ? `Nothing is ${status.toLowerCase()} right now` : "No videos yet"}
            body={
              status
                ? "Clear the status filter to see the rest of the library."
                : "Pick a product, lock its photos, and Astra renders vertical clips you can caption yourself."
            }
            action={
              status ? (
                <Button variant="outline" onClick={() => setStatus("")}>
                  Clear filter
                </Button>
              ) : (
                <Link to="/ai-ads/generate">
                  <Button>
                    <Sparkles className="h-4 w-4" />
                    Generate videos
                  </Button>
                </Link>
              )
            }
          />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {visibleGenerated.map((c) => (
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
        )
      ) : meta.length === 0 ? (
        <EmptyState
          icon={RefreshCw}
          title="No Meta ads imported"
          body="Sync your ad account from Overview. Astra studies these ads before writing anything new."
          action={
            <Link to="/ai-ads">
              <Button>Go to Overview</Button>
            </Link>
          }
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {meta.map((c) => (
            <MetaCard key={c.id} creative={c} onOpen={() => setViewer(previewFromMeta(c))} />
          ))}
        </div>
      )}

      {viewer && <CreativeViewer ad={viewer} onClose={() => setViewer(null)} />}

      {publishFor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button
            type="button"
            className="absolute inset-0 bg-black/50 backdrop-blur-[1px]"
            aria-label="Close publish"
            onClick={() => setPublishFor(null)}
          />
          <Card className="relative z-10 w-full max-w-md">
            <CardTitle>Publish to Meta</CardTitle>
            <CardDescription className="mb-4 mt-1">
              Uploads the rendered {publishFor.video_url ? "MP4" : "image"} into your ad account,
              then creates the ad in the selected ad set.
            </CardDescription>
            <Select
              label="Ad set"
              value={adsetId}
              onChange={(e) => setAdsetId(e.target.value)}
              className="mb-3"
            >
              {adsets.length === 0 && <option value="">No ad sets found</option>}
              {adsets.map((set) => (
                <option key={set.id} value={set.id}>
                  {set.name}
                  {set.status ? ` · ${set.status}` : ""}
                </option>
              ))}
            </Select>
            <label
              className={cn(
                "mb-4 flex cursor-pointer items-start gap-2.5 rounded-lg border p-3 text-sm transition-colors",
                activate
                  ? "border-amber-500/40 bg-amber-500/5 text-content"
                  : "border-border text-content-muted hover:bg-surface-muted/60"
              )}
            >
              <input
                type="checkbox"
                className="mt-0.5 h-4 w-4 accent-brand-600"
                checked={activate}
                onChange={(e) => setActivate(e.target.checked)}
              />
              <span>
                <span className="block font-medium text-content">Turn the ad on now</span>
                Leave this off to create it paused and review inside Meta first.
              </span>
            </label>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => void publish()} isLoading={publishing} disabled={!adsetId}>
                <Send className="h-4 w-4" />
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

function EmptyState({
  icon: Icon,
  title,
  body,
  action,
}: {
  icon: typeof Film;
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <Card className="py-12 text-center">
      <span className="mx-auto grid h-11 w-11 place-items-center rounded-xl bg-surface-muted">
        <Icon className="h-5 w-5 text-content-subtle" />
      </span>
      <p className="mt-3 font-semibold text-content">{title}</p>
      <p className="mx-auto mt-1 max-w-sm text-sm text-content-muted">{body}</p>
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </Card>
  );
}

function MediaButton({ ad, onOpen }: { ad: AdPreviewModel; onOpen: () => void }) {
  return (
    <button type="button" onClick={onOpen} className="group relative block w-full text-left">
      <CreativeFrame ad={ad} compact />
      <span className="absolute inset-0 flex items-center justify-center rounded-lg bg-black/40 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-white/95 px-3 py-1.5 text-xs font-semibold text-black">
          <Play className="h-3 w-3" />
          Open
        </span>
      </span>
    </button>
  );
}

function MetaCard({ creative, onOpen }: { creative: AIAdsMetaCreative; onOpen: () => void }) {
  const ad = previewFromMeta(creative);
  const perf = creative.performance;
  return (
    <Card padding="sm" className="flex flex-col gap-3">
      <MediaButton ad={ad} onOpen={onOpen} />
      <div className="flex items-start justify-between gap-2">
        <CardTitle className="text-sm leading-snug">{creative.ad_name || "Untitled ad"}</CardTitle>
        <Badge>{creative.format}</Badge>
      </div>
      <p className="line-clamp-2 text-sm text-content-muted">
        {creative.primary_text || creative.headline}
      </p>
      <p className="text-xs text-content-subtle">
        {perf?.insufficient_data
          ? "Not enough data yet"
          : `CTR ${fmtPct(perf?.ctr)} · ROAS ${fmtNum(perf?.roas)} · Spend ${fmtNum(perf?.spend)}`}
      </p>
      <div className="mt-auto flex flex-wrap gap-2">
        <DownloadCreativeButton ad={ad} />
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
  const status = String(creative.status || "");
  const canApprove = status === "READY";
  const canPublish =
    status === "APPROVED" &&
    Boolean(creative.has_rendered_media || creative.preview_url || creative.video_url);
  const canRegen = status === "READY" || status === "FAILED" || status === "REJECTED";

  return (
    <Card padding="sm" className="flex flex-col gap-3">
      <MediaButton ad={ad} onOpen={onOpen} />
      <div className="flex items-start justify-between gap-2">
        <CardTitle className="text-sm leading-snug">
          {creative.headline || creative.hook || "Untitled"}
        </CardTitle>
        <Badge variant={statusVariant(status)}>{status}</Badge>
      </div>
      {creative.hook && creative.hook !== creative.headline && (
        <p className="line-clamp-2 text-sm text-content-muted">{creative.hook}</p>
      )}
      <p className="text-xs text-content-subtle">
        {creative.video_url ? "MP4 ready" : creative.preview_url ? "Image ready" : "No file"}
        {creative.ai_score != null ? ` · AI score ${creative.ai_score}/100` : ""}
      </p>
      {creative.failure_reason && (
        <p className="text-sm text-amber-600 dark:text-amber-400">{creative.failure_reason}</p>
      )}
      <div className="mt-auto flex flex-wrap items-center gap-2">
        {canApprove && (
          <Button size="sm" onClick={onApprove} isLoading={busy}>
            <Check className="h-3.5 w-3.5" />
            Approve
          </Button>
        )}
        {canPublish && (
          <Button size="sm" onClick={onPublish} disabled={busy}>
            <Send className="h-3.5 w-3.5" />
            Publish
          </Button>
        )}
        <DownloadCreativeButton ad={ad} />
        <MoreMenu
          disabled={busy}
          items={[
            canApprove ? { label: "Reject", icon: X, onClick: onReject } : null,
            canRegen ? { label: "Regenerate", icon: RotateCcw, onClick: onRegen } : null,
            { label: "Delete", icon: Trash2, onClick: onDelete, danger: true },
          ]}
        />
      </div>
    </Card>
  );
}

type MenuItem = {
  label: string;
  icon: typeof Trash2;
  onClick: () => void;
  danger?: boolean;
};

function MoreMenu({ items, disabled }: { items: (MenuItem | null)[]; disabled?: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const visible = items.filter((i): i is MenuItem => i !== null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (visible.length === 0) return null;

  return (
    <div ref={ref} className="relative ml-auto">
      <Button
        size="sm"
        variant="ghost"
        disabled={disabled}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="More actions"
        onClick={() => setOpen((v) => !v)}
      >
        <MoreHorizontal className="h-4 w-4" />
      </Button>
      {open && (
        <div
          role="menu"
          className="absolute bottom-full right-0 z-20 mb-1 w-44 overflow-hidden rounded-lg border border-border bg-surface py-1 shadow-elevated"
        >
          {visible.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                item.onClick();
              }}
              className={cn(
                "flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors",
                item.danger
                  ? "text-red-600 hover:bg-red-500/10"
                  : "text-content-muted hover:bg-surface-muted hover:text-content"
              )}
            >
              <item.icon className="h-3.5 w-3.5 shrink-0" />
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
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
