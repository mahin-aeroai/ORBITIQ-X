/**
 * ORBITIQ-X — Provenance & Sources Panel
 * Phase 17.5
 *
 * Lists all provenance sources for an entity with confidence scores,
 * verification status, and links to original sources.
 * Also shows version history summary.
 */
"use client";

import React, { useState } from "react";
import type { EntityFull, ProvenanceRecord } from "@/lib/caem-api";

const TIER_LABEL: Record<string, string> = {
  official:          "Tier 1 · Official",
  official_registry: "Tier 2 · Registry",
  peer_reviewed:     "Tier 3 · Peer-Reviewed",
  reference:         "Tier 4 · Reference",
  news:              "Tier 5 · News",
  community:         "Tier 6 · Community",
  ai_generated:      "AI Generated",
};

const VERIFICATION_COLOR: Record<string, string> = {
  authoritative:  "#34d399",
  human_verified: "#818cf8",
  ai_verified:    "#7dd3fc",
  unverified:     "#fbbf24",
  disputed:       "#ef4444",
};

function SourceCard({ source }: { source: ProvenanceRecord }) {
  const tierLabel = TIER_LABEL[source.source_type] ?? source.source_type;
  const vColor    = VERIFICATION_COLOR[source.verification_status] ?? "#475569";
  const confPct   = Math.round(source.confidence * 100);

  return (
    <div
      className="rounded border p-3"
      style={{
        background: "var(--color-space-elevated)",
        borderColor: "var(--color-space-border)",
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          {/* Source name / URL */}
          {source.source_url ? (
            <a
              href={source.source_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: "var(--color-text-accent)" }}
              className="truncate text-sm font-medium hover:underline block"
            >
              {source.source_name ?? source.source_url}
            </a>
          ) : (
            <span style={{ color: "var(--color-text-primary)" }} className="text-sm font-medium">
              {source.source_name ?? "Unknown source"}
            </span>
          )}

          {/* Publisher / author */}
          {(source.publisher) && (
            <span style={{ color: "var(--color-text-tertiary)" }} className="block text-[10px] mt-0.5">
              {source.publisher}
            </span>
          )}

          {/* Citation */}
          {source.citation_text && (
            <span style={{ color: "var(--color-text-tertiary)" }} className="block text-[10px] italic mt-0.5">
              {source.citation_text.length > 80
                ? `${source.citation_text.slice(0, 80)}…`
                : source.citation_text}
            </span>
          )}
        </div>

        <div className="flex flex-col items-end gap-1 shrink-0">
          {/* Confidence */}
          <span
            style={{ color: "#7dd3fc", background: "rgba(125,211,252,0.1)" }}
            className="font-mono text-[10px] font-bold rounded px-1.5 py-0.5"
          >
            {confPct}%
          </span>

          {/* Verification */}
          <span
            style={{ color: vColor, background: `${vColor}18`, border: `1px solid ${vColor}40` }}
            className="rounded px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider"
          >
            {source.verification_status.replace(/_/g, " ")}
          </span>
        </div>
      </div>

      {/* Tier label */}
      <div className="mt-1.5">
        <span style={{ color: "var(--color-text-tertiary)" }} className="font-mono text-[9px]">
          {tierLabel}
        </span>
      </div>
    </div>
  );
}

interface ProvenancePanelProps {
  entity: EntityFull;
}

export function ProvenancePanel({ entity }: ProvenancePanelProps) {
  const [showAll, setShowAll] = useState(false);
  const sources = entity.all_sources ?? [];
  const visible = showAll ? sources : sources.slice(0, 5);

  return (
    <div
      className="rounded-lg border"
      style={{ borderColor: "var(--color-space-border)", background: "var(--color-space-surface)" }}
    >
      <div
        className="flex items-center justify-between border-b px-4 py-2.5"
        style={{ borderColor: "var(--color-space-border)" }}
      >
        <span style={{ color: "var(--color-text-secondary)" }} className="text-xs font-bold uppercase tracking-widest">
          ◈ Sources & Provenance · {sources.length}
        </span>
        <span
          style={{ color: "var(--color-text-data)" }}
          className="font-mono text-[10px]"
        >
          Overall confidence: {Math.round(entity.confidence_score * 100)}%
        </span>
      </div>

      <div className="p-4">
        {sources.length === 0 ? (
          <p style={{ color: "var(--color-text-tertiary)" }} className="text-sm italic">
            No provenance sources recorded yet.
          </p>
        ) : (
          <>
            <div className="flex flex-col gap-2">
              {visible.map((source, i) => (
                <SourceCard key={i} source={source} />
              ))}
            </div>

            {sources.length > 5 && (
              <button
                onClick={() => setShowAll(s => !s)}
                style={{ color: "var(--color-text-tertiary)" }}
                className="mt-3 w-full text-center font-mono text-[10px] hover:text-indigo-400 transition-colors"
              >
                {showAll ? "Show less ↑" : `Show all ${sources.length} sources ↓`}
              </button>
            )}
          </>
        )}

        {/* Version note */}
        <div
          className="mt-3 border-t pt-3"
          style={{ borderColor: "var(--color-space-border)" }}
        >
          <span style={{ color: "var(--color-text-tertiary)" }} className="font-mono text-[10px]">
            Record version: {entity.current_version} ·
            Verification: {entity.verification_status.replace(/_/g, " ")}
          </span>
        </div>
      </div>
    </div>
  );
}
