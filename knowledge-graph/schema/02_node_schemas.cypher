// ============================================================
// ORBITIQ-X Aerospace Knowledge Graph
// Node Property Schemas — Full Reference
// ============================================================


// ── 1. Country ───────────────────────────────────────────────
// Cardinality: ~250 nodes (static)
//
// (:Country {
//   iso2:       String   -- PK  e.g. "IN"
//   iso3:       String       e.g. "IND"
//   name:       String       e.g. "India"
//   continent:  String       e.g. "Asia"
//   un_member:  Boolean
//   space_agency: String     e.g. "ISRO"
// })
//
// Relationships:
//   (Country)-[:HEADQUARTERED_IN]->(Organization)    1..* → 1
//   (Country)-[:REGISTERED_IN]<-(Satellite)          1..* → 1
//   (Country)-[:HOSTS]->(LaunchSite)                 1..* → 1
//   (Country)-[:MEMBER_OF]->(Organization {type:'IGO'})  *  → *

CREATE (:Country {
  iso2: 'IN', iso3: 'IND', name: 'India',
  continent: 'Asia', un_member: true, space_agency: 'ISRO'
});

CREATE (:Country {
  iso2: 'US', iso3: 'USA', name: 'United States',
  continent: 'North America', un_member: true, space_agency: 'NASA'
});

CREATE (:Country {
  iso2: 'CN', iso3: 'CHN', name: 'China',
  continent: 'Asia', un_member: true, space_agency: 'CNSA'
});


// ── 2. Organization ──────────────────────────────────────────
// Cardinality: ~10K nodes
//
// (:Organization {
//   orgId:       String   -- PK  e.g. "ORG-ISRO"
//   name:        String       e.g. "Indian Space Research Organisation"
//   shortName:   String       e.g. "ISRO"
//   type:        String       ENUM: agency | company | igo | research | military
//   founded:     Integer      e.g. 1969
//   country:     String       e.g. "India"
//   website:     String
//   description: String       -- for full-text + embedding
// })
//
// Relationships:
//   (Organization)-[:FOUNDED_BY]->(Country)             * → 1
//   (Organization)-[:FUNDS]->(Operator)                 1 → *
//   (Organization)-[:PUBLISHED]->(ResearchPaper)        1 → *
//   (Organization)-[:COLLABORATES_WITH]->(Organization) * → *

MERGE (isro:Organization {orgId: 'ORG-ISRO'})
SET isro.name = 'Indian Space Research Organisation',
    isro.shortName = 'ISRO',
    isro.type = 'agency',
    isro.founded = 1969,
    isro.country = 'India',
    isro.website = 'https://www.isro.gov.in',
    isro.description = 'National space agency of India, responsible for civilian space programme and satellite technology development';

MERGE (spacex:Organization {orgId: 'ORG-SPACEX'})
SET spacex.name = 'Space Exploration Technologies Corp',
    spacex.shortName = 'SpaceX',
    spacex.type = 'company',
    spacex.founded = 2002,
    spacex.country = 'USA',
    spacex.website = 'https://www.spacex.com',
    spacex.description = 'Private aerospace manufacturer and launch services provider';


// ── 3. Operator ──────────────────────────────────────────────
// Cardinality: ~5K nodes
//
// (:Operator {
//   operatorId:  String   -- PK  e.g. "OP-ISRO"
//   name:        String
//   type:        String       ENUM: government | commercial | military | academic
//   active:      Boolean
//   satelliteCount: Integer
//   primaryMission: String   e.g. "Earth Observation"
// })
//
// Relationships:
//   (Operator)-[:OPERATES]->(Satellite)          1 → *
//   (Operator)-[:REGISTERED_IN]->(Country)       * → 1
//   (Operator)-[:FUNDED_BY]->(Organization)      * → *


