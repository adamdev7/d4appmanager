import { cn } from "@/lib/cn";

interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
  description?: string;
  disabled?: boolean;
}

export function Switch({ checked, onChange, label, description, disabled }: SwitchProps) {
  return (
    <label
      className={cn(
        "flex items-start justify-between gap-4 cursor-pointer",
        disabled && "opacity-50 cursor-not-allowed"
      )}
    >
      {(label || description) && (
        <div className="flex-1">
          {label && <span className="text-sm font-medium text-content block">{label}</span>}
          {description && (
            <span className="text-xs text-content-muted mt-0.5 block">{description}</span>
          )}
        </div>
      )}
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => !disabled && onChange(!checked)}
        className={cn(
          "relative inline-flex h-6 w-11 shrink-0 rounded-full border-2 border-transparent transition-colors duration-200",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40",
          checked ? "bg-brand-600" : "bg-border-strong"
        )}
      >
        <span
          className={cn(
            "pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow transform transition-transform duration-200",
            checked ? "translate-x-5" : "translate-x-0"
          )}
        />
      </button>
    </label>
  );
}
