import { useEffect, useState } from "react";
import { useStore } from "@/context/StoreContext";
import { api, type AIAdsPerformance } from "@/lib/api";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { PageLoader } from "@/components/ui/Loading";

export function PerformancePage() {
  const { activeStore, stores } = useStore();
  const storeId = activeStore?.id ?? stores[0]?.id ?? null;
  const [rows, setRows] = useState<AIAdsPerformance[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!storeId) {
      setLoading(false);
      return;
    }
    api.aiAds
      .getPerformance(storeId)
      .then((d) => setRows(d.snapshots))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [storeId]);

  if (!storeId) return <p className="text-sm text-content-muted">Select a store first.</p>;
  if (loading) return <PageLoader label="Loading performance" />;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Creative performance</CardTitle>
        <CardDescription>
          Latest imported Meta snapshots. Missing metrics stay blank — nothing is invented.
        </CardDescription>
      </CardHeader>
      {error && <p className="mb-3 text-sm text-red-600">{error}</p>}
      {rows.length === 0 ? (
        <p className="text-sm text-content-subtle">No snapshots yet. Sync Meta ads first.</p>
      ) : (
        <div className="-mx-1 overflow-x-auto px-1">
          <table className="w-full min-w-[44rem] text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-content-subtle">
                <th className="py-2.5 pr-3 font-medium">Ad</th>
                <th className="py-2.5 pr-3 text-right font-medium">Spend</th>
                <th className="py-2.5 pr-3 text-right font-medium">CTR</th>
                <th className="py-2.5 pr-3 text-right font-medium">ROAS</th>
                <th className="py-2.5 pr-3 text-right font-medium">CPA</th>
                <th className="py-2.5 pr-3 text-right font-medium">Purchases</th>
                <th className="py-2.5 font-medium">Range</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr
                  key={i}
                  className="border-b border-border/60 transition-colors last:border-0 hover:bg-surface-muted/50"
                >
                  <td className="py-2.5 pr-3 font-mono text-xs text-content-muted">
                    {r.ad_id || "—"}
                  </td>
                  <td className="py-2.5 pr-3 text-right tabular-nums">{n(r.spend)}</td>
                  <td className="py-2.5 pr-3 text-right tabular-nums">
                    {r.ctr == null ? "—" : `${r.ctr.toFixed(2)}%`}
                  </td>
                  <td className="py-2.5 pr-3 text-right font-medium tabular-nums">{n(r.roas)}</td>
                  <td className="py-2.5 pr-3 text-right tabular-nums">{n(r.cpa)}</td>
                  <td className="py-2.5 pr-3 text-right tabular-nums">{n(r.purchases)}</td>
                  <td className="py-2.5 text-xs text-content-muted">
                    {r.insufficient_data
                      ? "insufficient data"
                      : `${r.date_range_start || "?"} – ${r.date_range_end || "?"}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function n(v?: number | null) {
  return v == null ? "—" : v.toFixed(2);
}
