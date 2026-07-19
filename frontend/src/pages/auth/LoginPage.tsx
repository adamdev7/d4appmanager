import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      navigate("/dashboard");
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        navigate(`/verify-email?email=${encodeURIComponent(email)}`);
        return;
      }
      setError(err instanceof Error ? err.message : "Unable to sign in");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout title="Welcome back" subtitle="Sign in to your App Manager account">
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
          Sign in
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
