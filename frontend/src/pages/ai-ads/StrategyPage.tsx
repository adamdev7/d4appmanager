import { useCallback, useEffect, useState } from "react";
import { useStore } from "@/context/StoreContext";
import { api, type AIAdsProduct, type AIAdsStrategy } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { PageLoader } from "@/components/ui/Loading";

export function StrategyPage() {
  const { activeStore, stores } = useStore();
  const storeId = activeStore?.id ?? stores[0]?.id ?? null;
  const [strategy, setStrategy] = useState<AIAdsStrategy | null>(null);
  const [products, setProducts] = useState<AIAdsProduct[]>([]);
  const [productId, setProductId] = useState("");
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!storeId) return;
    const [s, p] = await Promise.all([
      api.aiAds.getStrategy(storeId),
      api.aiAds.listProducts(storeId),
    ]);
    setStrategy(s);
    setProducts(p);
    if (!productId && p[0]) setProductId(p[0].id);
  }, [storeId, productId]);

  useEffect(() => {
    if (!storeId) {
      setLoading(false);
      return;
    }
    load()
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load strategy"))
      .finally(() => setLoading(false));
  }, [load, storeId]);

  async function create() {
    if (!storeId || !productId) return;
    setRunning(true);
    setError("");
    try {
      setStrategy(await api.aiAds.createStrategy(storeId, { product_id: productId }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Strategy failed");
    } finally {
      setRunning(false);
    }
  }

  if (!storeId) return <p className="text-sm text-content-muted">Select a store first.</p>;
  if (loading) return <PageLoader label="Loading strategy" />;

  const body = strategy?.strategy || {};
  const report = strategy?.intelligence_report || {};

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Creative strategy</CardTitle>
          <CardDescription>
            Built from Shopify product data plus Meta creative intelligence. Not a performance
            guarantee.
          </CardDescription>
        </CardHeader>
        <div className="flex flex-wrap gap-3 items-end">
          <label className="text-sm font-medium text-content">
            Product
            <select
              value={productId}
              onChange={(e) => setProductId(e.target.value)}
              className="mt-1.5 flex h-10 min-w-[220px] rounded-lg border border-border bg-surface px-3 text-sm"
            >
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          </label>
          <Button onClick={() => void create()} isLoading={running} disabled={!productId}>
            Generate strategy
          </Button>
        </div>
        {error && <p className="text-sm text-red-600 mt-3">{error}</p>}
      </Card>
      {!strategy && (
        <Card>
          <p className="text-sm text-content-subtle">
            No strategy yet. Sync Meta ads, then generate a strategy for a product.
          </p>
        </Card>
      )}
      {strategy && (
        <>
          <Card>
            <CardTitle>Summary</CardTitle>
            <p className="mt-2 text-sm text-content">{strategy.summary}</p>
            <p className="mt-2 text-xs text-content-subtle">
              Confidence {Math.round((strategy.confidence || 0) * 100)}%
            </p>
          </Card>
          <ListCard title="Winning patterns (observed)" items={asList(body.winning_patterns)} />
          <ListCard title="Creative angles" items={asList(body.creative_angles)} />
          <ListCard title="Hook directions" items={asList(body.hook_directions)} />
          <ListCard title="Visual directions" items={asList(body.visual_directions)} />
          <ListCard title="Avoid" items={asList(body.avoid)} />
          <ListCard title="Hypotheses to test" items={asList(body.hypotheses)} />
          <Card>
            <CardTitle>Intelligence snapshot</CardTitle>
            <p className="text-sm text-content-muted mt-2">
              Winners {asList(report.winning_creatives).length} · Average{" "}
              {asList(report.average_creatives).length} · Underperformers{" "}
              {asList(report.losing_creatives).length}
            </p>
          </Card>
        </>
      )}
    </div>
  );
}

function asList(v: unknown): string[] {
  return Array.isArray(v) ? v.map((x) => (typeof x === "string" ? x : JSON.stringify(x))) : [];
}

function ListCard({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <Card>
      <CardTitle>{title}</CardTitle>
      <ul className="mt-2 list-disc pl-5 space-y-1 text-sm text-content">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </Card>
  );
}
