import { Link } from "react-router-dom";
import { Layers } from "lucide-react";
import type { ReactNode } from "react";
import { SiteFooter } from "./SiteFooter";

export function LegalLayout({
  title,
  lastUpdated,
  children,
}: {
  title: string;
  lastUpdated: string;
  children: ReactNode;
}) {
  return (
    <div className="min-h-screen bg-surface-muted flex flex-col">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-6 py-4">
          <Link to="/login" className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 text-white">
              <Layers className="h-5 w-5" />
            </div>
            <span className="font-semibold tracking-tight text-content">App Manager</span>
          </Link>
          <Link
            to="/login"
            className="text-sm font-medium text-brand-600 hover:text-brand-700"
          >
            Sign in
          </Link>
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-3xl px-6 py-10 sm:py-14">
        <h1 className="text-3xl font-bold tracking-tight text-content">{title}</h1>
        <p className="mt-2 text-sm text-content-muted">Last updated: {lastUpdated}</p>
        <div className="mt-10 space-y-8 text-content-muted leading-relaxed [&_h2]:text-lg [&_h2]:font-semibold [&_h2]:text-content [&_h2]:mt-0 [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:space-y-1.5 [&_a]:text-brand-600 [&_a]:hover:text-brand-700">
          {children}
        </div>
        <SiteFooter className="mt-14" variant="legal" />
      </main>
    </div>
  );
}
