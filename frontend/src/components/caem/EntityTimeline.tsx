/**
 * ORBITIQ-X — Entity Timeline Component
 * Phase 17.5
 *
 * Horizontally scrollable chronological timeline of entity lifecycle events.
 * Color-coded by importance: critical (red), major (indigo), minor (slate).
 * Each event links to related entities.
 */
"use client";

import React from "react";
import type { TimelineEvent } from "@/lib/caem-api";
import Link from "next/link";

const IMPORTANCE_COLOR = {
  critical: { dot: "#ef4444", line: "rgba(239,68,68,0.4)",  label: "var(--color-accent-red)" },
  major:    { dot: "#818cf8", line: "rgba(129,140,248,0.4)", label: "var(--color-accent-indigo-bright)" },
  minor:    { dot: "#475569", line: "rgba(71,85,105,0.4)",   label: "var(--color-text-tertiary)" },
};

function formatDate(dateStr?: string, precision?: string): string {
  if (!dateStr) return "Unknown";
  try {
    const d = new Date(dateStr);
    if (precision === "year")  return d.getFullYear().toString();
    if (precision === "month") return d.toLocaleDateString("en-US", { year: "numeric", month: "short" });
    return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return dateStr;
  }
}

interface EntityTimelineProps {
  events: TimelineEvent[];
}

export function EntityTimeline({ events }: EntityTimelineProps) {
  if (!events || events.length === 0) {
    return (
      <div
        className="rounded-lg border p-4 text-center"
        style={{ borderColor: "var(--color-space-border)", background: "var(--color-space-surface)" }}
      >
        <span style={{ color: "var(--color-text-tertiary)" }} className="text-sm">
          No timeline events recorded yet.
        </span>
      </div>
    );
  }

  const sorted = [...events].sort((a, b) => {
    if (!a.date && !b.date) return 0;
    if (!a.date) return 1;
    if (!b.date) return -1;
    return a.date < b.date ? -1 : 1;
  });

  return (
    <div
      className="rounded-lg border"
      style={{ borderColor: "var(--color-space-border)", background: "var(--color-space-surface)" }}
    >
      <div className="border-b px-4 py-2.5" style={{ borderColor: "var(--color-space-border)" }}>
        <span style={{ color: "var(--color-text-secondary)" }} className="text-xs font-bold uppercase tracking-widest">
          ◈ Timeline · {sorted.length} Events
        </span>
      </div>

      {/* Horizontal scroll container */}
      <div className="overflow-x-auto px-4 py-5">
        <div className="relative" style={{ minWidth: `${Math.max(sorted.length * 180, 600)}px` }}>
          {/* Horizontal connector line */}
          <div
            className="absolute top-3 left-0 right-0 h-px"
            style={{ background: "var(--color-space-border-strong)" }}
          />

          {/* Events */}
          <div className="flex gap-0">
            {sorted.map((event, idx) => {
              const importance = (event.importance ?? "minor") as keyof typeof IMPORTANCE_COLOR;
              const colors = IMPORTANCE_COLOR[importance] ?? IMPORTANCE_COLOR.minor;

              return (
                <div
                  key={event.event_id ?? idx}
                  className="flex flex-col items-center"
                  style={{ width: "180px", flexShrink: 0 }}
                >
                  {/* Dot */}
                  <div
                    className="relative z-10 flex h-6 w-6 items-center justify-center rounded-full border-2"
                    style={{
                      background: "var(--color-space-surface)",
                      borderColor: colors.dot,
                      boxShadow: `0 0 8px ${colors.line}`,
                    }}
                  >
                    <div
                      className="h-2 w-2 rounded-full"
                      style={{ background: colors.dot }}
                    />
                  </div>

                  {/* Content */}
                  <div className="mt-3 w-full px-2 text-center">
                    {/* Date */}
                    <div style={{ color: "var(--color-text-data)" }} className="mb-1 font-mono text-[10px] font-bold">
                      {formatDate(event.date, event.date_precision)}
                    </div>

                    {/* Label */}
                    <div
                      style={{ color: colors.label, wordBreak: "break-word" }}
                      className="text-[11px] font-semibold leading-tight"
                    >
                      {event.label}
                    </div>

                    {/* Description */}
                    {event.description && (
                      <div
                        style={{ color: "var(--color-text-tertiary)" }}
                        className="mt-1 text-[10px] leading-relaxed"
                      >
                        {event.description.length > 80
                          ? `${event.description.slice(0, 80)}…`
                          : event.description}
                      </div>
                    )}

                    {/* Linked entities */}
                    {event.linked_aqids?.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap justify-center gap-1">
                        {event.linked_aqids.slice(0, 2).map(aqid => (
                          <Link
                            key={aqid}
                            href={`/entities/${encodeURIComponent(aqid)}`}
                            style={{
                              color: "var(--color-accent-indigo-bright)",
                              border: "1px solid rgba(99,102,241,0.3)",
                              background: "rgba(99,102,241,0.08)",
                            }}
                            className="rounded px-1 py-0.5 font-mono text-[9px] hover:border-indigo-400 transition-colors"
                          >
                            →
                          </Link>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
