/**
 * ORBITIQ-X — CAEM API Client
 * Phase 17.5 — updated Phase 19
 *
 * Uses relative /api/v2 URLs so Vercel rewrites handle proxying to Railway.
 * Never hard-code the Railway URL — let vercel.json rewrites do it.
 */

import { getApiAccessToken } from "@/lib/api";

const V2 = "/api/v2";

async function caemFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getApiAccessToken();

  const res = await fetch(`${V2}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!res.ok) throw new Error(`CAEM API ${res.status}: ${path}`);
  return res.json();
}

// ─── Entity types ─────────────────────────────────────────────────────────────

export interface EntitySummary {
  aqid: string;
  entity_class: string;
  entity_subclass?: string;
  display_name: string;
  short_name?: string;
  description?: string;
  lifecycle_status: string;
  confidence_score: number;
  tags: string[];
  domains: string[];
  regions: string[];
  updated_at: string;
  ai_executive_summary?: string;
}

export interface EntityFull extends EntitySummary {
  long_description?: string;
  aliases: string[];
  founded_or_created?: string;
  operational_start?: string;
  operational_end?: string;
  timeline_events: TimelineEvent[];
  related_aqids: string[];
  qdrant_chunk_ids: string[];
  ai_key_facts: KeyFact[];
  ai_generated_at?: string;
  verification_status: string;
  all_sources: ProvenanceRecord[];
  primary_provenance?: ProvenanceRecord;
  current_version: string;
  extension_data: Record<string, unknown>;
}

export interface TimelineEvent {
  event_id: string;
  label: string;
  description?: string;
  date?: string;
  date_precision: string;
  importance: "critical" | "major" | "minor";
  linked_aqids: string[];
}

export interface KeyFact {
  label: string;
  value: string;
  unit?: string;
}

export interface ProvenanceRecord {
  source_url?: string;
  source_name?: string;
  source_type: string;
  publisher?: string;
  confidence: number;
  verification_status: string;
  citation_text?: string;
}

export interface RelationshipEntry {
  rel_id: string;
  source_aqid: string;
  target_aqid: string;
  relationship_type: string;
  category?: string;
  since?: string;
  until?: string;
  is_current: boolean;
  is_primary: boolean;
  confidence: number;
  provenance_url?: string;
  properties: Record<string, unknown>;
}

export interface NeighborhoodGraph {
  center_aqid: string;
  depth: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GraphNode {
  aqid: string;
  display_name: string;
  entity_class: string;
  confidence: number;
}

export interface GraphEdge {
  rel_id?: string;
  source: string;
  target: string;
  type: string;
  confidence?: number;
}

// ─── API Methods ──────────────────────────────────────────────────────────────

export const caemApi = {
  listEntities: (params: {
    entity_class?: string;
    domain?: string;
    region?: string;
    min_confidence?: number;
    page?: number;
    page_size?: number;
  } = {}) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) qs.set(k, String(v));
    });
    return caemFetch<{ entities: EntitySummary[]; total: number; page: number; page_size: number }>(
      `/entities?${qs}`
    );
  },

  getEntity: (aqid: string) =>
    caemFetch<EntityFull>(`/entities/${encodeURIComponent(aqid)}`),

  getRelationships: (aqid: string, params?: {
    direction?: string;
    category?: string;
    is_current?: boolean;
  }) => {
    const qs = new URLSearchParams(params as Record<string, string> ?? {});
    return caemFetch<RelationshipEntry[]>(
      `/entities/${encodeURIComponent(aqid)}/relationships?${qs}`
    );
  },

  getNeighborhood: (aqid: string, depth = 2) =>
    caemFetch<NeighborhoodGraph>(
      `/entities/${encodeURIComponent(aqid)}/neighborhood?depth=${depth}`
    ),

  searchEntities: (q: string, entity_class?: string) => {
    const qs = new URLSearchParams({ q });
    if (entity_class) qs.set("entity_class", entity_class);
    return caemFetch<{ results: EntitySummary[]; count: number }>(
      `/entities/search/fulltext?${qs}`
    );
  },

  refreshSummary: (aqid: string) =>
    caemFetch(`/entities/${encodeURIComponent(aqid)}/refresh-summary`, { method: "POST" }),

  getOntology: (category?: string) => {
    const qs = category ? `?category=${category}` : "";
    return caemFetch<unknown[]>(`/relationships/ontology${qs}`);
  },

  getEntityFacts: (aqid: string) =>
    caemFetch(`/provenance/${encodeURIComponent(aqid)}/facts`),

  getSnapshots: (aqid: string) =>
    caemFetch(`/provenance/${encodeURIComponent(aqid)}/snapshots`),

  seedFlagshipEntities: () =>
    caemFetch<{
      inserted_count: number;
      skipped_count:  number;
      failed_count:   number;
      inserted:       string[];
      skipped:        string[];
      failed:         { name: string; error: string }[];
    }>(`/entities/seed-flagship`, { method: "POST" }),
};
