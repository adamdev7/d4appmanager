import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  Check,
  ClipboardList,
  Copy,
  Download,
  Loader2,
  RefreshCw,
  Save,
  Sparkles,
  Undo2,
} from "lucide-react";
import {
  api,
  type AIAdsAdPackage,
  type AIAdsCopyLanguage,
  type AIAdsGeneratedCreative,
} from "@/lib/api";
import {
  AD_LIMITS,
  META_CTA_OPTIONS,
  copyToClipboard,
  counterTone,
  ctaLabel,
  downloadText,
  packageCsv,
  pasteBlock,
  withTracking,
  type CounterTone,
} from "@/lib/adPackage";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";

type LanguageChoice = "auto" | AIAdsCopyLanguage;

const POLL_MS = 3000;
const MAX_POLLS = 60;

const fieldClass =
  "w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-content placeholder:text-content-subtle transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500/30 focus:border-brand-500 disabled:opacity-50";

const toneClass: Record<CounterTone, string> = {
  ok: "text-emerald-600 dark:text-emerald-400",
  warn: "text-amber-600 dark:text-amber-400",
  over: "text-red-600 dark:text-red-400",
};

function message(e: unknown, fallback: string) {
  return e instanceof Error && e.message ? e.message : fallback;
}

function fileStem(pkg: AIAdsAdPackage) {
  return (pkg.ad_name || "ad-package").replace(/[^\w.-]+/g, "_").slice(0, 80);
}

