import { useState } from "react";
import { Link } from "react-router-dom";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { api } from "@/lib/api";
import { CheckCircle } from "lucide-react";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await api.auth.forgotPassword(email);
    } catch {
      /* UI still shows success — no account enumeration in Phase 1 */
    }
    setSent(true);
    setLoading(false);
  };

  if (sent) {
    return (
      <AuthLayout title="Check your email" subtitle="We sent password reset instructions if an account exists.">
        <div className="text-center py-4">
          <CheckCircle className="h-12 w-12 text-brand-600 mx-auto mb-4" />
          <p className="text-sm text-content-muted mb-6">
            Didn&apos;t receive it? Check spam or try again with another email.
          </p>
          <Link to="/login">
            <Button variant="outline" className="w-full">
              Back to sign in
            </Button>
          </Link>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Reset your password"
      subtitle="Enter your email and we'll send you a reset link."
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@company.com"
          required
        />
        <Button type="submit" className="w-full" size="lg" isLoading={loading}>
          Send reset link
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-content-muted">
        <Link to="/login" className="font-medium text-brand-600 hover:text-brand-700">
          Back to sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
