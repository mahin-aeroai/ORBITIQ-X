// ============================================================
// ORBITIQ-X Aerospace Knowledge Graph
// Relationship Wiring — Sample Data Connections
// ============================================================

// ── Wire Country → Organization ─────────────────────────────
MATCH (india:Country {iso2: 'IN'})
MATCH (isro:Organization {orgId: 'ORG-ISRO'})
MERGE (isro)-[:HEADQUARTERED_IN]->(india);

MATCH (usa:Country {iso2: 'US'})
MATCH (spacex:Organization {orgId: 'ORG-SPACEX'})
MERGE (spacex)-[:HEADQUARTERED_IN]->(usa);

// ── Wire Satellite → Orbit ───────────────────────────────────
MATCH (cs3:Satellite {noradId: 42063})
MATCH (orb:Orbit {orbitId: 'ORB-LEO-SSO-509'})
MERGE (cs3)-[:OCCUPIES]->(orb);

MATCH (sl:Satellite {noradId: 48274})
MATCH (orb:Orbit {orbitId: 'ORB-LEO-550'})
MERGE (sl)-[:OCCUPIES]->(orb);

// ── Wire Satellite → LaunchVehicle ──────────────────────────
MATCH (cs3:Satellite {noradId: 42063})
MATCH (pslv:LaunchVehicle {vehicleId: 'LV-PSLV'})
MERGE (cs3)-[:LAUNCHED_BY {
  launchDate: date('2019-11-27'),
  launchMassKg: 1625.0,
  launchSiteId: 'LS-SDSC',
  missionSuccess: true
}]->(pslv);

MATCH (sl:Satellite {noradId: 48274})
MATCH (f9:LaunchVehicle {vehicleId: 'LV-FALCON9'})
MERGE (sl)-[:LAUNCHED_BY {
  launchDate: date('2021-04-07'),
  launchMassKg: 260.0,
  launchSiteId: 'LS-KSC',
  missionSuccess: true
}]->(f9);

// ── Wire LaunchVehicle → LaunchSite ─────────────────────────
MATCH (pslv:LaunchVehicle {vehicleId: 'LV-PSLV'})
MATCH (sdsc:LaunchSite {siteId: 'LS-SDSC'})
MERGE (pslv)-[:LAUNCHES_FROM {primaryPad: 'FLP'}]->(sdsc);

MATCH (f9:LaunchVehicle {vehicleId: 'LV-FALCON9'})
MATCH (ksc:LaunchSite {siteId: 'LS-KSC'})
MERGE (f9)-[:LAUNCHES_FROM {primaryPad: 'LC-39A'}]->(ksc);

// ── Wire Satellite → Constellation ──────────────────────────
MATCH (sl:Satellite {noradId: 48274})
MATCH (starlink:Constellation {constellationId: 'CONST-STARLINK'})
MERGE (sl)-[:MEMBER_OF {
  shell: 1,
  plane: 24,
  slot: 4
}]->(starlink);

// ── Wire Debris → ConjunctionEvent ──────────────────────────
MATCH (iss:Satellite {noradId: 25544})
MATCH (cdm:ConjunctionEvent {conjunctionId: 'CDM-2024-0012847'})
MERGE (iss)-[:PRIMARY_IN {
  HBR: 10.0,
  positionCovarianceDiag: [0.25, 0.18, 0.12]
}]->(cdm);

MATCH (d:DebrisObject {noradId: 29777})
MATCH (cdm:ConjunctionEvent {conjunctionId: 'CDM-2024-0012847'})
MERGE (d)-[:SECONDARY_IN {
  HBR: 0.5,
  positionCovarianceDiag: [12.5, 8.3, 4.1]
}]->(cdm);

// ── Wire Mission → Satellite ─────────────────────────────────
MATCH (cs3:Satellite {noradId: 42063})
MATCH (mission:Mission {missionId: 'MSN-CARTOSAT3'})
MERGE (cs3)-[:CARRIES]->(mission)
ON CREATE SET mission.missionId = 'MSN-CARTOSAT3',
              mission.name = 'CARTOSAT-3 EO Mission',
              mission.type = 'eo',
              mission.status = 'operational';

// ── Wire SpaceWeatherEvent → Orbit ───────────────────────────
MATCH (swe:SpaceWeatherEvent {eventId: 'SWE-2024-X1.5-001'})
MATCH (orb:Orbit {orbitId: 'ORB-LEO-550'})
MERGE (swe)-[:AFFECTS {
  densityChangePct: 18.4,
  decayAccelerationPct: 12.1,
  affectedShellAlt: [400, 600]
}]->(orb);

// ── Wire ResearchPaper → ConjunctionEvent ───────────────────
MATCH (p:ResearchPaper {doi: '10.1016/j.actaastro.2023.08.001'})
MATCH (cdm:ConjunctionEvent {conjunctionId: 'CDM-2024-0012847'})
MERGE (p)-[:ANALYZES]->(cdm);
