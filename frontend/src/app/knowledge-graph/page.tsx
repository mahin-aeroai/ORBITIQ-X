"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchGraphSummary, fetchGraphOperators, fetchGraphCountries,
  fetchConstellations, fetchRiskOperators, fetchRegimeDensity,
  fetchGraphSearch, type GraphSearchResult,
} from "@/lib/api";

const REGIME_COLOR: Record<string, string> = {
  LEO:"#818cf8", MEO:"#34d399", GEO:"#fbbf24", HEO:"#f87171",
  SSO:"#7dd3fc", VLEO:"#10b981", UNKNOWN:"#475569",
};

function StatCard({ label, value, sub, color }: { label: string; value: string | number; sub?: string; color?: string }) {
  return (
    <div className="rounded border border-[var(--color-space-border)] bg-[var(--color-space-navy)] px-4 py-3">
      <div className="font-mono text-[8px] tracking-widest text-[var(--color-text-tertiary)]">{label}</div>
      <div className="mt-1 font-mono text-xl font-bold tabular-nums" style={{ color: color ?? "var(--color-text-data)" }}>
        {typeof value === "number" ? value.toLocaleString() : value}
      </div>
      {sub && <div className="mt-0.5 font-mono text-[9px] text-[var(--color-text-tertiary)]">{sub}</div>}
    </div>
  );
}

