"use client";
/**
 * ORBITIQ-X — Satellite Catalog (v0.4.0)
 * =========================================
 * 29,198 RSOs with regime/type filtering, search, and satellite detail drawer.
 */

import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchSatelliteList, fetchCatalogHealth, fetchSatelliteDetail, type CatalogSatellite } from "@/lib/api";

const RC: Record<string, string> = { LEO:"#818cf8",MEO:"#34d399",GEO:"#fbbf24",HEO:"#f87171",SSO:"#7dd3fc",VLEO:"#10b981",UNKNOWN:"#475569" };
const TC: Record<string, string> = { PAYLOAD:"#34d399",ROCKET_BODY:"#fbbf24",DEBRIS:"#ef4444",UNKNOWN:"#475569" };
const TL: Record<string, string> = { PAYLOAD:"SAT",ROCKET_BODY:"R/B",DEBRIS:"DEB",UNKNOWN:"UNK" };
const REGIME_BADGE_BG: Record<string, string> = { LEO:"rgba(129,140,248,0.12)",MEO:"rgba(52,211,153,0.12)",GEO:"rgba(251,191,36,0.12)",HEO:"rgba(248,113,113,0.12)",SSO:"rgba(125,211,252,0.12)",VLEO:"rgba(16,185,129,0.12)",UNKNOWN:"rgba(71,85,105,0.12)" };

const PAGE_SIZE = 200;
const REGIMES = ["ALL","LEO","MEO","GEO","HEO","SSO","VLEO"];
const TYPES   = ["ALL","PAYLOAD","ROCKET_BODY","DEBRIS"];

// Country code → full name lookup
const COUNTRIES: Record<string, string> = {
  US:"United States",RU:"Russia",CN:"China",FR:"France",JP:"Japan",
  IN:"India",GB:"United Kingdom",DE:"Germany",IT:"Italy",CA:"Canada",
  AU:"Australia",SG:"Singapore",KR:"South Korea",IL:"Israel",AR:"Argentina",
  AE:"UAE",SA:"Saudi Arabia",BR:"Brazil",ES:"Spain",NL:"Netherlands",
  LU:"Luxembourg",NZ:"New Zealand",NO:"Norway",SE:"Sweden",FI:"Finland",
  UA:"Ukraine",KZ:"Kazakhstan",ID:"Indonesia",TH:"Thailand",PK:"Pakistan",
  BD:"Bangladesh",NG:"Nigeria",ZA:"South Africa",MX:"Mexico",EG:"Egypt",
};

// Mission type → description
const MISSION_TYPES: Record<string, string> = {
  eo:"Earth Observation", comms:"Communications", nav:"Navigation",
  science:"Science", weather:"Weather", military:"Military",
  other:"Other", tbd:"TBD",
};

function Pill({ label, active, color, count, onClick }: {
  label: string; active: boolean; color?: string; count?: number; onClick: () => void;
}) {
  return (
    <button onClick={onClick}
      className="flex items-center gap-1 rounded border px-2 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider transition-all"
      style={{
        borderColor:     active ? (color ?? "#6366f1") : "var(--color-space-border)",
        color:           active ? (color ?? "#818cf8") : "var(--color-text-tertiary)",
        backgroundColor: active ? `${color ?? "#6366f1"}20` : "transparent",
      }}>
      {label}
      {count != null && <span className="tabular-nums opacity-70">{count>=1000?`${Math.round(count/1000)}k`:count}</span>}
    </button>
  );
}

