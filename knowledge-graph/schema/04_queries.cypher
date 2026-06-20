// ============================================================
// ORBITIQ-X Aerospace Knowledge Graph
// Example Intelligence Queries
// ============================================================

// ──────────────────────────────────────────────────────────────
// Q1. All Indian Earth Observation satellites
// ──────────────────────────────────────────────────────────────
MATCH (c:Country {iso2: 'IN'})<-[:REGISTERED_IN]-(s:Satellite)
WHERE s.missionType = 'eo'
  AND s.status = 'operational'
RETURN s.name AS satellite,
       s.noradId AS noradId,
       s.altitudeKm AS altKm,
       s.launchDate AS launched,
       s.massKg AS massKg
ORDER BY s.launchDate DESC;


// ──────────────────────────────────────────────────────────────
// Q2. All satellites launched by PSLV (with launch details)
// ──────────────────────────────────────────────────────────────
MATCH (s:Satellite)-[lb:LAUNCHED_BY]->(lv:LaunchVehicle {vehicleId: 'LV-PSLV'})
OPTIONAL MATCH (s)-[:REGISTERED_IN]->(c:Country)
RETURN s.name AS satellite,
       s.noradId AS noradId,
       lb.launchDate AS launchDate,
       lb.launchMassKg AS massKg,
       c.name AS country,
       s.status AS status
ORDER BY lb.launchDate DESC;


// ──────────────────────────────────────────────────────────────
// Q3. All conjunction events involving Starlink satellites
// ──────────────────────────────────────────────────────────────
MATCH (const:Constellation {constellationId: 'CONST-STARLINK'})
MATCH (s:Satellite)-[:MEMBER_OF]->(const)
MATCH (s)-[:PRIMARY_IN|SECONDARY_IN]->(ce:ConjunctionEvent)
WHERE ce.collisionProbability > 1e-5
OPTIONAL MATCH (other:Satellite)-[:SECONDARY_IN]->(ce)
OPTIONAL MATCH (debris:DebrisObject)-[:SECONDARY_IN]->(ce)
RETURN s.name AS starlinkSat,
       ce.conjunctionId AS cdmId,
       ce.tca AS tca,
       ce.missDistanceKm AS missDistKm,
       ce.collisionProbability AS Pc,
       ce.riskLevel AS risk,
       coalesce(other.name, debris.description, 'Unknown') AS secondaryObject,
       ce.resolution AS resolution
ORDER BY ce.collisionProbability DESC
LIMIT 50;


// ──────────────────────────────────────────────────────────────
// Q4. Debris cloud from a specific fragmentation event
//     (e.g. Fengyun-1C 2007 ASAT)
// ──────────────────────────────────────────────────────────────
MATCH (d:DebrisObject {fragmentationEvent: 'FRAG-FY1C-2007'})
OPTIONAL MATCH (d)-[:OCCUPIES]->(o:Orbit)
RETURN d.noradId AS norad,
       d.objectType AS type,
       d.radarCrossSection AS rcsM2,
       d.regime AS regime,
       o.altitudeKm AS altKm,
       o.inclinationDeg AS incDeg,
       d.riskCategory AS risk,
       d.decayDate AS predictedReentry
ORDER BY d.radarCrossSection DESC;

// Count and distribution
MATCH (d:DebrisObject {fragmentationEvent: 'FRAG-FY1C-2007'})
WITH d.regime AS regime, count(*) AS count
RETURN regime, count
ORDER BY count DESC;


// ──────────────────────────────────────────────────────────────
// Q5. Full mission lineage: operator → satellite → launch vehicle
//     → launch site → orbit
// ──────────────────────────────────────────────────────────────
MATCH path = (op:Operator)-[:OPERATES]->(s:Satellite)-[:LAUNCHED_BY]->(lv:LaunchVehicle)
             -[:LAUNCHES_FROM]->(ls:LaunchSite)-[:LOCATED_IN]->(c:Country)
