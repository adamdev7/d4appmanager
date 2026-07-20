import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Package, Save, Search } from "lucide-react";
import { api, type AnalyticsProduct } from "@/lib/api";
import { Card, CardDescription, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";

type Props = {
  storeId: string;
  currency: string;
};

export function ProductCostsPanel({ storeId, currency }: Props) {
  const [products, setProducts] = useState<AnalyticsProduct[]>([]);
  const [costs, setCosts] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [missingCosts, setMissingCosts] = useState(0);

  const costKey = (p: AnalyticsProduct) => `${p.shopify_product_id}:${p.shopify_variant_id}`;

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.analytics.getProducts(storeId);
      setProducts(res.products);
      setMissingCosts(res.missing_costs);
      const map: Record<string, string> = {};
      for (const p of res.products) {
        map[costKey(p)] = p.cost_per_unit > 0 ? String(p.cost_per_unit) : "";
      }
      setCosts(map);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load products");
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return products;
    return products.filter(
      (p) =>
        p.product_title.toLowerCase().includes(q) ||
        p.variant_title.toLowerCase().includes(q) ||
        p.sku.toLowerCase().includes(q)
    );
  }, [products, search]);

  const saveAll = async () => {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const items = products
        .filter((p) => {
          const val = costs[costKey(p)];
          return val !== undefined && val !== "" && parseFloat(val) >= 0;
        })
        .map((p) => ({
          shopify_product_id: p.shopify_product_id,
          shopify_variant_id: p.shopify_variant_id,
          cost_per_unit: parseFloat(costs[costKey(p)] || "0"),
          product_title: p.product_title,
          variant_title: p.variant_title,
          image_url: p.image_url,
          shopify_price: p.shopify_price,
        }));
      await api.analytics.updateProductCosts(storeId, items);
      setMessage(`Saved costs for ${items.length} product variants.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save costs");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Card padding="lg">
        <p className="text-content-muted text-sm">Loading products from Shopify…</p>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card padding="lg" className="border-brand-500/20 bg-brand-500/5">
        <div className="flex items-start gap-3">
          <Package className="h-5 w-5 text-brand-600 shrink-0 mt-0.5" />
          <div>
            <CardTitle>Product investment costs</CardTitle>
            <CardDescription className="mt-1">
              Enter what each product costs you (COGS). This powers accurate profit, margin, and
              break-even ROAS calculations on your dashboard.
            </CardDescription>
          </div>
        </div>
      </Card>

      {missingCosts > 0 && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-sm text-amber-700 dark:text-amber-400">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {missingCosts} variant{missingCosts !== 1 ? "s" : ""} still missing a cost — profit
          numbers may be understated.
        </div>
      )}

      <div className="flex flex-col sm:flex-row gap-3 sm:items-center sm:justify-between">
        <div className="relative max-w-sm w-full">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-content-muted" />
          <Input
            className="pl-9"
            placeholder="Search products…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Button onClick={saveAll} disabled={saving}>
          <Save className="h-4 w-4 mr-1.5" />
          {saving ? "Saving…" : "Save all costs"}
        </Button>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {message && <p className="text-sm text-emerald-600 dark:text-emerald-400">{message}</p>}

      <Card padding="none" className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-surface-muted/50 text-left text-content-muted">
                <th className="px-4 py-3 font-medium">Product</th>
                <th className="px-4 py-3 font-medium text-right">Sell price</th>
                <th className="px-4 py-3 font-medium text-right w-36">Your cost</th>
                <th className="px-4 py-3 font-medium text-right">Margin</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((p) => {
                const key = costKey(p);
                const price = parseFloat(p.shopify_price) || 0;
                const cost = parseFloat(costs[key] || "0") || 0;
                const margin = price > 0 ? ((price - cost) / price) * 100 : 0;
                return (
                  <tr key={key} className="border-b border-border last:border-0">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3 min-w-0">
                        {p.image_url ? (
                          <img
                            src={p.image_url}
                            alt=""
                            className="h-10 w-10 rounded-lg object-cover shrink-0 bg-surface-muted"
                          />
                        ) : (
                          <div className="h-10 w-10 rounded-lg bg-surface-muted flex items-center justify-center shrink-0">
                            <Package className="h-4 w-4 text-content-muted" />
                          </div>
                        )}
                        <div className="min-w-0">
                          <p className="font-medium text-content truncate">{p.product_title}</p>
                          <p className="text-xs text-content-muted truncate">
                            {p.variant_title !== "Default Title" ? p.variant_title : p.sku || "—"}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right text-content-muted whitespace-nowrap">
                      {currency} {price.toFixed(2)}
                    </td>
                    <td className="px-4 py-3">
                      <Input
                        type="number"
                        min="0"
                        step="0.01"
                        placeholder="0.00"
                        className="text-right"
                        value={costs[key] ?? ""}
                        onChange={(e) =>
                          setCosts((prev) => ({ ...prev, [key]: e.target.value }))
                        }
                      />
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      {cost > 0 ? (
                        <Badge variant={margin >= 50 ? "success" : margin >= 25 ? "warning" : "muted"}>
                          {margin.toFixed(0)}%
                        </Badge>
                      ) : (
                        <Badge variant="warning">Missing</Badge>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {filtered.length === 0 && (
          <p className="p-8 text-center text-content-muted text-sm">
            {products.length === 0
              ? "No products found. Make sure your Shopify store is connected."
              : "No products match your search."}
          </p>
        )}
      </Card>
    </div>
  );
}
