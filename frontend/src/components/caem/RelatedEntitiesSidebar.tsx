/**
 * ORBITIQ-X — Related Entities Sidebar
 * Phase 17.6 — Cross-Entity Navigation
 *
 * Contextually relevant entity cards shown alongside the entity intelligence page.
 * Groups related entities by semantic category (same class, same domain, neighbors).
 * Each card is an EntityLink in "card" variant → navigates to that entity's page.
 *
 * Data sources (in priority order):
 *   1. Relationship neighbors from the /neighborhood endpoint
 *   2. Same entity-class entities (from /entities list)
 *   3. Shared domain entities
 */
"use client";

import React, { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { caemApi } from "@/lib/caem-api";
import { EntityLink } from "./EntityLink";
import type { EntityFull, NeighborhoodGraph } from "@/lib/caem-api";

// ─── Neighbor section ─────────────────────────────────────────────────────────

function NeighborSection({
  neighborhood,
  centerAqid,
}: {
  neighborhood: NeighborhoodGraph;
  centerAqid: string;
}) {
  const neighbors = neighborhood.nodes
    .filter(n => n.aqid !== centerAqid)
    .slice(0, 8);

  if (neighbors.length === 0) return null;

  return (
    <div>
      <div style={{ color: "var(--color-text-tertiary)" }} className="mb-2 font-mono text-[9px] uppercase tracking-widest">
        Graph Neighbors
      </div>
      <div className="flex flex-col gap-1.5">
        {neighbors.map(node => (
          <EntityLink
            key={node.aqid}
            aqid={node.aqid}
            label={node.display_name}
            showClass
            showIcon
            variant="card"
          />
        ))}
      </div>
    </div>
  );
}

// ─── Same-class section ───────────────────────────────────────────────────────

function SameClassSection({
  entityClass,
  currentAqid,
}: {
  entityClass: string;
  currentAqid: string;
}) {
  const { data } = useQuery({
    queryKey: ["related-same-class", entityClass],
    queryFn: () => caemApi.listEntities({ entity_class: entityClass, page_size: 10 }),
    staleTime: 60_000,
  });

  const others = (data?.entities ?? [])
    .filter(e => e.aqid !== currentAqid)
    .slice(0, 6);

  if (others.length === 0) return null;

  const classLabel = entityClass.replace(/_/g, " ").toLowerCase();

  return (
    <div>
      <div style={{ color: "var(--color-text-tertiary)" }} className="mb-2 font-mono text-[9px] uppercase tracking-widest">
        More {classLabel}s
      </div>
      <div className="flex flex-col gap-1.5">
        {others.map(entity => (
          <EntityLink
            key={entity.aqid}
            aqid={entity.aqid}
            label={entity.display_name}
            showIcon
            variant="card"
          />
        ))}
      </div>
      <Link
        href={`/entities?class=${entityClass}`}
        style={{ color: "var(--color-text-tertiary)" }}
        className="mt-2 block text-center font-mono text-[9px] hover:text-indigo-400 transition-colors"
      >
        View all {classLabel}s →
      </Link>
    </div>
  );
}

// ─── Shared domain section ────────────────────────────────────────────────────

function SharedDomainSection({
  domains,
  currentAqid,
  entityClass,
}: {
  domains: string[];
  currentAqid: string;
  entityClass: string;
}) {
  const primaryDomain = domains[0];

  const { data } = useQuery({
    queryKey: ["related-domain", primaryDomain],
    queryFn: () => caemApi.listEntities({ domain: primaryDomain, page_size: 8 }),
    enabled: !!primaryDomain,
    staleTime: 60_000,
  });

  const related = (data?.entities ?? [])
    .filter(e => e.aqid !== currentAqid && e.entity_class !== entityClass)
    .slice(0, 5);

  if (related.length === 0 || !primaryDomain) return null;

  return (
    <div>
      <div style={{ color: "var(--color-text-tertiary)" }} className="mb-2 font-mono text-[9px] uppercase tracking-widest">
        Also in {primaryDomain.replace(/_/g, " ")}
      </div>
      <div className="flex flex-col gap-1.5">
        {related.map(entity => (
          <EntityLink
            key={entity.aqid}
            aqid={entity.aqid}
            label={entity.display_name}
            showClass
            showIcon
            variant="card"
          />
        ))}
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface RelatedEntitiesSidebarProps {
  entity: EntityFull;
  neighborhood?: NeighborhoodGraph | null;
}

export function RelatedEntitiesSidebar({ entity, neighborhood }: RelatedEntitiesSidebarProps) {
  return (
    <aside className="flex flex-col gap-5 w-64 shrink-0">
      {/* Header */}
      <div
        className="rounded-lg border px-4 py-3"
        style={{
          background: "var(--color-space-surface)",
          borderColor: "var(--color-space-border)",
        }}
      >
        <div style={{ color: "var(--color-text-secondary)" }} className="mb-1 font-mono text-[10px] font-bold uppercase tracking-widest">
          ◈ Related Entities
        </div>
        <p style={{ color: "var(--color-text-tertiary)" }} className="text-[10px] leading-relaxed">
          Navigate the Aerospace Knowledge Universe by exploring connected entities.
        </p>
      </div>

      {/* Neighbor entities from graph */}
      {neighborhood && neighborhood.nodes.length > 1 && (
        <div
          className="rounded-lg border p-4"
          style={{
            background: "var(--color-space-surface)",
            borderColor: "var(--color-space-border)",
          }}
        >
          <NeighborSection
            neighborhood={neighborhood}
            centerAqid={entity.aqid}
          />
        </div>
      )}

      {/* Same-class entities */}
      <div
        className="rounded-lg border p-4"
        style={{
          background: "var(--color-space-surface)",
          borderColor: "var(--color-space-border)",
        }}
      >
        <SameClassSection
          entityClass={entity.entity_class}
          currentAqid={entity.aqid}
        />
      </div>

      {/* Shared domain entities */}
      {entity.domains && entity.domains.length > 0 && (
        <div
          className="rounded-lg border p-4"
          style={{
            background: "var(--color-space-surface)",
            borderColor: "var(--color-space-border)",
          }}
        >
          <SharedDomainSection
            domains={entity.domains}
            currentAqid={entity.aqid}
            entityClass={entity.entity_class}
          />
        </div>
      )}

      {/* Quick navigation */}
      <div
        className="rounded-lg border p-4"
        style={{
          background: "var(--color-space-surface)",
          borderColor: "var(--color-space-border)",
        }}
      >
        <div style={{ color: "var(--color-text-tertiary)" }} className="mb-2 font-mono text-[9px] uppercase tracking-widest">
          Quick Jump
        </div>
        <div className="flex flex-col gap-1">
          {[
            { href: "/entities",         label: "◆ Entity Browser" },
            { href: "/knowledge-graph",  label: "◉ Knowledge Graph" },
            { href: "/intelligence",     label: "◈ AI Workspace" },
            { href: "/catalog",          label: "◫ Satellite Catalog" },
          ].map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              style={{
                color: "var(--color-text-tertiary)",
                background: "var(--color-space-elevated)",
                border: "1px solid var(--color-space-border)",
              }}
              className="block rounded px-2.5 py-1.5 font-mono text-[10px] transition-colors hover:border-indigo-500 hover:text-indigo-400"
            >
              {label}
            </Link>
          ))}
        </div>
      </div>
    </aside>
  );
}
