import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuth } from "@/context/AuthContext";

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const { email: registeredEmail } = await register(email, password, fullName);
      navigate(`/verify-email?email=${encodeURIComponent(registeredEmail)}`, {
        state: { devHint: true },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout title="Create your account" subtitle="We'll email you a verification code">
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Full name"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          placeholder="Jane Smith"
          required
        />
        <Input
          label="Email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@company.com"
          required
        />
        <Input
          label="Password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          hint="At least 8 characters"
          minLength={8}
          required
        />
        {error && <p className="text-sm text-red-500">{error}</p>}
        <Button type="submit" className="w-full" size="lg" isLoading={loading}>
          Create account
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-content-muted">
        Already have an account?{" "}
        <Link to="/login" className="font-medium text-brand-600 hover:text-brand-700">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
