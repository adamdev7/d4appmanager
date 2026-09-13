import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useStore } from "@/context/StoreContext";
import { api, type AIAdsAvatar, type AIAdsJob, type AIAdsProduct } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { PageLoader } from "@/components/ui/Loading";
import { GenerationStudio } from "@/pages/ai-ads/GenerationStudio";

const STYLES = ["UGC", "PRODUCT_DEMO", "LIFESTYLE", "PROBLEM_SOLUTION", "PROMOTIONAL"];

export function GeneratePage() {
  const navigate = useNavigate();
  const { activeStore, stores } = useStore();
  const storeId = activeStore?.id ?? stores[0]?.id ?? null;
  const [products, setProducts] = useState<AIAdsProduct[]>([]);
  const [avatars, setAvatars] = useState<AIAdsAvatar[]>([]);
  const [productId, setProductId] = useState("");
  const [imageCount, setImageCount] = useState(3);
  const [videoCount, setVideoCount] = useState(2);
  const [styles, setStyles] = useState<string[]>(["UGC", "PRODUCT_DEMO", "LIFESTYLE"]);
  const [audience, setAudience] = useState("");
  const [objective, setObjective] = useState("conversions");
  const [placement, setPlacement] = useState("feed");
  const [aspect, setAspect] = useState("4:5");
  const [avatarId, setAvatarId] = useState("");
  const [brandStyle, setBrandStyle] = useState("");
  const [job, setJob] = useState<AIAdsJob | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!storeId) return;
    const [prods, avs, jobs] = await Promise.all([
      api.aiAds.listProducts(storeId),
      api.aiAds.listAvatars(storeId),
      api.aiAds.listGenerationJobs(storeId),
    ]);
    setProducts(prods);
    setAvatars(avs);
    if (!productId && prods[0]) setProductId(prods[0].id);
    const active = jobs.find((j) => j.status === "QUEUED" || j.status === "RUNNING");
    if (active) setJob(active);
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

  const running = job && ["QUEUED", "RUNNING"].includes(String(job.status));
  const liveId = running ? job.job_id || job.id : null;

  useEffect(() => {
    if (!storeId || !liveId) return;
    const t = window.setInterval(() => {
      api.aiAds
        .getGenerationJob(storeId, liveId)
        .then(setJob)
        .catch(() => undefined);
    }, 1000);
    return () => window.clearInterval(t);
  }, [liveId, storeId]);

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
      setJob(created);
      navigate(`/ai-ads/progress/${created.job_id || created.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start generation");
    } finally {
      setSubmitting(false);
    }
  }

  if (!storeId) return <p className="text-sm text-content-muted">Select a store first.</p>;
  if (loading) return <PageLoader label="Loading products" />;

  return (
    <div className="space-y-6">
      {job && running && <GenerationStudio job={job} />}
      <Card>
        <CardHeader>
          <CardTitle>Generate creatives</CardTitle>
          <CardDescription>
            Learns from your stronger Meta ads (ROAS/CTR), then generates a small batch of complete
            image ads and video storyboards. Counts stay low to limit OpenAI usage. You will see
            every step on the live progress page.
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
          <Button onClick={() => void submit()} isLoading={submitting} disabled={!productId || !!running}>
            Generate creatives
          </Button>
        </div>
      </Card>
    </div>
  );
}
