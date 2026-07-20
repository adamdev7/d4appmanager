import { useEffect, useRef, useState } from "react";
import { X, Eye, Pencil, ImagePlus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  PERSONALIZATION_FIELDS,
  insertField,
  previewWithSamples,
} from "@/lib/emailPersonalization";
import {
  DEFAULT_THEME_COLOR,
  LAYOUT_PRESETS,
  type LayoutPresetId,
  renderEmailLayout,
} from "@/lib/emailLayouts";

export type TemplateData = {
  id: string;
  name: string;
  subject: string;
  body_html: string;
  layout_preset?: string;
};

export type BrandingData = {
  theme_color: string;
  logo_url: string | null;
};

type Props = {
  open: boolean;
  onClose: () => void;
  template: TemplateData | null;
  branding: BrandingData;
  automationTitle: string;
  storeName: string;
  initialTab?: "edit" | "preview";
  onSave: (data: {
    name: string;
    subject: string;
    body_html: string;
    layout_preset: string;
    theme_color: string;
  }) => Promise<void>;
  onUploadLogo: (file: File) => Promise<BrandingData>;
  onRemoveLogo: () => Promise<BrandingData>;
};

const THEME_SWATCHES = ["#0d9488", "#1d4ed8", "#b45309", "#be123c", "#166534", "#0f172a"];

