import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Sparkles } from "lucide-react";
import { useStore } from "@/context/StoreContext";
import { api, type AIAdsJob, type AIAdsProduct } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardTitle } from "@/components/ui/Card";
import { PageLoader } from "@/components/ui/Loading";
import { GenerationControlPanel } from "@/pages/ai-ads/GenerationControlPanel";
import { GenerationStudio } from "@/pages/ai-ads/GenerationStudio";
import { FinishedJobDetail, JobHistoryList, isLiveJob } from "@/pages/ai-ads/JobHistory";

export function GenerationProgressPage() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const { activeStore, stores } = useStore();
  const storeId = activeStore?.id ?? stores[0]?.id ?? null;
  const [jobs, setJobs] = useState<AIAdsJob[]>([]);
  const [job, setJob] = useState<AIAdsJob | null>(null);
  const [products, setProducts] = useState<AIAdsProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [replaying, setReplaying] = useState(false);

  const load = useCallback(async () => {
    if (!storeId) return;
    const [listed, prods] = await Promise.all([
      api.aiAds.listGenerationJobs(storeId),
      api.aiAds.listProducts(storeId).catch(() => [] as AIAdsProduct[]),
    ]);
    setJobs(listed);
    setProducts(prods);
    if (jobId) {
      setJob(await api.aiAds.getGenerationJob(storeId, jobId));
      return;
    }
    setJob(null);
  }, [storeId, jobId]);

  useEffect(() => {
    if (!storeId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    load()
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load jobs"))
      .finally(() => setLoading(false));
  }, [load, storeId]);

  const live = isLiveJob(job);
  const liveId = live ? job?.job_id || job?.id : null;

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

  useEffect(() => {
    if (!storeId || !jobId || live) return;
    api.aiAds
      .getGenerationJob(storeId, jobId)
      .then(setJob)
      .catch(() => undefined);
  }, [storeId, jobId, live]);

  async function replay() {
    if (!storeId || !job) return;
    const id = job.job_id || job.id;
    if (!id) return;
    setReplaying(true);
    try {
      const next = await api.aiAds.restartGenerationJob(storeId, id);
      const nextId = next.job_id || next.id;
      if (nextId) navigate(`/ai-ads/progress/${nextId}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start another run");
    } finally {
      setReplaying(false);
    }
  }

  if (!storeId) return <p className="text-sm text-content-muted">Select a store first.</p>;
  if (loading && !jobs.length && !job) return <PageLoader label="Loading jobs" />;

  if (error && !job && !jobs.length) {
    return (
      <Card>
        <CardTitle>Could not load jobs</CardTitle>
        <CardDescription className="mt-2">{error}</CardDescription>
        <Link to="/ai-ads/generate" className="inline-block mt-4">
          <Button>Back to Generate</Button>
        </Link>
      </Card>
    );
  }

  if (jobId && !job && !loading) {
    return (
      <div className="space-y-4">
        <Link
          to="/ai-ads/progress"
          className="inline-flex items-center gap-1.5 text-sm text-content-muted hover:text-content"
        >
          <ArrowLeft className="h-4 w-4" />
          All jobs
        </Link>
        <Card>
          <CardTitle>Job not found</CardTitle>
          <CardDescription className="mt-2">
            {error || "This generation run is not in the history for this store."}
          </CardDescription>
        </Card>
        <JobHistoryList jobs={jobs} products={products} />
      </div>
    );
  }

  if (jobId && job) {
    return (
      <div className="space-y-4">
        <Link
          to="/ai-ads/progress"
          className="inline-flex items-center gap-1.5 text-sm text-content-muted hover:text-content"
        >
          <ArrowLeft className="h-4 w-4" />
          All jobs
        </Link>
        {error && <p className="text-sm text-red-600">{error}</p>}
        {live ? (
          <>
            <GenerationControlPanel storeId={storeId} job={job} onChanged={setJob} />
            <GenerationStudio job={job} />
          </>
        ) : (
          <FinishedJobDetail
            job={job}
            products={products}
            onReplay={() => void replay()}
            replaying={replaying}
          />
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-content">Runs</h2>
          <p className="mt-0.5 text-sm text-content-muted">
            Every generation run, newest first. Open one for its clips, status, and activity log.
          </p>
        </div>
        <Link to="/ai-ads/generate">
          <Button size="sm">
            <Sparkles className="h-3.5 w-3.5" />
            New run
          </Button>
        </Link>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <JobHistoryList jobs={jobs} products={products} selectedId={jobId} />
    </div>
  );
}
