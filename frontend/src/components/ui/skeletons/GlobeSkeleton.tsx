/**
 * ORBITIQ-X — GlobeSkeleton
 * ==========================
 * Suspense fallback shown while CesiumJS/OrbitalGlobe loads.
 * Matches the globe panel dimensions exactly.
 */

export function GlobeSkeleton() {
  return (
    <div
      className="globe-scanlines relative flex h-full w-full items-center justify-center bg-space-midnight"
      role="status"
      aria-label="Loading orbital globe..."
    >
      {/* Animated pulsing circle to suggest globe */}
      <div className="relative flex h-64 w-64 items-center justify-center">
        <div className="absolute h-64 w-64 animate-ping rounded-full border border-[var(--color-accent-indigo)] opacity-20" />
        <div className="absolute h-48 w-48 animate-pulse rounded-full border border-[var(--color-accent-indigo-dim)] opacity-30" />
        <div className="absolute h-32 w-32 rounded-full border border-[var(--color-space-border-strong)] opacity-40" />
        <span className="section-label">INITIALIZING ORBITAL ENGINE</span>
      </div>

      {/* Coordinate readout skeleton */}
      <div className="absolute bottom-4 left-4 space-y-1">
        <div className="h-3 w-28 animate-pulse rounded bg-space-surface" />
        <div className="h-3 w-20 animate-pulse rounded bg-space-surface" />
      </div>

      {/* Object count skeleton */}
      <div className="absolute right-4 top-4 space-y-1">
        <div className="h-4 w-24 animate-pulse rounded bg-space-surface" />
        <div className="h-3 w-16 animate-pulse rounded bg-space-surface" />
      </div>
    </div>
  );
}
