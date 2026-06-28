# ORBITIQ-X CAEM Ontology Package
# Phase 17.2 — Universal Relationship Ontology

from caem.ontology.relationship_registry import (
    RelationshipDefinition,
    Cardinality,
    RELATIONSHIP_REGISTRY,
    get_definition,
    validate_relationship_classes,
    get_relationships_for_class,
    get_category_relationships,
    get_temporal_relationships,
    get_bidirectional_relationships,
)

__all__ = [
    "RelationshipDefinition",
    "Cardinality",
    "RELATIONSHIP_REGISTRY",
    "get_definition",
    "validate_relationship_classes",
    "get_relationships_for_class",
    "get_category_relationships",
    "get_temporal_relationships",
    "get_bidirectional_relationships",
]
