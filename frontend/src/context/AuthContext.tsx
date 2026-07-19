import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api, ApiError, type AuthUser } from "@/lib/api";

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string) => Promise<{ email: string }>;
  verifyEmail: (email: string, code: string) => Promise<void>;
  resendVerification: (email: string) => Promise<void>;
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

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.auth.login(email, password);
    persistSession(res.access_token, res.user);
    setUser(res.user);
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

  const resendVerification = useCallback(async (email: string) => {
    await api.auth.resendVerification(email);
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
        resendVerification,
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
