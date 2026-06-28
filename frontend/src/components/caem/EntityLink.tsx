/**
 * ORBITIQ-X — EntityLink
 * Phase 17.6 — Cross-Entity Navigation
 *
 * Universal component that renders any aerospace entity reference as a
 * navigable link to its Entity Intelligence Page.
 *
 * Usage:
 *   <EntityLink aqid="AQID-COMPANY-SPACEX" />
 *   <EntityLink aqid="AQID-COMPANY-SPACEX" label="SpaceX" showClass />
 *   <EntityLink aqid="AQID-SATELLITE-ISS" variant="badge" />
 *   <EntityLink aqid="AQID-MISSION-ARTEMIS-II" variant="chip" showClass />
 *
 * Variants:
 *   inline  — plain text link (default), flows in prose
 *   badge   — pill badge with entity class color
 *   chip    — compact mono chip, suitable for relationship panels
 *   card    — small card with name + class (for sidebars)
 */
"use client";

import React from "react";
import Link from "next/link";

// Entity class → color + icon mapping (mirrors EntityHeader)
const CLASS_META: Record<string, { color: string; bg: string; icon: string }> = {
  SATELLITE:       { color: "#818cf8", bg: "rgba(99,102,241,0.12)",   icon: "🛰" },
  LAUNCH_VEHICLE:  { color: "#fbbf24", bg: "rgba(245,158,11,0.12)",  icon: "🚀" },
  COMPANY:         { color: "#34d399", bg: "rgba(16,185,129,0.12)",  icon: "🏢" },
  GOV_AGENCY:      { color: "#7dd3fc", bg: "rgba(125,211,252,0.12)", icon: "🏛" },
  COUNTRY:         { color: "#a78bfa", bg: "rgba(167,139,250,0.12)", icon: "🌍" },
  MISSION:         { color: "#f97316", bg: "rgba(249,115,22,0.12)",  icon: "🎯" },
  PROGRAM:         { color: "#06b6d4", bg: "rgba(6,182,212,0.12)",   icon: "📋" },
  RESEARCH_PAPER:  { color: "#e879f9", bg: "rgba(232,121,249,0.12)", icon: "📄" },
  TECHNOLOGY:      { color: "#4ade80", bg: "rgba(74,222,128,0.12)",  icon: "⚙️" },
  STANDARD:        { color: "#fcd34d", bg: "rgba(252,211,77,0.12)",  icon: "📏" },
  PATENT:          { color: "#fb923c", bg: "rgba(251,146,60,0.12)",  icon: "©" },
  PERSON:          { color: "#94a3b8", bg: "rgba(148,163,184,0.12)", icon: "👤" },
  LAUNCH_SITE:     { color: "#2dd4bf", bg: "rgba(45,212,191,0.12)",  icon: "📍" },
  GROUND_STATION:  { color: "#a3e635", bg: "rgba(163,230,53,0.12)",  icon: "📡" },
  CONSTELLATION:   { color: "#818cf8", bg: "rgba(99,102,241,0.10)",  icon: "✨" },
  DEBRIS:          { color: "#ef4444", bg: "rgba(239,68,68,0.12)",   icon: "💥" },
  INCIDENT:        { color: "#f87171", bg: "rgba(248,113,113,0.12)", icon: "⚠️" },
  CONTRACT:        { color: "#86efac", bg: "rgba(134,239,172,0.12)", icon: "📝" },
  INVESTMENT:      { color: "#4ade80", bg: "rgba(74,222,128,0.10)",  icon: "💰" },
  UNIVERSITY:      { color: "#c084fc", bg: "rgba(192,132,252,0.12)", icon: "🎓" },
};

const DEFAULT_META = { color: "#818cf8", bg: "rgba(99,102,241,0.10)", icon: "◆" };

/**
 * Extract entity class and a human label from an AQID.
 * "AQID-COMPANY-SPACEX"       → { class: "COMPANY", label: "SpaceX" }
 * "AQID-SATELLITE-ISS"        → { class: "SATELLITE", label: "ISS" }
 * "AQID-MISSION-ARTEMIS-II"   → { class: "MISSION", label: "Artemis II" }
 */
