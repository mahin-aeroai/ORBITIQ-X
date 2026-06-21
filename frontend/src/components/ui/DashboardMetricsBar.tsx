"use client";
/**
 * ORBITIQ-X — DashboardMetricsBar
 * =================================
 * Top horizontal bar showing live SSA system metrics.
 *
 * Data source: GET /api/v1/ssa/statistics
 * Refresh:     30 seconds (staleTime from QueryProvider)
 *
 * Displays:
 *   • Total conjunction events in CDM archive
 *   • Unresolved events count
 *   • RED / YELLOW risk counts  (from by_risk map)
 *   • Maneuver required count
 *   • Max Pc in archive
 *   • Avg miss distance
 */

import { useQuery } from "@tanstack/react-query";
import { fetchSSAStatistics, type SSAStatistics } from "@/lib/api";

// ─── Sub-component: single metric cell ───────────────────────────────────────

interface MetricCellProps {
  label:    string;
  value:    React.ReactNode;
  accent?:  "indigo" | "amber" | "red" | "green" | "default";
  pulse?:   boolean;
}

function MetricCell({ label, value, accent = "default", pulse = false }: MetricCellProps) {
  const colorMap: Record<NonNullable<MetricCellProps["accent"]>, string> = {
    indigo:  "var(--color-accent-indigo-bright)",
    amber:   "var(--color-accent-amber-bright)",
    red:     "var(--color-accent-red-bright)",
    green:   "var(--color-accent-green-bright)",
    default: "var(--color-text-data)",
  };
  const color = colorMap[accent];

  return (
    <div className="flex flex-col items-center justify-center gap-0.5 px-4">
      <span className="section-label">{label}</span>
      <span
        className={["data-value-large tabular-nums", pulse ? "animate-pulse" : ""].join(" ").trim()}
        style={{ color }}
      >
        {value}
      </span>
    </div>
  );
}

function Divider() {
  return <div className="h-8 w-px bg-[var(--color-space-border)]" aria-hidden="true" />;
}

// ─── Skeleton ─────────────────────────────────────────────────────────────────

function MetricsBarSkeleton() {
  return (
    <div className="flex h-14 items-center gap-0 border-b border-space-border bg-space-midnight px-2">
      {Array.from({ length: 7 }).map((_, i) => (
        <div key={i} className="flex flex-1 flex-col items-center gap-1 px-3">
          <div className="h-2 w-16 animate-pulse rounded bg-space-surface" />
          <div className="h-5 w-10 animate-pulse rounded bg-space-surface" />
        </div>
      ))}
    </div>
  );
}

// ─── Error state ──────────────────────────────────────────────────────────────

function MetricsBarError({ error }: { error: Error }) {
  return (
    <div className="flex h-14 items-center justify-center border-b border-space-border bg-space-midnight px-4">
      <span className="font-mono text-xs text-[var(--color-accent-amber)]">
        ⚠ SSA STATISTICS UNAVAILABLE — {error.message.slice(0, 80)}
      </span>
    </div>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatPc(pc: number | null): string {
  if (pc === null || pc === undefined) return "—";
  if (pc === 0) return "0";
  const exp = Math.floor(Math.log10(pc));
  const man = (pc / Math.pow(10, exp)).toFixed(1);
  return `${man}e${exp}`;
}

function formatKm(km: number | null): string {
  if (km === null || km === undefined) return "—";
  return km.toFixed(1);
}

// ─── Main component ───────────────────────────────────────────────────────────

export function DashboardMetricsBar() {
  const {
    data,
    isLoading,
    isError,
    error,
  } = useQuery<SSAStatistics, Error>({
    queryKey:        ["ssa-statistics"],
    queryFn:         fetchSSAStatistics,
    refetchInterval: 30_000,
  });

  if (isLoading) return <MetricsBarSkeleton />;
  if (isError)   return <MetricsBarError error={error} />;
  if (!data)     return <MetricsBarSkeleton />;

  const byRisk  = data.by_risk ?? {};
  const redCount    = byRisk["red"]    ?? 0;
  const yellowCount = byRisk["yellow"] ?? 0;

  return (
    <div
      className="flex h-14 shrink-0 items-center border-b border-space-border bg-space-midnight"
      role="region"
      aria-label="SSA system metrics"
    >
      {/* Total CDM Events */}
      <MetricCell
        label="TOTAL EVENTS"
        value={data.total_events.toLocaleString()}
        accent="default"
      />
      <Divider />

      {/* Unresolved */}
      <MetricCell
        label="UNRESOLVED"
        value={data.unresolved_total.toLocaleString()}
        accent={data.unresolved_total > 50 ? "amber" : "default"}
      />
      <Divider />

      {/* RED alerts */}
      <MetricCell
        label="RED ALERTS"
        value={redCount.toLocaleString()}
        accent={redCount > 0 ? "red" : "green"}
        pulse={redCount > 0}
      />
      <Divider />

      {/* YELLOW watch */}
      <MetricCell
        label="YELLOW WATCH"
        value={yellowCount.toLocaleString()}
        accent={yellowCount > 0 ? "amber" : "default"}
      />
      <Divider />

      {/* Maneuver Required */}
      <MetricCell
        label="MANO REQD"
        value={data.maneuver_required_count.toLocaleString()}
        accent={data.maneuver_required_count > 0 ? "amber" : "default"}
      />
      <Divider />

      {/* Max Pc */}
      <MetricCell
        label="MAX Pc"
        value={formatPc(data.max_pc)}
        accent={
          data.max_pc !== null && data.max_pc >= 1e-3
            ? "red"
            : data.max_pc !== null && data.max_pc >= 1e-4
            ? "amber"
            : "green"
        }
      />
      <Divider />

      {/* Avg Miss Distance */}
      <MetricCell
        label="AVG MISS km"
        value={formatKm(data.avg_miss_distance_km)}
        accent="indigo"
      />
    </div>
  );
}
