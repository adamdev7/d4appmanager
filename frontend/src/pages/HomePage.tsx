import { Link, Navigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Mail, Package, BarChart3, Sparkles, ArrowRight } from "lucide-react";
import { BrandLogo } from "@/components/brand/BrandLogo";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { useAuth } from "@/context/AuthContext";

const features = [
  {
    icon: Sparkles,
    title: "AI Email Assistant",
    body: "Connect Gmail so App Manager can read customer threads, draft replies with AI, and send responses you approve.",
  },
  {
    icon: Mail,
    title: "Email Automation",
    body: "Send order and fulfillment emails from your connected Gmail accounts when Shopify events fire.",
  },
  {
    icon: Package,
    title: "Order Tracking",
    body: "Centralize shipment tracking and share branded tracking pages with your customers.",
  },
  {
    icon: BarChart3,
    title: "Analytics & Ads",
    body: "See store profitability and Meta ads performance in one workspace across multiple Shopify stores.",
  },
];

/**
 * Public application home page for https://appmanager.store
 * Written to satisfy Google OAuth branding verification:
 * - Exact app name "App Manager"
 * - Clear purpose / functionality (not login-only)
 * - Privacy Policy (+ Terms) links matching consent screen URLs
 */
export function HomePage() {
  const { isAuthenticated, isLoading } = useAuth();

  if (!isLoading && isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <div className="min-h-screen flex flex-col bg-[#050505] text-white">
      <header className="border-b border-white/10">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-6 py-4">
          <Link to="/" className="flex items-center gap-3" aria-label="App Manager home">
            <BrandLogo size="sm" />
            <span className="text-sm font-semibold tracking-wide uppercase">
              <span className="text-[#9FE870]">App</span>{" "}
              <span className="text-white">Manager</span>
            </span>
          </Link>
          <nav className="flex items-center gap-3 sm:gap-4 text-sm">
            <Link to="/privacy" className="text-white/60 hover:text-white transition-colors">
              Privacy Policy
            </Link>
            <Link to="/terms" className="hidden sm:inline text-white/60 hover:text-white transition-colors">
              Terms of Service
            </Link>
            <Link
              to="/login"
              className="rounded-lg bg-[#9FE870] px-3.5 py-2 font-semibold text-black hover:bg-[#b4f08c] transition-colors"
            >
              Sign in
            </Link>
          </nav>
        </div>
      </header>

      <main className="flex-1">
        <section className="relative overflow-hidden">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(159,232,112,0.12),_transparent_55%)]" />
          <div className="relative mx-auto max-w-5xl px-6 pt-16 pb-20 sm:pt-24 sm:pb-28 text-center">
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.45 }}
              className="flex flex-col items-center"
            >
              <BrandLogo size="hero" className="mb-8" />
              <h1 className="text-4xl sm:text-5xl font-bold tracking-tight uppercase">
                <span className="text-[#9FE870]">App</span>{" "}
                <span className="text-white">Manager</span>
              </h1>
              <p className="mt-3 text-xs sm:text-sm tracking-[0.28em] uppercase text-white/70">
                Power your business
              </p>
              <p className="mt-8 max-w-2xl text-base sm:text-lg text-white/75 leading-relaxed">
                App Manager is a multi-store Shopify automation platform. It helps ecommerce
                teams run email flows through Gmail, reply to customers with AI assistance,
                track shipments, and review analytics and Meta ads — all from one place.
              </p>
              <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
                <Link
                  to="/register"
                  className="inline-flex items-center gap-2 rounded-lg bg-[#9FE870] px-5 py-3 text-sm font-semibold text-black hover:bg-[#b4f08c] transition-colors"
                >
                  Get started
                  <ArrowRight className="h-4 w-4" />
                </Link>
                <Link
                  to="/login"
                  className="inline-flex items-center rounded-lg border border-white/20 px-5 py-3 text-sm font-semibold text-white hover:bg-white/5 transition-colors"
                >
                  Sign in to App Manager
                </Link>
              </div>
            </motion.div>
          </div>
        </section>

        <section className="border-t border-white/10 bg-white/[0.02]">
          <div className="mx-auto max-w-5xl px-6 py-16 sm:py-20">
            <h2 className="text-2xl font-bold tracking-tight text-center">
              What App Manager does
            </h2>
            <p className="mt-3 text-center text-white/65 max-w-2xl mx-auto leading-relaxed">
              App Manager connects to the tools you already use — including Shopify and
              Google Gmail — so you can automate store operations without switching between
              dashboards.
            </p>

            <div className="mt-12 grid gap-10 sm:grid-cols-2">
              {features.map((f) => (
                <div key={f.title} className="flex gap-4">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[#9FE870]/15 text-[#9FE870]">
                    <f.icon className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-white">{f.title}</h3>
                    <p className="mt-1.5 text-sm text-white/65 leading-relaxed">{f.body}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="border-t border-white/10">
          <div className="mx-auto max-w-5xl px-6 py-16 sm:py-20">
            <h2 className="text-2xl font-bold tracking-tight">
              Why App Manager uses Google account access
            </h2>
            <p className="mt-4 max-w-3xl text-white/70 leading-relaxed">
              When you connect Gmail inside App Manager, Google asks you to authorize access
              so we can send and manage business email on your behalf. App Manager uses that
              access only to operate Email Automation and the AI Email Assistant for stores
              you connect — for example reading relevant threads, drafting replies, marking
              messages as handled, and sending mail you configure. You can disconnect Gmail
              at any time from Settings.
            </p>
            <p className="mt-4 max-w-3xl text-white/70 leading-relaxed">
              How we access, use, store, and share Google user data is described in our{" "}
              <Link to="/privacy" className="text-[#9FE870] hover:underline">
                Privacy Policy
              </Link>
              . Use of App Manager is also governed by our{" "}
              <Link to="/terms" className="text-[#9FE870] hover:underline">
                Terms of Service
              </Link>
              .
            </p>
          </div>
        </section>
      </main>

      <div className="border-t border-white/10 px-6 py-6">
        <div className="mx-auto max-w-5xl">
          <SiteFooter variant="home" />
        </div>
      </div>
    </div>
  );
}
