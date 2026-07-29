import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { useAuth } from "@/context/AuthContext";

export function GoogleCallbackPage() {
  const { completeGoogleAuth } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [error, setError] = useState("");

  useEffect(() => {
    const token = params.get("token");
    // Drop the token from the address bar ASAP so it is less likely to linger in history.
    if (token) {
      window.history.replaceState({}, "", "/auth/google/callback");
    }
    if (!token) {
      setError("Missing sign-in token. Please try again.");
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        await completeGoogleAuth(token);
        if (!cancelled) navigate("/dashboard", { replace: true });
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Google sign-in failed");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [completeGoogleAuth, navigate, params]);

  return (
    <AuthLayout title="Signing you in" subtitle="Finishing Google sign-in…">
      {error ? (
        <div className="space-y-4">
          <p className="text-sm text-red-500">{error}</p>
          <Link to="/login" className="text-sm font-medium text-brand-600 hover:text-brand-700">
            Back to sign in
          </Link>
        </div>
      ) : (
        <div className="flex items-center gap-3 text-sm text-content-muted">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
          Please wait
        </div>
      )}
    </AuthLayout>
  );
}
