"use client";
/**
 * ORBITIQ-X — System Status Page
 * ================================
 * Mission Control operational status dashboard.
 * Aggregates health from GET /platform/health and GET /platform/status.
 *
 * Sections
 * ─────────
 *   Service Health Grid    — all 10 subsystems with status badges
 *   Scheduler Status       — 5 APScheduler jobs with next-run times
 *   Catalog Intelligence   — last sync time, object count, mode
 *   Digital Twin Status    — propagation age, object count
 *
 * Refresh cadence
 * ─────────────────
 *   /platform/health → every 30s (probes external services — keep slow)
 *   /platform/status → every 10s (reads in-memory state — fast)
 */

import { RedisStatusWidget } from "@/components/ssa/RedisStatusWidget";
import { Suspense } from "react";
import type { Metadata } from "next";
import { useQuery } from "@tanstack/react-query";
import {
  fetchPlatformHealth,
  fetchPlatformStatus,
  type ServiceHealth,
  type PlatformHealth,
  type PlatformStatus,
} from "@/lib/api";

// ─── Status badge ──────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<string, { label: string; color: string; dot: string }> = {
  healthy:        { label: "HEALTHY",       color: "#10b981", dot: "#10b981" },
  operational:    { label: "OPERATIONAL",   color: "#10b981", dot: "#10b981" },
  running:        { label: "RUNNING",       color: "#10b981", dot: "#10b981" },
  degraded:       { label: "DEGRADED",      color: "#f59e0b", dot: "#f59e0b" },
  stale:          { label: "STALE",         color: "#f59e0b", dot: "#f59e0b" },
  unavailable:    { label: "UNAVAILABLE",   color: "#f59e0b", dot: "#f59e0b" },
  not_initialised:{ label: "NOT INIT",      color: "#94a3b8", dot: "#94a3b8" },
  not_started:    { label: "NOT STARTED",   color: "#94a3b8", dot: "#94a3b8" },
  unhealthy:      { label: "UNHEALTHY",     color: "#ef4444", dot: "#ef4444" },
  stopped:        { label: "STOPPED",       color: "#ef4444", dot: "#ef4444" },
  error:          { label: "ERROR",         color: "#ef4444", dot: "#ef4444" },
  unknown:        { label: "UNKNOWN",       color: "#94a3b8", dot: "#94a3b8" },
};

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.unknown;
  return (
    <div className="flex items-center gap-1.5">
      <span
        className="inline-block h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: cfg.dot }}
      />
      <span className="font-mono text-[10px] font-semibold" style={{ color: cfg.color }}>
        {cfg.label}
      </span>
    </div>
  );
}

// ─── Service card ─────────────────────────────────────────────────────────

const SERVICE_META: Record<string, { label: string; icon: string; description: string }> = {
  postgres:          { label: "PostgreSQL",        icon: "◈", description: "Primary data store" },
  redis:             { label: "Redis",             icon: "◉", description: "Cache & alert pub/sub" },
  neo4j:             { label: "Neo4j",             icon: "◎", description: "Knowledge graph" },
  vector_store:      { label: "Vector Store",      icon: "◧", description: "Qdrant/Weaviate RAG" },
  minio:             { label: "MinIO",             icon: "◫", description: "Object storage" },
  digital_twin:      { label: "Digital Twin",      icon: "⊕", description: "Orbital propagation" },
  conjunction_engine:{ label: "Conjunction Engine",icon: "⚠", description: "CDM screening" },
  agents:            { label: "Agent System",      icon: "◈", description: "LangGraph + Anthropic" },
  graphrag:          { label: "GraphRAG",          icon: "◎", description: "Graph + RAG fusion" },
  scheduler:         { label: "Scheduler",         icon: "⊛", description: "APScheduler (5 jobs)" },
};

