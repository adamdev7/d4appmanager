import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  hover?: boolean;
  padding?: "none" | "sm" | "md" | "lg";
}

const paddingMap = {
  none: "",
  sm: "p-4",
  md: "p-5",
  lg: "p-6",
};

export function Card({ children, className, hover, padding = "md", ...props }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-surface shadow-card transition-all duration-200",
        paddingMap[padding],
        hover && "hover:shadow-elevated hover:border-border-strong cursor-pointer",
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("mb-4", className)}>{children}</div>;
}

export function CardTitle({ children, className }: { children: ReactNode; className?: string }) {
  return <h3 className={cn("text-base font-semibold text-content", className)}>{children}</h3>;
}

export function CardDescription({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <p className={cn("text-sm text-content-muted mt-0.5", className)}>{children}</p>;
}
