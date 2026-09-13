import { useCallback, useEffect, useMemo, useState } from "react";
import { useStore } from "@/context/StoreContext";
import { api, type AIAdsGeneratedCreative, type AIAdsLibrary, type AIAdsMetaCreative } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { PageLoader } from "@/components/ui/Loading";
import {
  AdPlacementMockup,
  CreativeViewer,
  previewFromGenerated,
  previewFromMeta,
  type AdPreviewModel,
} from "@/pages/ai-ads/CreativeViewer";

type SourceFilter = "all" | "meta" | "generated";

export function CreativesPage() {
  const { activeStore, stores } = useStore();
  const storeId = activeStore?.id ?? stores[0]?.id ?? null;
  const [lib, setLib] = useState<AIAdsLibrary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [source, setSource] = useState<SourceFilter>("all");
  const [status, setStatus] = useState("");
  const [busyId, setBusyId] = useState("");
  const [viewer, setViewer] = useState<AdPreviewModel | null>(null);

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

  async function act(id: string, kind: "approve" | "reject" | "regenerate") {
    if (!storeId) return;
    setBusyId(id);
    try {
      if (kind === "approve") await api.aiAds.approveCreative(storeId, id);
      if (kind === "reject") await api.aiAds.rejectCreative(storeId, id);
      if (kind === "regenerate") await api.aiAds.regenerateCreative(storeId, id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusyId("");
    }
  }

  const generated = lib?.generated ?? [];
  const meta = lib?.meta ?? [];

  if (!storeId) return <p className="text-sm text-content-muted">Select a store first.</p>;
  if (loading) return <PageLoader label="Loading creative library" />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-2 items-end">
        <select
          value={source}
          onChange={(e) => setSource(e.target.value as SourceFilter)}
          className="h-10 rounded-lg border border-border bg-surface px-3 text-sm"
        >
          <option value="all">All sources</option>
          <option value="meta">Existing Meta</option>
          <option value="generated">AI generated</option>
        </select>
        <Input
          placeholder="Filter generated status (READY, APPROVED…)"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="max-w-xs"
        />
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {source !== "generated" && (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold text-content">Existing Meta creatives</h2>
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
      {source !== "meta" && (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold text-content">AI generated creatives</h2>
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
                />
              ))}
            </div>
          )}
        </section>
      )}
      {viewer && <CreativeViewer ad={viewer} onClose={() => setViewer(null)} />}
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
  const dna = creative.dna?.visual as Record<string, unknown> | undefined;
  const perf = creative.performance;
  return (
    <Card padding="sm" className="flex flex-col gap-3">
      <button type="button" onClick={onOpen} className="text-left">
        <AdPlacementMockup ad={previewFromMeta(creative)} compact />
      </button>
      <div>
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-sm">{creative.ad_name || "Untitled ad"}</CardTitle>
          <Badge>{creative.format}</Badge>
        </div>
        <CardDescription className="line-clamp-2">{creative.campaign_name}</CardDescription>
      </div>
      <p className="text-sm text-content line-clamp-3">{creative.primary_text || creative.headline}</p>
      <div className="text-xs text-content-muted space-y-1">
        {perf?.insufficient_data ? (
          <p>Performance: insufficient data</p>
        ) : (
          <p>
            CTR {fmtPct(perf?.ctr)} · ROAS {fmtNum(perf?.roas)} · CPA {fmtNum(perf?.cpa)} · Spend{" "}
            {fmtNum(perf?.spend)}
          </p>
        )}
        {dna?.style ? <p>DNA: {String(dna.style)} · {String(dna.composition || "")}</p> : <p>DNA: not analyzed yet</p>}
        {creative.dna?.analysis_basis && (
          <p>Analysis basis: {creative.dna.analysis_basis}</p>
        )}
      </div>
      <Button size="sm" variant="outline" onClick={onOpen}>
        View ad
      </Button>
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
}: {
  creative: AIAdsGeneratedCreative;
  busy: boolean;
  onOpen: () => void;
  onApprove: () => void;
  onReject: () => void;
  onRegen: () => void;
}) {
  const sources = useMemo(() => creative.source_creative_ids ?? [], [creative.source_creative_ids]);
  const canApprove = creative.status === "READY";
  const canRegen = creative.status === "READY" || creative.status === "FAILED" || creative.status === "REJECTED";
  return (
    <Card padding="sm" className="flex flex-col gap-3">
      <button type="button" onClick={onOpen} className="text-left">
        <AdPlacementMockup ad={previewFromGenerated(creative)} compact />
      </button>
      <div className="flex items-start justify-between gap-2">
        <CardTitle className="text-sm">{creative.headline || creative.hook || "Untitled"}</CardTitle>
        <Badge variant={statusVariant(creative.status)}>{creative.status}</Badge>
      </div>
      <p className="text-sm text-content-muted line-clamp-3">{creative.hook}</p>
      <p className="text-xs text-content-subtle">
        AI Creative Evaluation: {creative.ai_score ?? "—"}/100 — not a guaranteed ROAS
      </p>
      {creative.rationale && (
        <p className="text-xs text-content-muted">Why: {creative.rationale}</p>
      )}
      {sources.length > 0 && (
        <p className="text-xs text-content-subtle">Inspired by Meta creatives: {sources.join(", ")}</p>
      )}
      <div className="flex flex-wrap gap-2 mt-auto">
        <Button size="sm" variant="outline" onClick={onOpen}>
          View ad
        </Button>
        {canApprove && (
          <>
            <Button size="sm" onClick={onApprove} isLoading={busy}>
              Approve
            </Button>
            <Button size="sm" variant="outline" onClick={onReject} disabled={busy}>
              Reject
            </Button>
          </>
        )}
        {canRegen && (
          <Button size="sm" variant="ghost" onClick={onRegen} disabled={busy}>
            Regenerate
          </Button>
        )}
      </div>
      {creative.failure_reason && (
        <p className="text-xs text-red-600">{creative.failure_reason}</p>
      )}
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
