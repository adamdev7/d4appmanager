import { useCallback, useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { motion } from "framer-motion";
import { Sidebar } from "./Sidebar";
import { TopNavbar } from "./TopNavbar";
import { cn } from "@/lib/cn";

export function DashboardLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const closeMobile = useCallback(() => setMobileOpen(false), []);

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const onChange = () => {
      if (mq.matches) setMobileOpen(false);
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    if (!mobileOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMobileOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [mobileOpen]);

  useEffect(() => {
    if (!mobileOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [mobileOpen]);

  return (
    <div className="min-h-screen bg-surface-muted">
      <Sidebar
        collapsed={collapsed}
        onCollapsedChange={setCollapsed}
        mobileOpen={mobileOpen}
        onMobileClose={closeMobile}
      />

      {mobileOpen && (
        <button
          type="button"
          aria-label="Close navigation"
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-[1px] lg:hidden"
          onClick={closeMobile}
        />
      )}

      <div
        className={cn(
          "min-h-screen flex flex-col transition-[padding] duration-300",
          collapsed ? "lg:pl-[72px]" : "lg:pl-[var(--sidebar-width)]"
        )}
      >
        <TopNavbar
          mobileNavOpen={mobileOpen}
          onMobileNavToggle={() => setMobileOpen((open) => !open)}
        />
        <motion.main
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.25 }}
          className="flex-1 p-4 sm:p-6"
        >
          <Outlet />
        </motion.main>
      </div>
    </div>
  );
}
