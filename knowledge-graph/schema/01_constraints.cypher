// ============================================================
// ORBITIQ-X Aerospace Knowledge Graph
// Neo4j Schema — Constraints & Indexes
// Designed for 10M+ nodes / 100M+ relationships
// ============================================================

// ── UNIQUENESS CONSTRAINTS (also create backing index) ──────

// Country
CREATE CONSTRAINT country_iso2 IF NOT EXISTS
  FOR (c:Country) REQUIRE c.iso2 IS UNIQUE;

// Organization
CREATE CONSTRAINT org_id IF NOT EXISTS
  FOR (o:Organization) REQUIRE o.orgId IS UNIQUE;

// Operator
CREATE CONSTRAINT operator_id IF NOT EXISTS
  FOR (op:Operator) REQUIRE op.operatorId IS UNIQUE;

// Satellite
CREATE CONSTRAINT satellite_norad IF NOT EXISTS
  FOR (s:Satellite) REQUIRE s.noradId IS UNIQUE;

CREATE CONSTRAINT satellite_cospar IF NOT EXISTS
  FOR (s:Satellite) REQUIRE s.cosparId IS UNIQUE;

// Constellation
CREATE CONSTRAINT constellation_id IF NOT EXISTS
  FOR (c:Constellation) REQUIRE c.constellationId IS UNIQUE;

// Mission
CREATE CONSTRAINT mission_id IF NOT EXISTS
  FOR (m:Mission) REQUIRE m.missionId IS UNIQUE;

// Orbit
CREATE CONSTRAINT orbit_id IF NOT EXISTS
  FOR (o:Orbit) REQUIRE o.orbitId IS UNIQUE;

// LaunchVehicle
CREATE CONSTRAINT lv_id IF NOT EXISTS
  FOR (lv:LaunchVehicle) REQUIRE lv.vehicleId IS UNIQUE;

// LaunchSite
CREATE CONSTRAINT ls_id IF NOT EXISTS
  FOR (ls:LaunchSite) REQUIRE ls.siteId IS UNIQUE;

// DebrisObject
CREATE CONSTRAINT debris_norad IF NOT EXISTS
  FOR (d:DebrisObject) REQUIRE d.noradId IS UNIQUE;

// ConjunctionEvent
CREATE CONSTRAINT conj_id IF NOT EXISTS
  FOR (ce:ConjunctionEvent) REQUIRE ce.conjunctionId IS UNIQUE;

// SpaceWeatherEvent
CREATE CONSTRAINT swe_id IF NOT EXISTS
  FOR (swe:SpaceWeatherEvent) REQUIRE swe.eventId IS UNIQUE;

// ResearchPaper
CREATE CONSTRAINT paper_doi IF NOT EXISTS
  FOR (p:ResearchPaper) REQUIRE p.doi IS UNIQUE;


// ── RANGE INDEXES (for range queries and sorting) ───────────

// Satellite
CREATE INDEX satellite_launch_date IF NOT EXISTS
  FOR (s:Satellite) ON (s.launchDate);

CREATE INDEX satellite_status IF NOT EXISTS
  FOR (s:Satellite) ON (s.status);

CREATE INDEX satellite_mass IF NOT EXISTS
  FOR (s:Satellite) ON (s.massKg);

// DebrisObject
CREATE INDEX debris_rcs IF NOT EXISTS
  FOR (d:DebrisObject) ON (d.radarCrossSection);

CREATE INDEX debris_perigee IF NOT EXISTS
  FOR (d:DebrisObject) ON (d.perigeeKm);

// ConjunctionEvent
CREATE INDEX conj_tca IF NOT EXISTS
  FOR (ce:ConjunctionEvent) ON (ce.tca);

CREATE INDEX conj_Pc IF NOT EXISTS
  FOR (ce:ConjunctionEvent) ON (ce.collisionProbability);

CREATE INDEX conj_miss_dist IF NOT EXISTS
  FOR (ce:ConjunctionEvent) ON (ce.missDistanceKm);

// SpaceWeatherEvent
CREATE INDEX swe_start IF NOT EXISTS
  FOR (swe:SpaceWeatherEvent) ON (swe.startTime);

CREATE INDEX swe_kp IF NOT EXISTS
  FOR (swe:SpaceWeatherEvent) ON (swe.kpIndex);

// Orbit
CREATE INDEX orbit_altitude IF NOT EXISTS
  FOR (o:Orbit) ON (o.altitudeKm);

CREATE INDEX orbit_inclination IF NOT EXISTS
  FOR (o:Orbit) ON (o.inclinationDeg);

// ResearchPaper
CREATE INDEX paper_year IF NOT EXISTS
  FOR (p:ResearchPaper) ON (p.publicationYear);


// ── FULL-TEXT INDEXES (for semantic search / GraphRAG) ──────

CREATE FULLTEXT INDEX satellite_fulltext IF NOT EXISTS
  FOR (s:Satellite) ON EACH [s.name, s.internationalDesignator, s.purpose];

CREATE FULLTEXT INDEX mission_fulltext IF NOT EXISTS
  FOR (m:Mission) ON EACH [m.name, m.description, m.objectives];

CREATE FULLTEXT INDEX paper_fulltext IF NOT EXISTS
  FOR (p:ResearchPaper) ON EACH [p.title, p.abstract, p.keywords];

CREATE FULLTEXT INDEX org_fulltext IF NOT EXISTS
  FOR (o:Organization) ON EACH [o.name, o.description, o.country];

CREATE FULLTEXT INDEX debris_fulltext IF NOT EXISTS
  FOR (d:DebrisObject) ON EACH [d.description, d.fragmentationEvent];


// ── COMPOSITE INDEXES (for multi-property queries) ──────────

CREATE INDEX sat_status_launch IF NOT EXISTS
  FOR (s:Satellite) ON (s.status, s.launchDate);

CREATE INDEX conj_tca_Pc IF NOT EXISTS
  FOR (ce:ConjunctionEvent) ON (ce.tca, ce.collisionProbability);

CREATE INDEX debris_orbit_rcs IF NOT EXISTS
  FOR (d:DebrisObject) ON (d.regime, d.radarCrossSection);


// ── VECTOR INDEX (for GraphRAG embedding lookup) ────────────
// Requires Neo4j 5.11+ with vector plugin

CREATE VECTOR INDEX satellite_embedding IF NOT EXISTS
  FOR (s:Satellite) ON s.embedding
  OPTIONS {
    indexConfig: {
      `vector.dimensions`: 1536,
      `vector.similarity_function`: 'cosine'
    }
  };

CREATE VECTOR INDEX paper_embedding IF NOT EXISTS
  FOR (p:ResearchPaper) ON p.embedding
  OPTIONS {
    indexConfig: {
      `vector.dimensions`: 1536,
      `vector.similarity_function`: 'cosine'
    }
  };

CREATE VECTOR INDEX mission_embedding IF NOT EXISTS
  FOR (m:Mission) ON m.embedding
  OPTIONS {
    indexConfig: {
      `vector.dimensions`: 1536,
      `vector.similarity_function`: 'cosine'
    }
  };
