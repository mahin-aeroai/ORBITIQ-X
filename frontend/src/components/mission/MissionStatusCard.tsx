"use client";
/**
 * ORBITIQ-X — MissionStatusCard
 * ===============================
 * Bottom bar fourth card: overall mission/system health.
 *
 * Data source: GET /api/v1/catalog/health
 * Maps overall → color + label for the operator.
 *
 * States:
 *   healthy   → green  NOMINAL
 *   degraded  → amber  DEGRADED
 *   unhealthy → red    CRITICAL
 *   unknown   → muted  UNKNOWN
 */

import { useQuery } from "@tanstack/react-query";
import { fetchCatalogHealth } from "@/lib/api";

const STATUS_MAP = {
  healthy:   { label: "NOMINAL",   color: "var(--color-accent-green-bright)",  bg: "var(--color-accent-green-glow)" },
  degraded:  { label: "DEGRADED",  color: "var(--color-accent-amber-bright)", bg: "var(--color-accent-amber-glow)" },
  unhealthy: { label: "CRITICAL",  color: "var(--color-accent-red-bright)",   bg: "var(--color-accent-red-glow)" },
} as const;

export function MissionStatusCard() {
  const { data, isLoading } = useQuery({
    queryKey:        ["catalog-health"],
    queryFn:         fetchCatalogHealth,
    refetchInterval: 60_000,
    staleTime:       30_000,
  });

  const overall = data?.overall ?? "unknown";
  const map     = STATUS_MAP[overall as keyof typeof STATUS_MAP] ?? {
    label: "UNKNOWN",
    color: "var(--color-text-tertiary)",
    bg:    "transparent",
  };

  return (
    <div
      className="flex flex-col items-center justify-center gap-1 px-4 py-3"
      role="region"
      aria-label="System mission status"
    >
      <span className="section-label">MISSION STATUS</span>

      {isLoading ? (
        <div className="h-6 w-20 animate-pulse rounded bg-space-surface" />
      ) : (
        <div className="flex items-center gap-2">
          {/* Status dot */}
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ backgroundColor: map.color }}
            aria-hidden="true"
          />
          <span
            className="rounded px-2 py-0.5 font-display text-xs font-bold tracking-wider"
            style={{ color: map.color, backgroundColor: map.bg }}
          >
            {map.label}
          </span>
        </div>
      )}

      {/* Sync age sub-label */}
      {data?.last_sync_age_minutes !== null && data?.last_sync_age_minutes !== undefined && (
        <span className="font-mono text-[10px] text-space-muted">
          SYNC {Math.round(data.last_sync_age_minutes)}m AGO
        </span>
      )}

      {/* Warning count */}
      {data?.warnings && data.warnings.length > 0 && (
        <span
          className="font-mono text-[10px]"
          style={{ color: "var(--color-accent-amber)" }}
        >
          {data.warnings.length} WARNING{data.warnings.length > 1 ? "S" : ""}
        </span>
      )}
    </div>
  );
}
