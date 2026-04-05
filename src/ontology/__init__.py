"""Ontology kernel — domain-agnostic typed knowledge graph engine."""

from ontology.graph import OntologyGraph
from ontology.registry import PluginRegistry, discover_plugins
from ontology.schema import Entity, EntityRef, Predicate, QueryResult, Triple

__all__ = [
    "EntityRef",
    "Entity",
    "OntologyGraph",
    "PluginRegistry",
    "Predicate",
    "QueryResult",
    "Triple",
    "discover_plugins",
]
