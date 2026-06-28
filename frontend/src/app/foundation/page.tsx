"use client";
// @ts-nocheck
import { useQuery } from "@tanstack/react-query";
import { fetchPlatformHealth, fetchPlatformStatus, fetchGraphSummary } from "@/lib/api";

const HC = (s) => {
  if (s === "healthy" || s === "operational" || s === "running") return "#34d399";
  if (s === "degraded" || s === "partial") return "#fbbf24";
  if (s === "unavailable" || s === "error" || s === "not_initialised") return "#ef4444";
  return "#475569";
};

function ServicePanel({ name, icon, status, details }) {
  const col = HC(status);
  const isOk = ["healthy","operational","running"].includes(status);
  return (
    <div className="rounded border bg-[var(--color-space-navy)] p-4 transition-all"
      style={{ borderColor: isOk ? `${col}40` : "var(--color-space-border)" }}>
      <div className="mb-3 flex items-center gap-2">
        <span className="font-mono text-base" style={{ color: col }}>{icon}</span>
        <span className="font-mono text-[10px] font-semibold text-[var(--color-text-primary)]">{name}</span>
        <div className="ml-auto flex items-center gap-1.5">
          <span className={`h-1.5 w-1.5 rounded-full ${isOk ? "animate-pulse" : ""}`} style={{ backgroundColor: col }} />
          <span className="font-mono text-[9px] font-semibold uppercase" style={{ color: col }}>{status}</span>
        </div>
      </div>
      <div className="space-y-1">
        {Object.entries(details).filter(([,v]) => v != null && v !== "").map(([k, v]) => (
          <div key={k} className="flex items-center justify-between">
            <span className="font-mono text-[8px] text-[var(--color-text-tertiary)]">{k}</span>
            <span className="font-mono text-[9px] tabular-nums" style={{ color: String(v).includes("✓") ? "#34d399" : String(v).includes("✗") ? "#ef4444" : "var(--color-text-data)" }}>{String(v)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function BenchmarkBar({ label, value, color }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[9px] text-[var(--color-text-secondary)]">{label}</span>
        <span className="font-mono text-[9px] font-semibold tabular-nums" style={{ color }}>{value}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-space-surface)]">
        <div className="h-full rounded-full transition-all duration-700" style={{ width:`${value}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}

export default function FoundationPage() {
  const { data: health }  = useQuery({ queryKey:["platform-health"],  queryFn:fetchPlatformHealth,  refetchInterval:30_000 });
  const { data: status }  = useQuery({ queryKey:["platform-status"],  queryFn:fetchPlatformStatus,  refetchInterval:30_000 });
  const { data: graph }   = useQuery({ queryKey:["graph-summary"],    queryFn:fetchGraphSummary,    staleTime:60_000 });

  const svcs = (health as any)?.services ?? {};
  const getS = (k) => {
    const v = svcs[k];
    if (!v) return "unknown";
    return v.status ?? "unknown";
  };
  const getV = (k, field) => svcs[k]?.[field];

  const catalogStatus = (status as any)?.catalog ?? {};
  const dtStatus      = (status as any)?.digital_twin ?? {};

  const services = [
    {
      name:"PostgreSQL", icon:"⊞", key:"postgres",
      details:{
        "Satellites":   "29,198",
        "Object types": "SAT 17,946 · DEB 8,392 · R/B 2,091",
        "Migrations":   "10",
        "Latency":      getV("postgres","latency_ms") ? `${getV("postgres","latency_ms")}ms` : "—",
      }
    },
    {
      name:"Neo4j Aura", icon:"◉", key:"neo4j",
      details:{
        "Nodes":         (graph?.node_count ?? 29248).toLocaleString(),
        "Relationships": (graph?.relationship_count ?? 29198).toLocaleString(),
        "Enrichment":    "Operators + Countries populating",
        "Latency":       getV("neo4j","latency_ms") ? `${getV("neo4j","latency_ms")}ms` : "—",
      }
    },
    {
      name:"Qdrant Cloud", icon:"◑", key:"vector_store",
      details:{
        "Collection": "aerospace_docs",
        "Points":     "185",
        "Dimensions": "384",
        "Model":      "all-MiniLM-L6-v2",
        "Mode":       "full_graphrag",
      }
    },
    {
      name:"GraphRAG Bridge", icon:"◈", key:"graphrag",
      details:{
        "Mode":             "full_graphrag",
        "Corpus chunks":    "185",
        "Domains":          "12",
        "Avg latency":      "~10-28s",
        "Retrieval":        "100% (v0.4.0 benchmark)",
      }
    },
    {
      name:"Agent System", icon:"◎", key:"agents",
      details:{
        "Specialists":      "7",
        "Foundation tiers": "3",
        "Benchmark tasks":  "17",
        "Framework":        "LangGraph + Claude",
      }
    },
    {
      name:"Digital Twin", icon:"◫", key:"digital_twin",
      details:{
        "Status":       getS("digital_twin"),
        "Live objects": dtStatus?.live_objects ?? 0,
        "Note":         "Activate via POST /catalog/sync",
      }
    },
    {
      name:"Redis", icon:"⊕", key:"redis",
      details:{
        "Role":   "cache · pub-sub · scheduler locks",
        "Status": getS("redis") === "unavailable" ? "✗ Reconnecting" : "✓ Active",
      }
    },
    {
      name:"Scheduler", icon:"⊛", key:"scheduler",
      details:{
        "Jobs":          (status as any)?.scheduler?.jobs?.length ?? 5,
        "Next Neo4j pop":(status as any)?.scheduler?.jobs?.find(j=>j.name?.includes("Graph"))?.next_run_utc?.slice(0,16) ?? "—",
        "Next TLE":      (status as any)?.scheduler?.jobs?.find(j=>j.name?.includes("TLE"))?.next_run_utc?.slice(0,16) ?? "—",
      }
    },
  ];

  // Overall platform status
  const healthyCount = services.filter(s => ["healthy","operational","running"].includes(getS(s.key))).length;
  const totalCount   = services.length;
  const overallOk    = healthyCount >= totalCount - 2; // Redis + Digital Twin can be down

  return (
    <div className="flex h-full flex-col bg-[var(--color-space-deep)]">
      <div className="shrink-0 border-b border-[var(--color-space-border)] bg-[var(--color-space-midnight)] px-6 py-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm text-[#818cf8]">⊕</span>
              <h1 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">Aerospace Foundation Model</h1>
            </div>
            <p className="mt-0.5 font-mono text-[9px] text-[var(--color-text-tertiary)]">
              ORBITIQ-X v0.4.0 · {healthyCount}/{totalCount} services healthy · 29,198 RSOs · 185 corpus chunks
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className={`rounded border px-2 py-0.5 font-mono text-[9px] font-semibold`}
              style={{ color: overallOk ? "#34d399" : "#fbbf24", borderColor: overallOk ? "#34d399" : "#fbbf24", backgroundColor: overallOk ? "rgba(52,211,153,0.1)" : "rgba(251,191,36,0.1)" }}>
              {overallOk ? "NOMINAL" : "DEGRADED"}
            </span>
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#34d399]" />
            <span className="font-mono text-[9px] text-[#34d399]">LIVE</span>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">

        {/* Architecture pipeline */}
        <div className="rounded border border-[var(--color-space-border)] bg-[var(--color-space-navy)] p-4">
          <div className="mb-3 font-mono text-[9px] tracking-widest text-[var(--color-text-tertiary)]">INTELLIGENCE PIPELINE</div>
          <div className="flex flex-wrap items-center gap-2">
            {[
              { label:"User Query",     icon:"⊙", color:"#64748b" },
              { label:"Embed",          icon:"◈", color:"#818cf8", sub:"384-dim" },
              { label:"Vector Search",  icon:"◑", color:"#818cf8", sub:"185 chunks" },
              { label:"Graph Query",    icon:"◉", color:"#34d399", sub:"29,248 nodes" },
              { label:"Live SSA",       icon:"◫", color:"#7dd3fc", sub:"29,198 RSOs" },
              { label:"Agents",         icon:"◎", color:"#fbbf24", sub:"7 specialists" },
              { label:"Claude",         icon:"⊕", color:"#c084fc", sub:"Sonnet 4.6" },
              { label:"Answer",         icon:"✓", color:"#34d399" },
            ].map((step, i, arr) => (
              <div key={step.label} className="flex items-center gap-1.5">
                <div className="flex flex-col items-center gap-0.5">
                  <span className="font-mono text-lg" style={{ color:step.color }}>{step.icon}</span>
                  <span className="font-mono text-[8px] text-center text-[var(--color-text-secondary)]">{step.label}</span>
                  {step.sub && <span className="font-mono text-[7px] text-[var(--color-text-tertiary)]">{step.sub}</span>}
                </div>
                {i < arr.length-1 && <span className="font-mono text-[var(--color-space-border-strong)]">→</span>}
              </div>
            ))}
          </div>
        </div>

        {/* Benchmark */}
        <div className="rounded border border-[var(--color-space-border)] bg-[var(--color-space-navy)] p-4">
          <div className="mb-3 font-mono text-[9px] tracking-widest text-[var(--color-text-tertiary)]">v0.4.0 BENCHMARK — 20 QUERIES ACROSS 12 DOMAINS</div>
          <div className="grid grid-cols-2 gap-6">
            <div className="space-y-2">
              <BenchmarkBar label="Retrieval Accuracy (20/20)" value={100} color="#34d399" />
              <BenchmarkBar label="Success Rate (20/20)"       value={100} color="#34d399" />
              <BenchmarkBar label="Corpus Coverage (12 domains)" value={100} color="#818cf8" />
            </div>
            <div className="space-y-1">
              {[
                ["Avg Latency","~10-28s"],["Min Latency","10,163ms"],["Max Latency","46,533ms"],
                ["Corpus Chunks","185"],["Domains","12"],["Embedding","all-MiniLM-L6-v2"],
              ].map(([k,v]) => (
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
          <div className="mb-2 font-mono text-[9px] tracking-widest text-[var(--color-text-tertiary)]">PLATFORM SERVICES — LIVE STATUS</div>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {services.map(s => (
              <ServicePanel key={s.name} name={s.name} icon={s.icon} status={getS(s.key)} details={s.details} />
            ))}
          </div>
        </div>

        {/* Corpus domains */}
        <div className="rounded border border-[var(--color-space-border)] bg-[var(--color-space-navy)] p-4">
          <div className="mb-3 font-mono text-[9px] tracking-widest text-[var(--color-text-tertiary)]">KNOWLEDGE CORPUS — 12 AEROSPACE DOMAINS · 185 CHUNKS · ~24,500 WORDS</div>
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

        {/* Known issues */}
        <div className="rounded border border-[var(--color-space-border)] bg-[var(--color-space-navy)] p-4">
          <div className="mb-3 font-mono text-[9px] tracking-widest text-[var(--color-text-tertiary)]">SYSTEM STATUS</div>
          <div className="grid grid-cols-2 gap-3">
            {[
              { label:"Redis",        status:"unavailable", note:"Cache/pub-sub offline — scheduler uses in-memory fallback" },
              { label:"Digital Twin", status:"not_initialised", note:"Requires catalog sync → POST /catalog/sync" },
              { label:"MinIO",        status:"unavailable", note:"Object storage not required for core SSA functions" },
              { label:"Neo4j Enrich", status:"running", note:"Operators + Countries populating from PostgreSQL (triggered)" },
            ].map(({ label, status, note }) => (
              <div key={label} className="flex gap-2 rounded border border-[var(--color-space-border)] bg-[var(--color-space-surface)] p-2">
                <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: HC(status) }} />
                <div>
                  <div className="font-mono text-[9px] font-semibold text-[var(--color-text-primary)]">{label}</div>
                  <div className="font-mono text-[8px] text-[var(--color-text-tertiary)]">{note}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
}
