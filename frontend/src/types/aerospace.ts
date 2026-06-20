/**
 * ORBITIQ-X — Core Domain Type Definitions
 * =========================================
 * Aerospace-domain TypeScript types matching the backend Pydantic schemas.
 * All types are readonly to prevent accidental mutation of orbital data.
 */

// ─── Orbital Mechanics ────────────────────────────────────────────────────────

export type OrbitalRegime = "LEO" | "VLEO" | "MEO" | "GEO" | "HEO" | "SSO" | "UNKNOWN";

export type ObjectType = "PAYLOAD" | "ROCKET_BODY" | "DEBRIS" | "UNKNOWN";

export interface TwoLineElement {
  readonly line0: string;       // Name line (optional)
  readonly line1: string;       // TLE line 1
  readonly line2: string;       // TLE line 2
  readonly epoch: string;       // ISO 8601 epoch derived from TLE
  readonly noradId: number;
  readonly intlDesignator: string;
  readonly meanMotion: number;          // rev/day
  readonly eccentricity: number;        // dimensionless [0, 1)
  readonly inclination: number;         // degrees [0, 180]
  readonly raan: number;                // Right Ascension of Ascending Node [deg]
  readonly argOfPerigee: number;        // degrees
  readonly meanAnomaly: number;         // degrees
  readonly bstar: number;               // BSTAR drag term
}

export interface StateVector {
  readonly epoch: string;             // ISO 8601 UTC
  readonly noradId: number;
  readonly positionEciKm: [number, number, number];    // [x, y, z] km
  readonly velocityEciKmS: [number, number, number];   // [vx, vy, vz] km/s
  readonly altitudeKm: number;
  readonly latitudeDeg: number;
  readonly longitudeDeg: number;
  readonly speedKmS: number;
  readonly errorCode: number;
}

export interface GroundTrackPoint {
  readonly epoch: string;
  readonly latitudeDeg: number;
  readonly longitudeDeg: number;
  readonly altitudeKm: number;
}

// ─── Resident Space Objects ───────────────────────────────────────────────────

export type RadarCrossSection = "SMALL" | "MEDIUM" | "LARGE" | "UNKNOWN";

export interface ResidentSpaceObject {
  readonly noradId: number;
  readonly satName: string;
  readonly intlDesignator: string;
  readonly objectType: ObjectType;
  readonly orbitClass: OrbitalRegime;
  readonly launchEpoch: string | null;
  readonly launchSite: string | null;
  readonly countryCode: string | null;
  readonly operatorName: string | null;
  readonly perigeeKm: number | null;
  readonly apogeeKm: number | null;
  readonly inclinationDeg: number | null;
  readonly periodMin: number | null;
  readonly rcs: RadarCrossSection;
  readonly tle: TwoLineElement | null;
  readonly currentState: StateVector | null;
  readonly isActive: boolean;
  readonly isDebris: boolean;
}

// ─── Conjunction Analysis ─────────────────────────────────────────────────────

export type ConjunctionRiskLevel = "WATCH" | "WARNING" | "RED";

export interface ConjunctionDataMessage {
  readonly cdmId: string;               // Unique CDM identifier
  readonly createdAt: string;           // ISO 8601 creation timestamp
  readonly tca: string;                 // Time of Closest Approach (ISO 8601 UTC)
  readonly missDistanceKm: number;      // Minimum miss distance [km]
  readonly probabilityOfCollision: number;   // Pc in [0, 1]
  readonly riskLevel: ConjunctionRiskLevel;
  readonly object1: {
    readonly noradId: number;
    readonly satName: string;
    readonly objectType: ObjectType;
    readonly operatorName: string | null;
  };
  readonly object2: {
    readonly noradId: number;
    readonly satName: string;
    readonly objectType: ObjectType;
    readonly operatorName: string | null;
  };
  readonly relativePositionRtnKm: [number, number, number]; // [radial, transverse, normal]
  readonly relativeVelocityRtnKmS: [number, number, number];
  readonly combinedCovarianceMatrix: number[][];   // 3x3 in RTN frame [km²]
  readonly isManeuverRecommended: boolean;
  readonly maneuverWindowStart: string | null;
  readonly maneuverWindowEnd: string | null;
}

// ─── Space Weather ────────────────────────────────────────────────────────────

