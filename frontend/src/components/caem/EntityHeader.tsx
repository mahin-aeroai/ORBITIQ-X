/**
 * ORBITIQ-X — Entity Intelligence Page Header
 * Phase 17.5
 *
 * Universal header for every aerospace entity page.
 * Renders: entity class badge, display name, AQID (copyable),
 * lifecycle status, confidence indicator, tags, domains.
 */
"use client";

import React, { useState } from "react";
import type { EntityFull } from "@/lib/caem-api";

// ─── Entity class → color + icon ─────────────────────────────────────────────

const CLASS_META: Record<string, { color: string; bg: string; icon: string; label: string }> = {
  SATELLITE:       { color: "#818cf8", bg: "rgba(99,102,241,0.12)",  icon: "🛰",  label: "Satellite" },
  LAUNCH_VEHICLE:  { color: "#fbbf24", bg: "rgba(245,158,11,0.12)", icon: "🚀",  label: "Launch Vehicle" },
  COMPANY:         { color: "#34d399", bg: "rgba(16,185,129,0.12)", icon: "🏢",  label: "Company" },
  GOV_AGENCY:      { color: "#7dd3fc", bg: "rgba(125,211,252,0.12)",icon: "🏛",  label: "Gov Agency" },
  COUNTRY:         { color: "#a78bfa", bg: "rgba(167,139,250,0.12)",icon: "🌍",  label: "Country" },
  MISSION:         { color: "#f97316", bg: "rgba(249,115,22,0.12)", icon: "🎯",  label: "Mission" },
  PROGRAM:         { color: "#06b6d4", bg: "rgba(6,182,212,0.12)",  icon: "📋",  label: "Program" },
  RESEARCH_PAPER:  { color: "#e879f9", bg: "rgba(232,121,249,0.12)",icon: "📄",  label: "Research Paper" },
  TECHNOLOGY:      { color: "#4ade80", bg: "rgba(74,222,128,0.12)", icon: "⚙️",  label: "Technology" },
  STANDARD:        { color: "#fcd34d", bg: "rgba(252,211,77,0.12)", icon: "📏",  label: "Standard" },
  PATENT:          { color: "#fb923c", bg: "rgba(251,146,60,0.12)", icon: "©",  label: "Patent" },
  PERSON:          { color: "#94a3b8", bg: "rgba(148,163,184,0.12)",icon: "👤",  label: "Person" },
  LAUNCH_SITE:     { color: "#2dd4bf", bg: "rgba(45,212,191,0.12)", icon: "📍",  label: "Launch Site" },
  GROUND_STATION:  { color: "#a3e635", bg: "rgba(163,230,53,0.12)", icon: "📡",  label: "Ground Station" },
  CONSTELLATION:   { color: "#818cf8", bg: "rgba(99,102,241,0.10)", icon: "✨",  label: "Constellation" },
  DEBRIS:          { color: "#ef4444", bg: "rgba(239,68,68,0.12)",  icon: "💥",  label: "Debris" },
  INCIDENT:        { color: "#f87171", bg: "rgba(248,113,113,0.12)",icon: "⚠️",  label: "Incident" },
  CONTRACT:        { color: "#86efac", bg: "rgba(134,239,172,0.12)",icon: "📝",  label: "Contract" },
  INVESTMENT:      { color: "#4ade80", bg: "rgba(74,222,128,0.10)", icon: "💰",  label: "Investment" },
};

const DEFAULT_META = { color: "#94a3b8", bg: "rgba(148,163,184,0.12)", icon: "◆", label: "Entity" };

// ─── Confidence badge ─────────────────────────────────────────────────────────

function ConfidenceBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const [color, label] =
    score >= 0.90 ? ["#34d399", "Authoritative"] :
    score >= 0.75 ? ["#818cf8", "Verified"] :
    score >= 0.60 ? ["#7dd3fc", "Confirmed"] :
    score >= 0.45 ? ["#fbbf24", "Unverified"] :
                    ["#ef4444", "Disputed"];

  return (
    <span
      style={{ color, border: `1px solid ${color}`, background: `${color}18` }}
      className="inline-flex items-center gap-1.5 rounded px-2 py-0.5 font-mono text-[10px] font-semibold"
    >
      <span
        style={{ background: color }}
        className="inline-block h-1.5 w-1.5 rounded-full"
      />
      {pct}% · {label}
    </span>
  );
}

// ─── Lifecycle badge ──────────────────────────────────────────────────────────

