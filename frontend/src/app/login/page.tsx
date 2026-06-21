"use client";
/**
 * ORBITIQ-X — Login Page
 * ========================
 * Mission Control authentication screen.
 * Matches the established deep-space design language.
 *
 * useSearchParams() requires a Suspense boundary in Next.js 14 App Router.
 * The inner LoginForm component reads search params; the outer export
 * wraps it in Suspense so SSG prerendering succeeds.
 */

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/providers/AuthProvider";

function LoginForm() {
  const { login } = useAuth();
  const router       = useRouter();
  const searchParams = useSearchParams();
  const nextPath     = searchParams.get("next") ?? "/";

  const [usernameOrEmail, setUsernameOrEmail] = useState("");
  const [password,        setPassword]        = useState("");
  const [error,           setError]           = useState<string | null>(null);
  const [loading,         setLoading]         = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await login(usernameOrEmail.trim(), password);
      // Redirect back to the originally requested page (or dashboard)
      router.replace(nextPath.startsWith("/") ? nextPath : "/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="flex min-h-screen items-center justify-center bg-space-midnight"
      style={{ fontFamily: "var(--font-body)" }}
    >
      {/* Background grid pattern */}
      <div
        className="pointer-events-none fixed inset-0 opacity-[0.03]"
        style={{
          backgroundImage: "linear-gradient(var(--color-space-border) 1px, transparent 1px), linear-gradient(90deg, var(--color-space-border) 1px, transparent 1px)",
          backgroundSize:  "40px 40px",
        }}
      />

      <div className="relative z-10 w-full max-w-sm px-4">
        {/* Header */}
        <div className="mb-8 text-center">
          <div className="mb-2 flex items-center justify-center gap-2">
            <span className="relative flex h-3 w-3">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--color-accent-green)] opacity-60" />
              <span className="relative inline-flex h-3 w-3 rounded-full bg-[var(--color-accent-green)]" />
            </span>
            <span
              className="font-display text-lg font-bold uppercase tracking-[0.3em]"
              style={{ color: "var(--color-text-primary)" }}
            >
              ORBITIQ-X
            </span>
          </div>
          <p
            className="font-mono text-[10px] uppercase tracking-widest"
            style={{ color: "var(--color-text-secondary)" }}
          >
            MISSION CONTROL — AEROSPACE INTELLIGENCE PLATFORM
          </p>
        </div>

        {/* Login card */}
        <div
          className="rounded-lg border p-6"
          style={{
            backgroundColor: "var(--color-space-navy)",
            borderColor:     "var(--color-space-border)",
            boxShadow:       "var(--shadow-panel)",
          }}
        >
          <div className="mb-5">
            <h1
              className="font-display text-base font-semibold"
              style={{ color: "var(--color-text-primary)" }}
            >
              Operator Authentication
            </h1>
            <p className="mt-0.5 font-mono text-[10px]" style={{ color: "var(--color-text-secondary)" }}>
              Enter your credentials to access the platform
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Username / Email */}
            <div>
              <label
                htmlFor="username"
                className="mb-1 block font-mono text-[9px] uppercase tracking-wider"
                style={{ color: "var(--color-text-secondary)" }}
              >
                Username or Email
              </label>
              <input
                id="username"
                type="text"
                autoComplete="username"
                required
                value={usernameOrEmail}
                onChange={(e) => setUsernameOrEmail(e.target.value)}
                className="w-full rounded border px-3 py-2 font-mono text-[11px] outline-none transition-colors"
                style={{
                  backgroundColor: "var(--color-space-surface)",
                  borderColor:     "var(--color-space-border)",
                  color:           "var(--color-text-primary)",
                }}
                onFocus={(e) => (e.target.style.borderColor = "var(--color-accent-indigo)")}
                onBlur ={(e) => (e.target.style.borderColor = "var(--color-space-border)")}
                placeholder="operator@orbitiq.dev"
              />
            </div>

            {/* Password */}
            <div>
              <label
                htmlFor="password"
                className="mb-1 block font-mono text-[9px] uppercase tracking-wider"
                style={{ color: "var(--color-text-secondary)" }}
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded border px-3 py-2 font-mono text-[11px] outline-none transition-colors"
                style={{
                  backgroundColor: "var(--color-space-surface)",
                  borderColor:     "var(--color-space-border)",
                  color:           "var(--color-text-primary)",
                }}
                onFocus={(e) => (e.target.style.borderColor = "var(--color-accent-indigo)")}
                onBlur ={(e) => (e.target.style.borderColor = "var(--color-space-border)")}
                placeholder="••••••••••••"
              />
            </div>

            {/* Error */}
            {error && (
              <div
                className="rounded border px-3 py-2 font-mono text-[10px]"
                style={{
                  backgroundColor: "var(--color-accent-red-glow)",
                  borderColor:     "var(--color-accent-red)",
                  color:           "var(--color-accent-red-bright)",
                }}
              >
                ⚠ {error}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded border py-2.5 font-mono text-[11px] font-semibold uppercase tracking-wider transition-all"
              style={{
                backgroundColor: loading
                  ? "var(--color-space-surface)"
                  : "var(--color-accent-indigo-glow)",
                borderColor:  "var(--color-accent-indigo)",
                color:        loading
                  ? "var(--color-text-tertiary)"
                  : "var(--color-accent-indigo-bright)",
                cursor: loading ? "not-allowed" : "pointer",
              }}
            >
              {loading ? "AUTHENTICATING…" : "ACCESS MISSION CONTROL"}
            </button>
          </form>
        </div>

        {/* Footer */}
        <p
          className="mt-4 text-center font-mono text-[9px]"
          style={{ color: "var(--color-text-tertiary)" }}
        >
          ORBITIQ-X v1.0 · SECURE PLATFORM · ALL ACCESS LOGGED
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={
      <div className="flex min-h-screen items-center justify-center bg-space-midnight">
        <span className="section-label">LOADING…</span>
      </div>
    }>
      <LoginForm />
    </Suspense>
  );
}
