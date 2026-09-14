import { useCallback, useEffect, useState } from "react";
import { useStore } from "@/context/StoreContext";
import { api, type AIAdsProduct, type AIAdsStrategy } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Select } from "@/components/ui/Select";
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
    setProductId((current) =>
      current && p.some((row) => row.id === current) ? current : p[0]?.id ?? ""
    );
  }, [storeId]);

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
        <div className="flex flex-wrap items-end gap-3">
          <Select
            label="Product"
            className="min-w-[16rem]"
            value={productId}
            onChange={(e) => setProductId(e.target.value)}
          >
            {products.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
          </Select>
          <Button onClick={() => void create()} isLoading={running} disabled={!productId}>
            Build strategy
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
            <div className="flex flex-wrap items-start justify-between gap-3">
              <CardTitle>Summary</CardTitle>
              <Badge variant="brand">
                {Math.round((strategy.confidence || 0) * 100)}% confidence
              </Badge>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-content">{strategy.summary}</p>
            <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 border-t border-border pt-3 text-xs text-content-muted">
              <span>Winners {asList(report.winning_creatives).length}</span>
              <span>Average {asList(report.average_creatives).length}</span>
              <span>Underperformers {asList(report.losing_creatives).length}</span>
            </div>
          </Card>
          <div className="grid gap-4 lg:grid-cols-2">
            <ListCard title="Winning patterns (observed)" items={asList(body.winning_patterns)} />
            <ListCard title="Creative angles" items={asList(body.creative_angles)} />
            <ListCard title="Hook directions" items={asList(body.hook_directions)} />
            <ListCard title="Visual directions" items={asList(body.visual_directions)} />
            <ListCard title="Avoid" items={asList(body.avoid)} tone="warn" />
            <ListCard title="Hypotheses to test" items={asList(body.hypotheses)} />
          </div>
        </>
      )}
    </div>
  );
}

function asList(v: unknown): string[] {
  return Array.isArray(v) ? v.map((x) => (typeof x === "string" ? x : JSON.stringify(x))) : [];
}

function ListCard({
  title,
  items,
  tone,
}: {
  title: string;
  items: string[];
  tone?: "warn";
}) {
  if (!items.length) return null;
  return (
    <Card className={tone === "warn" ? "border-amber-500/25" : undefined}>
      <CardTitle className="text-sm">{title}</CardTitle>
      <ul className="mt-3 space-y-2">
        {items.map((item, i) => (
          <li key={i} className="flex gap-2.5 text-sm text-content">
            <span
              className={cn(
                "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full",
                tone === "warn" ? "bg-amber-500" : "bg-brand-500"
              )}
            />
            <span className="min-w-0 leading-snug">{item}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
