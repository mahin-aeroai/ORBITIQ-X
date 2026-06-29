/**
 * ORBITIQ-X — Aerospace Knowledge Universe Intelligence Hub
 * Phases 17.7–17.10
 *
 * Unified intelligence dashboard covering:
 *   Business Intelligence  — contracts, investments, market
 *   Historical Intelligence — events, incidents, lineage
 *   Scientific Knowledge   — papers, standards, patents
 *   AKU v1 Status         — corpus overview
 */
"use client";
// @ts-nocheck
import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

const V2 = "/api/v2/intelligence";

async function apiFetch(path: string) {
  const res = await fetch(`${V2}${path}`);
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

// ─── Design tokens ────────────────────────────────────────────────────────────
const T = {
  indigo: "#818cf8", green: "#34d399", amber: "#fbbf24",
  cyan: "#7dd3fc", purple: "#c084fc", orange: "#f97316",
  surface: "var(--color-space-surface)", border: "var(--color-space-border)",
  elevated: "var(--color-space-elevated)", navy: "var(--color-space-navy)",
  textPrimary: "var(--color-text-primary)", textSecondary: "var(--color-text-secondary)",
  textTertiary: "var(--color-text-tertiary)", textData: "var(--color-text-data)",
};

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-lg border p-4 ${className}`}
      style={{ background: T.surface, borderColor: T.border }}>{children}</div>
  );
}

function SectionHeader({ icon, title, count }: { icon: string; title: string; count?: number }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <span className="text-base">{icon}</span>
      <span style={{ color: T.textSecondary }} className="font-mono text-xs font-bold uppercase tracking-widest">
        {title}
      </span>
      {count !== undefined && (
        <span style={{ color: T.textTertiary, background: T.elevated, border: `1px solid ${T.border}` }}
          className="ml-auto rounded px-1.5 py-0.5 font-mono text-[9px]">
          {count}
        </span>
      )}
    </div>
  );
}

function ValueChip({ value, unit = "M USD", color = T.green }: { value: number; unit?: string; color?: string }) {
  return (
    <span style={{ color, background: `${color}18` }}
      className="inline-flex items-baseline gap-0.5 rounded px-2 py-0.5 font-mono text-xs font-bold">
      ${value >= 1000 ? `${(value/1000).toFixed(1)}B` : `${value}M`}
    </span>
  );
}

// ─── TAB SECTIONS ─────────────────────────────────────────────────────────────

function AKUStatus() {
  const { data, isLoading } = useQuery({ queryKey: ["aku-status"], queryFn: () => apiFetch("/aku-status"), staleTime: 300_000 });
  if (isLoading) return <div className="animate-pulse h-40 rounded-lg" style={{ background: T.surface }} />;
  const s = data?.corpus_summary ?? {};
  const layers = data?.layers ?? {};

  return (
    <div className="space-y-4">
      {/* Corpus metrics grid */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {[
          { label: "Entity Classes", value: s.entity_classes_supported, color: T.indigo },
          { label: "Relationship Types", value: s.relationship_types, color: T.indigo },
          { label: "Neo4j Nodes", value: s.neo4j_nodes?.toLocaleString(), color: T.green },
          { label: "Neo4j Relationships", value: s.neo4j_relationships?.toLocaleString(), color: T.green },
          { label: "Qdrant Chunks", value: s.qdrant_chunks, color: T.cyan },
          { label: "GraphRAG Benchmark", value: s.graphrag_benchmark, color: T.green },
          { label: "Contracts Tracked", value: s.contracts_tracked, color: T.amber },
          { label: "Research Papers", value: s.research_papers, color: T.purple },
          { label: "Standards", value: s.standards, color: T.purple },
          { label: "Historical Events", value: s.historical_events, color: T.orange },
          { label: "Incidents", value: s.incidents_documented, color: T.orange },
          { label: "Patents", value: s.patents, color: T.purple },
        ].map(({ label, value, color }) => (
          <div key={label} className="rounded border p-3" style={{ background: T.elevated, borderColor: T.border }}>
            <div style={{ color: T.textTertiary }} className="mb-0.5 font-mono text-[9px] uppercase tracking-wider">{label}</div>
            <div style={{ color }} className="font-mono text-lg font-bold tabular-nums">{value ?? "—"}</div>
          </div>
        ))}
      </div>

      {/* Layer status */}
      <Card>
        <SectionHeader icon="◈" title="Knowledge Layer Status" />
        <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3 lg:grid-cols-5">
          {Object.entries(layers).map(([key, val]: [string, any]) => (
            <div key={key} className="flex items-center gap-2 rounded border px-2 py-1.5"
              style={{ borderColor: T.border, background: T.navy }}>
              <span style={{ background: val.status === "complete" ? T.green : T.amber }}
                className="h-1.5 w-1.5 rounded-full shrink-0" />
              <div>
                <div style={{ color: T.textPrimary }} className="font-mono text-[9px] font-semibold">
                  {key.replace(/_/g, " ")}
                </div>
                <div style={{ color: T.textTertiary }} className="font-mono text-[8px]">Phase {val.phase}</div>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function ContractsPanel() {
  const { data, isLoading } = useQuery({ queryKey: ["contracts"], queryFn: () => apiFetch("/contracts?limit=10"), staleTime: 300_000 });
  if (isLoading) return <div className="animate-pulse h-48 rounded-lg" style={{ background: T.surface }} />;
  const contracts = data?.contracts ?? [];

  return (
    <div className="space-y-2">
      {contracts.map((c: any, i: number) => (
        <div key={i} className="flex items-start gap-3 rounded border p-3 transition-colors hover:border-indigo-500"
          style={{ background: T.elevated, borderColor: T.border }}>
          <div className="flex-1 min-w-0">
            <div style={{ color: T.textPrimary }} className="text-sm font-semibold leading-tight">{c.display_name}</div>
            <div className="mt-0.5 flex flex-wrap gap-2">
              <span style={{ color: T.textTertiary }} className="font-mono text-[9px]">{c.client} → {c.recipient}</span>
              <span style={{ color: c.status === "active" ? T.green : T.textTertiary }}
                className="font-mono text-[9px] uppercase">{c.status}</span>
            </div>
            {c.scope && <div style={{ color: T.textTertiary }} className="mt-1 text-[10px] leading-relaxed line-clamp-1">{c.scope}</div>}
          </div>
          {c.value_musd && <ValueChip value={c.value_musd} />}
        </div>
      ))}
    </div>
  );
}

function InvestmentsPanel() {
  const { data, isLoading } = useQuery({ queryKey: ["investments"], queryFn: () => apiFetch("/investments?limit=10"), staleTime: 300_000 });
  if (isLoading) return <div className="animate-pulse h-48 rounded-lg" style={{ background: T.surface }} />;
  const investments = data?.investments ?? [];

  return (
    <div className="space-y-2">
      {investments.map((inv: any, i: number) => (
        <div key={i} className="flex items-start gap-3 rounded border p-3"
          style={{ background: T.elevated, borderColor: T.border }}>
          <div className="flex-1 min-w-0">
            <div style={{ color: T.textPrimary }} className="text-sm font-semibold leading-tight">{inv.recipient}</div>
            <div className="mt-0.5 flex items-center gap-2">
              <span style={{ color: T.amber, background: `${T.amber}18`, border: `1px solid ${T.amber}40` }}
                className="rounded px-1.5 py-0.5 font-mono text-[9px] font-bold">
                {inv.investment_type}
              </span>
              <span style={{ color: T.textTertiary }} className="font-mono text-[9px]">{inv.announcement_date?.slice(0,4)}</span>
            </div>
            <div style={{ color: T.textTertiary }} className="mt-0.5 font-mono text-[9px]">
              {inv.investors?.slice(0,3).join(" · ")}
            </div>
          </div>
          {inv.amount_musd && <ValueChip value={inv.amount_musd} color={T.amber} />}
        </div>
      ))}
    </div>
  );
}

function EventsPanel() {
  const { data, isLoading } = useQuery({ queryKey: ["events"], queryFn: () => apiFetch("/events?limit=10"), staleTime: 300_000 });
  if (isLoading) return <div className="animate-pulse h-48 rounded-lg" style={{ background: T.surface }} />;
  const events = data?.events ?? [];

  const importanceColor = { critical: "#ef4444", major: T.indigo, minor: T.textTertiary };

  return (
    <div className="space-y-2">
      {events.map((ev: any, i: number) => (
        <div key={i} className="flex gap-3 rounded border p-3"
          style={{ background: T.elevated, borderColor: T.border }}>
          <div style={{ background: importanceColor[ev.importance] ?? T.textTertiary }}
            className="mt-1 h-2 w-2 shrink-0 rounded-full" />
          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between gap-2">
              <div style={{ color: T.textPrimary }} className="text-sm font-semibold leading-tight">{ev.display_name}</div>
              <span style={{ color: T.textData }} className="shrink-0 font-mono text-[10px]">{ev.date?.slice(0,4)}</span>
            </div>
            <span style={{ color: T.textTertiary, background: T.surface, border: `1px solid ${T.border}` }}
              className="mt-1 inline-block rounded px-1.5 py-0.5 font-mono text-[8px]">
              {ev.era?.replace(/_/g, " ")}
            </span>
            {ev.description && (
              <p style={{ color: T.textTertiary }} className="mt-1 text-[10px] leading-relaxed line-clamp-2">{ev.description}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function IncidentsPanel() {
  const { data, isLoading } = useQuery({ queryKey: ["incidents"], queryFn: () => apiFetch("/incidents"), staleTime: 300_000 });
  if (isLoading) return <div className="animate-pulse h-48 rounded-lg" style={{ background: T.surface }} />;
  const incidents = data?.incidents ?? [];

  return (
    <div className="space-y-2">
      {incidents.map((inc: any, i: number) => (
        <div key={i} className="rounded border p-3" style={{ background: T.elevated, borderColor: T.border }}>
          <div className="flex items-start justify-between gap-2">
            <div style={{ color: T.textPrimary }} className="text-sm font-semibold leading-tight">{inc.display_name}</div>
            <span style={{ color: "#ef4444", background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.3)" }}
              className="shrink-0 rounded px-1.5 py-0.5 font-mono text-[9px] uppercase">{inc.severity}</span>
          </div>
          {inc.root_cause && (
            <div style={{ color: T.amber }} className="mt-1.5 font-mono text-[10px]">
              ⚠ Root cause: {inc.root_cause}
            </div>
          )}
          {inc.financial_loss_musd && (
            <div style={{ color: T.textTertiary }} className="mt-0.5 font-mono text-[9px]">
              Loss: ${inc.financial_loss_musd}M
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function PapersPanel() {
  const { data, isLoading } = useQuery({ queryKey: ["papers"], queryFn: () => apiFetch("/papers"), staleTime: 300_000 });
  if (isLoading) return <div className="animate-pulse h-48 rounded-lg" style={{ background: T.surface }} />;
  const papers = data?.papers ?? [];

  return (
    <div className="space-y-2">
      {papers.map((p: any, i: number) => (
        <div key={i} className="rounded border p-3" style={{ background: T.elevated, borderColor: T.border }}>
          <div className="flex items-start justify-between gap-2">
            <div style={{ color: T.textPrimary }} className="text-sm font-semibold leading-tight">{p.display_name}</div>
            <span style={{ color: T.purple }} className="shrink-0 font-mono text-[10px] font-bold">{p.citations?.toLocaleString()} cit.</span>
          </div>
          <div style={{ color: T.textTertiary }} className="mt-0.5 font-mono text-[9px]">
            {p.authors?.slice(0,2).join(", ")}{p.authors?.length > 2 ? " et al." : ""} · {p.published_year}
          </div>
          {p.doi && (
            <a href={`https://doi.org/${p.doi}`} target="_blank" rel="noopener noreferrer"
              style={{ color: T.indigo }} className="font-mono text-[9px] hover:underline">
              DOI: {p.doi}
            </a>
          )}
        </div>
      ))}
    </div>
  );
}

