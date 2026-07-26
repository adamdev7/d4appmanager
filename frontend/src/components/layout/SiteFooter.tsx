import { Link } from "react-router-dom";
import { cn } from "@/lib/cn";

export function SiteFooter({
  className,
  variant = "default",
}: {
  className?: string;
  variant?: "default" | "auth" | "legal";
}) {
  const year = new Date().getFullYear();
  const isAuth = variant === "auth";

  return (
    <footer
      className={cn(
        "flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between text-sm",
        isAuth ? "text-brand-200/60" : "text-content-subtle border-t border-border pt-6",
        className
      )}
    >
      <p>© {year} App Manager · D4TECH</p>
      <nav className="flex items-center gap-4">
        <Link
          to="/privacy"
          className={cn(
            "transition-colors",
            isAuth
              ? "hover:text-brand-100"
              : "text-content-muted hover:text-brand-600"
          )}
        >
          Privacy Policy
        </Link>
        <Link
          to="/terms"
          className={cn(
            "transition-colors",
            isAuth
              ? "hover:text-brand-100"
              : "text-content-muted hover:text-brand-600"
          )}
        >
          Terms of Service
        </Link>
      </nav>
    </footer>
  );
}