MATCH (s)-[:OCCUPIES]->(o:Orbit)
WHERE s.noradId = 42063  // CARTOSAT-3 example
RETURN s.name AS satellite,
       op.name AS operator,
       lv.name AS vehicle,
       ls.name AS site,
       c.name AS country,
       o.regime AS orbit,
       o.altitudeKm AS altKm,
       o.inclinationDeg AS inclination;


// ──────────────────────────────────────────────────────────────
// Q6. High-risk conjunction events in the next 72 hours
// ──────────────────────────────────────────────────────────────
WITH datetime() AS now,
     datetime() + duration('PT72H') AS cutoff
MATCH (ce:ConjunctionEvent)
WHERE ce.tca >= now
  AND ce.tca <= cutoff
  AND ce.collisionProbability >= 1e-4  // Yellow threshold
MATCH (primary)-[:PRIMARY_IN]->(ce)
MATCH (secondary)-[:SECONDARY_IN]->(ce)
RETURN ce.conjunctionId AS cdmId,
       ce.tca AS tca,
       ce.collisionProbability AS Pc,
       ce.missDistanceKm AS missDistKm,
       ce.riskLevel AS risk,
       labels(primary)[0] AS primaryType,
       coalesce(primary.name, primary.noradId) AS primaryObject,
       labels(secondary)[0] AS secondaryType,
       coalesce(secondary.name, secondary.description) AS secondaryObject,
       ce.maneuverWindow AS maneuverDeadline
ORDER BY ce.collisionProbability DESC;


// ──────────────────────────────────────────────────────────────
// Q7. Orbital density by shell — debris risk map
// ──────────────────────────────────────────────────────────────
MATCH (d:DebrisObject)-[:OCCUPIES]->(o:Orbit)
WITH round(o.altitudeKm / 50) * 50 AS altBand,
     count(d) AS debrisCount,
     avg(d.radarCrossSection) AS avgRcs
ORDER BY debrisCount DESC
RETURN altBand AS altBandKm,
       debrisCount,
       round(avgRcs * 1000) / 1000 AS avgRcsM2
LIMIT 20;


// ──────────────────────────────────────────────────────────────
// Q8. Space weather impact on active satellites
// ──────────────────────────────────────────────────────────────
MATCH (swe:SpaceWeatherEvent)-[af:AFFECTS]->(o:Orbit)<-[:OCCUPIES]-(s:Satellite)
WHERE swe.kpIndex >= 5.0
  AND s.status = 'operational'
  AND swe.startTime >= datetime() - duration('P30D')
RETURN swe.eventId AS stormId,
       swe.startTime AS stormStart,
       swe.kpIndex AS Kp,
       swe.category AS category,
       af.densityChangePct AS densityChangePct,
       count(s) AS affectedSatellites
ORDER BY swe.kpIndex DESC;


// ──────────────────────────────────────────────────────────────
// Q9. Satellite lineage — successor chain
// ──────────────────────────────────────────────────────────────
MATCH path = (root:Satellite)-[:SUCCESSOR_OF*0..10]->(ancestor:Satellite)
WHERE root.name CONTAINS 'CARTOSAT'
  AND NOT (ancestor)-[:SUCCESSOR_OF]->()
RETURN [n IN nodes(path) | n.name] AS lineage,
       [n IN nodes(path) | n.launchDate] AS launchDates,
       length(path) AS generations;


// ──────────────────────────────────────────────────────────────
// Q10. Research landscape — most-cited papers per mission type
// ──────────────────────────────────────────────────────────────
MATCH (p:ResearchPaper)-[:DESCRIBES]->(s:Satellite)
WHERE p.publicationYear >= 2020
WITH s.missionType AS missionType,
     p.title AS title,
     p.citationCount AS citations,
     p.publicationYear AS year
