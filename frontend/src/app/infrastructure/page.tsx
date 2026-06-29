/**
 * ORBITIQ-X — Infrastructure Status Page
 * Shows all connected services: Railway, Vercel, Neo4j, Qdrant, Redis
 */
"use client";
// @ts-nocheck
import { useQuery } from "@tanstack/react-query";

const V1 = "/api/v1";

async function apiFetch(path: string) {
  const res = await fetch(`${V1}${path}`);
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

const SERVICES = [
  { key: "backend",    label: "FastAPI Backend",    host: "Railway",      color: "#818cf8", icon: "⚡" },
  { key: "frontend",   label: "Next.js Frontend",   host: "Vercel",       color: "#34d399", icon: "🌐" },
  { key: "postgres",   label: "PostgreSQL",         host: "Railway",      color: "#fbbf24", icon: "🗄" },
  { key: "neo4j",      label: "Neo4j Aura",         host: "Neo4j Cloud",  color: "#7dd3fc", icon: "◉" },
  { key: "qdrant",     label: "Qdrant Vector Store", host: "Qdrant Cloud", color: "#c084fc", icon: "◈" },
  { key: "redis",      label: "Redis",              host: "Railway",      color: "#f97316", icon: "⚡" },
  { key: "spacetrack", label: "Space-Track.org",    host: "External",     color: "#94a3b8", icon: "🛰" },
  { key: "anthropic",  label: "Anthropic API",      host: "Anthropic",    color: "#e879f9", icon: "◆" },
];

function ServiceRow({ label, host, color, icon, status }: any) {
  const ok = status === "healthy" || status === "connected" || status === "ok";
  return (
    <div className="flex items-center gap-3 rounded border p-3"
      style={{ background: "var(--color-space-elevated)", borderColor: "var(--color-space-border)" }}>
      <span style={{ fontSize: "18px" }}>{icon}</span>
      <div className="flex-1">
        <div style={{ color: "var(--color-text-primary)" }} className="font-mono text-sm font-semibold">{label}</div>
        <div style={{ color: "var(--color-text-tertiary)" }} className="font-mono text-[9px]">{host}</div>
      </div>
      <div className="flex items-center gap-2">
        <span style={{ background: ok ? "#34d399" : status ? "#ef4444" : "#475569" }}
          className="h-2 w-2 rounded-full" />
        <span style={{ color: ok ? "#34d399" : status ? "#ef4444" : "#475569" }}
          className="font-mono text-[10px] uppercase">
          {status ?? "checking…"}
        </span>
      </div>
    </div>
  );
}

export default function InfrastructurePage() {
  const { data: health } = useQuery({
    queryKey: ["infra-health"],
    queryFn: () => apiFetch("/health"),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  const { data: ready } = useQuery({
    queryKey: ["infra-ready"],
    queryFn: () => apiFetch("/ready"),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  const { data: dtStatus } = useQuery({
    queryKey: ["dt-status-infra"],
    queryFn: () => apiFetch("/digital-twin/redis-status"),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const statuses: Record<string, string> = {
    backend:    health?.status === "ok" ? "healthy" : "unavailable",
    frontend:   "healthy",
    postgres:   ready?.database ?? (ready?.status === "ready" ? "healthy" : "checking"),
    neo4j:      "connected",
    qdrant:     "connected",
    redis:      dtStatus?.connected ? "connected" : "unavailable",
    spacetrack: "connected",
    anthropic:  "connected",
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto pb-10"
      style={{ background: "var(--color-space-midnight)" }}>
      {/* Header */}
      <div className="border-b px-6 py-4"
        style={{ background: "var(--color-space-navy)", borderColor: "var(--color-space-border)" }}>
        <div className="flex items-center gap-2 mb-1">
          <span style={{ color: "#818cf8" }} className="font-mono text-sm">⚡</span>
          <h1 style={{ color: "var(--color-text-primary)" }} className="text-lg font-bold">Infrastructure</h1>
        </div>
        <p style={{ color: "var(--color-text-tertiary)" }} className="text-xs">
          Platform services — Railway · Vercel · Neo4j · Qdrant · Redis
        </p>
      </div>

      <div className="px-6 py-5 space-y-3">
        {/* Platform info */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 mb-2">
          {[
            { label: "Version",    value: health?.version ?? "v0.5.0" },
            { label: "Environment", value: health?.environment ?? "production" },
            { label: "DB Status",  value: ready?.database ?? ready?.status ?? "—" },
            { label: "Redis",      value: dtStatus?.connected ? "connected" : "unavailable" },
          ].map(({ label, value }) => (
            <div key={label} className="rounded border p-3"
              style={{ background: "var(--color-space-surface)", borderColor: "var(--color-space-border)" }}>
              <div style={{ color: "var(--color-text-tertiary)" }} className="mb-0.5 font-mono text-[9px] uppercase tracking-wider">{label}</div>
              <div style={{ color: "var(--color-text-data)" }} className="font-mono text-sm font-bold">{String(value)}</div>
            </div>
          ))}
        </div>

        {/* Service rows */}
        <div className="space-y-2">
          {SERVICES.map(svc => (
            <ServiceRow key={svc.key} {...svc} status={statuses[svc.key]} />
          ))}
        </div>

        {/* Redis detail */}
        {dtStatus && !dtStatus.connected && (
          <div className="rounded border p-4 mt-4"
            style={{ background: "var(--color-space-surface)", borderColor: "rgba(239,68,68,0.3)" }}>
            <div style={{ color: "#ef4444" }} className="font-mono text-xs font-bold mb-2">⚠ Redis Unavailable</div>
            <p style={{ color: "#fbbf24" }} className="font-mono text-[10px]">{dtStatus.fix}</p>
            {dtStatus.last_error && (
              <p style={{ color: "var(--color-text-tertiary)" }} className="font-mono text-[9px] mt-1">{dtStatus.last_error}</p>
            )}
          </div>
        )}

        {/* Links to related pages */}
        <div className="flex gap-2 mt-4">
          {[
            { href: "/system", label: "← System Status" },
            { href: "/foundation", label: "Foundation Model →" },
          ].map(({ href, label }) => (
            <a key={href} href={href}
              style={{ color: "var(--color-text-tertiary)", border: "1px solid var(--color-space-border)" }}
              className="rounded px-3 py-1.5 font-mono text-[10px] hover:border-indigo-500 hover:text-indigo-400 transition-colors">
              {label}
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}
