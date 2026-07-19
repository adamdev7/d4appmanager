import { useEffect, useState } from "react";
import { X, Eye, Pencil } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  PERSONALIZATION_FIELDS,
  insertField,
  previewWithSamples,
} from "@/lib/emailPersonalization";

export type TemplateData = {
  id: string;
  name: string;
  subject: string;
  body_html: string;
};

type Props = {
  open: boolean;
  onClose: () => void;
  template: TemplateData | null;
  automationTitle: string;
  storeName: string;
  initialTab?: "edit" | "preview";
  onSave: (data: { name: string; subject: string; body_html: string }) => Promise<void>;
};

export function TemplateEditorModal({
  open,
  onClose,
  template,
  automationTitle,
  storeName,
  initialTab = "edit",
  onSave,
}: Props) {
  const [tab, setTab] = useState<"edit" | "preview">(initialTab);
  const [name, setName] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (template) {
      setName(template.name);
      setSubject(template.subject);
      setBody(template.body_html);
      setTab(initialTab);
      setError("");
    }
  }, [template, initialTab]);

  if (!open || !template) return null;

  const previewSubject = previewWithSamples(subject, storeName);
  const previewBody = previewWithSamples(body, storeName);

  const handleSave = async () => {
    setSaving(true);
    setError("");
    try {
      await onSave({ name, subject, body_html: body });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setSaving(false);
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
                <p className="text-xs text-content-subtle mt-3">
                  Tip: use &quot;Add personalization&quot; on the message body. For the subject
                  line, type naturally or click fields after focusing the subject box.
                </p>
                <div className="flex flex-wrap gap-2 mt-2">
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
                <p className="text-sm font-medium text-content mt-1">{previewSubject || "(No subject)"}</p>
              </div>
              <div
                className="px-4 py-5 text-sm text-content prose prose-sm dark:prose-invert max-w-none"
                dangerouslySetInnerHTML={{
                  __html:
                    previewBody ||
                    '<p class="text-content-muted">Your message will appear here.</p>',
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
