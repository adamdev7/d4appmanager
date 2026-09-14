import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useStore } from "@/context/StoreContext";
import { api, type AIAdsAvatar, type AIAdsJob, type AIAdsProduct } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { PageLoader } from "@/components/ui/Loading";
import { GenerationStudio } from "@/pages/ai-ads/GenerationStudio";
import { JobHistoryList, isLiveJob } from "@/pages/ai-ads/JobHistory";

const STYLES = ["UGC", "PRODUCT_DEMO", "LIFESTYLE", "PROBLEM_SOLUTION", "PROMOTIONAL"] as const;

const STYLE_HELP: Record<(typeof STYLES)[number], string> = {
  UGC: "Phone-shot real life — not a catalog retouch",
  PRODUCT_DEMO: "Show how the exact product works on a body",
  LIFESTYLE: "A new world around the product",
  PROBLEM_SOLUTION: "The pain, then this product as the fix",
  PROMOTIONAL: "Offer-ad energy using your real price — never a fake discount",
};

export function GeneratePage() {
  const navigate = useNavigate();
  const { activeStore, stores } = useStore();
  const storeId = activeStore?.id ?? stores[0]?.id ?? null;
  const [products, setProducts] = useState<AIAdsProduct[]>([]);
  const [avatars, setAvatars] = useState<AIAdsAvatar[]>([]);
  const [jobs, setJobs] = useState<AIAdsJob[]>([]);
  const [productId, setProductId] = useState("");
  const [imageCount, setImageCount] = useState(3);
  const [videoCount, setVideoCount] = useState(1);
  const [styles, setStyles] = useState<string[]>(["UGC", "PRODUCT_DEMO", "LIFESTYLE"]);
  const [audience, setAudience] = useState("");
  const [objective, setObjective] = useState("conversions");
  const [placement, setPlacement] = useState("feed");
  const [aspect, setAspect] = useState("4:5");
  const [avatarId, setAvatarId] = useState("");
  const [brandStyle, setBrandStyle] = useState("");
  const [liveJob, setLiveJob] = useState<AIAdsJob | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!storeId) return;
    const [prods, avs, listed] = await Promise.all([
      api.aiAds.listProducts(storeId),
      api.aiAds.listAvatars(storeId),
      api.aiAds.listGenerationJobs(storeId),
    ]);
    setProducts(prods);
    setAvatars(avs);
    setJobs(listed);
    if (!productId && prods[0]) setProductId(prods[0].id);
    const active = listed.find((j) => isLiveJob(j)) || null;
    setLiveJob(active);
  }, [storeId, productId]);

  useEffect(() => {
    if (!storeId) {
      setLoading(false);
      return;
    }
    load()
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [load, storeId]);

  const liveId = liveJob ? liveJob.job_id || liveJob.id : null;

  useEffect(() => {
    if (!storeId || !liveId) return;
    const t = window.setInterval(() => {
      api.aiAds
        .getGenerationJob(storeId, liveId)
        .then((next) => {
          setLiveJob(isLiveJob(next) ? next : null);
          if (!isLiveJob(next)) {
            void load();
          }
        })
        .catch(() => undefined);
    }, 1000);
    return () => window.clearInterval(t);
  }, [liveId, storeId, load]);

  function toggleStyle(s: string) {
    setStyles((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));
  }

  async function submit() {
    if (!storeId || !productId) return;
    setSubmitting(true);
    setError("");
    try {
      const created = await api.aiAds.createGenerationJob(storeId, {
        product_id: productId,
        image_count: imageCount,
        video_count: videoCount,
        styles,
        audience,
        objective,
        placement,
        aspect_ratio: aspect,
        brand_style: brandStyle,
        avatar_id: avatarId || undefined,
      });
      setLiveJob(created);
      navigate(`/ai-ads/progress/${created.job_id || created.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start generation");
    } finally {
      setSubmitting(false);
    }
  }

  if (!storeId) return <p className="text-sm text-content-muted">Select a store first.</p>;
  if (loading) return <PageLoader label="Loading products" />;

  const selectedProduct = products.find((p) => p.id === productId);
  const recent = jobs.filter((j) => !isLiveJob(j)).slice(0, 6);

  return (
    <div className="space-y-6">
      {liveJob && isLiveJob(liveJob) && <GenerationStudio job={liveJob} compact />}
      <Card>
        <CardHeader>
          <CardTitle>Generate creatives</CardTitle>
          <CardDescription>
            Pick a Shopify product. Astra studies how it actually looks, then invents new scenes
            that make people buy — not a lightly edited website or Meta photo. The styles you tap
            are required.
          </CardDescription>
        </CardHeader>
        {error && <p className="text-sm text-red-600 mb-3">{error}</p>}
        <div className="space-y-4">
          <label className="block text-sm font-medium text-content">
            Product
            <select
              value={productId}
              onChange={(e) => setProductId(e.target.value)}
              className="mt-1.5 flex h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm"
            >
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          </label>
          {selectedProduct?.image && (
            <div className="flex items-center gap-3 rounded-lg border border-border bg-surface-muted/40 p-2">
              <img
                src={selectedProduct.image}
                alt=""
                className="h-16 w-16 rounded-md object-cover border border-border"
              />
              <div className="min-w-0">
                <p className="text-sm font-medium text-content truncate">{selectedProduct.title}</p>
                <p className="text-xs text-content-muted">
                  Astra uses this Shopify photo as the product. Pick another item above if this is
                  wrong.
                </p>
              </div>
            </div>
          )}
          {!products.length && (
            <p className="text-sm text-content-subtle">No Shopify products found for this store.</p>
          )}
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              label="Images (max 8)"
              type="number"
              min={0}
              max={8}
              value={imageCount}
              onChange={(e) => setImageCount(Math.min(8, Math.max(0, Number(e.target.value))))}
            />
            <Input
              label="Video concepts (max 4)"
              type="number"
              min={0}
              max={4}
              value={videoCount}
              onChange={(e) => setVideoCount(Math.min(4, Math.max(0, Number(e.target.value))))}
            />
          </div>
          <div>
            <p className="text-sm font-medium text-content mb-2">Creative styles</p>
            <div className="flex flex-wrap gap-2">
              {STYLES.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => toggleStyle(s)}
                  className={`rounded-full border px-3 py-1 text-xs font-medium ${
                    styles.includes(s)
                      ? "border-brand-500 bg-brand-500/10 text-brand-700"
                      : "border-border text-content-muted"
                  }`}
                >
                  {s.replace("_", " ")}
                </button>
              ))}
            </div>
            {styles.length > 0 && (
              <ul className="mt-2 space-y-1">
                {styles.map((s) => (
                  <li key={s} className="text-xs text-content-muted">
                    <span className="font-medium text-content">{s.replace("_", " ")}</span>
                    {" — "}
                    {STYLE_HELP[s as (typeof STYLES)[number]]}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <Input label="Target audience" value={audience} onChange={(e) => setAudience(e.target.value)} />
          <div className="grid gap-3 sm:grid-cols-3">
            <Input label="Objective" value={objective} onChange={(e) => setObjective(e.target.value)} />
            <label className="block text-sm font-medium text-content">
              Placement
              <select
                value={placement}
                onChange={(e) => setPlacement(e.target.value)}
                className="mt-1.5 flex h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm"
              >
                <option value="feed">Feed</option>
                <option value="stories">Stories</option>
                <option value="reels">Reels</option>
              </select>
            </label>
            <label className="block text-sm font-medium text-content">
              Aspect ratio
              <select
                value={aspect}
                onChange={(e) => setAspect(e.target.value)}
                className="mt-1.5 flex h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm"
              >
                <option value="1:1">1:1</option>
                <option value="4:5">4:5</option>
                <option value="9:16">9:16</option>
                <option value="16:9">16:9</option>
              </select>
            </label>
          </div>
          <Input
            label="Brand style (optional)"
            value={brandStyle}
            onChange={(e) => setBrandStyle(e.target.value)}
          />
          {avatars.length > 0 && (
            <label className="block text-sm font-medium text-content">
              Optional avatar
              <select
                value={avatarId}
                onChange={(e) => setAvatarId(e.target.value)}
                className="mt-1.5 flex h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm"
              >
                <option value="">None</option>
                {avatars.filter((a) => a.active).map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <Button
            onClick={() => void submit()}
            isLoading={submitting}
            disabled={!productId || !!liveJob || styles.length === 0}
          >
            Generate creatives
          </Button>
        </div>
      </Card>
      {recent.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-end justify-between gap-3">
            <h3 className="text-sm font-semibold text-content">Recent jobs</h3>
            <Link to="/ai-ads/progress" className="text-sm font-medium text-brand-600">
              View all
            </Link>
          </div>
          <JobHistoryList jobs={recent} products={products} />
        </div>
      )}
    </div>
  );
}
