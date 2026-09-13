import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Images, Lightbulb, RefreshCw, Sparkles, WandSparkles } from "lucide-react";
import { useStore } from "@/context/StoreContext";
import { api, type AIAdsOverview } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { PageLoader, UpdatingBadge } from "@/components/ui/Loading";
import { GenerationStudio } from "@/pages/ai-ads/GenerationStudio";

export function AIAdsDashboardPage() {
  const { activeStore, stores } = useStore();
  const storeId = activeStore?.id ?? stores[0]?.id ?? null;
  const [data, setData] = useState<AIAdsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!storeId) {
      setLoading(false);
      return;
    }
    setError("");
    try {
      setData(await api.aiAds.getOverview(storeId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load AI Ads");
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => {
    setLoading(true);
    void load();
  }, [load]);

  useEffect(() => {
    const live = data?.active_job;
    const liveId =
      live && ["QUEUED", "RUNNING"].includes(String(live.status)) ? live.job_id || live.id : null;
    if (!storeId || !liveId) return;
    const t = window.setInterval(() => {
      api.aiAds
        .getOverview(storeId)
        .then(setData)
        .catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(t);
  }, [data?.active_job?.id, data?.active_job?.status, storeId]);

  async function sync() {
    if (!storeId) return;
    setSyncing(true);
    setError("");
    try {
      await api.aiAds.syncMeta(storeId);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Meta sync failed");
    } finally {
      setSyncing(false);
    }
  }

  if (!storeId) {
    return (
      <Card>
        <CardTitle>Connect a Shopify store</CardTitle>
        <CardDescription className="mt-2">
          AI Ads uses Shopify products and Meta ads from the selected store.
        </CardDescription>
        <Link to="/settings/stores" className="inline-block mt-4">
          <Button>Open stores</Button>
        </Link>
      </Card>
    );
  }

  if (loading && !data) return <PageLoader label="Loading AI Ads" />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold text-content">AI Creative Engine</h2>
          {syncing && <UpdatingBadge label="Syncing Meta" />}
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => void sync()} isLoading={syncing}>
            <RefreshCw className="h-4 w-4" />
            Sync Meta ads
          </Button>
          <Link to="/ai-ads/generate">
            <Button>
              <Sparkles className="h-4 w-4" />
              Generate creatives
            </Button>
          </Link>
        </div>
      </div>
      {error && (
        <p className="text-sm text-red-600 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
          {error}
        </p>
      )}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Generated this week"
          value={`${data?.generated_this_week.images ?? 0} images · ${data?.generated_this_week.videos ?? 0} video concepts`}
          icon={WandSparkles}
        />
        <StatCard
          label="Imported Meta creatives"
          value={String(data?.imported_meta_creatives ?? 0)}
          icon={Images}
        />
        <StatCard
          label="Analyzed creatives"
          value={String(data?.analyzed_creatives ?? 0)}
          icon={Sparkles}
        />
        <StatCard
          label="AI recommendations"
          value={String(data?.recommendations.length ?? 0)}
          icon={Lightbulb}
        />
      </div>
      {data?.active_job && ["QUEUED", "RUNNING"].includes(String(data.active_job.status)) && (
        <GenerationStudio job={data.active_job} compact />
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Top creative</CardTitle>
            <CardDescription>Highest AI Creative Evaluation in the library</CardDescription>
          </CardHeader>
          {data?.top_creative ? (
            <div className="flex gap-4">
              {data.top_creative.preview_url ? (
                <img
                  src={data.top_creative.preview_url}
                  alt=""
                  className="h-24 w-24 rounded-lg object-cover border border-border"
                />
              ) : (
                <div className="h-24 w-24 rounded-lg bg-surface-muted" />
              )}
              <div>
                <p className="font-medium text-content">{data.top_creative.headline || "Untitled"}</p>
                <p className="text-sm text-content-muted line-clamp-2">{data.top_creative.hook}</p>
                <Badge variant="brand" className="mt-2">
                  AI score {data.top_creative.ai_score ?? "—"}/100
                </Badge>
              </div>
            </div>
          ) : (
            <p className="text-sm text-content-subtle">No generated creatives yet.</p>
          )}
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Current strategy</CardTitle>
            <CardDescription>Latest strategy grounded in Meta + Shopify data</CardDescription>
          </CardHeader>
          {data?.current_strategy ? (
            <>
              <p className="text-sm text-content">{data.current_strategy.summary}</p>
              <Link to="/ai-ads/strategy" className="inline-block mt-3 text-sm font-medium text-brand-600">
                Open strategy
              </Link>
            </>
          ) : (
            <p className="text-sm text-content-subtle">Run analysis after syncing Meta ads.</p>
          )}
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>AI recommendations</CardTitle>
          <CardDescription>Observed patterns vs experiments to test — not guaranteed ROAS</CardDescription>
        </CardHeader>
        {data?.recommendations.length ? (
          <ul className="space-y-3">
            {data.recommendations.map((r) => (
              <li key={r.id} className="border-b border-border pb-3 last:border-0 last:pb-0">
                <p className="font-medium text-content">{r.title}</p>
                <p className="text-sm text-content-muted mt-1">{r.explanation}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-content-subtle">
            Sync Meta ads and run analysis to see recommendations.
          </p>
        )}
      </Card>
    </div>
  );
}

function StatCard({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon: typeof Sparkles;
}) {
  return (
    <Card>
      <div className="flex items-start justify-between">
        <p className="text-xs uppercase tracking-wide text-content-subtle">{label}</p>
        <Icon className="h-4 w-4 text-brand-600" />
      </div>
      <p className="mt-2 text-lg font-semibold text-content">{value}</p>
    </Card>
  );
}
