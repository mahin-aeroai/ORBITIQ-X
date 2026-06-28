/**
 * ORBITIQ-X — Quick Facts + Mini Graph Panel
 * Phase 17.5
 *
 * Two-column layout: structured quick facts on the left,
 * a mini graph neighborhood preview on the right.
 * Entity-class-specific fields rendered from extension_data.
 */
"use client";

import React from "react";
import Link from "next/link";
import type { EntityFull, NeighborhoodGraph } from "@/lib/caem-api";

// ─── Entity-class fact extractors ─────────────────────────────────────────────

function extractFacts(entity: EntityFull): Array<{ label: string; value: string }> {
  const ext  = entity.extension_data ?? {};
  const cls  = entity.entity_class;
  const facts: Array<{ label: string; value: string }> = [];

  const add = (label: string, value: unknown, unit = "") => {
    if (value !== null && value !== undefined && value !== "") {
      facts.push({ label, value: `${value}${unit ? " " + unit : ""}` });
    }
  };

  // Universal
  add("Founded / Created", entity.founded_or_created);
  add("Operational Start",  entity.operational_start);
  add("Operational End",    entity.operational_end);

  // Class-specific
  if (cls === "SATELLITE" || cls === "PAYLOAD" || cls === "DEBRIS") {
    add("NORAD ID",       ext.norad_id);
    add("COSPAR ID",      ext.cospar_id);
    add("Orbit Regime",   ext.orbit_regime);
    add("Altitude",       ext.altitude_km, "km");
    add("Inclination",    ext.inclination_deg, "°");
    add("Period",         ext.period_min, "min");
    add("Mass",           ext.mass_kg, "kg");
    add("Launch Date",    ext.launch_date);
    add("Mission Type",   ext.mission_type);
  }

  if (cls === "LAUNCH_VEHICLE") {
    add("Payload to LEO", ext.payload_leo_kg, "kg");
    add("Payload to GTO", ext.payload_gto_kg, "kg");
    add("Height",         ext.height_m, "m");
    add("Liftoff Mass",   ext.liftoff_mass_t, "t");
    add("Reusable",       ext.reusable ? "Yes" : ext.reusable === false ? "No" : undefined);
    add("Success Rate",   ext.success_rate_pct, "%");
    add("Total Launches", ext.total_launches);
    add("First Flight",   ext.first_flight_date);
  }

  if (cls === "COMPANY" || cls === "GOV_AGENCY") {
    add("Founded",        ext.founded_year);
    add("HQ",             ext.headquarters_city);
    add("Employees",      ext.employee_count);
    add("Revenue",        ext.revenue_musd, "M USD");
    add("CEO",            ext.ceo);
    add("Ticker",         ext.ticker);
    add("Active Satellites", ext.active_satellites);
  }

  if (cls === "MISSION") {
    add("Type",           ext.mission_type);
    add("Destination",    ext.destination);
    add("Status",         ext.mission_status);
    add("Launch Date",    ext.launch_date);
    add("Duration",       ext.duration_days, "days");
    add("Crew Size",      ext.crew_size);
    add("Total Cost",     ext.total_cost_musd, "M USD");
  }

  if (cls === "RESEARCH_PAPER") {
    add("DOI",            ext.doi);
    add("Journal",        ext.journal);
    add("Published",      ext.published_year);
    add("Citations",      ext.citation_count);
  }

  if (cls === "COUNTRY") {
    add("ISO Code",       ext.iso_code_alpha2);
    add("Capital",        ext.capital_city);
    add("Space Budget",   ext.space_budget_musd, "M USD");
    add("Active Satellites", ext.active_satellites);
    add("Launch Capability", ext.launch_capability ? "Yes" : undefined);
  }

  return facts.slice(0, 12);  // Cap at 12 for layout
}

// ─── Mini graph node ──────────────────────────────────────────────────────────

function MiniNode({
  aqid,
  label,
  isCenter,
  x,
  y,
}: {
  aqid: string;
  label: string;
  isCenter: boolean;
  x: number;
  y: number;
}) {
  const short = label.length > 18 ? `${label.slice(0, 17)}…` : label;
  return (
    <g transform={`translate(${x},${y})`}>
      <circle
        r={isCenter ? 16 : 10}
        fill={isCenter ? "rgba(99,102,241,0.25)" : "rgba(71,85,105,0.25)"}
        stroke={isCenter ? "#818cf8" : "#475569"}
        strokeWidth={isCenter ? 2 : 1}
      />
      <text
        textAnchor="middle"
        dy="0.35em"
        fontSize={isCenter ? 6 : 5}
        fill={isCenter ? "#818cf8" : "#94a3b8"}
      >
        {short.slice(0, 10)}
      </text>
    </g>
  );
}

