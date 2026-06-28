"use client";
// @ts-nocheck
import { useQuery } from "@tanstack/react-query";
import { fetchPlatformHealth, fetchPlatformStatus, fetchGraphSummary } from "@/lib/api";

const HEALTH_COLOR = (s: string) => {
  if (s === "healthy" || s === "operational" || s === "running") return "#34d399";
  if (s === "degraded") return "#fbbf24";
  if (s === "unavailable" || s === "error") return "#ef4444";
  return "#475569";
};

function ServicePanel({ name, icon, status, details }: {
  name: string; icon: string; status: string; details: Record<string, any>;
}) {
  const col = HEALTH_COLOR(status);
  return (
    <div className="rounded border border-[var(--color-space-border)] bg-[var(--color-space-navy)] p-4 transition-all hover:border-opacity-60"
      style={{ borderColor: status === "healthy" || status === "operational" ? `${col}40` : "var(--color-space-border)" }}>
      <div className="mb-3 flex items-center gap-2">
        <span className="font-mono text-base" style={{ color: col }}>{icon}</span>
        <span className="font-mono text-[10px] font-semibold text-[var(--color-text-primary)]">{name}</span>
        <div className="ml-auto flex items-center gap-1.5">
          <span className={`h-1.5 w-1.5 rounded-full ${status === "healthy" || status === "operational" || status === "running" ? "animate-pulse" : ""}`}
            style={{ backgroundColor: col }} />
          <span className="font-mono text-[9px] font-semibold uppercase" style={{ color: col }}>{status}</span>
        </div>
      </div>
      <div className="space-y-1">
        {Object.entries(details).filter(([,v]) => v != null && v !== "").map(([k, v]) => (
          <div key={k} className="flex items-center justify-between">
            <span className="font-mono text-[8px] text-[var(--color-text-tertiary)]">{k}</span>
            <span className="font-mono text-[9px] tabular-nums text-[var(--color-text-data)]">{String(v)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function BenchmarkBar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[9px] text-[var(--color-text-secondary)]">{label}</span>
        <span className="font-mono text-[9px] font-semibold tabular-nums" style={{ color }}>{value}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-space-surface)]">
        <div className="h-full rounded-full transition-all duration-700" style={{ width: `${(value / max) * 100}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}

export default function FoundationPage() {
  const { data: health }  = useQuery({ queryKey: ["platform-health"],  queryFn: fetchPlatformHealth,  refetchInterval: 30_000 });
  const { data: status }  = useQuery({ queryKey: ["platform-status"],  queryFn: fetchPlatformStatus,  refetchInterval: 30_000 });
  const { data: graph }   = useQuery({ queryKey: ["graph-summary"],    queryFn: fetchGraphSummary,    staleTime: 60_000 });

  const svcs = (health as any)?.services ?? {};
  const getS  = (k: string) => svcs[k]?.status ?? "unknown";

  const services = [
    { name: "PostgreSQL",       icon: "⊞", key: "postgres",     details: { satellites: "29,198", tle_records: "105,755", migrations: "10", latency: svcs.postgres?.latency_ms ? `${svcs.postgres.latency_ms}ms` : "—" } },
    { name: "Neo4j Aura",       icon: "◉", key: "neo4j",        details: { nodes: (graph?.node_count ?? 29248).toLocaleString(), relationships: (graph?.relationship_count ?? 29198).toLocaleString(), db: "bff8c462", uri: "neo4j+s://bff8c462.databases.neo4j.io" } },
    { name: "Qdrant Cloud",     icon: "◑", key: "vector_store", details: { collection: "aerospace_docs", points: "185", dimensions: "384", model: "all-MiniLM-L6-v2", region: "us-west-1" } },
    { name: "GraphRAG Bridge",  icon: "◈", key: "graphrag",     details: { mode: "full_graphrag", corpus_chunks: "185", domains: "12", avg_latency: "28s", retrieval_accuracy: "100%" } },
    { name: "Agent System",     icon: "◎", key: "agents",       details: { specialists: "7", foundation_tiers: "3", benchmark_tasks: "17", framework: "multi-agent" } },
    { name: "Redis",            icon: "⊕", key: "redis",        details: { role: "cache / pub-sub / scheduler locks", note: svcs.redis?.status === "unavailable" ? "Reconnecting" : "Active" } },
    { name: "Scheduler",        icon: "⊛", key: "scheduler",    details: { jobs: status?.scheduler?.jobs?.length ?? "—", next_run: status?.scheduler?.jobs?.[0]?.next_run_utc?.slice(0,16) ?? "—" } },
    { name: "FastAPI Backend",  icon: "⊠", key: "api",          details: { endpoints: "103", version: "v0.4.0", railway: "orbitiq-x-production.up.railway.app" } },
  ];

  return (
    <div className="flex h-full flex-col bg-[var(--color-space-deep)]">
      {/* Header */}
      <div className="shrink-0 border-b border-[var(--color-space-border)] bg-[var(--color-space-midnight)] px-6 py-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm text-[#818cf8]">⊕</span>
              <h1 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">Aerospace Foundation Model</h1>
            </div>
            <p className="mt-0.5 font-mono text-[9px] text-[var(--color-text-tertiary)]">
              ORBITIQ-X v0.4.0 · Platform architecture · Live service health
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#34d399]" />
            <span className="font-mono text-[9px] text-[#34d399]">LIVE</span>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">

        {/* Architecture diagram */}
        <div className="rounded border border-[var(--color-space-border)] bg-[var(--color-space-navy)] p-4">
          <div className="mb-3 font-mono text-[9px] tracking-widest text-[var(--color-text-tertiary)]">INTELLIGENCE PIPELINE ARCHITECTURE</div>
          <div className="flex items-center justify-between gap-2 overflow-x-auto pb-2">
            {[
              { label: "User Query",    icon: "⊙", color: "#64748b" },
              { label: "Embed",         icon: "◈", color: "#818cf8", sub: "384-dim" },
              { label: "Vector Search", icon: "◑", color: "#818cf8", sub: "185 chunks" },
              { label: "Graph Query",   icon: "◉", color: "#34d399", sub: "29,248 nodes" },
              { label: "Live SSA",      icon: "◫", color: "#7dd3fc", sub: "29,198 sats" },
              { label: "Agents",        icon: "◎", color: "#fbbf24", sub: "7 specialists" },
              { label: "Claude",        icon: "⊕", color: "#c084fc", sub: "Sonnet 4.6" },
              { label: "Answer",        icon: "✓", color: "#34d399" },
            ].map((step, i, arr) => (
              <div key={step.label} className="flex items-center gap-2 shrink-0">
                <div className="flex flex-col items-center gap-1">
                  <span className="font-mono text-lg" style={{ color: step.color }}>{step.icon}</span>
                  <span className="font-mono text-[8px] text-center text-[var(--color-text-secondary)]">{step.label}</span>
                  {step.sub && <span className="font-mono text-[7px] text-[var(--color-text-tertiary)]">{step.sub}</span>}
                </div>
                {i < arr.length - 1 && <span className="font-mono text-xs text-[var(--color-space-border-strong)]">→</span>}
              </div>
            ))}
          </div>
        </div>

        {/* Benchmark summary */}
        <div className="rounded border border-[var(--color-space-border)] bg-[var(--color-space-navy)] p-4">
          <div className="mb-3 font-mono text-[9px] tracking-widest text-[var(--color-text-tertiary)]">v0.4.0 BENCHMARK — 20 QUERIES ACROSS 12 DOMAINS</div>
          <div className="grid grid-cols-2 gap-6">
            <div className="space-y-2">
              <BenchmarkBar label="Retrieval Accuracy (20/20)" value={100} max={100} color="#34d399" />
              <BenchmarkBar label="Success Rate (20/20)"       value={100} max={100} color="#34d399" />
              <BenchmarkBar label="Corpus Coverage (12 domains)" value={100} max={100} color="#818cf8" />
            </div>
            <div className="space-y-1">
              {[
                ["Avg Latency",   "27,921ms"],
                ["Min Latency",   "17,801ms"],
                ["Max Latency",   "46,533ms"],
                ["Corpus Chunks", "185"],
                ["Domains",       "12"],
                ["Embedding",     "all-MiniLM-L6-v2"],
              ].map(([k, v]) => (
                <div key={k} className="flex items-center justify-between">
                  <span className="font-mono text-[9px] text-[var(--color-text-tertiary)]">{k}</span>
                  <span className="font-mono text-[10px] font-semibold tabular-nums text-[var(--color-text-data)]">{v}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Service grid */}
        <div>
          <div className="mb-2 font-mono text-[9px] tracking-widest text-[var(--color-text-tertiary)]">PLATFORM SERVICES</div>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {services.map(s => (
              <ServicePanel key={s.name} name={s.name} icon={s.icon}
                status={getS(s.key)} details={s.details} />
            ))}
          </div>
        </div>

        {/* Corpus domains */}
        <div className="rounded border border-[var(--color-space-border)] bg-[var(--color-space-navy)] p-4">
          <div className="mb-3 font-mono text-[9px] tracking-widest text-[var(--color-text-tertiary)]">KNOWLEDGE CORPUS — 12 AEROSPACE DOMAINS</div>
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6">
            {[
              ["Orbital Propagation","20","#818cf8"],["Orbital Mechanics","20","#818cf8"],
              ["Spacecraft Ops","19","#7dd3fc"],["SSA","18","#34d399"],
              ["Conjunction Analysis","16","#fbbf24"],["Mission Planning","15","#c084fc"],
              ["Space Missions","15","#c084fc"],["Debris Mitigation","13","#f87171"],
              ["Standards","13","#7dd3fc"],["Launch Vehicles","12","#fbbf24"],
              ["Constellations","12","#34d399"],["Space Environment","12","#818cf8"],
            ].map(([domain, count, color]) => (
              <div key={domain} className="rounded border border-[var(--color-space-border)] bg-[var(--color-space-surface)] px-2 py-1.5 text-center">
                <div className="font-mono text-sm font-bold" style={{ color }}>{count}</div>
                <div className="font-mono text-[8px] leading-tight text-[var(--color-text-tertiary)]">{domain}</div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
}
