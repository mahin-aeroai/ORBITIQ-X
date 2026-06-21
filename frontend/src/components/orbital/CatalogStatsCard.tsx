"use client";
/**
 * ORBITIQ-X — CatalogStatsCard
 * ==============================
 * Bottom bar catalog metrics card.
 * Shows the value of a specific dataKey from the catalog backend.
 *
 * Data sources:
 *   GET /api/v1/catalog/health  → database_satellite_count
 *   GET /api/v1/catalog/status  → total_parsed, inserted, stale_satellite_count
 *
 * Props:
 *   label   — display label (e.g. "Tracked Objects")
 *   dataKey — which field to pull from the merged catalog data
 */

import { useQuery } from "@tanstack/react-query";
import { fetchCatalogHealth, fetchCatalogStatus } from "@/lib/api";

type CatalogDataKey =
  | "total_rso_count"         // → health.database_satellite_count
  | "active_payload_count"    // → status.satellites_updated (best proxy)
  | "debris_count"            // → status.stale_satellite_count (proxy)
  | "total_parsed"
  | "inserted"
  | "parse_errors";

interface CatalogStatsCardProps {
  label:   string;
  dataKey: CatalogDataKey;
}

function resolveDataKey(
  dataKey: CatalogDataKey,
  health:  Awaited<ReturnType<typeof fetchCatalogHealth>> | undefined,
  status:  Awaited<ReturnType<typeof fetchCatalogStatus>> | undefined,
): number | string | null {
  if (!health && !status) return null;
  switch (dataKey) {
    case "total_rso_count":      return health?.database_satellite_count ?? null;
    case "active_payload_count": return status?.satellites_updated ?? null;
    case "debris_count":         return status?.stale_satellite_count ?? null;
    case "total_parsed":         return status?.total_parsed ?? null;
    case "inserted":             return status?.inserted ?? null;
    case "parse_errors":         return status?.parse_errors ?? null;
    default:                     return null;
  }
}

export function CatalogStatsCard({ label, dataKey }: CatalogStatsCardProps) {
  const { data: health } = useQuery({
    queryKey:        ["catalog-health"],
    queryFn:         fetchCatalogHealth,
    refetchInterval: 60_000,
    staleTime:       30_000,
  });

  const { data: status } = useQuery({
    queryKey:        ["catalog-status"],
    queryFn:         fetchCatalogStatus,
    refetchInterval: 60_000,
    staleTime:       30_000,
  });

  const value = resolveDataKey(dataKey, health, status);
  const isLoading = !health && !status;

  return (
    <div
      className="flex flex-col items-center justify-center gap-1 px-4 py-3"
      role="region"
      aria-label={label}
    >
      <span className="section-label">{label}</span>
      {isLoading ? (
        <div className="h-6 w-16 animate-pulse rounded bg-space-surface" />
      ) : (
        <span className="data-value-large tabular-nums">
          {value !== null ? Number(value).toLocaleString() : "—"}
        </span>
      )}
    </div>
  );
}
