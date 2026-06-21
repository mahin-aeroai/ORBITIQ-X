"use client";
/**
 * ORBITIQ-X — ConjunctionAlertPanel
 * ===================================
 * Right panel conjunction alerts list.
 *
 * Data source (polling): GET /api/v1/ssa/conjunctions/high-risk?limit={maxItems}
 * Data source (SSE):     GET /api/v1/ssa/alerts/stream  (Phase 13B bridge)
 * Refresh:               15 seconds (polling fallback when SSE disconnected)
 *
 * Each card shows:
 *   • Risk level badge (RED / YELLOW)
 *   • Primary × Secondary object names + NORAD IDs
 *   • Miss distance, Pc, TCA
 *   • Maneuver urgency badge
 *   • Maneuver window countdown
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchHighRiskConjunctions,
  type ConjunctionItem,
  CONJUNCTION_SSE_URL,
} from "@/lib/api";

// ─── Risk badge ───────────────────────────────────────────────────────────────

function RiskBadge({ level }: { level: string }) {
  const isRed = level === "red";
  return (
    <span
      className={[
        "inline-block rounded px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wider",
        isRed ? "status-critical" : "status-watch",
      ].join(" ")}
    >
      {level.toUpperCase()}
    </span>
  );
}

// ─── Urgency badge ────────────────────────────────────────────────────────────

function UrgencyBadge({ urgency }: { urgency: string }) {
  const colorMap: Record<string, string> = {
    CRITICAL: "var(--color-accent-red-bright)",
    HIGH:     "var(--color-accent-amber-bright)",
    ELEVATED: "var(--color-accent-amber)",
    MONITOR:  "var(--color-text-tertiary)",
  };
  const color = colorMap[urgency] ?? colorMap.MONITOR;
  return (
    <span className="font-mono text-[9px]" style={{ color }}>
      {urgency}
    </span>
  );
}

// ─── Conjunction card ─────────────────────────────────────────────────────────

function ConjunctionCard({ event }: { event: ConjunctionItem }) {
  const tcaDate = event.tca ? new Date(event.tca) : null;
  const tcaStr  = tcaDate
    ? tcaDate.toISOString().slice(0, 16).replace("T", " ") + " UTC"
    : "—";

  const pcStr = event.collision_probability > 0
    ? event.collision_probability.toExponential(2)
    : "0";

  const hoursStr = event.maneuver_window_hours_remaining !== null
    ? `${event.maneuver_window_hours_remaining.toFixed(1)}h`
    : "—";

  return (
    <div
      className={[
        "border-b border-space-border px-4 py-3 transition-colors hover:bg-space-surface",
        event.risk_level === "red" ? "border-l-2 border-l-[var(--color-accent-red)]" : "border-l-2 border-l-[var(--color-accent-amber)]",
      ].join(" ")}
      role="listitem"
    >
      {/* Header row */}
      <div className="mb-1 flex items-center justify-between">
        <RiskBadge level={event.risk_level} />
        <UrgencyBadge urgency={event.maneuver_urgency} />
      </div>

      {/* Objects */}
      <div className="mb-1.5 grid grid-cols-[1fr_auto_1fr] items-center gap-1">
        <span className="truncate font-mono text-[11px] text-space-text" title={event.primary.name}>
          {event.primary.name || `NORAD-${event.primary.norad}`}
        </span>
        <span className="font-mono text-[10px] text-space-muted">×</span>
        <span className="truncate text-right font-mono text-[11px] text-space-text" title={event.secondary.name}>
          {event.secondary.name || `NORAD-${event.secondary.norad}`}
        </span>
      </div>

      {/* Metrics row */}
      <div className="grid grid-cols-3 gap-1 text-center">
        <div>
          <div className="text-[9px] uppercase text-space-muted">Miss km</div>
          <div className="data-value text-[11px]">{event.miss_distance_km.toFixed(2)}</div>
        </div>
        <div>
          <div className="text-[9px] uppercase text-space-muted">Pc</div>
          <div
            className="font-mono text-[11px]"
            style={{ color: event.risk_level === "red" ? "var(--color-accent-red-bright)" : "var(--color-accent-amber-bright)" }}
          >
            {pcStr}
          </div>
        </div>
        <div>
          <div className="text-[9px] uppercase text-space-muted">Window</div>
          <div className="data-value text-[11px]">{hoursStr}</div>
        </div>
      </div>

      {/* TCA */}
      <div className="mt-1 font-mono text-[9px] text-space-muted">TCA {tcaStr}</div>
    </div>
  );
}