// ── 4. Satellite ─────────────────────────────────────────────
// Cardinality: ~10K active, 50K+ catalog entries
//
// (:Satellite {
//   noradId:               Integer  -- PK
//   cosparId:              String   -- PK  e.g. "2023-001A"
//   name:                  String   e.g. "CARTOSAT-3"
//   internationalDesignator: String
//   status:                String   ENUM: operational | defunct | reentry | unknown
//   purpose:               String   e.g. "Earth Observation"
//   missionType:           String   ENUM: eo | comms | nav | science | weather | debris | other
//   massKg:                Float
//   spanM:                 Float    -- physical span in meters
//   launchDate:            Date
//   expectedEol:           Date
//   inclination:           Float
//   altitudeKm:            Float
//   period:                Float    -- orbital period minutes
//   rcs:                   Float    -- radar cross-section m²
//   tle_line1:             String   -- cached TLE
//   tle_line2:             String
//   tle_epoch:             DateTime
//   embedding:             List<Float>  -- 1536-dim vector
// })
//
// Relationships:
//   (Satellite)-[:CARRIES]->(Mission)              1 → 1..*
//   (Satellite)-[:OCCUPIES]->(Orbit)               * → 1
//   (Satellite)-[:MEMBER_OF]->(Constellation)      * → 0..1
//   (Satellite)-[:LAUNCHED_BY]->(LaunchVehicle)    * → 1
//   (Satellite)-[:OPERATED_BY]->(Operator)         * → 1..*
//   (Satellite)-[:REGISTERED_IN]->(Country)        * → 1
//   (Satellite)-[:PRIMARY_IN]->(ConjunctionEvent)  * → *
//   (Satellite)-[:SUCCESSOR_OF]->(Satellite)       1 → 0..1
//   (Satellite)-[:DEPLOYED_FROM]->(Satellite)      * → 0..1

MERGE (cs3:Satellite {noradId: 42063})
SET cs3.cosparId = '2019-028A',
    cs3.name = 'CARTOSAT-3',
    cs3.status = 'operational',
    cs3.purpose = 'Earth Observation',
    cs3.missionType = 'eo',
    cs3.massKg = 1625.0,
    cs3.launchDate = date('2019-11-27'),
    cs3.altitudeKm = 509.0,
    cs3.inclination = 97.5;

MERGE (iss:Satellite {noradId: 25544})
SET iss.cosparId = '1998-067A',
    iss.name = 'ISS (ZARYA)',
    iss.status = 'operational',
    iss.purpose = 'Space Station',
    iss.missionType = 'science',
    iss.massKg = 419725.0,
    iss.launchDate = date('1998-11-20'),
    iss.altitudeKm = 408.0,
    iss.inclination = 51.6;

MERGE (sl2145:Satellite {noradId: 48274})
SET sl2145.cosparId = '2021-024-BD',
    sl2145.name = 'STARLINK-2145',
    sl2145.status = 'operational',
    sl2145.purpose = 'Communications',
    sl2145.missionType = 'comms',
    sl2145.massKg = 260.0,
    sl2145.launchDate = date('2021-04-07'),
    sl2145.altitudeKm = 550.0,
    sl2145.inclination = 53.0;


// ── 5. Constellation ─────────────────────────────────────────
// Cardinality: ~200 nodes
//
// (:Constellation {
//   constellationId: String  -- PK  e.g. "CONST-STARLINK"
//   name:            String  e.g. "Starlink"
//   operator:        String
//   totalPlanned:    Integer
//   totalDeployed:   Integer
//   shellAltKm:      List<Float>
//   shellInc:        List<Float>
//   purpose:         String  ENUM: broadband | eo | nav | sar | iot
//   status:          String  ENUM: active | planned | decommissioned
// })
//
// Relationships:
//   (Constellation)<-[:MEMBER_OF]-(Satellite)         * → 1
//   (Constellation)-[:OPERATED_BY]->(Operator)        1 → 1
//   (Constellation)-[:RAISES_CONCERN]->(ConjunctionEvent) 1 → *

