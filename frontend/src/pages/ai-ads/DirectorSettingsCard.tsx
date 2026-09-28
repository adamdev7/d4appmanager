import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { api, type AIAdsProduct } from "@/lib/api";
import type { DirectorAggressiveness, DirectorOffer, DirectorSettings } from "@/lib/directorTypes";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Switch } from "@/components/ui/Switch";
import { cn } from "@/lib/cn";

const LEVELS: Array<{ id: DirectorAggressiveness; label: string; help: string }> = [
  { id: "safe", label: "Safe", help: "Proven formats and winners, one small wild card" },
  { id: "balanced", label: "Balanced", help: "Mostly proven, one wild card" },
  { id: "bold", label: "Bold", help: "More novelty, two wild cards" },
];

export function DirectorSettingsCard({
  storeId,
  settings,
  products,
  onSaved,
}: {
  storeId: string;
  settings: DirectorSettings;
  products: AIAdsProduct[];
  onSaved: (settings: DirectorSettings) => void;
}) {
  const [form, setForm] = useState<DirectorSettings>(settings);
  const [neverDo, setNeverDo] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function set<K extends keyof DirectorSettings>(key: K, value: DirectorSettings[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function toggleProduct(key: "priority_product_ids" | "excluded_product_ids", id: string) {
    const other = key === "priority_product_ids" ? "excluded_product_ids" : "priority_product_ids";
    setForm((prev) => {
      const has = prev[key].includes(id);
      return {
        ...prev,
        [key]: has ? prev[key].filter((x) => x !== id) : [...prev[key], id],
        [other]: prev[other].filter((x) => x !== id),
      };
    });
  }

  function setOffer(index: number, patch: Partial<DirectorOffer>) {
    set(
      "offers",
      form.offers.map((o, i) => (i === index ? { ...o, ...patch } : o))
    );
  }

  async function save() {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const saved = await api.aiAds.updateDirectorSettings(storeId, {
        enabled: form.enabled,
        drive_weekly: form.drive_weekly,
        challenge_requests: form.challenge_requests,
        aggressiveness: form.aggressiveness,
        weekly_credit_cap_usd: Number(form.weekly_credit_cap_usd) || 0,
        priority_product_ids: form.priority_product_ids,
        excluded_product_ids: form.excluded_product_ids,
        offers: form.offers.filter((o) => o.label.trim()),
        never_do: form.never_do,
        margin_floor_pct: form.margin_floor_pct,
        low_stock_threshold: Number(form.low_stock_threshold) || 0,
        copy_language: form.copy_language,
      });
      setForm(saved);
      onSaved(saved);
      setMessage("Saved");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save Director settings");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardTitle>Director settings</CardTitle>
      <CardDescription>How bold to be, how much to spend, and what is off limits.</CardDescription>

      <div className="mt-5 space-y-4">
        <Switch
          checked={form.enabled}
          onChange={(v) => set("enabled", v)}
          label="Creative Director on"
          description="Builds the weekly brief and idea board."
        />
        <Switch
          checked={form.drive_weekly}
          onChange={(v) => set("drive_weekly", v)}
          disabled={!form.enabled}
          label="Director drives weekly runs"
          description="The weekly batch produces the brief (several products and ad types) instead of fixed counts on one product. Your weekly stills/videos counts stay the maximum."
        />
        <Switch
          checked={form.challenge_requests}
          onChange={(v) => set("challenge_requests", v)}
          disabled={!form.enabled}
          label="Second opinion on manual requests"
          description="Before Generate runs, the Director flags weak or risky requests and offers an alternative. You can always generate exactly what you asked."
        />

        <div>
          <p className="mb-1.5 text-sm font-medium text-content">Aggressiveness</p>
          <div className="grid gap-2 sm:grid-cols-3">
            {LEVELS.map((level) => (
              <button
                key={level.id}
                type="button"
                onClick={() => set("aggressiveness", level.id)}
                className={cn(
                  "rounded-lg border p-3 text-left text-sm transition-colors",
                  form.aggressiveness === level.id
                    ? "border-brand-500 bg-brand-500/5 ring-1 ring-brand-500/30"
                    : "border-border hover:bg-surface-muted"
                )}
              >
                <span className="block font-medium">{level.label}</span>
                <span className="block text-xs text-content-muted">{level.help}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Input
            label="Weekly credit cap (USD)"
            type="number"
            min={0}
            step={1}
            value={form.weekly_credit_cap_usd}
            onChange={(e) => set("weekly_credit_cap_usd", Number(e.target.value))}
            hint="0 = no cap. Estimated OpenAI usage."
          />
          <Input
            label="Margin floor (%)"
            type="number"
            min={0}
            max={95}
            value={form.margin_floor_pct ?? ""}
            onChange={(e) => set("margin_floor_pct", e.target.value === "" ? null : Number(e.target.value))}
            hint="Skip products below this margin (needs COGS)."
          />
          <Input
            label="Low-stock threshold"
            type="number"
            min={0}
            value={form.low_stock_threshold}
            onChange={(e) => set("low_stock_threshold", Number(e.target.value))}
            hint="Units at or below this are not pushed."
          />
          <Select
            label="Copy language"
            value={form.copy_language}
            onChange={(e) => set("copy_language", e.target.value as DirectorSettings["copy_language"])}
          >
            <option value="auto">Auto (EN + Quebec FR)</option>
            <option value="en">English</option>
            <option value="fr">Français (Québec)</option>
          </Select>
        </div>

        <div>
          <p className="mb-1.5 text-sm font-medium text-content">Products</p>
          <p className="mb-2 text-xs text-content-muted">Prioritize to push a product; exclude to never suggest it.</p>
          <div className="max-h-64 space-y-1 overflow-y-auto rounded-lg border border-border p-2">
            {products.length === 0 && <p className="text-xs text-content-muted">No products synced yet.</p>}
            {products.map((p) => {
              const priority = form.priority_product_ids.includes(p.id);
              const excluded = form.excluded_product_ids.includes(p.id);
              return (
                <div key={p.id} className="flex items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-surface-muted">
                  <span className={cn("min-w-0 flex-1 truncate", excluded && "text-content-subtle line-through")}>{p.title}</span>
                  <button
                    type="button"
                    onClick={() => toggleProduct("priority_product_ids", p.id)}
                    className={cn(
                      "rounded-full border px-2 py-0.5 text-xs",
                      priority ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700" : "border-border text-content-subtle"
                    )}
                  >
                    Prioritize
                  </button>
                  <button
                    type="button"
                    onClick={() => toggleProduct("excluded_product_ids", p.id)}
                    className={cn(
                      "rounded-full border px-2 py-0.5 text-xs",
                      excluded ? "border-red-500/30 bg-red-500/10 text-red-600" : "border-border text-content-subtle"
                    )}
                  >
                    Exclude
                  </button>
                </div>
              );
            })}
          </div>
        </div>

        <div>
          <p className="mb-1.5 text-sm font-medium text-content">Offers you actually run</p>
          <p className="mb-2 text-xs text-content-muted">
            The Director only uses offers listed here. Anything else it suggests is marked “requires your confirmation”.
          </p>
          <div className="space-y-2">
            {form.offers.map((offer, i) => (
              <div key={offer.id || i} className="flex flex-wrap items-end gap-2">
                <div className="min-w-[10rem] flex-1">
                  <Input
                    placeholder="Free shipping over $75"
                    value={offer.label}
                    onChange={(e) => setOffer(i, { label: e.target.value })}
                  />
                </div>
                <div className="min-w-[12rem] flex-[2]">
                  <Input
                    placeholder="Details (dates, conditions)"
                    value={offer.details}
                    onChange={(e) => setOffer(i, { details: e.target.value })}
                  />
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label="Remove offer"
                  onClick={() => set("offers", form.offers.filter((_, j) => j !== i))}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
            <Button
              variant="outline"
              size="sm"
              onClick={() => set("offers", [...form.offers, { id: "", label: "", details: "" }])}
            >
              <Plus className="h-3.5 w-3.5" />
              Add offer
            </Button>
          </div>
        </div>

        <div>
          <p className="mb-1.5 text-sm font-medium text-content">Never do</p>
          <div className="flex flex-wrap gap-1.5">
            {form.never_do.map((rule) => (
              <span key={rule} className="inline-flex items-center gap-1 rounded-full border border-border bg-surface-muted px-2.5 py-1 text-xs">
                {rule}
                <button
                  type="button"
                  aria-label={`Remove ${rule}`}
                  onClick={() => set("never_do", form.never_do.filter((r) => r !== rule))}
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
          <form
            className="mt-2 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              const rule = neverDo.trim();
              if (rule && !form.never_do.includes(rule)) set("never_do", [...form.never_do, rule]);
              setNeverDo("");
            }}
          >
            <div className="flex-1">
              <Input
                placeholder="e.g. countdown timers, pets, the word “cheap”"
                value={neverDo}
                onChange={(e) => setNeverDo(e.target.value)}
              />
            </div>
            <Button type="submit" variant="outline">
              Add
            </Button>
          </form>
        </div>

        <div className="flex items-center gap-3">
          <Button onClick={() => void save()} isLoading={saving}>
            Save Director settings
          </Button>
          {message && <span className="text-sm text-emerald-600">{message}</span>}
          {error && <span className="text-sm text-red-600">{error}</span>}
        </div>
      </div>
    </Card>
  );
}
