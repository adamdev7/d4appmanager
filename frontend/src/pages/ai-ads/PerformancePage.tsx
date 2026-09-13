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
      {error && <p className="text-sm text-red-600 mb-3">{error}</p>}
      {rows.length === 0 ? (
        <p className="text-sm text-content-subtle">No snapshots yet. Sync Meta ads first.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-content-subtle border-b border-border">
                <th className="py-2 pr-3">Ad</th>
                <th className="py-2 pr-3">Spend</th>
                <th className="py-2 pr-3">CTR</th>
                <th className="py-2 pr-3">ROAS</th>
                <th className="py-2 pr-3">CPA</th>
                <th className="py-2 pr-3">Purchases</th>
                <th className="py-2">Range</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-b border-border/60">
                  <td className="py-2 pr-3 font-mono text-xs">{r.ad_id || "—"}</td>
                  <td className="py-2 pr-3">{n(r.spend)}</td>
                  <td className="py-2 pr-3">{r.ctr == null ? "—" : `${r.ctr.toFixed(2)}%`}</td>
                  <td className="py-2 pr-3">{n(r.roas)}</td>
                  <td className="py-2 pr-3">{n(r.cpa)}</td>
                  <td className="py-2 pr-3">{n(r.purchases)}</td>
                  <td className="py-2 text-content-muted text-xs">
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
