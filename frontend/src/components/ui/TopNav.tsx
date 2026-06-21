"use client";
/**
 * ORBITIQ-X — TopNav
 * ====================
 * Mission control top navigation bar.
 * Shows: platform name, live UTC clock, system status pulse, settings.
 */

import { useEffect, useState } from "react";
import { useAuth } from "@/components/providers/AuthProvider";

function UTCClock() {
  const [time, setTime] = useState<string>("");

  useEffect(() => {
    const tick = () =>
      setTime(new Date().toISOString().replace("T", " ").slice(0, 19) + " UTC");
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <span className="font-mono text-xs tabular-nums text-space-muted">
      {time || "—"}
    </span>
  );
}

function UserBadge() {
  const { user, logout, isAuthenticated } = useAuth();
  if (!isAuthenticated || !user) return null;

  const ROLE_COLOR: Record<string, string> = {
    admin:    "var(--color-accent-red)",
    operator: "var(--color-accent-amber)",
    analyst:  "var(--color-accent-indigo-bright)",
    readonly: "var(--color-text-secondary)",
  };

  return (
    <div className="flex items-center gap-2">
      <span
        className="rounded border px-1.5 py-0.5 font-mono text-[8px] font-bold uppercase"
        style={{
          color:           ROLE_COLOR[user.role] ?? "var(--color-text-secondary)",
          borderColor:     ROLE_COLOR[user.role] ?? "var(--color-space-border)",
          backgroundColor: `${ROLE_COLOR[user.role] ?? "#94a3b8"}18`,
        }}
      >
        {user.role}
      </span>
      <span className="font-mono text-[10px] text-space-muted">{user.username}</span>
      <button
        onClick={() => logout()}
        className="rounded border border-space-border px-2 py-0.5 font-mono text-[9px] text-space-muted hover:border-[var(--color-accent-red)] hover:text-[var(--color-accent-red)]"
        title="Logout"
      >
        LOGOUT
      </button>
    </div>
  );
}

export function TopNav() {
  return (
    <header
      className="flex h-10 shrink-0 items-center justify-between border-b border-space-border bg-space-midnight px-4"
      role="banner"
    >
      {/* Left — platform identity */}
      <div className="flex items-center gap-3">
        {/* Status pulse */}
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--color-accent-green)] opacity-60" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--color-accent-green)]" />
        </span>
        <span className="font-display text-xs font-semibold uppercase tracking-[0.2em] text-space-text">
          ORBITIQ-X
        </span>
        <span className="text-[10px] text-space-muted">
          MISSION CONTROL
        </span>
      </div>

      {/* Right — user + clock + build tag */}
      <div className="flex items-center gap-4">
        <UTCClock />
        <UserBadge />
        <span className="rounded border border-space-border px-2 py-0.5 font-mono text-[10px] text-space-muted">
          v1.0.0
        </span>
      </div>
    </header>
  );
}
