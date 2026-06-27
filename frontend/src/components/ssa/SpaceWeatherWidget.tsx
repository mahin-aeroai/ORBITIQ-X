"use client";
/**
 * ORBITIQ-X — SpaceWeatherWidget (v0.4.0)
 * ==========================================
 * Redesigned space weather panel with honest status display.
 * Shows "Space weather data unavailable" instead of zeroed values.
 */

import { useQuery } from "@tanstack/react-query";
import { fetchSpaceWeather, type SpaceWeatherData } from "@/lib/api";

function kpColor(kp: number): string {
  if (kp <= 3) return "var(--color-accent-green-bright)";
  if (kp <= 5) return "var(--color-accent-amber)";
  if (kp <= 7) return "var(--color-accent-amber-bright)";
  return "var(--color-accent-red-bright)";
}

function kpLabel(kp: number): string {
  if (kp <= 1) return "QUIET";
  if (kp <= 3) return "UNSETTLED";
  if (kp <= 5) return "ACTIVE";
  if (kp <= 7) return "STORM";
  return "SEVERE";
}

function StormBadge({ level }: { level: string }) {
  const isNone = !level || level === "NONE" || level === "G0" || level === "S0" || level === "R0";
  const isSevere = level >= "G3" || level >= "S3" || level >= "R3";
  const color = isNone
    ? "var(--color-text-tertiary)"
    : isSevere
    ? "var(--color-accent-red-bright)"
    : "var(--color-accent-amber)";

  return (
    <span
      className="rounded border px-1.5 py-0.5 font-mono text-[9px] font-bold"
      style={{
        color,
        borderColor: isNone ? "var(--color-space-border)" : `${color}80`,
        backgroundColor: isNone ? "transparent" : `${color}15`,
      }}
    >
      {isNone ? level || "—" : level}
    </span>
  );
}

interface SpaceWeatherWidgetProps {
  compact?: boolean;
}

export function SpaceWeatherWidget({ compact = false }: SpaceWeatherWidgetProps) {
  const { data, isLoading, isError, dataUpdatedAt } = useQuery<SpaceWeatherData, Error>({
    queryKey:        ["space-weather"],
    queryFn:         fetchSpaceWeather,
    refetchInterval: 5 * 60 * 1000,
    staleTime:       4 * 60 * 1000,
  });

  if (isLoading) {
    return (
      <div className="space-y-2" aria-busy="true">
        <div className="flex items-center justify-between">
          <span className="font-mono text-[9px] tracking-[0.15em] text-[var(--color-text-tertiary)]">SPACE WEATHER</span>
          <div className="h-2 w-8 animate-pulse rounded bg-[var(--color-space-surface)]" />
        </div>
        <div className="h-6 w-12 animate-pulse rounded bg-[var(--color-space-surface)]" />
        <div className="h-1.5 w-full animate-pulse rounded-full bg-[var(--color-space-surface)]" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div>
        <div className="mb-2 flex items-center justify-between">
          <span className="font-mono text-[9px] tracking-[0.15em] text-[var(--color-text-tertiary)]">SPACE WEATHER</span>
          <span className="inline-flex items-center gap-1">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--color-text-tertiary)]" />
            <span className="font-mono text-[8px] text-[var(--color-text-tertiary)]">OFFLINE</span>
          </span>
        </div>
        <p className="font-mono text-[10px] text-[var(--color-text-secondary)]">
          Space weather data unavailable
        </p>
        <p className="mt-1 font-mono text-[9px] text-[var(--color-text-tertiary)]">
          NOAA SWPC feed not reachable
        </p>
      </div>
    );
  }

  const kp = data.kp_index ?? 0;
  const kpC = kpColor(kp);
  const freshMs = Date.now() - dataUpdatedAt;
  const isStale = freshMs > 10 * 60 * 1000;

  return (
    <div>
      {/* Header */}
      <div className="mb-2 flex items-center justify-between">
        <span className="font-mono text-[9px] tracking-[0.15em] text-[var(--color-text-tertiary)]">
          SPACE WEATHER
        </span>
        <span className="inline-flex items-center gap-1">
          <span className={`inline-block h-1.5 w-1.5 rounded-full ${isStale ? "bg-[var(--color-accent-amber)]" : "animate-pulse bg-[var(--color-accent-green-bright)]"}`} />
          <span className="font-mono text-[8px]" style={{ color: isStale ? "var(--color-accent-amber)" : "var(--color-accent-green-bright)" }}>
            {isStale ? "STALE" : "LIVE"}
          </span>
        </span>
      </div>

      {/* Kp hero */}
      <div className="mb-2 flex items-end gap-2">
        <span className="font-mono text-2xl font-bold tabular-nums leading-none" style={{ color: kpC }}>
          {kp.toFixed(1)}
        </span>
        <div className="mb-0.5 flex flex-col">
          <span className="font-mono text-[8px] text-[var(--color-text-tertiary)]">Kp INDEX</span>
          <span className="font-mono text-[9px] font-semibold" style={{ color: kpC }}>{kpLabel(kp)}</span>
        </div>
      </div>

      {/* Kp progress bar */}
      <div className="mb-2 h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-space-surface)]">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${(kp / 9) * 100}%`, backgroundColor: kpC }}
        />
      </div>

      {/* Storm level badges */}
      <div className="mb-1 flex flex-wrap gap-1">
        <StormBadge level={data.geomagnetic_storm ?? "G0"} />
        <StormBadge level={data.solar_radiation_storm ?? "S0"} />
        <StormBadge level={data.radio_blackout ?? "R0"} />
      </div>

      {!compact && (
        <>
          <div className="my-2 border-t border-[var(--color-space-border)]" />
          {[
            { label: "F10.7 Flux", value: data.f107_solar_flux != null ? `${data.f107_solar_flux.toFixed(1)} sfu` : "—" },
            { label: "Ap Index",   value: data.ap_index?.toString() ?? "—" },
            { label: "Sunspot #",  value: data.sunspot_number?.toString() ?? "—" },
            { label: "Atm Density ×", value: data.atmospheric_density_scale_factor?.toFixed(2) ?? "—" },
          ].map(({ label, value }) => (
            <div key={label} className="flex items-center justify-between py-0.5">
              <span className="font-mono text-[9px] text-[var(--color-text-tertiary)]">{label}</span>
              <span className="font-mono text-[10px] text-[var(--color-text-data)]">{value}</span>
            </div>
          ))}
        </>
      )}

      {data.timestamp && (
        <div className="mt-2 font-mono text-[8px] text-[var(--color-text-tertiary)]">
          {new Date(data.timestamp).toISOString().slice(0, 16).replace("T", " ")} UTC
        </div>
      )}
    </div>
  );
}
