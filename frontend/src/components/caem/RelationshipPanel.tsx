/**
 * ORBITIQ-X — Entity Relationship Panel
 * Phase 17.5
 *
 * Tab-grouped relationship browser. One tab per semantic category:
 * Organizational / Operational / Technical / Scientific / Commercial /
 * Supply Chain / Regulatory / Historical / Knowledge / Geographic.
 *
 * Each row links to the connected entity's intelligence page.
 */
"use client";

import React, { useState } from "react";
import Link from "next/link";
import type { RelationshipEntry } from "@/lib/caem-api";

const CATEGORIES = [
  { key: "all",           label: "All" },
  { key: "organizational",label: "Org" },
  { key: "operational",   label: "Ops" },
  { key: "technical",     label: "Tech" },
  { key: "scientific",    label: "Science" },
  { key: "supply_chain",  label: "Supply" },
  { key: "commercial",    label: "Commercial" },
  { key: "regulatory",    label: "Regulatory" },
  { key: "historical",    label: "Historical" },
  { key: "knowledge",     label: "Knowledge" },
  { key: "geographic",    label: "Geo" },
];

function ConfidenceDot({ score }: { score: number }) {
  const color =
    score >= 0.85 ? "#34d399" :
    score >= 0.70 ? "#818cf8" :
    score >= 0.55 ? "#fbbf24" : "#ef4444";
  return (
    <span
      title={`Confidence: ${Math.round(score * 100)}%`}
      style={{ background: color }}
      className="inline-block h-2 w-2 rounded-full"
    />
  );
}

function RelRow({
  rel,
  centerAqid,
}: {
  rel: RelationshipEntry;
  centerAqid: string;
}) {
  const isOutbound  = rel.source_aqid === centerAqid;
  const peerAqid    = isOutbound ? rel.target_aqid : rel.source_aqid;
  const peerLabel   = peerAqid.split("-").slice(2).join(" ") || peerAqid;
  const relLabel    = rel.relationship_type.replace(/_/g, " ").toLowerCase();

  return (
    <div
      className="flex items-center gap-3 rounded border px-3 py-2 transition-colors hover:border-indigo-500"
      style={{
        background: "var(--color-space-elevated)",
        borderColor: "var(--color-space-border)",
      }}
    >
      {/* Direction arrow */}
      <span
        style={{ color: isOutbound ? "#818cf8" : "#34d399" }}
        className="font-mono text-xs font-bold"
      >
        {isOutbound ? "→" : "←"}
      </span>

      {/* Relationship type */}
      <span
        style={{ color: "var(--color-text-tertiary)" }}
        className="w-44 shrink-0 font-mono text-[10px] uppercase tracking-wide"
      >
        {relLabel}
      </span>

      {/* Peer entity link */}
      <Link
        href={`/entities/${encodeURIComponent(peerAqid)}`}
        style={{ color: "var(--color-text-accent)" }}
        className="flex-1 truncate text-sm font-medium hover:underline"
      >
        {peerLabel}
      </Link>

      {/* Temporal */}
      {rel.since && (
        <span style={{ color: "var(--color-text-tertiary)" }} className="font-mono text-[10px]">
          {rel.since.slice(0, 4)}
          {rel.until ? `–${rel.until.slice(0, 4)}` : "–"}
        </span>
      )}

      {/* Confidence */}
      <ConfidenceDot score={rel.confidence} />

      {/* Provenance link */}
      {rel.provenance_url && (
        <a
          href={rel.provenance_url}
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: "var(--color-text-tertiary)" }}
          className="font-mono text-[10px] hover:text-indigo-400"
          title="Source"
        >
          ↗
        </a>
      )}
    </div>
  );
}

interface RelationshipPanelProps {
  relationships: RelationshipEntry[];
  centerAqid: string;
}

export function RelationshipPanel({ relationships, centerAqid }: RelationshipPanelProps) {
  const [activeCategory, setActiveCategory] = useState("all");
  const [searchTerm, setSearchTerm] = useState("");

  const filtered = relationships.filter(r => {
    const catMatch = activeCategory === "all" || r.category === activeCategory;
    const searchMatch = !searchTerm ||
      r.relationship_type.toLowerCase().includes(searchTerm.toLowerCase()) ||
      r.source_aqid.toLowerCase().includes(searchTerm.toLowerCase()) ||
      r.target_aqid.toLowerCase().includes(searchTerm.toLowerCase());
    return catMatch && searchMatch && r.is_current;
  });

  // Count per category
  const counts: Record<string, number> = { all: relationships.length };
  relationships.forEach(r => {
    if (r.category) counts[r.category] = (counts[r.category] ?? 0) + 1;
  });

  return (
    <div
      className="rounded-lg border"
      style={{ borderColor: "var(--color-space-border)", background: "var(--color-space-surface)" }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between border-b px-4 py-2.5"
        style={{ borderColor: "var(--color-space-border)" }}
      >
        <span style={{ color: "var(--color-text-secondary)" }} className="text-xs font-bold uppercase tracking-widest">
          ◈ Relationships · {relationships.length}
        </span>
        <input
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
          placeholder="Filter…"
          style={{
            background: "var(--color-space-elevated)",
            border: "1px solid var(--color-space-border)",
            color: "var(--color-text-primary)",
          }}
          className="rounded px-2 py-0.5 font-mono text-[11px] outline-none focus:border-indigo-500 w-32"
        />
      </div>

      {/* Category tabs */}
      <div
        className="flex gap-0 overflow-x-auto border-b"
        style={{ borderColor: "var(--color-space-border)" }}
      >
        {CATEGORIES.map(cat => {
          const count = counts[cat.key] ?? 0;
          if (cat.key !== "all" && count === 0) return null;
          const active = activeCategory === cat.key;
          return (
            <button
              key={cat.key}
              onClick={() => setActiveCategory(cat.key)}
              style={{
                color:        active ? "#818cf8" : "var(--color-text-tertiary)",
                borderBottom: active ? "2px solid #818cf8" : "2px solid transparent",
                background:   active ? "rgba(99,102,241,0.06)" : "transparent",
              }}
              className="flex shrink-0 items-center gap-1 px-3 py-2 font-mono text-[10px] font-semibold uppercase tracking-wider transition-colors hover:text-indigo-400"
            >
              {cat.label}
              <span
                style={{
                  background: active ? "rgba(99,102,241,0.2)" : "var(--color-space-border)",
                  color: active ? "#818cf8" : "var(--color-text-tertiary)",
                }}
                className="rounded px-1 py-0.5 text-[9px]"
              >
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Relationship rows */}
      <div className="max-h-96 overflow-y-auto p-3">
        {filtered.length === 0 ? (
          <div className="py-6 text-center">
            <span style={{ color: "var(--color-text-tertiary)" }} className="text-sm">
              {searchTerm ? "No matches" : "No relationships in this category."}
            </span>
          </div>
        ) : (
          <div className="flex flex-col gap-1.5">
            {filtered.map(rel => (
              <RelRow key={rel.rel_id} rel={rel} centerAqid={centerAqid} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
