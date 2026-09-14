import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ImagePlus,
  Search,
  Sliders,
  Sparkles,
  Video,
  X,
} from "lucide-react";
import { useStore } from "@/context/StoreContext";
import { api, type AIAdsAvatar, type AIAdsJob, type AIAdsProduct } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { PageLoader } from "@/components/ui/Loading";
import { GenerationStudio } from "@/pages/ai-ads/GenerationStudio";
import { JobHistoryList, isLiveJob } from "@/pages/ai-ads/JobHistory";
import { cn } from "@/lib/cn";

const STYLES = [
  { id: "UGC", label: "UGC", help: "Phone-shot real life — not a catalog retouch" },
  { id: "PRODUCT_DEMO", label: "Product demo", help: "Show how the exact product works on a body" },
  { id: "LIFESTYLE", label: "Lifestyle", help: "Build a world around the product" },
  { id: "PROBLEM_SOLUTION", label: "Problem / solution", help: "The pain first, then this product as the fix" },
  { id: "PROMOTIONAL", label: "Promotional", help: "Offer energy on your real price — never a fake discount" },
  { id: "UNBOXING", label: "Unboxing", help: "First-touch reveal from tissue or a box" },
  { id: "MACRO", label: "Macro", help: "Extreme close-up of materials and hardware" },
  { id: "FLAT_LAY", label: "Flat lay", help: "Editorial overhead — product fully readable" },
  { id: "STREET_STYLE", label: "Street style", help: "Candid outdoor fashion, product worn" },
] as const;

const MAX_IMAGES = 4;
const MAX_VIDEOS = 4;

