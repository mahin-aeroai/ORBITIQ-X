/**
 * ORBITIQ-X — Mission Control Dashboard
 * =======================================
 * Primary operator interface: live RSO count, active conjunction alerts,
 * space weather status, agent activity feed, and the 3D orbital globe.
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

export const metadata: Metadata = {
  title: "Mission Control",
  description: "ORBITIQ-X real-time space situational awareness dashboard.",
};

// Dashboard revalidates every 30s (ISR) — live data pulled client-side
export const revalidate = 30;

export default function MissionControlPage() {
  return (
    <div className="flex h-full flex-col gap-0">

      {/* ── Top metrics bar ────────────────────────────────────────────── */}
      <DashboardMetricsBar />

      {/* ── Main content area ──────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── 3D Globe (2/3 width) ─────────────────────────────────────── */}
        <div className="relative flex-[2] overflow-hidden border-r border-space-border">
          <Suspense fallback={<GlobeSkeleton />}>
            <OrbitalGlobe
              defaultObjectTypes={["PAYLOAD", "DEBRIS"]}
              showConjunctions
              showGroundTracks
              autoRotate={false}
            />
          </Suspense>
        </div>

        {/* ── Right panel stack (1/3 width) ────────────────────────────── */}
        <div className="flex w-96 flex-col overflow-y-auto">

          {/* Space weather */}
          <div className="border-b border-space-border p-4">
            <Suspense fallback={<div className="h-24 animate-pulse rounded bg-space-surface" />}>
              <SpaceWeatherWidget compact />
            </Suspense>
          </div>

          {/* Conjunction alerts */}
          <div className="flex-1 border-b border-space-border">
            <div className="p-4">
              <h2 className="font-display text-sm font-semibold uppercase tracking-widest text-space-accent-amber">
                Active Conjunction Alerts
              </h2>
            </div>
            <Suspense fallback={<div className="space-y-2 px-4">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-16 animate-pulse rounded bg-space-surface" />
              ))}
            </div>}>
              <ConjunctionAlertPanel maxItems={8} />
            </Suspense>
          </div>

          {/* Agent activity */}
          <div className="flex-1">
            <div className="p-4">
              <h2 className="font-display text-sm font-semibold uppercase tracking-widest text-space-accent-indigo">
                Agent Activity
              </h2>
            </div>
            <AgentActivityFeed maxItems={5} />
          </div>
        </div>
      </div>

      {/* ── Bottom stats bar ───────────────────────────────────────────── */}
      <div className="grid grid-cols-4 divide-x divide-space-border border-t border-space-border">
        <CatalogStatsCard label="Tracked Objects" dataKey="total_rso_count" />
        <CatalogStatsCard label="Active Payloads" dataKey="active_payload_count" />
        <CatalogStatsCard label="Debris Objects" dataKey="debris_count" />
        <MissionStatusCard />
      </div>
    </div>
  );
}