function parseAqid(aqid: string): { entityClass: string; derivedLabel: string } {
  const parts = aqid.split("-");
  if (parts.length < 3 || parts[0] !== "AQID") {
    return { entityClass: "UNKNOWN", derivedLabel: aqid };
  }
  const entityClass   = parts[1];
  const slug          = parts.slice(2).join("-");
  const derivedLabel  = slug
    .split("-")
    .map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
  return { entityClass, derivedLabel };
}

// ─── Component ────────────────────────────────────────────────────────────────

interface EntityLinkProps {
  aqid: string;
  label?: string;              // Override derived label
  showClass?: boolean;         // Show entity class prefix
  showIcon?: boolean;          // Show class icon
  variant?: "inline" | "badge" | "chip" | "card";
  className?: string;
}

export function EntityLink({
  aqid,
  label,
  showClass = false,
  showIcon  = false,
  variant   = "inline",
  className = "",
}: EntityLinkProps) {
  const { entityClass, derivedLabel } = parseAqid(aqid);
  const meta    = CLASS_META[entityClass] ?? DEFAULT_META;
  const display = label ?? derivedLabel;
  const href    = `/entities/${encodeURIComponent(aqid)}`;

  if (variant === "badge") {
    return (
      <Link href={href} className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 font-mono text-[10px] font-semibold transition-all hover:opacity-90 ${className}`}
        style={{ color: meta.color, background: meta.bg, borderColor: `${meta.color}40` }}>
        {showIcon && <span>{meta.icon}</span>}
        {showClass && (
          <span style={{ color: `${meta.color}99`, fontSize: "9px" }}>
            {entityClass.replace(/_/g, " ")} ·{" "}
          </span>
        )}
        {display}
      </Link>
    );
  }

  if (variant === "chip") {
    return (
      <Link href={href} className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[9px] transition-colors hover:border-indigo-400 ${className}`}
        style={{
          color: "var(--color-text-accent)",
          background: "var(--color-space-elevated)",
          borderColor: "var(--color-space-border)",
        }}>
        {showIcon && <span style={{ fontSize: "8px" }}>{meta.icon}</span>}
        {display}
        <span style={{ color: "var(--color-text-tertiary)", fontSize: "8px" }}>↗</span>
      </Link>
    );
  }

  if (variant === "card") {
    return (
      <Link href={href} className={`block rounded border p-2.5 transition-all hover:border-indigo-500 hover:shadow-sm ${className}`}
        style={{ background: "var(--color-space-elevated)", borderColor: "var(--color-space-border)" }}>
        <div className="flex items-center gap-1.5 mb-0.5">
          <span style={{ fontSize: "10px" }}>{meta.icon}</span>
          <span style={{ color: `${meta.color}99` }} className="font-mono text-[8px] uppercase tracking-wider">
            {entityClass.replace(/_/g, " ")}
          </span>
        </div>
        <div style={{ color: "var(--color-text-primary)" }} className="text-[11px] font-medium leading-tight">
          {display}
        </div>
        <div style={{ color: "var(--color-text-tertiary)" }} className="mt-0.5 font-mono text-[8px] truncate">
          {aqid}
        </div>
      </Link>
    );
  }

  // Default: inline
  return (
    <Link href={href} className={`font-medium transition-colors hover:underline ${className}`}
      style={{ color: "var(--color-text-accent)" }}>
      {showIcon && <span className="mr-1">{meta.icon}</span>}
      {showClass && (
        <span style={{ color: "var(--color-text-tertiary)", fontSize: "11px" }}>
          {entityClass.toLowerCase().replace(/_/g, " ")} ·{" "}
        </span>
      )}
      {display}
    </Link>
  );
}

// ─── AQID auto-linker ─────────────────────────────────────────────────────────
// Renders a string and converts any AQID-* tokens into EntityLink components.

const AQID_PATTERN = /AQID-[A-Z_]+-[A-Z0-9\-]+/g;

export function AutoLink({ text, variant = "chip" }: { text: string; variant?: EntityLinkProps["variant"] }) {
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  AQID_PATTERN.lastIndex = 0;
  while ((match = AQID_PATTERN.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    parts.push(
      <EntityLink key={match.index} aqid={match[0]} variant={variant} />
    );
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return <>{parts}</>;
}