export function GeneratePage() {
  const navigate = useNavigate();
  const { activeStore, stores } = useStore();
  const storeId = activeStore?.id ?? stores[0]?.id ?? null;
  const [products, setProducts] = useState<AIAdsProduct[]>([]);
  const [avatars, setAvatars] = useState<AIAdsAvatar[]>([]);
  const [jobs, setJobs] = useState<AIAdsJob[]>([]);
  const [productId, setProductId] = useState("");
  const [query, setQuery] = useState("");
  const [imageCount, setImageCount] = useState(2);
  const [videoCount, setVideoCount] = useState(1);
  const [styles, setStyles] = useState<string[]>(["UGC", "PRODUCT_DEMO", "LIFESTYLE"]);
  const [audience, setAudience] = useState("");
  const [objective, setObjective] = useState("conversions");
  const [placement, setPlacement] = useState("feed");
  const [aspect, setAspect] = useState("4:5");
  const [avatarId, setAvatarId] = useState("");
  const [brandStyle, setBrandStyle] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [liveJob, setLiveJob] = useState<AIAdsJob | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

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
    // Keep the operator's pick across refreshes; only fall back to the first SKU.
    setProductId((current) =>
      current && prods.some((p) => p.id === current) ? current : prods[0]?.id ?? ""
    );
    setLiveJob(listed.find((j) => isLiveJob(j)) || null);
  }, [storeId]);

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
          if (!isLiveJob(next)) void load();
        })
        .catch(() => undefined);
    }, 1000);
    return () => window.clearInterval(t);
  }, [liveId, storeId, load]);

  function toggleStyle(id: string) {
    setStyles((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  function mergeProduct(card: AIAdsProduct) {
    setProducts((prev) => {
      const idx = prev.findIndex((p) => p.id === card.id);
      if (idx < 0) return [...prev, card];
      const next = [...prev];
      next[idx] = { ...next[idx], ...card };
      return next;
    });
  }

  async function onPickPhotos(files: FileList | null) {
    if (!storeId || !productId || !files?.length) return;
    setUploading(true);
    setError("");
    try {
      mergeProduct(await api.aiAds.uploadProductPhotos(storeId, productId, Array.from(files)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save pictures");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function onClearPhotos() {
    if (!storeId || !productId) return;
    setUploading(true);
    setError("");
    try {
      mergeProduct(await api.aiAds.clearProductPhotos(storeId, productId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not remove pictures");
    } finally {
      setUploading(false);
    }
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

  const selectedProduct = products.find((p) => p.id === productId);
  const savedPhotos = useMemo(() => {
    if (!selectedProduct) return [] as string[];
    if (selectedProduct.photos?.length) return selectedProduct.photos;
    return selectedProduct.photos_cached && selectedProduct.image ? [selectedProduct.image] : [];
  }, [selectedProduct]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return products;
    return products.filter((p) => p.title.toLowerCase().includes(q));
  }, [products, query]);

  if (!storeId) return <p className="text-sm text-content-muted">Select a store first.</p>;
  if (loading) return <PageLoader label="Loading products" />;

  const photosLocked = Boolean(selectedProduct?.photos_cached);
  const recent = jobs.filter((j) => !isLiveJob(j)).slice(0, 6);
  const hasMedia = imageCount + videoCount >= 1;
  const blocked = !productId || !photosLocked || styles.length === 0 || !hasMedia || Boolean(liveJob);
  const mixLabel = [
    imageCount ? `${imageCount} still${imageCount === 1 ? "" : "s"}` : null,
    videoCount ? `${videoCount} video${videoCount === 1 ? "" : "s"}` : null,
  ]
    .filter(Boolean)
    .join(" + ") || "Nothing selected";

  return (
    <div className="space-y-6">
      {liveJob && isLiveJob(liveJob) && <GenerationStudio job={liveJob} compact />}

      {error && (
        <p className="flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-600">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </p>
      )}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_20rem] xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-4">
          <Step
            n={1}
            done={Boolean(selectedProduct)}
            title="Pick the product"
            description="Every still and clip is rendered from this SKU's real photos, so the product on screen is the one you ship."
          >
            {products.length === 0 ? (
              <p className="text-sm text-content-subtle">
                No Shopify products found for this store. Sync the store from Settings → Stores.
              </p>
            ) : (
              <div className="space-y-2.5">
                {products.length > 6 && (
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-content-subtle" />
                    <input
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder={`Search ${products.length} products`}
                      className="h-10 w-full rounded-lg border border-border bg-surface pl-9 pr-9 text-sm text-content placeholder:text-content-subtle focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30"
                    />
                    {query && (
                      <button
                        type="button"
                        onClick={() => setQuery("")}
                        aria-label="Clear search"
                        className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-1 text-content-subtle hover:text-content"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                )}
                <ul className="max-h-[19rem] divide-y divide-border overflow-y-auto rounded-lg border border-border">
                  {filtered.length === 0 && (
                    <li className="px-3 py-6 text-center text-sm text-content-subtle">
                      Nothing matches “{query}”.
                    </li>
                  )}
                  {filtered.map((p) => (
                    <li key={p.id}>
                      <button
                        type="button"
                        onClick={() => setProductId(p.id)}
                        aria-pressed={p.id === productId}
                        className={cn(
                          "flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors",
                          p.id === productId
                            ? "bg-brand-500/10"
                            : "hover:bg-surface-muted/70"
                        )}
                      >
                        <Thumb src={p.image} />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium text-content">
                            {p.title}
                          </span>
                          <span className="block text-xs text-content-subtle">
                            {p.price != null
                              ? `${p.price} ${p.currency || ""}`.trim()
                              : "No price on file"}
                          </span>
                        </span>
                        {p.photos_cached ? (
                          <Badge variant="success">
                            {p.photos_ready ? `${p.photos_ready} photos` : "Photos ready"}
                          </Badge>
                        ) : (
                          <Badge variant="warning">Needs photos</Badge>
                        )}
                        {p.id === productId && (
                          <Check className="h-4 w-4 shrink-0 text-brand-600 dark:text-brand-400" />
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Step>

          <Step
            n={2}
            done={photosLocked}
            title="Lock the product photos"
            description={
              photosLocked
                ? "These are stored in App Manager. Generation reuses them, so no Shopify download is needed."
                : "Shopify photos never saved for this SKU. Add them once — PNG, JPEG, WebP, or HEIC. We convert and compress here."
            }
          >
            {!selectedProduct ? (
              <p className="text-sm text-content-subtle">Pick a product above first.</p>
            ) : (
              <div className="space-y-3">
                {savedPhotos.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {savedPhotos.map((src) => (
                      <img
                        key={src}
                        src={src}
                        alt=""
                        className="h-20 w-20 rounded-lg border border-border bg-surface object-cover"
                      />
                    ))}
                  </div>
                ) : (
                  <button
                    type="button"
                    disabled={uploading}
                    onClick={() => fileRef.current?.click()}
                    className="flex w-full flex-col items-center gap-1.5 rounded-lg border border-dashed border-border bg-surface-muted/40 px-4 py-7 text-center transition-colors hover:border-brand-500/50 hover:bg-brand-500/5"
                  >
                    <ImagePlus className="h-5 w-5 text-content-subtle" />
                    <span className="text-sm font-medium text-content">Add product pictures</span>
                    <span className="text-xs text-content-subtle">
                      2–4 clear shots of the product work best
                    </span>
                  </button>
                )}
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp,image/heic,image/heif,.jpg,.jpeg,.png,.webp,.heic,.heif"
                  multiple
                  className="hidden"
                  onChange={(e) => void onPickPhotos(e.target.files)}
                />
                {savedPhotos.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      isLoading={uploading}
                      disabled={uploading}
                      onClick={() => fileRef.current?.click()}
                    >
                      <ImagePlus className="h-3.5 w-3.5" />
                      Add more
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={uploading}
                      onClick={() => void onClearPhotos()}
                    >
                      Remove all
                    </Button>
                  </div>
                )}
              </div>
            )}
          </Step>

          <Step
            n={3}
            done={styles.length > 0}
            title="Choose the creative angles"
            description="Astra writes one concept per angle and keeps rotating through your picks."
          >
            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {STYLES.map((s) => {
                const on = styles.includes(s.id);
                return (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => toggleStyle(s.id)}
                    aria-pressed={on}
                    className={cn(
                      "flex items-start gap-2.5 rounded-lg border p-3 text-left transition-all duration-200",
                      on
                        ? "border-brand-500/50 bg-brand-500/10 shadow-sm"
                        : "border-border hover:border-border-strong hover:bg-surface-muted/60"
                    )}
                  >
                    <span
                      className={cn(
                        "mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded border transition-colors",
                        on ? "border-brand-600 bg-brand-600 text-white" : "border-border-strong"
                      )}
                    >
                      {on && <Check className="h-3 w-3" />}
                    </span>
                    <span className="min-w-0">
                      <span className="block text-sm font-medium text-content">{s.label}</span>
                      <span className="mt-0.5 block text-xs leading-snug text-content-muted">
                        {s.help}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
            {styles.length === 0 && (
              <p className="mt-2.5 text-xs text-amber-600 dark:text-amber-400">
                Pick at least one angle.
              </p>
            )}

            <div className="mt-5 space-y-4 border-t border-border pt-4">
              <CountRow
                label="Still images"
                hint="Feed-ready stills. Clean plates — you add copy later."
                value={imageCount}
                max={MAX_IMAGES}
                onChange={setImageCount}
              />
              <CountRow
                label="Vertical videos"
                hint="9:16 MP4s. No burned-in text or voice."
                value={videoCount}
                max={MAX_VIDEOS}
                onChange={setVideoCount}
              />
              {imageCount + videoCount < 1 && (
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  Set images or videos to at least 1.
                </p>
              )}
            </div>
          </Step>

          <Step
            n={4}
            done={Boolean(audience.trim())}
            optional
            title="Aim the brief"
            description="Optional, but a specific audience sharpens the hooks a lot."
          >
            <Input
              label="Target audience"
              placeholder="e.g. women 30–45 with lower back pain from desk work"
              value={audience}
              onChange={(e) => setAudience(e.target.value)}
            />
            <button
              type="button"
              onClick={() => setShowAdvanced((v) => !v)}
              className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-content-muted transition-colors hover:text-content"
            >
              <Sliders className="h-3.5 w-3.5" />
              Advanced options
              <ChevronDown className={cn("h-4 w-4 transition-transform", showAdvanced && "rotate-180")} />
            </button>
            {showAdvanced && (
              <div className="mt-4 grid gap-3 border-t border-border pt-4 sm:grid-cols-2">
                <Select
                  label="Objective"
                  value={objective}
                  onChange={(e) => setObjective(e.target.value)}
                >
                  <option value="conversions">Conversions</option>
                  <option value="traffic">Traffic</option>
                  <option value="awareness">Awareness</option>
                  <option value="engagement">Engagement</option>
                </Select>
                <Select
                  label="Placement"
                  value={placement}
                  onChange={(e) => {
                    const next = e.target.value;
                    setPlacement(next);
                    setAspect(next === "feed" ? "4:5" : "9:16");
                  }}
                >
                  <option value="feed">Feed</option>
                  <option value="reels">Reels</option>
                  <option value="stories">Stories</option>
                </Select>
                <Select
                  label="Image aspect"
                  value={aspect}
                  onChange={(e) => setAspect(e.target.value)}
                  hint="Videos always render 9:16"
                >
                  <option value="4:5">4:5 feed</option>
                  <option value="1:1">1:1 square</option>
                  <option value="9:16">9:16 stories</option>
                </Select>
                <Input
                  label="Brand style"
                  placeholder="e.g. warm morning light, matte tones"
                  value={brandStyle}
                  onChange={(e) => setBrandStyle(e.target.value)}
                />
                {avatars.length > 0 && (
                  <Select
                    label="Brand avatar"
                    value={avatarId}
                    onChange={(e) => setAvatarId(e.target.value)}
                    hint="Used for UGC-style concepts only"
                  >
                    <option value="">None</option>
                    {avatars
                      .filter((a) => a.active)
                      .map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.name}
                        </option>
                      ))}
                  </Select>
                )}
              </div>
            )}
          </Step>
        </div>

        <div className="space-y-4 lg:sticky lg:top-32">
          <Card className="border-brand-line/40 bg-[radial-gradient(circle_at_top_right,rgba(34,197,94,0.09),transparent_45%)]">
            <div className="flex items-center gap-2">
              {videoCount && !imageCount ? (
                <Video className="h-4 w-4 text-brand-600 dark:text-brand-400" />
              ) : (
                <ImagePlus className="h-4 w-4 text-brand-600 dark:text-brand-400" />
              )}
              <CardTitle className="text-base">{mixLabel}</CardTitle>
            </div>
            <CardDescription>
              {imageCount
                ? `${aspect} stills`
                : null}
              {imageCount && videoCount ? " · " : ""}
              {videoCount ? `9:16 MP4 · ${placement}` : placement}
              {" · "}
              clean plates with no burned-in text
              {videoCount ? " or voice" : ""}, so you add captions yourself.
            </CardDescription>

            <ul className="mt-4 space-y-2">
              <Requirement ok={Boolean(selectedProduct)}>
                {selectedProduct ? selectedProduct.title : "Pick a product"}
              </Requirement>
              <Requirement ok={photosLocked}>
                {photosLocked
                  ? `${savedPhotos.length || selectedProduct?.photos_ready || 1} photo${
                      (savedPhotos.length || 1) === 1 ? "" : "s"
                    } locked for identity`
                  : "Save at least one product photo"}
              </Requirement>
              <Requirement ok={styles.length > 0}>
                {styles.length
                  ? `${styles.length} angle${styles.length === 1 ? "" : "s"} selected`
                  : "Choose a creative angle"}
              </Requirement>
              <Requirement ok={hasMedia}>
                {hasMedia ? mixLabel : "Set images or videos above 0"}
              </Requirement>
            </ul>

            <Button
              className="mt-5 w-full"
              size="lg"
              onClick={() => void submit()}
              isLoading={submitting}
              disabled={blocked}
            >
              <Sparkles className="h-4 w-4" />
              Generate {mixLabel.toLowerCase()}
            </Button>

            <p className="mt-3 text-xs text-content-subtle">
              {liveJob
                ? "A run is already in progress. Wait for it to finish or halt it from Jobs."
                : "Rendering takes a few minutes per file. You can leave this page — progress is saved under Jobs."}
            </p>
          </Card>

          {!photosLocked && selectedProduct && (
            <Card padding="sm" className="border-amber-500/30 bg-amber-500/5">
              <p className="flex items-start gap-2 text-sm text-amber-700 dark:text-amber-400">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>
                  Astra needs stored photos to keep the real product on screen. Add pictures in
                  step 2 to unlock generation.
                </span>
              </p>
            </Card>
          )}
        </div>
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
    </div>
  );
}

function CountRow({
  label,
  hint,
  value,
  max,
  onChange,
}: {
  label: string;
  hint: string;
  value: number;
  max: number;
  onChange: (n: number) => void;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <p className="text-sm font-medium text-content">{label}</p>
        <p className="text-xs text-content-subtle">{hint}</p>
      </div>
      <div className="inline-flex rounded-lg border border-border bg-surface-muted p-1">
        {Array.from({ length: max + 1 }, (_, n) => n).map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => onChange(n)}
            aria-pressed={value === n}
            className={cn(
              "h-8 w-9 rounded-md text-sm font-semibold transition-all duration-150",
              value === n
                ? "bg-surface text-content shadow-sm ring-1 ring-inset ring-brand-500/25"
                : "text-content-muted hover:text-content"
            )}
          >
            {n}
          </button>
        ))}
      </div>
    </div>
  );
}

function Step({
  n,
  title,
  description,
  done,
  optional,
  children,
}: {
  n: number;
  title: string;
  description?: string;
  done: boolean;
  optional?: boolean;
  children: ReactNode;
}) {
  return (
    <Card>
      <div className="flex items-start gap-3.5">
        <span
          className={cn(
            "mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full border text-xs font-semibold transition-colors",
            done
              ? "border-brand-500/40 bg-brand-500/15 text-brand-700 dark:text-brand-400"
              : "border-border bg-surface-muted text-content-muted"
          )}
        >
          {done ? <Check className="h-3.5 w-3.5" /> : n}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-content">{title}</h3>
            {optional && <Badge variant="muted">Optional</Badge>}
          </div>
          {description && (
            <p className="mt-1 text-sm leading-snug text-content-muted">{description}</p>
          )}
          <div className="mt-4">{children}</div>
        </div>
      </div>
    </Card>
  );
}

function Requirement({ ok, children }: { ok: boolean; children: ReactNode }) {
  return (
    <li className="flex items-start gap-2 text-sm">
      <span
        className={cn(
          "mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full",
          ok ? "bg-brand-500/20 text-brand-700 dark:text-brand-400" : "bg-surface-muted"
        )}
      >
        {ok ? <Check className="h-2.5 w-2.5" /> : <span className="h-1 w-1 rounded-full bg-content-subtle" />}
      </span>
      <span className={cn("min-w-0 truncate", ok ? "text-content" : "text-content-muted")}>
        {children}
      </span>
    </li>
  );
}

function Thumb({ src }: { src: string | null }) {
  if (!src) {
    return (
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-md border border-border bg-surface-muted">
        <ImagePlus className="h-4 w-4 text-content-subtle" />
      </span>
    );
  }
  return (
    <img
      src={src}
      alt=""
      className="h-10 w-10 shrink-0 rounded-md border border-border bg-surface object-cover"
    />
  );
}