export function AdPackagePanel({
  storeId,
  creative,
  onCreativeChange,
}: {
  storeId: string;
  creative: AIAdsGeneratedCreative;
  onCreativeChange?: (next: AIAdsGeneratedCreative) => void;
}) {
  const [local, setLocal] = useState<AIAdsGeneratedCreative>(creative);
  const saved = local.ad_package ?? null;
  const savedKey = saved ? `${saved.status}|${saved.generated_at}|${saved.updated_at}` : "none";
  const savedRef = useRef(saved);
  savedRef.current = saved;

  const [draft, setDraft] = useState<AIAdsAdPackage | null>(saved);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [language, setLanguage] = useState<LanguageChoice>(saved?.language ?? "auto");
  const [copied, setCopied] = useState<string | null>(null);
  const [pollsLeft, setPollsLeft] = useState(MAX_POLLS);

  useEffect(() => {
    setLocal(creative);
  }, [creative]);

  useEffect(() => {
    if (!dirty) setDraft(savedRef.current);
  }, [savedKey, dirty]);

  const savedLanguage = saved?.status === "READY" ? saved.language : null;
  useEffect(() => {
    if (savedLanguage) setLanguage(savedLanguage);
  }, [savedLanguage]);

  const generating = saved?.status === "GENERATING";
  useEffect(() => {
    if (!generating || pollsLeft <= 0) return;
    const t = window.setTimeout(() => {
      api.aiAds
        .getCreative(storeId, local.id)
        .then((next) => accept(next))
        .catch(() => undefined)
        .finally(() => setPollsLeft((n) => n - 1));
    }, POLL_MS);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [generating, pollsLeft, storeId, local.id]);

  function accept(next: AIAdsGeneratedCreative) {
    setLocal(next);
    onCreativeChange?.(next);
  }

  function edit(mutate: (p: AIAdsAdPackage) => AIAdsAdPackage) {
    setDraft((prev) => (prev ? withTracking(mutate(prev)) : prev));
    setDirty(true);
  }

  async function copy(key: string, text: string) {
    if (await copyToClipboard(text)) {
      setCopied(key);
      window.setTimeout(() => setCopied((k) => (k === key ? null : k)), 1500);
    }
  }

  async function save(): Promise<boolean> {
    if (!draft) return false;
    setBusy("save");
    setError("");
    try {
      const next = await api.aiAds.saveAdPackage(storeId, local.id, draft);
      setDirty(false);
      accept(next);
      return true;
    } catch (e) {
      setError(message(e, "Could not save your edits"));
      return false;
    } finally {
      setBusy(null);
    }
  }

  function discard() {
    setDirty(false);
    setDraft(saved);
  }

  async function regenerate(field?: string) {
    if (!field && dirty && !window.confirm("Regenerating replaces your unsaved edits. Continue?")) return;
    if (field && dirty && !(await save())) return;
    setBusy(field ?? "all");
    setError("");
    try {
      const next = await api.aiAds.regenerateAdPackage(
        storeId,
        local.id,
        field ? { field } : { language }
      );
      setDirty(false);
      setPollsLeft(MAX_POLLS);
      accept(next);
    } catch (e) {
      setError(message(e, "Could not write the ad copy"));
    } finally {
      setBusy(null);
    }
  }

  const header = (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h3 className="flex items-center gap-2 text-base font-semibold text-content">
          <ClipboardList className="h-4 w-4 text-brand-600 dark:text-brand-400" />
          Ads Manager copy
        </h3>
        <p className="mt-0.5 text-xs text-content-muted">
          Everything to paste into Meta Ads Manager for this creative.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {draft?.status === "READY" && (
          <Badge variant="muted">{draft.language === "fr" ? "Français (QC)" : "English"}</Badge>
        )}
        {draft?.edited && <Badge variant="brand">Edited</Badge>}
        <select
          aria-label="Copy language"
          value={language}
          onChange={(e) => setLanguage(e.target.value as LanguageChoice)}
          disabled={Boolean(busy) || generating}
          className="h-8 rounded-lg border border-border bg-surface px-2 text-xs text-content focus:outline-none focus:ring-2 focus:ring-brand-500/30"
        >
          <option value="auto">Auto language</option>
          <option value="en">English</option>
          <option value="fr">Français (Québec)</option>
        </select>
        <Button
          size="sm"
          variant="outline"
          onClick={() => void regenerate()}
          isLoading={busy === "all"}
          disabled={Boolean(busy) || generating}
        >
          <RefreshCw className="h-3.5 w-3.5" />
          {saved ? "Regenerate copy" : "Write ad copy"}
        </Button>
      </div>
    </div>
  );

  if (!draft || draft.status !== "READY") {
    return (
      <section className="space-y-4">
        {header}
        {error && <ErrorNote>{error}</ErrorNote>}
        {generating && busy !== "all" ? (
          <div className="rounded-xl border border-brand-line/40 bg-surface-muted/40 px-4 py-5">
            <p className="flex items-center gap-2 text-sm font-medium text-content">
              {pollsLeft > 0 && <Loader2 className="h-4 w-4 animate-spin text-brand-600" />}
              {pollsLeft > 0
                ? "Writing primary text, headlines, A/B variants, and ad setup…"
                : "Still writing. Refresh the page, or regenerate the copy."}
            </p>
            <div className="mt-4 space-y-2">
              {[88, 72, 55].map((w) => (
                <div key={w} className="h-3 animate-pulse rounded bg-surface-muted" style={{ width: `${w}%` }} />
              ))}
            </div>
          </div>
        ) : busy === "all" ? (
          <p className="flex items-center gap-2 rounded-xl border border-border px-4 py-5 text-sm text-content-muted">
            <Loader2 className="h-4 w-4 animate-spin text-brand-600" />
            Writing the Ads Manager copy. This takes a few seconds.
          </p>
        ) : draft?.status === "FAILED" ? (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-4 text-sm">
            <p className="flex items-start gap-2 font-medium text-amber-700 dark:text-amber-400">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              The ad copy did not generate. The creative itself is fine.
            </p>
            {draft.error && <p className="mt-1 pl-6 text-content-muted">{draft.error}</p>}
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-border px-4 py-6 text-center">
            <Sparkles className="mx-auto h-5 w-5 text-content-subtle" />
            <p className="mt-2 text-sm text-content-muted">
              No Ads Manager copy for this creative yet. Pick a language and click “Write ad copy”.
            </p>
          </div>
        )}
      </section>
    );
  }

  const pkg = draft;
  const fieldBusy = (key: string) => busy === key;
  const locked = Boolean(busy);

  return (
    <section className="space-y-5">
      {header}

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={() => void copy("all", pasteBlock(pkg))}>
          {copied === "all" ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          {copied === "all" ? "Copied" : "Copy all"}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() =>
            downloadText(`${fileStem(pkg)}.csv`, packageCsv(pkg), "text/csv")
          }
        >
          <Download className="h-3.5 w-3.5" />
          CSV
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() =>
            downloadText(`${fileStem(pkg)}.json`, JSON.stringify(pkg, null, 2), "application/json")
          }
        >
          <Download className="h-3.5 w-3.5" />
          JSON
        </Button>
        {dirty && (
          <>
            <span className="ml-auto text-xs text-amber-600 dark:text-amber-400">Unsaved changes</span>
            <Button size="sm" variant="ghost" onClick={discard} disabled={locked}>
              <Undo2 className="h-3.5 w-3.5" />
              Discard
            </Button>
            <Button size="sm" onClick={() => void save()} isLoading={busy === "save"} disabled={locked}>
              <Save className="h-3.5 w-3.5" />
              Save
            </Button>
          </>
        )}
      </div>

      {error && <ErrorNote>{error}</ErrorNote>}
      {busy === "all" && (
        <p className="flex items-center gap-2 text-sm text-content-muted">
          <Loader2 className="h-4 w-4 animate-spin text-brand-600" />
          Rewriting the whole package…
        </p>
      )}

      {pkg.ai_generated !== false && (
        <div className="flex items-start gap-2 rounded-xl border border-brand-500/20 bg-brand-500/5 px-4 py-3 text-xs">
          <Badge variant="brand" className="shrink-0">
            AI-generated
          </Badge>
          <span className="text-content-muted">
            {pkg.ai_disclosure_note ||
              "Made with generative AI. Keep Meta's AI info label on and never present an AI person as a real customer."}
          </span>
        </div>
      )}

      {pkg.test_hypothesis && (
        <p className="rounded-xl border border-border px-4 py-3 text-xs">
          <span className="font-medium text-content">Test: </span>
          <span className="text-content-muted">
            {pkg.test_hypothesis}
            {pkg.test_variable ? ` · variable: ${pkg.test_variable}` : ""}
          </span>
        </p>
      )}

      {pkg.warnings.length > 0 && (
        <ul className="space-y-1 rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-xs text-amber-800 dark:text-amber-300">
          {pkg.warnings.map((w) => (
            <li key={w} className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>{w}</span>
            </li>
          ))}
        </ul>
      )}

      <Section title="Creative copy" hint={pkg.angle ? `Main angle: ${pkg.angle}` : undefined}>
        <CopyField
          label="Primary text"
          value={pkg.primary_text}
          onChange={(v) => edit((p) => ({ ...p, primary_text: v }))}
          limit={AD_LIMITS.primary_text.limit}
          ideal={AD_LIMITS.primary_text.ideal}
          multiline
          rows={6}
          hookAt={AD_LIMITS.primary_hook}
          copied={copied === "primary_text"}
          onCopy={() => void copy("primary_text", pkg.primary_text)}
          onRegenerate={() => void regenerate("primary_text")}
          regenerating={fieldBusy("primary_text")}
          disabled={locked}
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <CopyField
            label="Headline"
            value={pkg.headline}
            onChange={(v) => edit((p) => ({ ...p, headline: v }))}
            limit={AD_LIMITS.headline.limit}
            ideal={AD_LIMITS.headline.ideal}
            hint={`Under ${AD_LIMITS.headline.ideal} avoids mobile truncation`}
            copied={copied === "headline"}
            onCopy={() => void copy("headline", pkg.headline)}
            onRegenerate={() => void regenerate("headline")}
            regenerating={fieldBusy("headline")}
            disabled={locked}
          />
          <CopyField
            label="Description"
            value={pkg.description}
            onChange={(v) => edit((p) => ({ ...p, description: v }))}
            limit={AD_LIMITS.description.limit}
            ideal={AD_LIMITS.description.ideal}
            copied={copied === "description"}
            onCopy={() => void copy("description", pkg.description)}
            onRegenerate={() => void regenerate("description")}
            regenerating={fieldBusy("description")}
            disabled={locked}
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <FieldShell
            label="Call to action"
            actions={
              <>
                <MiniAction
                  label="Regenerate"
                  onClick={() => void regenerate("cta")}
                  busy={fieldBusy("cta")}
                  disabled={locked}
                  icon={RefreshCw}
                />
                <MiniAction
                  label={copied === "cta" ? "Copied" : "Copy"}
                  onClick={() => void copy("cta", ctaLabel(pkg.cta))}
                  icon={copied === "cta" ? Check : Copy}
                />
              </>
            }
          >
            <select
              value={pkg.cta}
              onChange={(e) => edit((p) => ({ ...p, cta: e.target.value }))}
              disabled={locked}
              className={cn(fieldClass, "h-10")}
            >
              {META_CTA_OPTIONS.map((cta) => (
                <option key={cta} value={cta}>
                  {ctaLabel(cta)} ({cta})
                </option>
              ))}
              {!META_CTA_OPTIONS.includes(pkg.cta as (typeof META_CTA_OPTIONS)[number]) && pkg.cta ? (
                <option value={pkg.cta}>
                  {ctaLabel(pkg.cta)} ({pkg.cta})
                </option>
              ) : null}
            </select>
          </FieldShell>
          <CopyField
            label="Display link"
            badge="Optional"
            value={pkg.display_link}
            placeholder="luxory.com"
            onChange={(v) => edit((p) => ({ ...p, display_link: v }))}
            copied={copied === "display_link"}
            onCopy={() => void copy("display_link", pkg.display_link)}
            disabled={locked}
          />
        </div>
      </Section>

      <Section title="A/B variants" hint="Three angles to test against the main ad">
        <div className="space-y-3">
          {pkg.primary_text_variants.map((v, i) => {
            const headline = pkg.headline_variants[i];
            const pKey = `primary_text_variants.${i}`;
            const hKey = `headline_variants.${i}`;
            return (
              <div key={v.angle || i} className="space-y-3 rounded-xl border border-border bg-surface-muted/30 p-3">
                <Badge variant="brand">{v.label || `Variant ${i + 1}`}</Badge>
                <CopyField
                  label="Primary text"
                  value={v.text}
                  onChange={(text) =>
                    edit((p) => ({
                      ...p,
                      primary_text_variants: p.primary_text_variants.map((x, j) => (j === i ? { ...x, text } : x)),
                    }))
                  }
                  limit={AD_LIMITS.primary_text.limit}
                  ideal={AD_LIMITS.primary_text.ideal}
                  multiline
                  rows={4}
                  hookAt={AD_LIMITS.primary_hook}
                  copied={copied === pKey}
                  onCopy={() => void copy(pKey, v.text)}
                  onRegenerate={() => void regenerate(pKey)}
                  regenerating={fieldBusy(pKey)}
                  disabled={locked}
                />
                {headline && (
                  <CopyField
                    label="Headline"
                    value={headline.text}
                    onChange={(text) =>
                      edit((p) => ({
                        ...p,
                        headline_variants: p.headline_variants.map((x, j) => (j === i ? { ...x, text } : x)),
                      }))
                    }
                    limit={AD_LIMITS.headline.limit}
                    ideal={AD_LIMITS.headline.ideal}
                    copied={copied === hKey}
                    onCopy={() => void copy(hKey, headline.text)}
                    onRegenerate={() => void regenerate(hKey)}
                    regenerating={fieldBusy(hKey)}
                    disabled={locked}
                  />
                )}
              </div>
            );
          })}
        </div>
      </Section>

      <Section title="Ad setup">
        <CopyField
          label="Ad name"
          hint="[Product]_[Angle]_[Format]_[YYYY-MM-DD]"
          value={pkg.ad_name}
          onChange={(v) =>
            edit((p) => ({
              ...p,
              ad_name: v,
              utm: p.utm.utm_content === p.ad_name ? { ...p.utm, utm_content: v } : p.utm,
            }))
          }
          copied={copied === "ad_name"}
          onCopy={() => void copy("ad_name", pkg.ad_name)}
          disabled={locked}
        />
        <CopyField
          label="Website URL"
          value={pkg.base_url || ""}
          placeholder="https://your-store.com/products/…"
          onChange={(v) => edit((p) => ({ ...p, base_url: v || null }))}
          copied={copied === "base_url"}
          onCopy={() => void copy("base_url", pkg.base_url || "")}
          disabled={locked}
        />
        <div className="grid gap-3 sm:grid-cols-3">
          {(["utm_campaign", "utm_content", "utm_term"] as const).map((key) => (
            <label key={key} className="block space-y-1">
              <span className="text-xs font-medium text-content-muted">{key}</span>
              <input
                value={pkg.utm[key]}
                onChange={(e) => edit((p) => ({ ...p, utm: { ...p.utm, [key]: e.target.value } }))}
                disabled={locked}
                className={cn(fieldClass, "h-9 font-mono text-xs")}
              />
            </label>
          ))}
        </div>
        <ReadOnlyRow
          label="URL parameters"
          hint="Paste into the ad's URL parameters field"
          value={pkg.url_parameters}
          copied={copied === "url_parameters"}
          onCopy={() => void copy("url_parameters", pkg.url_parameters)}
        />
        <ReadOnlyRow
          label="Full destination URL"
          value={pkg.destination_url || "Add a website URL above"}
          copied={copied === "destination_url"}
          onCopy={() => void copy("destination_url", pkg.destination_url || "")}
        />
        <dl className="grid gap-3 rounded-xl border border-border px-4 py-3 text-sm sm:grid-cols-3">
          <KeyValue label="Campaign objective" value={`${pkg.campaign_objective_label} (${pkg.campaign_objective})`} />
          <KeyValue label="Conversion location" value={pkg.conversion_location} />
          <KeyValue label="Conversion event" value={pkg.conversion_event || "—"} />
        </dl>
        {pkg.tracking_notes.length > 0 && (
          <ul className="list-disc space-y-1 pl-5 text-xs text-content-muted">
            {pkg.tracking_notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        )}
        <div className="rounded-xl border border-border px-4 py-3 text-sm">
          <p className="text-xs uppercase tracking-wide text-content-subtle">Special ad category</p>
          <p className="font-medium text-content">{pkg.special_ad_category}</p>
          <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">{pkg.special_ad_category_note}</p>
        </div>
      </Section>

      <Section
        title="Audience & targeting"
        hint="Suggestions to review, not claims about people"
        actions={
          <>
            <MiniAction
              label="Regenerate"
              onClick={() => void regenerate("audience")}
              busy={fieldBusy("audience")}
              disabled={locked}
              icon={RefreshCw}
            />
            <MiniAction
              label={copied === "audience" ? "Copied" : "Copy"}
              onClick={() => void copy("audience", audienceText(pkg))}
              icon={copied === "audience" ? Check : Copy}
            />
          </>
        }
      >
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="block space-y-1">
            <span className="text-xs font-medium text-content-muted">Age min</span>
            <input
              type="number"
              min={18}
              max={65}
              value={pkg.audience.age_min}
              onChange={(e) => edit((p) => ({ ...p, audience: { ...p.audience, age_min: Number(e.target.value) } }))}
              disabled={locked}
              className={cn(fieldClass, "h-9")}
            />
          </label>
          <label className="block space-y-1">
            <span className="text-xs font-medium text-content-muted">Age max</span>
            <input
              type="number"
              min={18}
              max={65}
              value={pkg.audience.age_max}
              onChange={(e) => edit((p) => ({ ...p, audience: { ...p.audience, age_max: Number(e.target.value) } }))}
              disabled={locked}
              className={cn(fieldClass, "h-9")}
            />
          </label>
          <label className="block space-y-1">
            <span className="text-xs font-medium text-content-muted">Gender</span>
            <select
              value={pkg.audience.genders}
              onChange={(e) => edit((p) => ({ ...p, audience: { ...p.audience, genders: e.target.value } }))}
              disabled={locked}
              className={cn(fieldClass, "h-9")}
            >
              <option value="All">All</option>
              <option value="Women">Women</option>
              <option value="Men">Men</option>
            </select>
          </label>
        </div>
        <ListField
          label="Interests"
          separator=", "
          value={pkg.audience.interests}
          onChange={(interests) => edit((p) => ({ ...p, audience: { ...p.audience, interests } }))}
          disabled={locked}
        />
        <label className="block space-y-1">
          <span className="text-xs font-medium text-content-muted">Notes</span>
          <textarea
            rows={2}
            value={pkg.audience.notes}
            onChange={(e) => edit((p) => ({ ...p, audience: { ...p.audience, notes: e.target.value } }))}
            disabled={locked}
            className={fieldClass}
          />
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <ListField
            label="Lookalike ideas (one per line)"
            separator={"\n"}
            value={pkg.audience.lookalike_ideas}
            onChange={(lookalike_ideas) => edit((p) => ({ ...p, audience: { ...p.audience, lookalike_ideas } }))}
            disabled={locked}
          />
          <ListField
            label="Retargeting ideas (one per line)"
            separator={"\n"}
            value={pkg.audience.retargeting_ideas}
            onChange={(retargeting_ideas) => edit((p) => ({ ...p, audience: { ...p.audience, retargeting_ideas } }))}
            disabled={locked}
          />
        </div>
      </Section>

      <Section title={`Placements · ${pkg.aspect_ratio}`}>
        <div className="flex flex-wrap gap-1.5">
          {pkg.placements.map((p) => (
            <Badge key={p} variant="default">
              {p}
            </Badge>
          ))}
        </div>
        {pkg.placement_notes && <p className="text-xs text-content-muted">{pkg.placement_notes}</p>}
      </Section>
    </section>
  );
}

function audienceText(pkg: AIAdsAdPackage) {
  const a = pkg.audience;
  const clean = (xs: string[]) => xs.map((x) => x.trim()).filter(Boolean);
  return [
    `Age: ${a.age_min}–${a.age_max} · Gender: ${a.genders}`,
    clean(a.interests).length ? `Interests: ${clean(a.interests).join(", ")}` : "",
    a.notes,
    clean(a.lookalike_ideas).length ? `Lookalikes:\n${clean(a.lookalike_ideas).map((x) => `- ${x}`).join("\n")}` : "",
    clean(a.retargeting_ideas).length
      ? `Retargeting:\n${clean(a.retargeting_ideas).map((x) => `- ${x}`).join("\n")}`
      : "",
  ]
    .filter(Boolean)
    .join("\n");
}

function Section({
  title,
  hint,
  actions,
  children,
}: {
  title: string;
  hint?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="space-y-3 border-t border-border pt-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex flex-wrap items-baseline gap-2">
          <h4 className="text-sm font-semibold text-content">{title}</h4>
          {hint && <span className="text-xs text-content-subtle">{hint}</span>}
        </div>
        {actions && <div className="flex items-center gap-1">{actions}</div>}
      </div>
      {children}
    </div>
  );
}

function MiniAction({
  label,
  onClick,
  icon: Icon,
  busy,
  disabled,
}: {
  label: string;
  onClick: () => void;
  icon: typeof Copy;
  busy?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || busy}
      className="inline-flex h-7 items-center gap-1 rounded-md px-2 text-xs font-medium text-content-muted transition-colors hover:bg-surface-muted hover:text-content disabled:cursor-not-allowed disabled:opacity-50"
    >
      {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Icon className="h-3.5 w-3.5" />}
      {label}
    </button>
  );
}

