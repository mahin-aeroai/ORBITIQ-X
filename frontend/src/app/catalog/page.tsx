"use client";
/**
 * ORBITIQ-X — Satellite Catalog (v0.4.0)
 * =========================================
 * Full 29,198 satellite catalog with regime/type filtering, search,
 * and live orbital data from the Digital Twin.
 */

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchCesiumStates,
  fetchCatalogHealth,
  fetchRegimeDensity,
  type CesiumSatObject,
} from "@/lib/api";

// ─── Constants ────────────────────────────────────────────────────────────────

const REGIME_COLORS: Record<string, string> = {
  LEO:     "var(--color-accent-indigo-bright)",
  MEO:     "var(--color-accent-green-bright)",
  GEO:     "var(--color-accent-amber-bright)",
  HEO:     "var(--color-accent-red-bright)",
  SSO:     "var(--color-text-data)",
  VLEO:    "var(--color-accent-green)",
  UNKNOWN: "var(--color-text-tertiary)",
};

const TYPE_LABELS: Record<string, string> = {
  PAYLOAD:     "SAT",
  ROCKET_BODY: "R/B",
  DEBRIS:      "DEB",
  UNKNOWN:     "UNK",
};

const TYPE_COLORS: Record<string, string> = {
  PAYLOAD:     "var(--color-accent-green-bright)",
  ROCKET_BODY: "var(--color-accent-amber)",
  DEBRIS:      "var(--color-accent-red-bright)",
  UNKNOWN:     "var(--color-text-tertiary)",
};

const ALL_REGIMES = ["ALL", "LEO", "MEO", "GEO", "HEO", "SSO", "VLEO"];
const ALL_TYPES   = ["ALL", "PAYLOAD", "ROCKET_BODY", "DEBRIS"];
const PAGE_SIZE   = 100;

// ─── Sub-components ───────────────────────────────────────────────────────────

function FilterPill({
  label, active, color, count, onClick,
}: { label: string; active: boolean; color?: string; count?: number; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1.5 rounded border px-2.5 py-1 font-mono text-[9px] font-semibold uppercase tracking-wider transition-all"
      style={{
        borderColor: active ? (color ?? "var(--color-accent-indigo)") : "var(--color-space-border)",
        color: active ? (color ?? "var(--color-accent-indigo-bright)") : "var(--color-text-tertiary)",
        backgroundColor: active ? `${color ?? "var(--color-accent-indigo)"}18` : "transparent",
      }}
    >
      {label}
      {count !== undefined && (
        <span className="rounded bg-[rgba(255,255,255,0.05)] px-1 tabular-nums">
          {count.toLocaleString()}
        </span>
      )}
    </button>
  );
}

function SatRow({ sat }: { sat: CesiumSatObject }) {
  const regimeColor = REGIME_COLORS[sat.regime] ?? REGIME_COLORS.UNKNOWN;
  const typeColor   = TYPE_COLORS[sat.type]   ?? TYPE_COLORS.UNKNOWN;
  const typeLabel   = TYPE_LABELS[sat.type]   ?? "UNK";

  return (
    <div className="grid grid-cols-[60px_1fr_56px_64px_72px_72px_72px] items-center gap-2 border-b border-[var(--color-space-border)] px-4 py-1.5 hover:bg-[var(--color-space-surface)] transition-colors">
      {/* NORAD ID */}
      <span className="font-mono text-[10px] tabular-nums text-[var(--color-text-tertiary)]">
        {sat.id}
      </span>
      {/* Name */}
      <span className="truncate font-mono text-[11px] text-[var(--color-text-primary)]" title={sat.name}>
        {sat.name}
      </span>
      {/* Type badge */}
      <span
        className="rounded border px-1 py-0.5 text-center font-mono text-[8px] font-bold"
        style={{ color: typeColor, borderColor: `${typeColor}50`, backgroundColor: `${typeColor}12` }}
      >
        {typeLabel}
      </span>
      {/* Regime */}
      <span className="font-mono text-[9px] font-semibold" style={{ color: regimeColor }}>
        {sat.regime}
      </span>
      {/* Altitude */}
      <span className="text-right font-mono text-[10px] tabular-nums text-[var(--color-text-data)]">
        {sat.alt_km.toFixed(0)} km
      </span>
      {/* Speed */}
      <span className="text-right font-mono text-[10px] tabular-nums text-[var(--color-text-secondary)]">
        {sat.speed.toFixed(2)} km/s
      </span>
      {/* Position */}
      <span className="text-right font-mono text-[9px] tabular-nums text-[var(--color-text-tertiary)]">
        {sat.lat.toFixed(1)}° {sat.lon.toFixed(1)}°
      </span>
    </div>
  );
}

