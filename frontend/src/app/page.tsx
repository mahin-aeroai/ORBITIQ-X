/**
 * ORBITIQ-X — Mission Control Dashboard (v0.4.0)
 * ===============================================
 * Redesigned for maximum aerospace intelligence impact.
 * Layout: full-bleed globe + live telemetry column + status footer.
 */
import { Suspense } from "react";
import type { Metadata } from "next";

import { OrbitalGlobe } from "@/components/orbital/OrbitalGlobe";
import { ConjunctionAlertPanel } from "@/components/ssa/ConjunctionAlertPanel";
import { SpaceWeatherWidget } from "@/components/ssa/SpaceWeatherWidget";
import { CatalogStatsCard } from "@/components/orbital/CatalogStatsCard";
import { AgentActivityFeed } from "@/components/agents/AgentActivityFeed";
import { MissionStatusCard } from "@/components/mission/MissionStatusCard";
import { GlobeSkeleton } from "@/components/ui/skeletons/GlobeSkeleton";
import { DashboardMetricsBar } from "@/components/ui/DashboardMetricsBar";
import { SystemHealthStrip } from "@/components/ui/SystemHealthStrip";

export const metadata: Metadata = {
  title: "Mission Control",
  description: "ORBITIQ-X real-time space situational awareness dashboard.",
};

export const revalidate = 30;

export default function MissionControlPage() {
  return (
    <div className="flex h-full flex-col gap-0 bg-[var(--color-space-deep)]">

      {/* ── Top metrics bar ────────────────────────────────────────────── */}
      <DashboardMetricsBar />

      {/* ── Main content area ──────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── 3D Globe (fills available space) ─────────────────────────── */}
        <div className="relative flex-1 overflow-hidden">
          {/* Scan-line overlay for CRT mission control aesthetic */}
          <div
            className="pointer-events-none absolute inset-0 z-10"
            style={{
              background: "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.03) 2px, rgba(0,0,0,0.03) 4px)",
            }}
            aria-hidden="true"
          />
          {/* Corner coordinates overlay */}
          <div className="pointer-events-none absolute bottom-4 left-4 z-20 font-mono text-[9px] text-[var(--color-text-tertiary)]" aria-hidden="true">
            <span>28°32′N  80°39′W · KSC</span>
          </div>
          <div className="pointer-events-none absolute bottom-4 right-4 z-20 font-mono text-[9px] text-[var(--color-text-tertiary)]" aria-hidden="true">
            <span>J2000 · TEME · UTC</span>
          </div>
          {/* Live indicator */}
          <div className="pointer-events-none absolute left-4 top-4 z-20 flex items-center gap-1.5" aria-hidden="true">
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-accent-green-bright)]" />
            <span className="font-mono text-[9px] tracking-widest text-[var(--color-accent-green-bright)]">LIVE</span>
          </div>
          <Suspense fallback={<GlobeSkeleton />}>
            <OrbitalGlobe
              defaultObjectTypes={["PAYLOAD", "DEBRIS"]}
              showConjunctions
              showGroundTracks
              autoRotate={false}
            />
          </Suspense>
        </div>

        {/* ── Right intelligence column ─────────────────────────────────── */}
        <aside
          className="flex w-80 shrink-0 flex-col border-l border-[var(--color-space-border)] bg-[var(--color-space-midnight)]"
          aria-label="Intelligence panel"
        >

          {/* Space weather — always visible, compact */}
          <section className="border-b border-[var(--color-space-border)] p-4">
            <Suspense fallback={<WeatherSkeleton />}>
              <SpaceWeatherWidget compact />
            </Suspense>
          </section>

          {/* Conjunction alerts — scrollable */}
          <section className="flex min-h-0 flex-1 flex-col border-b border-[var(--color-space-border)]">
            <header className="flex items-center justify-between px-4 pt-3 pb-2">
              <span className="font-mono text-[9px] font-semibold tracking-[0.15em] text-[var(--color-accent-amber)]">
                ⚠ CONJUNCTION ALERTS
              </span>
              <span className="font-mono text-[8px] text-[var(--color-text-tertiary)]">
                Pc ≥ 1e–5
              </span>
            </header>
            <div className="min-h-0 flex-1 overflow-y-auto">
              <Suspense fallback={<PanelSkeleton rows={5} />}>
                <ConjunctionAlertPanel maxItems={10} />
              </Suspense>
            </div>
          </section>

          {/* Agent activity — bottom */}
          <section className="flex min-h-0 flex-1 flex-col">
            <header className="flex items-center justify-between px-4 pt-3 pb-2">
              <span className="font-mono text-[9px] font-semibold tracking-[0.15em] text-[var(--color-accent-indigo-bright)]">
                ◎ AGENT ACTIVITY
              </span>
              <span className="font-mono text-[8px] text-[var(--color-text-tertiary)]">
                7 SPECIALISTS
              </span>
            </header>
            <div className="min-h-0 flex-1 overflow-y-auto">
              <AgentActivityFeed maxItems={5} />
            </div>
          </section>
        </aside>
      </div>

      {/* ── Bottom telemetry bar ───────────────────────────────────────── */}
      <footer className="grid shrink-0 grid-cols-5 divide-x divide-[var(--color-space-border)] border-t border-[var(--color-space-border)] bg-[var(--color-space-midnight)]">
        <CatalogStatsCard label="Tracked Objects" dataKey="total_rso_count" />
        <CatalogStatsCard label="Active Payloads" dataKey="active_payload_count" />
        <CatalogStatsCard label="Debris Objects"  dataKey="debris_count" />
        <CatalogStatsCard label="Rocket Bodies"   dataKey="rocket_body_count" />
        <MissionStatusCard />
      </footer>
    </div>
  );
}

// ─── Skeleton helpers ─────────────────────────────────────────────────────────

function WeatherSkeleton() {
  return (
    <div className="space-y-2">
      <div className="h-3 w-24 animate-pulse rounded bg-[var(--color-space-surface)]" />
      <div className="h-8 w-16 animate-pulse rounded bg-[var(--color-space-surface)]" />
      <div className="h-1.5 w-full animate-pulse rounded-full bg-[var(--color-space-surface)]" />
      <div className="flex gap-1">
        {[1,2,3].map(i => <div key={i} className="h-5 w-10 animate-pulse rounded bg-[var(--color-space-surface)]" />)}
      </div>
    </div>
  );
}

function PanelSkeleton({ rows }: { rows: number }) {
  return (
    <div className="space-y-1 px-4 py-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-14 animate-pulse rounded bg-[var(--color-space-surface)]" />
      ))}
    </div>
  );
}
