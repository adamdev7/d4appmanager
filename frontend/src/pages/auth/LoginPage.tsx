import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { AuthDivider, GoogleAuthButton } from "@/components/auth/GoogleAuthButton";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuth } from "@/context/AuthContext";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const oauthError = searchParams.get("error");
    if (oauthError) setError(oauthError);
  }, [searchParams]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await login(email, password);
      if (result.status === "requires_2fa") {
        navigate(
          `/verify-email?email=${encodeURIComponent(result.email)}&purpose=login`
        );
        return;
      }
      if (result.status === "requires_verification") {
        navigate(
          `/verify-email?email=${encodeURIComponent(result.email)}&purpose=register`
        );
        return;
      }
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to sign in");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      title="Welcome back"
      subtitle="Sign in with Google, or use your password and email code."
    >
      <GoogleAuthButton label="Continue with Google" />
      <AuthDivider />
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@company.com"
          required
        />
        <div>
          <Input
            label="Password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <div className="mt-2 text-right">
            <Link
              to="/forgot-password"
              className="text-sm text-brand-600 hover:text-brand-700 font-medium"
            >
              Forgot password?
            </Link>
          </div>
        </div>
        {error && <p className="text-sm text-red-500">{error}</p>}
        <Button type="submit" className="w-full" size="lg" isLoading={loading}>
          Continue
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-content-muted">
        Don&apos;t have an account?{" "}
        <Link to="/register" className="font-medium text-brand-600 hover:text-brand-700">
          Create account
        </Link>
      </p>
    </AuthLayout>
  );
}
