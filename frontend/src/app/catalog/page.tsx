"use client";
/**
 * ORBITIQ-X — Satellite Catalog (v0.4.0)
 * =========================================
 * 29,198 RSOs. Uses /catalog/satellites (PostgreSQL) with server-side
 * filtering. Falls back to regime counts from knowledge-graph if main
 * endpoint not yet deployed.
 */

import { useState, useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchSatelliteList, fetchCatalogHealth, type CatalogSatellite } from "@/lib/api";

const REGIME_COLOR: Record<string, string> = {
  LEO:     "#818cf8",
  MEO:     "#34d399",
  GEO:     "#fbbf24",
  HEO:     "#f87171",
  SSO:     "#7dd3fc",
  VLEO:    "#10b981",
  UNKNOWN: "#475569",
};

const TYPE_LABEL: Record<string, string> = {
  PAYLOAD:     "SAT",
  ROCKET_BODY: "R/B",
  DEBRIS:      "DEB",
  UNKNOWN:     "UNK",
};

const TYPE_COLOR: Record<string, string> = {
  PAYLOAD:     "#34d399",
  ROCKET_BODY: "#fbbf24",
  DEBRIS:      "#f87171",
  UNKNOWN:     "#475569",
};

const PAGE_SIZE = 200;
const REGIMES = ["ALL", "LEO", "MEO", "GEO", "HEO", "SSO", "VLEO"];
const TYPES   = ["ALL", "PAYLOAD", "ROCKET_BODY", "DEBRIS"];

// Known regime counts from Neo4j (used for the regime bar display)
const KNOWN_COUNTS: Record<string, number> = {
  LEO: 25285, MEO: 1665, GEO: 1535, HEO: 713,
};

function Pill({ label, active, color, count, onClick }: {
  label: string; active: boolean; color?: string; count?: number; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1 rounded border px-2 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider transition-all"
      style={{
        borderColor:     active ? (color ?? "#6366f1") : "var(--color-space-border)",
        color:           active ? (color ?? "#818cf8") : "var(--color-text-tertiary)",
        backgroundColor: active ? `${color ?? "#6366f1"}20` : "transparent",
      }}
    >
      {label}
      {count !== undefined && (
        <span className="tabular-nums opacity-70">
          {count >= 1000 ? `${Math.round(count / 1000)}k` : count}
        </span>
      )}
    </button>
  );
}

function SatRow({ s }: { s: CatalogSatellite }) {
  const rc = REGIME_COLOR[s.regime] ?? REGIME_COLOR.UNKNOWN;
  const tc = TYPE_COLOR[s.object_type] ?? TYPE_COLOR.UNKNOWN;
  const tl = TYPE_LABEL[s.object_type] ?? "UNK";
  const alt = s.apogee_km != null && s.perigee_km != null
    ? Math.round((s.apogee_km + s.perigee_km) / 2)
    : s.apogee_km != null ? Math.round(s.apogee_km) : null;

  return (
    <div className="grid grid-cols-[64px_1fr_44px_64px_68px_60px_36px] items-center gap-2 border-b border-[var(--color-space-border)] px-4 py-1 hover:bg-[var(--color-space-surface)] transition-colors cursor-default">
      <span className="font-mono text-[9px] tabular-nums text-[var(--color-text-tertiary)]">{s.norad_id}</span>
      <span className="truncate font-mono text-[10px] text-[var(--color-text-primary)]" title={s.name}>{s.name}</span>
      <span className="rounded border px-1 py-px text-center font-mono text-[8px] font-bold"
        style={{ color: tc, borderColor: `${tc}60`, backgroundColor: `${tc}15` }}>{tl}</span>
      <span className="font-mono text-[9px] font-semibold" style={{ color: rc }}>{s.regime || "—"}</span>
      <span className="text-right font-mono text-[9px] tabular-nums" style={{ color: "var(--color-text-data)" }}>
        {alt != null ? `${alt} km` : "—"}
      </span>
      <span className="text-right font-mono text-[9px] tabular-nums text-[var(--color-text-secondary)]">
        {s.inclination_deg != null ? `${s.inclination_deg.toFixed(1)}°` : "—"}
      </span>
      <span className="text-right font-mono text-[9px] text-[var(--color-text-tertiary)]">
        {s.country_code ?? "—"}
      </span>
    </div>
  );
}

