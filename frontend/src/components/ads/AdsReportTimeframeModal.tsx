import { useEffect, useState } from "react";
import { Sparkles, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import type { AdsPeriod } from "@/lib/adsTypes";

export type ReportTimeframe = AdsPeriod;

const OPTIONS: Array<{ id: ReportTimeframe; label: string; hint: string }> = [
  { id: "1d", label: "Daily", hint: "Today only" },
  { id: "7d", label: "7 days", hint: "Last week" },
  { id: "14d", label: "14 days", hint: "Last 2 weeks" },
  { id: "30d", label: "30 days", hint: "Last month" },
  { id: "90d", label: "90 days", hint: "Last quarter" },
  { id: "all", label: "All time", hint: "Full history" },
  { id: "custom", label: "Custom", hint: "Pick dates" },
];

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function daysAgoISO(days: number) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

type Props = {
  open: boolean;
  generating: boolean;
  defaultPeriod?: ReportTimeframe;
  defaultSince?: string;
  defaultUntil?: string;
  onClose: () => void;
  onConfirm: (opts: {
    period: ReportTimeframe;
    since?: string;
    until?: string;
  }) => void;
};

export function AdsReportTimeframeModal({
  open,
  generating,
  defaultPeriod = "7d",
  defaultSince,
  defaultUntil,
  onClose,
  onConfirm,
}: Props) {
  const [selected, setSelected] = useState<ReportTimeframe>("7d");
  const [since, setSince] = useState(daysAgoISO(29));
  const [until, setUntil] = useState(todayISO());
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setSelected(defaultPeriod || "7d");
    setSince(defaultSince || daysAgoISO(29));
    setUntil(defaultUntil || todayISO());
    setError("");
  }, [open, defaultPeriod, defaultSince, defaultUntil]);

  if (!open) return null;

  const confirm = () => {
    if (selected === "custom") {
      if (!since || !until) {
        setError("Pick both a start and end date");
        return;
      }
      if (since > until) {
        setError("Start date must be on or before end date");
        return;
      }
      setError("");
      onConfirm({ period: "custom", since, until });
      return;
    }
    setError("");
    onConfirm({ period: selected });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        type="button"
        className="absolute inset-0 bg-black/40 backdrop-blur-[1px]"
        aria-label="Close"
        onClick={() => !generating && onClose()}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="ads-report-timeframe-title"
        className="relative w-full max-w-md rounded-xl border border-border bg-surface p-5 shadow-elevated"
      >
        <div className="flex items-start justify-between gap-3 mb-1">
          <div>
            <h2 id="ads-report-timeframe-title" className="text-lg font-semibold text-content">
              Report timeframe
            </h2>
            <p className="text-sm text-content-muted mt-0.5">
              Choose the period for this AI ads analysis.
            </p>
          </div>
          <button
            type="button"
            onClick={() => !generating && onClose()}
            className="rounded-lg p-1.5 text-content-muted hover:bg-surface-muted hover:text-content"
            aria-label="Close dialog"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2">
          {OPTIONS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              disabled={generating}
              onClick={() => {
                setSelected(opt.id);
                setError("");
              }}
              className={cn(
                "rounded-lg border px-3 py-2.5 text-left transition-colors",
                selected === opt.id
                  ? "border-brand-500 bg-brand-500/10"
                  : "border-border hover:border-border-strong hover:bg-surface-muted/60"
              )}
            >
              <span className="block text-sm font-medium text-content">{opt.label}</span>
              <span className="block text-xs text-content-muted mt-0.5">{opt.hint}</span>
            </button>
          ))}
        </div>

        {selected === "custom" && (
          <div className="mt-4 space-y-3 rounded-lg border border-border bg-surface-muted/30 p-3">
            <Input
              label="From"
              type="date"
              value={since}
              max={until || todayISO()}
              disabled={generating}
              onChange={(e) => setSince(e.target.value)}
            />
            <Input
              label="To"
              type="date"
              value={until}
              min={since}
              max={todayISO()}
              disabled={generating}
              onChange={(e) => setUntil(e.target.value)}
            />
          </div>
        )}

        {error && <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose} disabled={generating}>
            Cancel
          </Button>
          <Button onClick={confirm} disabled={generating}>
            <Sparkles className="h-4 w-4" />
            {generating ? "Analyzing…" : "Generate report"}
          </Button>
        </div>
      </div>
    </div>
  );
}
