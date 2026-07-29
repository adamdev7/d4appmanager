import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api, type AuthUser } from "@/lib/api";

export type LoginResult =
  | { status: "authenticated" }
  | { status: "requires_2fa"; email: string }
  | { status: "requires_verification"; email: string };

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<LoginResult>;
  register: (email: string, password: string, fullName: string) => Promise<{ email: string }>;
  verifyEmail: (email: string, code: string) => Promise<void>;
  verifyLogin: (email: string, code: string) => Promise<void>;
  resendVerification: (email: string) => Promise<void>;
  resendLoginCode: (email: string) => Promise<void>;
  completeGoogleAuth: (token: string) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function persistSession(token: string, user: AuthUser) {
  localStorage.setItem("access_token", token);
  localStorage.setItem("user", JSON.stringify(user));
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadMe = useCallback(async () => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      setUser(null);
      setIsLoading(false);
      return;
    }
    try {
      const me = await api.auth.me();
      setUser(me);
      localStorage.setItem("user", JSON.stringify(me));
    } catch {
      localStorage.removeItem("access_token");
      localStorage.removeItem("user");
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMe();
  }, [loadMe]);

  const login = useCallback(async (email: string, password: string): Promise<LoginResult> => {
    const res = await api.auth.login(email, password);
    if (res.requires_verification) {
      return { status: "requires_verification", email: res.email || email };
    }
    if (res.requires_2fa) {
      return { status: "requires_2fa", email: res.email || email };
    }
    if (res.access_token && res.user) {
      persistSession(res.access_token, res.user);
      setUser(res.user);
      return { status: "authenticated" };
    }
    throw new Error(res.message || "Unable to sign in");
  }, []);

  const register = useCallback(async (email: string, password: string, fullName: string) => {
    const res = await api.auth.register(email, password, fullName);
    return { email: res.email };
  }, []);

  const verifyEmail = useCallback(async (email: string, code: string) => {
    const res = await api.auth.verifyEmail(email, code);
    persistSession(res.access_token, res.user);
    setUser(res.user);
  }, []);

  const verifyLogin = useCallback(async (email: string, code: string) => {
    const res = await api.auth.verifyLogin(email, code);
    persistSession(res.access_token, res.user);
    setUser(res.user);
  }, []);

  const resendVerification = useCallback(async (email: string) => {
    await api.auth.resendVerification(email);
  }, []);

  const resendLoginCode = useCallback(async (email: string) => {
    await api.auth.resendLoginCode(email);
  }, []);

  const completeGoogleAuth = useCallback(async (token: string) => {
    localStorage.setItem("access_token", token);
    const me = await api.auth.me();
    persistSession(token, me);
    setUser(me);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user");
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        login,
        register,
        verifyEmail,
        verifyLogin,
        resendVerification,
        resendLoginCode,
        completeGoogleAuth,
        logout,
        isAuthenticated: !!user?.is_verified,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
