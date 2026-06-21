"use client";
/**
 * ORBITIQ-X — OrbitalGlobe
 * ==========================
 * Phase 13C: Production-grade Mission Control Cesium globe.
 *
 * Architecture
 * ─────────────
 * The Cesium Viewer is wrapped in next/dynamic (ssr:false) because it requires
 * the browser DOM and WebGL context. The <OrbitalGlobe> export is a thin shell
 * that dynamic-imports <GlobeInner> and shows a loading skeleton while Cesium
 * initialises.
 *
 * Performance strategy for 50K+ objects
 * ───────────────────────────────────────
 * • PointPrimitiveCollection  — GPU-instanced points; O(1) draw call regardless
 *   of object count. No entity overhead.
 * • requestRenderMode: true   — Cesium only re-renders when state changes.
 * • Refresh: update existing point positions/colours in place every 30 s.
 *   Never destroy and recreate the collection or viewer.
 * • Conjunction markers: separate Entity per CDM (count is always small ≤100).
 *
 * Data sources (verified against actual backend source)
 * ─────────────────────────────────────────────────────
 * Satellites : GET /api/v1/digital-twin/cesium/states?limit=10000
 * Detail     : GET /api/v1/digital-twin/state/{norad_id}
 * Conjunctions: GET /api/v1/ssa/conjunctions/high-risk?limit=50
 */

import dynamic from "next/dynamic";
import { GlobeSkeleton } from "@/components/ui/skeletons/GlobeSkeleton";

// ─── Props ────────────────────────────────────────────────────────────────────

export interface OrbitalGlobeProps {
  defaultObjectTypes?: string[];
  showConjunctions?:   boolean;
  showGroundTracks?:   boolean;
  autoRotate?:         boolean;
}

// ─── Dynamic import — Cesium requires DOM/WebGL; never SSR ───────────────────

const GlobeInner = dynamic(
  () => import("./OrbitalGlobeInner").then((m) => ({ default: m.OrbitalGlobeInner })),
  {
    ssr:     false,
    loading: () => <GlobeSkeleton />,
  },
);

// ─── Public export ────────────────────────────────────────────────────────────

export function OrbitalGlobe(props: OrbitalGlobeProps) {
  return (
    <div className="relative h-full w-full overflow-hidden bg-space-midnight">
      <GlobeInner {...props} />
    </div>
  );
}
