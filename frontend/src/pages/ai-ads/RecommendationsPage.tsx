import { useEffect, useState } from "react";
import { Lightbulb } from "lucide-react";
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
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-content">Recommendations</h2>
          <p className="mt-0.5 max-w-2xl text-sm text-content-muted">
            Each one separates what the data shows from what Astra infers, so you can decide what to
            test. None of it is a promised return.
          </p>
        </div>
        <Button onClick={() => void analyze()} isLoading={analyzing}>
          <Lightbulb className="h-4 w-4" />
          Analyze creatives
        </Button>
      </div>
      {error && (
        <p className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-600">
          {error}
        </p>
      )}
      {rows.length === 0 ? (
        <Card className="py-12 text-center">
          <span className="mx-auto grid h-11 w-11 place-items-center rounded-xl bg-surface-muted">
            <Lightbulb className="h-5 w-5 text-content-subtle" />
          </span>
          <p className="mt-3 font-semibold text-content">Nothing to recommend yet</p>
          <p className="mx-auto mt-1 max-w-sm text-sm text-content-muted">
            Sync your Meta ads from Overview, then run the analysis to surface what your winners
            have in common.
          </p>
        </Card>
      ) : (
        rows.map((r) => (
          <Card key={r.id}>
            <CardHeader className="mb-3">
              <div className="flex items-start justify-between gap-3">
                <CardTitle>{r.title}</CardTitle>
                <Badge variant="brand" className="shrink-0">
                  {Math.round((r.confidence || 0) * 100)}% confidence
                </Badge>
              </div>
              <CardDescription className="mt-1.5 leading-relaxed">{r.explanation}</CardDescription>
            </CardHeader>
            {r.recommended_action && (
              <p className="rounded-lg border border-brand-line/30 bg-brand-500/5 px-3 py-2.5 text-sm text-content">
                <span className="font-medium">Try this: </span>
                {r.recommended_action}
              </p>
            )}
            {(r.supporting_creative_ids?.length || 0) > 0 && (
              <p className="mt-2 text-xs text-content-subtle">
                Based on {r.supporting_creative_ids?.length} creative
                {r.supporting_creative_ids?.length === 1 ? "" : "s"} in your account.
              </p>
            )}
          </Card>
        ))
      )}
    </div>
  );
}