// ─── Empty state ──────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12">
      <span
        className="font-mono text-2xl"
        style={{ color: "var(--color-accent-green)" }}
      >
        ✓
      </span>
      <span className="section-label" style={{ color: "var(--color-accent-green)" }}>
        NO HIGH-RISK CONJUNCTIONS
      </span>
      <span className="font-mono text-[10px] text-space-muted">
        All events below alert threshold
      </span>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface ConjunctionAlertPanelProps {
  maxItems?: number;
}

export function ConjunctionAlertPanel({ maxItems = 8 }: ConjunctionAlertPanelProps) {
  const queryClient = useQueryClient();
  const [sseConnected, setSseConnected] = useState(false);
  const [newAlertCount, setNewAlertCount] = useState(0);
  const esRef = useRef<EventSource | null>(null);

  // ── Polling query (always active as fallback) ──────────────────────────────
  const { data, isLoading, isError } = useQuery({
    queryKey:        ["conjunction-high-risk", maxItems],
    queryFn:         () => fetchHighRiskConjunctions(maxItems),
    refetchInterval: sseConnected ? false : 15_000,  // SSE takes over when connected
  });

  // ── SSE connection ─────────────────────────────────────────────────────────
  const connectSSE = useCallback(() => {
    if (esRef.current) esRef.current.close();

    const es = new EventSource(CONJUNCTION_SSE_URL);
    esRef.current = es;

    es.onopen = () => setSseConnected(true);

    es.addEventListener("conjunction_alert", () => {
      // Invalidate and refetch the high-risk query when a push arrives
      queryClient.invalidateQueries({ queryKey: ["conjunction-high-risk"] });
      queryClient.invalidateQueries({ queryKey: ["ssa-statistics"] });
      setNewAlertCount((n) => n + 1);
    });

    es.onerror = () => {
      setSseConnected(false);
      es.close();
      // Reconnect after 10 seconds
      setTimeout(connectSSE, 10_000);
    };
  }, [queryClient]);

  useEffect(() => {
    connectSSE();
    return () => esRef.current?.close();
  }, [connectSSE]);

  // ─────────────────────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="space-y-2 px-4 py-2" role="status" aria-label="Loading conjunctions">
        {Array.from({ length: maxItems }).map((_, i) => (
          <div key={i} className="h-16 animate-pulse rounded bg-space-surface" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="px-4 py-4">
        <span className="font-mono text-xs text-[var(--color-accent-amber)]">
          ⚠ CONJUNCTION FEED UNAVAILABLE
        </span>
      </div>
    );
  }

  const items = data?.items ?? [];

  return (
    <div role="list" aria-label="High-risk conjunction alerts">
      {/* SSE status + new alert badge */}
      <div className="flex items-center justify-between px-4 pb-1">
        <div className="flex items-center gap-1.5">
          <span
            className={[
              "inline-block h-1.5 w-1.5 rounded-full",
              sseConnected ? "bg-[var(--color-accent-green)]" : "bg-[var(--color-text-tertiary)]",
            ].join(" ")}
            title={sseConnected ? "Live stream connected" : "Polling mode"}
          />
          <span className="font-mono text-[9px] text-space-muted">
            {sseConnected ? "LIVE" : "POLLING"}
          </span>
        </div>
        {newAlertCount > 0 && (
          <span
            className="rounded bg-[var(--color-accent-red-glow)] px-1.5 py-0.5 font-mono text-[9px] text-[var(--color-accent-red-bright)]"
            onClick={() => setNewAlertCount(0)}
            role="button"
            tabIndex={0}
          >
            +{newAlertCount} NEW
          </span>
        )}
      </div>

      {items.length === 0 ? (
        <EmptyState />
      ) : (
        items.map((event) => (
          <ConjunctionCard key={event.conjunction_id} event={event} />
        ))
      )}
    </div>
  );
}