// ─── Component ────────────────────────────────────────────────────────────────

interface QuickFactsProps {
  entity: EntityFull;
  neighborhood?: NeighborhoodGraph | null;
}

export function QuickFacts({ entity, neighborhood }: QuickFactsProps) {
  const facts = extractFacts(entity);

  // Simple radial layout for mini graph
  const centerX = 120, centerY = 100, radius = 72;
  const neighbors = neighborhood?.nodes
    ?.filter(n => n.aqid !== entity.aqid)
    ?.slice(0, 8) ?? [];

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      {/* Quick facts — 2/3 width */}
      <div
        className="col-span-1 rounded-lg border p-4 lg:col-span-2"
        style={{ background: "var(--color-space-surface)", borderColor: "var(--color-space-border)" }}
      >
        <div className="mb-3">
          <span style={{ color: "var(--color-text-secondary)" }} className="text-xs font-bold uppercase tracking-widest">
            ◈ Quick Facts
          </span>
        </div>

        {facts.length === 0 ? (
          <p style={{ color: "var(--color-text-tertiary)" }} className="text-sm italic">
            No structured facts available yet.
          </p>
        ) : (
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2">
            {facts.map(({ label, value }) => (
              <div key={label}>
                <dt style={{ color: "var(--color-text-tertiary)" }} className="font-mono text-[9px] uppercase tracking-wider">
                  {label}
                </dt>
                <dd style={{ color: "var(--color-text-data)" }} className="font-mono text-sm font-semibold">
                  {value}
                </dd>
              </div>
            ))}
          </dl>
        )}

        {/* Description */}
        {entity.description && (
          <p
            style={{ color: "var(--color-text-secondary)", borderTop: "1px solid var(--color-space-border)" }}
            className="mt-4 pt-3 text-sm leading-relaxed"
          >
            {entity.description}
          </p>
        )}
      </div>

      {/* Mini graph — 1/3 width */}
      <div
        className="rounded-lg border p-4"
        style={{ background: "var(--color-space-surface)", borderColor: "var(--color-space-border)" }}
      >
        <div className="mb-3 flex items-center justify-between">
          <span style={{ color: "var(--color-text-secondary)" }} className="text-xs font-bold uppercase tracking-widest">
            ◈ Graph
          </span>
          <Link
            href={`/knowledge-graph?center=${encodeURIComponent(entity.aqid)}`}
            style={{ color: "var(--color-text-tertiary)" }}
            className="font-mono text-[10px] hover:text-indigo-400"
          >
            Expand →
          </Link>
        </div>

        {neighbors.length === 0 ? (
          <div className="flex h-32 items-center justify-center">
            <span style={{ color: "var(--color-text-tertiary)" }} className="text-[11px]">
              No graph data yet
            </span>
          </div>
        ) : (
          <svg viewBox="0 0 240 200" className="w-full" style={{ maxHeight: "180px" }}>
            {/* Edges */}
            {neighbors.map((node, i) => {
              const angle  = (i / neighbors.length) * 2 * Math.PI - Math.PI / 2;
              const nx     = centerX + radius * Math.cos(angle);
              const ny     = centerY + radius * Math.sin(angle);
              return (
                <line
                  key={node.aqid}
                  x1={centerX} y1={centerY} x2={nx} y2={ny}
                  stroke="#2a3f66" strokeWidth={1}
                />
              );
            })}

            {/* Neighbor nodes */}
            {neighbors.map((node, i) => {
              const angle  = (i / neighbors.length) * 2 * Math.PI - Math.PI / 2;
              const nx     = centerX + radius * Math.cos(angle);
              const ny     = centerY + radius * Math.sin(angle);
              return (
                <MiniNode
                  key={node.aqid}
                  aqid={node.aqid}
                  label={node.display_name}
                  isCenter={false}
                  x={nx}
                  y={ny}
                />
              );
            })}

            {/* Center node */}
            <MiniNode
              aqid={entity.aqid}
              label={entity.display_name}
              isCenter
              x={centerX}
              y={centerY}
            />
          </svg>
        )}
      </div>
    </div>
  );
}