export default function CatalogPage() {
  const [regime,          setRegime]          = useState("ALL");
  const [type,            setType]            = useState("ALL");
  const [search,          setSearch]          = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [page,            setPage]            = useState(0);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 350);
    return () => clearTimeout(t);
  }, [search]);

  // Reset page whenever filters change
  useEffect(() => { setPage(0); }, [regime, type, debouncedSearch]);

  const { data, isLoading, isFetching, isError } = useQuery({
    queryKey:        ["satellite-list", regime, type, debouncedSearch, page],
    queryFn:         () => fetchSatelliteList({
      regime: regime !== "ALL" ? regime : undefined,
      type:   type   !== "ALL" ? type   : undefined,
      search: debouncedSearch || undefined,
      page,
      limit: PAGE_SIZE,
    }),
    staleTime:       60_000,
    retry:           2,
    placeholderData: (prev) => prev,
  });

  const { data: health } = useQuery({
    queryKey: ["catalog-health"],
    queryFn:  fetchCatalogHealth,
    staleTime: 30_000,
  });

  const objects   = data?.objects ?? [];
  const total     = data?.total   ?? 0;
  const pageCount = Math.ceil(total / PAGE_SIZE);
  const totalInDB = health?.database_satellite_count ?? 0;

  // Regime counts for the filter pills — use known counts when ALL, use total for specific
  const regimeCounts = useMemo(() => {
    if (data && regime !== "ALL") return { [regime]: total };
    return KNOWN_COUNTS;
  }, [data, regime, total]);

  return (
    <div className="flex h-full flex-col bg-[var(--color-space-deep)]">

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="shrink-0 border-b border-[var(--color-space-border)] bg-[var(--color-space-midnight)] px-6 py-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm text-[var(--color-accent-indigo-bright)]">◫</span>
              <h1 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">
                Satellite Catalog
              </h1>
            </div>
            <p className="mt-0.5 font-mono text-[9px] text-[var(--color-text-tertiary)]">
              {totalInDB > 0 ? `${totalInDB.toLocaleString()} RSOs · PostgreSQL · TLE-propagated orbits` : "Loading catalog…"}
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            {isFetching && <span className="h-1.5 w-1.5 animate-ping rounded-full bg-[var(--color-accent-amber)]" />}
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-accent-green-bright)]" />
            <span className="font-mono text-[9px] text-[var(--color-accent-green-bright)]">LIVE</span>
          </div>
        </div>

        {/* Regime distribution bar */}
        <div className="mt-3 space-y-1.5">
          <div className="flex h-1 w-full overflow-hidden rounded-full bg-[var(--color-space-surface)]">
            {Object.entries(KNOWN_COUNTS).map(([r, n]) => (
              <div key={r} title={`${r}: ${n.toLocaleString()}`}
                className="h-full transition-all duration-500"
                style={{ width: `${(n / 29198) * 100}%`, backgroundColor: REGIME_COLOR[r] }} />
            ))}
          </div>
          <div className="flex gap-5">
            {Object.entries(KNOWN_COUNTS).map(([r, n]) => (
              <button key={r} onClick={() => setRegime(r === regime ? "ALL" : r)}
                className="flex items-center gap-1.5 transition-opacity hover:opacity-80">
                <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: REGIME_COLOR[r] }} />
                <span className="font-mono text-[8px] text-[var(--color-text-tertiary)]">{r}</span>
                <span className="font-mono text-[9px] font-semibold tabular-nums" style={{ color: REGIME_COLOR[r] }}>
                  {n.toLocaleString()}
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Filters ─────────────────────────────────────────────────────── */}
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-[var(--color-space-border)] bg-[var(--color-space-navy)] px-4 py-2">
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search name or NORAD ID…"
          className="w-48 rounded border border-[var(--color-space-border)] bg-[var(--color-space-surface)] px-2.5 py-1 font-mono text-[10px] text-[var(--color-text-primary)] placeholder-[var(--color-text-tertiary)] outline-none focus:border-[#6366f1] transition-colors"
        />

        <span className="mx-1 h-3 w-px bg-[var(--color-space-border)]" />
        <span className="font-mono text-[8px] tracking-[0.15em] text-[var(--color-text-tertiary)]">REGIME</span>
        {REGIMES.map(r => (
          <Pill key={r} label={r} active={regime === r}
            color={r !== "ALL" ? REGIME_COLOR[r] : undefined}
            count={r !== "ALL" ? regimeCounts[r] : undefined}
            onClick={() => setRegime(r)} />
        ))}

        <span className="mx-1 h-3 w-px bg-[var(--color-space-border)]" />
        <span className="font-mono text-[8px] tracking-[0.15em] text-[var(--color-text-tertiary)]">TYPE</span>
        {TYPES.map(t => (
          <Pill key={t}
            label={t === "ROCKET_BODY" ? "R/B" : t === "PAYLOAD" ? "SAT" : t === "DEBRIS" ? "DEB" : t}
            active={type === t}
            color={t !== "ALL" ? TYPE_COLOR[t] : undefined}
            onClick={() => setType(t)} />
        ))}

        <span className="ml-auto font-mono text-[9px] tabular-nums text-[var(--color-text-tertiary)]">
          {total > 0 ? `${total.toLocaleString()} results` : isFetching ? "Loading…" : ""}
        </span>
      </div>

      {/* ── Table header ────────────────────────────────────────────────── */}
      <div className="grid grid-cols-[64px_1fr_44px_64px_68px_60px_36px] shrink-0 items-center gap-2 border-b border-[var(--color-space-border-strong)] bg-[var(--color-space-navy)] px-4 py-1">
        {["NORAD", "NAME", "TYPE", "REGIME", "ALT", "INC", "CC"].map(h => (
          <span key={h} className="font-mono text-[8px] tracking-[0.1em] text-[var(--color-text-tertiary)]">{h}</span>
        ))}
      </div>

      {/* ── Table body ──────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && objects.length === 0 ? (
          <div className="flex h-32 items-center justify-center gap-2">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#6366f1]" />
            <span className="font-mono text-[10px] text-[var(--color-text-tertiary)]">
              Loading {totalInDB > 0 ? totalInDB.toLocaleString() : "29,198"} satellites…
            </span>
          </div>
        ) : isError ? (
          <div className="flex h-32 flex-col items-center justify-center gap-2">
            <span className="font-mono text-[10px] text-[var(--color-accent-amber)]">⚠ Catalog endpoint unavailable</span>
            <span className="font-mono text-[9px] text-[var(--color-text-tertiary)]">
              Railway backend is deploying — reload in 30 seconds
            </span>
          </div>
        ) : objects.length === 0 ? (
          <div className="flex h-32 items-center justify-center">
            <span className="font-mono text-[10px] text-[var(--color-text-tertiary)]">No satellites match current filters</span>
          </div>
        ) : (
          objects.map(s => <SatRow key={s.norad_id} s={s} />)
        )}
      </div>

      {/* ── Pagination ──────────────────────────────────────────────────── */}
      {pageCount > 1 && (
        <div className="flex shrink-0 items-center justify-between border-t border-[var(--color-space-border)] bg-[var(--color-space-midnight)] px-4 py-2">
          <span className="font-mono text-[9px] text-[var(--color-text-tertiary)]">
            {(page * PAGE_SIZE + 1).toLocaleString()}–{Math.min((page + 1) * PAGE_SIZE, total).toLocaleString()} of {total.toLocaleString()}
          </span>
          <div className="flex items-center gap-1">
            <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
              className="rounded border border-[var(--color-space-border)] px-2 py-0.5 font-mono text-[9px] text-[var(--color-text-secondary)] disabled:opacity-30 hover:border-[#6366f1] transition-colors">
              ← Prev
            </button>
            {Array.from({ length: Math.min(5, pageCount) }, (_, i) => {
              const p = Math.max(0, Math.min(page - 2, pageCount - 5)) + i;
              return (
                <button key={p} onClick={() => setPage(p)}
                  className="rounded border px-2 py-0.5 font-mono text-[9px] transition-colors"
                  style={{
                    borderColor:     p === page ? "#6366f1" : "var(--color-space-border)",
                    color:           p === page ? "#818cf8" : "var(--color-text-secondary)",
                    backgroundColor: p === page ? "rgba(99,102,241,0.15)" : "transparent",
                  }}>
                  {p + 1}
                </button>
              );
            })}
            <button onClick={() => setPage(p => Math.min(pageCount - 1, p + 1))} disabled={page === pageCount - 1}
              className="rounded border border-[var(--color-space-border)] px-2 py-0.5 font-mono text-[9px] text-[var(--color-text-secondary)] disabled:opacity-30 hover:border-[#6366f1] transition-colors">
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
