/**
 * ORBITIQ-X — API Client
 * =======================
 * Typed fetch wrappers for all Phase 13B backend endpoints.
 * All URLs match the verified router.py contracts.
 *
 * Base URL:  NEXT_PUBLIC_API_URL (default: http://localhost:8000)
 * API prefix: /api/v1
 */

const BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").split("/api/v1")[0].replace(/\/$/, "");
const V1   = `${BASE}/api/v1`;

// ─── Auth token store (set by AuthProvider) ─────────────────────────────────
// Module-level reference so apiFetch can attach it without React context.
// This is intentionally not localStorage — it's reset on page reload.

let _accessToken: string | null = null;

export function setApiAccessToken(token: string | null): void {
  _accessToken = token;
}

export function getApiAccessToken(): string | null {
  return _accessToken;
}

// ─── Fetch helper ─────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const authHeader: Record<string, string> = _accessToken
    ? { Authorization: `Bearer ${_accessToken}` }
    : {};

  const res = await fetch(`${V1}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...authHeader,
      ...(init?.headers ?? {}),
    },
    next: { revalidate: 0 },
    ...init,
  });

  if (res.status === 401) {
    // Trigger silent refresh via Next.js route handler
    const refreshed = await fetch("/api/auth/refresh", { method: "POST" });
    if (refreshed.ok) {
      const data = await refreshed.json();
      if (data.access_token) {
        _accessToken = data.access_token;
        // Retry the original request with the new token
        const retryRes = await fetch(`${V1}${path}`, {
          headers: {
            "Content-Type": "application/json",
            Authorization:  `Bearer ${_accessToken}`,
            ...(init?.headers ?? {}),
          },
          next: { revalidate: 0 },
          ...init,
        });
        if (retryRes.ok) return retryRes.json() as Promise<T>;
      }
    }
    // If refresh failed, redirect to login
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new Error("Session expired. Please log in again.");
  }

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


// ─── Orbit Forecast / Trajectory (verified vs OrbitForecastService + tests) ───
// Endpoint: GET /api/v1/digital-twin/forecast/{norad_id}?days=N&step_min=N
// Fields verified from: twin_services.py TrajectoryPoint constructor + test assertions

export interface TrajectoryPoint {
  epoch:           string;   // ISO 8601 UTC — "epoch" attribute on OrbitForecast
  position_eci_km: [number, number, number];
  altitude_km:     number;
  latitude_deg:    number;
  longitude_deg:   number;
}

export interface OrbitForecast {
  norad_id:          number;
  name:              string;
  generated_at:      string;   // ISO 8601
  horizon_days:      number;
  step_minutes:      number;
  trajectory:        TrajectoryPoint[];   // may be empty if TLE unavailable
  reentry_predicted: boolean;
  reentry_epoch:     string | null;       // ISO 8601 | null
  lifetime_days:     number | null;
  decay_rate_km_day: number | null;
}

export const fetchOrbitForecast = (
  noradId:  number,
  days      = 1.0,
  stepMin   = 5,
): Promise<OrbitForecast> =>
  apiFetch<OrbitForecast>(
    `/digital-twin/forecast/${noradId}?days=${days}&step_min=${stepMin}`,
  );

// Endpoint: GET /api/v1/digital-twin/conjunctions/future?min_pc=N&limit=N
export interface FutureConjunction {
  conjunctionId:   string;
  primaryNorad:    number;
  secondaryNorad:  number;
  forecastEpoch:   string;    // ISO 8601
  missDistanceKm:  number;
  estimatedPc:     number;
  riskLevel:       string;
  confidence:      number;
  generatedAt:     string;
}

export const fetchFutureConjunctions = (
  minPc = 1e-6,
  limit = 50,
): Promise<{ count: number; events: FutureConjunction[] }> =>
  apiFetch(`/digital-twin/conjunctions/future?min_pc=${minPc}&limit=${limit}`);


// ─── Platform Observability API (Phase 14B) ────────────────────────────────
// GET /api/v1/platform/health
export interface ServiceHealth {
  status:       string;   // healthy | degraded | unavailable | unhealthy | error | unknown
  latency_ms?:  number;
  error?:       string;
  [key: string]: unknown;
}
export interface PlatformHealth {
  overall:     string;
  checked_at:  string;
  elapsed_ms:  number;
  services: {
    postgres:          ServiceHealth;
    redis:             ServiceHealth;
    neo4j:             ServiceHealth;
    vector_store:      ServiceHealth;
    minio:             ServiceHealth;
    digital_twin:      ServiceHealth;
    conjunction_engine:ServiceHealth;
    agents:            ServiceHealth;
    graphrag:          ServiceHealth;
    scheduler:         ServiceHealth;
  };
}
export const fetchPlatformHealth = (): Promise<PlatformHealth> =>
  apiFetch<PlatformHealth>("/platform/health");

// GET /api/v1/platform/status
export interface PlatformStatus {
  checked_at:  string;
  scheduler: {
    status:    string;
    job_count: number;
    jobs:      Array<{ id: string; name: string; next_run_utc: string | null }>;
  };
  catalog: {
    status?:         string;
    last_sync?:      string;
    satellites?:     number;
    sync_mode?:      string;
    failure_reason?: string;
    error?:          string;
  };
  digital_twin: {
    objects_propagated?:  number;
    last_propagation?:    string;
    propagation_seconds?: number;
    live_objects?:        number;
    error?:               string;
  };
}
export const fetchPlatformStatus = (): Promise<PlatformStatus> =>
  apiFetch<PlatformStatus>("/platform/status");

// ─── Satellite Catalog List ───────────────────────────────────────────────────
// Endpoint: GET /api/v1/catalog/satellites
// Returns paginated satellite list from PostgreSQL (all 29,198 objects)

export interface CatalogSatellite {
  norad_id:        number;
  name:            string;
  object_type:     string;   // PAYLOAD | ROCKET_BODY | DEBRIS | UNKNOWN
  regime:          string;   // LEO | MEO | GEO | HEO | SSO | VLEO | UNKNOWN
  inclination_deg: number | null;
  perigee_km:      number | null;
  apogee_km:       number | null;
  period_minutes:  number | null;
  country_code:    string | null;
}

export interface CatalogSatelliteResponse {
  total:   number;
  page:    number;
  limit:   number;
  objects: CatalogSatellite[];
}

export const fetchSatelliteList = (params: {
  regime?: string;
  type?:   string;
  search?: string;
  page?:   number;
  limit?:  number;
}): Promise<CatalogSatelliteResponse> => {
  const q = new URLSearchParams();
  if (params.regime && params.regime !== "ALL") q.set("regime", params.regime);
  if (params.type   && params.type   !== "ALL") q.set("type",   params.type);
  if (params.search) q.set("search", params.search);
  if (params.page  !== undefined) q.set("page",  String(params.page));
  if (params.limit !== undefined) q.set("limit", String(params.limit));
  return apiFetch<CatalogSatelliteResponse>(`/catalog/satellites?${q.toString()}`);
};
