import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { Layers } from "lucide-react";
import type { ReactNode } from "react";

export function AuthLayout({
  children,
  title,
  subtitle,
}: {
  children: ReactNode;
  title: string;
  subtitle?: string;
}) {
  return (
    <div className="min-h-screen flex">
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden bg-gradient-to-br from-brand-900 via-brand-800 to-slate-900">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-brand-500/20 via-transparent to-transparent" />
        <div className="relative z-10 flex flex-col justify-between p-12 text-white">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/10 backdrop-blur">
              <Layers className="h-5 w-5" />
            </div>
            <span className="text-lg font-semibold tracking-tight">App Manager</span>
          </Link>
          <div className="max-w-md">
            <h2 className="text-3xl font-bold tracking-tight leading-tight">
              Automate your Shopify stores from one place
            </h2>
            <p className="mt-4 text-brand-100/80 text-lg leading-relaxed">
              Email flows, order tracking, and multi-store management — built for scale.
            </p>
          </div>
          <p className="text-sm text-brand-200/60">© {new Date().getFullYear()} App Manager</p>
        </div>
        <div className="absolute -bottom-32 -right-32 h-96 w-96 rounded-full bg-brand-500/10 blur-3xl" />
      </div>

      <div className="flex flex-1 flex-col justify-center px-6 py-12 lg:px-16 bg-surface-muted">
        <div className="lg:hidden mb-8 flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 text-white">
            <Layers className="h-5 w-5" />
          </div>
          <span className="font-semibold text-content">App Manager</span>
        </div>
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
          className="mx-auto w-full max-w-md"
        >
          <div className="mb-8">
            <h1 className="text-2xl font-bold tracking-tight text-content">{title}</h1>
            {subtitle && <p className="mt-2 text-content-muted">{subtitle}</p>}
          </div>
          <div className="rounded-2xl border border-border bg-surface p-8 shadow-card">{children}</div>
        </motion.div>
      </div>
    </div>
  );
}