MERGE (starlink:Constellation {constellationId: 'CONST-STARLINK'})
SET starlink.name = 'Starlink',
    starlink.operator = 'SpaceX',
    starlink.totalPlanned = 42000,
    starlink.totalDeployed = 5500,
    starlink.shellAltKm = [550.0, 540.0, 570.0],
    starlink.shellInc = [53.0, 53.2, 70.0],
    starlink.purpose = 'broadband',
    starlink.status = 'active';


// ── 6. Mission ───────────────────────────────────────────────
// Cardinality: ~20K nodes
//
// (:Mission {
//   missionId:    String  -- PK  e.g. "MSN-CHANDRAYAAN3"
//   name:         String  e.g. "Chandrayaan-3"
//   type:         String  ENUM: eo | comms | nav | science | military | demo | weather
//   description:  String
//   objectives:   List<String>
//   launchDate:   Date
//   endDate:      Date
//   lifetimeYrs:  Float
//   status:       String  ENUM: planned | active | completed | failed | extended
//   budget_musd:  Float   -- million USD
//   embedding:    List<Float>
// })
//
// Relationships:
//   (Mission)<-[:CARRIES]-(Satellite)             1..* → 1
//   (Mission)-[:FUNDED_BY]->(Organization)        * → 1..*
//   (Mission)-[:STUDIED_IN]->(ResearchPaper)      * → *

MERGE (ch3:Mission {missionId: 'MSN-CHANDRAYAAN3'})
SET ch3.name = 'Chandrayaan-3',
    ch3.type = 'science',
    ch3.description = 'Third Indian lunar exploration mission; achieved soft landing at lunar south pole',
    ch3.objectives = ['Lunar south pole landing', 'In-situ surface analysis', 'Inter-planetary science'],
    ch3.launchDate = date('2023-07-14'),
    ch3.status = 'completed',
    ch3.budget_musd = 75.0;


// ── 7. Orbit ─────────────────────────────────────────────────
// Cardinality: ~500K nodes (one per unique orbital shell)
//
// (:Orbit {
//   orbitId:       String  -- PK  composite key
//   regime:        String  ENUM: LEO | MEO | GEO | HEO | SSO | VLEO | TLI | GTO
//   altitudeKm:    Float   -- mean altitude
//   perigeeKm:     Float
//   apogeeKm:      Float
//   inclinationDeg: Float
//   eccentricity:  Float
//   raan:          Float   -- right ascension of ascending node
//   argPerigee:    Float
//   meanMotion:    Float   -- rev/day
//   period:        Float   -- minutes
//   decayYrs:      Float   -- estimated atmospheric decay lifetime
// })
//
// Relationships:
//   (Orbit)<-[:OCCUPIES]-(Satellite)       * → 1
//   (Orbit)<-[:OCCUPIES]-(DebrisObject)    * → 1
//   (Orbit)-[:INTERSECTS]->(Orbit)         * → *  (shell crossings)

MERGE (leo_sso:Orbit {orbitId: 'ORB-LEO-SSO-509'})
SET leo_sso.regime = 'SSO',
    leo_sso.altitudeKm = 509.0,
    leo_sso.perigeeKm = 505.0,
    leo_sso.apogeeKm = 513.0,
    leo_sso.inclinationDeg = 97.5,
    leo_sso.eccentricity = 0.0007,
    leo_sso.period = 94.8,
    leo_sso.decayYrs = 25.0;

MERGE (leo_550:Orbit {orbitId: 'ORB-LEO-550'})
SET leo_550.regime = 'LEO',
    leo_550.altitudeKm = 550.0,
    leo_550.inclinationDeg = 53.0,
    leo_550.eccentricity = 0.0002,
    leo_550.period = 95.5,
    leo_550.decayYrs = 5.0;