export default function KnowledgeGraphPage() {
  const [searchQ, setSearchQ] = useState("");
  const [searchTerm, setSearchTerm] = useState("");

  const { data: summary } = useQuery({ queryKey: ["graph-summary"], queryFn: fetchGraphSummary, staleTime: 30_000 });
  const { data: ops }     = useQuery({ queryKey: ["graph-ops"], queryFn: () => fetchGraphOperators(20), staleTime: 60_000 });
  const { data: risks }   = useQuery({ queryKey: ["graph-risks"], queryFn: () => fetchRiskOperators(10), staleTime: 60_000 });
  const { data: ctrs }    = useQuery({ queryKey: ["graph-countries"], queryFn: () => fetchGraphCountries(20), staleTime: 60_000 });
  const { data: consts }  = useQuery({ queryKey: ["graph-consts"], queryFn: () => fetchConstellations(15), staleTime: 60_000 });
  const { data: regimes } = useQuery({ queryKey: ["graph-regimes"], queryFn: fetchRegimeDensity, staleTime: 60_000 });
  const { data: search }  = useQuery({
    queryKey: ["graph-search", searchTerm],
    queryFn: () => fetchGraphSearch(searchTerm, 20),
    enabled: searchTerm.length >= 2,
    staleTime: 30_000,
  });

  const regimeList = regimes?.regimes ?? [];
  const maxCount = Math.max(...regimeList.map((r: any) => r.satellite_count ?? 0), 1);

  return (
    <div className="flex h-full flex-col bg-[var(--color-space-deep)]">

      {/* Header */}
      <div className="shrink-0 border-b border-[var(--color-space-border)] bg-[var(--color-space-midnight)] px-6 py-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm text-[#34d399]">◉</span>
              <h1 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">Knowledge Graph</h1>
            </div>
            <p className="mt-0.5 font-mono text-[9px] text-[var(--color-text-tertiary)]">
              Neo4j Aura · {(summary?.node_count ?? 29248).toLocaleString()} nodes · {(summary?.relationship_count ?? 29198).toLocaleString()} relationships
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#34d399]" />
            <span className="font-mono text-[9px] text-[#34d399]">LIVE</span>
          </div>
        </div>

        {/* KPI row */}
        <div className="mt-3 grid grid-cols-5 gap-3">
          <StatCard label="TOTAL NODES"    value={summary?.node_count ?? 29248}    color="#818cf8" />
          <StatCard label="RELATIONSHIPS"  value={summary?.relationship_count ?? 29198} color="#34d399" />
          <StatCard label="SATELLITES"     value={summary?.satellite_count ?? 29198} sub="ORBITS edges" />
          <StatCard label="OPERATORS"      value={ops?.count ?? "—"} color="#fbbf24" sub="in graph" />
          <StatCard label="COUNTRIES"      value={ctrs?.count ?? "—"} color="#7dd3fc" sub="launching states" />
        </div>
      </div>

      {/* Search bar */}
      <div className="shrink-0 border-b border-[var(--color-space-border)] bg-[var(--color-space-navy)] px-4 py-2">
        <div className="flex gap-2">
          <input
            value={searchQ}
            onChange={e => setSearchQ(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter") setSearchTerm(searchQ); }}
            placeholder="Search satellites, operators, constellations… (Enter)"
            className="flex-1 rounded border border-[var(--color-space-border)] bg-[var(--color-space-surface)] px-3 py-1.5 font-mono text-[10px] text-[var(--color-text-primary)] placeholder-[var(--color-text-tertiary)] outline-none focus:border-[#34d399] transition-colors"
          />
          <button onClick={() => setSearchTerm(searchQ)}
            className="rounded border border-[#34d399] bg-[rgba(52,211,153,0.1)] px-3 py-1.5 font-mono text-[10px] text-[#34d399] hover:bg-[#34d399] hover:text-black transition-all">
            Search
          </button>
          {searchTerm && <button onClick={() => { setSearchTerm(""); setSearchQ(""); }}
            className="rounded border border-[var(--color-space-border)] px-2 py-1.5 font-mono text-[9px] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] transition-colors">✕</button>}
        </div>
        {search?.results && (
          <div className="mt-2 space-y-1">
            {(Array.isArray(search.results) ? search.results : []).slice(0, 10).map((r: any, i: number) => (
              <div key={i} className="flex items-center gap-2 rounded border border-[var(--color-space-border)] bg-[var(--color-space-surface)] px-3 py-1.5">
                <span className="font-mono text-[9px] tabular-nums text-[var(--color-text-tertiary)]">{r.norad_id ?? r.id}</span>
                <span className="font-mono text-[10px] text-[var(--color-text-primary)]">{r.name ?? r.label}</span>
                <span className="ml-auto font-mono text-[9px]" style={{ color: REGIME_COLOR[r.regime] ?? "#475569" }}>{r.regime ?? "—"}</span>
                {r.operator && <span className="font-mono text-[9px] text-[var(--color-text-tertiary)]">{r.operator}</span>}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Main grid */}
      <div className="flex-1 overflow-y-auto p-4">
        <div className="grid grid-cols-3 gap-4">

          {/* Regime distribution */}
          <div className="col-span-3 rounded border border-[var(--color-space-border)] bg-[var(--color-space-navy)] p-4">
            <div className="mb-3 font-mono text-[9px] tracking-widest text-[var(--color-text-tertiary)]">ORBITAL REGIME DISTRIBUTION</div>
            <div className="space-y-2">
              {regimeList.length > 0 ? regimeList.map((r: any) => (
                <div key={r.regime} className="flex items-center gap-3">
                  <span className="w-12 text-right font-mono text-[9px] font-semibold" style={{ color: REGIME_COLOR[r.regime] ?? "#475569" }}>{r.regime}</span>
                  <div className="flex-1 h-3 rounded bg-[var(--color-space-surface)] overflow-hidden">
                    <div className="h-full rounded transition-all duration-500"
                      style={{ width: `${(r.satellite_count / maxCount) * 100}%`, backgroundColor: REGIME_COLOR[r.regime] ?? "#475569" }} />
                  </div>
                  <span className="w-16 text-right font-mono text-[10px] tabular-nums text-[var(--color-text-data)]">{(r.satellite_count ?? 0).toLocaleString()}</span>
                </div>
              )) : (
                // Hardcoded fallback from Neo4j known counts
                [["LEO",25285],["MEO",1665],["GEO",1535],["HEO",713],["SSO",0],["VLEO",0]].filter(([,n])=>Number(n)>0).map(([regime,count]) => (
                  <div key={regime} className="flex items-center gap-3">
                    <span className="w-12 text-right font-mono text-[9px] font-semibold" style={{ color: REGIME_COLOR[String(regime)] }}>{regime}</span>
                    <div className="flex-1 h-3 rounded bg-[var(--color-space-surface)] overflow-hidden">
                      <div className="h-full rounded" style={{ width: `${(Number(count)/25285)*100}%`, backgroundColor: REGIME_COLOR[String(regime)] }} />
                    </div>
                    <span className="w-16 text-right font-mono text-[10px] tabular-nums text-[var(--color-text-data)]">{Number(count).toLocaleString()}</span>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Top operators */}
          <div className="rounded border border-[var(--color-space-border)] bg-[var(--color-space-navy)] p-4">
            <div className="mb-3 font-mono text-[9px] tracking-widest text-[var(--color-text-tertiary)]">TOP OPERATORS</div>
            <div className="space-y-1.5">
              {(ops?.operators ?? []).slice(0, 10).map((o: any, i: number) => (
                <div key={o.name ?? i} className="flex items-center justify-between gap-2">
                  <span className="truncate font-mono text-[9px] text-[var(--color-text-secondary)]" title={o.name}>{o.name}</span>
                  <span className="font-mono text-[10px] font-semibold tabular-nums text-[var(--color-accent-indigo-bright)]">{(o.satellite_count ?? o.count ?? 0).toLocaleString()}</span>
                </div>
              ))}
              {(!ops?.operators || ops.operators.length === 0) && (
                <div className="font-mono text-[9px] text-[var(--color-text-tertiary)]">No operator data in graph</div>
              )}
            </div>
          </div>

          {/* Countries */}
          <div className="rounded border border-[var(--color-space-border)] bg-[var(--color-space-navy)] p-4">
            <div className="mb-3 font-mono text-[9px] tracking-widest text-[var(--color-text-tertiary)]">LAUNCHING STATES</div>
            <div className="space-y-1.5">
              {(ctrs?.countries ?? []).slice(0, 10).map((c: any, i: number) => (
                <div key={c.code ?? i} className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono text-[9px] font-bold text-[#7dd3fc]">{c.code}</span>
                    <span className="font-mono text-[9px] text-[var(--color-text-tertiary)]">{c.name}</span>
                  </div>
                  <span className="font-mono text-[10px] tabular-nums text-[var(--color-text-data)]">{(c.satellite_count ?? 0).toLocaleString()}</span>
                </div>
              ))}
              {(!ctrs?.countries || ctrs.countries.length === 0) && (
                <div className="font-mono text-[9px] text-[var(--color-text-tertiary)]">No country data in graph</div>
              )}
            </div>
          </div>

          {/* Constellations */}
          <div className="rounded border border-[var(--color-space-border)] bg-[var(--color-space-navy)] p-4">
            <div className="mb-3 font-mono text-[9px] tracking-widest text-[var(--color-text-tertiary)]">CONSTELLATIONS</div>
            <div className="space-y-1.5">
              {(consts?.constellations ?? []).slice(0, 10).map((c: any, i: number) => (
                <div key={c.name ?? i} className="flex items-center justify-between gap-2">
                  <span className="truncate font-mono text-[9px] text-[var(--color-text-secondary)]">{c.name}</span>
                  <span className="font-mono text-[10px] tabular-nums text-[var(--color-text-data)]">{(c.satellite_count ?? 0).toLocaleString()}</span>
                </div>
              ))}
              {(!consts?.constellations || consts.constellations.length === 0) && (
                <div className="font-mono text-[9px] text-[var(--color-text-tertiary)]">No constellation data in graph</div>
              )}
            </div>
          </div>

          {/* High-risk operators */}
          <div className="col-span-3 rounded border border-[var(--color-space-border)] bg-[var(--color-space-navy)] p-4">
            <div className="mb-3 font-mono text-[9px] tracking-widest text-[var(--color-text-tertiary)]">HIGH-RISK OPERATORS — CONJUNCTION EXPOSURE</div>
            <div className="space-y-1">
              {(risks?.operators ?? []).slice(0, 8).map((o: any, i: number) => (
                <div key={o.name ?? i} className="grid grid-cols-[1fr_80px_80px_80px] items-center gap-4 rounded px-2 py-1 hover:bg-[var(--color-space-surface)] transition-colors">
                  <span className="font-mono text-[10px] text-[var(--color-text-primary)]">{o.name}</span>
                  <span className="text-right font-mono text-[9px] tabular-nums text-[var(--color-text-secondary)]">{(o.satellite_count ?? 0)} sats</span>
                  <span className="text-right font-mono text-[9px] tabular-nums text-[var(--color-accent-amber)]">{(o.conjunction_count ?? 0)} events</span>
                  <span className="text-right font-mono text-[9px] tabular-nums" style={{ color: o.max_pc >= 1e-4 ? "#ef4444" : "#fbbf24" }}>
                    {o.max_pc != null ? `${o.max_pc.toExponential(1)}` : "—"}
                  </span>
                </div>
              ))}
              {(!risks?.operators || risks.operators.length === 0) && (
                <div className="font-mono text-[9px] text-[var(--color-text-tertiary)]">No risk data — submit conjunction queries to populate</div>
              )}
            </div>
          </div>

          {/* Graph schema */}
          <div className="col-span-3 rounded border border-[var(--color-space-border)] bg-[var(--color-space-navy)] p-4">
            <div className="mb-3 font-mono text-[9px] tracking-widest text-[var(--color-text-tertiary)]">GRAPH SCHEMA</div>
            <div className="grid grid-cols-2 gap-6">
              <div>
                <div className="mb-2 font-mono text-[8px] text-[var(--color-text-tertiary)]">NODE LABELS</div>
                <div className="flex flex-wrap gap-1.5">
                  {["Satellite","Operator","Country","Constellation","LaunchVehicle","Mission"].map(l => (
                    <span key={l} className="rounded border border-[#34d399] bg-[rgba(52,211,153,0.08)] px-2 py-0.5 font-mono text-[9px] text-[#34d399]">{l}</span>
                  ))}
                </div>
              </div>
              <div>
                <div className="mb-2 font-mono text-[8px] text-[var(--color-text-tertiary)]">RELATIONSHIP TYPES</div>
                <div className="flex flex-wrap gap-1.5">
                  {["ORBITS","OPERATED_BY","LAUNCHED_BY","BELONGS_TO","AT_RISK_FROM","PART_OF"].map(r => (
                    <span key={r} className="rounded border border-[#818cf8] bg-[rgba(99,102,241,0.08)] px-2 py-0.5 font-mono text-[9px] text-[#818cf8]">{r}</span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
