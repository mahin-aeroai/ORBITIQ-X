"use client";
/**
 * ORBITIQ-X — SystemHealthStrip
 * ================================
 * Compact horizontal strip showing live status of all platform services.
 * Sits below the metrics bar on the dashboard.
 */

import { useQuery } from "@tanstack/react-query";
import { fetchPlatformHealth } from "@/lib/api";

interface ServiceDotProps {
  label: string;
  status: "healthy" | "degraded" | "unavailable" | "unknown";
}

function ServiceDot({ label, status }: ServiceDotProps) {
  const colorMap = {
    healthy:     "var(--color-accent-green-bright)",
    degraded:    "var(--color-accent-amber)",
    unavailable: "var(--color-accent-red-bright)",
    unknown:     "var(--color-text-tertiary)",
  };
  const color = colorMap[status] ?? colorMap.unknown;

  return (
    <div className="flex items-center gap-1.5">
      <span
        className={`inline-block h-1.5 w-1.5 rounded-full ${status === "healthy" ? "" : status === "degraded" ? "animate-pulse" : ""}`}
        style={{ backgroundColor: color }}
        aria-hidden="true"
      />
      <span className="font-mono text-[9px] tracking-wide" style={{ color }}>
        {label}
      </span>
    </div>
  );
}

export function SystemHealthStrip() {
  const { data } = useQuery({
    queryKey: ["platform-health"],
    queryFn: fetchPlatformHealth,
    refetchInterval: 30_000,
    staleTime: 20_000,
  });

  const svcs = (data as any)?.services ?? {};

  const getStatus = (key: string): "healthy" | "degraded" | "unavailable" | "unknown" => {
    const s = svcs[key]?.status;
    if (s === "healthy" || s === "operational") return "healthy";
    if (s === "degraded") return "degraded";
    if (s === "unavailable") return "unavailable";
    return "unknown";
  };

  return (
    <div className="flex h-7 shrink-0 items-center gap-4 border-b border-[var(--color-space-border)] bg-[var(--color-space-deep)] px-4">
      <span className="font-mono text-[8px] tracking-[0.2em] text-[var(--color-text-tertiary)]">
        PLATFORM
      </span>
      <ServiceDot label="PostgreSQL" status={getStatus("postgres")} />
      <ServiceDot label="Neo4j"     status={getStatus("neo4j")} />
      <ServiceDot label="Qdrant"    status={getStatus("vector_store")} />
      <ServiceDot label="GraphRAG"  status={getStatus("graphrag")} />
      <ServiceDot label="Agents"    status={getStatus("agents")} />
      <ServiceDot label="Redis"     status={getStatus("redis")} />
      <ServiceDot label="Scheduler" status={getStatus("scheduler") === "unknown" ? "unknown" : svcs.scheduler?.status === "running" ? "healthy" : "degraded"} />
    </div>
  );
}
