"""
ORBITIQ-X — CAEM Entity Extension Schemas
Phase 17.1

Every entity class that extends BaseAerospaceEntity defines its
domain-specific fields here as a Pydantic model.

These models:
  1. Validate entity-class-specific fields at the API layer
  2. Serialize to `extension_data` JSONB column in PostgreSQL
  3. Are never stored directly in Neo4j (graph nodes carry minimal props)
  4. Power the "Technical Details" panel on every entity intelligence page

Extension models do not inherit from BaseAerospaceEntity.
They are composed into it via the `extension_data` field.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# ACTOR EXTENSIONS
# ---------------------------------------------------------------------------

class CountryExtension(BaseModel):
    iso_code_alpha2:        Optional[str]   = None   # US, IN, FR
    iso_code_alpha3:        Optional[str]   = None   # USA, IND, FRA
    capital_city:           Optional[str]   = None
    continent:              Optional[str]   = None
    population:             Optional[int]   = None
    gdp_usd_billions:       Optional[float] = None
    space_budget_musd:      Optional[float] = None
    space_budget_year:      Optional[int]   = None
    space_agency_aqids:     List[str]       = []
    active_satellites:      Optional[int]   = None
    launch_capability:      bool            = False
    treaties:               List[str]       = []     # AQID-AGREEMENT-...
    un_registry_member:     bool            = False
    outer_space_treaty:     bool            = True


class GovernmentAgencyExtension(BaseModel):
    parent_country_aqid:    Optional[str]   = None
    agency_type:            Optional[str]   = None   # civil / military / commercial_regulator
    established_year:       Optional[int]   = None
    annual_budget_musd:     Optional[float] = None
    budget_year:            Optional[int]   = None
    headquarters_city:      Optional[str]   = None
    administrator:          Optional[str]   = None
    employee_count:         Optional[int]   = None
    website:                Optional[str]   = None
    active_programs:        List[str]       = []     # AQIDs
    active_missions:        List[str]       = []     # AQIDs
    international_partners: List[str]       = []     # AQIDs


class CommercialCompanyExtension(BaseModel):
    ticker:                 Optional[str]   = None
    exchange:               Optional[str]   = None   # NYSE / NASDAQ / NSE
    founded_year:           Optional[int]   = None
    headquarters_city:      Optional[str]   = None
    headquarters_country:   Optional[str]   = None   # AQID-COUNTRY-...
    ceo:                    Optional[str]   = None
    employee_count:         Optional[int]   = None
    revenue_musd:           Optional[float] = None
    revenue_year:           Optional[int]   = None
    valuation_musd:         Optional[float] = None
    publicly_traded:        bool            = False
    parent_company_aqid:    Optional[str]   = None
    subsidiary_aqids:       List[str]       = []
    website:                Optional[str]   = None
    primary_domain:         Optional[str]   = None   # launch_services / satellites / defence
    active_satellites:      Optional[int]   = None
    launch_vehicles:        List[str]       = []     # AQIDs


class UniversityExtension(BaseModel):
    country_aqid:           Optional[str]   = None
    city:                   Optional[str]   = None
    established_year:       Optional[int]   = None
    aerospace_department:   Optional[str]   = None
    notable_alumni:         List[str]       = []     # Person AQIDs
    research_groups:        List[str]       = []
    active_missions:        List[str]       = []     # CubeSat / research AQIDs
    website:                Optional[str]   = None


class PersonExtension(BaseModel):
    nationality_aqid:       Optional[str]   = None
    birth_year:             Optional[int]   = None
    death_year:             Optional[int]   = None
    education:              List[Dict[str, str]] = []   # [{degree, institution, year}]
    roles:                  List[Dict[str, str]] = []   # [{title, org_aqid, start, end}]
    specializations:        List[str]       = []
    notable_contributions:  List[str]       = []
    awards:                 List[str]       = []
    publication_count:      Optional[int]   = None
    citation_count:         Optional[int]   = None
    orcid:                  Optional[str]   = None
    wikipedia_url:          Optional[str]   = None


# ---------------------------------------------------------------------------
# HARDWARE EXTENSIONS
# ---------------------------------------------------------------------------

class PropulsionStage(BaseModel):
    stage_number:       int
    engine_designation: str
    engine_count:       int             = 1
    propellant_type:    str             # LOX/RP-1 / LOX/LH2 / Hydrazine / Solid
    thrust_kn:          Optional[float] = None
    isp_vacuum_s:       Optional[float] = None
    isp_sl_s:           Optional[float] = None
    burn_time_s:        Optional[float] = None
    restartable:        bool            = False
    reusable:           bool            = False


class LaunchVehicleExtension(BaseModel):
    family:                 Optional[str]   = None   # Falcon / Ariane / GSLV
    variant:                Optional[str]   = None   # Block 5 / ECA / Mk III
    status:                 str             = "active"   # active / retired / development
    stages:                 List[PropulsionStage] = []
    stage_count:            Optional[int]   = None

    # Performance (to standard reference orbits)
    payload_leo_kg:         Optional[float] = None
    payload_gto_kg:         Optional[float] = None
    payload_sso_kg:         Optional[float] = None
    payload_tli_kg:         Optional[float] = None   # Trans-Lunar Injection
    payload_mars_kg:        Optional[float] = None

    # Physical
    height_m:               Optional[float] = None
    diameter_m:             Optional[float] = None
    liftoff_mass_t:         Optional[float] = None
    fairing_diameter_m:     Optional[float] = None
    fairing_height_m:       Optional[float] = None

    # Operational
    reusable:               bool            = False
    reuse_record:           Optional[int]   = None   # max times a booster was reused
    first_flight_date:      Optional[date]  = None
    total_launches:         Optional[int]   = None
    total_successes:        Optional[int]   = None
    total_failures:         Optional[int]   = None
    success_rate_pct:       Optional[float] = None
    launch_sites:           List[str]       = []     # AQID-SITE-...

    # Commercial
    manufacturer_aqid:      Optional[str]   = None
    operator_aqid:          Optional[str]   = None
    unit_cost_musd:         Optional[float] = None
    cost_year:              Optional[int]   = None


class SatelliteExtension(BaseModel):
    # Catalog identifiers
    norad_id:               Optional[int]   = None
    cospar_id:              Optional[str]   = None
    object_type:            str             = "PAYLOAD"   # PAYLOAD / ROCKET BODY / DEBRIS

    # Orbit
    orbit_regime:           Optional[str]   = None   # LEO / MEO / GEO / HEO / SSO / GTO
    altitude_km:            Optional[float] = None
    altitude_perigee_km:    Optional[float] = None
    altitude_apogee_km:     Optional[float] = None
    inclination_deg:        Optional[float] = None
    period_min:             Optional[float] = None
    raan_deg:               Optional[float] = None
    eccentricity:           Optional[float] = None
    semi_major_axis_km:     Optional[float] = None

    # Mission
    mission_type:           Optional[str]   = None   # Earth Obs / Comms / Nav / Science
    coverage:               Optional[str]   = None   # Global / Regional / Polar
    design_life_years:      Optional[float] = None
    mass_kg:                Optional[float] = None
    power_w:                Optional[float] = None

    # Operational
    operator_aqid:          Optional[str]   = None
    manufacturer_aqid:      Optional[str]   = None
    launch_vehicle_aqid:    Optional[str]   = None
    launch_site_aqid:       Optional[str]   = None
    launch_date:            Optional[date]  = None
    eol_date:               Optional[date]  = None
    operational_status:     str             = "operational"   # operational / decommissioned / failed

    # Constellation
    constellation_aqid:     Optional[str]   = None
    slot_id:                Optional[str]   = None   # Position within constellation


class ComponentExtension(BaseModel):
    component_type:         Optional[str]   = None   # Engine / Solar Panel / Antenna / Battery
    manufacturer_aqid:      Optional[str]   = None
    mass_kg:                Optional[float] = None
    trl:                    Optional[int]   = None   # Technology Readiness Level 1-9
    used_on:                List[str]       = []     # AQIDs of vehicles/satellites using this
    part_number:            Optional[str]   = None
    qualified_for:          List[str]       = []     # Environment qualifications


# ---------------------------------------------------------------------------
# INFRASTRUCTURE EXTENSIONS
# ---------------------------------------------------------------------------

class LaunchPad(BaseModel):
    pad_id:             str
    pad_name:           str
    status:             str             = "active"
    supported_vehicles: List[str]       = []     # AQIDs
    latitude:           Optional[float] = None
    longitude:          Optional[float] = None


class LaunchSiteExtension(BaseModel):
    country_aqid:               Optional[str]   = None
    operator_aqid:              Optional[str]   = None
    site_type:                  str             = "launch_site"   # launch_site / spaceport / range
    latitude:                   Optional[float] = None
    longitude:                  Optional[float] = None
    elevation_m:                Optional[float] = None
    established_year:           Optional[int]   = None
    pads:                       List[LaunchPad] = []
    supported_inclinations:     List[float]     = []   # Degrees
    total_launches:             Optional[int]   = None
    annual_capacity:            Optional[int]   = None
    status:                     str             = "active"


class GroundStationExtension(BaseModel):
    operator_aqid:          Optional[str]   = None
    country_aqid:           Optional[str]   = None
    latitude:               Optional[float] = None
    longitude:              Optional[float] = None
    elevation_m:            Optional[float] = None
    station_type:           Optional[str]   = None   # TT&C / DSN / Commercial
    antenna_diameters_m:    List[float]     = []
    frequency_bands:        List[str]       = []     # S / X / Ka / Ku
    supported_satellites:   List[str]       = []     # AQIDs


# ---------------------------------------------------------------------------
# PROGRAM & MISSION EXTENSIONS
# ---------------------------------------------------------------------------

class ProgramExtension(BaseModel):
    program_type:           Optional[str]   = None   # exploration / commercial / defence / science
    lead_agency_aqid:       Optional[str]   = None
    partner_aqids:          List[str]       = []
    total_budget_musd:      Optional[float] = None
    budget_year:            Optional[int]   = None
    start_year:             Optional[int]   = None
    end_year:               Optional[int]   = None
    status:                 str             = "active"
    mission_aqids:          List[str]       = []
    objectives:             List[str]       = []
    destination:            Optional[str]   = None   # Moon / Mars / ISS / GEO


class MissionExtension(BaseModel):
    mission_type:           Optional[str]   = None   # crewed / robotic / cargo / science
    destination:            Optional[str]   = None
    program_aqid:           Optional[str]   = None
    lead_agency_aqid:       Optional[str]   = None
    partner_aqids:          List[str]       = []

    # Crew (for crewed missions)
    crew_aqids:             List[str]       = []     # Person AQIDs
    crew_size:              Optional[int]   = None

    # Hardware
    launch_vehicle_aqid:    Optional[str]   = None
    spacecraft_aqid:        Optional[str]   = None
    instrument_aqids:       List[str]       = []

    # Timeline
    launch_date:            Optional[date]  = None
    arrival_date:           Optional[date]  = None
    end_date:               Optional[date]  = None
    duration_days:          Optional[int]   = None

    # Outcomes
    mission_status:         str             = "planned"   # planned / active / complete / failed
    objectives:             List[str]       = []
    outcomes:               List[str]       = []
    key_discoveries:        List[str]       = []

    # Cost
    total_cost_musd:        Optional[float] = None


class ConstellationExtension(BaseModel):
    operator_aqid:          Optional[str]   = None
    purpose:                Optional[str]   = None   # broadband / imaging / IoT / navigation
    target_altitude_km:     Optional[float] = None
    orbit_regime:           Optional[str]   = None
    planned_size:           Optional[int]   = None
    operational_count:      Optional[int]   = None
    total_launched:         Optional[int]   = None
    orbital_planes:         Optional[int]   = None
    satellites_per_plane:   Optional[int]   = None
    coverage:               Optional[str]   = None


# ---------------------------------------------------------------------------
# KNOWLEDGE EXTENSIONS
# ---------------------------------------------------------------------------

class TechnologyExtension(BaseModel):
    trl:                    Optional[int]   = Field(default=None, ge=1, le=9)
    domain:                 Optional[str]   = None   # propulsion / comms / materials / AI
    applications:           List[str]       = []
    developer_aqids:        List[str]       = []
    patent_aqids:           List[str]       = []
    paper_aqids:            List[str]       = []
    predecessor_tech_aqids: List[str]       = []
    successor_tech_aqids:   List[str]       = []
    first_demonstrated:     Optional[date]  = None
    space_heritage:         bool            = False


class StandardExtension(BaseModel):
    issuing_body:           Optional[str]   = None   # CCSDS / ISO / ECSS / IEEE / MIL
    standard_number:        Optional[str]   = None   # 727.0-B-5
    full_reference:         Optional[str]   = None
    status:                 str             = "active"   # active / superseded / withdrawn
    domain:                 Optional[str]   = None
    supersedes:             List[str]       = []     # AQIDs of superseded standards
    superseded_by:          Optional[str]   = None   # AQID
    published_date:         Optional[date]  = None
    revision_history:       List[Dict]      = []


class ResearchPaperExtension(BaseModel):
    doi:                    Optional[str]   = None
    arxiv_id:               Optional[str]   = None
    journal:                Optional[str]   = None
    conference:             Optional[str]   = None
    volume:                 Optional[str]   = None
    issue:                  Optional[str]   = None
    pages:                  Optional[str]   = None
    published_year:         Optional[int]   = None
    author_aqids:           List[str]       = []     # Person AQIDs (if in system)
    author_names:           List[str]       = []     # Raw names for unresolved authors
    citation_count:         Optional[int]   = None
    abstract:               Optional[str]   = None
    keywords:               List[str]       = []
    cites_aqids:            List[str]       = []     # Papers this paper cites


class PatentExtension(BaseModel):
    patent_number:          Optional[str]   = None
    patent_office:          Optional[str]   = None   # USPTO / EPO / JPO
    filing_date:            Optional[date]  = None
    granted_date:           Optional[date]  = None
    expiry_date:            Optional[date]  = None
    status:                 str             = "active"   # active / expired / pending
    assignee_aqid:          Optional[str]   = None
    inventor_aqids:         List[str]       = []
    inventor_names:         List[str]       = []
    ipc_codes:              List[str]       = []     # International Patent Classification
    claims_summary:         Optional[str]   = None
    related_technology_aqids: List[str]    = []


# ---------------------------------------------------------------------------
# COMMERCIAL EXTENSIONS
# ---------------------------------------------------------------------------

class ContractExtension(BaseModel):
    contract_number:        Optional[str]   = None
    contract_type:          Optional[str]   = None   # IDIQ / FFP / CPFF / OTA / FAR
    value_musd:             Optional[float] = None
    ceiling_musd:           Optional[float] = None   # For IDIQ contracts
    client_aqid:            Optional[str]   = None
    recipient_aqid:         Optional[str]   = None
    subcontractor_aqids:    List[str]       = []
    award_date:             Optional[date]  = None
    start_date:             Optional[date]  = None
    end_date:               Optional[date]  = None
    period_of_performance:  Optional[str]   = None
    scope:                  Optional[str]   = None
    status:                 str             = "active"
    program_aqid:           Optional[str]   = None
    mission_aqids:          List[str]       = []


class InvestmentExtension(BaseModel):
    investment_type:        Optional[str]   = None   # Seed / Series A-E / IPO / Acquisition / Grant
    amount_musd:            Optional[float] = None
    recipient_aqid:         Optional[str]   = None
    investor_aqids:         List[str]       = []
    announcement_date:      Optional[date]  = None
    close_date:             Optional[date]  = None
    post_money_valuation:   Optional[float] = None
    round_number:           Optional[str]   = None
    notable_terms:          Optional[str]   = None


# ---------------------------------------------------------------------------
# EVENT EXTENSIONS
# ---------------------------------------------------------------------------

class IncidentExtension(BaseModel):
    incident_type:          Optional[str]   = None   # launch_failure / anomaly / collision / reentry
    severity:               Optional[str]   = None   # critical / major / minor
    affected_mission_aqids: List[str]       = []
    date_of_incident:       Optional[date]  = None
    location:               Optional[str]   = None
    casualties:             Optional[int]   = None
    financial_loss_musd:    Optional[float] = None
    root_cause:             Optional[str]   = None
    contributing_factors:   List[str]       = []
    corrective_actions:     List[str]       = []
    investigation_status:   str             = "complete"
    investigation_body:     Optional[str]   = None
    report_aqids:           List[str]       = []     # Investigation report document AQIDs


# ---------------------------------------------------------------------------
# CELESTIAL EXTENSIONS
# ---------------------------------------------------------------------------

class CelestialBodyExtension(BaseModel):
    body_type:              Optional[str]   = None   # planet / moon / asteroid / comet / dwarf_planet
    diameter_km:            Optional[float] = None
    mass_kg:                Optional[float] = None
    density_g_cm3:          Optional[float] = None
    surface_gravity_ms2:    Optional[float] = None
    escape_velocity_kms:    Optional[float] = None
    orbital_period_days:    Optional[float] = None
    rotation_period_hours:  Optional[float] = None
    semi_major_axis_au:     Optional[float] = None
    eccentricity:           Optional[float] = None
    inclination_deg:        Optional[float] = None
    atmosphere:             Optional[str]   = None
    composition:            Optional[str]   = None
    hazard_level:           Optional[str]   = None   # For PHAs: PHA / non-PHA
    torino_scale:           Optional[int]   = None
    discovery_year:         Optional[int]   = None
    discoverer_aqid:        Optional[str]   = None
    visited_by:             List[str]       = []     # Mission AQIDs


# ---------------------------------------------------------------------------
# EXTENSION REGISTRY
# Maps EntityClass → extension Pydantic model for validation and serialization.
# ---------------------------------------------------------------------------

from caem.base import EntityClass

EXTENSION_REGISTRY: Dict[EntityClass, type] = {
    EntityClass.COUNTRY:            CountryExtension,
    EntityClass.GOV_AGENCY:         GovernmentAgencyExtension,
    EntityClass.COMPANY:            CommercialCompanyExtension,
    EntityClass.UNIVERSITY:         UniversityExtension,
    EntityClass.RESEARCH_ORG:       UniversityExtension,   # Shares schema
    EntityClass.PERSON:             PersonExtension,
    EntityClass.LAUNCH_VEHICLE:     LaunchVehicleExtension,
    EntityClass.SATELLITE:          SatelliteExtension,
    EntityClass.PAYLOAD:            SatelliteExtension,    # Shares base schema
    EntityClass.SPACECRAFT:         SatelliteExtension,
    EntityClass.DEBRIS:             SatelliteExtension,
    EntityClass.COMPONENT:          ComponentExtension,
    EntityClass.SENSOR:             ComponentExtension,
    EntityClass.INSTRUMENT:         ComponentExtension,
    EntityClass.LAUNCH_SITE:        LaunchSiteExtension,
    EntityClass.GROUND_STATION:     GroundStationExtension,
    EntityClass.PROGRAM:            ProgramExtension,
    EntityClass.MISSION:            MissionExtension,
    EntityClass.CONSTELLATION:      ConstellationExtension,
    EntityClass.TECHNOLOGY:         TechnologyExtension,
    EntityClass.STANDARD:           StandardExtension,
    EntityClass.SPECIFICATION:      StandardExtension,
    EntityClass.RESEARCH_PAPER:     ResearchPaperExtension,
    EntityClass.PATENT:             PatentExtension,
    EntityClass.CONTRACT:           ContractExtension,
    EntityClass.INVESTMENT:         InvestmentExtension,
    EntityClass.INCIDENT:           IncidentExtension,
    EntityClass.ANOMALY:            IncidentExtension,
    EntityClass.ASTEROID:           CelestialBodyExtension,
    EntityClass.COMET:              CelestialBodyExtension,
    EntityClass.CELESTIAL_BODY:     CelestialBodyExtension,
}


def validate_extension(entity_class: EntityClass, extension_data: Dict) -> Dict:
    """
    Validate extension_data against the registered schema for the entity class.
    Returns validated dict. Raises ValidationError on schema violations.
    """
    model_class = EXTENSION_REGISTRY.get(entity_class)
    if model_class is None:
        return extension_data   # No registered extension — pass through
    validated = model_class(**extension_data)
    return validated.model_dump(exclude_none=True)