// ─── Satellite Detail Drawer ──────────────────────────────────────────────────
function DetailDrawer({ noradId, onClose }: { noradId: number; onClose: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ["sat-detail", noradId],
    queryFn:  () => fetchSatelliteDetail(noradId),
    staleTime: 120_000,
  });

  const s = data as any;
  const regime  = s?.orbital_regime ?? s?.regime ?? "UNKNOWN";
  const objType = s?.object_type ?? "UNKNOWN";
  const rc = RC[regime]  ?? RC.UNKNOWN;
  const tc = TC[objType] ?? TC.UNKNOWN;

  return (
    <div className="flex h-full flex-col">
      {/* Drawer header */}
      <div className="flex shrink-0 items-center justify-between border-b border-[var(--color-space-border)] bg-[var(--color-space-midnight)] px-4 py-3">
        <div>
          {isLoading ? (
            <div className="h-4 w-32 animate-pulse rounded bg-[var(--color-space-surface)]" />
          ) : (
            <div className="font-mono text-[11px] font-semibold text-[var(--color-text-primary)]">{s?.name ?? "—"}</div>
          )}
          <div className="font-mono text-[9px] text-[var(--color-text-tertiary)]">NORAD {noradId}</div>
        </div>
        <button onClick={onClose} className="rounded border border-[var(--color-space-border)] px-2 py-0.5 font-mono text-[9px] text-[var(--color-text-tertiary)] hover:border-[#ef4444] hover:text-[#ef4444] transition-colors">✕ Close</button>
      </div>

      {isLoading ? (
        <div className="flex flex-1 items-center justify-center">
          <div className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#818cf8]" />
            <span className="font-mono text-[9px] text-[var(--color-text-tertiary)]">Loading…</span>
          </div>
        </div>
      ) : s ? (
        <div className="flex-1 overflow-y-auto p-4 space-y-4">

          {/* Type + regime badges */}
          <div className="flex flex-wrap gap-2">
            <span className="rounded border px-2.5 py-1 font-mono text-[9px] font-bold"
              style={{ color: tc, borderColor:`${tc}50`, backgroundColor:`${tc}15` }}>
              {TL[objType] ?? objType}
            </span>
            <span className="rounded border px-2.5 py-1 font-mono text-[9px] font-semibold"
              style={{ color: rc, borderColor:`${rc}50`, backgroundColor: REGIME_BADGE_BG[regime] }}>
              {regime}
            </span>
            {s.status && (
              <span className="rounded border border-[var(--color-space-border)] px-2.5 py-1 font-mono text-[9px] text-[var(--color-text-secondary)]">
                {s.status}
              </span>
            )}
          </div>

          {/* Identity */}
          <Section title="IDENTITY">
            <Row k="NORAD ID"      v={noradId} />
            <Row k="COSPAR ID"     v={s.cospar_id ?? s.international_designator} />
            <Row k="Name"          v={s.name} />
            <Row k="Object Type"   v={s.object_type} />
            <Row k="Mission Type"  v={MISSION_TYPES[s.mission_type] ?? s.mission_type} />
          </Section>

          {/* Ownership */}
          <Section title="OWNERSHIP">
            <Row k="Country"       v={s.country_code ? `${s.country_code} — ${COUNTRIES[s.country_code] ?? ""}` : null} />
            <Row k="Operator"      v={s.operator_name} />
          </Section>

          {/* Orbital Parameters */}
          <Section title="ORBITAL PARAMETERS">
            <Row k="Regime"        v={regime} color={rc} />
            <Row k="Perigee"       v={s.perigee_km    != null ? `${s.perigee_km.toFixed(1)} km`    : null} />
            <Row k="Apogee"        v={s.apogee_km     != null ? `${s.apogee_km.toFixed(1)} km`     : null} />
            <Row k="Mean Altitude" v={s.perigee_km != null && s.apogee_km != null ? `${((s.perigee_km + s.apogee_km)/2).toFixed(1)} km` : null} />
            <Row k="Inclination"   v={s.inclination_deg  != null ? `${s.inclination_deg.toFixed(3)}°`   : null} />
            <Row k="Period"        v={s.period_minutes   != null ? `${s.period_minutes.toFixed(2)} min`  : null} />
            <Row k="Altitude"      v={s.alt_km   != null ? `${s.alt_km.toFixed(1)} km`   : null} />
            <Row k="Speed"         v={s.speed    != null ? `${s.speed.toFixed(3)} km/s`  : null} />
            <Row k="Latitude"      v={s.lat      != null ? `${s.lat.toFixed(4)}°`        : null} />
            <Row k="Longitude"     v={s.lon      != null ? `${s.lon.toFixed(4)}°`        : null} />
          </Section>

          {/* TLE */}
          {(s.tle_line1 || s.tle_line2) && (
            <Section title="CURRENT TLE">
              <Row k="Epoch"  v={s.tle_epoch?.slice(0,19)?.replace("T"," ")} />
              <Row k="Age"    v={s.tle_age_days != null ? `${s.tle_age_days.toFixed(1)} days` : null} />
              <Row k="Source" v={s.tle_source} />
              {s.tle_line1 && (
                <div className="mt-2 rounded bg-[var(--color-space-surface)] p-2">
                  <div className="font-mono text-[8px] leading-relaxed text-[var(--color-text-tertiary)] break-all">{s.tle_line1}</div>
                  <div className="font-mono text-[8px] leading-relaxed text-[var(--color-text-tertiary)] break-all">{s.tle_line2}</div>
                </div>
              )}
            </Section>
          )}

        </div>
      ) : (
        <div className="flex flex-1 items-center justify-center">
          <span className="font-mono text-[9px] text-[var(--color-text-tertiary)]">Satellite not found in catalog</span>
        </div>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1.5 font-mono text-[8px] tracking-widest text-[var(--color-text-tertiary)]">{title}</div>
      <div className="rounded border border-[var(--color-space-border)] bg-[var(--color-space-navy)] divide-y divide-[var(--color-space-border)]">
        {children}
      </div>
    </div>
  );
}

function Row({ k, v, color }: { k: string; v: any; color?: string }) {
  if (v == null || v === "" || v === "—") return null;
  return (
    <div className="flex items-center justify-between gap-4 px-3 py-1.5">
      <span className="font-mono text-[9px] text-[var(--color-text-tertiary)] shrink-0">{k}</span>
      <span className="font-mono text-[9px] text-right" style={{ color: color ?? "var(--color-text-data)" }}>{String(v)}</span>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function CatalogPage() {
  const [regime,  setRegime]  = useState("ALL");
  const [type,    setType]    = useState("ALL");
  const [search,  setSearch]  = useState("");
  const [dbSearch,setDbSearch]= useState("");
  const [page,    setPage]    = useState(0);
  const [selected,setSelected]= useState<number | null>(null);

  useEffect(() => { const t = setTimeout(()=>setDbSearch(search),350); return ()=>clearTimeout(t); }, [search]);
  useEffect(() => { setPage(0); }, [regime, type, dbSearch]);

  const { data, isLoading, isFetching, isError } = useQuery({
    queryKey:        ["satellite-list", regime, type, dbSearch, page],
    queryFn:         () => fetchSatelliteList({
      regime: regime !== "ALL" ? regime : undefined,
      type:   type   !== "ALL" ? type   : undefined,
      search: dbSearch || undefined,
      page, limit: PAGE_SIZE,
    }),
    staleTime:       60_000, retry: 2, placeholderData: (p) => p,
  });

  const { data: health } = useQuery({ queryKey:["catalog-health"], queryFn:fetchCatalogHealth, staleTime:30_000 });

  const objects   = data?.objects ?? [];
  const total     = data?.total   ?? 0;
  const pageCount = Math.ceil(total / PAGE_SIZE);
  const totalInDB = health?.database_satellite_count ?? 0;

  return (
    <div className="flex h-full overflow-hidden bg-[var(--color-space-deep)]">
      <div className="flex min-w-0 flex-1 flex-col">

        {/* Header */}
        <div className="shrink-0 border-b border-[var(--color-space-border)] bg-[var(--color-space-midnight)] px-5 py-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-sm text-[#818cf8]">◫</span>
                <h1 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">Satellite Catalog</h1>
              </div>
              <p className="mt-0.5 font-mono text-[9px] text-[var(--color-text-tertiary)]">
                {totalInDB > 0 ? `${totalInDB.toLocaleString()} RSOs · PostgreSQL · Click row for details` : "Loading…"}
              </p>
            </div>
            <div className="flex items-center gap-1.5">
              {isFetching && <span className="h-1.5 w-1.5 animate-ping rounded-full bg-[var(--color-accent-amber)]" />}
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#34d399]" />
              <span className="font-mono text-[9px] text-[#34d399]">LIVE</span>
            </div>
          </div>

          {/* Regime bar - clickable */}
          <div className="mt-2.5 space-y-1">
            <div className="flex h-1 w-full overflow-hidden rounded-full bg-[var(--color-space-surface)]">
              {[["LEO",25285],["MEO",1665],["GEO",1535],["HEO",713]].map(([r,n])=>(
                <div key={r} title={`${r}: ${Number(n).toLocaleString()}`} onClick={()=>setRegime(regime===r?"ALL":String(r))}
                  className="h-full cursor-pointer transition-opacity hover:opacity-80"
                  style={{ width:`${(Number(n)/29198)*100}%`, backgroundColor:RC[String(r)] }} />
              ))}
            </div>
            <div className="flex gap-4">
              {[["LEO","25,285"],["MEO","1,665"],["GEO","1,535"],["HEO","713"]].map(([r,n])=>(
                <button key={r} onClick={()=>setRegime(regime===r?"ALL":r)}
                  className="flex items-center gap-1 transition-opacity hover:opacity-80">
                  <span className="h-1.5 w-1.5 rounded-full" style={{backgroundColor:RC[r]}}/>
                  <span className="font-mono text-[8px] text-[var(--color-text-tertiary)]">{r}</span>
                  <span className="font-mono text-[9px] font-semibold tabular-nums" style={{color:RC[r]}}>{n}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Filters */}
        <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-[var(--color-space-border)] bg-[var(--color-space-navy)] px-4 py-1.5">
          <input value={search} onChange={e=>setSearch(e.target.value)}
            placeholder="Name or NORAD ID…"
            className="w-44 rounded border border-[var(--color-space-border)] bg-[var(--color-space-surface)] px-2.5 py-1 font-mono text-[10px] text-[var(--color-text-primary)] placeholder-[var(--color-text-tertiary)] outline-none focus:border-[#6366f1] transition-colors" />
          <span className="h-3 w-px bg-[var(--color-space-border)]" />
          <span className="font-mono text-[8px] tracking-widest text-[var(--color-text-tertiary)]">REGIME</span>
          {REGIMES.map(r=>(
            <Pill key={r} label={r} active={regime===r} color={r!=="ALL"?RC[r]:undefined} onClick={()=>setRegime(r)} />
          ))}
          <span className="h-3 w-px bg-[var(--color-space-border)]" />
          <span className="font-mono text-[8px] tracking-widest text-[var(--color-text-tertiary)]">TYPE</span>
          {TYPES.map(t=>(
            <Pill key={t} label={t==="ROCKET_BODY"?"R/B":t==="PAYLOAD"?"SAT":t==="DEBRIS"?"DEB":t}
              active={type===t} color={t!=="ALL"?TC[t]:undefined} onClick={()=>setType(t)} />
          ))}
          <span className="ml-auto font-mono text-[9px] tabular-nums text-[var(--color-text-tertiary)]">
            {total>0?`${total.toLocaleString()} results`:isFetching?"…":""}
          </span>
        </div>

        {/* Table header */}
        <div className="grid grid-cols-[64px_1fr_44px_64px_68px_60px_36px] shrink-0 items-center gap-2 border-b border-[var(--color-space-border-strong)] bg-[var(--color-space-navy)] px-4 py-1">
          {["NORAD","NAME","TYPE","REGIME","ALT","INC","CC"].map(h=>(
            <span key={h} className="font-mono text-[8px] tracking-[0.1em] text-[var(--color-text-tertiary)]">{h}</span>
          ))}
        </div>

        {/* Table body */}
        <div className="flex-1 overflow-y-auto">
          {isLoading && objects.length===0 ? (
            <div className="flex h-32 items-center justify-center gap-2">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#818cf8]" />
              <span className="font-mono text-[10px] text-[var(--color-text-tertiary)]">Loading satellites…</span>
            </div>
          ) : isError ? (
            <div className="flex h-32 flex-col items-center justify-center gap-1">
              <span className="font-mono text-[10px] text-[var(--color-accent-amber)]">⚠ Catalog endpoint unavailable</span>
              <span className="font-mono text-[9px] text-[var(--color-text-tertiary)]">Railway redeploying — retry in 30s</span>
            </div>
          ) : objects.length===0 ? (
            <div className="flex h-32 items-center justify-center">
              <span className="font-mono text-[10px] text-[var(--color-text-tertiary)]">No satellites match filters</span>
            </div>
          ) : objects.map((s: CatalogSatellite) => {
            const rc2 = RC[s.regime]??RC.UNKNOWN;
            const tc2 = TC[s.object_type]??TC.UNKNOWN;
            const alt = s.apogee_km!=null&&s.perigee_km!=null ? Math.round((s.apogee_km+s.perigee_km)/2) : s.apogee_km!=null?Math.round(s.apogee_km):null;
            return (
              <div key={s.norad_id}
                onClick={()=>setSelected(selected===s.norad_id?null:s.norad_id)}
                className={`grid grid-cols-[64px_1fr_44px_64px_68px_60px_36px] items-center gap-2 border-b border-[var(--color-space-border)] px-4 py-1 cursor-pointer transition-colors ${selected===s.norad_id?"bg-[rgba(99,102,241,0.1)]":"hover:bg-[var(--color-space-surface)]"}`}>
                <span className="font-mono text-[9px] tabular-nums text-[var(--color-text-tertiary)]">{s.norad_id}</span>
                <span className="truncate font-mono text-[10px] text-[var(--color-text-primary)]" title={s.name}>{s.name}</span>
                <span className="rounded border px-1 py-px text-center font-mono text-[8px] font-bold"
                  style={{color:tc2,borderColor:`${tc2}60`,backgroundColor:`${tc2}15`}}>{TL[s.object_type]??"UNK"}</span>
                <span className="font-mono text-[9px] font-semibold" style={{color:rc2}}>{s.regime||"—"}</span>
                <span className="text-right font-mono text-[9px] tabular-nums" style={{color:"var(--color-text-data)"}}>{alt!=null?`${alt} km`:"—"}</span>
                <span className="text-right font-mono text-[9px] tabular-nums text-[var(--color-text-secondary)]">
                  {s.inclination_deg!=null?`${s.inclination_deg.toFixed(1)}°`:"—"}
                </span>
                <span className="text-right font-mono text-[9px] text-[var(--color-text-tertiary)]">{s.country_code??"—"}</span>
              </div>
            );
          })}
        </div>

        {/* Pagination */}
        {pageCount>1 && (
          <div className="flex shrink-0 items-center justify-between border-t border-[var(--color-space-border)] bg-[var(--color-space-midnight)] px-4 py-2">
            <span className="font-mono text-[9px] text-[var(--color-text-tertiary)]">
              {(page*PAGE_SIZE+1).toLocaleString()}–{Math.min((page+1)*PAGE_SIZE,total).toLocaleString()} of {total.toLocaleString()}
            </span>
            <div className="flex items-center gap-1">
              <button onClick={()=>setPage(p=>Math.max(0,p-1))} disabled={page===0}
                className="rounded border border-[var(--color-space-border)] px-2 py-0.5 font-mono text-[9px] disabled:opacity-30 hover:border-[#6366f1] transition-colors">← Prev</button>
              {Array.from({length:Math.min(5,pageCount)},(_,i)=>{
                const p=Math.max(0,Math.min(page-2,pageCount-5))+i;
                return (
                  <button key={p} onClick={()=>setPage(p)}
                    className="rounded border px-2 py-0.5 font-mono text-[9px] transition-colors"
                    style={{ borderColor:p===page?"#6366f1":"var(--color-space-border)", color:p===page?"#818cf8":"var(--color-text-secondary)", backgroundColor:p===page?"rgba(99,102,241,0.15)":"transparent" }}>
                    {p+1}
                  </button>
                );
              })}
              <button onClick={()=>setPage(p=>Math.min(pageCount-1,p+1))} disabled={page===pageCount-1}
                className="rounded border border-[var(--color-space-border)] px-2 py-0.5 font-mono text-[9px] disabled:opacity-30 hover:border-[#6366f1] transition-colors">Next →</button>
            </div>
          </div>
        )}
      </div>

      {/* Satellite detail drawer */}
      {selected !== null && (
        <div className="w-80 shrink-0 border-l border-[var(--color-space-border)] bg-[var(--color-space-midnight)]">
          <DetailDrawer noradId={selected} onClose={()=>setSelected(null)} />
        </div>
      )}
    </div>
  );
}
