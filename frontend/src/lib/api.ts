/**
 * ORBITIQ-X — API Client
 * =======================
 * Typed fetch wrappers for all Phase 13B backend endpoints.
 * All URLs match the verified router.py contracts.
 *
 * Base URL:  NEXT_PUBLIC_API_URL (default: http://localhost:8000)
 * API prefix: /api/v1
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const V1   = `${BASE}/api/v1`;

// ─── Fetch helper ─────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${V1}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    next:    { revalidate: 0 },   // Always fresh for dashboard data
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status} — ${path}: ${text.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

// ─── SSA Statistics (DashboardMetricsBar) ─────────────────────────────────────
// Endpoint: GET /api/v1/ssa/statistics
// Source:   ssa_conjunctions.py → get_ssa_statistics()

export interface SSAStatistics {
  total_events:            number;
  unresolved_total:        number;
  by_risk:                 Record<string, number>;
  maneuver_required_count: number;
  avg_miss_distance_km:    number | null;
  max_pc:                  number | null;
  screening_coverage:      string;
  graph_conjunctions:      number;
  risk_thresholds:         Record<string, string>;
  pc_method:               string;
  ccsds_standard:          string;
}

export const fetchSSAStatistics = (): Promise<SSAStatistics> =>
  apiFetch<SSAStatistics>("/ssa/statistics");


// ─── Catalog Health (CatalogStatsCard + MissionStatusCard) ───────────────────
// Endpoint: GET /api/v1/catalog/health
// Source:   catalog.py → get_catalog_health()

export interface CatalogHealth {
  overall:                    "healthy" | "degraded" | "unhealthy";
  spacetrack_reachable:       boolean;
  spacetrack_authenticated:   boolean;
  spacetrack_latency_ms:      number;
  database_ok:                boolean;
  database_satellite_count:   number;
  last_sync_status:           string | null;
  last_sync_age_minutes:      number | null;
  checked_at:                 string;
  warnings:                   string[];
}

export const fetchCatalogHealth = (): Promise<CatalogHealth> =>
  apiFetch<CatalogHealth>("/catalog/health");


// ─── Catalog Status (CatalogStatsCard) ───────────────────────────────────────
// Endpoint: GET /api/v1/catalog/status
// Source:   catalog.py → get_catalog_status()

export interface CatalogStatus {
  sync_id:              string | null;
  status:               string;
  sync_mode:            string | null;
  started_at:           string | null;
  completed_at:         string | null;
  duration_seconds:     number | null;
  downloaded_records:   number;
  total_parsed:         number;
  inserted:             number;
  duplicates:           number;
  satellites_updated:   number;
  parse_errors:         number;
  stale_satellite_count:number;
  failure_reason:       string | null;
  phases_completed:     string[];
}

export const fetchCatalogStatus = (): Promise<CatalogStatus> =>
  apiFetch<CatalogStatus>("/catalog/status");


// ─── Space Weather (SpaceWeatherWidget) ───────────────────────────────────────
// Endpoint: GET /api/v1/digital-twin/weather
// Source:   digital_twin.py → get_space_weather()

export interface SpaceWeatherData {
  timestamp:                      string;
  kp_index:                       number;
  f107_solar_flux:                number;
  ap_index:                       number;
  sunspot_number:                 number;
  geomagnetic_storm:              "NONE" | "G1" | "G2" | "G3" | "G4" | "G5";
  solar_radiation_storm:          "NONE" | "S1" | "S2" | "S3" | "S4" | "S5";
  radio_blackout:                 "NONE" | "R1" | "R2" | "R3" | "R4" | "R5";
  atmospheric_density_scale_factor: number;
  // Backend may also return these as flat fields
  source?:                        string;
  next_update?:                   string;
}

export const fetchSpaceWeather = (): Promise<SpaceWeatherData> =>
  apiFetch<SpaceWeatherData>("/digital-twin/weather");


// ─── High-Risk Conjunctions (ConjunctionAlertPanel) ──────────────────────────
// Endpoint: GET /api/v1/ssa/conjunctions/high-risk?limit=20
// Source:   ssa_conjunctions.py → get_high_risk_conjunctions()

export interface ConjunctionItem {
  id:                          number;
  conjunction_id:              string;
  primary:                     { norad: number; name: string; type: string };
  secondary:                   { norad: number; name: string; type: string };
  tca:                         string | null;
  miss_distance_km:            number;
  relative_velocity_kms:       number;
  collision_probability:       number;
  risk_level:                  "red" | "yellow" | "green" | "white";
  maneuver_required:           boolean;
  maneuver_window_close:       string | null;
  maneuver_window_hours_remaining: number | null;
  maneuver_urgency:            "CRITICAL" | "HIGH" | "ELEVATED" | "MONITOR";
  recommended_dv_kms:          number | null;
  resolved:                    boolean;
  created_at:                  string | null;
}

export interface HighRiskConjunctionsResponse {
  count: number;
  items: ConjunctionItem[];
  note:  string;
}

export const fetchHighRiskConjunctions = (limit = 20): Promise<HighRiskConjunctionsResponse> =>
  apiFetch<HighRiskConjunctionsResponse>(`/ssa/conjunctions/high-risk?limit=${limit}`);


// ─── Agent Tasks (AgentActivityFeed) ──────────────────────────────────────────
// Endpoint: GET /api/v1/agents/tasks?limit=10
// Source:   agents.py → list_recent_tasks()

export interface AgentTaskStatus {
  task_id:          string;
  status:           "queued" | "running" | "waiting_human" | "completed" | "failed" | "cancelled";
  query:            string;
  task_type:        string;
  submitted_at:     string;
  completed_at:     string | null;
  agents_invoked:   string[];
  latency_ms:       number | null;
  error_message:    string | null;
  query_intent?:    string;
  confidence?:      number;
}

export const fetchAgentTasks = (limit = 10): Promise<AgentTaskStatus[]> =>
  apiFetch<AgentTaskStatus[]>(`/agents/tasks?limit=${limit}`);


// ─── SSE — Conjunction Alert Stream ──────────────────────────────────────────
// Endpoint: GET /api/v1/ssa/alerts/stream  (Phase 13B SSE bridge)
// Returns:  text/event-stream — Redis pub/sub conjunction alerts

export const CONJUNCTION_SSE_URL = `${V1}/ssa/alerts/stream`;


// ─── Cesium Globe States (OrbitalGlobe) ───────────────────────────────────────
// Endpoint: GET /api/v1/digital-twin/cesium/states?limit=10000
// Source:   digital_twin.py → get_cesium_states()
// Verified response shape from actual endpoint code.

export interface CesiumSatObject {
  id:       number;       // NORAD catalog number
  name:     string;
  type:     string;       // "PAYLOAD" | "ROCKET_BODY" | "DEBRIS" | "UNKNOWN"
  regime:   string;       // "LEO" | "MEO" | "GEO" | "SSO" | "VLEO" | "HEO" | "UNKNOWN"
  lat:      number;       // geodetic latitude [deg]
  lon:      number;       // geodetic longitude [deg]
  alt_km:   number;       // altitude above WGS-84 ellipsoid [km]
  speed:    number;       // orbital speed [km/s]
  pos_eci:  [number, number, number];  // ECI J2000 [km]
}

export interface CesiumStatesResponse {
  epoch:          string | null;
  count:          number;
  regime_filter:  string | null;
  objects:        CesiumSatObject[];
  cesium_note:    string;
  refresh_ms:     number;
}

export const fetchCesiumStates = (limit = 10000): Promise<CesiumStatesResponse> =>
  apiFetch<CesiumStatesResponse>(`/digital-twin/cesium/states?limit=${limit}`);


// ─── Satellite Detail State (OrbitalGlobe selection panel) ───────────────────
// Endpoint: GET /api/v1/digital-twin/state/{norad_id}
// Source:   digital_twin.py → get_satellite_state() → SatelliteState.to_dict()
// Verified fields from test_digital_twin.py test_state_to_dict_has_required_fields

export interface SatelliteDetailState {
  norad_id:         number;
  name:             string;
  epoch:            string;
  altitude_km:      number;
  latitude_deg:     number;
  longitude_deg:    number;
  speed_kms:        number;
  orbital_regime:   string;
  position_eci_km:  [number, number, number];
  velocity_eci_kms: [number, number, number];
  inclination_deg:  number;
  perigee_km:       number;
  apogee_km:        number;
  period_min:       number;
  propagation_ok:   boolean;
  object_type?:     string;
  error_code?:      number;
}

export const fetchSatelliteDetail = (noradId: number): Promise<SatelliteDetailState> =>
  apiFetch<SatelliteDetailState>(`/digital-twin/state/${noradId}`);


// ─── Knowledge Graph API types (verified against graph_analytics_service.py) ──
// All field names match exact Cypher RETURN aliases.

// GET /api/v1/knowledge-graph/analytics/summary
export interface GraphSummary {
  available:   boolean;
  node_counts: Record<string, number>;
  rel_counts:  Record<string, number>;
  total_nodes: number;
  total_rels:  number;
  checked_at:  string;
}
export const fetchGraphSummary = (): Promise<GraphSummary> =>
  apiFetch<GraphSummary>("/knowledge-graph/analytics/summary");

// GET /api/v1/knowledge-graph/analytics/operators?limit=N
export interface GraphOperator {
  operator:       string;
  satelliteCount: number;
  regimes:        string[];
  countryCode:    string | null;
}
export const fetchGraphOperators = (limit = 30): Promise<{ count: number; operators: GraphOperator[] }> =>
  apiFetch(`/knowledge-graph/analytics/operators?limit=${limit}`);

// GET /api/v1/knowledge-graph/analytics/risk-operators?limit=N
export interface RiskOperator {
  operator:   string;
  unresolved: number;
  maxPc:      number;
  redEvents:  number;
}
export const fetchRiskOperators = (limit = 15): Promise<{ count: number; operators: RiskOperator[] }> =>
  apiFetch(`/knowledge-graph/analytics/risk-operators?limit=${limit}`);

// GET /api/v1/knowledge-graph/analytics/countries?limit=N
export interface GraphCountry {
  countryCode:      string;
  countryName:      string;
  activeSatellites: number;
  regimes:          string[];
}
export const fetchGraphCountries = (limit = 20): Promise<{ count: number; countries: GraphCountry[] }> =>
  apiFetch(`/knowledge-graph/analytics/countries?limit=${limit}`);

// GET /api/v1/knowledge-graph/analytics/conjunctions?min_pc=N&limit=N
// Returns graph-JSON directly consumable by vis-network
export interface GraphNetworkNode {
  id:        string;   // NORAD id as string
  label:     string;
  type:      string;   // "Satellite"
  riskLevel: string;   // "red" | "yellow" | "green"
}
export interface GraphNetworkEdge {
  source:        string;
  target:        string;
  conjunctionId: string;
  Pc:            number;
  missKm:        number;
  riskLevel:     string;
  resolved:      boolean;
}
export interface ConjunctionNetwork {
  nodes: GraphNetworkNode[];
  edges: GraphNetworkEdge[];
  meta:  { minPc: number; nodeCount: number; edgeCount: number; format: string };
}
export const fetchConjunctionNetwork = (minPc = 1e-5, limit = 300): Promise<ConjunctionNetwork> =>
  apiFetch<ConjunctionNetwork>(`/knowledge-graph/analytics/conjunctions?min_pc=${minPc}&limit=${limit}`);

// GET /api/v1/knowledge-graph/analytics/regimes
export interface RegimeDensity {
  regimeId:    string;
  regime:      string;
  altMinKm:    number | null;
  altMaxKm:    number | null;
  totalObjects:number;
  satellites:  number;
  debris:      number;
  rocketBodies:number;
}
export const fetchRegimeDensity = (): Promise<{ regimes: RegimeDensity[] }> =>
  apiFetch("/knowledge-graph/analytics/regimes");

// GET /api/v1/knowledge-graph/analytics/constellations?limit=N
export interface GraphConstellation {
  constellation: string;
  memberCount:   number;
  primaryRegime: string | null;
  operator:      string | null;
}
export const fetchConstellations = (limit = 15): Promise<{ count: number; constellations: GraphConstellation[] }> =>
  apiFetch(`/knowledge-graph/analytics/constellations?limit=${limit}`);

// GET /api/v1/knowledge-graph/search?q=&limit=N
export interface GraphSearchResult {
  query:   string;
  count:   number;
  results: Record<string, unknown>[];
}
export const fetchGraphSearch = (q: string, limit = 20): Promise<GraphSearchResult> =>
  apiFetch(`/knowledge-graph/search?q=${encodeURIComponent(q)}&limit=${limit}`);

// GET /api/v1/knowledge-graph/satellite/{norad_id}
export const fetchSatelliteSubgraph = (noradId: number): Promise<Record<string, unknown>> =>
  apiFetch(`/knowledge-graph/satellite/${noradId}`);
