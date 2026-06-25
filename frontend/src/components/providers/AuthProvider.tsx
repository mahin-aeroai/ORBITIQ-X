"use client";
/**
 * ORBITIQ-X — AuthProvider
 * ==========================
 * React context that manages:
 *   • Access token (in-memory only — never localStorage)
 *   • User profile + role
 *   • Silent token refresh (before expiry)
 *   • Login / logout actions
 *
 * Security design
 * ────────────────
 * Access tokens are stored in React state (memory) only.
 * Refresh tokens are stored in HttpOnly cookies set by the Next.js API route
 * to prevent XSS access. The Next.js /api/auth/refresh route handles rotation.
 *
 * Role hierarchy
 * ──────────────
 * admin > operator > analyst > readonly (viewer)
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { setApiAccessToken } from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────

export type UserRole = "admin" | "operator" | "analyst" | "readonly";

export interface AuthUser {
  id:           number;
  email:        string;
  username:     string;
  full_name:    string | null;
  organization: string | null;
  role:         UserRole;
  is_active:    boolean;
  last_login_at:string | null;
  created_at:   string;
}

interface AuthState {
  user:         AuthUser | null;
  accessToken:  string | null;
  isLoading:    boolean;
  isAuthenticated: boolean;
}

interface AuthContextValue extends AuthState {
  login:         (usernameOrEmail: string, password: string) => Promise<void>;
  logout:        () => Promise<void>;
  refreshTokens: () => Promise<boolean>;
  hasRole:       (role: UserRole) => boolean;
  hasMinRole:    (minRole: UserRole) => boolean;
}

// ─── Role hierarchy ───────────────────────────────────────────────────────────

const ROLE_LEVEL: Record<UserRole, number> = {
  admin:    4,
  operator: 3,
  analyst:  2,
  readonly: 1,
};

// ─── Context ──────────────────────────────────────────────────────────────────

const AuthContext = createContext<AuthContextValue | null>(null);

// ─── API base ────────────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const AUTH_URL = `${API_BASE}/api/v1/auth`;

// ─── Provider ────────────────────────────────────────────────────────────────

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user:            null,
    accessToken:     null,
    isLoading:       true,
    isAuthenticated: false,
  });

  // Refresh timer ref — cleared on logout
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Token refresh ────────────────────────────────────────────────────────

  const refreshTokens = useCallback(async (): Promise<boolean> => {
    try {
      // Refresh token is stored in HttpOnly cookie via Next.js API route
      const res = await fetch("/api/auth/refresh", { method: "POST" });
      if (!res.ok) return false;

      const data = await res.json();
      const { access_token, user, expires_in } = data;

      setApiAccessToken(access_token);
      setState({
        user:            user,
        accessToken:     access_token,
        isLoading:       false,
        isAuthenticated: true,
      });

      // Schedule next refresh 60 seconds before expiry
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
      const msUntilRefresh = Math.max(0, (expires_in - 60) * 1000);
      refreshTimerRef.current = setTimeout(refreshTokens, msUntilRefresh);

      return true;
    } catch {
      return false;
    }
  }, []);

  // ── Boot: attempt silent refresh on mount ────────────────────────────────

  useEffect(() => {
    refreshTokens().then((ok) => {
      if (!ok) {
        setState((s) => ({ ...s, isLoading: false }));
      }
    });

    return () => {
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Login ────────────────────────────────────────────────────────────────

  const login = useCallback(
    async (usernameOrEmail: string, password: string): Promise<void> => {
      const res = await fetch(`${AUTH_URL}/login`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({
          username_or_email: usernameOrEmail,
          password,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? "Login failed. Check your credentials.");
      }

      const data = await res.json();
      const { access_token, refresh_token, user, expires_in } = data;

      // Store refresh token in HttpOnly cookie via Next.js API route
      await fetch("/api/auth/set-cookie", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ refresh_token }),
      });

      setApiAccessToken(access_token);
      setState({
        user,
        accessToken:     access_token,
        isLoading:       false,
        isAuthenticated: true,
      });

      // Schedule silent refresh
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
      const msUntilRefresh = Math.max(0, (expires_in - 60) * 1000);
      refreshTimerRef.current = setTimeout(refreshTokens, msUntilRefresh);
    },
    [refreshTokens],
  );

  // ── Logout ───────────────────────────────────────────────────────────────

  const logout = useCallback(async (): Promise<void> => {
    // Revoke refresh token server-side
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch { /* best-effort */ }

    // Clear refresh timer
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);

    setApiAccessToken(null);
    setState({
      user:            null,
      accessToken:     null,
      isLoading:       false,
      isAuthenticated: false,
    });
  }, []);

  // ── Role checks ──────────────────────────────────────────────────────────

  const hasRole = useCallback(
    (role: UserRole): boolean => state.user?.role === role,
    [state.user],
  );

  const hasMinRole = useCallback(
    (minRole: UserRole): boolean => {
      if (!state.user) return false;
      return (ROLE_LEVEL[state.user.role] ?? 0) >= (ROLE_LEVEL[minRole] ?? 99);
    },
    [state.user],
  );

  return (
    <AuthContext.Provider
      value={{ ...state, login, logout, refreshTokens, hasRole, hasMinRole }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return ctx;
}

// ─── Role guard hook ──────────────────────────────────────────────────────────

export function useRequireAuth(minRole?: UserRole): AuthContextValue & { ready: boolean } {
  const auth = useAuth();
  const ready = !auth.isLoading;

  if (ready && !auth.isAuthenticated) {
    // Trigger redirect via side-effect in the component
  }

  if (ready && auth.isAuthenticated && minRole && !auth.hasMinRole(minRole)) {
    // Role insufficient
  }

  return { ...auth, ready };
}
