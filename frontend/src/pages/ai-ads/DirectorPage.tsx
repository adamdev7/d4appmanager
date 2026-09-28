import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  Bookmark,
  CalendarDays,
  ClipboardList,
  Flame,
  FlaskConical,
  History,
  Info,
  Lightbulb,
  Package,
  Pencil,
  Play,
  Settings2,
  Sparkles,
  Trophy,
  Users,
  X,
} from "lucide-react";
import { useStore } from "@/context/StoreContext";
import { api, type AIAdsProduct } from "@/lib/api";
import type {
  DirectorAlert,
  DirectorOverview,
  DirectorReport,
  DirectorSuggestion,
  DirectorSuggestionEdit,
} from "@/lib/directorTypes";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { PageLoader } from "@/components/ui/Loading";
import { DirectorSettingsCard } from "@/pages/ai-ads/DirectorSettingsCard";
import { cn } from "@/lib/cn";

const POLL_MS = 4000;

function money(value: number | null | undefined) {
  return `$${(value ?? 0).toFixed(2)}`;
}

function when(iso: string | null | undefined) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function isRunning(report: DirectorReport | null | undefined) {
  return report?.status === "QUEUED" || report?.status === "RUNNING";
}

function mediaLabel(s: Pick<DirectorSuggestion, "image_count" | "video_count">) {
  return [
    s.image_count ? `${s.image_count} still${s.image_count === 1 ? "" : "s"}` : null,
    s.video_count ? `${s.video_count} video${s.video_count === 1 ? "" : "s"}` : null,
  ]
    .filter(Boolean)
    .join(" + ");
}

