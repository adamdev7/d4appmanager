import { cn } from "@/lib/cn";

type BrandLogoProps = {
  className?: string;
  /** Visual size of the logo image */
  size?: "sm" | "md" | "lg" | "hero";
  /** Show wordmark text beside a compact mark (not used when full logo includes text) */
  showWordmark?: boolean;
  alt?: string;
};

const sizeClass = {
  sm: "h-8 w-8",
  md: "h-10 w-10",
  lg: "h-14 w-14",
  hero: "h-40 w-40 sm:h-52 sm:w-52",
} as const;

/**
 * Official App Manager brand mark.
 * Use the full square logo (emblem + APP MANAGER) on public/marketing surfaces.
 * Use compact crop sizes in chrome where space is tight.
 */
export function BrandLogo({
  className,
  size = "md",
  showWordmark = false,
  alt = "App Manager",
}: BrandLogoProps) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <img
        src="/app-manager-logo.png"
        alt={alt}
        className={cn(
          "object-contain shrink-0 rounded-lg",
          sizeClass[size],
          size === "hero" && "rounded-2xl"
        )}
      />
      {showWordmark && (
        <span className="font-semibold tracking-tight text-content">App Manager</span>
      )}
    </span>
  );
}
