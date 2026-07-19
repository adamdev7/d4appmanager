import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { TopNavbar } from "./TopNavbar";
import { motion } from "framer-motion";

export function DashboardLayout() {
  return (
    <div className="min-h-screen bg-surface-muted">
      <Sidebar />
      <div className="pl-[var(--sidebar-width)] transition-[padding] duration-300 min-h-screen flex flex-col">
        <TopNavbar />
        <motion.main
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.25 }}
          className="flex-1 p-6"
        >
          <Outlet />
        </motion.main>
      </div>
    </div>
  );
}
