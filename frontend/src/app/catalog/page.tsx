"use client";
/**
 * ORBITIQ-X — Satellite Catalog (v0.4.0)
 * =========================================
 * 29,198 RSOs from PostgreSQL via /catalog/satellites.
 * Server-side filtering + pagination, client-side search debounce.
 */

import { useState, useEffect, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchSatelliteList, fetchCatalogHealth, type CatalogSatellite } from "@/lib/api";

// ─── Design tokens ────────────────────────────────────────────────────────────

const REGIME_COLOR: Record<string, string> = {
  LEO:     "var(--color-accent-indigo-bright)",
  MEO:     "var(--color-accent-green-bright)",
  GEO:     "var(--color-accent-amber-bright)",
  HEO:     "var(--color-accent-red-bright)",
  SSO:     "var(--color-text-data)",
  VLEO:    "var(--color-accent-green)",
  UNKNOWN: "var(--color-text-tertiary)",
};

const TYPE_LABEL: Record<string, string> = {
  PAYLOAD:     "SAT",
  ROCKET_BODY: "R/B",
  DEBRIS:      "DEB",
  UNKNOWN:     "UNK",
};

const TYPE_COLOR: Record<string, string> = {
  PAYLOAD:     "var(--color-accent-green-bright)",
  ROCKET_BODY: "var(--color-accent-amber)",
  DEBRIS:      "var(--color-accent-red-bright)",
  UNKNOWN:     "var(--color-text-tertiary)",
};

const PAGE_SIZE = 200;
const REGIMES   = ["ALL","LEO","MEO","GEO","HEO","SSO","VLEO"];
const TYPES     = ["ALL","PAYLOAD","ROCKET_BODY","DEBRIS"];

// ─── Sub-components ───────────────────────────────────────────────────────────

function Pill({
  label, count, active, color, onClick,
}: { label: string; count?: number; active: boolean; color?: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1 rounded border px-2 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider transition-all"
      style={{
        borderColor:     active ? (color ?? "var(--color-accent-indigo)") : "var(--color-space-border)",
        color:           active ? (color ?? "var(--color-accent-indigo-bright)") : "var(--color-text-tertiary)",
        backgroundColor: active ? `${color ?? "var(--color-accent-indigo)"}18` : "transparent",
      }}
    >
      {label}
      {count !== undefined && (
        <span className="opacity-70 tabular-nums">{count >= 1000 ? `${(count/1000).toFixed(0)}k` : count}</span>
      )}
    </button>
  );
}

