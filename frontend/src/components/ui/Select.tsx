import { forwardRef, type SelectHTMLAttributes } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/cn";

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  hint?: string;
  error?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, label, hint, error, id, children, ...props }, ref) => {
    const selectId = id ?? label?.toLowerCase().replace(/\s/g, "-");
    return (
      <div className="space-y-1.5 min-w-0">
        {label && (
          <label htmlFor={selectId} className="block text-sm font-medium text-content">
            {label}
          </label>
        )}
        <div className="relative">
          <select
            ref={ref}
            id={selectId}
            className={cn(
              "flex h-10 w-full appearance-none rounded-lg border border-border bg-surface pl-3 pr-9 text-sm text-content transition-colors",
              "focus:outline-none focus:ring-2 focus:ring-brand-500/30 focus:border-brand-500",
              "disabled:cursor-not-allowed disabled:opacity-50",
              error && "border-red-500 focus:ring-red-500/30",
              className
            )}
            {...props}
          >
            {children}
          </select>
          <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-content-subtle" />
        </div>
        {error && <p className="text-xs text-red-500">{error}</p>}
        {hint && !error && <p className="text-xs text-content-subtle">{hint}</p>}
      </div>
    );
  }
);
Select.displayName = "Select";