// ── 8. LaunchVehicle ─────────────────────────────────────────
// Cardinality: ~500 nodes (including retired)
//
// (:LaunchVehicle {
//   vehicleId:       String  -- PK  e.g. "LV-PSLV"
//   name:            String  e.g. "PSLV"
//   family:          String  e.g. "PSLV-XL"
//   manufacturer:    String
//   country:         String
//   status:          String  ENUM: active | retired | development | test
//   payloadLeoKg:    Float
//   payloadGeoKg:    Float
//   payloadSsoKg:    Float
//   firstFlight:     Date
//   lastFlight:      Date
//   totalLaunches:   Integer
//   successRate:     Float   -- 0.0 to 1.0
//   propellant:      String  ENUM: solid | liquid | hybrid | cryogenic
//   stages:          Integer
//   heightM:         Float
//   massKg:          Float
//   thrustKN:        Float
// })
//
// Relationships:
//   (LaunchVehicle)-[:LAUNCHES_FROM]->(LaunchSite)   * → *
//   (LaunchVehicle)-[:MANUFACTURED_BY]->(Organization) * → 1
//   (LaunchVehicle)<-[:LAUNCHED_BY]-(Satellite)      1 → *
//   (LaunchVehicle)<-[:LAUNCHED_BY]-(DebrisObject)   1 → *
//   (LaunchVehicle)-[:EVOLVED_FROM]->(LaunchVehicle) 1 → 0..1

MERGE (pslv:LaunchVehicle {vehicleId: 'LV-PSLV'})
SET pslv.name = 'PSLV',
    pslv.family = 'PSLV-XL',
    pslv.manufacturer = 'ISRO',
    pslv.country = 'India',
    pslv.status = 'active',
    pslv.payloadLeoKg = 3800.0,
    pslv.payloadSsoKg = 1750.0,
    pslv.firstFlight = date('1993-09-20'),
    pslv.totalLaunches = 62,
    pslv.successRate = 0.95,
    pslv.propellant = 'solid',
    pslv.stages = 4,
    pslv.heightM = 44.4,
    pslv.thrustKN = 4806.0;

MERGE (f9:LaunchVehicle {vehicleId: 'LV-FALCON9'})
SET f9.name = 'Falcon 9',
    f9.family = 'Falcon',
    f9.manufacturer = 'SpaceX',
    f9.country = 'USA',
    f9.status = 'active',
    f9.payloadLeoKg = 22800.0,
    f9.payloadGeoKg = 8300.0,
    f9.firstFlight = date('2010-06-04'),
    f9.successRate = 0.99,
    f9.propellant = 'liquid',
    f9.stages = 2;


// ── 9. LaunchSite ────────────────────────────────────────────
// Cardinality: ~100 nodes
//
// (:LaunchSite {
//   siteId:      String  -- PK  e.g. "LS-SDSC"
//   name:        String  e.g. "Satish Dhawan Space Centre"
//   shortName:   String  e.g. "SDSC SHAR"
//   country:     String
//   lat:         Float
//   lon:         Float
//   altitudeM:   Float
//   status:      String  ENUM: active | inactive | decommissioned
//   operator:    String
//   totalLaunches: Integer
//   firstLaunch: Date
//   pads:        List<String>
// })
//
// Relationships:
//   (LaunchSite)<-[:LAUNCHES_FROM]-(LaunchVehicle)  1 → *
//   (LaunchSite)-[:LOCATED_IN]->(Country)           * → 1

MERGE (sdsc:LaunchSite {siteId: 'LS-SDSC'})
SET sdsc.name = 'Satish Dhawan Space Centre',
    sdsc.shortName = 'SDSC SHAR',
    sdsc.country = 'India',
    sdsc.lat = 13.7199,
    sdsc.lon = 80.2304,
    sdsc.altitudeM = 14.0,
    sdsc.status = 'active',
    sdsc.operator = 'ISRO',
    sdsc.totalLaunches = 65,
    sdsc.pads = ['FLP', 'SLP'];