export function DirectorPage() {
  const navigate = useNavigate();
  const { activeStore, stores } = useStore();
  const storeId = activeStore?.id ?? stores[0]?.id ?? null;
  const [data, setData] = useState<DirectorOverview | null>(null);
  const [products, setProducts] = useState<AIAdsProduct[]>([]);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  const load = useCallback(async () => {
    if (!storeId) return;
    try {
      setData(await api.aiAds.getDirector(storeId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the Creative Director");
    }
  }, [storeId]);

  useEffect(() => {
    void load();
    if (storeId) {
      api.aiAds
        .listProducts(storeId)
        .then(setProducts)
        .catch(() => setProducts([]));
    }
  }, [load, storeId]);

  const running = isRunning(data?.latest_run);
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [running, load]);

  async function runNow() {
    if (!storeId) return;
    setStarting(true);
    setError("");
    try {
      await api.aiAds.runDirector(storeId);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the Director");
    } finally {
      setStarting(false);
    }
  }

  function replace(updated: DirectorSuggestion) {
    setData((prev) => {
      if (!prev) return prev;
      const open = updated.status === "NEW" || updated.status === "SAVED";
      const board = open
        ? prev.board.map((s) => (s.id === updated.id ? updated : s))
        : prev.board.filter((s) => s.id !== updated.id);
      const log = open ? prev.log : [updated, ...prev.log.filter((s) => s.id !== updated.id)];
      return { ...prev, board, log };
    });
  }

  if (!storeId) return <p className="text-sm text-content-muted">Select a store first.</p>;
  if (!data && !error) return <PageLoader label="Loading the Creative Director" />;

  const report = data?.report ?? null;
  const latest = data?.latest_run ?? null;
  const reportId = report?.id;
  const board = (data?.board ?? []).filter((s) => s.status === "NEW" && s.report_id === reportId);
  const saved = (data?.board ?? []).filter((s) => s.status === "SAVED" || (s.status === "NEW" && s.report_id !== reportId));
  const byId = new Map((data?.board ?? []).map((s) => [s.id, s]));

  return (
    <div className="space-y-6">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <CardTitle className="flex items-center gap-2">
              <Lightbulb className="h-5 w-5 text-brand-600 dark:text-brand-400" />
              Creative Director
            </CardTitle>
            <CardDescription className="max-w-2xl">
              Reads your Shopify sales and stock, Meta results, the playbook, and the Quebec/Canada
              calendar, then proposes what to make this week. It suggests; you decide. Nothing is
              generated or published without your click.
            </CardDescription>
            {data && (
              <p className="mt-2 text-xs text-content-subtle">
                This week: {money(data.budget.spent_usd)} spent
                {data.budget.cap_usd > 0 ? ` of ${money(data.budget.cap_usd)} cap` : " (no cap)"}
                {data.settings.last_run_at ? ` · last run ${when(data.settings.last_run_at)}` : ""}
                {` · aggressiveness: ${data.settings.aggressiveness}`}
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" onClick={() => setShowSettings((v) => !v)}>
              <Settings2 className="h-4 w-4" />
              {showSettings ? "Hide settings" : "Director settings"}
            </Button>
            <Button
              onClick={() => void runNow()}
              isLoading={starting}
              disabled={running || !data?.settings.enabled || !data?.settings.server_enabled}
              title={
                !data?.settings.server_enabled
                  ? "Switched off on the server (AI_DIRECTOR_ENABLED)"
                  : !data?.settings.enabled
                    ? "Turn the Director on in its settings"
                    : undefined
              }
            >
              <Play className="h-4 w-4" />
              Run Director now
            </Button>
          </div>
        </div>

        {running && latest && (
          <p className="mt-4 flex items-center gap-2 rounded-lg border border-brand-500/20 bg-brand-500/5 px-3 py-2 text-sm">
            <span className="h-2 w-2 animate-pulse rounded-full bg-brand-500" />
            {latest.progress || "Starting…"}
          </p>
        )}
        {latest?.status === "FAILED" && latest.error_message && (
          <p className="mt-4 flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-600">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>Last run failed: {latest.error_message}</span>
          </p>
        )}
        {error && (
          <p className="mt-4 flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-600">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </p>
        )}
        {report?.data_gaps?.length ? (
          <ul className="mt-3 space-y-1">
            {report.data_gaps.map((gap) => (
              <li key={gap} className="flex items-start gap-2 text-xs text-content-muted">
                <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                {gap}
              </li>
            ))}
          </ul>
        ) : null}
      </Card>

      {showSettings && data && (
        <DirectorSettingsCard
          storeId={storeId}
          settings={data.settings}
          products={products}
          onSaved={(settings) => setData((prev) => (prev ? { ...prev, settings } : prev))}
        />
      )}

      {!report && !running && (
        <Card>
          <p className="text-sm text-content-muted">
            No brief yet. Click <strong>Run Director now</strong> to get this week's brief and idea
            board. It takes one to two minutes and costs about{" "}
            {money(data?.budget.rates.director_run_usd)} in OpenAI usage.
          </p>
        </Card>
      )}

      {report && report.alerts.length > 0 && <AlertsCard alerts={report.alerts} />}

      {report && <BriefCard report={report} byId={byId} />}

      {board.length > 0 && (
        <section className="space-y-3">
          <SectionTitle icon={Sparkles} title="Idea board" hint={`${board.length} concepts from ${when(report?.finished_at)}`} />
          <div className="grid gap-4 xl:grid-cols-2">
            {board.map((s) => (
              <SuggestionCard
                key={s.id}
                storeId={storeId}
                suggestion={s}
                products={products}
                adTypes={data?.ad_types ?? []}
                onChange={replace}
                onGenerated={(jobId) => navigate(`/ai-ads/progress/${jobId}`)}
              />
            ))}
          </div>
        </section>
      )}

      {saved.length > 0 && (
        <section className="space-y-3">
          <SectionTitle icon={Bookmark} title="Saved for later" hint="Kept across weeks until you generate or dismiss them" />
          <div className="grid gap-4 xl:grid-cols-2">
            {saved.map((s) => (
              <SuggestionCard
                key={s.id}
                storeId={storeId}
                suggestion={s}
                products={products}
                adTypes={data?.ad_types ?? []}
                onChange={replace}
                onGenerated={(jobId) => navigate(`/ai-ads/progress/${jobId}`)}
              />
            ))}
          </div>
        </section>
      )}

      {report && (report.audience_ideas.length > 0 || report.offer_ideas.length > 0) && (
        <IdeasCard report={report} />
      )}

      {data && data.log.length > 0 && <LogCard log={data.log} />}

      {data && data.playbook.length > 0 && <PlaybookCard entries={data.playbook} />}
    </div>
  );
}

function SectionTitle({ icon: Icon, title, hint }: { icon: typeof Sparkles; title: string; hint?: string }) {
  return (
    <div className="flex flex-wrap items-baseline gap-2">
      <h2 className="flex items-center gap-2 text-base font-semibold text-content">
        <Icon className="h-4 w-4 text-brand-600 dark:text-brand-400" />
        {title}
      </h2>
      {hint && <span className="text-xs text-content-subtle">{hint}</span>}
    </div>
  );
}

const ALERT_ICON: Record<string, typeof Flame> = {
  fatigue: Flame,
  winner: Trophy,
  stock: Package,
  occasion: CalendarDays,
};

function AlertsCard({ alerts }: { alerts: DirectorAlert[] }) {
  return (
    <Card padding="sm">
      <SectionTitle icon={AlertTriangle} title="Alerts" />
      <ul className="mt-3 grid gap-2 md:grid-cols-2">
        {alerts.map((a, i) => {
          const Icon = ALERT_ICON[a.type] ?? Info;
          return (
            <li
              key={`${a.type}-${i}`}
              className={cn(
                "flex items-start gap-2 rounded-lg border px-3 py-2 text-sm",
                a.level === "warning"
                  ? "border-amber-500/20 bg-amber-500/10"
                  : "border-border bg-surface-muted/50"
              )}
            >
              <Icon className="mt-0.5 h-4 w-4 shrink-0 text-content-muted" />
              <span className="min-w-0">
                <span className="block font-medium">{a.title}</span>
                <span className="block text-xs text-content-muted">{a.message}</span>
              </span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function BriefCard({ report, byId }: { report: DirectorReport; byId: Map<string, DirectorSuggestion> }) {
  const brief = report.brief;
  const items = brief.items ?? [];
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-content-subtle">
            Weekly creative brief · {report.week_key}
            {report.trigger === "weekly" ? " · weekly run" : ""}
          </p>
          <CardTitle className="mt-1">{brief.headline || "This week's brief"}</CardTitle>
          {brief.summary && <CardDescription className="max-w-3xl">{brief.summary}</CardDescription>}
        </div>
        <div className="text-right text-xs text-content-subtle">
          <p className="text-sm font-medium text-content">{money(brief.estimated_cost_usd)} est.</p>
          <p>
            {brief.total_images ?? 0} stills · {brief.total_videos ?? 0} videos
          </p>
        </div>
      </div>

      {items.length > 0 ? (
        <ol className="mt-4 space-y-2">
          {items.map((item, i) => {
            const s = byId.get(item.suggestion_id);
            return (
              <li key={item.suggestion_id} className="flex items-start gap-3 rounded-lg border border-border p-3 text-sm">
                <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-brand-500/10 text-xs font-semibold text-brand-700 dark:text-brand-400">
                  {i + 1}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="font-medium">{s?.concept_name ?? "Concept"}</span>
                  {s && (
                    <span className="text-content-subtle">
                      {" "}
                      · {s.ad_type_label} · {s.product_title}
                    </span>
                  )}
                  <span className="block text-xs text-content-muted">{item.reason}</span>
                  {s && s.status !== "NEW" && s.status !== "SAVED" && (
                    <span className="mt-1 block text-xs text-content-subtle">Status: {s.status.toLowerCase()}</span>
                  )}
                </span>
                <span className="shrink-0 text-xs text-content-subtle">
                  {mediaLabel(item)} · {money(item.estimated_cost_usd)}
                </span>
              </li>
            );
          })}
        </ol>
      ) : (
        <p className="mt-4 text-sm text-content-muted">
          Nothing made it into the brief (weekly cap, stock, or unconfirmed offers). Pick from the idea board below.
        </p>
      )}

      <div className="mt-4 grid gap-3 text-xs md:grid-cols-3">
        {brief.testing_plan && (
          <div className="rounded-lg bg-surface-muted/60 p-3">
            <p className="mb-1 flex items-center gap-1.5 font-medium text-content">
              <FlaskConical className="h-3.5 w-3.5" /> Testing plan
            </p>
            <p className="text-content-muted">{brief.testing_plan}</p>
          </div>
        )}
        {brief.naming_convention && (
          <div className="rounded-lg bg-surface-muted/60 p-3">
            <p className="mb-1 flex items-center gap-1.5 font-medium text-content">
              <ClipboardList className="h-3.5 w-3.5" /> Naming
            </p>
            <p className="break-words font-mono text-content-muted">{brief.naming_convention}</p>
          </div>
        )}
        {brief.budget_note && (
          <div className="rounded-lg bg-surface-muted/60 p-3">
            <p className="mb-1 font-medium text-content">Test budget</p>
            <p className="text-content-muted">{brief.budget_note}</p>
          </div>
        )}
      </div>
      <p className="mt-3 text-xs text-content-subtle">
        {report.trigger === "weekly"
          ? "The weekly run is producing this brief. Creatives land in the approval queue."
          : "With “Director drives weekly runs” on, the next weekly batch plans and produces a fresh brief like this one. Or generate any idea below now."}
      </p>
      {brief.filtered_out && brief.filtered_out.length > 0 && (
        <details className="mt-3 text-xs text-content-muted">
          <summary className="cursor-pointer">{brief.filtered_out.length} ideas blocked by guardrails or too close to past ads</summary>
          <ul className="mt-2 space-y-1">
            {brief.filtered_out.map((r, i) => (
              <li key={i}>
                {r.concept_name ? <strong>{r.concept_name}: </strong> : null}
                {r.reason}
              </li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  );
}

function SuggestionCard({
  storeId,
  suggestion: s,
  products,
  adTypes,
  onChange,
  onGenerated,
}: {
  storeId: string;
  suggestion: DirectorSuggestion;
  products: AIAdsProduct[];
  adTypes: DirectorOverview["ad_types"];
  onChange: (s: DirectorSuggestion) => void;
  onGenerated: (jobId: string) => void;
}) {
  const [mode, setMode] = useState<"view" | "edit" | "dismiss">("view");
  const [busy, setBusy] = useState<"" | "generate" | "save" | "dismiss" | "edit">("");
  const [error, setError] = useState("");
  const [reason, setReason] = useState("");
  const [draft, setDraft] = useState<DirectorSuggestionEdit>({});
  const [showDetails, setShowDetails] = useState(false);

  const blocking = s.flags.filter((f) => f.code !== "needs_photos");

  async function act<T>(kind: typeof busy, fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(kind);
    setError("");
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      return undefined;
    } finally {
      setBusy("");
    }
  }

  async function generate() {
    setBusy("generate");
    setError("");
    try {
      const result = await api.aiAds.generateSuggestion(storeId, s.id);
      onChange(result.suggestion);
      onGenerated(result.job.job_id || result.job.id);
    } catch (e) {
      const status = (e as { status?: number }).status;
      const message = e instanceof Error ? e.message : "Could not start generation";
      if (status === 409 && window.confirm(`${message}\n\nGenerate anyway?`)) {
        try {
          const result = await api.aiAds.generateSuggestion(storeId, s.id, true);
          onChange(result.suggestion);
          onGenerated(result.job.job_id || result.job.id);
        } catch (inner) {
          setError(inner instanceof Error ? inner.message : "Could not start generation");
        }
      } else {
        setError(message);
      }
    } finally {
      setBusy("");
    }
  }

  function startEdit() {
    setDraft({
      concept_name: s.concept_name,
      ad_type: s.ad_type,
      product_id: s.product_id ?? "",
      hook: s.hook,
      angle: s.angle,
      audience: s.audience,
      hypothesis: s.hypothesis,
      test_design: s.test_design,
      image_count: s.image_count,
      video_count: s.video_count,
    });
    setMode("edit");
  }

  const scoreEntries = useMemo(
    () =>
      (
        [
          ["Brand fit", s.scores.brand_fit],
          ["Novelty", s.scores.novelty],
          ["Predicted", s.scores.predicted_performance],
          ["Cost", s.scores.production_cost],
          ["Risk", s.scores.risk],
        ] as const
      ).filter(([, v]) => typeof v === "number"),
    [s.scores]
  );

  return (
    <Card padding="sm" className={cn(s.is_experiment && "border-dashed")}>
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant="brand">{s.ad_type_label}</Badge>
        {s.in_brief && <Badge variant="success">In brief</Badge>}
        {s.is_experiment && <Badge variant="warning">Wild card · small test budget</Badge>}
        {s.kind === "clone" && <Badge>Clone the winner</Badge>}
        {s.kind === "refresh" && <Badge>Refresh</Badge>}
        {s.occasion && <Badge variant="muted">{s.occasion}</Badge>}
        {s.status === "SAVED" && <Badge variant="muted">Saved</Badge>}
        <span className="ml-auto text-xs text-content-subtle">
          {mediaLabel(s)} · ~{money(s.estimated_cost_usd)}
        </span>
      </div>

      <h3 className="mt-2 text-sm font-semibold text-content">{s.concept_name}</h3>
      <p className="text-xs text-content-subtle">{s.product_title || "No product"}</p>

      {s.why && (
        <p className="mt-2 rounded-md bg-brand-500/5 px-2.5 py-1.5 text-xs">
          <span className="font-medium text-brand-700 dark:text-brand-400">Why this? </span>
          {s.why}
        </p>
      )}

      {mode === "edit" ? (
        <div className="mt-3 space-y-2">
          <Input
            label="Name"
            value={draft.concept_name ?? ""}
            onChange={(e) => setDraft({ ...draft, concept_name: e.target.value })}
          />
          <div className="grid gap-2 sm:grid-cols-2">
            <Select
              label="Ad type"
              value={draft.ad_type ?? ""}
              onChange={(e) => setDraft({ ...draft, ad_type: e.target.value })}
            >
              {adTypes.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </Select>
            <Select
              label="Product"
              value={draft.product_id ?? ""}
              onChange={(e) => setDraft({ ...draft, product_id: e.target.value })}
            >
              {!products.some((p) => p.id === draft.product_id) && (
                <option value={draft.product_id ?? ""}>{s.product_title || "Current product"}</option>
              )}
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </Select>
          </div>
          <Input label="Hook" value={draft.hook ?? ""} onChange={(e) => setDraft({ ...draft, hook: e.target.value })} />
          <Input label="Angle" value={draft.angle ?? ""} onChange={(e) => setDraft({ ...draft, angle: e.target.value })} />
          <Input
            label="Audience"
            value={draft.audience ?? ""}
            onChange={(e) => setDraft({ ...draft, audience: e.target.value })}
          />
          <Input
            label="Hypothesis (one variable)"
            value={draft.hypothesis ?? ""}
            onChange={(e) => setDraft({ ...draft, hypothesis: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-2">
            <Input
              label="Stills"
              type="number"
              min={0}
              max={4}
              value={draft.image_count ?? 0}
              onChange={(e) => setDraft({ ...draft, image_count: Number(e.target.value) })}
            />
            <Input
              label="Videos"
              type="number"
              min={0}
              max={2}
              value={draft.video_count ?? 0}
              onChange={(e) => setDraft({ ...draft, video_count: Number(e.target.value) })}
            />
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              isLoading={busy === "edit"}
              onClick={async () => {
                const updated = await act("edit", () => api.aiAds.editSuggestion(storeId, s.id, draft));
                if (updated) {
                  onChange(updated);
                  setMode("view");
                }
              }}
            >
              Save changes
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setMode("view")}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <>
          <dl className="mt-3 space-y-1.5 text-xs">
            <Row label="Hook">
              “{s.hook}”{s.hook_type ? <span className="text-content-subtle"> · {s.hook_type}</span> : null}
            </Row>
            <Row label="Angle">{s.angle}</Row>
            {(s.emotion || s.funnel) && (
              <Row label="Feel">
                {[s.emotion, s.funnel].filter(Boolean).join(" · ")}
              </Row>
            )}
            {s.audience && <Row label="Audience">{s.audience}</Row>}
            {s.hypothesis && (
              <Row label="Test">
                {s.hypothesis}
                {s.test_variable && <span className="text-content-subtle"> · variable: {s.test_variable}</span>}
              </Row>
            )}
          </dl>

          {blocking.length > 0 && (
            <ul className="mt-2 space-y-1">
              {blocking.map((f, i) => (
                <li key={i} className="flex items-start gap-1.5 text-xs text-amber-700 dark:text-amber-400">
                  <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                  {f.message}
                </li>
              ))}
            </ul>
          )}
          {s.flags.some((f) => f.code === "needs_photos") && (
            <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">
              Add product photos on <Link to="/ai-ads/generate" className="underline">Generate</Link> before this can render.
            </p>
          )}

          <button
            type="button"
            className="mt-2 text-xs font-medium text-brand-600 underline"
            onClick={() => setShowDetails((v) => !v)}
          >
            {showDetails ? "Hide details" : "Test design, script, scores"}
          </button>
          {showDetails && (
            <div className="mt-2 space-y-2 rounded-lg bg-surface-muted/60 p-3 text-xs">
              {s.test_design && <Row label="Design">{s.test_design}</Row>}
              {s.test_budget && <Row label="Budget">{s.test_budget}</Row>}
              {s.ad_name && (
                <Row label="Ad name">
                  <span className="font-mono">{s.ad_name}</span>
                </Row>
              )}
              {(s.script.first_two_seconds || s.script.lines?.length) && (
                <div>
                  <p className="font-medium text-content">
                    Script{s.script.language ? ` (${s.script.language})` : ""}
                  </p>
                  {s.script.first_two_seconds && (
                    <p className="text-content-muted">
                      <strong>0–2s:</strong> {s.script.first_two_seconds}
                    </p>
                  )}
                  {s.script.lines?.map((line, i) => (
                    <p key={i} className="text-content-muted">
                      {line}
                    </p>
                  ))}
                  {s.script.cta && (
                    <p className="text-content-muted">
                      <strong>CTA:</strong> {s.script.cta}
                    </p>
                  )}
                </div>
              )}
              {scoreEntries.length > 0 && (
                <p className="text-content-muted">
                  {scoreEntries.map(([k, v]) => `${k} ${v}/5`).join(" · ")}
                  {typeof s.scores.measured_novelty === "number" &&
                    ` · novelty vs past ads ${Math.round(s.scores.measured_novelty * 100)}%`}
                </p>
              )}
              {s.rationale && <p className="text-content-muted">Critic: {s.rationale}</p>}
            </div>
          )}
        </>
      )}

      {mode === "dismiss" && (
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <div className="min-w-[12rem] flex-1">
            <Input
              label="Why not? (optional, teaches the Director)"
              value={reason}
              placeholder="e.g. too salesy, not our look"
              onChange={(e) => setReason(e.target.value)}
            />
          </div>
          <Button
            size="sm"
            variant="danger"
            isLoading={busy === "dismiss"}
            onClick={async () => {
              const updated = await act("dismiss", () => api.aiAds.dismissSuggestion(storeId, s.id, reason));
              if (updated) onChange(updated);
            }}
          >
            Dismiss
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setMode("view")}>
            Cancel
          </Button>
        </div>
      )}

      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}

      {mode === "view" && (
        <div className="mt-3 flex flex-wrap gap-2">
          <Button size="sm" onClick={() => void generate()} isLoading={busy === "generate"} disabled={!s.product_id}>
            <Sparkles className="h-3.5 w-3.5" />
            Generate
          </Button>
          <Button size="sm" variant="outline" onClick={startEdit}>
            <Pencil className="h-3.5 w-3.5" />
            Edit
          </Button>
          {s.status !== "SAVED" && (
            <Button
              size="sm"
              variant="outline"
              isLoading={busy === "save"}
              onClick={async () => {
                const updated = await act("save", () => api.aiAds.saveSuggestion(storeId, s.id));
                if (updated) onChange(updated);
              }}
            >
              <Bookmark className="h-3.5 w-3.5" />
              Save for later
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={() => setMode("dismiss")}>
            <X className="h-3.5 w-3.5" />
            Dismiss
          </Button>
        </div>
      )}
    </Card>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[4.5rem_1fr] gap-2">
      <dt className="text-content-subtle">{label}</dt>
      <dd className="min-w-0 text-content">{children}</dd>
    </div>
  );
}

function IdeasCard({ report }: { report: DirectorReport }) {
  return (
    <Card>
      <SectionTitle icon={Users} title="Audience & offer ideas" hint="Suggestions only. Nothing is changed in Meta or Shopify." />
      <div className="mt-3 grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          {report.audience_ideas.map((a, i) => (
            <div key={i} className="rounded-lg border border-border p-3 text-sm">
              <p className="font-medium">
                {a.name} <span className="text-xs font-normal text-content-subtle">· {a.segment_type}</span>
              </p>
              {a.description && <p className="text-xs text-content-muted">{a.description}</p>}
              {a.why && <p className="mt-1 text-xs text-content-subtle">Why: {a.why}</p>}
            </div>
          ))}
        </div>
        <div className="space-y-2">
          {report.offer_ideas.map((o, i) => (
            <div key={i} className="rounded-lg border border-border p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-medium">{o.label}</p>
                {o.requires_confirmation ? (
                  <Badge variant="warning">Requires your confirmation</Badge>
                ) : (
                  <Badge variant="success">Confirmed offer</Badge>
                )}
              </div>
              {o.description && <p className="text-xs text-content-muted">{o.description}</p>}
              {o.why && <p className="mt-1 text-xs text-content-subtle">Why: {o.why}</p>}
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

function LogCard({ log }: { log: DirectorSuggestion[] }) {
  return (
    <Card>
      <SectionTitle icon={History} title="Past recommendations" hint="What you decided and how it did" />
      <ul className="mt-3 divide-y divide-border">
        {log.map((s) => (
          <li key={s.id} className="flex flex-wrap items-start gap-2 py-2.5 text-sm">
            {s.status === "GENERATED" ? <Badge variant="success">Generated</Badge> : <Badge variant="muted">Dismissed</Badge>}
            <span className="min-w-0 flex-1">
              <span className="font-medium">{s.concept_name}</span>
              <span className="text-content-subtle"> · {s.ad_type_label} · {s.product_title}</span>
              {s.status === "GENERATED" && s.outcome?.summary && (
                <span className="block text-xs text-content-muted">{s.outcome.summary}</span>
              )}
              {s.status === "DISMISSED" && (
                <span className="block text-xs text-content-muted">
                  {s.dismiss_reason ? `Reason: ${s.dismiss_reason}` : "No reason given"}
                </span>
              )}
            </span>
            <span className="text-xs text-content-subtle">{when(s.decided_at)}</span>
            {s.job_id && (
              <Link to={`/ai-ads/progress/${s.job_id}`} className="text-xs font-medium text-brand-600 underline">
                View job
              </Link>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}

const PLAYBOOK_BADGE: Record<string, "success" | "warning" | "muted" | "brand" | "default"> = {
  supported: "success",
  refuted: "warning",
  inconclusive: "muted",
  open: "brand",
  active: "default",
};

function PlaybookCard({ entries }: { entries: DirectorOverview["playbook"] }) {
  return (
    <Card>
      <SectionTitle icon={FlaskConical} title="Playbook" hint="Hypotheses under test, learnings, and your preferences" />
      <ul className="mt-3 space-y-2">
        {entries.map((e) => (
          <li key={e.id} className="rounded-lg border border-border p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="muted">{e.kind}</Badge>
              <Badge variant={PLAYBOOK_BADGE[e.status] ?? "default"}>{e.status}</Badge>
              <span className="ml-auto text-xs text-content-subtle">{when(e.updated_at)}</span>
            </div>
            <p className="mt-1.5">{e.statement}</p>
            {e.evidence.length > 0 && (
              <p className="mt-1 text-xs text-content-muted">Latest evidence: {e.evidence[e.evidence.length - 1].note}</p>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}