function ServiceCard({
  id,
  svc,
}: {
  id: string;
  svc: ServiceHealth;
}) {
  const meta = SERVICE_META[id] ?? { label: id, icon: "○", description: "" };
  const cfg  = STATUS_CONFIG[svc.status] ?? STATUS_CONFIG.unknown;

  return (
    <div
      className="rounded border p-3 transition-colors"
      style={{
        borderColor:     `${cfg.color}40`,
        backgroundColor: "var(--color-space-navy)",
      }}
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-[11px] text-space-muted">{meta.icon}</span>
            <span className="font-display text-[11px] font-semibold text-space-text">
              {meta.label}
            </span>
          </div>
          <div className="mt-0.5 font-mono text-[9px] text-space-muted">{meta.description}</div>
        </div>
        <StatusBadge status={svc.status} />
      </div>

      {/* Extra details */}
      <div className="space-y-0.5">
        {svc.latency_ms != null && (
          <div className="flex justify-between">
            <span className="font-mono text-[9px] text-space-muted">Latency</span>
            <span className="font-mono text-[9px] text-space-text">{svc.latency_ms} ms</span>
          </div>
        )}
        {svc.node_count != null && (
          <div className="flex justify-between">
            <span className="font-mono text-[9px] text-space-muted">Nodes</span>
            <span className="font-mono text-[9px] text-space-text">
              {(svc.node_count as number).toLocaleString()}
            </span>
          </div>
        )}
        {svc.objects != null && (
          <div className="flex justify-between">
            <span className="font-mono text-[9px] text-space-muted">Objects</span>
            <span className="font-mono text-[9px] text-space-text">
              {(svc.objects as number).toLocaleString()}
            </span>
          </div>
        )}
        {(svc.age_minutes as number) != null && (
          <div className="flex justify-between">
            <span className="font-mono text-[9px] text-space-muted">Last propagation</span>
            <span className="font-mono text-[9px] text-space-text">
              {(svc.age_minutes as number).toFixed(1)} min ago
            </span>
          </div>
        )}
        {svc.active_tasks != null && (
          <div className="flex justify-between">
            <span className="font-mono text-[9px] text-space-muted">Active tasks</span>
            <span className="font-mono text-[9px] text-space-text">{String(svc.active_tasks)}</span>
          </div>
        )}
        {svc.job_count != null && (
          <div className="flex justify-between">
            <span className="font-mono text-[9px] text-space-muted">Jobs registered</span>
            <span className="font-mono text-[9px] text-space-text">{String(svc.job_count)}</span>
          </div>
        )}
        {svc.error && (
          <div className="mt-1 truncate font-mono text-[8px]" style={{ color: "#ef4444" }}>
            {svc.error}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Overall health banner ────────────────────────────────────────────────

function OverallBanner({ health }: { health: PlatformHealth }) {
  const cfg = STATUS_CONFIG[health.overall] ?? STATUS_CONFIG.unknown;
  return (
    <div
      className="flex items-center justify-between rounded border px-4 py-3"
      style={{ borderColor: `${cfg.color}60`, backgroundColor: `${cfg.color}10` }}
    >
      <div className="flex items-center gap-3">
        <span
          className="relative flex h-3 w-3"
          aria-hidden="true"
        >
          <span
            className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-60"
            style={{ backgroundColor: cfg.dot }}
          />
          <span
            className="relative inline-flex h-3 w-3 rounded-full"
            style={{ backgroundColor: cfg.dot }}
          />
        </span>
        <div>
          <span className="font-display text-sm font-bold" style={{ color: cfg.color }}>
            PLATFORM {cfg.label}
          </span>
          <span className="ml-3 font-mono text-[9px] text-space-muted">
            {health.elapsed_ms} ms
          </span>
        </div>
      </div>
      <div className="font-mono text-[9px] text-space-muted">
        {new Date(health.checked_at).toISOString().slice(11, 19)} UTC
      </div>
    </div>
  );
}

// ─── Scheduler panel ──────────────────────────────────────────────────────

function SchedulerPanel({ status }: { status: PlatformStatus }) {
  const sched = status.scheduler;

  return (
    <div className="rounded border border-space-border bg-space-navy p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="section-label">SCHEDULER JOBS</span>
        <StatusBadge status={sched.status} />
      </div>
      <div className="space-y-1.5">
        {(sched.jobs ?? []).map((job) => (
          <div
            key={job.id}
            className="flex items-center justify-between rounded border border-space-border px-3 py-1.5"
          >
            <div>
              <div className="font-mono text-[10px] text-space-text">{job.name}</div>
              <div className="font-mono text-[8px] text-space-muted">{job.id}</div>
            </div>
            <div className="text-right">
              {job.next_run_utc ? (
                <div className="font-mono text-[9px] text-space-muted">
                  {new Date(job.next_run_utc).toISOString().slice(11, 16)} UTC
                </div>
              ) : (
                <span className="font-mono text-[9px] text-space-muted">—</span>
              )}
            </div>
          </div>
        ))}
        {sched.jobs?.length === 0 && (
          <div className="py-2 text-center font-mono text-[10px] text-space-muted">
            No jobs registered
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Catalog + Twin status ────────────────────────────────────────────────

function OperationalStatus({ status }: { status: PlatformStatus }) {
  const cat  = status.catalog;
  const twin = status.digital_twin;

  return (
    <div className="grid grid-cols-2 gap-3">
      {/* Catalog */}
      <div className="rounded border border-space-border bg-space-navy p-4">
        <div className="mb-3 section-label">CATALOG SYNC</div>
        <div className="space-y-1.5">
          {[
            ["Status",    cat.status ?? "—"],
            ["Mode",      cat.sync_mode ?? "—"],
            ["Satellites",cat.satellites != null ? cat.satellites.toLocaleString() : "—"],
            ["Last sync", cat.last_sync ? new Date(cat.last_sync).toISOString().slice(0, 19).replace("T", " ") + " UTC" : "—"],
          ].map(([label, value]) => (
            <div key={label} className="flex items-center justify-between">
              <span className="font-mono text-[9px] text-space-muted">{label}</span>
              <span className="font-mono text-[10px] text-space-text">{String(value)}</span>
            </div>
          ))}
          {cat.failure_reason && (
            <div className="mt-1 font-mono text-[8px]" style={{ color: "#ef4444" }}>
              ⚠ {cat.failure_reason}
            </div>
          )}
        </div>
      </div>

      {/* Digital Twin */}
      <div className="rounded border border-space-border bg-space-navy p-4">
        <div className="mb-3 section-label">DIGITAL TWIN</div>
        <div className="space-y-1.5">
          {[
            ["Live objects",     twin.live_objects?.toLocaleString() ?? "—"],
            ["Last propagation", twin.last_propagation
              ? new Date(twin.last_propagation).toISOString().slice(11, 19) + " UTC"
              : "—"],
            ["Propagation time", twin.propagation_seconds != null
              ? `${twin.propagation_seconds.toFixed(1)} s`
              : "—"],
            ["Propagated",       twin.objects_propagated?.toLocaleString() ?? "—"],
          ].map(([label, value]) => (
            <div key={label} className="flex items-center justify-between">
              <span className="font-mono text-[9px] text-space-muted">{label}</span>
              <span className="font-mono text-[10px] text-space-text">{String(value)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────

function SystemStatusContent() {
  const { data: health, isLoading: healthLoading, isError: healthError, dataUpdatedAt: healthTs } = useQuery({
    queryKey:        ["platform-health"],
    queryFn:         fetchPlatformHealth,
    staleTime:       25_000,
    refetchInterval: 30_000,
    retry:           1,
  });

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey:        ["platform-status"],
    queryFn:         fetchPlatformStatus,
    staleTime:       8_000,
    refetchInterval: 10_000,
    retry:           1,
  });

  return (
    <div className="flex h-full flex-col gap-0 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-space-border px-6 py-3">
        <div>
          <h1 className="font-display text-sm font-bold uppercase tracking-widest text-space-text">
            System Status
          </h1>
          <p className="mt-0.5 font-mono text-[10px] text-space-muted">
            Platform operational health — deep probe of all subsystems
          </p>
        </div>
        <div className="flex items-center gap-3">
          {healthTs > 0 && (
            <span className="font-mono text-[9px] text-space-muted">
              Updated {new Date(healthTs).toISOString().slice(11, 19)} UTC
            </span>
          )}
          <span className="section-label">AUTO-REFRESH 30s</span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="mx-auto max-w-5xl space-y-4">

          {/* Overall status banner */}
          {healthLoading && (
            <div className="rounded border border-space-border px-4 py-3 bg-space-navy">
              <div className="flex items-center gap-2">
                <div className="h-3 w-3 animate-pulse rounded-full bg-space-surface" />
                <span className="section-label">PROBING PLATFORM HEALTH…</span>
              </div>
            </div>
          )}
          {healthError && (
            <div
              className="rounded border px-4 py-3"
              style={{ borderColor: "#ef444460", backgroundColor: "#ef444410" }}
            >
              <span className="font-mono text-[11px]" style={{ color: "#ef4444" }}>
                ⚠ Unable to reach /platform/health — backend may be starting up
              </span>
            </div>
          )}
          {health && <OverallBanner health={health} />}

          {/* Service health grid */}
          <div>
            <div className="mb-2 section-label">SERVICE HEALTH MATRIX</div>
            {healthLoading ? (
              <div className="grid grid-cols-2 gap-2 lg:grid-cols-5">
                {Array.from({ length: 10 }).map((_, i) => (
                  <div key={i} className="h-24 animate-pulse rounded border border-space-border bg-space-navy" />
                ))}
              </div>
            ) : health ? (
              <div className="grid grid-cols-2 gap-2 lg:grid-cols-5">
                {Object.entries(health.services).map(([id, svc]) => (
                  <ServiceCard key={id} id={id} svc={svc} />
                ))}
              </div>
            ) : null}
          </div>

          {/* Scheduler + Operational status */}
          {statusLoading ? (
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {Array.from({ length: 2 }).map((_, i) => (
                <div key={i} className="h-48 animate-pulse rounded border border-space-border bg-space-navy" />
              ))}
            </div>
          ) : status ? (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <SchedulerPanel status={status} />
              <div className="space-y-3">
                <OperationalStatus status={status} />
              </div>
            </div>
          ) : null}

        </div>
      </div>
    
      <div className="mt-4">
        <RedisStatusWidget />
      </div>
</div>
  );
}

export default function SystemStatusPage() {
  return (
    <Suspense fallback={
      <div className="flex h-full items-center justify-center">
        <span className="section-label">LOADING…</span>
      </div>
    }>
      <SystemStatusContent />
    </Suspense>
  );
}