function LifecycleBadge({ status }: { status: string }) {
  const s = status.toUpperCase();
  const [color, bg] =
    s === "PUBLISHED"   ? ["#34d399", "rgba(52,211,153,0.12)"] :
    s === "DRAFT"       ? ["#fbbf24", "rgba(251,191,36,0.12)"] :
    s === "PENDING"     ? ["#7dd3fc", "rgba(125,211,252,0.12)"] :
    s === "DEPRECATED"  ? ["#94a3b8", "rgba(148,163,184,0.12)"] :
                          ["#475569", "rgba(71,85,105,0.12)"];
  return (
    <span
      style={{ color, background: bg, border: `1px solid ${color}40` }}
      className="rounded px-2 py-0.5 font-mono text-[9px] font-bold uppercase tracking-widest"
    >
      {status}
    </span>
  );
}

// ─── Component ────────────────────────────────────────────────────────────────

interface EntityHeaderProps {
  entity: EntityFull;
}

export function EntityHeader({ entity }: EntityHeaderProps) {
  const [copied, setCopied] = useState(false);
  const meta = CLASS_META[entity.entity_class] ?? DEFAULT_META;

  const copyAqid = () => {
    navigator.clipboard.writeText(entity.aqid).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <div
      className="border-b px-6 py-5"
      style={{ borderColor: "var(--color-space-border)", background: "var(--color-space-navy)" }}
    >
      {/* Class badge + name row */}
      <div className="flex flex-wrap items-start gap-3">
        {/* Entity class badge */}
        <span
          style={{ color: meta.color, background: meta.bg, border: `1px solid ${meta.color}40` }}
          className="mt-0.5 flex items-center gap-1.5 rounded px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-widest"
        >
          <span>{meta.icon}</span>
          {meta.label}
          {entity.entity_subclass && (
            <span style={{ color: `${meta.color}99` }}>· {entity.entity_subclass.toLowerCase()}</span>
          )}
        </span>

        {/* Display name */}
        <h1
          style={{ color: "var(--color-text-primary)", fontFamily: "var(--font-display, inherit)" }}
          className="text-2xl font-bold leading-tight"
        >
          {entity.display_name}
          {entity.short_name && entity.short_name !== entity.display_name && (
            <span style={{ color: "var(--color-text-tertiary)" }} className="ml-2 text-base font-normal">
              ({entity.short_name})
            </span>
          )}
        </h1>
      </div>

      {/* AQID + status row */}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {/* Copyable AQID */}
        <button
          onClick={copyAqid}
          title="Copy AQID"
          style={{
            color: copied ? "#34d399" : "var(--color-text-tertiary)",
            background: "var(--color-space-surface)",
            border: "1px solid var(--color-space-border)",
            fontFamily: "var(--font-mono, monospace)",
          }}
          className="flex items-center gap-1.5 rounded px-2 py-0.5 text-[10px] transition-colors hover:border-indigo-500 hover:text-indigo-400"
        >
          {copied ? "✓ Copied" : entity.aqid}
        </button>

        <LifecycleBadge status={entity.lifecycle_status} />
        <ConfidenceBadge score={entity.confidence_score} />

        {entity.current_version && (
          <span style={{ color: "var(--color-text-tertiary)" }} className="font-mono text-[9px]">
            v{entity.current_version}
          </span>
        )}

        {entity.updated_at && (
          <span style={{ color: "var(--color-text-tertiary)" }} className="text-[10px]">
            Updated {new Date(entity.updated_at).toLocaleDateString()}
          </span>
        )}
      </div>

      {/* Aliases */}
      {entity.aliases?.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {entity.aliases.slice(0, 6).map(a => (
            <span
              key={a}
              style={{ color: "var(--color-text-tertiary)", background: "var(--color-space-surface)", border: "1px solid var(--color-space-border)" }}
              className="rounded px-1.5 py-0.5 font-mono text-[9px]"
            >
              {a}
            </span>
          ))}
          {entity.aliases.length > 6 && (
            <span style={{ color: "var(--color-text-tertiary)" }} className="text-[9px]">
              +{entity.aliases.length - 6} more
            </span>
          )}
        </div>
      )}

      {/* Tags + domains */}
      <div className="mt-2 flex flex-wrap gap-1.5">
        {entity.tags?.slice(0, 8).map(tag => (
          <span
            key={tag}
            style={{ color: meta.color, background: meta.bg, border: `1px solid ${meta.color}30` }}
            className="rounded px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider"
          >
            {tag}
          </span>
        ))}
        {entity.domains?.slice(0, 4).map(d => (
          <span
            key={d}
            style={{ color: "var(--color-text-secondary)", background: "var(--color-space-surface)", border: "1px solid var(--color-space-border)" }}
            className="rounded px-1.5 py-0.5 font-mono text-[9px]"
          >
            {d.replace(/_/g, " ")}
          </span>
        ))}
      </div>
    </div>
  );
}
