"use client";
/**
 * ORBITIQ-X — SpaceWeatherWidget
 * ================================
 * Right panel space weather summary.
 *
 * Data source: GET /api/v1/digital-twin/weather
 * Refresh:     5 minutes (space weather changes slowly)
 *
 * Displays:
 *   • Kp index (0–9) with color band
 *   • F10.7 solar flux
 *   • Geomagnetic storm level (G0–G5)
 *   • Solar radiation storm level
 *   • Radio blackout level
 *   • Atmospheric density scale factor
 *
 * compact prop: reduces height for the right panel slot.
 */

import { useQuery } from "@tanstack/react-query";
import { fetchSpaceWeather, type SpaceWeatherData } from "@/lib/api";

// ─── Kp color scale ───────────────────────────────────────────────────────────

function kpColor(kp: number): string {
  if (kp <= 3) return "var(--color-accent-green-bright)";
  if (kp <= 5) return "var(--color-accent-amber)";
  if (kp <= 7) return "var(--color-accent-amber-bright)";
  return "var(--color-accent-red-bright)";
}

// ─── Storm badge ──────────────────────────────────────────────────────────────

function StormBadge({ level, prefix }: { level: string; prefix?: string }) {
  const isNone = level === "NONE";
  const color = isNone
    ? "var(--color-text-tertiary)"
    : level >= "G3" || level >= "S3" || level >= "R3"
    ? "var(--color-accent-red-bright)"
    : "var(--color-accent-amber)";

  return (
    <span
      className="rounded border px-1.5 py-0.5 font-mono text-[10px] font-bold"
      style={{
        color,
        borderColor: isNone ? "var(--color-space-border)" : color,
        backgroundColor: isNone ? "transparent" : `${color}20`,
      }}
    >
      {prefix}{level}
    </span>
  );
}

// ─── Row ──────────────────────────────────────────────────────────────────────

function WeatherRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-[10px] uppercase tracking-wider text-space-muted">{label}</span>
      <span className="data-value text-right text-[11px]">{value}</span>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface SpaceWeatherWidgetProps {
  compact?: boolean;
}

export function SpaceWeatherWidget({ compact = false }: SpaceWeatherWidgetProps) {
  const { data, isLoading, isError } = useQuery<SpaceWeatherData, Error>({
    queryKey:        ["space-weather"],
    queryFn:         fetchSpaceWeather,
    refetchInterval: 5 * 60 * 1000,  // 5 min
    staleTime:       4 * 60 * 1000,
  });

  if (isLoading) {
    return (
      <div className="space-y-2">
        <div className="section-label mb-2">SPACE WEATHER</div>
        {Array.from({ length: compact ? 3 : 6 }).map((_, i) => (
          <div key={i} className="h-5 w-full animate-pulse rounded bg-space-surface" />
        ))}
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div>
        <div className="section-label mb-2">SPACE WEATHER</div>
        <span className="font-mono text-[11px] text-[var(--color-accent-amber)]">
          ⚠ NOAA FEED UNAVAILABLE
        </span>
      </div>
    );
  }

  const kpColor_ = kpColor(data.kp_index ?? 0);

  return (
    <div>
      {/* Header + Kp hero */}
      <div className="mb-2 flex items-center justify-between">
        <span className="section-label">SPACE WEATHER</span>
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] text-space-muted">Kp</span>
          <span
            className="font-mono text-lg font-bold tabular-nums"
            style={{ color: kpColor_ }}
          >
            {(data.kp_index ?? 0).toFixed(1)}
          </span>
        </div>
      </div>

      {/* Kp bar */}
      <div className="mb-3 h-1.5 w-full overflow-hidden rounded-full bg-space-surface">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width:           `${((data.kp_index ?? 0) / 9) * 100}%`,
            backgroundColor: kpColor_,
          }}
        />
      </div>

      {/* Storm levels */}
      <div className="mb-2 flex items-center gap-1.5 flex-wrap">
        <StormBadge level={data.geomagnetic_storm ?? "NONE"} />
        <StormBadge level={data.solar_radiation_storm ?? "NONE"} />
        <StormBadge level={data.radio_blackout ?? "NONE"} />
      </div>

      {!compact && (
        <>
          <div className="my-2 border-t border-space-border" />
          <WeatherRow
            label="F10.7 Flux"
            value={`${(data.f107_solar_flux ?? 0).toFixed(1)} sfu`}
          />
          <WeatherRow
            label="Ap Index"
            value={(data.ap_index ?? 0).toString()}
          />
          <WeatherRow
            label="Sunspot #"
            value={(data.sunspot_number ?? 0).toString()}
          />
          <WeatherRow
            label="Atm Density ×"
            value={(data.atmospheric_density_scale_factor ?? 1).toFixed(2)}
          />
        </>
      )}

      {/* Timestamp */}
      {data.timestamp && (
        <div className="mt-2 font-mono text-[9px] text-space-muted">
          {new Date(data.timestamp).toISOString().slice(0, 16).replace("T", " ")} UTC
        </div>
      )}
    </div>
  );
}