ORDER BY citations DESC
WITH missionType, collect({title: title, citations: citations, year: year})[..3] AS topPapers
RETURN missionType, topPapers;


// ──────────────────────────────────────────────────────────────
// Q11. Operator risk profile — all their conjunction events
// ──────────────────────────────────────────────────────────────
MATCH (op:Operator {name: 'SpaceX'})-[:OPERATES]->(s:Satellite)
MATCH (s)-[:PRIMARY_IN|SECONDARY_IN]->(ce:ConjunctionEvent)
RETURN op.name AS operator,
       count(ce) AS totalConjunctions,
       count(CASE WHEN ce.riskLevel = 'red' THEN 1 END) AS redEvents,
       count(CASE WHEN ce.riskLevel = 'yellow' THEN 1 END) AS yellowEvents,
       count(CASE WHEN ce.resolved THEN 1 END) AS resolved,
       count(CASE WHEN ce.resolution = 'maneuver' THEN 1 END) AS maneuvered,
       avg(ce.collisionProbability) AS avgPc;


// ──────────────────────────────────────────────────────────────
// Q12. Cross-constellation conjunction risk matrix
// ──────────────────────────────────────────────────────────────
MATCH (s1:Satellite)-[:MEMBER_OF]->(c1:Constellation)
MATCH (s2:Satellite)-[:MEMBER_OF]->(c2:Constellation)
MATCH (s1)-[:PRIMARY_IN]->(ce:ConjunctionEvent)<-[:SECONDARY_IN]-(s2)
WHERE c1.constellationId < c2.constellationId
RETURN c1.name AS constellation1,
       c2.name AS constellation2,
       count(ce) AS conjunctions,
       avg(ce.collisionProbability) AS avgPc,
       max(ce.collisionProbability) AS maxPc
ORDER BY conjunctions DESC
LIMIT 20;


// ──────────────────────────────────────────────────────────────
// Q13. GRAPH DATA SCIENCE — PageRank on orbital neighborhood
//      (requires Neo4j GDS plugin)
// ──────────────────────────────────────────────────────────────
// Project graph
CALL gds.graph.project(
  'orbital-risk-graph',
  ['Satellite', 'DebrisObject'],
  {
    SECONDARY_IN: {orientation: 'UNDIRECTED'},
    PRIMARY_IN: {orientation: 'UNDIRECTED'}
  }
);

// Run PageRank to find highest-centrality objects
CALL gds.pageRank.stream('orbital-risk-graph')
YIELD nodeId, score
WITH gds.util.asNode(nodeId) AS node, score
WHERE 'Satellite' IN labels(node) OR 'DebrisObject' IN labels(node)
RETURN coalesce(node.name, node.description, node.noradId) AS object,
       labels(node)[0] AS type,
       round(score * 10000) / 10000 AS pageRankScore
ORDER BY pageRankScore DESC
LIMIT 25;

// Community detection — find orbital neighborhoods
CALL gds.louvain.stream('orbital-risk-graph')
YIELD nodeId, communityId
WITH gds.util.asNode(nodeId) AS node, communityId
RETURN communityId,
       count(*) AS members,
       collect(coalesce(node.name, node.noradId))[..5] AS sampleMembers
ORDER BY members DESC
LIMIT 10;


// ──────────────────────────────────────────────────────────────
// Q14. Vector similarity search (GraphRAG entry point)
// ──────────────────────────────────────────────────────────────
// Find satellites semantically similar to a query embedding
// $queryEmbedding is a List<Float> passed as parameter

CALL db.index.vector.queryNodes(
  'satellite_embedding',
  10,
  $queryEmbedding
)
YIELD node AS s, score
MATCH (s)-[:OPERATES]->(op:Operator)
MATCH (s)-[:OCCUPIES]->(o:Orbit)
RETURN s.name AS satellite,
       s.purpose AS purpose,
       o.regime AS orbit,
       op.name AS operator,
       score AS similarityScore
ORDER BY score DESC;
