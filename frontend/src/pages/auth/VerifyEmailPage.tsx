import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuth } from "@/context/AuthContext";

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { verifyEmail, verifyLogin, resendVerification, resendLoginCode } = useAuth();
  const purpose = params.get("purpose") === "login" ? "login" : "register";
  const [email, setEmail] = useState(params.get("email") ?? "");
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [resendLoading, setResendLoading] = useState(false);
  const [error, setError] = useState("");
  const [resent, setResent] = useState(false);

  const isLogin2fa = purpose === "login";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (isLogin2fa) {
        await verifyLogin(email, code);
      } else {
        await verifyEmail(email, code);
      }
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed");
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    setResendLoading(true);
    setError("");
    try {
      if (isLogin2fa) {
        await resendLoginCode(email);
      } else {
        await resendVerification(email);
      }
      setResent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not resend code");
    } finally {
      setResendLoading(false);
    }
  };

  return (
    <AuthLayout
      title={isLogin2fa ? "Check your email" : "Verify your email"}
      subtitle={
        isLogin2fa
          ? "Enter the 6-digit sign-in code we just sent to finish logging in."
          : "Enter the 6-digit code we sent to your inbox."
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <Input
          label={isLogin2fa ? "Sign-in code" : "Verification code"}
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
          placeholder="123456"
          inputMode="numeric"
          autoComplete="one-time-code"
          required
        />
        {error && <p className="text-sm text-red-500">{error}</p>}
        {resent && (
          <p className="text-sm text-brand-600">A new code was sent. Check your email.</p>
        )}
        <Button type="submit" className="w-full" size="lg" isLoading={loading}>
          {isLogin2fa ? "Verify and sign in" : "Verify and continue"}
        </Button>
      </form>
      <div className="mt-4 flex flex-col gap-2 text-center text-sm">
        <button
          type="button"
          onClick={handleResend}
          disabled={resendLoading || !email}
          className="text-brand-600 hover:text-brand-700 font-medium disabled:opacity-50"
        >
          {resendLoading ? "Sending…" : "Resend code"}
        </button>
        <Link to="/login" className="text-content-muted hover:text-content">
          Back to sign in
        </Link>
      </div>
      <div className="mt-4 rounded-lg border border-border bg-surface-muted px-3 py-2 text-xs text-content-muted">
        <p className="font-medium text-content mb-1">Didn&apos;t get the email?</p>
        <ul className="list-disc list-inside space-y-0.5">
          <li>Check spam / promotions</li>
          <li>
            Click <strong>Resend code</strong> above
          </li>
          <li>
            With the API running, check the <strong>App Manager API</strong> terminal window —
            the code is printed there when <code className="text-[10px]">DEBUG=true</code>
          </li>
        </ul>
      </div>
    </AuthLayout>
  );
}