function Counter({ length, limit, ideal }: { length: number; limit: number; ideal?: number }) {
  return (
    <span className={cn("text-xs font-medium tabular-nums", toneClass[counterTone(length, limit, ideal)])}>
      {length}/{limit}
    </span>
  );
}

function FieldShell({
  label,
  badge,
  counter,
  actions,
  hint,
  children,
}: {
  label: string;
  badge?: string;
  counter?: ReactNode;
  actions?: ReactNode;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="min-w-0 space-y-1.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-content">{label}</span>
          {badge && <Badge variant="muted">{badge}</Badge>}
          {counter}
        </div>
        {actions && <div className="flex items-center gap-0.5">{actions}</div>}
      </div>
      {children}
      {hint && <p className="text-xs text-content-subtle">{hint}</p>}
    </div>
  );
}

function CopyField({
  label,
  badge,
  value,
  onChange,
  limit,
  ideal,
  multiline,
  rows = 3,
  hookAt,
  hint,
  placeholder,
  copied,
  onCopy,
  onRegenerate,
  regenerating,
  disabled,
}: {
  label: string;
  badge?: string;
  value: string;
  onChange: (value: string) => void;
  limit?: number;
  ideal?: number;
  multiline?: boolean;
  rows?: number;
  hookAt?: number;
  hint?: string;
  placeholder?: string;
  copied?: boolean;
  onCopy: () => void;
  onRegenerate?: () => void;
  regenerating?: boolean;
  disabled?: boolean;
}) {
  const over = limit !== undefined && value.length > limit;
  return (
    <FieldShell
      label={label}
      badge={badge}
      hint={hint}
      counter={limit !== undefined ? <Counter length={value.length} limit={limit} ideal={ideal} /> : null}
      actions={
        <>
          {onRegenerate && (
            <MiniAction
              label="Regenerate"
              onClick={onRegenerate}
              busy={regenerating}
              disabled={disabled}
              icon={RefreshCw}
            />
          )}
          <MiniAction label={copied ? "Copied" : "Copy"} onClick={onCopy} icon={copied ? Check : Copy} />
        </>
      }
    >
      {multiline ? (
        <textarea
          rows={rows}
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          className={cn(fieldClass, "leading-relaxed", over && "border-red-500 focus:ring-red-500/30")}
        />
      ) : (
        <input
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          className={cn(fieldClass, "h-10", over && "border-red-500 focus:ring-red-500/30")}
        />
      )}
      {hookAt !== undefined && value.length > hookAt && (
        <p className="text-xs text-content-subtle">
          Shown before “See more”:{" "}
          <span className="text-content-muted">{value.slice(0, hookAt).trimEnd()}…</span>
        </p>
      )}
    </FieldShell>
  );
}

