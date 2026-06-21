"use client";
/**
 * ORBITIQ-X — TopNav
 * ====================
 * Mission control top navigation bar.
 * Shows: platform name, live UTC clock, system status pulse, settings.
 */

import { useEffect, useState } from "react";

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

      {/* Right — clock + build tag */}
      <div className="flex items-center gap-4">
        <UTCClock />
        <span className="rounded border border-space-border px-2 py-0.5 font-mono text-[10px] text-space-muted">
          v1.0.0
        </span>
      </div>
    </header>
  );
}