MERGE (ksc:LaunchSite {siteId: 'LS-KSC'})
SET ksc.name = 'Kennedy Space Center',
    ksc.shortName = 'KSC',
    ksc.country = 'USA',
    ksc.lat = 28.5729,
    ksc.lon = -80.6490,
    ksc.status = 'active',
    ksc.operator = 'NASA';


// ── 10. DebrisObject ─────────────────────────────────────────
// Cardinality: 20K tracked + 500K+ sub-catalog
//
// (:DebrisObject {
//   noradId:            Integer  -- PK
//   cosparId:           String
//   description:        String   e.g. "Rocket body fragment"
//   objectType:         String   ENUM: rocket_body | debris | fragmentation | unknown
//   radarCrossSection:  Float    -- m²  (>0.1 trackable)
//   regime:             String
//   perigeeKm:          Float
//   apogeeKm:           Float
//   inclinationDeg:     Float
//   fragmentationEvent: String   -- parent event ID
//   parentSatNorad:     Integer  -- NORAD of parent if known
//   decayDate:          Date     -- predicted reentry
//   riskCategory:       String   ENUM: critical | high | medium | low
// })
//
// Relationships:
//   (DebrisObject)-[:OCCUPIES]->(Orbit)                  * → 1
//   (DebrisObject)-[:ORIGINATED_FROM]->(Satellite)       * → 0..1
//   (DebrisObject)-[:ORIGINATED_FROM]->(LaunchVehicle)   * → 0..1
//   (DebrisObject)-[:FRAGMENT_OF]->(DebrisObject)        * → 0..1  (fragmentation chain)
//   (DebrisObject)-[:SECONDARY_IN]->(ConjunctionEvent)   * → *

MERGE (fengyun_debris:DebrisObject {noradId: 29777})
SET fengyun_debris.cosparId = '2007-001BS',
    fengyun_debris.description = 'Fengyun-1C ASAT fragmentation debris',
    fengyun_debris.objectType = 'fragmentation',
    fengyun_debris.radarCrossSection = 0.085,
    fengyun_debris.regime = 'LEO',
    fengyun_debris.perigeeKm = 795.0,
    fengyun_debris.apogeeKm = 830.0,
    fengyun_debris.inclinationDeg = 98.6,
    fengyun_debris.fragmentationEvent = 'FRAG-FY1C-2007',
    fengyun_debris.riskCategory = 'high';


// ── 11. ConjunctionEvent ─────────────────────────────────────
// Cardinality: ~100K active CDMs, millions historical
//
// (:ConjunctionEvent {
//   conjunctionId:      String   -- PK  e.g. "CDM-2024-0012847"
//   tca:                DateTime -- time of closest approach
//   missDistanceKm:     Float
//   collisionProbability: Float  -- Pc (Foster method)
//   relativeVelocityKms: Float   -- km/s at TCA
//   riskLevel:          String   ENUM: red | yellow | green | white
//   screeningOrg:       String   e.g. "18 SWS" | "LeoLabs" | "CARA"
//   cdmIssued:          DateTime
//   maneuverRequired:   Boolean
//   maneuverWindow:     DateTime -- latest maneuver time
//   resolved:           Boolean
//   resolution:         String   ENUM: maneuver | miss | conjunction_occurred | expired
// })
//
// Relationships:
//   (ConjunctionEvent)<-[:PRIMARY_IN]-(Satellite)     1..* → 1
//   (ConjunctionEvent)<-[:SECONDARY_IN]-(Satellite)   1..* → 1
//   (ConjunctionEvent)<-[:SECONDARY_IN]-(DebrisObject) * → *
//   (ConjunctionEvent)-[:ANALYZED_IN]->(ResearchPaper) * → *
//   (ConjunctionEvent)-[:TRIGGERED_BY]->(SpaceWeatherEvent) * → 0..1

