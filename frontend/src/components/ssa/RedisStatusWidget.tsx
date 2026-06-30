/**
 * ORBITIQ-X — Redis & Digital Twin Status Widget
 * Phase 18
 *
 * Shows Redis connection status, Digital Twin state,
 * and provides one-click reconnect + activation buttons.
 * Designed for the System Status page and dashboard header.
 */
"use client";

import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getApiAccessToken } from "@/lib/api";

const V1 = "/api/v1";

async function apiFetch(path: string, method = "GET") {
  const token = getApiAccessToken();
  const res = await fetch(`${V1}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

function StatusDot({ ok, pulse }: { ok: boolean; pulse?: boolean }) {
  return (
    <span
      style={{ background: ok ? "#34d399" : "#ef4444" }}
      className={`inline-block h-2 w-2 rounded-full ${pulse && ok ? "animate-pulse" : ""}`}
    />
  );
}

function StatRow({ label, value, color = "var(--color-text-data)" }: {
  label: string; value: React.ReactNode; color?: string
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span style={{ color: "var(--color-text-tertiary)" }} className="font-mono text-[9px] uppercase tracking-wider">
        {label}
      </span>
      <span style={{ color }} className="font-mono text-[10px] font-semibold">
        {value}
      </span>
    </div>
  );
}

export function RedisStatusWidget() {
  const queryClient = useQueryClient();
  const [reconnecting, setReconnecting] = useState(false);
  const [activating, setActivating]     = useState(false);

  const { data: redisStatus, isLoading: redisLoading } = useQuery({
    queryKey: ["redis-status"],
    queryFn: () => apiFetch("/digital-twin/redis-status"),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  const { data: dtStatus } = useQuery({
    queryKey: ["dt-status"],
    queryFn: () => apiFetch("/digital-twin/status"),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const handleReconnect = async () => {
    setReconnecting(true);
    try {
      await apiFetch("/digital-twin/redis-reconnect", "POST");
      await queryClient.invalidateQueries({ queryKey: ["redis-status"] });
      await queryClient.invalidateQueries({ queryKey: ["dt-status"] });
    } finally {
      setReconnecting(false);
    }
  };

  const handleActivate = async () => {
    setActivating(true);
    try {
      // Note: the real endpoint is /propagate, not /activate.
      // /activate only exists under /api/v2/digital-twin (a separate router).
      const res = await fetch(`${V1}/digital-twin/propagate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(getApiAccessToken() ? { Authorization: `Bearer ${getApiAccessToken()}` } : {}),
        },
        body: JSON.stringify({}),
      });
      if (!res.ok) throw new Error(`${res.status}`);

      // Propagating 29,198 objects takes 30-120s — poll /status every 5s
      // until objects_propagated > 0 or we give up after 2 minutes.
      let attempts = 0;
      const poll = setInterval(async () => {
        attempts += 1;
        await queryClient.invalidateQueries({ queryKey: ["dt-status"] });
        const latest = queryClient.getQueryData<any>(["dt-status"]);
        if ((latest?.objects_propagated ?? 0) > 0 || attempts >= 24) {
          clearInterval(poll);
          setActivating(false);
        }
      }, 5000);
    } catch {
      setActivating(false);
    }
  };

  const handleCatalogSync = async (mode: "full" | "incremental") => {
    // Real endpoint is POST /catalog/sync with mode in the JSON body —
    // not /digital-twin/catalog-sync (that only exists under /api/v2).
    const token = getApiAccessToken();
    await fetch(`${V1}/catalog/sync`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ mode }),
    });
    setTimeout(() => queryClient.invalidateQueries({ queryKey: ["dt-status"] }), 3000);
  };

  const redisConnected = redisStatus?.connected ?? false;
  const dtStatusLabel  = dtStatus?.status ?? "unknown";
  const dtInitialized  = dtStatusLabel === "operational" || (dtStatus?.objects_propagated ?? 0) > 0;

  return (
    <div
      className="rounded-lg border"
      style={{ background: "var(--color-space-surface)", borderColor: "var(--color-space-border)" }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between border-b px-4 py-2.5"
        style={{ borderColor: "var(--color-space-border)" }}
      >
        <div className="flex items-center gap-2">
          <StatusDot ok={redisConnected} pulse={redisConnected} />
          <span style={{ color: "var(--color-text-secondary)" }} className="font-mono text-[10px] font-bold uppercase tracking-widest">
            Redis & Digital Twin
          </span>
        </div>
        <span
          style={{
            color: dtStatusLabel === "operational" ? "#34d399" :
                   dtStatusLabel === "degraded"    ? "#fbbf24" : "#ef4444",
          }}
          className="font-mono text-[9px] uppercase tracking-widest"
        >
          {dtStatusLabel}
        </span>
      </div>

      <div className="p-4 space-y-3">
        {/* Redis status */}
        <div className="space-y-1.5">
          <StatRow
            label="Redis"
            value={redisConnected ? "connected" : "unavailable"}
            color={redisConnected ? "#34d399" : "#ef4444"}
          />
          {redisStatus?.uptime_s && (
            <StatRow label="Redis uptime" value={`${Math.round(redisStatus.uptime_s / 60)}m`} />
          )}
          {!redisConnected && redisStatus?.last_error && (
            <div
              style={{ color: "#ef4444", background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)" }}
              className="rounded p-2 font-mono text-[9px] leading-relaxed"
            >
              {redisStatus.last_error.slice(0, 80)}
            </div>
          )}
        </div>

        {/* Digital Twin status */}
        <div className="space-y-1.5 border-t pt-3" style={{ borderColor: "var(--color-space-border)" }}>
          <StatRow
            label="Digital Twin"
            value={dtInitialized ? "active" : "not initialised"}
            color={dtInitialized ? "#34d399" : "#fbbf24"}
          />
          {(dtStatus?.objects_propagated ?? 0) > 0 && (
            <StatRow label="Propagated objects" value={dtStatus.objects_propagated.toLocaleString()} />
          )}
          {dtStatus?.last_propagation && (
            <StatRow label="Last propagation" value={new Date(dtStatus.last_propagation).toLocaleTimeString()} />
          )}
          <StatRow label="SSE alerts" value={redisConnected ? "active" : "polling fallback"}
            color={redisConnected ? "#34d399" : "#fbbf24"} />
        </div>

        {/* Impact list when Redis is down */}
        {!redisConnected && redisStatus?.impact_if_down?.length > 0 && (
          <div className="border-t pt-3 space-y-1" style={{ borderColor: "var(--color-space-border)" }}>
            <div style={{ color: "var(--color-text-tertiary)" }} className="font-mono text-[9px] uppercase tracking-wider mb-1">
              Impact
            </div>
            {redisStatus.impact_if_down.map((item: string, i: number) => (
              <div key={i} style={{ color: "#fbbf24" }} className="font-mono text-[9px] leading-relaxed">
                ⚠ {item}
              </div>
            ))}
            {redisStatus.fix && (
              <div
                style={{ color: "#7dd3fc", background: "rgba(125,211,252,0.06)", border: "1px solid rgba(125,211,252,0.2)" }}
                className="mt-2 rounded p-2 font-mono text-[9px] leading-relaxed"
              >
                💡 {redisStatus.fix}
              </div>
            )}
          </div>
        )}

        {/* Action buttons */}
        <div className="flex flex-col gap-1.5 border-t pt-3" style={{ borderColor: "var(--color-space-border)" }}>
          {!redisConnected && (
            <button
              onClick={handleReconnect}
              disabled={reconnecting}
              style={{
                color: "#818cf8",
                background: "rgba(99,102,241,0.1)",
                border: "1px solid rgba(99,102,241,0.4)",
              }}
              className="w-full rounded px-3 py-1.5 font-mono text-[10px] font-semibold transition-colors hover:bg-indigo-500/20 disabled:opacity-50"
            >
              {reconnecting ? "Reconnecting…" : "↻ Reconnect Redis"}
            </button>
          )}

          {redisConnected && !dtInitialized && (
            <button
              onClick={handleActivate}
              disabled={activating}
              style={{
                color: "#34d399",
                background: "rgba(52,211,153,0.1)",
                border: "1px solid rgba(52,211,153,0.4)",
              }}
              className="w-full rounded px-3 py-1.5 font-mono text-[10px] font-semibold transition-colors hover:bg-green-500/20 disabled:opacity-50"
            >
              {activating ? "Activating…" : "▶ Activate Digital Twin"}
            </button>
          )}

          <div className="flex gap-1.5">
            <button
              onClick={() => handleCatalogSync("incremental")}
              style={{ color: "var(--color-text-tertiary)", border: "1px solid var(--color-space-border)" }}
              className="flex-1 rounded px-2 py-1 font-mono text-[9px] transition-colors hover:border-indigo-500 hover:text-indigo-400"
            >
              Sync Incremental
            </button>
            <button
              onClick={() => handleCatalogSync("full")}
              style={{ color: "var(--color-text-tertiary)", border: "1px solid var(--color-space-border)" }}
              className="flex-1 rounded px-2 py-1 font-mono text-[9px] transition-colors hover:border-indigo-500 hover:text-indigo-400"
            >
              Full Sync
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
