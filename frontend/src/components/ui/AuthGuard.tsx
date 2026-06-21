"use client";
/**
 * ORBITIQ-X — AuthGuard
 * ======================
 * Client-side auth wrapper for dashboard pages.
 * Redirects unauthenticated users to /login while the session loads.
 *
 * The middleware.ts handles server-side cookie presence check.
 * AuthGuard handles the client-side case (e.g. cookie present but
 * access token expired before silent refresh completes).
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth, type UserRole } from "@/components/providers/AuthProvider";

interface AuthGuardProps {
  children:  React.ReactNode;
  minRole?:  UserRole;
}

export function AuthGuard({ children, minRole }: AuthGuardProps) {
  const { isLoading, isAuthenticated, hasMinRole } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (isLoading) return;

    if (!isAuthenticated) {
      const next = typeof window !== "undefined" ? window.location.pathname : "/";
      router.replace(`/login?next=${encodeURIComponent(next)}`);
      return;
    }

    if (minRole && !hasMinRole(minRole)) {
      // Authenticated but insufficient role — redirect to dashboard root
      router.replace("/");
    }
  }, [isLoading, isAuthenticated, minRole, hasMinRole, router]);

  // Show nothing while loading or if redirect is pending
  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center bg-space-midnight">
        <div className="text-center">
          <div className="mx-auto mb-2 h-1 w-40 overflow-hidden rounded-full bg-space-surface">
            <div className="h-full w-2/3 animate-pulse rounded-full bg-[var(--color-accent-indigo)]" />
          </div>
          <span className="section-label">AUTHENTICATING</span>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) return null;
  if (minRole && !hasMinRole(minRole)) return null;

  return <>{children}</>;
}
