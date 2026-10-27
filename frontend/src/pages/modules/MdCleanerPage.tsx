import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Download,
  Eraser,
  ImagePlus,
  ScanSearch,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  XCircle,
} from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { createZip } from "@/lib/zip";
import type {
  MdCheck,
  MdCleanResult,
  MdFinding,
  MdOutputFormat,
  MdScanReport,
  MdSeverity,
  MdVerdict,
} from "@/lib/mdCleanerTypes";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Loading";

const MAX_BYTES = 32 * 1024 * 1024;
const CONCURRENCY = 2;
const ACCEPT = "image/*,.heic,.heif,.avif,.jfif,.tif,.tiff";

const FORMATS: Array<{ id: MdOutputFormat; label: string; hint: string }> = [
  { id: "auto", label: "Auto", hint: "Keeps PNG as PNG, everything else becomes JPG" },
  { id: "jpeg", label: "JPG", hint: "Smallest files, best for Meta feed ads" },
  { id: "png", label: "PNG", hint: "Lossless, keeps transparency" },
];

type Mode = "clean" | "check";

type Item = {
  id: string;
  file: File;
  mode: Mode;
  format: MdOutputFormat;
  status: "queued" | "working" | "done" | "error";
  result?: Omit<MdCleanResult, "data_base64">;
  report?: MdScanReport;
  url?: string;
  blob?: Blob;
  error?: string;
  open: boolean;
};

const SEVERITY_DOT: Record<MdSeverity, string> = {
  critical: "bg-red-500",
  high: "bg-amber-500",
  medium: "bg-slate-400",
  low: "bg-slate-300 dark:bg-slate-600",
};

const VERDICT_COPY: Record<MdVerdict, { title: string; body: string; tone: "bad" | "warn" | "ok" }> = {
  ai_labeled: {
    title: "Meta will likely add an “AI info” label",
    body: "This file carries the industry AI markers Meta reads on upload.",
    tone: "bad",
  },
  ai_traces: {
    title: "AI traces found",
    body: "No official AI label marker, but the file names the tool or holds the prompt.",
    tone: "warn",
  },
  metadata: {
    title: "No AI markers, some metadata",
    body: "Nothing that triggers Meta's AI label, but the file still carries extra data.",
    tone: "warn",
  },
  clean: {
    title: "Nothing found — this file is clean",
    body: "No metadata, AI markers, or hidden extras.",
    tone: "ok",
  },
};

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function newId() {
  return Math.random().toString(36).slice(2, 10);
}

function downloadBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

