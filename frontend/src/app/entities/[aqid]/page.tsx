/**
 * ORBITIQ-X — Entity Intelligence Page
 * Phase 17.5
 *
 * Universal entity page. Every aerospace entity in the CAEM renders here.
 * Loads the full entity record, relationships, and neighborhood graph,
 * then composes the canonical 8-panel layout.
 *
 * URL: /entities/AQID-COMPANY-SPACEX
 *      /entities/AQID-SATELLITE-ISS
 *      /entities/AQID-MISSION-ARTEMIS-II
 */

"use client";
// @ts-nocheck

import React, { Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";

import { caemApi } from "@/lib/caem-api";
import { EntityHeader }      from "@/components/caem/EntityHeader";
import { AISummaryCard }     from "@/components/caem/AISummaryCard";
import { QuickFacts }        from "@/components/caem/QuickFacts";
import { EntityTimeline }    from "@/components/caem/EntityTimeline";
import { RelationshipPanel } from "@/components/caem/RelationshipPanel";
import { ProvenancePanel }   from "@/components/caem/ProvenancePanel";

// ─── Loading skeleton ─────────────────────────────────────────────────────────

function EntitySkeleton() {
  const pulse = "animate-pulse rounded";
  return (
    <div className="flex flex-col gap-5 p-6">
      <div className={`${pulse} h-16 w-full`} style={{ background: "var(--color-space-surface)" }} />
      <div className={`${pulse} h-28 w-full`} style={{ background: "var(--color-space-surface)" }} />
      <div className="grid grid-cols-3 gap-4">
        <div className={`${pulse} col-span-2 h-40`} style={{ background: "var(--color-space-surface)" }} />
        <div className={`${pulse} h-40`}             style={{ background: "var(--color-space-surface)" }} />
      </div>
      <div className={`${pulse} h-32 w-full`} style={{ background: "var(--color-space-surface)" }} />
      <div className={`${pulse} h-64 w-full`} style={{ background: "var(--color-space-surface)" }} />
      <div className={`${pulse} h-40 w-full`} style={{ background: "var(--color-space-surface)" }} />
    </div>
  );
}

// ─── Error state ──────────────────────────────────────────────────────────────

function EntityError({ aqid, error }: { aqid: string; error: Error }) {
  return (
    <div className="flex flex-col items-center justify-center py-24">
      <div
        className="mb-4 rounded-lg border px-6 py-8 text-center"
        style={{
          borderColor: "rgba(239,68,68,0.3)",
          background: "rgba(239,68,68,0.05)",
          maxWidth: "480px",
        }}
      >
        <div style={{ color: "#ef4444" }} className="mb-2 text-2xl">⚠</div>
        <div style={{ color: "var(--color-text-primary)" }} className="mb-1 font-bold">
          Entity Not Found
        </div>
        <div style={{ color: "var(--color-text-tertiary)" }} className="font-mono text-sm">
          {aqid}
        </div>
        <div style={{ color: "var(--color-text-tertiary)" }} className="mt-2 text-xs">
          {error.message}
        </div>
      </div>
    </div>
  );
}

// ─── Section wrapper ──────────────────────────────────────────────────────────

function Section({
  title,
  children,
  action,
}: {
  title: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h2
          style={{ color: "var(--color-text-secondary)", fontFamily: "var(--font-mono, monospace)" }}
          className="text-[11px] font-bold uppercase tracking-widest"
        >
          {title}
        </h2>
        {action}
      </div>
      {children}
    </section>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function EntityPage() {
  const { aqid } = useParams<{ aqid: string }>();
  const decodedAqid = decodeURIComponent(aqid ?? "");

  const { data: entity, isLoading, error, refetch } = useQuery({
    queryKey: ["entity", decodedAqid],
    queryFn: () => caemApi.getEntity(decodedAqid),
    enabled: !!decodedAqid,
    staleTime: 30_000,
  });

  const { data: relationships } = useQuery({
    queryKey: ["entity-relationships", decodedAqid],
    queryFn: () => caemApi.getRelationships(decodedAqid),
    enabled: !!decodedAqid,
    staleTime: 60_000,
  });

  const { data: neighborhood } = useQuery({
    queryKey: ["entity-neighborhood", decodedAqid],
    queryFn: () => caemApi.getNeighborhood(decodedAqid, 2),
    enabled: !!decodedAqid,
    staleTime: 120_000,
  });

  if (isLoading) return <EntitySkeleton />;
  if (error || !entity) return <EntityError aqid={decodedAqid} error={error as Error ?? new Error("Not found")} />;

  return (
    <div
      className="flex flex-col gap-5 overflow-y-auto pb-10"
      style={{ background: "var(--color-space-midnight)", minHeight: "100vh" }}
    >
      {/* 1. HEADER */}
      <EntityHeader entity={entity} />

      <div className="flex flex-col gap-5 px-6">
        {/* 2. AI EXECUTIVE SUMMARY */}
        <Section title="Intelligence Summary">
          <AISummaryCard entity={entity} onRefresh={() => refetch()} />
        </Section>

        {/* 3. QUICK FACTS + MINI GRAPH */}
        <Section title="Quick Facts">
          <QuickFacts entity={entity} neighborhood={neighborhood ?? null} />
        </Section>

        {/* 4. TIMELINE */}
        <Section title="Timeline">
          <EntityTimeline events={entity.timeline_events ?? []} />
        </Section>

        {/* 5. RELATIONSHIPS */}
        <Section
          title="Relationships"
          action={
            <a
              href={`/knowledge-graph?center=${encodeURIComponent(decodedAqid)}`}
              style={{ color: "var(--color-text-tertiary)" }}
              className="font-mono text-[10px] hover:text-indigo-400 transition-colors"
            >
              Open in Graph Explorer →
            </a>
          }
        >
          <RelationshipPanel
            relationships={relationships ?? []}
            centerAqid={decodedAqid}
          />
        </Section>

        {/* 6. EXTENSION DETAILS */}
        {entity.extension_data && Object.keys(entity.extension_data).length > 0 && (
          <Section title="Technical Details">
            <div
              className="rounded-lg border p-4"
              style={{
                background: "var(--color-space-surface)",
                borderColor: "var(--color-space-border)",
              }}
            >
              <dl className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3 lg:grid-cols-4">
                {Object.entries(entity.extension_data)
                  .filter(([, v]) => v !== null && v !== undefined && v !== "" && !Array.isArray(v) && typeof v !== "object")
                  .slice(0, 24)
                  .map(([key, value]) => (
                    <div key={key}>
                      <dt style={{ color: "var(--color-text-tertiary)" }} className="font-mono text-[9px] uppercase tracking-wider">
                        {key.replace(/_/g, " ")}
                      </dt>
                      <dd style={{ color: "var(--color-text-data)" }} className="font-mono text-sm font-semibold">
                        {String(value)}
                      </dd>
                    </div>
                  ))}
              </dl>
            </div>
          </Section>
        )}

        {/* 7. SOURCES & PROVENANCE */}
        <Section title="Sources & Provenance">
          <ProvenancePanel entity={entity} />
        </Section>

        {/* 8. LONG DESCRIPTION */}
        {entity.long_description && (
          <Section title="Historical Context">
            <div
              className="rounded-lg border p-5"
              style={{
                background: "var(--color-space-surface)",
                borderColor: "var(--color-space-border)",
              }}
            >
              <p
                style={{ color: "var(--color-text-secondary)", lineHeight: 1.75 }}
                className="text-sm"
              >
                {entity.long_description}
              </p>
            </div>
          </Section>
        )}
      </div>
    </div>
  );
}