function SatRow({ s }: { s: CatalogSatellite }) {
  const rc = REGIME_COLOR[s.regime] ?? REGIME_COLOR.UNKNOWN;
  const tc = TYPE_COLOR[s.object_type]  ?? TYPE_COLOR.UNKNOWN;
  const tl = TYPE_LABEL[s.object_type]  ?? "UNK";
  const alt = s.apogee_km != null && s.perigee_km != null
    ? `${((s.apogee_km + s.perigee_km) / 2).toFixed(0)}`
    : s.apogee_km != null ? s.apogee_km.toFixed(0) : "—";

  return (
    <div className="grid grid-cols-[60px_1fr_44px_60px_64px_56px_36px] items-center gap-2 border-b border-[var(--color-space-border)] px-4 py-1 hover:bg-[var(--color-space-surface)] transition-colors">
      <span className="font-mono text-[9px] tabular-nums text-[var(--color-text-tertiary)]">{s.norad_id}</span>
      <span className="truncate font-mono text-[10px] text-[var(--color-text-primary)]" title={s.name}>{s.name}</span>
      <span className="rounded border px-1 py-0.5 text-center font-mono text-[8px] font-bold"
        style={{ color: tc, borderColor: `${tc}50`, backgroundColor: `${tc}12` }}>{tl}</span>
      <span className="font-mono text-[9px] font-semibold" style={{ color: rc }}>{s.regime}</span>
      <span className="text-right font-mono text-[9px] tabular-nums text-[var(--color-text-data)]">{alt} km</span>
      <span className="text-right font-mono text-[9px] tabular-nums text-[var(--color-text-secondary)]">
        {s.inclination_deg != null ? `${s.inclination_deg.toFixed(1)}°` : "—"}
      </span>
      <span className="text-right font-mono text-[9px] tabular-nums text-[var(--color-text-tertiary)]">
        {s.country_code ?? "—"}
      </span>
    </div>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function CatalogPage() {
  const [regime, setRegime] = useState("ALL");
  const [type,   setType]   = useState("ALL");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [page,   setPage]   = useState(0);

  // Debounce search input
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  const resetPage = useCallback(() => setPage(0), []);

  const { data, isLoading, isFetching } = useQuery({
    queryKey:        ["satellite-list", regime, type, debouncedSearch, page],
    queryFn:         () => fetchSatelliteList({
      regime: regime !== "ALL" ? regime : undefined,
      type:   type   !== "ALL" ? type   : undefined,
      search: debouncedSearch || undefined,
      page, limit: PAGE_SIZE,
    }),
    staleTime:       60_000,
    placeholderData: (prev) => prev,
  });

  const { data: health } = useQuery({
    queryKey: ["catalog-health"],
    queryFn:  fetchCatalogHealth,
    staleTime: 30_000,
  });

  const objects    = data?.objects  ?? [];
  const total      = data?.total    ?? 0;
  const pageCount  = Math.ceil(total / PAGE_SIZE);
  const totalInDB  = health?.database_satellite_count ?? 0;

  return (
    <div className="flex h-full flex-col bg-[var(--color-space-deep)]">

      {/* Header */}
      <div className="shrink-0 border-b border-[var(--color-space-border)] bg-[var(--color-space-midnight)] px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">
              Satellite Catalog
            </h1>
            <p className="mt-0.5 font-mono text-[9px] text-[var(--color-text-tertiary)]">
              {totalInDB > 0
                ? `${totalInDB.toLocaleString()} objects in catalog · PostgreSQL`
                : "Loading catalog…"}
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            {isFetching && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-accent-amber)]" />}
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-accent-green-bright)]" />
            <span className="font-mono text-[9px] text-[var(--color-accent-green-bright)]">LIVE</span>
          </div>
        </div>

        {/* Regime distribution bar */}
        {totalInDB > 0 && (
          <div className="mt-3 space-y-1">
            <div className="flex h-1 w-full overflow-hidden rounded-full bg-[var(--color-space-surface)]">
              {[
                { r: "LEO", n: 25285 },
                { r: "MEO", n: 1665  },
                { r: "GEO", n: 1535  },
                { r: "HEO", n: 713   },
              ].map(({ r, n }) => (
                <div key={r} title={`${r}: ${n.toLocaleString()}`} className="h-full"
                  style={{ width: `${(n / totalInDB) * 100}%`, backgroundColor: REGIME_COLOR[r] }} />
              ))}
            </div>
            <div className="flex gap-4">
              {[["LEO","25,285"],["MEO","1,665"],["GEO","1,535"],["HEO","713"]].map(([r,n]) => (
                <div key={r} className="flex items-center gap-1">
                  <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: REGIME_COLOR[r] }} />
                  <span className="font-mono text-[8px] text-[var(--color-text-tertiary)]">{r}</span>
                  <span className="font-mono text-[9px] font-semibold tabular-nums" style={{ color: REGIME_COLOR[r] }}>{n}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Filters */}
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-[var(--color-space-border)] bg-[var(--color-space-navy)] px-4 py-2">
        <input
          value={search}
          onChange={e => { setSearch(e.target.value); resetPage(); }}
          placeholder="Search name or NORAD ID…"
          className="w-48 rounded border border-[var(--color-space-border)] bg-[var(--color-space-surface)] px-2.5 py-1 font-mono text-[10px] text-[var(--color-text-primary)] placeholder-[var(--color-text-tertiary)] outline-none focus:border-[var(--color-accent-indigo)] transition-colors"
        />

        <div className="mx-1 h-3 w-px bg-[var(--color-space-border)]" />
        <span className="font-mono text-[8px] tracking-[0.15em] text-[var(--color-text-tertiary)]">REGIME</span>
        {REGIMES.map(r => (
          <Pill key={r} label={r} active={regime === r} color={r !== "ALL" ? REGIME_COLOR[r] : undefined}
            onClick={() => { setRegime(r); resetPage(); }} />
        ))}

        <div className="mx-1 h-3 w-px bg-[var(--color-space-border)]" />
        <span className="font-mono text-[8px] tracking-[0.15em] text-[var(--color-text-tertiary)]">TYPE</span>
        {TYPES.map(t => (
          <Pill key={t}
            label={t === "ROCKET_BODY" ? "R/B" : t === "PAYLOAD" ? "SAT" : t === "DEBRIS" ? "DEB" : t}
            active={type === t} color={t !== "ALL" ? TYPE_COLOR[t] : undefined}
            onClick={() => { setType(t); resetPage(); }} />
        ))}

        <span className="ml-auto font-mono text-[9px] tabular-nums text-[var(--color-text-tertiary)]">
          {total.toLocaleString()} results
        </span>
      </div>

      {/* Table header */}
      <div className="grid grid-cols-[60px_1fr_44px_60px_64px_56px_36px] shrink-0 items-center gap-2 border-b border-[var(--color-space-border-strong)] bg-[var(--color-space-navy)] px-4 py-1">
        {["NORAD","NAME","TYPE","REGIME","ALT","INC","CC"].map(h => (
          <span key={h} className="font-mono text-[8px] tracking-[0.1em] text-[var(--color-text-tertiary)]">{h}</span>
        ))}
      </div>

      {/* Table body */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex h-32 items-center justify-center gap-2">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-accent-indigo)]" />
            <span className="font-mono text-[10px] text-[var(--color-text-tertiary)]">
              Loading {totalInDB > 0 ? totalInDB.toLocaleString() : "29,198"} satellites…
            </span>
          </div>
        ) : objects.length === 0 ? (
          <div className="flex h-32 flex-col items-center justify-center gap-2">
            <span className="font-mono text-xs text-[var(--color-text-tertiary)]">No satellites match</span>
            {data === undefined && (
              <span className="font-mono text-[9px] text-[var(--color-accent-amber)]">
                ⚠ Backend deploying — retry in 30s
              </span>
            )}
          </div>
        ) : (
          objects.map(s => <SatRow key={s.norad_id} s={s} />)
        )}
      </div>

      {/* Pagination */}
      {pageCount > 1 && (
        <div className="flex shrink-0 items-center justify-between border-t border-[var(--color-space-border)] bg-[var(--color-space-midnight)] px-4 py-2">
          <span className="font-mono text-[9px] text-[var(--color-text-tertiary)]">
            {(page * PAGE_SIZE + 1).toLocaleString()}–{Math.min((page + 1) * PAGE_SIZE, total).toLocaleString()} of {total.toLocaleString()}
          </span>
          <div className="flex items-center gap-1">
            <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
              className="rounded border border-[var(--color-space-border)] px-2 py-0.5 font-mono text-[9px] text-[var(--color-text-secondary)] disabled:opacity-30 hover:border-[var(--color-accent-indigo)] transition-colors">
              ← Prev
            </button>
            {Array.from({ length: Math.min(5, pageCount) }, (_, i) => {
              const p = Math.max(0, Math.min(page - 2, pageCount - 5)) + i;
              return (
                <button key={p} onClick={() => setPage(p)}
                  className="rounded border px-2 py-0.5 font-mono text-[9px] transition-colors"
                  style={{
                    borderColor:     p === page ? "var(--color-accent-indigo)" : "var(--color-space-border)",
                    color:           p === page ? "var(--color-accent-indigo-bright)" : "var(--color-text-secondary)",
                    backgroundColor: p === page ? "var(--color-accent-indigo-glow)" : "transparent",
                  }}>
                  {p + 1}
                </button>
              );
            })}
            <button onClick={() => setPage(p => Math.min(pageCount - 1, p + 1))} disabled={page === pageCount - 1}
              className="rounded border border-[var(--color-space-border)] px-2 py-0.5 font-mono text-[9px] text-[var(--color-text-secondary)] disabled:opacity-30 hover:border-[var(--color-accent-indigo)] transition-colors">
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
