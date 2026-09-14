import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  BrainCircuit,
  Compass,
  Film,
  Images,
  KeyRound,
  RefreshCw,
  Sparkles,
  Star,
} from "lucide-react";
import { useStore } from "@/context/StoreContext";
import { api, type AIAdsOverview, type AIAdsProduct } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { PageLoader, UpdatingBadge } from "@/components/ui/Loading";
import { GenerationStudio } from "@/pages/ai-ads/GenerationStudio";
import { JobHistoryList, isLiveJob } from "@/pages/ai-ads/JobHistory";
import { cn } from "@/lib/cn";

export function AIAdsDashboardPage() {
  const { activeStore, stores } = useStore();
  const storeId = activeStore?.id ?? stores[0]?.id ?? null;
  const [data, setData] = useState<AIAdsOverview | null>(null);
  const [products, setProducts] = useState<AIAdsProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!storeId) {
      setLoading(false);
      return;
    }
    setError("");
    try {
      const [overview, prods] = await Promise.all([
        api.aiAds.getOverview(storeId),
        api.aiAds.listProducts(storeId).catch(() => [] as AIAdsProduct[]),
      ]);
      setData(overview);
      setProducts(prods);
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

  const liveJob = data?.active_job && isLiveJob(data.active_job) ? data.active_job : null;

  useEffect(() => {
    const liveId = liveJob ? liveJob.job_id || liveJob.id : null;
    if (!storeId || !liveId) return;
    const t = window.setInterval(() => {
      api.aiAds.getOverview(storeId).then(setData).catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(t);
  }, [liveJob?.id, liveJob?.job_id, liveJob?.status, storeId]);

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

  async function analyze() {
    if (!storeId) return;
    setAnalyzing(true);
    setError("");
    try {
      await api.aiAds.analyzePerformance(storeId);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analysis failed");
    } finally {
      setAnalyzing(false);
    }
  }

  if (!storeId) {
    return (
      <Card>
        <CardTitle>Connect a Shopify store</CardTitle>
        <CardDescription className="mt-2">
          AI Ads reads Shopify products and Meta ads from the selected store.
        </CardDescription>
        <Link to="/settings/stores" className="mt-4 inline-block">
          <Button>Open stores</Button>
        </Link>
      </Card>
    );
  }

  if (loading && !data) return <PageLoader label="Loading AI Ads" />;

  const recent = (data?.recent_jobs || []).filter((j) => !isLiveJob(j)).slice(0, 5);
  const recs = (data?.recommendations || []).slice(0, 3);
  const readyProducts = products.filter((p) => p.photos_cached).length;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold text-content">Overview</h2>
          {syncing && <UpdatingBadge label="Syncing Meta" />}
          {analyzing && <UpdatingBadge label="Analyzing" />}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => void sync()} isLoading={syncing}>
            <RefreshCw className="h-4 w-4" />
            Sync Meta ads
          </Button>
          <Link to="/ai-ads/generate">
            <Button>
              <Sparkles className="h-4 w-4" />
              Generate ads
            </Button>
          </Link>
        </div>
      </div>

      {error && (
        <p className="flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-600">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </p>
      )}

      {liveJob ? (
        <GenerationStudio job={liveJob} compact />
      ) : (
        <NextStep
          data={data}
          readyProducts={readyProducts}
          totalProducts={products.length}
          onSync={() => void sync()}
          onAnalyze={() => void analyze()}
          syncing={syncing}
          analyzing={analyzing}
        />
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Generated this week"
          value={`${data?.generated_this_week.images ?? 0} · ${data?.generated_this_week.videos ?? 0}`}
          foot="Stills · videos"
          icon={Film}
        />
        <Stat
          label="Meta ads imported"
          value={String(data?.imported_meta_creatives ?? 0)}
          foot={data?.last_sync_at ? `Synced ${ago(data.last_sync_at)}` : "Never synced"}
          icon={Images}
        />
        <Stat
          label="Creatives analyzed"
          value={String(data?.analyzed_creatives ?? 0)}
          foot={data?.last_analyze_at ? `Analyzed ${ago(data.last_analyze_at)}` : "No analysis yet"}
          icon={BrainCircuit}
        />
        <Stat
          label="Products photo-ready"
          value={`${readyProducts}/${products.length}`}
          foot={
            products.length === 0
              ? "No products synced yet"
              : readyProducts === products.length
                ? "Every SKU can render"
                : "Add photos in Generate"
          }
          icon={Star}
          warn={products.length > 0 && readyProducts === 0}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="mb-3">
            <CardTitle>Top creative</CardTitle>
            <CardDescription>Highest AI score in the library</CardDescription>
          </CardHeader>
          {data?.top_creative ? (
            <div className="flex gap-4">
              {data.top_creative.preview_url ? (
                <img
                  src={data.top_creative.preview_url}
                  alt=""
                  className="h-24 w-20 shrink-0 rounded-lg border border-border object-cover"
                />
              ) : (
                <div className="grid h-24 w-20 shrink-0 place-items-center rounded-lg bg-surface-muted">
                  <Film className="h-5 w-5 text-content-subtle" />
                </div>
              )}
              <div className="min-w-0">
                <p className="truncate font-medium text-content">
                  {data.top_creative.headline || "Untitled"}
                </p>
                <p className="line-clamp-2 text-sm text-content-muted">{data.top_creative.hook}</p>
                <Badge variant="brand" className="mt-2">
                  AI score {data.top_creative.ai_score ?? "—"}/100
                </Badge>
              </div>
            </div>
          ) : (
            <EmptyLine
              text="No generated creatives yet."
              to="/ai-ads/generate"
              cta="Generate your first ads"
            />
          )}
        </Card>

        <Card>
          <CardHeader className="mb-3">
            <CardTitle>Current strategy</CardTitle>
            <CardDescription>Grounded in your Meta + Shopify data</CardDescription>
          </CardHeader>
          {data?.current_strategy ? (
            <>
              <p className="line-clamp-4 text-sm text-content">{data.current_strategy.summary}</p>
              <Link
                to="/ai-ads/strategy"
                className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-brand-600 hover:underline dark:text-brand-400"
              >
                Open strategy
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </>
          ) : (
            <EmptyLine
              text="No strategy yet. Sync Meta ads, then build one."
              to="/ai-ads/strategy"
              cta="Build strategy"
            />
          )}
        </Card>
      </div>

      {recent.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-end justify-between gap-3">
            <h3 className="text-sm font-semibold text-content">Recent runs</h3>
            <Link
              to="/ai-ads/progress"
              className="text-sm font-medium text-brand-600 hover:underline dark:text-brand-400"
            >
              View all
            </Link>
          </div>
          <JobHistoryList jobs={recent} products={products} />
        </div>
      )}

      <Card>
        <CardHeader className="mb-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle>Recommendations</CardTitle>
              <CardDescription>Patterns worth testing — not guaranteed ROAS</CardDescription>
            </div>
            {recs.length > 0 && (
              <Link
                to="/ai-ads/recommendations"
                className="shrink-0 text-sm font-medium text-brand-600 hover:underline dark:text-brand-400"
              >
                See all
              </Link>
            )}
          </div>
        </CardHeader>
        {recs.length ? (
          <ul className="space-y-3">
            {recs.map((r) => (
              <li key={r.id} className="border-b border-border pb-3 last:border-0 last:pb-0">
                <p className="font-medium text-content">{r.title}</p>
                <p className="mt-1 line-clamp-2 text-sm text-content-muted">{r.explanation}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-content-subtle">
            Sync Meta ads and run an analysis to see what your winners have in common.
          </p>
        )}
      </Card>
    </div>
  );
}

/** One clear thing to do next, chosen from the real state of the account. */
function NextStep({
  data,
  readyProducts,
  totalProducts,
  onSync,
  onAnalyze,
  syncing,
  analyzing,
}: {
  data: AIAdsOverview | null;
  readyProducts: number;
  totalProducts: number;
  onSync: () => void;
  onAnalyze: () => void;
  syncing: boolean;
  analyzing: boolean;
}) {
  const step = (() => {
    if (data && !data.openai_configured) {
      return {
        icon: KeyRound,
        title: "Add your OpenAI key",
        body: "Rendering needs an OpenAI key. It lives in AI Email Assistant settings and is never sent to the browser.",
        action: (
          <Link to="/ai-ads/settings">
            <Button>Check connections</Button>
          </Link>
        ),
      };
    }
    if (!data?.imported_meta_creatives) {
      return {
        icon: RefreshCw,
        title: "Import your Meta ads",
        body: "Astra copies your live ads and their metrics so new videos are built on what already works for you.",
        action: (
          <Button onClick={onSync} isLoading={syncing}>
            Sync Meta ads
          </Button>
        ),
      };
    }
    if (!data?.analyzed_creatives) {
      return {
        icon: BrainCircuit,
        title: "Analyze what is working",
        body: `${data.imported_meta_creatives} ads are imported. Run the analysis to separate winners from the rest.`,
        action: (
          <Button onClick={onAnalyze} isLoading={analyzing}>
            Analyze creatives
          </Button>
        ),
      };
    }
    if (!data?.current_strategy) {
      return {
        icon: Compass,
        title: "Build the creative strategy",
        body: "Turn the analysis into hooks, angles, and visual directions for one product.",
        action: (
          <Link to="/ai-ads/strategy">
            <Button>Build strategy</Button>
          </Link>
        ),
      };
    }
    if (totalProducts > 0 && readyProducts === 0) {
      return {
        icon: Images,
        title: "Store product photos once",
        body: "Astra needs saved photos to keep the real product on screen. Add them once per SKU and every future run reuses them.",
        action: (
          <Link to="/ai-ads/generate">
            <Button>Add product photos</Button>
          </Link>
        ),
      };
    }
    return {
      icon: Sparkles,
      title: "Render your next batch",
      body: "Strategy is ready and photos are stored. Pick a product and generate stills and vertical clips you can caption yourself.",
      action: (
        <Link to="/ai-ads/generate">
          <Button>Generate ads</Button>
        </Link>
      ),
    };
  })();

  const Icon = step.icon;
  return (
    <Card className="border-brand-line/40 bg-[radial-gradient(circle_at_top_right,rgba(34,197,94,0.1),transparent_48%)]">
      <div className="flex flex-wrap items-start gap-4">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-500/15 ring-1 ring-inset ring-brand-500/25">
          <Icon className="h-5 w-5 text-brand-600 dark:text-brand-400" />
        </span>
        <div className="min-w-[16rem] flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-content-subtle">
            Next step
          </p>
          <h3 className="mt-0.5 text-base font-semibold text-content">{step.title}</h3>
          <p className="mt-1 max-w-2xl text-sm text-content-muted">{step.body}</p>
        </div>
        <div className="shrink-0">{step.action}</div>
      </div>
    </Card>
  );
}

function Stat({
  label,
  value,
  foot,
  icon: Icon,
  warn,
}: {
  label: string;
  value: string;
  foot: string;
  icon: typeof Sparkles;
  warn?: boolean;
}) {
  return (
    <Card padding="sm" className="min-w-0">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wide text-content-subtle">{label}</p>
        <Icon className="h-4 w-4 shrink-0 text-brand-600 dark:text-brand-400" />
      </div>
      <p className="mt-2 text-2xl font-semibold tabular-nums tracking-tight text-content">{value}</p>
      <p
        className={cn(
          "mt-0.5 truncate text-xs",
          warn ? "text-amber-600 dark:text-amber-400" : "text-content-subtle"
        )}
      >
        {foot}
      </p>
    </Card>
  );
}

function EmptyLine({ text, to, cta }: { text: string; to: string; cta: string }) {
  return (
    <div>
      <p className="text-sm text-content-subtle">{text}</p>
      <Link
        to={to}
        className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-brand-600 hover:underline dark:text-brand-400"
      >
        {cta}
        <ArrowRight className="h-3.5 w-3.5" />
      </Link>
    </div>
  );
}

function ago(iso: string) {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "recently";
  const min = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const hours = Math.round(min / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? "yesterday" : `${days}d ago`;
}
