/**
 * ORBITIQ-X — Entity Navigation Breadcrumb
 * Phase 17.6 — Cross-Entity Navigation
 *
 * Breadcrumb trail for graph exploration.
 * Stores the navigation history in sessionStorage so users can retrace
 * their path through the Aerospace Knowledge Universe.
 *
 * Shows: Home → Entity Class → Entity Name → (current)
 * Supports: back navigation, history clearing, "You are here" label.
 *
 * Usage (in entity page):
 *   <EntityBreadcrumb aqid={aqid} displayName={entity.display_name} entityClass={entity.entity_class} />
 */
"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";

const HISTORY_KEY = "orbitiq_entity_nav_history";
const MAX_HISTORY = 8;

interface BreadcrumbEntry {
  aqid: string;
  displayName: string;
  entityClass: string;
  href: string;
}

const CLASS_ICON: Record<string, string> = {
  SATELLITE: "🛰", LAUNCH_VEHICLE: "🚀", COMPANY: "🏢", GOV_AGENCY: "🏛",
  COUNTRY: "🌍", MISSION: "🎯", PROGRAM: "📋", TECHNOLOGY: "⚙️",
  RESEARCH_PAPER: "📄", PERSON: "👤", LAUNCH_SITE: "📍", CONSTELLATION: "✨",
  PATENT: "©", STANDARD: "📏", INCIDENT: "⚠️",
};

function loadHistory(): BreadcrumbEntry[] {
  try {
    const raw = sessionStorage.getItem(HISTORY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveHistory(history: BreadcrumbEntry[]): void {
  try {
    sessionStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(-MAX_HISTORY)));
  } catch {}
}

interface EntityBreadcrumbProps {
  aqid: string;
  displayName: string;
  entityClass: string;
}

export function EntityBreadcrumb({ aqid, displayName, entityClass }: EntityBreadcrumbProps) {
  const [history, setHistory] = useState<BreadcrumbEntry[]>([]);

  // On mount: load history and append current page
  useEffect(() => {
    const prev = loadHistory();
    const current: BreadcrumbEntry = {
      aqid,
      displayName,
      entityClass,
      href: `/entities/${encodeURIComponent(aqid)}`,
    };

    // Don't duplicate the current page
    const filtered = prev.filter(e => e.aqid !== aqid);
    const next = [...filtered, current];
    saveHistory(next);
    setHistory(next);
  }, [aqid, displayName, entityClass]);

  // The "trail" is everything before the current page
  const trail = history.slice(0, -1);
  const icon = CLASS_ICON[entityClass] ?? "◆";

  return (
    <nav
      className="flex items-center gap-1 px-6 py-2 overflow-x-auto"
      style={{
        background: "var(--color-space-deep)",
        borderBottom: "1px solid var(--color-space-border)",
      }}
      aria-label="Entity navigation breadcrumb"
    >
      {/* Home */}
      <Link
        href="/"
        style={{ color: "var(--color-text-tertiary)" }}
        className="shrink-0 font-mono text-[10px] hover:text-indigo-400 transition-colors"
      >
        ⊕ Mission Control
      </Link>

      <span style={{ color: "var(--color-space-border-strong)" }} className="font-mono text-[10px]">›</span>

      {/* Entity browser */}
      <Link
        href="/entities"
        style={{ color: "var(--color-text-tertiary)" }}
        className="shrink-0 font-mono text-[10px] hover:text-indigo-400 transition-colors"
      >
        ◆ Entity Browser
      </Link>

      {/* Navigation history trail */}
      {trail.slice(-3).map((entry) => (
        <React.Fragment key={entry.aqid}>
          <span style={{ color: "var(--color-space-border-strong)" }} className="font-mono text-[10px]">›</span>
          <Link
            href={entry.href}
            style={{ color: "var(--color-text-tertiary)" }}
            className="shrink-0 font-mono text-[10px] max-w-[120px] truncate hover:text-indigo-400 transition-colors"
            title={entry.displayName}
          >
            {CLASS_ICON[entry.entityClass] ?? "◆"} {entry.displayName}
          </Link>
        </React.Fragment>
      ))}

      {/* Current page */}
      <span style={{ color: "var(--color-space-border-strong)" }} className="font-mono text-[10px]">›</span>
      <span
        style={{ color: "var(--color-text-primary)" }}
        className="shrink-0 flex items-center gap-1 font-mono text-[10px] font-semibold"
      >
        <span>{icon}</span>
        <span className="max-w-[180px] truncate">{displayName}</span>
        <span
          style={{
            color: "#34d399",
            background: "rgba(52,211,153,0.1)",
            border: "1px solid rgba(52,211,153,0.3)",
          }}
          className="ml-1 rounded px-1 py-0.5 text-[8px] font-bold uppercase tracking-widest"
        >
          Here
        </span>
      </span>

      {/* Clear history */}
      {trail.length > 0 && (
        <button
          onClick={() => {
            saveHistory([]);
            setHistory(h => [h[h.length - 1]].filter(Boolean));
          }}
          style={{ color: "var(--color-text-tertiary)", marginLeft: "auto" }}
          className="shrink-0 font-mono text-[9px] hover:text-red-400 transition-colors"
          title="Clear navigation history"
        >
          ✕ Clear trail
        </button>
      )}
    </nav>
  );
}

// ─── Simple static breadcrumb for non-entity pages ────────────────────────────

interface StaticBreadcrumbProps {
  items: Array<{ label: string; href?: string }>;
}

export function StaticBreadcrumb({ items }: StaticBreadcrumbProps) {
  return (
    <nav
      className="flex items-center gap-1 px-6 py-2 overflow-x-auto"
      style={{
        background: "var(--color-space-deep)",
        borderBottom: "1px solid var(--color-space-border)",
      }}
    >
      {items.map((item, i) => (
        <React.Fragment key={i}>
          {i > 0 && (
            <span style={{ color: "var(--color-space-border-strong)" }} className="font-mono text-[10px]">›</span>
          )}
          {item.href ? (
            <Link
              href={item.href}
              style={{ color: i === items.length - 1 ? "var(--color-text-primary)" : "var(--color-text-tertiary)" }}
              className="shrink-0 font-mono text-[10px] hover:text-indigo-400 transition-colors"
            >
              {item.label}
            </Link>
          ) : (
            <span
              style={{ color: "var(--color-text-primary)" }}
              className="shrink-0 font-mono text-[10px] font-semibold"
            >
              {item.label}
            </span>
          )}
        </React.Fragment>
      ))}
    </nav>
  );
}
