/**
 * ORBITIQ-X — Entity Browser
 * Phase 17.5
 *
 * Search and browse all aerospace entities in the CAEM.
 * Filter by entity class, domain, confidence.
 * Each result links to the entity's intelligence page.
 */
"use client";
// @ts-nocheck

import React, { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { caemApi } from "@/lib/caem-api";
import type { EntitySummary } from "@/lib/caem-api";

const ENTITY_CLASSES = [
  "All", "SATELLITE", "LAUNCH_VEHICLE", "COMPANY", "GOV_AGENCY",
  "COUNTRY", "MISSION", "PROGRAM", "TECHNOLOGY", "RESEARCH_PAPER",
  "PERSON", "LAUNCH_SITE", "CONSTELLATION", "PATENT", "STANDARD",
  "CONTRACT", "INCIDENT",
];

const CLASS_COLOR: Record<string, string> = {
  SATELLITE: "#818cf8", LAUNCH_VEHICLE: "#fbbf24", COMPANY: "#34d399",
  GOV_AGENCY: "#7dd3fc", COUNTRY: "#a78bfa", MISSION: "#f97316",
  PROGRAM: "#06b6d4", TECHNOLOGY: "#4ade80", RESEARCH_PAPER: "#e879f9",
  PERSON: "#94a3b8", LAUNCH_SITE: "#2dd4bf", CONSTELLATION: "#818cf8",
  PATENT: "#fb923c", STANDARD: "#fcd34d", INCIDENT: "#ef4444",
};

function EntityCard({ entity }: { entity: EntitySummary }) {
  const color = CLASS_COLOR[entity.entity_class] ?? "#94a3b8";
  const confPct = Math.round(entity.confidence_score * 100);

  return (
    <Link
      href={`/entities/${encodeURIComponent(entity.aqid)}`}
      className="block rounded-lg border p-4 transition-all hover:border-indigo-500 hover:shadow-lg hover:shadow-indigo-500/10"
      style={{
        background: "var(--color-space-surface)",
        borderColor: "var(--color-space-border)",
      }}
    >
      {/* Class badge */}
      <div className="mb-2 flex items-center justify-between">
        <span
          style={{ color, background: `${color}18`, border: `1px solid ${color}40` }}
          className="rounded px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-widest"
        >
          {entity.entity_class.replace(/_/g, " ")}
        </span>
        <span style={{ color: "#475569" }} className="font-mono text-[9px]">
          {confPct}%
        </span>
      </div>

      {/* Name */}
      <div style={{ color: "var(--color-text-primary)" }} className="mb-1 font-semibold leading-tight">
        {entity.display_name}
      </div>

      {/* Description */}
      {entity.description && (
        <p style={{ color: "var(--color-text-tertiary)" }} className="text-[11px] leading-relaxed line-clamp-2">
          {entity.description}
        </p>
      )}

      {/* Tags */}
      <div className="mt-2 flex flex-wrap gap-1">
        {entity.tags?.slice(0, 4).map(tag => (
          <span
            key={tag}
            style={{ color: "var(--color-text-tertiary)", background: "var(--color-space-elevated)", border: "1px solid var(--color-space-border)" }}
            className="rounded px-1 py-0.5 font-mono text-[9px]"
          >
            {tag}
          </span>
        ))}
      </div>

      {/* AI summary snippet */}
      {entity.ai_executive_summary && (
        <p
          style={{
            color: "var(--color-text-secondary)",
            borderTop: "1px solid var(--color-space-border)",
          }}
          className="mt-2 pt-2 text-[11px] italic line-clamp-1"
        >
          {entity.ai_executive_summary}
        </p>
      )}
    </Link>
  );
}

export default function EntityBrowserPage() {
  const [selectedClass, setSelectedClass] = useState("All");
  const [searchQuery, setSearchQuery]     = useState("");
  const [page, setPage]                   = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ["entities", selectedClass, page],
    queryFn: () => caemApi.listEntities({
      entity_class: selectedClass === "All" ? undefined : selectedClass,
      page,
      page_size: 24,
    }),
    staleTime: 30_000,
  });

  const { data: searchData, isLoading: searching } = useQuery({
    queryKey: ["entity-search", searchQuery],
    queryFn: () => caemApi.searchEntities(
      searchQuery,
      selectedClass === "All" ? undefined : selectedClass
    ),
    enabled: searchQuery.length >= 2,
    staleTime: 10_000,
  });

  const entities: EntitySummary[] = searchQuery.length >= 2
    ? (searchData?.results ?? [])
    : (data?.entities ?? []);

  const total = searchQuery.length >= 2
    ? (searchData?.count ?? 0)
    : (data?.total ?? 0);

  return (
    <div
      className="flex h-full flex-col gap-4 overflow-y-auto pb-10"
      style={{ background: "var(--color-space-midnight)" }}
    >
      {/* Header */}
      <div
        className="sticky top-0 z-10 border-b px-6 py-4"
        style={{
          background: "var(--color-space-navy)",
          borderColor: "var(--color-space-border)",
        }}
      >
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h1
              style={{ color: "var(--color-text-primary)", fontFamily: "var(--font-display, inherit)" }}
              className="text-lg font-bold"
            >
              Aerospace Entity Browser
            </h1>
            <p style={{ color: "var(--color-text-tertiary)" }} className="text-xs">
              {total.toLocaleString()} entities in the Aerospace Knowledge Universe
            </p>
          </div>
        </div>

        {/* Search */}
        <input
          value={searchQuery}
          onChange={e => { setSearchQuery(e.target.value); setPage(1); }}
          placeholder="Search entities by name, description, or alias…"
          style={{
            background: "var(--color-space-surface)",
            border: "1px solid var(--color-space-border)",
            color: "var(--color-text-primary)",
          }}
          className="mb-3 w-full rounded-lg px-4 py-2 text-sm outline-none focus:border-indigo-500 placeholder:text-[var(--color-text-tertiary)]"
        />

        {/* Class filter pills */}
        <div className="flex flex-wrap gap-1.5">
          {ENTITY_CLASSES.map(cls => {
            const active = selectedClass === cls;
            const color  = cls === "All" ? "#818cf8" : (CLASS_COLOR[cls] ?? "#94a3b8");
            return (
              <button
                key={cls}
                onClick={() => { setSelectedClass(cls); setPage(1); }}
                style={{
                  color:       active ? color : "var(--color-text-tertiary)",
                  background:  active ? `${color}18` : "var(--color-space-surface)",
                  border:      `1px solid ${active ? color : "var(--color-space-border)"}`,
                }}
                className="rounded px-2 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wider transition-all hover:border-indigo-400"
              >
                {cls === "All" ? "All Classes" : cls.replace(/_/g, " ")}
              </button>
            );
          })}
        </div>
      </div>

      {/* Results grid */}
      <div className="px-6">
        {(isLoading || searching) ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 12 }).map((_, i) => (
              <div
                key={i}
                className="animate-pulse rounded-lg h-32"
                style={{ background: "var(--color-space-surface)" }}
              />
            ))}
          </div>
        ) : entities.length === 0 ? (
          <div className="py-16 text-center">
            <div style={{ color: "var(--color-text-tertiary)" }} className="text-4xl mb-3">◇</div>
            <p style={{ color: "var(--color-text-tertiary)" }} className="text-sm">
              {searchQuery.length >= 2 ? "No entities match your search." : "No entities found. Run ingestion to populate."}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {entities.map(entity => (
              <EntityCard key={entity.aqid} entity={entity} />
            ))}
          </div>
        )}

        {/* Pagination */}
        {!searchQuery && total > 24 && (
          <div className="mt-6 flex items-center justify-center gap-3">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              style={{ color: "var(--color-text-tertiary)", border: "1px solid var(--color-space-border)" }}
              className="rounded px-3 py-1 font-mono text-xs disabled:opacity-40 hover:border-indigo-500 hover:text-indigo-400 transition-colors"
            >
              ← Prev
            </button>
            <span style={{ color: "var(--color-text-tertiary)" }} className="font-mono text-xs">
              Page {page} of {Math.ceil(total / 24)}
            </span>
            <button
              onClick={() => setPage(p => p + 1)}
              disabled={page >= Math.ceil(total / 24)}
              style={{ color: "var(--color-text-tertiary)", border: "1px solid var(--color-space-border)" }}
              className="rounded px-3 py-1 font-mono text-xs disabled:opacity-40 hover:border-indigo-500 hover:text-indigo-400 transition-colors"
            >
              Next →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
