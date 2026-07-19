import { useEffect, useRef, useState } from "react";
import { MoreVertical, Pencil, Eye } from "lucide-react";

type Props = {
  onEdit: () => void;
  onPreview: () => void;
};

export function RuleActionsMenu({ onEdit, onPreview }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="rounded-lg p-2 text-content-muted hover:bg-surface-muted hover:text-content transition-colors"
        aria-label="More actions"
      >
        <MoreVertical className="h-5 w-5" />
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 z-20 min-w-[180px] rounded-xl border border-border bg-surface py-1 shadow-lg">
          <button
            type="button"
            className="flex w-full items-center gap-2 px-3 py-2 text-sm text-content hover:bg-surface-muted"
            onClick={() => {
              setOpen(false);
              onEdit();
            }}
          >
            <Pencil className="h-4 w-4 text-content-muted" />
            Edit email
          </button>
          <button
            type="button"
            className="flex w-full items-center gap-2 px-3 py-2 text-sm text-content hover:bg-surface-muted"
            onClick={() => {
              setOpen(false);
              onPreview();
            }}
          >
            <Eye className="h-4 w-4 text-content-muted" />
            Preview email
          </button>
        </div>
      )}
    </div>
  );
}