function StandardsPanel() {
  const { data, isLoading } = useQuery({ queryKey: ["standards"], queryFn: () => apiFetch("/standards"), staleTime: 300_000 });
  if (isLoading) return <div className="animate-pulse h-48 rounded-lg" style={{ background: T.surface }} />;
  const standards = data?.standards ?? [];

  return (
    <div className="space-y-2">
      {standards.map((s: any, i: number) => (
        <div key={i} className="rounded border p-3" style={{ background: T.elevated, borderColor: T.border }}>
          <div className="flex items-start gap-2">
            <span style={{ color: T.amber, background: `${T.amber}18`, border: `1px solid ${T.amber}40` }}
              className="shrink-0 rounded px-1.5 py-0.5 font-mono text-[9px] font-bold">
              {s.issuing_body}
            </span>
            <div style={{ color: T.textPrimary }} className="text-sm font-semibold leading-tight">{s.display_name}</div>
          </div>
          {s.description && <p style={{ color: T.textTertiary }} className="mt-1 text-[10px] leading-relaxed line-clamp-2">{s.description}</p>}
        </div>
      ))}
    </div>
  );
}

// ─── TAB NAVIGATION ───────────────────────────────────────────────────────────

const TABS = [
  { key: "aku",       label: "◈ AKU Status",      icon: "🌌" },
  { key: "contracts", label: "📝 Contracts",        icon: "📝" },
  { key: "invest",    label: "💰 Investments",      icon: "💰" },
  { key: "events",    label: "📅 Historical Events", icon: "📅" },
  { key: "incidents", label: "⚠ Incidents",         icon: "⚠" },
  { key: "papers",    label: "📄 Research Papers",   icon: "📄" },
  { key: "standards", label: "📏 Standards",         icon: "📏" },
];

