"use client";
/**
 * ORBITIQ-X — OrbitalGlobe (STUB)
 * =================================
 * Phase 13C target. CesiumJS/Resium 3D orbital globe.
 *
 * Phase 13B: render a placeholder that matches the panel dimensions
 * and doesn't block the build. Full implementation in Phase 13C.
 *
 * Props mirrored from page.tsx usage:
 *   defaultObjectTypes  — object type filter
 *   showConjunctions    — overlay conjunction events
 *   showGroundTracks    — show ground track lines
 *   autoRotate          — globe auto-rotation
 */

interface OrbitalGlobeProps {
  defaultObjectTypes?: string[];
  showConjunctions?:   boolean;
  showGroundTracks?:   boolean;
  autoRotate?:         boolean;
}

export function OrbitalGlobe({
  defaultObjectTypes = [],
  showConjunctions   = false,
  showGroundTracks   = false,
  autoRotate         = false,
}: OrbitalGlobeProps) {
  return (
    <div className="globe-scanlines relative flex h-full w-full flex-col items-center justify-center bg-space-midnight">
      {/* Animated orbital rings */}
      <div className="relative h-72 w-72">
        <div className="absolute inset-0 flex items-center justify-center">
          <div
            className="h-72 w-72 rounded-full border border-[var(--color-accent-indigo-dim)] opacity-30"
            style={{ animation: "spin 30s linear infinite" }}
          />
        </div>
        <div className="absolute inset-4 flex items-center justify-center">
          <div
            className="h-64 w-64 rounded-full border border-[var(--color-accent-indigo-dim)] opacity-20"
            style={{ animation: "spin 20s linear infinite reverse" }}
          />
        </div>
        <div className="absolute inset-8 flex items-center justify-center">
          <div
            className="h-56 w-56 rounded-full border border-[var(--color-space-border-strong)] opacity-40"
          />
        </div>
        {/* Earth placeholder */}
        <div className="absolute inset-0 flex items-center justify-center">
          <div
            className="h-32 w-32 rounded-full"
            style={{
              background: "radial-gradient(circle at 35% 35%, #1a4a8a, #0a1a3a 70%, #050810)",
              boxShadow: "0 0 40px rgba(99,102,241,0.2), inset 0 0 20px rgba(0,0,0,0.5)",
            }}
          />
        </div>
      </div>

      <div className="mt-4 text-center">
        <div className="section-label mb-1">ORBITAL GLOBE</div>
        <div className="font-mono text-[10px] text-space-muted">
          Phase 13C — CesiumJS integration pending
        </div>
        <div className="mt-1 font-mono text-[9px] text-[var(--color-text-tertiary)]">
          {defaultObjectTypes.length > 0 && `Tracking: ${defaultObjectTypes.join(", ")}`}
        </div>
      </div>

      {/* Overlay legend */}
      <div className="absolute bottom-4 left-4 space-y-1">
        {showConjunctions && (
          <div className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-[var(--color-accent-amber)]" />
            <span className="font-mono text-[9px] text-space-muted">Conjunctions</span>
          </div>
        )}
        {showGroundTracks && (
          <div className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-[var(--color-accent-indigo)]" />
            <span className="font-mono text-[9px] text-space-muted">Ground Tracks</span>
          </div>
        )}
      </div>

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