MERGE (cdm1:ConjunctionEvent {conjunctionId: 'CDM-2024-0012847'})
SET cdm1.tca = datetime('2024-03-15T14:30:00Z'),
    cdm1.missDistanceKm = 0.083,
    cdm1.collisionProbability = 0.00123,
    cdm1.relativeVelocityKms = 14.2,
    cdm1.riskLevel = 'red',
    cdm1.screeningOrg = '18 SWS',
    cdm1.maneuverRequired = true,
    cdm1.resolved = true,
    cdm1.resolution = 'maneuver';


// ── 12. SpaceWeatherEvent ────────────────────────────────────
// Cardinality: ~50K historical events
//
// (:SpaceWeatherEvent {
//   eventId:    String   -- PK  e.g. "SWE-2024-X1.5-001"
//   type:       String   ENUM: solar_flare | geomagnetic_storm | cme | spe | dst_event
//   startTime:  DateTime
//   endTime:    DateTime
//   peakTime:   DateTime
//   kpIndex:    Float    -- 0-9 Kp
//   dstIndex:   Float    -- nT (negative = storm)
//   f107:       Float    -- solar flux index
//   xrayClass:  String   ENUM: A | B | C | M | X
//   xrayPeak:   Float    -- W/m²
//   category:   String   ENUM: G1|G2|G3|G4|G5 | S1-S5 | R1-R5
//   atmDensityEffect: Float  -- % change at 400km
//   source:     String   e.g. "AR3590"
//   impactAssessment: String
// })
//
// Relationships:
//   (SpaceWeatherEvent)-[:AFFECTS]->(Orbit)           1 → *
//   (SpaceWeatherEvent)-[:TRIGGERS]->(ConjunctionEvent) 1 → *  (density-driven)
//   (SpaceWeatherEvent)-[:ANALYZED_IN]->(ResearchPaper) * → *

MERGE (swe1:SpaceWeatherEvent {eventId: 'SWE-2024-X1.5-001'})
SET swe1.type = 'solar_flare',
    swe1.startTime = datetime('2024-01-22T06:07:00Z'),
    swe1.endTime = datetime('2024-01-22T06:32:00Z'),
    swe1.kpIndex = 6.7,
    swe1.xrayClass = 'X',
    swe1.xrayPeak = 1.5e-4,
    swe1.category = 'G3',
    swe1.atmDensityEffect = 18.4,
    swe1.source = 'AR3575';


// ── 13. ResearchPaper ────────────────────────────────────────
// Cardinality: ~500K nodes
//
// (:ResearchPaper {
//   doi:             String  -- PK  e.g. "10.1016/j.actaastro.2024.01.001"
//   title:           String
//   abstract:        String
//   keywords:        List<String>
//   authors:         List<String>
//   publicationYear: Integer
//   journal:         String
//   citationCount:   Integer
//   arxivId:         String
//   embedding:       List<Float>  -- 1536-dim
// })
//
// Relationships:
//   (ResearchPaper)<-[:PUBLISHED]-(Organization)       * → *
//   (ResearchPaper)-[:CITES]->(ResearchPaper)          * → *
//   (ResearchPaper)-[:ANALYZES]->(ConjunctionEvent)    * → *
//   (ResearchPaper)-[:ANALYZES]->(SpaceWeatherEvent)   * → *
//   (ResearchPaper)-[:DESCRIBES]->(Satellite)          * → *
//   (ResearchPaper)-[:DESCRIBES]->(LaunchVehicle)      * → *

MERGE (p1:ResearchPaper {doi: '10.1016/j.actaastro.2023.08.001'})
SET p1.title = 'Collision probability estimation for LEO conjunction events',
    p1.authors = ['Smith, J.', 'Patel, R.', 'Nair, K.'],
    p1.publicationYear = 2023,
    p1.journal = 'Acta Astronautica',
    p1.keywords = ['conjunction analysis', 'Foster method', 'Pc', 'LEO debris'],
    p1.citationCount = 87;
