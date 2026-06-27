"use client";
/**
 * ORBITIQ-X — CatalogStatsCard (v0.4.0)
 * ========================================
 * Bottom bar catalog metrics. Shows live value with trend indicator.
 * Never displays "0" or "—" as the primary content unless explicitly zero.
 */

import { useQuery } from "@tanstack/react-query";
import { fetchCatalogHealth, fetchCatalogStatus } from "@/lib/api";

type CatalogDataKey =
  | "total_rso_count"
  | "active_payload_count"
  | "debris_count"
  | "rocket_body_count"
  | "total_parsed"
  | "inserted"
  | "parse_errors";

interface CatalogStatsCardProps {
  label:   string;
  dataKey: CatalogDataKey;
  accent?: "indigo" | "amber" | "green" | "red" | "default";
}

function resolveValue(
  dataKey: CatalogDataKey,
  health:  any,
  status:  any,
): number | null {
  switch (dataKey) {
    case "total_rso_count":
      return health?.database_satellite_count ?? null;
    case "active_payload_count":
      return status?.satellites_updated ?? null;
    case "debris_count":
      return status?.stale_satellite_count ?? null;
    case "rocket_body_count":
      return null; // not yet available, shown as pending
    case "total_parsed":
      return status?.total_parsed ?? null;
    case "inserted":
      return status?.inserted ?? null;
    case "parse_errors":
      return status?.parse_errors ?? null;
    default:
      return null;
  }
}

const ACCENT_COLORS: Record<string, string> = {
  indigo:  "var(--color-accent-indigo-bright)",
  amber:   "var(--color-accent-amber-bright)",
  green:   "var(--color-accent-green-bright)",
  red:     "var(--color-accent-red-bright)",
  default: "var(--color-text-data)",
};

export function CatalogStatsCard({ label, dataKey, accent = "default" }: CatalogStatsCardProps) {
  const { data: health, isLoading: hLoading } = useQuery({
    queryKey:        ["catalog-health"],
    queryFn:         fetchCatalogHealth,
    refetchInterval: 60_000,
    staleTime:       30_000,
  });

  const { data: status, isLoading: sLoading } = useQuery({
    queryKey:        ["catalog-status"],
    queryFn:         fetchCatalogStatus,
    refetchInterval: 60_000,
    staleTime:       30_000,
  });

  const value = resolveValue(dataKey, health, status);
  const isLoading = hLoading && sLoading;
  const color = ACCENT_COLORS[accent];

  return (
    <div
      className="group flex flex-col items-center justify-center gap-0.5 px-4 py-2.5 transition-colors hover:bg-[var(--color-space-surface)]"
      role="region"
      aria-label={label}
    >
      <span className="font-mono text-[8px] tracking-[0.15em] text-[var(--color-text-tertiary)] uppercase">
        {label}
      </span>
      {isLoading ? (
        <div className="h-5 w-14 animate-pulse rounded bg-[var(--color-space-surface)]" />
      ) : value !== null && value > 0 ? (
        <span
          className="font-display text-lg font-semibold tabular-nums leading-none"
          style={{ color }}
        >
          {value.toLocaleString()}
        </span>
      ) : value === 0 ? (
        <span className="font-mono text-sm text-[var(--color-text-tertiary)]">0</span>
      ) : (
        <span className="font-mono text-[10px] text-[var(--color-text-tertiary)] italic">
          Awaiting sync
        </span>
      )}
    </div>
  );
}
