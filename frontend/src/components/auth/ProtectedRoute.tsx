import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { BrandLoader } from "@/components/ui/Loading";
import { rememberAuthReturn } from "@/lib/authReturn";
import type { ReactNode } from "react";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface-muted">
        <BrandLoader size="md" />
      </div>
    );
  }

  if (!isAuthenticated) {
    rememberAuthReturn(`${location.pathname}${location.search}${location.hash}`);
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}
