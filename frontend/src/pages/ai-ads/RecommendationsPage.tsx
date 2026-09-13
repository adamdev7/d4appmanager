import { useEffect, useState } from "react";
import { useStore } from "@/context/StoreContext";
import { api, type AIAdsRecommendation } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { PageLoader } from "@/components/ui/Loading";

export function RecommendationsPage() {
  const { activeStore, stores } = useStore();
  const storeId = activeStore?.id ?? stores[0]?.id ?? null;
  const [rows, setRows] = useState<AIAdsRecommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    if (!storeId) return;
    setRows(await api.aiAds.getRecommendations(storeId));
  }

  useEffect(() => {
    if (!storeId) {
      setLoading(false);
      return;
    }
    load()
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeId]);

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

  if (!storeId) return <p className="text-sm text-content-muted">Select a store first.</p>;
  if (loading) return <PageLoader label="Loading recommendations" />;

  return (
    <div className="space-y-4">
      <div className="flex justify-between gap-3 items-center">
        <p className="text-sm text-content-muted">
          Recommendations distinguish observed data from interpretation and experiments.
        </p>
        <Button onClick={() => void analyze()} isLoading={analyzing}>
          Analyze creatives
        </Button>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {rows.length === 0 ? (
        <Card>
          <p className="text-sm text-content-subtle">
            No recommendations yet. Sync Meta ads, then run analysis.
          </p>
        </Card>
      ) : (
        rows.map((r) => (
          <Card key={r.id}>
            <CardHeader>
              <div className="flex items-start justify-between gap-2">
                <CardTitle>{r.title}</CardTitle>
                <Badge variant="brand">
                  {Math.round((r.confidence || 0) * 100)}% confidence
                </Badge>
              </div>
              <CardDescription>{r.explanation}</CardDescription>
            </CardHeader>
            {r.recommended_action && (
              <p className="text-sm text-content">
                <span className="font-medium">Action: </span>
                {r.recommended_action}
              </p>
            )}
            {(r.supporting_creative_ids?.length || 0) > 0 && (
              <p className="text-xs text-content-subtle mt-2">
                Supporting creatives: {r.supporting_creative_ids?.join(", ")}
              </p>
            )}
          </Card>
        ))
      )}
    </div>
  );
}
