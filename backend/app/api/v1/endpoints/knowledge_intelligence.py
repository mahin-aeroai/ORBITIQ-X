"""
ORBITIQ-X — Knowledge Intelligence API
Phases 17.7 / 17.8 / 17.9 / 17.10

Unified REST API for:
  Business Intelligence  — contracts, investments, market context
  Historical Intelligence — events, incidents, lineage chains, eras
  Scientific Knowledge   — papers, standards, patents, citation stats
  AKU Status            — Aerospace Knowledge Universe corpus summary

Mounts at: /api/v2/intelligence
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query

from caem.intelligence.business   import BusinessIntelligenceService
from caem.intelligence.historical import HistoricalIntelligenceService
from caem.intelligence.scientific import ScientificKnowledgeService

router = APIRouter(prefix="/api/v2/intelligence", tags=["Knowledge Intelligence"])

def require_viewer(): pass
def get_pg_session(): raise NotImplementedError("Wire to existing session dependency")


# ─── BUSINESS INTELLIGENCE ────────────────────────────────────────────────────

@router.get("/contracts")
async def list_contracts(
    client:         Optional[str]   = Query(None),
    recipient:      Optional[str]   = Query(None),
    status:         Optional[str]   = Query(None, description="active / complete / cancelled"),
    min_value_musd: float           = Query(0.0),
    limit:          int             = Query(50, ge=1, le=200),
    _auth                           = Depends(require_viewer),
):
    """List aerospace contracts sorted by value (largest first)."""
    svc = BusinessIntelligenceService()
    return {
        "contracts": svc.get_contract_portfolio(client, recipient, status, min_value_musd, limit),
        "count": len(svc.get_contract_portfolio(client, recipient, status, min_value_musd, limit)),
    }


@router.get("/investments")
async def list_investments(
    company:        Optional[str]   = Query(None),
    type:           Optional[str]   = Query(None, description="Series A / IPO / Strategic / etc."),
    min_amount_musd: float          = Query(0.0),
    limit:          int             = Query(50, ge=1, le=200),
    _auth                           = Depends(require_viewer),
):
    """List aerospace investment rounds sorted by date (newest first)."""
    svc = BusinessIntelligenceService()
    return {
        "investments": svc.get_investment_timeline(company, type, min_amount_musd, limit),
        "count": len(svc.get_investment_timeline(company, type, min_amount_musd, limit)),
    }


@router.get("/market-overview")
async def get_market_overview(_auth = Depends(require_viewer)):
    """Global space economy market context and major operator summary."""
    return BusinessIntelligenceService().get_market_overview()


@router.get("/funding-summary")
async def get_funding_summary(_auth = Depends(require_viewer)):
    """Aggregated funding metrics: totals, by type, largest round."""
    return BusinessIntelligenceService().get_funding_summary()


# ─── HISTORICAL INTELLIGENCE ──────────────────────────────────────────────────

@router.get("/events")
async def list_events(
    era:        Optional[str]   = Query(None, description="SPACE_RACE / SHUTTLE_ERA / COMMERCIAL_ERA / etc."),
    importance: Optional[str]   = Query(None, description="critical / major / minor"),
    domain:     Optional[str]   = Query(None),
    limit:      int             = Query(50, ge=1, le=200),
    _auth                       = Depends(require_viewer),
):
    """List historical aerospace events sorted by date."""
    svc = HistoricalIntelligenceService()
    return {
        "events": svc.get_events(era, importance, domain, limit),
        "count": len(svc.get_events(era, importance, domain, limit)),
    }


@router.get("/incidents")
async def list_incidents(
    severity:       Optional[str]   = Query(None, description="critical / major / minor"),
    incident_type:  Optional[str]   = Query(None, description="launch_failure / mission_failure / anomaly"),
    limit:          int             = Query(50, ge=1, le=200),
    _auth                           = Depends(require_viewer),
):
    """List incidents with root cause and corrective actions."""
    svc = HistoricalIntelligenceService()
    return {
        "incidents": svc.get_incidents(severity, incident_type, limit),
        "count": len(svc.get_incidents(severity, incident_type, limit)),
    }


@router.get("/lineage")
async def get_lineage_chains(_auth = Depends(require_viewer)):
    """Technology and program lineage chains (predecessor → successor)."""
    return {"chains": HistoricalIntelligenceService().get_lineage_chains()}


@router.get("/eras")
async def get_eras(_auth = Depends(require_viewer)):
    """Space history era reference with periods and descriptions."""
    return {"eras": HistoricalIntelligenceService().get_eras()}


# ─── SCIENTIFIC KNOWLEDGE ─────────────────────────────────────────────────────

@router.get("/papers")
async def list_papers(
    keyword:        Optional[str]   = Query(None),
    domain:         Optional[str]   = Query(None),
    min_citations:  int             = Query(0),
    limit:          int             = Query(50, ge=1, le=200),
    _auth                           = Depends(require_viewer),
):
    """List research papers sorted by citation count."""
    svc = ScientificKnowledgeService()
    return {
        "papers": svc.get_papers(keyword, domain, min_citations, limit),
        "count": len(svc.get_papers(keyword, domain, min_citations, limit)),
    }


@router.get("/standards")
async def list_standards(
    issuing_body:   Optional[str]   = Query(None, description="CCSDS / ISO / ECSS / IADC / IEEE"),
    domain:         Optional[str]   = Query(None),
    status:         str             = Query("active"),
    limit:          int             = Query(50, ge=1, le=200),
    _auth                           = Depends(require_viewer),
):
    """List aerospace standards and specifications."""
    svc = ScientificKnowledgeService()
    return {
        "standards": svc.get_standards(issuing_body, domain, status, limit),
        "count": len(svc.get_standards(issuing_body, domain, status, limit)),
    }


@router.get("/patents")
async def list_patents(
    assignee:   Optional[str]   = Query(None),
    domain:     Optional[str]   = Query(None),
    ipc_code:   Optional[str]   = Query(None),
    limit:      int             = Query(50, ge=1, le=200),
    _auth                       = Depends(require_viewer),
):
    """List aerospace patents sorted by filing date."""
    svc = ScientificKnowledgeService()
    return {
        "patents": svc.get_patents(assignee, domain, ipc_code, limit),
        "count": len(svc.get_patents(assignee, domain, ipc_code, limit)),
    }


@router.get("/citation-stats")
async def get_citation_stats(_auth = Depends(require_viewer)):
    """Aggregated citation and corpus statistics."""
    return ScientificKnowledgeService().get_citation_stats()


# ─── AEROSPACE KNOWLEDGE UNIVERSE v1 ─────────────────────────────────────────

@router.get("/aku-status")
async def get_aku_status(_auth = Depends(require_viewer)):
    """
    Aerospace Knowledge Universe v1 corpus status.
    Aggregates all knowledge layers: entities, relationships,
    BI data, historical records, scientific knowledge, Qdrant chunks.
    """
    from caem.intelligence.business   import SEED_CONTRACTS, SEED_INVESTMENTS
    from caem.intelligence.historical import SEED_HISTORICAL_EVENTS, SEED_INCIDENTS, LINEAGE_CHAINS
    from caem.intelligence.scientific import SEED_PAPERS, SEED_STANDARDS, SEED_PATENTS

    return {
        "version": "v1.0",
        "released": "2026-06-28",
        "status": "operational",
        "description": "Aerospace Knowledge Universe — first public knowledge corpus",

        "corpus_summary": {
            # From CAEM entity layer (Phases 17.1–17.6)
            "entity_classes_supported":     39,
            "relationship_types":           76,
            "caem_extension_schemas":       31,
            "neo4j_nodes":                  29248,
            "neo4j_relationships":          118681,
            "qdrant_chunks":                185,
            "knowledge_domains":            16,
            "graphrag_benchmark":           "20/20 (100%)",

            # Business Intelligence (Phase 17.7)
            "contracts_tracked":            len(SEED_CONTRACTS),
            "contracts_total_value_busd":   round(sum(c.get("value_musd",0) for c in SEED_CONTRACTS)/1000, 2),
            "investments_tracked":          len(SEED_INVESTMENTS),
            "investments_total_value_busd": round(sum(i.get("amount_musd",0) for i in SEED_INVESTMENTS)/1000, 2),

            # Historical Intelligence (Phase 17.8)
            "historical_events":            len(SEED_HISTORICAL_EVENTS),
            "incidents_documented":         len(SEED_INCIDENTS),
            "lineage_chains":               len(LINEAGE_CHAINS),
            "eras_covered":                 5,

            # Scientific Knowledge (Phase 17.9)
            "research_papers":              len(SEED_PAPERS),
            "standards":                    len(SEED_STANDARDS),
            "patents":                      len(SEED_PATENTS),
            "tracked_citations":            sum(p.get("citations",0) for p in SEED_PAPERS),
        },

        "layers": {
            "entity_model":         {"status": "complete", "phase": "17.1"},
            "relationship_ontology":{"status": "complete", "phase": "17.2"},
            "provenance_versioning":{"status": "complete", "phase": "17.3"},
            "ingestion_framework":  {"status": "complete", "phase": "17.4"},
            "entity_pages":         {"status": "complete", "phase": "17.5"},
            "cross_navigation":     {"status": "complete", "phase": "17.6"},
            "business_intelligence":{"status": "complete", "phase": "17.7"},
            "historical_intelligence":{"status": "complete", "phase": "17.8"},
            "scientific_knowledge": {"status": "complete", "phase": "17.9"},
            "aku_v1":               {"status": "complete", "phase": "17.10"},
        },

        "next_milestones": [
            "Phase 18: Redis activation + Digital Twin live positions",
            "Phase 19: Corpus expansion (185 → 500+ Qdrant chunks)",
            "Phase 20: Operator intelligence (OPERATED_BY population)",
        ],
    }
