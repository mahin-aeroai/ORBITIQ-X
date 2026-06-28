/**
 * ORBITIQ-X — AI Executive Summary Card
 * Phase 17.5
 *
 * Displays the AI-generated executive summary for an entity.
 * Shows key facts in a structured grid. Includes confidence indicator
 * and a manual refresh trigger.
 */
"use client";

import React, { useState } from "react";
import type { EntityFull } from "@/lib/caem-api";
import { caemApi } from "@/lib/caem-api";

interface AISummaryCardProps {
  entity: EntityFull;
  onRefresh?: () => void;
}

export function AISummaryCard({ entity, onRefresh }: AISummaryCardProps) {
  const [refreshing, setRefreshing] = useState(false);
  const [refreshed, setRefreshed] = useState(false);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await caemApi.refreshSummary(entity.aqid);
      setRefreshed(true);
      setTimeout(() => setRefreshed(false), 3000);
      onRefresh?.();
    } catch {
      // Silent — refresh is best-effort
    } finally {
      setRefreshing(false);
    }
  };

  const hasSummary = !!entity.ai_executive_summary;
  const keyFacts   = entity.ai_key_facts ?? [];

  return (
    <div
      className="rounded-lg border p-5"
      style={{
        background: "var(--color-space-surface)",
        borderColor: "rgba(99,102,241,0.25)",
        boxShadow: "0 0 20px rgba(99,102,241,0.05)",
      }}
    >
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span style={{ color: "#818cf8" }} className="text-xs font-bold uppercase tracking-widest">
            ◈ AI Intelligence Summary
          </span>
          {entity.ai_generated_at && (
            <span style={{ color: "var(--color-text-tertiary)" }} className="text-[10px]">
              Generated {new Date(entity.ai_generated_at).toLocaleDateString()}
            </span>
          )}
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          style={{
            color: refreshed ? "#34d399" : "var(--color-text-tertiary)",
            border: "1px solid var(--color-space-border)",
            background: "var(--color-space-elevated)",
          }}
          className="rounded px-2 py-0.5 font-mono text-[10px] transition-colors hover:border-indigo-500 hover:text-indigo-400 disabled:opacity-50"
        >
          {refreshing ? "Queuing…" : refreshed ? "✓ Queued" : "↻ Refresh"}
        </button>
      </div>

      {/* Summary text */}
      {hasSummary ? (
        <p
          style={{ color: "var(--color-text-primary)", lineHeight: 1.7 }}
          className="text-sm"
        >
          {entity.ai_executive_summary}
        </p>
      ) : (
        <p style={{ color: "var(--color-text-tertiary)" }} className="text-sm italic">
          No AI summary available. Click Refresh to generate one.
        </p>
      )}

      {/* Key facts grid */}
      {keyFacts.length > 0 && (
        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
          {keyFacts.map((fact, i) => (
            <div
              key={i}
              className="rounded border p-2"
              style={{
                background: "var(--color-space-elevated)",
                borderColor: "var(--color-space-border)",
              }}
            >
              <div style={{ color: "var(--color-text-tertiary)" }} className="mb-0.5 font-mono text-[9px] uppercase tracking-wider">
                {fact.label}
              </div>
              <div style={{ color: "var(--color-text-data)" }} className="font-mono text-sm font-bold">
                {fact.value}
                {fact.unit && (
                  <span style={{ color: "var(--color-text-tertiary)" }} className="ml-1 text-[10px] font-normal">
                    {fact.unit}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
