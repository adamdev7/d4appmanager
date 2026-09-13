import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useStore } from "@/context/StoreContext";
import { api, type AIAdsJob } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardTitle } from "@/components/ui/Card";
import { PageLoader } from "@/components/ui/Loading";
import { GenerationControlPanel } from "@/pages/ai-ads/GenerationControlPanel";
import { GenerationStudio } from "@/pages/ai-ads/GenerationStudio";

function isLive(job: AIAdsJob | null) {
  return !!job && ["QUEUED", "RUNNING"].includes(String(job.status));
}

export function GenerationProgressPage() {
  const { jobId } = useParams();
  const { activeStore, stores } = useStore();
  const storeId = activeStore?.id ?? stores[0]?.id ?? null;
  const [job, setJob] = useState<AIAdsJob | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!storeId) return;
    if (jobId) {
      setJob(await api.aiAds.getGenerationJob(storeId, jobId));
      return;
    }
    const jobs = await api.aiAds.listGenerationJobs(storeId);
    const active = jobs.find((j) => isLive(j));
    setJob(active || jobs[0] || null);
  }, [storeId, jobId]);

  useEffect(() => {
    if (!storeId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    load()
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load progress"))
      .finally(() => setLoading(false));
  }, [load, storeId]);

  const liveId =
    job && (["QUEUED", "RUNNING"].includes(String(job.status)) || job.worker_alive)
      ? job.job_id || job.id
      : null;

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

  if (!storeId) return <p className="text-sm text-content-muted">Select a store first.</p>;
  if (loading && !job) return <PageLoader label="Opening generation studio" />;

  if (error) {
    return (
      <Card>
        <CardTitle>Could not load progress</CardTitle>
        <CardDescription className="mt-2">{error}</CardDescription>
        <Link to="/ai-ads/generate" className="inline-block mt-4">
          <Button>Back to Generate</Button>
        </Link>
      </Card>
    );
  }

  if (!job) {
    return (
      <Card>
        <CardTitle>No generation in progress</CardTitle>
        <CardDescription className="mt-2">
          Start a job from Generate to watch the AI load your product, learn from Meta ads, write
          scenes, and render images or video stills.
        </CardDescription>
        <Link to="/ai-ads/generate" className="inline-block mt-4">
          <Button>Generate creatives</Button>
        </Link>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <GenerationControlPanel storeId={storeId} job={job} onChanged={setJob} />
      <GenerationStudio job={job} />
    </div>
  );
}
