"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchHighRiskConjunctions, fetchSSAStatistics, fetchConjunctionNetwork,
  type ConjunctionItem,
} from "@/lib/api";

const PC_COLOR = (pc: number) => {
  if (pc >= 1e-3) return "#ef4444";
  if (pc >= 1e-4) return "#f97316";
  if (pc >= 1e-5) return "#fbbf24";
  return "#34d399";
};
const PC_LABEL = (pc: number) => {
  if (pc >= 1e-3) return "CRITICAL";
  if (pc >= 1e-4) return "HIGH";
  if (pc >= 1e-5) return "ELEVATED";
  return "NOMINAL";
};
const fmtPc = (pc: number) => {
  if (!pc) return "—";
  const exp = Math.floor(Math.log10(pc));
  const man = pc / Math.pow(10, exp);
  return `${man.toFixed(2)}×10⁻${Math.abs(exp)}`;
};

function ConjunctionRow({ c }: { c: ConjunctionItem }) {
  const [open, setOpen] = useState(false);
  const pc = c.max_pc ?? c.pc ?? 0;
  const col = PC_COLOR(pc);
  return (
    <div className="border-b border-[var(--color-space-border)] transition-colors hover:bg-[var(--color-space-surface)]">
      <button onClick={() => setOpen(o => !o)} className="grid w-full grid-cols-[28px_1fr_1fr_110px_110px_90px_80px] items-center gap-2 px-4 py-2 text-left">
        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: col }} />
        <span className="truncate font-mono text-[10px] text-[var(--color-text-primary)]">{c.object1_name ?? c.primary_object ?? "—"}</span>
        <span className="truncate font-mono text-[10px] text-[var(--color-text-secondary)]">{c.object2_name ?? c.secondary_object ?? "—"}</span>
        <span className="text-right font-mono text-[10px] font-semibold tabular-nums" style={{ color: col }}>{fmtPc(pc)}</span>
        <span className="text-right font-mono text-[10px] tabular-nums text-[var(--color-text-data)]">
          {c.miss_distance_km != null ? `${c.miss_distance_km.toFixed(3)} km` : "—"}
        </span>
        <span className="text-right font-mono text-[9px]" style={{ color: col }}>{PC_LABEL(pc)}</span>
        <span className="text-right font-mono text-[9px] text-[var(--color-text-tertiary)]">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="grid grid-cols-2 gap-x-8 gap-y-1 border-t border-[var(--color-space-border)] bg-[var(--color-space-navy)] px-8 py-3">
          {[
            ["TCA", c.tca ?? c.time_of_closest_approach ?? "—"],
            ["Relative Speed", c.relative_speed_km_s != null ? `${c.relative_speed_km_s.toFixed(2)} km/s` : "—"],
            ["NORAD 1", c.norad_id_1 ?? "—"],
            ["NORAD 2", c.norad_id_2 ?? "—"],
            ["Object Type 1", c.object1_type ?? "—"],
            ["Object Type 2", c.object2_type ?? "—"],
            ["Pc", fmtPc(pc)],
            ["Status", c.status ?? "—"],
          ].map(([k, v]) => (
            <div key={k} className="flex items-center justify-between">
              <span className="font-mono text-[9px] text-[var(--color-text-tertiary)]">{k}</span>
              <span className="font-mono text-[10px] text-[var(--color-text-data)]">{String(v)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ConjunctionsPage() {
  const [minPc, setMinPc] = useState("1e-5");

  const { data: stats } = useQuery({ queryKey: ["ssa-stats"], queryFn: fetchSSAStatistics, refetchInterval: 30_000 });
  const { data: conj, isLoading } = useQuery({
    queryKey: ["conjunctions", minPc],
    queryFn: () => fetchHighRiskConjunctions(100),
    refetchInterval: 60_000,
  });

  const items = conj?.events ?? conj?.conjunctions ?? [];
  const filtered = items.filter((c: ConjunctionItem) => {
    const pc = c.max_pc ?? c.pc ?? 0;
    return pc >= parseFloat(minPc);
  });

  return (
    <div className="flex h-full flex-col bg-[var(--color-space-deep)]">
      {/* Header */}
      <div className="shrink-0 border-b border-[var(--color-space-border)] bg-[var(--color-space-midnight)] px-6 py-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm text-[var(--color-accent-amber)]">⚠</span>
              <h1 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">Conjunction Analysis</h1>
            </div>
            <p className="mt-0.5 font-mono text-[9px] text-[var(--color-text-tertiary)]">
              Real-time collision probability assessment · {filtered.length} events above threshold
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-accent-green-bright)]" />
            <span className="font-mono text-[9px] text-[var(--color-accent-green-bright)]">LIVE</span>
          </div>
        </div>

        {/* KPI row */}
        <div className="mt-3 grid grid-cols-4 gap-3">
          {[
            { label: "Total Events", value: stats?.total_events ?? 0, color: "var(--color-text-data)" },
            { label: "Red (≥1e-4)", value: stats?.red_count ?? 0, color: "#ef4444" },
            { label: "Yellow (≥1e-5)", value: stats?.yellow_count ?? 0, color: "#fbbf24" },
            { label: "Max Pc", value: stats?.max_pc != null ? fmtPc(stats.max_pc) : "—", color: stats?.max_pc >= 1e-4 ? "#ef4444" : "#34d399" },
          ].map(({ label, value, color }) => (
            <div key={label} className="rounded border border-[var(--color-space-border)] bg-[var(--color-space-navy)] px-3 py-2">
              <div className="font-mono text-[8px] text-[var(--color-text-tertiary)]">{label}</div>
              <div className="font-mono text-base font-bold tabular-nums" style={{ color }}>{String(value)}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex shrink-0 items-center gap-3 border-b border-[var(--color-space-border)] bg-[var(--color-space-navy)] px-4 py-2">
        <span className="font-mono text-[8px] tracking-widest text-[var(--color-text-tertiary)]">MIN Pc</span>
        {[["1e-3","CRITICAL","#ef4444"],["1e-4","HIGH","#f97316"],["1e-5","ELEVATED","#fbbf24"],["1e-6","ALL","#34d399"]].map(([val, label, color]) => (
          <button key={val} onClick={() => setMinPc(val)}
            className="rounded border px-2.5 py-0.5 font-mono text-[9px] font-semibold transition-all"
            style={{
              borderColor: minPc === val ? color : "var(--color-space-border)",
              color: minPc === val ? color : "var(--color-text-tertiary)",
              backgroundColor: minPc === val ? `${color}20` : "transparent",
            }}>{label} ({val})</button>
        ))}
        <span className="ml-auto font-mono text-[9px] text-[var(--color-text-tertiary)]">{filtered.length} events</span>
      </div>

      {/* Table header */}
      <div className="grid grid-cols-[28px_1fr_1fr_110px_110px_90px_80px] shrink-0 items-center gap-2 border-b border-[var(--color-space-border-strong)] bg-[var(--color-space-navy)] px-4 py-1">
        {["","OBJECT 1","OBJECT 2","Pc","MISS DIST","RISK",""].map((h,i) => (
          <span key={i} className="font-mono text-[8px] tracking-[0.1em] text-[var(--color-text-tertiary)]">{h}</span>
        ))}
      </div>

      {/* Table body */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex h-32 items-center justify-center gap-2">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-accent-amber)]" />
            <span className="font-mono text-[10px] text-[var(--color-text-tertiary)]">Loading conjunction events…</span>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex h-48 flex-col items-center justify-center gap-2">
            <span className="text-2xl">✓</span>
            <span className="font-mono text-xs text-[var(--color-accent-green-bright)]">No high-risk conjunctions above Pc {minPc}</span>
            <span className="font-mono text-[9px] text-[var(--color-text-tertiary)]">All tracked objects below alert threshold</span>
          </div>
        ) : (
          filtered.map((c: ConjunctionItem, i: number) => <ConjunctionRow key={c.id ?? i} c={c} />)
        )}
      </div>
    </div>
  );
}
