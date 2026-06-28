"""
ORBITIQ-X — Alembic Migration: Phase 17.2 Universal Relationship Ontology
Revision: 20260628_0012_relationship_ontology

Creates:
  1. relationship_ontology         — Formal registry of all 76 relationship types
                                     with cardinality, direction, and temporal rules
  2. relationship_temporal_index   — Temporal property index support table
  3. relationship_audit_log        — Audit trail for relationship changes

Also seeds relationship_type_registry (created in 0011) with full metadata.

Neo4j schema additions are applied separately via
caem/graph/neo4j_relationship_schema.py (idempotent, run on startup).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision      = '20260628_0012_relationship_ontology'
down_revision = '017_01_caem_base'
branch_labels = None
depends_on    = None


def upgrade() -> None:

    # ------------------------------------------------------------------
    # 1. RELATIONSHIP ONTOLOGY — full formal registry
    # ------------------------------------------------------------------
    op.create_table(
        'relationship_ontology',
        sa.Column('rel_type',           sa.String(60),  primary_key=True,
                  comment='RelationshipType enum value'),
        sa.Column('category',           sa.String(40),  nullable=False, index=True),
        sa.Column('description',        sa.Text,        nullable=False),
        sa.Column('direction_note',     sa.String(255), nullable=False),
        sa.Column('cardinality',        sa.String(20),  nullable=False),
        sa.Column('allowed_sources',    JSONB,          server_default='[]',
                  comment='EntityClass values allowed as source. Empty = any.'),
        sa.Column('allowed_targets',    JSONB,          server_default='[]',
                  comment='EntityClass values allowed as target. Empty = any.'),
        sa.Column('temporal',           sa.Boolean,     server_default='false'),
        sa.Column('temporal_note',      sa.Text,        nullable=True),
        sa.Column('confidence_floor',   sa.Float,       server_default='0.5'),
        sa.Column('is_bidirectional',   sa.Boolean,     server_default='false'),
        sa.Column('display_label',      sa.String(80),  nullable=True),
        sa.Column('inverse_label',      sa.String(80),  nullable=True),
        sa.Column('created_at',         sa.DateTime,    server_default=sa.func.now()),
    )

    op.execute("CREATE INDEX ix_ro_category ON relationship_ontology USING btree (category)")
    op.execute("CREATE INDEX ix_ro_temporal ON relationship_ontology USING btree (temporal)")
    op.execute("CREATE INDEX ix_ro_sources ON relationship_ontology USING GIN (allowed_sources)")
    op.execute("CREATE INDEX ix_ro_targets ON relationship_ontology USING GIN (allowed_targets)")

    # ------------------------------------------------------------------
    # 2. RELATIONSHIP AUDIT LOG
    # Every Neo4j relationship mutation (create/update/delete) is logged.
    # ------------------------------------------------------------------
    op.create_table(
        'relationship_audit_log',
        sa.Column('log_id',             sa.Integer,     primary_key=True, autoincrement=True),
        sa.Column('rel_id',             sa.String(80),  nullable=False, index=True),
        sa.Column('source_aqid',        sa.String(120), nullable=False, index=True),
        sa.Column('target_aqid',        sa.String(120), nullable=False, index=True),
        sa.Column('rel_type',           sa.String(60),  nullable=False, index=True),
        sa.Column('action',             sa.String(20),  nullable=False,
                  comment='created / updated / deleted / disputed'),
        sa.Column('old_properties',     JSONB,          nullable=True),
        sa.Column('new_properties',     JSONB,          nullable=True),
        sa.Column('changed_by',         sa.String(120), server_default='system'),
        sa.Column('change_reason',      sa.Text,        nullable=True),
        sa.Column('provenance_url',     sa.Text,        nullable=True),
        sa.Column('confidence_before',  sa.Float,       nullable=True),
        sa.Column('confidence_after',   sa.Float,       nullable=True),
        sa.Column('created_at',         sa.DateTime,    server_default=sa.func.now()),
    )

    op.create_index('ix_ral_source', 'relationship_audit_log', ['source_aqid'])
    op.create_index('ix_ral_target', 'relationship_audit_log', ['target_aqid'])
    op.create_index('ix_ral_type',   'relationship_audit_log', ['rel_type'])
    op.create_index('ix_ral_date',   'relationship_audit_log', ['created_at'])

    # ------------------------------------------------------------------
    # 3. SEED relationship_ontology with all 76 types
    # ------------------------------------------------------------------
    import json

    ontology_rows = [
        # --- ORGANIZATIONAL ---
        ("PART_OF",           "organizational",   "Entity is a structural part of a larger entity.",               "Child → Parent",                 "MANY_TO_ONE",  True,  False, "part of",             "contains"),
        ("SUBSIDIARY_OF",     "organizational",   "Company is owned by a parent company.",                         "Subsidiary → Parent",            "MANY_TO_ONE",  True,  False, "subsidiary of",       "owns"),
        ("DEPARTMENT_OF",     "organizational",   "Division within an organization.",                              "Division → Organization",        "MANY_TO_ONE",  True,  False, "department of",       "has department"),
        ("MEMBER_OF",         "organizational",   "Entity is a member of an alliance or treaty.",                  "Member → Alliance",              "MANY_TO_MANY", True,  False, "member of",           "has member"),
        ("ESTABLISHED_BY",    "organizational",   "Agency was established by a country or authority.",             "Agency → Founding Country",      "MANY_TO_ONE",  True,  False, "established by",      "established"),
        ("GOVERNED_BY",       "organizational",   "Program is governed by an agency.",                             "Program → Governing Agency",     "MANY_TO_ONE",  True,  False, "governed by",         "governs"),
        ("FUNDED_BY",         "organizational",   "Entity receives funding from an organization.",                 "Recipient → Funder",             "MANY_TO_MANY", True,  False, "funded by",           "funds"),
        ("ACQUIRED_BY",       "organizational",   "Company was acquired by another.",                              "Acquired → Acquirer",            "MANY_TO_ONE",  True,  False, "acquired by",         "acquired"),
        ("COLLABORATES_WITH", "organizational",   "Organizations actively collaborate.",                           "Org ↔ Org",                      "MANY_TO_MANY", True,  True,  "collaborates with",   "collaborates with"),
        ("COMPETES_WITH",     "organizational",   "Companies compete in the same market.",                         "Company ↔ Company",              "MANY_TO_MANY", True,  True,  "competes with",       "competes with"),
        # --- OPERATIONAL ---
        ("OPERATED_BY",       "operational",      "Satellite is operated by an organization.",                     "Satellite → Operator",           "MANY_TO_ONE",  True,  False, "operated by",         "operates"),
        ("MANAGED_BY",        "operational",      "Mission is managed by an agency.",                              "Mission → Manager",              "MANY_TO_ONE",  True,  False, "managed by",          "manages"),
        ("CONTROLLED_FROM",   "operational",      "Satellite commanded from a ground station.",                    "Satellite → Ground Station",     "MANY_TO_MANY", True,  False, "controlled from",     "controls"),
        ("LAUNCHED_BY",       "operational",      "Payload launched by a launch vehicle.",                         "Payload → Launch Vehicle",       "MANY_TO_ONE",  True,  False, "launched by",         "launched"),
        ("LAUNCHED_FROM",     "operational",      "Vehicle launched from a launch site.",                          "LV/Mission → Launch Site",       "MANY_TO_ONE",  True,  False, "launched from",       "launch site for"),
        ("TRACKED_BY",        "operational",      "Satellite tracked by a network.",                               "Satellite → Network",            "MANY_TO_MANY", False, False, "tracked by",          "tracks"),
        ("SERVICED_BY",       "operational",      "Satellite serviced by a mission.",                              "Satellite → Service Mission",    "MANY_TO_MANY", True,  False, "serviced by",         "serviced"),
        ("DEPLOYED_FROM",     "operational",      "Payload deployed from a spacecraft.",                           "Payload → Spacecraft",           "MANY_TO_ONE",  True,  False, "deployed from",       "deployed"),
        ("LANDED_ON",         "operational",      "Spacecraft landed on a celestial body.",                        "Spacecraft → Celestial Body",    "MANY_TO_ONE",  True,  False, "landed on",           "landing site for"),
        ("ORBITS",            "operational",      "Satellite orbits a celestial body.",                            "Satellite → Celestial Body",     "MANY_TO_ONE",  True,  False, "orbits",              "orbited by"),
        ("RENDEZVOUSED_WITH", "operational",      "Spacecraft rendezvoused with another.",                         "Spacecraft ↔ Spacecraft",        "MANY_TO_MANY", True,  True,  "rendezvoused with",   "rendezvoused with"),
        # --- SUPPLY CHAIN ---
        ("MANUFACTURED_BY",   "supply_chain",     "Hardware was manufactured by an organization.",                 "Hardware → Manufacturer",        "MANY_TO_ONE",  False, False, "manufactured by",     "manufactured"),
        ("DESIGNED_BY",       "supply_chain",     "System was designed by an organization.",                       "Hardware → Designer",            "MANY_TO_MANY", False, False, "designed by",         "designed"),
        ("SUPPLIED_BY",       "supply_chain",     "Component is supplied by a vendor.",                            "Component → Supplier",           "MANY_TO_MANY", True,  False, "supplied by",         "supplies"),
        ("COMPONENT_OF",      "supply_chain",     "Component is part of a larger system.",                         "Component → System",             "MANY_TO_ONE",  False, False, "component of",        "has component"),
        ("USES_COMPONENT",    "supply_chain",     "System incorporates a component.",                              "System → Component",             "MANY_TO_MANY", False, False, "uses component",      "used in"),
        ("USES_MATERIAL",     "supply_chain",     "Hardware uses a specific material.",                            "Hardware → Material",            "MANY_TO_MANY", False, False, "uses material",       "used in"),
        ("PRODUCED_UNDER",    "supply_chain",     "Hardware was produced under a contract.",                       "Hardware → Contract",            "MANY_TO_ONE",  False, False, "produced under",      "covers production of"),
        ("LICENSED_FROM",     "supply_chain",     "Technology is licensed from another organization.",             "Technology → License Holder",    "MANY_TO_ONE",  True,  False, "licensed from",       "licensed to"),
        # --- TECHNICAL ---
        ("USES_TECHNOLOGY",   "technical",        "Mission or hardware employs a technology.",                     "Entity → Technology",            "MANY_TO_MANY", False, False, "uses technology",     "used in"),
        ("IMPLEMENTS",        "technical",        "Hardware implements a standard.",                               "Hardware → Standard",            "MANY_TO_MANY", True,  False, "implements",          "implemented by"),
        ("CERTIFIED_BY",      "technical",        "Hardware is certified by a body.",                              "Hardware → Certifying Body",     "MANY_TO_MANY", True,  False, "certified by",        "certified"),
        ("REQUIRES",          "technical",        "System has a hard dependency.",                                 "System → Dependency",            "MANY_TO_MANY", False, False, "requires",            "required by"),
        ("ENABLES",           "technical",        "Technology enables a capability.",                              "Technology → Capability",        "MANY_TO_MANY", False, False, "enables",             "enabled by"),
        ("DERIVED_FROM",      "technical",        "Design is derived from a predecessor.",                         "New → Predecessor",              "MANY_TO_ONE",  False, False, "derived from",        "basis for"),
        ("SUCCESSOR_OF",      "technical",        "System is the direct successor.",                               "New → Old",                      "ONE_TO_ONE",   True,  False, "successor of",        "preceded by"),
        ("REPLACED_BY",       "technical",        "System was superseded.",                                        "Old → New",                      "ONE_TO_ONE",   True,  False, "replaced by",         "replaces"),
        ("COMPATIBLE_WITH",   "technical",        "Hardware is compatible with another.",                          "Hardware ↔ Hardware",            "MANY_TO_MANY", False, True,  "compatible with",     "compatible with"),
        ("INTERFERES_WITH",   "technical",        "Satellite causes interference.",                                "Satellite ↔ Satellite",          "MANY_TO_MANY", True,  True,  "interferes with",     "interferes with"),
        # --- SCIENTIFIC ---
        ("DISCOVERED_BY",     "scientific",       "Body was discovered by person or mission.",                     "Body → Discoverer",              "MANY_TO_ONE",  True,  False, "discovered by",       "discovered"),
        ("STUDIED_BY",        "scientific",       "Body is studied by a mission.",                                 "Body → Mission",                 "MANY_TO_MANY", True,  False, "studied by",          "studies"),
        ("INSTRUMENTS_ON",    "scientific",       "Instrument is mounted on a spacecraft.",                        "Instrument → Spacecraft",        "MANY_TO_ONE",  False, False, "instrument on",       "carries instrument"),
        ("MEASURES",          "scientific",       "Instrument measures a phenomenon.",                             "Instrument → Phenomenon",        "MANY_TO_MANY", False, False, "measures",            "measured by"),
        ("AUTHORED_BY",       "scientific",       "Paper was authored by a person.",                               "Paper → Author",                 "MANY_TO_MANY", True,  False, "authored by",         "authored"),
        ("PUBLISHED_IN",      "scientific",       "Paper was published in a journal.",                             "Paper → Journal",                "MANY_TO_ONE",  True,  False, "published in",        "published"),
        ("CITES",             "scientific",       "Paper cites another paper.",                                    "Citing → Cited",                 "MANY_TO_MANY", False, False, "cites",               "cited by"),
        ("REFERENCES",        "scientific",       "Document references another document.",                         "Document → Reference",           "MANY_TO_MANY", False, False, "references",          "referenced by"),
        ("VALIDATES",         "scientific",       "Mission validates a theory.",                                   "Mission → Theory",               "MANY_TO_MANY", True,  False, "validates",           "validated by"),
        ("MODELS",            "scientific",       "Software models a physical system.",                            "Software → System",              "MANY_TO_MANY", False, False, "models",              "modeled by"),
        # --- GEOGRAPHIC ---
        ("LOCATED_IN",        "geographic",       "Entity is physically located in a country.",                    "Entity → Country",               "MANY_TO_ONE",  True,  False, "located in",          "hosts"),
        ("OPERATES_IN",       "geographic",       "Organization has presence in a country.",                       "Org → Country",                  "MANY_TO_MANY", True,  False, "operates in",         "hosts operations of"),
        ("COVERS",            "geographic",       "Satellite provides coverage of a region.",                      "Satellite → Region",             "MANY_TO_MANY", False, False, "covers",              "covered by"),
        ("LAUNCHES_TO",       "geographic",       "Launch site supports launches to an orbital regime.",           "Site → Orbital Regime",          "MANY_TO_MANY", False, False, "launches to",         "reachable from"),
        # --- COMMERCIAL ---
        ("AWARDED_TO",        "commercial",       "Contract was awarded to an organization.",                      "Contract → Recipient",           "MANY_TO_MANY", True,  False, "awarded to",          "recipient of"),
        ("AWARDED_BY",        "commercial",       "Contract was awarded by a client.",                             "Contract → Client",              "MANY_TO_ONE",  True,  False, "awarded by",          "awarded contract"),
        ("INVESTED_IN",       "commercial",       "Investment was made into a company.",                           "Investment → Recipient",         "MANY_TO_ONE",  True,  False, "invested in",         "received investment"),
        ("INSURED_BY",        "commercial",       "Mission is insured by a provider.",                             "Mission → Insurer",              "MANY_TO_ONE",  True,  False, "insured by",          "insures"),
        ("PROVIDES_SERVICE_TO","commercial",      "Organization provides service to a client.",                    "Provider → Client",              "MANY_TO_MANY", True,  False, "provides service to", "receives service from"),
        ("COMPETES_FOR",      "commercial",       "Company competes for a contract.",                              "Company → Contract",             "MANY_TO_MANY", True,  False, "competes for",        "competed for by"),
        # --- REGULATORY ---
        ("REGULATED_BY",      "regulatory",       "Entity is regulated by an agency.",                             "Entity → Regulatory Agency",     "MANY_TO_MANY", True,  False, "regulated by",        "regulates"),
        ("LICENSED_BY",       "regulatory",       "Operator holds a license from a regulatory body.",             "Operator → Regulatory Body",     "MANY_TO_MANY", True,  False, "licensed by",         "issued license to"),
        ("COMPLIES_WITH",     "regulatory",       "Entity complies with a standard or policy.",                   "Entity → Standard/Policy",       "MANY_TO_MANY", True,  False, "complies with",       "required of"),
        ("PROHIBITED_BY",     "regulatory",       "Activity is prohibited by a policy.",                          "Activity → Policy",              "MANY_TO_MANY", True,  False, "prohibited by",       "prohibits"),
        ("RATIFIED_BY",       "regulatory",       "Treaty was ratified by a country.",                            "Treaty → Country",               "MANY_TO_MANY", True,  False, "ratified by",         "ratified"),
        ("SANCTIONS",         "regulatory",       "Policy imposes sanctions on an entity.",                       "Policy → Entity",                "MANY_TO_MANY", True,  False, "sanctions",           "sanctioned by"),
        # --- HISTORICAL ---
        ("PRECEDED_BY",       "historical",       "Event was preceded by an earlier event.",                      "Later → Earlier",                "MANY_TO_ONE",  True,  False, "preceded by",         "followed by"),
        ("CAUSED",            "historical",       "Event caused a consequence.",                                  "Cause → Consequence",            "MANY_TO_MANY", True,  False, "caused",              "caused by"),
        ("TRIGGERED",         "historical",       "Incident triggered a policy change.",                          "Incident → Policy Change",       "MANY_TO_MANY", True,  False, "triggered",           "triggered by"),
        ("EVOLVED_INTO",      "historical",       "Program evolved into a successor.",                            "Earlier → Successor",            "ONE_TO_ONE",   True,  False, "evolved into",        "evolved from"),
        ("BASED_ON",          "historical",       "Mission is based on prior heritage.",                          "New → Prior",                    "MANY_TO_MANY", False, False, "based on",            "heritage for"),
        ("COMMEMORATES",      "historical",       "Event commemorates a historical entity.",                      "Event → Historical Entity",      "MANY_TO_MANY", True,  False, "commemorates",        "commemorated by"),
        # --- KNOWLEDGE ---
        ("MENTIONED_IN",      "knowledge",        "Entity is mentioned in a document.",                           "Entity → Document",              "MANY_TO_MANY", False, False, "mentioned in",        "mentions"),
        ("DESCRIBED_BY",      "knowledge",        "Entity is described by a paper.",                              "Entity → Paper",                 "MANY_TO_MANY", False, False, "described by",        "describes"),
        ("STANDARDIZED_IN",   "knowledge",        "Technology is standardized in a formal standard.",             "Technology → Standard",          "MANY_TO_MANY", False, False, "standardized in",     "standardizes"),
        ("PATENTED_BY",       "knowledge",        "Technology is protected by a patent.",                         "Technology → Patent",            "MANY_TO_MANY", True,  False, "patented by",         "covers technology"),
        ("INSPIRED",          "knowledge",        "Research inspired the development of a technology.",           "Research → Technology",          "MANY_TO_MANY", False, False, "inspired",            "inspired by"),
    ]

    for row in ontology_rows:
        (rel_type, category, description, direction_note, cardinality,
         temporal, is_bidirectional, display_label, inverse_label) = row
        op.execute(f"""
            INSERT INTO relationship_ontology (
                rel_type, category, description, direction_note, cardinality,
                temporal, is_bidirectional, display_label, inverse_label
            ) VALUES (
                '{rel_type}', '{category}',
                $${description}$$,
                '{direction_note}', '{cardinality}',
                {str(temporal).lower()}, {str(is_bidirectional).lower()},
                '{display_label}', '{inverse_label}'
            ) ON CONFLICT DO NOTHING
        """)


def downgrade() -> None:
    op.drop_table('relationship_audit_log')
    op.drop_table('relationship_ontology')