function ListField({
  label,
  value,
  separator,
  onChange,
  disabled,
}: {
  label: string;
  value: string[];
  separator: ", " | "\n";
  onChange: (value: string[]) => void;
  disabled?: boolean;
}) {
  const splitOn = separator === "\n" ? "\n" : ",";
  return (
    <label className="block space-y-1">
      <span className="text-xs font-medium text-content-muted">{label}</span>
      <textarea
        rows={separator === "\n" ? 3 : 2}
        value={value.join(separator)}
        onChange={(e) =>
          onChange(e.target.value.split(splitOn).map((part) => (splitOn === "," ? part.trimStart() : part)))
        }
        disabled={disabled}
        className={fieldClass}
      />
    </label>
  );
}

function ReadOnlyRow({
  label,
  hint,
  value,
  copied,
  onCopy,
}: {
  label: string;
  hint?: string;
  value: string;
  copied: boolean;
  onCopy: () => void;
}) {
  return (
    <FieldShell
      label={label}
      hint={hint}
      actions={<MiniAction label={copied ? "Copied" : "Copy"} onClick={onCopy} icon={copied ? Check : Copy} />}
    >
      <p className="break-all rounded-lg border border-border bg-surface-muted/40 px-3 py-2 font-mono text-xs text-content">
        {value}
      </p>
    </FieldShell>
  );
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-content-subtle">{label}</dt>
      <dd className="font-medium text-content">{value}</dd>
    </div>
  );
}

function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <p className="flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-600">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{children}</span>
    </p>
  );
}