export type GemagneticStormLevel = "NONE" | "G1" | "G2" | "G3" | "G4" | "G5";
export type SolarRadiationStormLevel = "NONE" | "S1" | "S2" | "S3" | "S4" | "S5";
export type RadioBlackoutLevel = "NONE" | "R1" | "R2" | "R3" | "R4" | "R5";

export interface SpaceWeatherSnapshot {
  readonly timestamp: string;
  readonly kpIndex: number;             // 0-9 planetary geomagnetic index
  readonly f107SolarFlux: number;       // Solar flux index [sfu]
  readonly apIndex: number;             // Daily geomagnetic Ap index
  readonly sunspotNumber: number;
  readonly geomagneticStorm: GemagneticStormLevel;
  readonly solarRadiationStorm: SolarRadiationStormLevel;
  readonly radioBlackout: RadioBlackoutLevel;
  readonly atmosphericDensityScaleFactor: number;   // Relative to NRLMSISE-00 standard
}

// ─── Knowledge Graph ──────────────────────────────────────────────────────────

export type KGEntityType =
  | "Satellite"
  | "LaunchVehicle"
  | "Operator"
  | "Orbit"
  | "Payload"
  | "GroundStation"
  | "Mission"
  | "Debris"
  | "Country"
  | "Maneuver";

export interface KGEntity {
  readonly id: string;
  readonly entityType: KGEntityType;
  readonly name: string;
  readonly properties: Record<string, string | number | boolean | null>;
  readonly sources: string[];
}

export interface KGRelationship {
  readonly id: string;
  readonly type: string;
  readonly sourceId: string;
  readonly targetId: string;
  readonly properties: Record<string, string | number | null>;
}

export interface KGNeighborhood {
  readonly entity: KGEntity;
  readonly relationships: KGRelationship[];
  readonly neighbors: KGEntity[];
}

// ─── Agent System ─────────────────────────────────────────────────────────────

export type AgentType =
  | "SSA_AGENT"
  | "MISSION_AGENT"
  | "CATALOG_AGENT"
  | "KNOWLEDGE_AGENT"
  | "ORCHESTRATOR";

export type TaskStatus =
  | "queued"
  | "running"
  | "waiting_human"
  | "completed"
  | "failed"
  | "cancelled";

export interface AgentToolCall {
  readonly toolName: string;
  readonly inputArgs: Record<string, unknown>;
  readonly outputSummary: string | null;
  readonly durationMs: number;
  readonly success: boolean;
}

export interface AgentReasoningStep {
  readonly stepNumber: number;
  readonly agentType: AgentType;
  readonly thought: string;
  readonly toolCalls: AgentToolCall[];
  readonly timestampMs: number;
}

export interface AgentTask {
  readonly taskId: string;
  readonly status: TaskStatus;
  readonly query: string;
  readonly taskType: string;
  readonly submittedAt: string;
  readonly completedAt: string | null;
  readonly answer: string | null;
  readonly citations: string[];
  readonly reasoningSteps: AgentReasoningStep[];
  readonly agentsInvolved: AgentType[];
  readonly errorMessage: string | null;
}

// ─── Mission Planning ─────────────────────────────────────────────────────────

export type ManeuverType =
  | "HOHMANN_TRANSFER"
  | "BI_ELLIPTIC_TRANSFER"
  | "PLANE_CHANGE"
  | "PHASING"
  | "DEORBIT"
  | "STATION_KEEPING"
  | "COLLISION_AVOIDANCE";

export interface ManeuverBurn {
  readonly burnId: string;
  readonly epoch: string;
  readonly deltaVKmS: [number, number, number];   // RTN delta-V components [km/s]
  readonly deltaNorm: number;                     // |ΔV| [km/s]
  readonly burnDurationS: number;
  readonly maneuverType: ManeuverType;
}

export interface TrajectoryOption {
  readonly optionId: string;
  readonly label: string;
  readonly description: string;
  readonly totalDeltaVKmS: number;
  readonly transferDurationHours: number;
  readonly burns: ManeuverBurn[];
  readonly finalOrbit: {
    readonly perigeeKm: number;
    readonly apogeeKm: number;
    readonly inclinationDeg: number;
  };
  readonly fuelMassKg: number | null;
  readonly feasibility: "NOMINAL" | "MARGINAL" | "INFEASIBLE";
}

// ─── UI / API Utility Types ───────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  readonly data: T[];
  readonly total: number;
  readonly page: number;
  readonly pageSize: number;
  readonly hasNext: boolean;
}

export interface ApiError {
  readonly status: number;
  readonly detail: string;
  readonly requestId: string;
}