export default function IntelligenceHubPage() {
  const [activeTab, setActiveTab] = useState("aku");

  return (
    <div className="flex h-full flex-col overflow-y-auto" style={{ background: "var(--color-space-midnight)" }}>
      {/* Header */}
      <div className="border-b px-6 py-4 shrink-0"
        style={{ background: T.navy, borderColor: T.border }}>
        <div className="flex items-center gap-2 mb-1">
          <span style={{ color: T.indigo }} className="font-mono text-sm">◈</span>
          <h1 style={{ color: T.textPrimary, fontFamily: "var(--font-display, inherit)" }}
            className="text-lg font-bold">Aerospace Knowledge Universe</h1>
          <span style={{ color: T.green, background: "rgba(52,211,153,0.1)", border: "1px solid rgba(52,211,153,0.3)" }}
            className="rounded px-2 py-0.5 font-mono text-[9px] font-bold">v1.0</span>
        </div>
        <p style={{ color: T.textTertiary }} className="text-xs">
          Business Intelligence · Historical Intelligence · Scientific Knowledge
        </p>

        {/* Tabs */}
        <div className="mt-3 flex gap-0 overflow-x-auto">
          {TABS.map(tab => {
            const active = activeTab === tab.key;
            return (
              <button key={tab.key} onClick={() => setActiveTab(tab.key)}
                style={{
                  color:        active ? T.indigo : T.textTertiary,
                  borderBottom: active ? `2px solid ${T.indigo}` : "2px solid transparent",
                  background:   active ? "rgba(99,102,241,0.06)" : "transparent",
                }}
                className="shrink-0 px-4 py-2 font-mono text-[10px] font-semibold uppercase tracking-wider transition-colors hover:text-indigo-400">
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-5">
        {activeTab === "aku"       && <AKUStatus />}
        {activeTab === "contracts" && (<><SectionHeader icon="📝" title="Aerospace Contracts" /><ContractsPanel /></>)}
        {activeTab === "invest"    && (<><SectionHeader icon="💰" title="Investment Rounds" /><InvestmentsPanel /></>)}
        {activeTab === "events"    && (<><SectionHeader icon="📅" title="Historical Events" /><EventsPanel /></>)}
        {activeTab === "incidents" && (<><SectionHeader icon="⚠" title="Incidents & Anomalies" /><IncidentsPanel /></>)}
        {activeTab === "papers"    && (<><SectionHeader icon="📄" title="Research Papers" /><PapersPanel /></>)}
        {activeTab === "standards" && (<><SectionHeader icon="📏" title="Standards & Specifications" /><StandardsPanel /></>)}
      </div>
    </div>
  );
}