export function TemplateEditorModal({
  open,
  onClose,
  template,
  branding,
  automationTitle,
  storeName,
  initialTab = "edit",
  onSave,
  onUploadLogo,
  onRemoveLogo,
}: Props) {
  const [tab, setTab] = useState<"edit" | "preview">(initialTab);
  const [name, setName] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [layout, setLayout] = useState<LayoutPresetId>("classic");
  const [themeColor, setThemeColor] = useState(DEFAULT_THEME_COLOR);
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [logoBusy, setLogoBusy] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (template) {
      setName(template.name);
      setSubject(template.subject);
      setBody(template.body_html);
      setLayout((template.layout_preset as LayoutPresetId) || "classic");
      setTab(initialTab);
      setError("");
    }
  }, [template, initialTab]);

  useEffect(() => {
    setThemeColor(branding.theme_color || DEFAULT_THEME_COLOR);
    setLogoUrl(branding.logo_url);
  }, [branding.theme_color, branding.logo_url]);

  if (!open || !template) return null;

  const previewSubject = previewWithSamples(subject, storeName);
  const previewInner = previewWithSamples(body, storeName);
  const previewHtml = renderEmailLayout({
    layoutPreset: layout,
    bodyHtml: previewInner,
    themeColor,
    logoUrl,
    storeName,
  });

  const handleSave = async () => {
    setSaving(true);
    setError("");
    try {
      await onSave({
        name,
        subject,
        body_html: body,
        layout_preset: layout,
        theme_color: themeColor,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setSaving(false);
    }
  };

  const handleLogoPick = async (file: File | null) => {
    if (!file) return;
    setLogoBusy(true);
    setError("");
    try {
      const next = await onUploadLogo(file);
      setLogoUrl(next.logo_url);
      if (next.theme_color) setThemeColor(next.theme_color);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not upload logo");
    } finally {
      setLogoBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleRemoveLogo = async () => {
    setLogoBusy(true);
    setError("");
    try {
      const next = await onRemoveLogo();
      setLogoUrl(next.logo_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove logo");
    } finally {
      setLogoBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-black/50 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="template-editor-title"
    >
      <div className="w-full max-w-2xl max-h-[95vh] sm:max-h-[90vh] flex flex-col rounded-t-2xl sm:rounded-2xl border border-border bg-surface shadow-xl">
        <div className="flex items-start justify-between gap-4 border-b border-border px-4 sm:px-6 py-4">
          <div>
            <h2 id="template-editor-title" className="text-lg font-semibold text-content">
              Customize email
            </h2>
            <p className="text-sm text-content-muted mt-0.5">{automationTitle}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-content-muted hover:bg-surface-muted hover:text-content"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex gap-1 px-4 sm:px-6 pt-3 border-b border-border">
          <button
            type="button"
            onClick={() => setTab("edit")}
            className={`flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-t-lg border-b-2 -mb-px transition-colors ${
              tab === "edit"
                ? "border-brand-600 text-brand-700 dark:text-brand-400"
                : "border-transparent text-content-muted hover:text-content"
            }`}
          >
            <Pencil className="h-3.5 w-3.5" />
            Edit
          </button>
          <button
            type="button"
            onClick={() => setTab("preview")}
            className={`flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-t-lg border-b-2 -mb-px transition-colors ${
              tab === "preview"
                ? "border-brand-600 text-brand-700 dark:text-brand-400"
                : "border-transparent text-content-muted hover:text-content"
            }`}
          >
            <Eye className="h-3.5 w-3.5" />
            Preview
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-5 space-y-5">
          {tab === "edit" ? (
            <>
              <div className="space-y-2">
                <p className="text-sm font-medium text-content">Template style</p>
                <p className="text-xs text-content-muted">
                  Pick one of three ready-made layouts for this email.
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  {LAYOUT_PRESETS.map((preset) => {
                    const selected = layout === preset.id;
                    return (
                      <button
                        key={preset.id}
                        type="button"
                        onClick={() => setLayout(preset.id)}
                        className={`text-left rounded-xl border p-3 transition-colors ${
                          selected
                            ? "border-brand-500 bg-brand-500/10 ring-1 ring-brand-500/40"
                            : "border-border hover:border-brand-500/40 hover:bg-surface-muted/60"
                        }`}
                      >
                        <div
                          className="h-10 rounded-md mb-2"
                          style={{
                            background:
                              preset.id === "modern"
                                ? `linear-gradient(${themeColor} 0 3px, #fff 3px)`
                                : preset.id === "bold"
                                  ? themeColor
                                  : `linear-gradient(${themeColor} 40%, #fff 40%)`,
                          }}
                        />
                        <p className="text-sm font-medium text-content">{preset.name}</p>
                        <p className="text-xs text-content-muted mt-0.5 leading-snug">
                          {preset.description}
                        </p>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="space-y-2">
                <p className="text-sm font-medium text-content">Store theme colour</p>
                <p className="text-xs text-content-muted">
                  Applies to all automated emails for this store.
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  {THEME_SWATCHES.map((c) => (
                    <button
                      key={c}
                      type="button"
                      title={c}
                      onClick={() => setThemeColor(c)}
                      className={`h-8 w-8 rounded-full border-2 transition-transform ${
                        themeColor.toLowerCase() === c
                          ? "border-content scale-110"
                          : "border-transparent hover:scale-105"
                      }`}
                      style={{ backgroundColor: c }}
                    />
                  ))}
                  <label className="inline-flex items-center gap-2 rounded-lg border border-border px-2.5 py-1.5 text-xs text-content-muted">
                    Custom
                    <input
                      type="color"
                      value={themeColor.length === 7 ? themeColor : DEFAULT_THEME_COLOR}
                      onChange={(e) => setThemeColor(e.target.value)}
                      className="h-6 w-8 cursor-pointer bg-transparent border-0 p-0"
                    />
                  </label>
                </div>
              </div>

              <div className="space-y-2">
                <p className="text-sm font-medium text-content">Store logo</p>
                <p className="text-xs text-content-muted">
                  Shown in the logo spot on every layout. Leave empty to hide it.
                </p>
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex h-16 w-28 items-center justify-center rounded-xl border border-dashed border-border bg-surface-muted/50 overflow-hidden">
                    {logoUrl ? (
                      <img src={logoUrl} alt="Store logo" className="max-h-14 max-w-[6.5rem] object-contain" />
                    ) : (
                      <span className="text-xs text-content-subtle px-2 text-center">No logo</span>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <input
                      ref={fileRef}
                      type="file"
                      accept="image/png,image/jpeg,image/webp,image/gif"
                      className="hidden"
                      onChange={(e) => handleLogoPick(e.target.files?.[0] ?? null)}
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={logoBusy}
                      onClick={() => fileRef.current?.click()}
                    >
                      <ImagePlus className="h-4 w-4 mr-1.5" />
                      {logoUrl ? "Replace logo" : "Add logo"}
                    </Button>
                    {logoUrl && (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={logoBusy}
                        onClick={handleRemoveLogo}
                      >
                        <Trash2 className="h-4 w-4 mr-1.5" />
                        Remove
                      </Button>
                    )}
                  </div>
                </div>
              </div>

              <Input
                label="Template name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                hint="Internal name so you can recognize this email"
              />
              <Input
                label="Email subject"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="e.g. Your order is on the way"
              />
              <div className="space-y-1.5">
                <label className="block text-sm font-medium text-content">Message</label>
                <textarea
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  rows={8}
                  className="flex w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-content placeholder:text-content-subtle focus:outline-none focus:ring-2 focus:ring-brand-500/30 focus:border-brand-500"
                  placeholder="Write your email message here..."
                />
              </div>
              <div className="rounded-xl bg-surface-muted/80 border border-border p-4">
                <p className="text-sm font-medium text-content mb-2">Add personalization</p>
                <p className="text-xs text-content-muted mb-3">
                  Click a field to insert it where it belongs in your message. Customers will see
                  their real details automatically.
                </p>
                <div className="flex flex-wrap gap-2">
                  {PERSONALIZATION_FIELDS.map((field) => (
                    <button
                      key={field.key}
                      type="button"
                      onClick={() => setBody(insertField(body, field.key))}
                      className="inline-flex items-center rounded-full border border-border bg-surface px-3 py-1.5 text-xs font-medium text-content hover:border-brand-500/50 hover:bg-brand-500/5 transition-colors"
                    >
                      + {field.label}
                    </button>
                  ))}
                </div>
                <div className="flex flex-wrap gap-2 mt-3">
                  {PERSONALIZATION_FIELDS.map((field) => (
                    <button
                      key={`sub-${field.key}`}
                      type="button"
                      onClick={() => setSubject(insertField(subject, field.key))}
                      className="inline-flex items-center rounded-full border border-dashed border-border px-2.5 py-1 text-xs text-content-muted hover:text-content hover:border-brand-500/40"
                    >
                      Subject: {field.label}
                    </button>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <div className="rounded-xl border border-border overflow-hidden">
              <div className="bg-surface-muted px-4 py-3 border-b border-border">
                <p className="text-xs text-content-muted uppercase tracking-wide">Sample preview</p>
                <p className="text-sm font-medium text-content mt-1">
                  {previewSubject || "(No subject)"}
                </p>
              </div>
              <div
                className="bg-[#f8fafc] dark:bg-zinc-900"
                dangerouslySetInnerHTML={{
                  __html:
                    previewHtml ||
                    '<p class="text-content-muted p-4">Your message will appear here.</p>',
                }}
              />
            </div>
          )}
          {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        </div>

        <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2 border-t border-border px-4 sm:px-6 py-4">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSave} isLoading={saving}>
            Save changes
          </Button>
        </div>
      </div>
    </div>
  );
}