export function MdCleanerPage() {
  const [items, setItems] = useState<Item[]>([]);
  const [format, setFormat] = useState<MdOutputFormat>("auto");
  const [dragging, setDragging] = useState(false);
  const [zipping, setZipping] = useState(false);
  const cleanInput = useRef<HTMLInputElement>(null);
  const checkInput = useRef<HTMLInputElement>(null);
  const started = useRef(new Set<string>());
  const urls = useRef(new Set<string>());

  const patch = useCallback((id: string, update: Partial<Item>) => {
    setItems((prev) => prev.map((item) => (item.id === id ? { ...item, ...update } : item)));
  }, []);

  const run = useCallback(
    async (item: Item) => {
      try {
        if (item.mode === "check") {
          const report = await api.mdCleaner.scan(item.file);
          patch(item.id, { status: "done", report });
          return;
        }
        const { data_base64, ...result } = await api.mdCleaner.clean(item.file, item.format);
        const blob = await (await fetch(`data:${result.mime};base64,${data_base64}`)).blob();
        const url = URL.createObjectURL(blob);
        urls.current.add(url);
        patch(item.id, { status: "done", result, blob, url });
      } catch (err) {
        patch(item.id, {
          status: "error",
          error: err instanceof Error ? err.message : "Something went wrong. Try again.",
        });
      }
    },
    [patch]
  );

  useEffect(() => {
    const working = items.filter((i) => i.status === "working").length;
    const slots = CONCURRENCY - working;
    if (slots <= 0) return;
    const next = items.filter((i) => i.status === "queued" && !started.current.has(i.id)).slice(0, slots);
    for (const item of next) {
      started.current.add(item.id);
      patch(item.id, { status: "working" });
      void run(item);
    }
  }, [items, patch, run]);

  useEffect(() => {
    const owned = urls.current;
    return () => owned.forEach((url) => URL.revokeObjectURL(url));
  }, []);

  const enqueue = useCallback(
    (files: FileList | File[] | null, mode: Mode) => {
      if (!files) return;
      const added: Item[] = Array.from(files).map((file) => {
        const tooBig = file.size > MAX_BYTES;
        return {
          id: newId(),
          file,
          mode,
          format,
          status: tooBig ? "error" : "queued",
          error: tooBig ? "Over 32 MB — export a smaller copy first." : undefined,
          open: false,
        };
      });
      if (added.length) setItems((prev) => [...added, ...prev]);
    },
    [format]
  );

  const cleanFromCheck = (item: Item) => {
    patch(item.id, { mode: "clean", status: "queued", report: undefined, format, open: false });
    started.current.delete(item.id);
  };

  const remove = (item: Item) => {
    if (item.url) {
      URL.revokeObjectURL(item.url);
      urls.current.delete(item.url);
    }
    setItems((prev) => prev.filter((i) => i.id !== item.id));
  };

  const clearAll = () => {
    urls.current.forEach((url) => URL.revokeObjectURL(url));
    urls.current.clear();
    started.current.clear();
    setItems([]);
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    enqueue(e.dataTransfer.files, "clean");
  };

  const cleaned = useMemo(
    () => items.filter((i) => i.mode === "clean" && i.status === "done" && i.blob && i.result),
    [items]
  );
  const busy = items.some((i) => i.status === "queued" || i.status === "working");
  const signalsRemoved = cleaned.reduce((sum, i) => sum + (i.result?.meta_signals_removed ?? 0), 0);

  const downloadAll = async () => {
    if (!cleaned.length) return;
    if (cleaned.length === 1) {
      downloadBlob(cleaned[0].blob!, cleaned[0].result!.filename);
      return;
    }
    setZipping(true);
    try {
      const zip = await createZip(cleaned.map((i) => ({ name: i.result!.filename, blob: i.blob! })));
      downloadBlob(zip, `pictures-${new Date().toISOString().slice(0, 10)}.zip`);
    } finally {
      setZipping(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2">
          <Eraser className="h-5 w-5 text-brand-600" />
          <h1 className="text-2xl font-semibold text-content tracking-tight">MD Cleaner</h1>
        </div>
        <p className="mt-1 text-sm text-content-muted max-w-2xl">
          Drop AI-made pictures here. We strip every metadata trace Meta reads on upload, rescan the
          result, and only hand back files that pass.
        </p>
      </div>

      <Card padding="lg" className="space-y-4">
        <button
          type="button"
          onClick={() => cleanInput.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cn(
            "flex w-full flex-col items-center gap-2 rounded-xl border-2 border-dashed px-4 py-10 text-center transition-colors",
            dragging
              ? "border-brand-500 bg-brand-500/10"
              : "border-border bg-surface-muted/40 hover:border-brand-500/50 hover:bg-brand-500/5"
          )}
        >
          <ImagePlus className="h-7 w-7 text-brand-600" />
          <span className="text-base font-medium text-content">
            Drop pictures here or click to choose
          </span>
          <span className="text-xs text-content-subtle">
            JPG, PNG, WebP, HEIC, AVIF, GIF, TIFF · up to 32 MB each · nothing is stored
          </span>
        </button>
        <input
          ref={cleanInput}
          type="file"
          accept={ACCEPT}
          multiple
          className="hidden"
          onChange={(e) => {
            enqueue(e.target.files, "clean");
            e.target.value = "";
          }}
        />
        <input
          ref={checkInput}
          type="file"
          accept={ACCEPT}
          multiple
          className="hidden"
          onChange={(e) => {
            enqueue(e.target.files, "check");
            e.target.value = "";
          }}
        />

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-content-muted">Save as</span>
            <div className="inline-flex rounded-lg border border-border p-0.5">
              {FORMATS.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  title={f.hint}
                  onClick={() => setFormat(f.id)}
                  className={cn(
                    "rounded-md px-3 py-1 text-xs font-medium transition-colors",
                    format === f.id
                      ? "bg-brand-600 text-white"
                      : "text-content-muted hover:text-content"
                  )}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>
          <button
            type="button"
            onClick={() => checkInput.current?.click()}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-brand-700 hover:underline dark:text-brand-400"
          >
            <ScanSearch className="h-3.5 w-3.5" />
            Only check a picture (no changes)
          </button>
        </div>
      </Card>

      {items.length > 0 && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-content-muted">
              {cleaned.length > 0 ? (
                <>
                  <span className="font-medium text-content">{cleaned.length}</span> cleaned
                  {signalsRemoved > 0 && (
                    <>
                      {" · "}
                      <span className="font-medium text-content">{signalsRemoved}</span> Meta AI
                      marker{signalsRemoved === 1 ? "" : "s"} removed
                    </>
                  )}
                </>
              ) : busy ? (
                "Working…"
              ) : (
                "Results"
              )}
            </p>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={clearAll}
                disabled={busy}
              >
                <Trash2 className="h-3.5 w-3.5" />
                Clear
              </Button>
              <Button
                type="button"
                size="sm"
                onClick={() => void downloadAll()}
                disabled={!cleaned.length || zipping}
                isLoading={zipping}
              >
                <Download className="h-3.5 w-3.5" />
                {cleaned.length > 1 ? `Download all (${cleaned.length})` : "Download"}
              </Button>
            </div>
          </div>

          <ul className="space-y-2">
            {items.map((item) => (
              <li key={item.id}>
                <ItemRow
                  item={item}
                  onToggle={() => patch(item.id, { open: !item.open })}
                  onRemove={() => remove(item)}
                  onClean={() => cleanFromCheck(item)}
                />
              </li>
            ))}
          </ul>
        </div>
      )}

      <Card padding="md" className="space-y-3">
        <div className="grid gap-4 sm:grid-cols-3">
          <Explainer
            title="AI labels Meta reads"
            body="Content Credentials (C2PA) and the IPTC “AI-generated” source tag — the two markers Meta uses for its AI info label."
          />
          <Explainer
            title="Tool names & prompts"
            body="EXIF, XMP, IPTC, PNG text chunks, Stable Diffusion / ComfyUI / Midjourney settings, and comments."
          />
          <Explainer
            title="Hidden extras"
            body="Thumbnails, appended images, color-profile text, prompts hidden in transparency, and AI-looking file names."
          />
        </div>
        <p className="border-t border-border pt-3 text-xs text-content-subtle">
          Only file metadata is removed — the picture itself stays visually identical (colors are
          converted to sRGB and rotation is applied so nothing shifts). Invisible pixel watermarks
          such as Google SynthID are not metadata and are not touched. Political and social-issue
          ads still need Meta's AI disclosure in Ads Manager.
        </p>
      </Card>
    </div>
  );
}

function Explainer({ title, body }: { title: string; body: string }) {
  return (
    <div>
      <p className="text-sm font-medium text-content">{title}</p>
      <p className="mt-0.5 text-xs text-content-muted">{body}</p>
    </div>
  );
}

function ItemRow({
  item,
  onToggle,
  onRemove,
  onClean,
}: {
  item: Item;
  onToggle: () => void;
  onRemove: () => void;
  onClean: () => void;
}) {
  const { result, report } = item;
  const done = item.status === "done";
  const expandable = done && (result || report);

  return (
    <Card padding="none" className="overflow-hidden">
      <div className="flex items-center gap-3 px-4 py-3">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-border bg-surface-muted">
          {item.url ? (
            <img src={item.url} alt="" className="h-full w-full object-cover" />
          ) : item.status === "error" ? (
            <XCircle className="h-5 w-5 text-red-500" />
          ) : done ? (
            <ScanSearch className="h-5 w-5 text-content-subtle" />
          ) : (
            <Spinner className="text-brand-600" />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-medium text-content">
              {result ? result.filename : item.file.name}
            </p>
            <StatusBadge item={item} />
          </div>
          <p className="mt-0.5 truncate text-xs text-content-muted">
            {item.status === "error" && <span className="text-red-600 dark:text-red-400">{item.error}</span>}
            {(item.status === "queued" || item.status === "working") &&
              (item.mode === "check" ? "Scanning…" : "Cleaning and rescanning…")}
            {result && <CleanSummary result={result} original={item.file} />}
            {report && VERDICT_COPY[report.verdict].body}
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-1">
          {result && item.url && (
            <a
              href={item.url}
              download={result.filename}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-brand-600 px-3 text-xs font-medium text-white shadow-sm hover:bg-brand-700"
            >
              <Download className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Download</span>
            </a>
          )}
          {report && report.verdict !== "clean" && (
            <Button type="button" size="sm" onClick={onClean}>
              <Eraser className="h-3.5 w-3.5" />
              Clean it
            </Button>
          )}
          {expandable && (
            <button
              type="button"
              onClick={onToggle}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-content-subtle hover:bg-surface-muted hover:text-content"
              aria-label={item.open ? "Hide details" : "Show details"}
            >
              <ChevronDown className={cn("h-4 w-4 transition-transform", item.open && "rotate-180")} />
            </button>
          )}
          {item.status !== "working" && (
            <button
              type="button"
              onClick={onRemove}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-content-subtle hover:bg-surface-muted hover:text-content"
              aria-label="Remove"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {expandable && item.open && (
        <div className="border-t border-border bg-surface-muted/30 px-4 py-4">
          {result && <CleanDetails result={result} />}
          {report && <CheckDetails report={report} />}
        </div>
      )}
    </Card>
  );
}

function StatusBadge({ item }: { item: Item }) {
  if (item.status === "error") return <Badge variant="warning">Failed</Badge>;
  if (item.status !== "done") return <Badge variant="muted">{item.status === "queued" ? "Waiting" : "Working"}</Badge>;
  if (item.result) {
    return (
      <Badge variant="success">
        <ShieldCheck className="mr-1 h-3 w-3" />
        Meta check passed
      </Badge>
    );
  }
  if (item.report) {
    const tone = VERDICT_COPY[item.report.verdict].tone;
    return (
      <Badge variant={tone === "ok" ? "success" : "warning"}>
        {tone === "bad" && <ShieldAlert className="mr-1 h-3 w-3" />}
        {VERDICT_COPY[item.report.verdict].title}
      </Badge>
    );
  }
  return null;
}

function CleanSummary({ result, original }: { result: Omit<MdCleanResult, "data_base64">; original: File }) {
  const parts: string[] = [];
  if (result.removed_count === 0) {
    parts.push("Nothing found — rebuilt anyway");
  } else {
    parts.push(`Removed ${result.removed_count} item${result.removed_count === 1 ? "" : "s"}`);
    if (result.meta_signals_removed > 0) {
      parts.push(
        `${result.meta_signals_removed} Meta AI marker${result.meta_signals_removed === 1 ? "" : "s"}`
      );
    }
  }
  parts.push(result.fidelity.label);
  parts.push(`${formatBytes(original.size)} → ${formatBytes(result.size_bytes)}`);
  return <>{parts.join(" · ")}</>;
}

function CleanDetails({ result }: { result: Omit<MdCleanResult, "data_base64"> }) {
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-content-subtle">
          Found in the original
        </p>
        <FindingList findings={result.removed} empty="No metadata was found in the upload." />
      </div>
      <div className="space-y-4">
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-content-subtle">
            Rescan of the cleaned file
          </p>
          <CheckList checks={result.after.checks} />
          <p className="mt-2 text-xs text-content-subtle">
            {result.width}×{result.height} {result.format.toUpperCase()}
            {result.fidelity.psnr_db ? ` · ${result.fidelity.psnr_db} dB match` : ""}
            {result.passes > 1 ? ` · passed on attempt ${result.passes}` : ""}
          </p>
        </div>
        {result.notes.length > 0 && (
          <ul className="space-y-1">
            {result.notes.map((note) => (
              <li key={note} className="flex gap-2 text-xs text-content-muted">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
                {note}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function CheckDetails({ report }: { report: MdScanReport }) {
  const copy = VERDICT_COPY[report.verdict];
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-content-subtle">
          What's in this file
        </p>
        <FindingList findings={report.findings} empty={copy.body} />
      </div>
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-content-subtle">
          Meta-style check
        </p>
        <CheckList checks={report.checks} />
      </div>
    </div>
  );
}

function FindingList({ findings, empty }: { findings: MdFinding[]; empty: string }) {
  if (!findings.length) return <p className="text-xs text-content-muted">{empty}</p>;
  return (
    <ul className="space-y-2">
      {findings.map((f, i) => (
        <li key={`${f.code}-${f.location}-${i}`} className="flex gap-2.5">
          <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", SEVERITY_DOT[f.severity])} />
          <div className="min-w-0">
            <p className="text-sm text-content">
              {f.label}
              {f.meta_signal && (
                <span className="ml-1.5 rounded bg-red-500/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-red-600 dark:text-red-400">
                  Meta reads this
                </span>
              )}
            </p>
            <p className="break-words text-xs text-content-muted">{f.detail}</p>
            <p className="text-[11px] text-content-subtle">{f.location}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

function CheckList({ checks }: { checks: MdCheck[] }) {
  return (
    <ul className="space-y-1.5">
      {checks.map((c) => (
        <li key={c.id} className="flex items-center gap-2 text-sm">
          {c.passed ? (
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
          ) : (
            <XCircle className="h-4 w-4 shrink-0 text-red-500" />
          )}
          <span className={c.passed ? "text-content" : "text-red-700 dark:text-red-300"}>{c.label}</span>
          {!c.passed && <span className="text-xs text-content-subtle">({c.count})</span>}
        </li>
      ))}
    </ul>
  );
}
