"use client";
// @ts-nocheck
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchHighRiskConjunctions, fetchSSAStatistics, type ConjunctionItem } from "@/lib/api";

const PC_COLOR = (pc: number) => pc >= 1e-3 ? "#ef4444" : pc >= 1e-4 ? "#f97316" : pc >= 1e-5 ? "#fbbf24" : "#34d399";
const PC_LABEL = (pc: number) => pc >= 1e-3 ? "CRITICAL" : pc >= 1e-4 ? "HIGH" : pc >= 1e-5 ? "ELEVATED" : "NOMINAL";
const fmtPc = (pc: number) => {
  if (!pc) return "—";
  const exp = Math.floor(Math.log10(pc));
  return `${(pc / Math.pow(10, exp)).toFixed(2)}×10⁻${Math.abs(exp)}`;
};

function ConjRow({ c }: { c: ConjunctionItem }) {
  const [open, setOpen] = useState(false);
  const pc = c.collision_probability ?? 0;
  const col = PC_COLOR(pc);
  return (
    <div className="border-b border-[var(--color-space-border)] hover:bg-[var(--color-space-surface)] transition-colors">
      <button onClick={() => setOpen(o => !o)}
        className="grid w-full grid-cols-[20px_1fr_1fr_110px_110px_90px_24px] items-center gap-2 px-4 py-2 text-left">
        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: col }} />
        <span className="truncate font-mono text-[10px] text-[var(--color-text-primary)]">{c.primary?.name ?? `NORAD-${c.primary?.norad}`}</span>
        <span className="truncate font-mono text-[10px] text-[var(--color-text-secondary)]">{c.secondary?.name ?? `NORAD-${c.secondary?.norad}`}</span>
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
            ["TCA", c.tca ?? "—"],
            ["Relative Velocity", c.relative_velocity_kms != null ? `${c.relative_velocity_kms.toFixed(2)} km/s` : "—"],
            ["NORAD 1", c.primary?.norad ?? "—"],
            ["NORAD 2", c.secondary?.norad ?? "—"],
            ["Object Type 1", c.primary?.type ?? "—"],
            ["Object Type 2", c.secondary?.type ?? "—"],
            ["Risk Level", c.risk_level ?? "—"],
            ["Maneuver Required", c.maneuver_required ? "YES" : "NO"],
            ["Recommended ΔV", c.recommended_dv_kms != null ? `${c.recommended_dv_kms.toFixed(4)} km/s` : "—"],
            ["Maneuver Window", c.maneuver_window_hours_remaining != null ? `${c.maneuver_window_hours_remaining.toFixed(1)}h remaining` : "—"],
          ].map(([k, v]) => (
            <div key={String(k)} className="flex items-center justify-between">
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
    queryKey: ["conjunctions"],
    queryFn: () => fetchHighRiskConjunctions(200),
    refetchInterval: 60_000,
  });

  const items: ConjunctionItem[] = conj?.items ?? [];
  const filtered = items.filter(c => (c.collision_probability ?? 0) >= parseFloat(minPc));

  return (
    <div className="flex h-full flex-col bg-[var(--color-space-deep)]">
      <div className="shrink-0 border-b border-[var(--color-space-border)] bg-[var(--color-space-midnight)] px-6 py-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm text-[var(--color-accent-amber)]">⚠</span>
              <h1 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">Conjunction Analysis</h1>
            </div>
            <p className="mt-0.5 font-mono text-[9px] text-[var(--color-text-tertiary)]">
              Collision probability assessment · {filtered.length} events above Pc {minPc}
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#34d399]" />
            <span className="font-mono text-[9px] text-[#34d399]">LIVE</span>
          </div>
        </div>
        <div className="mt-3 grid grid-cols-4 gap-3">
          {[
            { label: "Total Events", value: stats?.total_events ?? 0, color: "var(--color-text-data)" },
            { label: "Red (≥1e-4)",  value: stats?.red_count ?? 0,   color: "#ef4444" },
            { label: "Yellow (≥1e-5)",value:stats?.yellow_count ?? 0, color: "#fbbf24" },
            { label: "Max Pc", value: stats?.max_pc != null ? fmtPc(stats.max_pc) : "—",
              color: (stats?.max_pc ?? 0) >= 1e-4 ? "#ef4444" : "#34d399" },
          ].map(({ label, value, color }) => (
            <div key={label} className="rounded border border-[var(--color-space-border)] bg-[var(--color-space-navy)] px-3 py-2">
              <div className="font-mono text-[8px] text-[var(--color-text-tertiary)]">{label}</div>
              <div className="font-mono text-base font-bold tabular-nums" style={{ color }}>{String(value)}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-3 border-b border-[var(--color-space-border)] bg-[var(--color-space-navy)] px-4 py-2">
        <span className="font-mono text-[8px] tracking-widest text-[var(--color-text-tertiary)]">MIN Pc</span>
        {[["1e-3","CRITICAL","#ef4444"],["1e-4","HIGH","#f97316"],["1e-5","ELEVATED","#fbbf24"],["1e-6","ALL","#34d399"]].map(([val, label, color]) => (
          <button key={val} onClick={() => setMinPc(val)}
            className="rounded border px-2.5 py-0.5 font-mono text-[9px] font-semibold transition-all"
            style={{ borderColor: minPc===val ? color : "var(--color-space-border)", color: minPc===val ? color : "var(--color-text-tertiary)", backgroundColor: minPc===val ? `${color}20` : "transparent" }}>
            {label} ({val})
          </button>
        ))}
        <span className="ml-auto font-mono text-[9px] text-[var(--color-text-tertiary)]">{filtered.length} events</span>
      </div>

      <div className="grid grid-cols-[20px_1fr_1fr_110px_110px_90px_24px] shrink-0 items-center gap-2 border-b border-[var(--color-space-border-strong)] bg-[var(--color-space-navy)] px-4 py-1">
        {["","OBJECT 1","OBJECT 2","Pc","MISS DIST","RISK",""].map((h, i) => (
          <span key={i} className="font-mono text-[8px] tracking-[0.1em] text-[var(--color-text-tertiary)]">{h}</span>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex h-32 items-center justify-center gap-2">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#fbbf24]" />
            <span className="font-mono text-[10px] text-[var(--color-text-tertiary)]">Loading conjunction events…</span>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex h-48 flex-col items-center justify-center gap-2">
            <span className="text-2xl">✓</span>
            <span className="font-mono text-xs text-[#34d399]">No conjunctions above Pc {minPc}</span>
            <span className="font-mono text-[9px] text-[var(--color-text-tertiary)]">All tracked objects below alert threshold</span>
          </div>
        ) : filtered.map((c, i) => <ConjRow key={c.id ?? i} c={c} />)}
      </div>
    </div>
  );
}
