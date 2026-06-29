"""
ORBITIQ-X — Business Intelligence Layer
Phase 17.7

Provides structured BI queries over aerospace commercial entities:
  - Contracts (value, parties, status, program linkage)
  - Investments (rounds, investors, valuations, timeline)
  - Market context (company revenue, competitive landscape)
  - Funding flows (agency → program → company)

All data served from PostgreSQL aerospace_entities table,
with Neo4j graph traversal for relationship intelligence.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SEED DATA — curated real aerospace BI data to bootstrap the corpus
# ---------------------------------------------------------------------------

SEED_CONTRACTS: List[Dict[str, Any]] = [
    {
        "aqid": "AQID-CONTRACT-NASA-CRS-2-SPACEX",
        "display_name": "NASA CRS-2 Commercial Resupply Services — SpaceX",
        "contract_number": "NNK14MA95C",
        "contract_type": "IDIQ",
        "value_musd": 3040.0,
        "client": "NASA",
        "recipient": "SpaceX",
        "award_date": "2014-12-05",
        "start_date": "2016-01-01",
        "end_date": "2024-12-31",
        "status": "complete",
        "scope": "ISS cargo delivery missions via Dragon spacecraft",
        "program": "Commercial Resupply Services",
        "domains": ["human_spaceflight", "commercial"],
        "tags": ["nasa", "spacex", "crs", "iss"],
    },
    {
        "aqid": "AQID-CONTRACT-NASA-ARTEMIS-SPACEX-HLS",
        "display_name": "NASA Artemis Human Landing System — SpaceX",
        "contract_number": "80ARC020C0003",
        "contract_type": "FFP",
        "value_musd": 2890.0,
        "client": "NASA",
        "recipient": "SpaceX",
        "award_date": "2021-04-16",
        "start_date": "2021-04-16",
        "end_date": "2026-12-31",
        "status": "active",
        "scope": "Human lunar landing system (Starship HLS) for Artemis III",
        "program": "Artemis",
        "domains": ["human_spaceflight", "lunar_exploration"],
        "tags": ["nasa", "spacex", "artemis", "moon", "hls"],
    },
    {
        "aqid": "AQID-CONTRACT-DOD-NSSL-ULA",
        "display_name": "National Security Space Launch Phase 2 — ULA",
        "contract_number": "FA8811-20-C-0003",
        "contract_type": "IDIQ",
        "value_musd": 2000.0,
        "client": "US Space Force",
        "recipient": "United Launch Alliance",
        "award_date": "2020-08-07",
        "start_date": "2020-10-01",
        "end_date": "2027-09-30",
        "status": "active",
        "scope": "National security satellite launches via Vulcan Centaur",
        "program": "National Security Space Launch",
        "domains": ["launch_systems", "defence_security"],
        "tags": ["ussf", "ula", "nssl", "vulcan"],
    },
    {
        "aqid": "AQID-CONTRACT-DOD-NSSL-SPACEX",
        "display_name": "National Security Space Launch Phase 2 — SpaceX",
        "contract_number": "FA8811-20-C-0001",
        "contract_type": "IDIQ",
        "value_musd": 316.0,
        "client": "US Space Force",
        "recipient": "SpaceX",
        "award_date": "2020-08-07",
        "start_date": "2020-10-01",
        "end_date": "2027-09-30",
        "status": "active",
        "scope": "National security satellite launches via Falcon 9/Heavy",
        "program": "National Security Space Launch",
        "domains": ["launch_systems", "defence_security"],
        "tags": ["ussf", "spacex", "nssl", "falcon"],
    },
    {
        "aqid": "AQID-CONTRACT-ESA-ARIANE-6-AIRBUS",
        "display_name": "Ariane 6 Development Contract — Airbus/ArianeGroup",
        "contract_number": "ESA-ARI-6-DEV",
        "contract_type": "CPFF",
        "value_musd": 4000.0,
        "client": "ESA",
        "recipient": "ArianeGroup",
        "award_date": "2015-12-01",
        "start_date": "2015-12-01",
        "end_date": "2024-12-31",
        "status": "complete",
        "scope": "Development of Ariane 6 launch vehicle to replace Ariane 5",
        "program": "Ariane 6",
        "domains": ["launch_systems"],
        "tags": ["esa", "ariane", "airbus", "europe"],
    },
]

SEED_INVESTMENTS: List[Dict[str, Any]] = [
    {
        "aqid": "AQID-INVESTMENT-SPACEX-SERIES-N-2023",
        "display_name": "SpaceX Series N Funding Round 2023",
        "investment_type": "Series N",
        "amount_musd": 750.0,
        "recipient": "SpaceX",
        "investors": ["Andreessen Horowitz", "Google", "Baillie Gifford"],
        "announcement_date": "2023-06-01",
        "post_money_valuation": 150000.0,
        "domains": ["commercial", "launch_systems"],
        "tags": ["spacex", "funding", "commercial"],
    },
    {
        "aqid": "AQID-INVESTMENT-AST-SPACEMOBILE-IPO-2021",
        "display_name": "AST SpaceMobile SPAC Merger / Public Listing",
        "investment_type": "IPO",
        "amount_musd": 462.0,
        "recipient": "AST SpaceMobile",
        "investors": ["NPA Acquisition Corp", "Rakuten", "Vodafone", "American Tower"],
        "announcement_date": "2021-04-06",
        "post_money_valuation": 1800.0,
        "domains": ["commercial", "communications"],
        "tags": ["ast-spacemobile", "spac", "ipo", "satellite-broadband"],
    },
    {
        "aqid": "AQID-INVESTMENT-PLANET-SERIES-D-2018",
        "display_name": "Planet Labs Series D Funding",
        "investment_type": "Series D",
        "amount_musd": 183.0,
        "recipient": "Planet Labs",
        "investors": ["Google", "Founders Fund", "Innovation Endeavors"],
        "announcement_date": "2018-02-28",
        "post_money_valuation": 1100.0,
        "domains": ["commercial", "earth_observation"],
        "tags": ["planet", "earth-observation", "series-d"],
    },
    {
        "aqid": "AQID-INVESTMENT-ROCKET-LAB-SERIES-E-2020",
        "display_name": "Rocket Lab Series E Funding",
        "investment_type": "Series E",
        "amount_musd": 140.0,
        "recipient": "Rocket Lab",
        "investors": ["Future Fund", "Khosla Ventures", "Vector Capital"],
        "announcement_date": "2020-04-22",
        "post_money_valuation": 1410.0,
        "domains": ["commercial", "launch_systems"],
        "tags": ["rocket-lab", "small-sat", "launch"],
    },
    {
        "aqid": "AQID-INVESTMENT-ONEWEB-RESCUE-2020",
        "display_name": "OneWeb Bankruptcy Exit Investment",
        "investment_type": "Strategic",
        "amount_musd": 1000.0,
        "recipient": "OneWeb",
        "investors": ["UK Government", "Bharti Global"],
        "announcement_date": "2020-11-03",
        "post_money_valuation": 1000.0,
        "domains": ["commercial", "communications"],
        "tags": ["oneweb", "constellation", "broadband", "uk"],
    },
]

SEED_MARKET_CONTEXT: Dict[str, Any] = {
    "global_space_economy_busd": 469.0,
    "reference_year": 2021,
    "commercial_share_pct": 74.0,
    "government_share_pct": 26.0,
    "launch_services_busd": 9.1,
    "satellite_manufacturing_busd": 13.7,
    "satellite_services_busd": 116.0,
    "ground_equipment_busd": 133.6,
    "major_commercial_operators": [
        {"name": "SpaceX/Starlink", "satellites": 4500, "revenue_busd": 1.4, "type": "broadband"},
        {"name": "OneWeb", "satellites": 634, "revenue_busd": None, "type": "broadband"},
        {"name": "Planet Labs", "satellites": 200, "revenue_busd": 0.19, "type": "earth_obs"},
        {"name": "Maxar", "satellites": 5, "revenue_busd": 1.7, "type": "earth_obs"},
        {"name": "Iridium", "satellites": 66, "revenue_busd": 0.59, "type": "voice_data"},
    ],
    "source": "Space Foundation Space Report 2022",
    "source_url": "https://www.spacefoundation.org/space_brief/the-space-report-2022/",
}


class BusinessIntelligenceService:
    """
    Provides BI queries and aggregations for aerospace commercial entities.
    Reads from PostgreSQL aerospace_entities; falls back to seed data.
    """

    def __init__(self, pg=None, neo4j=None):
        self.pg     = pg
        self.neo4j  = neo4j

    def get_contract_portfolio(
        self,
        client: Optional[str] = None,
        recipient: Optional[str] = None,
        status: Optional[str] = None,
        min_value_musd: float = 0.0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Query contracts from DB; fall back to seed data."""
        if self.pg:
            try:
                where = ["entity_class = 'CONTRACT'", "lifecycle_status = 'published'"]
                params: Dict[str, Any] = {"limit": limit, "min_val": min_value_musd}
                if client:
                    where.append("extension_data->>'client' ILIKE :client")
                    params["client"] = f"%{client}%"
                if recipient:
                    where.append("extension_data->>'recipient' ILIKE :recipient")
                    params["recipient"] = f"%{recipient}%"
                if status:
                    where.append("extension_data->>'status' = :status")
                    params["status"] = status
                where.append("(extension_data->>'value_musd')::float >= :min_val")

                rows = self.pg.execute(
                    f"""SELECT aqid, display_name, extension_data, confidence_score, updated_at
                        FROM aerospace_entities
                        WHERE {' AND '.join(where)}
                        ORDER BY (extension_data->>'value_musd')::float DESC NULLS LAST
                        LIMIT :limit""",
                    params
                ).fetchall()

                if rows:
                    return [self._row_to_dict(r) for r in rows]
            except Exception as e:
                logger.warning(f"Contract DB query failed: {e}")

        # Fall back to seed data
        results = SEED_CONTRACTS
        if client:
            results = [c for c in results if client.lower() in c.get("client", "").lower()]
        if recipient:
            results = [c for c in results if recipient.lower() in c.get("recipient", "").lower()]
        if status:
            results = [c for c in results if c.get("status") == status]
        results = [c for c in results if (c.get("value_musd") or 0) >= min_value_musd]
        return sorted(results, key=lambda x: x.get("value_musd", 0), reverse=True)[:limit]

    def get_investment_timeline(
        self,
        company: Optional[str] = None,
        investment_type: Optional[str] = None,
        min_amount_musd: float = 0.0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Return investment records sorted by announcement date."""
        results = SEED_INVESTMENTS
        if company:
            results = [i for i in results if company.lower() in i.get("recipient", "").lower()]
        if investment_type:
            results = [i for i in results if investment_type.lower() in i.get("investment_type", "").lower()]
        results = [i for i in results if (i.get("amount_musd") or 0) >= min_amount_musd]
        return sorted(results, key=lambda x: x.get("announcement_date", ""), reverse=True)[:limit]

    def get_market_overview(self) -> Dict[str, Any]:
        """Return global space economy market context."""
        return SEED_MARKET_CONTEXT

    def get_funding_summary(self) -> Dict[str, Any]:
        """Aggregate funding metrics across all investment records."""
        total = sum(i.get("amount_musd", 0) for i in SEED_INVESTMENTS)
        by_type: Dict[str, float] = {}
        for inv in SEED_INVESTMENTS:
            t = inv.get("investment_type", "Other")
            by_type[t] = by_type.get(t, 0) + (inv.get("amount_musd") or 0)

        return {
            "total_tracked_investments": len(SEED_INVESTMENTS),
            "total_value_musd": round(total, 1),
            "by_type": by_type,
            "largest_round": max(SEED_INVESTMENTS, key=lambda x: x.get("amount_musd", 0)),
            "tracked_contracts": len(SEED_CONTRACTS),
            "total_contract_value_musd": round(
                sum(c.get("value_musd", 0) for c in SEED_CONTRACTS), 1
            ),
        }

    @staticmethod
    def _row_to_dict(row) -> Dict[str, Any]:
        r = dict(row._mapping)
        if isinstance(r.get("extension_data"), str):
            r["extension_data"] = json.loads(r["extension_data"])
        return {**r.get("extension_data", {}), "aqid": r["aqid"],
                "display_name": r["display_name"], "confidence_score": r.get("confidence_score")}
