"use client";
/**
 * ORBITIQ-X — KnowledgeGraphExplorer
 * =====================================
 * Interactive Mission Control knowledge graph visualisation.
 *
 * This file is the SSR-safe shell.
 * vis-network is imperative / DOM-based and requires the browser window.
 * The full implementation lives in KnowledgeGraphInner.tsx, loaded via
 * next/dynamic with ssr:false so Next.js never attempts to render Vis on
 * the server.
 *
 * Views
 * ──────
 *   "conjunction"  — satellite conjunction risk network (graph-JSON from API)
 *   "operator"     — operator intelligence + fleet stats panel
 *   "regime"       — orbital regime density breakdown
 *   "constellation"— constellation ranking
 *
 * Data sources (all verified against actual API contracts)
 * ─────────────────────────────────────────────────────────
 *   /knowledge-graph/analytics/summary       — node/rel counts
 *   /knowledge-graph/analytics/conjunctions  — graph-JSON network
 *   /knowledge-graph/analytics/operators     — fleet stats
 *   /knowledge-graph/analytics/risk-operators— risk ranking
 *   /knowledge-graph/analytics/countries     — country breakdown
 *   /knowledge-graph/analytics/regimes       — orbital density
 *   /knowledge-graph/analytics/constellations— largest constellations
 *   /knowledge-graph/search?q=               — node search
 *   /knowledge-graph/satellite/{id}          — subgraph detail
 */

import dynamic from "next/dynamic";

const KnowledgeGraphInner = dynamic(
  () =>
    import("./KnowledgeGraphInner").then((m) => ({
      default: m.KnowledgeGraphInner,
    })),
  {
    ssr:     false,
    loading: () => (
      <div className="flex h-full w-full items-center justify-center bg-space-midnight">
        <div className="text-center">
          <div className="mb-3 h-1 w-56 overflow-hidden rounded-full bg-space-surface mx-auto">
            <div className="h-full w-2/3 animate-pulse rounded-full bg-[var(--color-accent-indigo)]" />
          </div>
          <span className="section-label">LOADING KNOWLEDGE GRAPH</span>
        </div>
      </div>
    ),
  },
);

export function KnowledgeGraphExplorer() {
  return (
    <div className="relative h-full w-full overflow-hidden bg-space-midnight">
      <KnowledgeGraphInner />
    </div>
  );
}