function RegimeBar({ regimes }: { regimes: Record<string, number> }) {
  const total = Object.values(regimes).reduce((a, b) => a + b, 0);
  if (total === 0) return null;
  const order = ["LEO", "GEO", "MEO", "HEO", "SSO", "VLEO", "UNKNOWN"];
  return (
    <div className="flex h-1.5 w-full overflow-hidden rounded-full">
      {order.map(regime => {
        const count = regimes[regime] ?? 0;
        if (!count) return null;
        return (
          <div
            key={regime}
            title={`${regime}: ${count.toLocaleString()}`}
            className="h-full transition-all"
            style={{
              width: `${(count / total) * 100}%`,
              backgroundColor: REGIME_COLORS[regime] ?? REGIME_COLORS.UNKNOWN,
            }}
          />
        );
      })}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function CatalogPage() {
  const [regime, setRegime] = useState("ALL");
  const [type,   setType]   = useState("ALL");
  const [search, setSearch] = useState("");
  const [page,   setPage]   = useState(0);

  const { data: cesium, isLoading } = useQuery({
    queryKey:        ["cesium-states-catalog"],
    queryFn:         () => fetchCesiumStates(30000),
    staleTime:       60_000,
    refetchInterval: 120_000,
  });

  const { data: health } = useQuery({
    queryKey: ["catalog-health"],
    queryFn:  fetchCatalogHealth,
    staleTime: 30_000,
  });

  const objects = cesium?.objects ?? [];

  // Regime counts
  const regimeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const o of objects) counts[o.regime] = (counts[o.regime] ?? 0) + 1;
    return counts;
  }, [objects]);

  // Type counts
  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const o of objects) counts[o.type] = (counts[o.type] ?? 0) + 1;
    return counts;
  }, [objects]);

  // Filtered results
  const filtered = useMemo(() => {
    let list = objects;
    if (regime !== "ALL") list = list.filter(o => o.regime === regime);
    if (type   !== "ALL") list = list.filter(o => o.type   === type);
    if (search) {
      const q = search.toLowerCase();
      list = list.filter(o =>
        o.name.toLowerCase().includes(q) ||
        o.id.toString().includes(q)
      );
    }
    return list;
  }, [objects, regime, type, search]);

  const pageCount = Math.ceil(filtered.length / PAGE_SIZE);
  const pageData  = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  // Reset page on filter change
  const setFilter = (fn: () => void) => { fn(); setPage(0); };

  return (
    <div className="flex h-full flex-col bg-[var(--color-space-deep)]">

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="border-b border-[var(--color-space-border)] bg-[var(--color-space-midnight)] px-6 py-4">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h1 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">
              Satellite Catalog
            </h1>
            <p className="font-mono text-[10px] text-[var(--color-text-tertiary)]">
              {isLoading
                ? "Loading catalog..."
                : `${objects.length.toLocaleString()} tracked objects · Digital Twin epoch: ${cesium?.epoch?.slice(0, 16) ?? "—"} UTC`
              }
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-accent-green-bright)]" />
            <span className="font-mono text-[9px] text-[var(--color-accent-green-bright)]">LIVE</span>
          </div>
        </div>

        {/* Regime bar */}
        {objects.length > 0 && <RegimeBar regimes={regimeCounts} />}

        {/* Stats row */}
        <div className="mt-3 flex flex-wrap gap-4">
          {["LEO","MEO","GEO","HEO"].map(r => (
            <div key={r} className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: REGIME_COLORS[r] }} />
              <span className="font-mono text-[9px] text-[var(--color-text-tertiary)]">{r}</span>
              <span className="font-mono text-[10px] font-semibold tabular-nums" style={{ color: REGIME_COLORS[r] }}>
                {(regimeCounts[r] ?? 0).toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Filters ─────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-2 border-b border-[var(--color-space-border)] bg-[var(--color-space-navy)] px-4 py-2">
        {/* Search */}
        <input
          value={search}
          onChange={e => setFilter(() => setSearch(e.target.value))}
          placeholder="Search name or NORAD ID…"
          className="w-52 rounded border border-[var(--color-space-border)] bg-[var(--color-space-surface)] px-2.5 py-1 font-mono text-[10px] text-[var(--color-text-primary)] placeholder-[var(--color-text-tertiary)] outline-none focus:border-[var(--color-accent-indigo)] transition-colors"
        />

        <div className="mx-1 h-4 w-px bg-[var(--color-space-border)]" />

        {/* Regime filters */}
        <span className="font-mono text-[8px] tracking-[0.15em] text-[var(--color-text-tertiary)]">REGIME</span>
        {ALL_REGIMES.map(r => (
          <FilterPill
            key={r}
            label={r}
            active={regime === r}
            color={r !== "ALL" ? REGIME_COLORS[r] : undefined}
            count={r !== "ALL" ? regimeCounts[r] : undefined}
            onClick={() => setFilter(() => setRegime(r))}
          />
        ))}

        <div className="mx-1 h-4 w-px bg-[var(--color-space-border)]" />

        {/* Type filters */}
        <span className="font-mono text-[8px] tracking-[0.15em] text-[var(--color-text-tertiary)]">TYPE</span>
        {ALL_TYPES.map(t => (
          <FilterPill
            key={t}
            label={t === "ROCKET_BODY" ? "R/B" : t === "PAYLOAD" ? "SAT" : t === "DEBRIS" ? "DEB" : t}
            active={type === t}
            color={t !== "ALL" ? TYPE_COLORS[t] : undefined}
            count={t !== "ALL" ? typeCounts[t] : undefined}
            onClick={() => setFilter(() => setType(t))}
          />
        ))}

        <div className="ml-auto font-mono text-[9px] text-[var(--color-text-tertiary)]">
          {filtered.length.toLocaleString()} results
        </div>
      </div>

      {/* ── Table header ────────────────────────────────────────────────── */}
      <div className="grid grid-cols-[60px_1fr_56px_64px_72px_72px_72px] items-center gap-2 border-b border-[var(--color-space-border-strong)] bg-[var(--color-space-navy)] px-4 py-1.5">
        {["NORAD", "NAME", "TYPE", "REGIME", "ALT", "SPEED", "POSITION"].map(h => (
          <span key={h} className="font-mono text-[8px] font-semibold tracking-[0.12em] text-[var(--color-text-tertiary)]">
            {h}
          </span>
        ))}
      </div>

      {/* ── Table body ──────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex h-32 items-center justify-center">
            <div className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-accent-indigo)]" />
              <span className="font-mono text-xs text-[var(--color-text-tertiary)]">Loading {health?.database_satellite_count?.toLocaleString() ?? "29,198"} satellites…</span>
            </div>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex h-32 items-center justify-center">
            <span className="font-mono text-xs text-[var(--color-text-tertiary)]">No satellites match current filters</span>
          </div>
        ) : (
          pageData.map(sat => <SatRow key={sat.id} sat={sat} />)
        )}
      </div>

      {/* ── Pagination ──────────────────────────────────────────────────── */}
      {pageCount > 1 && (
        <div className="flex items-center justify-between border-t border-[var(--color-space-border)] bg-[var(--color-space-midnight)] px-4 py-2">
          <span className="font-mono text-[9px] text-[var(--color-text-tertiary)]">
            Page {page + 1} of {pageCount} · showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, filtered.length)} of {filtered.length.toLocaleString()}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage(p => Math.max(0, p - 1))}
              disabled={page === 0}
              className="rounded border border-[var(--color-space-border)] px-2 py-0.5 font-mono text-[9px] text-[var(--color-text-secondary)] disabled:opacity-30 hover:border-[var(--color-accent-indigo)] transition-colors"
            >← Prev</button>
            {Array.from({ length: Math.min(7, pageCount) }).map((_, i) => {
              const p = page < 4 ? i : page > pageCount - 4 ? pageCount - 7 + i : page - 3 + i;
              if (p < 0 || p >= pageCount) return null;
              return (
                <button
                  key={p}
                  onClick={() => setPage(p)}
                  className="rounded border px-2 py-0.5 font-mono text-[9px] transition-colors"
                  style={{
                    borderColor: p === page ? "var(--color-accent-indigo)" : "var(--color-space-border)",
                    color: p === page ? "var(--color-accent-indigo-bright)" : "var(--color-text-secondary)",
                    backgroundColor: p === page ? "var(--color-accent-indigo-glow)" : "transparent",
                  }}
                >
                  {p + 1}
                </button>
              );
            })}
            <button
              onClick={() => setPage(p => Math.min(pageCount - 1, p + 1))}
              disabled={page === pageCount - 1}
              className="rounded border border-[var(--color-space-border)] px-2 py-0.5 font-mono text-[9px] text-[var(--color-text-secondary)] disabled:opacity-30 hover:border-[var(--color-accent-indigo)] transition-colors"
            >Next →</button>
          </div>
        </div>
      )}
    </div>
  );
}
